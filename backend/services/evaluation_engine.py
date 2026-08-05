import csv
import io
import json
import re
import time
from datetime import datetime
from statistics import mean
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.chatbot import Chatbot
from models.evaluation import EvaluationCase, EvaluationCaseResult, EvaluationDataset, EvaluationRun
from models.llm_config import LLMConfig
from models.version import VersionChatbot
from routes.chat_routes import build_rag_response
from services.flow_runtime import execute_flow
from services.runtime_contracts import RuntimeFailureCategory, sanitized_category_from_error


SCORING_POLICY = {
    "passed_threshold": 80,
    "warning_threshold": 60,
    "score_tolerance": 3,
    "critical_case_weight": 2,
    "judge_prompt_version": "evaluation-judge-v1",
}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [item.strip() for item in value.split("|") if item.strip()]
    return [value]


def _source_text(source: dict) -> str:
    return " ".join(
        str(source.get(key) or "")
        for key in ("document_id", "filename", "title", "section_type", "text")
    )


def assertion_result(
    code: str,
    label: str,
    passed: bool,
    expected: Any,
    actual: Any,
    message: str,
    weight: int = 1,
) -> dict:
    return {
        "code": code,
        "label": label,
        "status": "passed" if passed else "failed",
        "expected": expected,
        "actual": actual,
        "message": message,
        "score_contribution": weight if passed else 0,
        "weight": weight,
    }


def case_snapshot(case: EvaluationCase) -> dict:
    return {
        "id": case.id,
        "name": case.name,
        "description": case.description,
        "order_index": case.order_index,
        "input_message": case.input_message,
        "turns": case.turns or [],
        "initial_variables": case.initial_variables or {},
        "expected_response_mode": case.expected_response_mode,
        "expected_intent": case.expected_intent,
        "expected_keywords": case.expected_keywords or [],
        "forbidden_keywords": case.forbidden_keywords or [],
        "expected_source_document_ids": case.expected_source_document_ids or [],
        "expected_source_patterns": case.expected_source_patterns or [],
        "expected_flow_node_ids": case.expected_flow_node_ids or [],
        "forbidden_flow_node_ids": case.forbidden_flow_node_ids or [],
        "expected_final_node_id": case.expected_final_node_id,
        "expected_variable_assertions": case.expected_variable_assertions or [],
        "maximum_latency_ms": case.maximum_latency_ms,
        "minimum_retrieval_score": case.minimum_retrieval_score,
        "minimum_answer_score": case.minimum_answer_score,
        "minimum_source_count": case.minimum_source_count,
        "expected_fallback": case.expected_fallback,
        "expected_handoff": case.expected_handoff,
        "expected_failure_category": case.expected_failure_category,
        "critical": case.critical,
        "enabled": case.enabled,
        "tags": case.tags or [],
        "judge_config": case.judge_config or {},
    }


def dataset_snapshot(dataset: EvaluationDataset, cases: list[EvaluationCase]) -> dict:
    return {
        "schema_version": 1,
        "dataset": {
            "id": dataset.id,
            "name": dataset.name,
            "description": dataset.description,
            "status": dataset.status,
        },
        "cases": [case_snapshot(case) for case in cases],
        "scoring_policy": SCORING_POLICY,
        "captured_at": datetime.utcnow().isoformat(),
    }


