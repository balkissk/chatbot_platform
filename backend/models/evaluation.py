from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from database.db import Base


class EvaluationDataset(Base):
    __tablename__ = "evaluation_datasets"

    id = Column(Integer, primary_key=True)
    assistant_id = Column(Integer, ForeignKey("chatbots.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, nullable=False, default="active", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cases = relationship("EvaluationCase", back_populates="dataset")


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    order_index = Column(Integer, nullable=False, default=0)
    input_message = Column(Text, nullable=False)
    turns = Column(JSON, default=list)
    initial_variables = Column(JSON, default=dict)
    expected_response_mode = Column(String, nullable=True)
    expected_intent = Column(String, nullable=True)
    expected_keywords = Column(JSON, default=list)
    forbidden_keywords = Column(JSON, default=list)
    expected_source_document_ids = Column(JSON, default=list)
    expected_source_patterns = Column(JSON, default=list)
    expected_flow_node_ids = Column(JSON, default=list)
    forbidden_flow_node_ids = Column(JSON, default=list)
    expected_final_node_id = Column(String, nullable=True)
    expected_variable_assertions = Column(JSON, default=list)
    maximum_latency_ms = Column(Integer, nullable=True)
    minimum_retrieval_score = Column(Float, nullable=True)
    minimum_answer_score = Column(Float, nullable=True)
    minimum_source_count = Column(Integer, nullable=True)
    expected_fallback = Column(Boolean, nullable=True)
    expected_handoff = Column(Boolean, nullable=True)
    expected_failure_category = Column(String, nullable=True)
    critical = Column(Boolean, nullable=False, default=False)
    enabled = Column(Boolean, nullable=False, default=True)
    tags = Column(JSON, default=list)
    judge_config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    dataset = relationship("EvaluationDataset", back_populates="cases")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id = Column(Integer, primary_key=True)
    assistant_id = Column(Integer, ForeignKey("chatbots.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id = Column(Integer, ForeignKey("evaluation_datasets.id", ondelete="SET NULL"), nullable=True, index=True)
    version_id = Column(Integer, ForeignKey("versions.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False, default="queued", index=True)
    triggered_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    trigger_type = Column(String, nullable=False, default="manual", index=True)
    total_cases = Column(Integer, default=0)
    passed_cases = Column(Integer, default=0)
    warning_cases = Column(Integer, default=0)
    failed_cases = Column(Integer, default=0)
    critical_failures = Column(Integer, default=0)
    overall_score = Column(Float, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    runtime_mode = Column(String, nullable=True)
    evaluator_configuration = Column(JSON, default=dict)
    dataset_snapshot = Column(JSON, default=dict)
    error_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    results = relationship("EvaluationCaseResult", back_populates="run")


class EvaluationCaseResult(Base):
    __tablename__ = "evaluation_case_results"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("evaluation_cases.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String, nullable=False, index=True)
    score = Column(Float, default=0)
    case_snapshot = Column(JSON, default=dict)
    actual_response = Column(Text, nullable=True)
    actual_response_mode = Column(String, nullable=True)
    actual_sources = Column(JSON, default=list)
    actual_visited_nodes = Column(JSON, default=list)
    actual_variables = Column(JSON, default=dict)
    latency_ms = Column(Integer, nullable=True)
    runtime_execution_id = Column(String, nullable=True, index=True)
    failure_category = Column(String, nullable=True, index=True)
    assertion_results = Column(JSON, default=list)
    judge_result = Column(JSON, nullable=True)
    error_message_sanitized = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    run = relationship("EvaluationRun", back_populates="results")


class EvaluationPolicy(Base):
    __tablename__ = "evaluation_policies"

    id = Column(Integer, primary_key=True)
    assistant_id = Column(Integer, ForeignKey("chatbots.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    required_before_publish = Column(Boolean, nullable=False, default=False)
    required_dataset_id = Column(Integer, ForeignKey("evaluation_datasets.id", ondelete="SET NULL"), nullable=True)
    minimum_score = Column(Float, nullable=False, default=80)
    maximum_failed_cases = Column(Integer, nullable=False, default=0)
    critical_failures_allowed = Column(Integer, nullable=False, default=0)
    block_on_regression = Column(Boolean, nullable=False, default=False)
    maximum_evaluation_age_hours = Column(Integer, nullable=False, default=72)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
