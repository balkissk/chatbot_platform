import time
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.chatbot import Chatbot
from models.chatbot_channel import ChatbotChannel
from models.chunk import Chunk
from models.document import Document
from models.evaluation import EvaluationPolicy, EvaluationRun
from models.flow import Flow, FlowNode
from models.knowledge_base import KnowledgeBase
from models.llm_config import LLMConfig
from models.version import VersionChatbot
from models.version_smoke_test import VersionSmokeTest
from routes.chat_routes import build_rag_response
from services.flow_runtime import execute_flow
from services.flow_validation import validate_flow_version
from services.runtime_contracts import RuntimeFailureCategory, sanitized_category_from_error


def latest_completed_evaluation(db: Session, version_id: int, dataset_id: int | None = None) -> EvaluationRun | None:
    query = db.query(EvaluationRun).filter(
        EvaluationRun.version_id == version_id,
        EvaluationRun.status == "completed",
    )
    if dataset_id:
        query = query.filter(EvaluationRun.dataset_id == dataset_id)
    return query.order_by(EvaluationRun.completed_at.desc(), EvaluationRun.id.desc()).first()


def evaluation_readiness_check(db: Session, version: VersionChatbot, chatbot: Chatbot) -> dict | None:
    policy = db.query(EvaluationPolicy).filter(EvaluationPolicy.assistant_id == chatbot.id).first()
    if not policy or not policy.required_before_publish:
        return None

    run = latest_completed_evaluation(db, version.id, policy.required_dataset_id)
    metadata = {
        "required_dataset_id": policy.required_dataset_id,
        "minimum_score": policy.minimum_score,
        "maximum_failed_cases": policy.maximum_failed_cases,
        "critical_failures_allowed": policy.critical_failures_allowed,
        "maximum_evaluation_age_hours": policy.maximum_evaluation_age_hours,
    }
    if not run:
        return readiness_item(
            "EVALUATION_REQUIRED",
            "Required evaluation completed",
            "BLOCKED",
            "Run the required evaluation dataset on this exact version before publishing.",
            "evaluations",
            metadata,
        )

    metadata.update({
        "run_id": run.id,
        "score": run.overall_score,
        "failed_cases": run.failed_cases,
        "critical_failures": run.critical_failures,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    })
    blockers = []
    if (run.overall_score or 0) < policy.minimum_score:
        blockers.append("score below required threshold")
    if (run.failed_cases or 0) > policy.maximum_failed_cases:
        blockers.append("too many failed cases")
    if (run.critical_failures or 0) > policy.critical_failures_allowed:
        blockers.append("critical failures exceeded policy")
    if blockers:
        return readiness_item(
            "EVALUATION_REQUIRED",
            "Required evaluation completed",
            "BLOCKED",
            "Evaluation cannot approve publishing: " + ", ".join(blockers) + ".",
            "evaluations",
            metadata,
        )

    if run.completed_at and run.completed_at < datetime.utcnow() - timedelta(hours=policy.maximum_evaluation_age_hours):
        return readiness_item(
            "EVALUATION_REQUIRED",
            "Required evaluation completed",
            "WARNING",
            "Evaluation passed, but the run is older than the configured freshness window.",
            "evaluations",
            metadata,
        )

    return readiness_item(
        "EVALUATION_REQUIRED",
        "Required evaluation completed",
        "PASSED",
        "Required evaluation passed for this exact version.",
        "evaluations",
        metadata,
    )


RECENT_SMOKE_WINDOW = timedelta(hours=24)


def readiness_item(code: str, label: str, status: str, message: str, action: str | None = None, metadata: dict | None = None) -> dict:
    return {
        "code": code,
        "label": label,
        "status": status,
        "message": message,
        "related_action": action,
        "metadata": metadata or {},
    }


def version_flow(db: Session, version_id: int) -> Flow | None:
    return db.query(Flow).filter(Flow.version_id == version_id).first()


def version_nodes(db: Session, version_id: int) -> list[FlowNode]:
    flow = version_flow(db, version_id)
    if not flow:
        return []
    return db.query(FlowNode).filter(FlowNode.flow_id == flow.id).all()


def node_requires_knowledge(node: FlowNode) -> bool:
    config = node.config or {}
    if node.type == "knowledge_search":
        return bool(config.get("retrieval_only") or config.get("use_knowledge_base", True))
    if node.type == "rag_answer":
        return bool(config.get("use_knowledge_base", True))
    return False


def version_requires_knowledge(nodes: list[FlowNode]) -> bool:
    return any(node_requires_knowledge(node) for node in nodes)