def evaluate_assertions(case: EvaluationCase, runtime_result: dict, latency_ms: int, trace: dict, failure_category: str | None = None) -> tuple[str, float, list[dict]]:
    response = runtime_result.get("response") or ""
    sources = runtime_result.get("sources") or []
    variables = runtime_result.get("variables") or {}
    visited = trace.get("visited_nodes") or []
    visited_keys = [node.get("node_key") for node in visited if node.get("node_key")]
    assertions: list[dict] = []

    assertions.append(assertion_result(
        "RESPONSE_NOT_EMPTY",
        "Response is not empty",
        bool(response.strip()),
        "non-empty response",
        bool(response.strip()),
        "Assistant returned a response." if response.strip() else "Assistant response was empty.",
    ))

    expected_keywords = [str(item) for item in _as_list(case.expected_keywords)]
    if expected_keywords:
        text = _norm(response)
        missing = [keyword for keyword in expected_keywords if _norm(keyword) not in text]
        assertions.append(assertion_result(
            "REQUIRED_KEYWORDS",
            "Required keywords present",
            not missing,
            expected_keywords,
            {"missing": missing},
            "All required keywords were found." if not missing else "Required keywords were missing.",
        ))

    forbidden_keywords = [str(item) for item in _as_list(case.forbidden_keywords)]
    if forbidden_keywords:
        text = _norm(response)
        found = [keyword for keyword in forbidden_keywords if _norm(keyword) in text]
        assertions.append(assertion_result(
            "FORBIDDEN_KEYWORDS",
            "Forbidden keywords absent",
            not found,
            forbidden_keywords,
            {"found": found},
            "No forbidden keywords were found." if not found else "Forbidden keywords appeared in the response.",
        ))

    if case.expected_response_mode:
        actual_mode = runtime_result.get("mode_used") or runtime_result.get("retrieval_mode")
        assertions.append(assertion_result(
            "RESPONSE_MODE",
            "Expected response mode",
            _norm(actual_mode) == _norm(case.expected_response_mode),
            case.expected_response_mode,
            actual_mode,
            "Response mode matched." if _norm(actual_mode) == _norm(case.expected_response_mode) else "Response mode did not match.",
        ))

    expected_doc_ids = {str(item) for item in _as_list(case.expected_source_document_ids)}
    if expected_doc_ids:
        actual_doc_ids = {str(source.get("document_id")) for source in sources if source.get("document_id") is not None}
        missing = sorted(expected_doc_ids - actual_doc_ids)
        assertions.append(assertion_result(
            "REQUIRED_SOURCE_DOCUMENT",
            "Required source document",
            not missing,
            sorted(expected_doc_ids),
            sorted(actual_doc_ids),
            "Required documents were retrieved." if not missing else "Required source documents were not retrieved.",
        ))

    source_patterns = [str(item) for item in _as_list(case.expected_source_patterns)]
    if source_patterns:
        source_blob = "\n".join(_source_text(source) for source in sources)
        missing_patterns = []
        for pattern in source_patterns:
            if not re.search(pattern, source_blob, flags=re.IGNORECASE):
                missing_patterns.append(pattern)
        assertions.append(assertion_result(
            "SOURCE_PATTERN",
            "Required source pattern",
            not missing_patterns,
            source_patterns,
            {"missing": missing_patterns},
            "Required source patterns matched." if not missing_patterns else "Required source patterns were missing.",
        ))

    if case.minimum_source_count is not None:
        assertions.append(assertion_result(
            "MINIMUM_SOURCE_COUNT",
            "Minimum source count",
            len(sources) >= case.minimum_source_count,
            case.minimum_source_count,
            len(sources),
            "Enough sources were returned." if len(sources) >= case.minimum_source_count else "Not enough sources were returned.",
        ))

    if case.minimum_retrieval_score is not None:
        scores = [float(source.get("score") or 0) for source in sources]
        top_score = max(scores) if scores else 0
        assertions.append(assertion_result(
            "MINIMUM_RETRIEVAL_SCORE",
            "Minimum retrieval score",
            top_score >= case.minimum_retrieval_score,
            case.minimum_retrieval_score,
            top_score,
            "Retrieval score met the threshold." if top_score >= case.minimum_retrieval_score else "Retrieval score was below threshold.",
        ))

    expected_nodes = [str(item) for item in _as_list(case.expected_flow_node_ids)]
    if expected_nodes:
        missing = [node_id for node_id in expected_nodes if node_id not in visited_keys]
        assertions.append(assertion_result(
            "EXPECTED_FLOW_NODE",
            "Expected flow node visited",
            not missing,
            expected_nodes,
            visited_keys,
            "Expected flow nodes were visited." if not missing else "Expected flow nodes were not visited.",
        ))

    forbidden_nodes = [str(item) for item in _as_list(case.forbidden_flow_node_ids)]
    if forbidden_nodes:
        found = [node_id for node_id in forbidden_nodes if node_id in visited_keys]
        assertions.append(assertion_result(
            "FORBIDDEN_FLOW_NODE",
            "Forbidden flow node not visited",
            not found,
            forbidden_nodes,
            visited_keys,
            "Forbidden flow nodes were not visited." if not found else "Forbidden flow nodes were visited.",
        ))

    if case.expected_final_node_id:
        actual_final = runtime_result.get("current_node_key") or (visited_keys[-1] if visited_keys else None)
        assertions.append(assertion_result(
            "EXPECTED_FINAL_NODE",
            "Expected final node",
            str(actual_final or "") == str(case.expected_final_node_id),
            case.expected_final_node_id,
            actual_final,
            "Final node matched." if str(actual_final or "") == str(case.expected_final_node_id) else "Final node did not match.",
        ))

    for index, item in enumerate(_as_list(case.expected_variable_assertions), start=1):
        if not isinstance(item, dict):
            continue
        field = item.get("field") or item.get("name")
        operator = item.get("operator") or "equals"
        expected = item.get("value")
        actual = variables.get(field) if field else None
        if operator == "exists":
            passed = actual is not None and str(actual).strip() != ""
        else:
            passed = actual == expected
        assertions.append(assertion_result(
            f"VARIABLE_ASSERTION_{index}",
            f"Variable {field}",
            passed,
            item,
            actual,
            "Variable assertion passed." if passed else "Variable assertion failed.",
        ))

    if case.maximum_latency_ms is not None:
        assertions.append(assertion_result(
            "MAXIMUM_LATENCY",
            "Maximum latency",
            latency_ms <= case.maximum_latency_ms,
            case.maximum_latency_ms,
            latency_ms,
            "Latency was within the threshold." if latency_ms <= case.maximum_latency_ms else "Latency exceeded the threshold.",
        ))

    if case.expected_fallback is not None:
        actual = runtime_result.get("mode_used") == "fallback"
        assertions.append(assertion_result(
            "EXPECTED_FALLBACK",
            "Expected fallback",
            actual == bool(case.expected_fallback),
            bool(case.expected_fallback),
            actual,
            "Fallback expectation matched." if actual == bool(case.expected_fallback) else "Fallback expectation did not match.",
        ))

    if case.expected_handoff is not None:
        actual = bool(variables.get("__handoff_requested") or variables.get("__handoff") or variables.get("handoff"))
        assertions.append(assertion_result(
            "EXPECTED_HANDOFF",
            "Expected handoff",
            actual == bool(case.expected_handoff),
            bool(case.expected_handoff),
            actual,
            "Handoff expectation matched." if actual == bool(case.expected_handoff) else "Handoff expectation did not match.",
        ))

    if case.expected_failure_category:
        assertions.append(assertion_result(
            "EXPECTED_FAILURE_CATEGORY",
            "Expected outcome category",
            _norm(failure_category) == _norm(case.expected_failure_category),
            case.expected_failure_category,
            failure_category,
            "Failure category matched." if _norm(failure_category) == _norm(case.expected_failure_category) else "Failure category did not match.",
        ))
    else:
        assertions.append(assertion_result(
            "NO_TECHNICAL_FAILURE",
            "Runtime completed without technical failure",
            failure_category is None,
            "no technical failure",
            failure_category,
            "Runtime completed without a technical failure." if failure_category is None else "Runtime produced a technical failure.",
        ))

    total_weight = sum(item["weight"] for item in assertions) or 1
    earned = sum(item["score_contribution"] for item in assertions)
    score = round((earned / total_weight) * 100, 2)
    failed_assertions = [item for item in assertions if item["status"] != "passed"]
    if failure_category and not case.expected_failure_category:
        status = "error"
    elif failed_assertions and case.critical:
        status = "failed"
    elif score >= SCORING_POLICY["passed_threshold"]:
        status = "passed"
    elif score >= SCORING_POLICY["warning_threshold"]:
        status = "warning"
    else:
        status = "failed"
    return status, score, assertions


