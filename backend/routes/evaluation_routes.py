from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.chatbot import Chatbot
from models.evaluation import EvaluationCase, EvaluationCaseResult, EvaluationDataset, EvaluationPolicy, EvaluationRun
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from services.audit import record_audit_log
from services.auth import require_roles
from services.evaluation_engine import (
    compare_runs,
    export_dataset_csv,
    export_dataset_json,
    parse_import_payload,
    run_dataset_evaluation,
    serialize_case,
    serialize_dataset,
    serialize_result,
    serialize_run,
)

router = APIRouter(prefix="/evaluations", tags=["Evaluations"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class DatasetPayload(BaseModel):
    name: str
    description: str | None = None


class CasePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    order_index: int | None = None
    input_message: str
    turns: list[dict[str, Any]] | None = None
    initial_variables: dict[str, Any] | None = None
    expected_response_mode: str | None = None
    expected_intent: str | None = None
    expected_keywords: list[str] | None = None
    forbidden_keywords: list[str] | None = None
    expected_source_document_ids: list[Any] | None = None
    expected_source_patterns: list[str] | None = None
    expected_flow_node_ids: list[str] | None = None
    forbidden_flow_node_ids: list[str] | None = None
    expected_final_node_id: str | None = None
    expected_variable_assertions: list[dict[str, Any]] | None = None
    maximum_latency_ms: int | None = None
    minimum_retrieval_score: float | None = None
    minimum_answer_score: float | None = None
    minimum_source_count: int | None = None
    expected_fallback: bool | None = None
    expected_handoff: bool | None = None
    expected_failure_category: str | None = None
    critical: bool = False
    enabled: bool = True
    tags: list[str] | None = None
    judge_config: dict[str, Any] | None = None


class CaseReorderPayload(BaseModel):
    case_ids: list[int]


class ImportPayload(BaseModel):
    format: str = "json"
    content: str


class RunPayload(BaseModel):
    dataset_id: int
    version_id: int
    deterministic_only: bool = True
    judge_enabled: bool = False
    trigger_type: str = "manual"


class PolicyPayload(BaseModel):
    required_before_publish: bool = False
    required_dataset_id: int | None = None
    minimum_score: float = 80
    maximum_failed_cases: int = 0
    critical_failures_allowed: int = 0
    block_on_regression: bool = False
    maximum_evaluation_age_hours: int = 72


def get_accessible_chatbot(db: Session, assistant_id: int, current_user: User) -> Chatbot:
    query = db.query(Chatbot).filter(Chatbot.id == assistant_id)
    if current_user.role == "manager":
        query = query.join(Project, Chatbot.project_id == Project.id).filter(Project.user_id == current_user.id)
    chatbot = query.first()
    if not chatbot:
        raise HTTPException(status_code=404, detail="Assistant not found")
    return chatbot


def get_accessible_dataset(db: Session, dataset_id: int, current_user: User) -> EvaluationDataset:
    dataset = db.query(EvaluationDataset).filter(EvaluationDataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Evaluation dataset not found")
    get_accessible_chatbot(db, dataset.assistant_id, current_user)
    return dataset


def get_accessible_run(db: Session, run_id: int, current_user: User) -> EvaluationRun:
    run = db.query(EvaluationRun).filter(EvaluationRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    get_accessible_chatbot(db, run.assistant_id, current_user)
    return run


def get_accessible_version(db: Session, version_id: int, current_user: User) -> VersionChatbot:
    version = db.query(VersionChatbot).filter(VersionChatbot.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    get_accessible_chatbot(db, version.chatbot_id, current_user)
    return version


def apply_case_payload(case: EvaluationCase, payload: CasePayload) -> None:
    for field, value in payload.model_dump().items():
        setattr(case, field, value)
    case.updated_at = datetime.utcnow()


@router.post("/assistants/{assistant_id}/datasets")
def create_dataset(
    assistant_id: int,
    payload: DatasetPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    chatbot = get_accessible_chatbot(db, assistant_id, current_user)
    dataset = EvaluationDataset(
        assistant_id=chatbot.id,
        name=payload.name.strip(),
        description=payload.description,
        created_by=current_user.id,
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    record_audit_log(db, actor=current_user, action="EVALUATION_DATASET_CREATED", resource_type="evaluation_dataset", resource_id=dataset.id, resource_name=dataset.name, metadata={"assistant_id": chatbot.id})
    return serialize_dataset(dataset)


@router.get("/assistants/{assistant_id}/datasets")
def list_datasets(
    assistant_id: int,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    chatbot = get_accessible_chatbot(db, assistant_id, current_user)
    query = db.query(EvaluationDataset).filter(EvaluationDataset.assistant_id == chatbot.id)
    if not include_archived:
        query = query.filter(EvaluationDataset.status != "archived")
    datasets = query.order_by(EvaluationDataset.updated_at.desc(), EvaluationDataset.id.desc()).all()
    return [serialize_dataset(dataset) for dataset in datasets]


@router.get("/datasets/{dataset_id}")
def read_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    dataset = get_accessible_dataset(db, dataset_id, current_user)
    return serialize_dataset(dataset, include_cases=True)


@router.put("/datasets/{dataset_id}")
def update_dataset(
    dataset_id: int,
    payload: DatasetPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    dataset = get_accessible_dataset(db, dataset_id, current_user)
    dataset.name = payload.name.strip()
    dataset.description = payload.description
    dataset.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(dataset)
    record_audit_log(db, actor=current_user, action="EVALUATION_DATASET_UPDATED", resource_type="evaluation_dataset", resource_id=dataset.id, resource_name=dataset.name)
    return serialize_dataset(dataset)


@router.post("/datasets/{dataset_id}/archive")
def archive_dataset(dataset_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    dataset = get_accessible_dataset(db, dataset_id, current_user)
    dataset.status = "archived"
    dataset.updated_at = datetime.utcnow()
    db.commit()
    record_audit_log(db, actor=current_user, action="EVALUATION_DATASET_ARCHIVED", resource_type="evaluation_dataset", resource_id=dataset.id, resource_name=dataset.name)
    return serialize_dataset(dataset)


@router.post("/datasets/{dataset_id}/restore")
def restore_dataset(dataset_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    dataset = get_accessible_dataset(db, dataset_id, current_user)
    dataset.status = "active"
    dataset.updated_at = datetime.utcnow()
    db.commit()
    record_audit_log(db, actor=current_user, action="EVALUATION_DATASET_RESTORED", resource_type="evaluation_dataset", resource_id=dataset.id, resource_name=dataset.name)
    return serialize_dataset(dataset)


@router.delete("/datasets/{dataset_id}")
def delete_dataset(dataset_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    dataset = get_accessible_dataset(db, dataset_id, current_user)
    run_count = db.query(EvaluationRun).filter(EvaluationRun.dataset_id == dataset.id).count()
    if run_count:
        raise HTTPException(status_code=400, detail="Dataset has historical runs. Archive it instead.")
    db.delete(dataset)
    db.commit()
    record_audit_log(db, actor=current_user, action="EVALUATION_DATASET_DELETED", resource_type="evaluation_dataset", resource_id=dataset_id)
    return {"deleted": True}


@router.post("/datasets/{dataset_id}/cases")
def create_case(dataset_id: int, payload: CasePayload, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    dataset = get_accessible_dataset(db, dataset_id, current_user)
    next_index = db.query(EvaluationCase).filter(EvaluationCase.dataset_id == dataset.id).count()
    case = EvaluationCase(dataset_id=dataset.id, order_index=payload.order_index if payload.order_index is not None else next_index)
    apply_case_payload(case, payload)
    db.add(case)
    db.commit()
    db.refresh(case)
    record_audit_log(db, actor=current_user, action="EVALUATION_CASE_CREATED", resource_type="evaluation_case", resource_id=case.id, resource_name=case.name, metadata={"dataset_id": dataset.id})
    return serialize_case(case)


@router.put("/cases/{case_id}")
def update_case(case_id: int, payload: CasePayload, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    case = db.query(EvaluationCase).filter(EvaluationCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Evaluation case not found")
    get_accessible_dataset(db, case.dataset_id, current_user)
    apply_case_payload(case, payload)
    db.commit()
    db.refresh(case)
    record_audit_log(db, actor=current_user, action="EVALUATION_CASE_UPDATED", resource_type="evaluation_case", resource_id=case.id, resource_name=case.name)
    return serialize_case(case)


@router.post("/cases/{case_id}/duplicate")
def duplicate_case(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    case = db.query(EvaluationCase).filter(EvaluationCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Evaluation case not found")
    get_accessible_dataset(db, case.dataset_id, current_user)
    clone = EvaluationCase(**{
        key: value
        for key, value in serialize_case(case).items()
        if key not in {"id", "created_at", "updated_at"}
    })
    clone.name = f"{case.name} copy"
    clone.order_index = (case.order_index or 0) + 1
    db.add(clone)
    db.commit()
    db.refresh(clone)
    record_audit_log(db, actor=current_user, action="EVALUATION_CASE_CREATED", resource_type="evaluation_case", resource_id=clone.id, resource_name=clone.name, metadata={"duplicated_from": case.id})
    return serialize_case(clone)


@router.post("/datasets/{dataset_id}/cases/reorder")
def reorder_cases(dataset_id: int, payload: CaseReorderPayload, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    dataset = get_accessible_dataset(db, dataset_id, current_user)
    cases = db.query(EvaluationCase).filter(EvaluationCase.dataset_id == dataset.id, EvaluationCase.id.in_(payload.case_ids)).all()
    if len(cases) != len(set(payload.case_ids)):
        raise HTTPException(status_code=400, detail="Reorder payload contains cases outside this dataset.")
    by_id = {case.id: case for case in cases}
    for index, case_id in enumerate(payload.case_ids):
        by_id[case_id].order_index = index
    db.commit()
    return [serialize_case(by_id[case_id]) for case_id in payload.case_ids]


@router.post("/cases/{case_id}/enabled")
def set_case_enabled(case_id: int, enabled: bool = Query(...), db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    case = db.query(EvaluationCase).filter(EvaluationCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Evaluation case not found")
    get_accessible_dataset(db, case.dataset_id, current_user)
    case.enabled = enabled
    case.updated_at = datetime.utcnow()
    db.commit()
    return serialize_case(case)


@router.delete("/cases/{case_id}")
def delete_case(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    case = db.query(EvaluationCase).filter(EvaluationCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Evaluation case not found")
    get_accessible_dataset(db, case.dataset_id, current_user)
    has_results = db.query(EvaluationCaseResult).filter(EvaluationCaseResult.case_id == case.id).count() > 0
    if has_results:
        case.enabled = False
        case.updated_at = datetime.utcnow()
        db.commit()
        return {"deleted": False, "disabled": True}
    db.delete(case)
    db.commit()
    record_audit_log(db, actor=current_user, action="EVALUATION_CASE_DELETED", resource_type="evaluation_case", resource_id=case_id)
    return {"deleted": True}


@router.post("/datasets/{dataset_id}/import")
def import_cases(dataset_id: int, payload: ImportPayload, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    dataset = get_accessible_dataset(db, dataset_id, current_user)
    format_name = payload.format.strip().lower()
    if format_name not in {"json", "csv"}:
        raise HTTPException(status_code=400, detail="Import format must be json or csv.")
    try:
        rows = parse_import_payload(payload.content, format_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"message": "Import validation failed.", "errors": [str(exc)]}) from exc
    errors = []
    for index, row in enumerate(rows, start=1):
        if not (row.get("name") or "").strip():
            errors.append({"row": index, "field": "name", "message": "Name is required."})
        if not (row.get("input_message") or "").strip():
            errors.append({"row": index, "field": "input_message", "message": "Input message is required."})
    if errors:
        raise HTTPException(status_code=400, detail={"message": "Import validation failed.", "errors": errors})
    start_index = db.query(EvaluationCase).filter(EvaluationCase.dataset_id == dataset.id).count()
    created = []
    for offset, row in enumerate(rows):
        case = EvaluationCase(
            dataset_id=dataset.id,
            name=row.get("name"),
            description=row.get("description"),
            order_index=row.get("order_index", start_index + offset),
            input_message=row.get("input_message"),
            turns=row.get("turns") or [],
            initial_variables=row.get("initial_variables") or {},
            expected_response_mode=row.get("expected_response_mode"),
            expected_intent=row.get("expected_intent"),
            expected_keywords=row.get("expected_keywords") or [],
            forbidden_keywords=row.get("forbidden_keywords") or [],
            expected_source_document_ids=row.get("expected_source_document_ids") or [],
            expected_source_patterns=row.get("expected_source_patterns") or [],
            expected_flow_node_ids=row.get("expected_flow_node_ids") or [],
            forbidden_flow_node_ids=row.get("forbidden_flow_node_ids") or [],
            expected_final_node_id=row.get("expected_final_node_id"),
            expected_variable_assertions=row.get("expected_variable_assertions") or [],
            maximum_latency_ms=row.get("maximum_latency_ms"),
            minimum_retrieval_score=row.get("minimum_retrieval_score"),
            minimum_source_count=row.get("minimum_source_count"),
            expected_fallback=row.get("expected_fallback"),
            expected_handoff=row.get("expected_handoff"),
            critical=bool(row.get("critical", False)),
            enabled=bool(row.get("enabled", True)),
            tags=row.get("tags") or [],
            judge_config=row.get("judge_config") or {},
        )
        db.add(case)
        created.append(case)
    db.commit()
    return {"created": len(created), "cases": [serialize_case(case) for case in created]}


@router.get("/datasets/{dataset_id}/export")
def export_dataset(dataset_id: int, format: str = "json", db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    dataset = get_accessible_dataset(db, dataset_id, current_user)
    cases = db.query(EvaluationCase).filter(EvaluationCase.dataset_id == dataset.id).order_by(EvaluationCase.order_index.asc()).all()
    if format == "csv":
        return PlainTextResponse(export_dataset_csv(cases), media_type="text/csv")
    return export_dataset_json(dataset, cases)


@router.post("/runs")
def run_evaluation(payload: RunPayload, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    dataset = get_accessible_dataset(db, payload.dataset_id, current_user)
    version = get_accessible_version(db, payload.version_id, current_user)
    chatbot = get_accessible_chatbot(db, dataset.assistant_id, current_user)
    run = run_dataset_evaluation(
        db=db,
        dataset=dataset,
        version=version,
        chatbot=chatbot,
        user_id=current_user.id,
        trigger_type=payload.trigger_type,
        evaluator_configuration={
            "deterministic_only": payload.deterministic_only,
            "judge_enabled": payload.judge_enabled,
        },
    )
    record_audit_log(db, actor=current_user, action="EVALUATION_RUN_COMPLETED", resource_type="evaluation_run", resource_id=run.id, resource_name=f"run-{run.id}", metadata={"status": run.status, "score": run.overall_score})
    return serialize_run(run)


@router.get("/assistants/{assistant_id}/runs")
def list_runs(assistant_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    chatbot = get_accessible_chatbot(db, assistant_id, current_user)
    runs = db.query(EvaluationRun).filter(EvaluationRun.assistant_id == chatbot.id).order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc()).limit(100).all()
    return [serialize_run(run) for run in runs]


@router.get("/runs/{run_id}")
def read_run(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    run = get_accessible_run(db, run_id, current_user)
    results = db.query(EvaluationCaseResult).filter(EvaluationCaseResult.run_id == run.id).order_by(EvaluationCaseResult.id.asc()).all()
    return {**serialize_run(run), "results": [serialize_result(result) for result in results]}


@router.get("/results/{result_id}")
def read_result(result_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    result = db.query(EvaluationCaseResult).filter(EvaluationCaseResult.id == result_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Evaluation result not found")
    get_accessible_run(db, result.run_id, current_user)
    return serialize_result(result)


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    run = get_accessible_run(db, run_id, current_user)
    if run.status not in {"queued", "running"}:
        return serialize_run(run)
    run.status = "cancelled"
    run.completed_at = datetime.utcnow()
    db.commit()
    record_audit_log(db, actor=current_user, action="EVALUATION_RUN_CANCELLED", resource_type="evaluation_run", resource_id=run.id)
    return serialize_run(run)


@router.get("/compare")
def compare_evaluation_runs(baseline_run_id: int, candidate_run_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    baseline = get_accessible_run(db, baseline_run_id, current_user)
    candidate = get_accessible_run(db, candidate_run_id, current_user)
    if baseline.status != "completed" or candidate.status != "completed":
        raise HTTPException(status_code=400, detail="Only completed runs can be compared.")
    return compare_runs(db, baseline, candidate)


@router.get("/assistants/{assistant_id}/policy")
def read_policy(assistant_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    chatbot = get_accessible_chatbot(db, assistant_id, current_user)
    policy = db.query(EvaluationPolicy).filter(EvaluationPolicy.assistant_id == chatbot.id).first()
    if not policy:
        return {
            "assistant_id": chatbot.id,
            "required_before_publish": False,
            "required_dataset_id": None,
            "minimum_score": 80,
            "maximum_failed_cases": 0,
            "critical_failures_allowed": 0,
            "block_on_regression": False,
            "maximum_evaluation_age_hours": 72,
        }
    return {
        "assistant_id": policy.assistant_id,
        "required_before_publish": policy.required_before_publish,
        "required_dataset_id": policy.required_dataset_id,
        "minimum_score": policy.minimum_score,
        "maximum_failed_cases": policy.maximum_failed_cases,
        "critical_failures_allowed": policy.critical_failures_allowed,
        "block_on_regression": policy.block_on_regression,
        "maximum_evaluation_age_hours": policy.maximum_evaluation_age_hours,
        "updated_by": policy.updated_by,
        "updated_at": policy.updated_at,
    }


@router.put("/assistants/{assistant_id}/policy")
def update_policy(assistant_id: int, payload: PolicyPayload, db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin", "manager"))):
    chatbot = get_accessible_chatbot(db, assistant_id, current_user)
    if payload.required_dataset_id:
        dataset = get_accessible_dataset(db, payload.required_dataset_id, current_user)
        if dataset.assistant_id != chatbot.id:
            raise HTTPException(status_code=400, detail="Required dataset must belong to this assistant.")
    policy = db.query(EvaluationPolicy).filter(EvaluationPolicy.assistant_id == chatbot.id).first()
    if not policy:
        policy = EvaluationPolicy(assistant_id=chatbot.id)
        db.add(policy)
    for field, value in payload.model_dump().items():
        setattr(policy, field, value)
    policy.updated_by = current_user.id
    policy.updated_at = datetime.utcnow()
    db.commit()
    record_audit_log(db, actor=current_user, action="EVALUATION_POLICY_CHANGED", resource_type="chatbot", resource_id=chatbot.id, resource_name=chatbot.name, metadata=payload.model_dump())
    return read_policy(assistant_id, db, current_user)