def knowledge_status(db: Session, version_id: int) -> dict:
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.version_id == version_id).first()
    if not kb:
        return {"documents": 0, "chunks": 0, "ready_chunks": 0, "pending_chunks": 0, "failed_chunks": 0, "failed_documents": 0}

    documents = db.query(Document).filter(Document.knowledge_base_id == kb.id).all()
    document_ids = [document.id for document in documents]
    if not document_ids:
        return {"documents": 0, "chunks": 0, "ready_chunks": 0, "pending_chunks": 0, "failed_chunks": 0, "failed_documents": 0}

    rows = db.query(Chunk.embedding_status, func.count(Chunk.id)).filter(
        Chunk.document_id.in_(document_ids)
    ).group_by(Chunk.embedding_status).all()
    counts = {status or "pending": count for status, count in rows}
    chunks = sum(counts.values())
    return {
        "documents": len(documents),
        "chunks": chunks,
        "ready_chunks": counts.get("ready", 0),
        "pending_chunks": counts.get("pending", 0) + counts.get("processing", 0),
        "failed_chunks": counts.get("failed", 0),
        "failed_documents": sum(1 for document in documents if document.status == "failed"),
    }


def latest_smoke(db: Session, version_id: int) -> VersionSmokeTest | None:
    return db.query(VersionSmokeTest).filter(
        VersionSmokeTest.version_id == version_id
    ).order_by(VersionSmokeTest.created_at.desc(), VersionSmokeTest.id.desc()).first()


def readiness_report(db: Session, version: VersionChatbot, chatbot: Chatbot) -> dict:
    nodes = version_nodes(db, version.id)
    config = db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()
    validation = validate_flow_version(db, version.id)
    requires_knowledge = version_requires_knowledge(nodes)
    knowledge = knowledge_status(db, version.id)
    smoke = latest_smoke(db, version.id)
    channels = db.query(ChatbotChannel).filter(ChatbotChannel.chatbot_id == chatbot.id).all()

    checks: list[dict] = []
    checks.append(readiness_item(
        "DRAFT_VERSION_EXISTS",
        "Draft version exists",
        "PASSED" if version.status == "draft" else "WARNING",
        "Selected version is a draft." if version.status == "draft" else "Selected version is not a draft; publishing will replace the active version.",
        "versions",
        {"version_status": version.status},
    ))
    checks.append(readiness_item(
        "INSTRUCTIONS_CONFIGURED",
        "Instructions configured",
        "PASSED" if config and (config.system_prompt or "").strip() else "BLOCKED",
        "System instructions are configured." if config and (config.system_prompt or "").strip() else "Add system instructions before publishing.",
        "instructions",
    ))
    checks.append(readiness_item(
        "FLOW_VALID",
        "Flow validates",
        "PASSED" if validation.get("valid") else "BLOCKED",
        "Flow validation passed." if validation.get("valid") else "Fix flow validation errors before publishing.",
        "flow",
        {"errors": validation.get("validation_errors") or validation.get("errors") or []},
    ))
    checks.append(readiness_item(
        "BLOCK_CONFIGURATION_COMPLETE",
        "Required block configuration complete",
        "PASSED" if validation.get("valid") else "BLOCKED",
        "Required block configuration is complete." if validation.get("valid") else "One or more blocks need configuration.",
        "flow",
    ))

    if requires_knowledge:
        if knowledge["failed_documents"] or knowledge["failed_chunks"]:
            status = "BLOCKED"
            message = "Knowledge ingestion has failed items that need reprocessing."
            category = RuntimeFailureCategory.INGESTION_NOT_READY
        elif knowledge["pending_chunks"]:
            status = "BLOCKED"
            message = "Knowledge ingestion is still pending."
            category = RuntimeFailureCategory.INGESTION_NOT_READY
        elif knowledge["ready_chunks"] > 0:
            status = "PASSED"
            message = "Required knowledge is indexed."
            category = None
        else:
            status = "BLOCKED"
            message = "This flow requires knowledge, but no indexed chunks are ready."
            category = RuntimeFailureCategory.INGESTION_NOT_READY
        checks.append(readiness_item(
            "KNOWLEDGE_INDEXED",
            "Knowledge indexed",
            status,
            message,
            "knowledge",
            {**knowledge, "failure_category": category.value if category else None},
        ))
    else:
        checks.append(readiness_item(
            "KNOWLEDGE_INDEXED",
            "Knowledge indexed",
            "PASSED",
            "Knowledge is not required for this assistant mode.",
            "knowledge",
            knowledge,
        ))

    if requires_knowledge:
        checks.append(readiness_item(
            "RETRIEVAL_CONFIGURATION_VALID",
            "Retrieval configuration valid",
            "PASSED",
            "Retrieval settings are within supported ranges.",
            "rag-settings",
        ))

    active_channels = [channel for channel in channels if channel.status in {"configured", "active", "verified", "ready"}]
    if chatbot.public_api_enabled or active_channels:
        checks.append(readiness_item(
            "PUBLIC_CHANNEL_VALID",
            "Public channel configuration valid",
            "PASSED" if chatbot.public_api_key else "BLOCKED",
            "Public API key is available." if chatbot.public_api_key else "Generate a public API key before publishing public channels.",
            "deployment",
            {"enabled_channels": [channel.channel_type for channel in active_channels]},
        ))
    else:
        checks.append(readiness_item(
            "PUBLIC_CHANNEL_VALID",
            "Public channel configuration valid",
            "WARNING",
            "No active public channel is configured.",
            "deployment",
        ))

    if smoke and smoke.status == "passed":
        recent = smoke.created_at and smoke.created_at >= datetime.utcnow() - RECENT_SMOKE_WINDOW
        checks.append(readiness_item(
            "RUNTIME_SMOKE_TEST",
            "Runtime smoke test passes",
            "PASSED" if recent else "WARNING",
            "Recent smoke test passed." if recent else "Last smoke test passed, but it is older than 24 hours.",
            "smoke-test",
            {"smoke_test_id": smoke.id, "latency_ms": smoke.latency_ms, "tested_at": smoke.created_at.isoformat() if smoke.created_at else None},
        ))
    elif smoke:
        checks.append(readiness_item(
            "RUNTIME_SMOKE_TEST",
            "Runtime smoke test passes",
            "BLOCKED",
            smoke.message or "Last smoke test failed.",
            "smoke-test",
            {"smoke_test_id": smoke.id, "failure_category": smoke.failure_category, "latency_ms": smoke.latency_ms},
        ))
    else:
        checks.append(readiness_item(
            "RUNTIME_SMOKE_TEST",
            "Runtime smoke test passes",
            "WARNING",
            "Run a smoke test before publishing.",
            "smoke-test",
        ))

    evaluation_check = evaluation_readiness_check(db, version, chatbot)
    if evaluation_check:
        checks.append(evaluation_check)

    ai_or_rag_nodes = [node for node in nodes if node.type in {"rag_answer", "knowledge_search"}]
    if ai_or_rag_nodes and not any((node.config or {}).get("fallback") for node in ai_or_rag_nodes):
        checks.append(readiness_item(
            "FALLBACK_MESSAGE_CONFIGURED",
            "Fallback message configured",
            "WARNING",
            "No AI/RAG fallback message is configured.",
            "flow",
        ))

    summary = {
        "blocked": sum(1 for check in checks if check["status"] == "BLOCKED"),
        "warnings": sum(1 for check in checks if check["status"] == "WARNING"),
        "passed": sum(1 for check in checks if check["status"] == "PASSED"),
    }
    return {
        "version_id": version.id,
        "chatbot_id": chatbot.id,
        "requires_knowledge": requires_knowledge,
        "can_publish": summary["blocked"] == 0,
        "requires_confirmation": summary["warnings"] > 0,
        "summary": summary,
        "checks": checks,
    }