def execute_evaluation_case(db: Session, chatbot: Chatbot, version: VersionChatbot, config: LLMConfig, run: EvaluationRun, case: EvaluationCase) -> EvaluationCaseResult:
    started_at = time.perf_counter()
    variables = {
        **(case.initial_variables or {}),
        "__language": chatbot.language or "en",
        "__evaluation_run_id": run.id,
        "__evaluation_case_id": case.id,
    }
    trace = {
        "evaluation_run_id": run.id,
        "evaluation_case_id": case.id,
        "assistant_id": chatbot.id,
        "version_id": version.id,
    }
    runtime_result: dict = {}
    failure_category = None
    error_message = None
    current_node_key = None
    turns = case.turns or []
    messages = [
        str(turn.get("message", "")) if isinstance(turn, dict) else str(turn or "")
        for turn in turns
    ] or [case.input_message]

    def rag_answer(query: str, fallback_variables: dict | None = None, node_config: dict | None = None):
        return build_rag_response(
            db=db,
            version=version,
            config=config,
            message=query or case.input_message,
            variables=fallback_variables or variables,
            history=[],
            mode_used="evaluation_rag",
            node_config=node_config,
        )

    try:
        for index, turn_message in enumerate(messages, start=1):
            trace.setdefault("turns", []).append({"turn": index, "message_present": bool(turn_message.strip())})
            runtime_result = execute_flow(
                db=db,
                version_id=version.id,
                message=turn_message,
                current_node_key=current_node_key,
                variables=variables,
                rag_answer=rag_answer,
                allow_rag_fallback=False,
                trace=trace,
            )
            variables = runtime_result.get("variables") or variables
            current_node_key = runtime_result.get("current_node_key")
            runtime_error = runtime_result.get("runtime_error")
            if runtime_error:
                failure_category = runtime_error.get("category") or RuntimeFailureCategory.INVALID_FLOW.value
                error_message = runtime_error.get("message")
                break
    except Exception as exc:
        failure_category = sanitized_category_from_error(exc).value
        error_message = str(getattr(exc, "detail", None) or exc)[:500]

    latency_ms = max(0, round((time.perf_counter() - started_at) * 1000))
    status, score, assertions = evaluate_assertions(case, runtime_result, latency_ms, trace, failure_category)
    result = EvaluationCaseResult(
        run_id=run.id,
        case_id=case.id,
        status=status,
        score=score,
        case_snapshot=case_snapshot(case),
        actual_response=runtime_result.get("response") or "",
        actual_response_mode=runtime_result.get("mode_used") or runtime_result.get("retrieval_mode"),
        actual_sources=runtime_result.get("sources") or [],
        actual_visited_nodes=trace.get("visited_nodes") or [],
        actual_variables=runtime_result.get("variables") or variables,
        latency_ms=latency_ms,
        runtime_execution_id=f"eval-{run.id}-{case.id}",
        failure_category=failure_category,
        assertion_results=assertions,
        judge_result={
            "enabled": False,
            "message": "LLM-as-judge is disabled by default for this run.",
            "prompt_version": SCORING_POLICY["judge_prompt_version"],
        },
        error_message_sanitized=error_message,
    )
    db.add(result)
    db.flush()
    return result


def run_dataset_evaluation(
    db: Session,
    dataset: EvaluationDataset,
    version: VersionChatbot,
    chatbot: Chatbot,
    user_id: int | None,
    trigger_type: str = "manual",
    evaluator_configuration: dict | None = None,
) -> EvaluationRun:
    if dataset.status == "archived":
        raise HTTPException(status_code=400, detail="Archived datasets cannot be run until restored.")
    if dataset.assistant_id != chatbot.id or version.chatbot_id != chatbot.id:
        raise HTTPException(status_code=400, detail="Dataset and version must belong to the same assistant.")

    config = db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()
    if not config:
        raise HTTPException(status_code=400, detail="Assistant version has no LLM configuration.")

    cases = db.query(EvaluationCase).filter(
        EvaluationCase.dataset_id == dataset.id,
        EvaluationCase.enabled.is_(True),
    ).order_by(EvaluationCase.order_index.asc(), EvaluationCase.id.asc()).all()
    if not cases:
        raise HTTPException(status_code=400, detail="Dataset has no enabled evaluation cases.")

    started_at = datetime.utcnow()
    run = EvaluationRun(
        assistant_id=chatbot.id,
        dataset_id=dataset.id,
        version_id=version.id,
        status="running",
        triggered_by=user_id,
        trigger_type=trigger_type,
        total_cases=len(cases),
        runtime_mode=chatbot.mode or chatbot.type or "builder",
        evaluator_configuration={
            "deterministic_only": True,
            "judge_enabled": False,
            **(evaluator_configuration or {}),
        },
        dataset_snapshot=dataset_snapshot(dataset, cases),
        started_at=started_at,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        for case in cases:
            execute_evaluation_case(db, chatbot, version, config, run, case)
            db.commit()

        results = db.query(EvaluationCaseResult).filter(EvaluationCaseResult.run_id == run.id).all()
        run.passed_cases = sum(1 for item in results if item.status == "passed")
        run.warning_cases = sum(1 for item in results if item.status == "warning")
        run.failed_cases = sum(1 for item in results if item.status in {"failed", "error"})
        run.critical_failures = sum(
            1 for item in results
            if item.status in {"failed", "error"} and (item.case_snapshot or {}).get("critical")
        )
        weighted_scores = []
        for item in results:
            weight = SCORING_POLICY["critical_case_weight"] if (item.case_snapshot or {}).get("critical") else 1
            weighted_scores.extend([item.score or 0] * weight)
        run.overall_score = round(mean(weighted_scores), 2) if weighted_scores else 0
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        run.duration_ms = max(0, round((run.completed_at - started_at).total_seconds() * 1000))
    except Exception as exc:
        run.status = "failed"
        run.error_summary = str(getattr(exc, "detail", None) or exc)[:500]
        run.completed_at = datetime.utcnow()
        run.duration_ms = max(0, round((run.completed_at - started_at).total_seconds() * 1000))
    db.commit()
    db.refresh(run)
    return run


def serialize_dataset(dataset: EvaluationDataset, include_cases: bool = False) -> dict:
    data = {
        "id": dataset.id,
        "assistant_id": dataset.assistant_id,
        "name": dataset.name,
        "description": dataset.description,
        "status": dataset.status,
        "created_by": dataset.created_by,
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
    }
    if include_cases:
        data["cases"] = [serialize_case(case) for case in sorted(dataset.cases, key=lambda item: (item.order_index or 0, item.id or 0))]
    return data


def serialize_case(case: EvaluationCase) -> dict:
    return case_snapshot(case) | {
        "dataset_id": case.dataset_id,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
    }


def serialize_run(run: EvaluationRun) -> dict:
    return {
        "id": run.id,
        "assistant_id": run.assistant_id,
        "dataset_id": run.dataset_id,
        "version_id": run.version_id,
        "status": run.status,
        "triggered_by": run.triggered_by,
        "trigger_type": run.trigger_type,
        "total_cases": run.total_cases,
        "passed_cases": run.passed_cases,
        "warning_cases": run.warning_cases,
        "failed_cases": run.failed_cases,
        "critical_failures": run.critical_failures,
        "overall_score": run.overall_score,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "duration_ms": run.duration_ms,
        "runtime_mode": run.runtime_mode,
        "evaluator_configuration": run.evaluator_configuration or {},
        "error_summary": run.error_summary,
        "created_at": run.created_at,
    }


def serialize_result(result: EvaluationCaseResult) -> dict:
    return {
        "id": result.id,
        "run_id": result.run_id,
        "case_id": result.case_id,
        "status": result.status,
        "score": result.score,
        "case_snapshot": result.case_snapshot or {},
        "actual_response": result.actual_response,
        "actual_response_mode": result.actual_response_mode,
        "actual_sources": result.actual_sources or [],
        "actual_visited_nodes": result.actual_visited_nodes or [],
        "actual_variables": result.actual_variables or {},
        "latency_ms": result.latency_ms,
        "runtime_execution_id": result.runtime_execution_id,
        "failure_category": result.failure_category,
        "assertion_results": result.assertion_results or [],
        "judge_result": result.judge_result,
        "error_message_sanitized": result.error_message_sanitized,
        "created_at": result.created_at,
    }


def compare_runs(db: Session, baseline: EvaluationRun, candidate: EvaluationRun) -> dict:
    baseline_results = db.query(EvaluationCaseResult).filter(EvaluationCaseResult.run_id == baseline.id).all()
    candidate_results = db.query(EvaluationCaseResult).filter(EvaluationCaseResult.run_id == candidate.id).all()
    baseline_by_case = {item.case_id: item for item in baseline_results}
    candidate_by_case = {item.case_id: item for item in candidate_results}
    case_ids = sorted(set(baseline_by_case) | set(candidate_by_case))
    tolerance = SCORING_POLICY["score_tolerance"]
    cases = []
    regressions = 0
    fixed = 0
    improved = 0
    for case_id in case_ids:
        before = baseline_by_case.get(case_id)
        after = candidate_by_case.get(case_id)
        if not before or not after:
            state = "not_comparable"
            reason = "Case exists in only one run."
        elif before.status == "passed" and after.status in {"warning", "failed", "error"}:
            state = "regressed"
            reason = "Previously passed case no longer passes."
        elif before.status == "warning" and after.status in {"failed", "error"}:
            state = "regressed"
            reason = "Previously warning case now fails or errors."
        elif (before.score or 0) - (after.score or 0) > tolerance:
            state = "regressed"
            reason = "Score decreased beyond tolerance."
        elif before.status in {"failed", "error", "warning"} and after.status == "passed":
            state = "fixed"
            reason = "Previously non-passing case now passes."
        elif (after.score or 0) - (before.score or 0) > tolerance:
            state = "improved"
            reason = "Score increased beyond tolerance."
        else:
            state = "unchanged"
            reason = "No material change."
        regressions += 1 if state == "regressed" else 0
        fixed += 1 if state == "fixed" else 0
        improved += 1 if state == "improved" else 0
        cases.append({
            "case_id": case_id,
            "case_name": ((after or before).case_snapshot or {}).get("name"),
            "state": state,
            "reason": reason,
            "baseline_status": before.status if before else None,
            "candidate_status": after.status if after else None,
            "baseline_score": before.score if before else None,
            "candidate_score": after.score if after else None,
        })
    return {
        "baseline_run_id": baseline.id,
        "candidate_run_id": candidate.id,
        "same_dataset": baseline.dataset_id == candidate.dataset_id,
        "overall_score_delta": round((candidate.overall_score or 0) - (baseline.overall_score or 0), 2),
        "pass_rate_delta": candidate.passed_cases - baseline.passed_cases,
        "critical_failure_delta": candidate.critical_failures - baseline.critical_failures,
        "duration_delta_ms": (candidate.duration_ms or 0) - (baseline.duration_ms or 0),
        "regressions": regressions,
        "fixed_cases": fixed,
        "improved_cases": improved,
        "cases": cases,
    }


def export_dataset_json(dataset: EvaluationDataset, cases: list[EvaluationCase]) -> dict:
    return {
        "schema_version": 1,
        "dataset": {
            "name": dataset.name,
            "description": dataset.description,
        },
        "cases": [case_snapshot(case) for case in cases],
    }


def export_dataset_csv(cases: list[EvaluationCase]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "name",
        "input_message",
        "expected_keywords",
        "forbidden_keywords",
        "expected_sources",
        "maximum_latency_ms",
        "critical",
        "tags",
    ])
    writer.writeheader()
    for case in cases:
        writer.writerow({
            "name": case.name,
            "input_message": case.input_message,
            "expected_keywords": "|".join(_as_list(case.expected_keywords)),
            "forbidden_keywords": "|".join(_as_list(case.forbidden_keywords)),
            "expected_sources": "|".join(str(item) for item in _as_list(case.expected_source_document_ids)),
            "maximum_latency_ms": case.maximum_latency_ms or "",
            "critical": "true" if case.critical else "false",
            "tags": "|".join(_as_list(case.tags)),
        })
    return output.getvalue()


def parse_import_payload(content: str, format_name: str) -> list[dict]:
    if format_name == "json":
        parsed = json.loads(content)
        if int(parsed.get("schema_version", 0)) != 1:
            raise ValueError("Unsupported evaluation import schema_version.")
        cases = parsed.get("cases")
        if not isinstance(cases, list):
            raise ValueError("JSON import must contain a cases array.")
        return cases
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for row in reader:
        rows.append({
            "name": row.get("name"),
            "input_message": row.get("input_message"),
            "turns": row.get("turns") or [],
            "expected_keywords": _as_list(row.get("expected_keywords")),
            "forbidden_keywords": _as_list(row.get("forbidden_keywords")),
            "expected_source_document_ids": _as_list(row.get("expected_sources")),
            "maximum_latency_ms": int(row["maximum_latency_ms"]) if (row.get("maximum_latency_ms") or "").strip() else None,
            "critical": _norm(row.get("critical")) in {"true", "1", "yes"},
            "tags": _as_list(row.get("tags")),
        })
    return rows