def run_version_smoke_test(db: Session, version: VersionChatbot, chatbot: Chatbot, user_id: int | None, test_message: str | None = None) -> dict:
    started_at = time.perf_counter()
    trace: dict = {"turns": []}
    config = db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()
    if not config:
        raise ValueError("Chatbot configuration is missing")

    state = {"__language": chatbot.language or "en", "__smoke_test": True}
    current_node_key = None
    message = (test_message or "Hello, this is a pre-publish smoke test.").strip()
    result = None

    def rag_answer(query: str, fallback_variables: dict | None = None, node_config: dict | None = None):
        return build_rag_response(
            db=db,
            version=version,
            config=config,
            message=query or message,
            variables=fallback_variables or state,
            history=[],
            mode_used="smoke_test_rag",
            node_config=node_config,
        )

    try:
        for turn in range(3):
            result = execute_flow(
                db=db,
                version_id=version.id,
                message=message if turn == 0 else "Can you answer this smoke-test question?",
                current_node_key=current_node_key,
                variables=state,
                rag_answer=rag_answer,
                allow_rag_fallback=False,
                trace=trace,
            )
            trace["turns"].append({
                "turn": turn + 1,
                "mode_used": result.get("mode_used"),
                "current_node_key": result.get("current_node_key"),
                "response_present": bool((result.get("response") or "").strip()),
                "runtime_error": result.get("runtime_error"),
                "retrieval_mode": result.get("retrieval_mode"),
            })
            if result.get("runtime_error"):
                raise RuntimeError(result["runtime_error"].get("message") or "Runtime error")
            state = result.get("variables") or state
            current_node_key = result.get("current_node_key")
            if result.get("mode_used") in {"flow_rag", "public_flow_rag", "smoke_test_rag", "fallback"}:
                break
            if not current_node_key:
                break

        if not result or not (result.get("response") or "").strip():
            category = RuntimeFailureCategory.NO_ANSWER
            status = "failed"
            message_out = "Smoke test completed without a usable assistant response."
        else:
            category = None
            status = "passed"
            message_out = "Smoke test passed."
    except Exception as exc:
        db.rollback()
        category = sanitized_category_from_error(exc)
        status = "failed"
        message_out = str(getattr(exc, "detail", None) or exc)[:500]

    latency_ms = max(0, round((time.perf_counter() - started_at) * 1000))
    record = VersionSmokeTest(
        version_id=version.id,
        chatbot_id=chatbot.id,
        tested_by=user_id,
        test_mode="auto",
        status=status,
        failure_category=category.value if category else None,
        latency_ms=latency_ms,
        trace=trace,
        message=message_out,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": record.id,
        "version_id": version.id,
        "chatbot_id": chatbot.id,
        "status": status,
        "failure_category": record.failure_category,
        "latency_ms": latency_ms,
        "message": message_out,
        "trace": trace,
        "created_at": record.created_at,
    }
