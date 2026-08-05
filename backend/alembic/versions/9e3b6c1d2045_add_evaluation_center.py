"""add evaluation center

Revision ID: 9e3b6c1d2045
Revises: 8d1e5f7a9034
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "9e3b6c1d2045"
down_revision: Union[str, None] = "8d1e5f7a9034"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "evaluation_datasets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assistant_id", sa.Integer(), sa.ForeignKey("chatbots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_evaluation_datasets_assistant_id", "evaluation_datasets", ["assistant_id"])
    op.create_index("ix_evaluation_datasets_status", "evaluation_datasets", ["status"])
    op.create_index("ix_evaluation_datasets_created_by", "evaluation_datasets", ["created_by"])
    op.create_index("ix_evaluation_datasets_created_at", "evaluation_datasets", ["created_at"])

    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_message", sa.Text(), nullable=False),
        sa.Column("initial_variables", sa.JSON(), nullable=True),
        sa.Column("expected_response_mode", sa.String(), nullable=True),
        sa.Column("expected_intent", sa.String(), nullable=True),
        sa.Column("expected_keywords", sa.JSON(), nullable=True),
        sa.Column("forbidden_keywords", sa.JSON(), nullable=True),
        sa.Column("expected_source_document_ids", sa.JSON(), nullable=True),
        sa.Column("expected_source_patterns", sa.JSON(), nullable=True),
        sa.Column("expected_flow_node_ids", sa.JSON(), nullable=True),
        sa.Column("forbidden_flow_node_ids", sa.JSON(), nullable=True),
        sa.Column("expected_final_node_id", sa.String(), nullable=True),
        sa.Column("expected_variable_assertions", sa.JSON(), nullable=True),
        sa.Column("maximum_latency_ms", sa.Integer(), nullable=True),
        sa.Column("minimum_retrieval_score", sa.Float(), nullable=True),
        sa.Column("minimum_answer_score", sa.Float(), nullable=True),
        sa.Column("minimum_source_count", sa.Integer(), nullable=True),
        sa.Column("expected_fallback", sa.Boolean(), nullable=True),
        sa.Column("expected_handoff", sa.Boolean(), nullable=True),
        sa.Column("expected_failure_category", sa.String(), nullable=True),
        sa.Column("critical", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("judge_config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_evaluation_cases_dataset_id", "evaluation_cases", ["dataset_id"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assistant_id", sa.Integer(), sa.ForeignKey("chatbots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("evaluation_datasets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("triggered_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("trigger_type", sa.String(), nullable=False, server_default="manual"),
        sa.Column("total_cases", sa.Integer(), nullable=True),
        sa.Column("passed_cases", sa.Integer(), nullable=True),
        sa.Column("warning_cases", sa.Integer(), nullable=True),
        sa.Column("failed_cases", sa.Integer(), nullable=True),
        sa.Column("critical_failures", sa.Integer(), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("runtime_mode", sa.String(), nullable=True),
        sa.Column("evaluator_configuration", sa.JSON(), nullable=True),
        sa.Column("dataset_snapshot", sa.JSON(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_evaluation_runs_assistant_id", "evaluation_runs", ["assistant_id"])
    op.create_index("ix_evaluation_runs_dataset_id", "evaluation_runs", ["dataset_id"])
    op.create_index("ix_evaluation_runs_version_id", "evaluation_runs", ["version_id"])
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"])
    op.create_index("ix_evaluation_runs_triggered_by", "evaluation_runs", ["triggered_by"])
    op.create_index("ix_evaluation_runs_trigger_type", "evaluation_runs", ["trigger_type"])
    op.create_index("ix_evaluation_runs_created_at", "evaluation_runs", ["created_at"])

    op.create_table(
        "evaluation_case_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("evaluation_cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("case_snapshot", sa.JSON(), nullable=True),
        sa.Column("actual_response", sa.Text(), nullable=True),
        sa.Column("actual_response_mode", sa.String(), nullable=True),
        sa.Column("actual_sources", sa.JSON(), nullable=True),
        sa.Column("actual_visited_nodes", sa.JSON(), nullable=True),
        sa.Column("actual_variables", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("runtime_execution_id", sa.String(), nullable=True),
        sa.Column("failure_category", sa.String(), nullable=True),
        sa.Column("assertion_results", sa.JSON(), nullable=True),
        sa.Column("judge_result", sa.JSON(), nullable=True),
        sa.Column("error_message_sanitized", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_evaluation_case_results_run_id", "evaluation_case_results", ["run_id"])
    op.create_index("ix_evaluation_case_results_case_id", "evaluation_case_results", ["case_id"])
    op.create_index("ix_evaluation_case_results_status", "evaluation_case_results", ["status"])
    op.create_index("ix_evaluation_case_results_runtime_execution_id", "evaluation_case_results", ["runtime_execution_id"])
    op.create_index("ix_evaluation_case_results_failure_category", "evaluation_case_results", ["failure_category"])
    op.create_index("ix_evaluation_case_results_created_at", "evaluation_case_results", ["created_at"])

    op.create_table(
        "evaluation_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assistant_id", sa.Integer(), sa.ForeignKey("chatbots.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("required_before_publish", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("required_dataset_id", sa.Integer(), sa.ForeignKey("evaluation_datasets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("minimum_score", sa.Float(), nullable=False, server_default="80"),
        sa.Column("maximum_failed_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("critical_failures_allowed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("block_on_regression", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("maximum_evaluation_age_hours", sa.Integer(), nullable=False, server_default="72"),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_evaluation_policies_assistant_id", "evaluation_policies", ["assistant_id"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_policies_assistant_id", table_name="evaluation_policies")
    op.drop_table("evaluation_policies")
    op.drop_index("ix_evaluation_case_results_created_at", table_name="evaluation_case_results")
    op.drop_index("ix_evaluation_case_results_failure_category", table_name="evaluation_case_results")
    op.drop_index("ix_evaluation_case_results_runtime_execution_id", table_name="evaluation_case_results")
    op.drop_index("ix_evaluation_case_results_status", table_name="evaluation_case_results")
    op.drop_index("ix_evaluation_case_results_case_id", table_name="evaluation_case_results")
    op.drop_index("ix_evaluation_case_results_run_id", table_name="evaluation_case_results")
    op.drop_table("evaluation_case_results")
    op.drop_index("ix_evaluation_runs_created_at", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_trigger_type", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_triggered_by", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_status", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_version_id", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_dataset_id", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_assistant_id", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index("ix_evaluation_cases_dataset_id", table_name="evaluation_cases")
    op.drop_table("evaluation_cases")
    op.drop_index("ix_evaluation_datasets_created_at", table_name="evaluation_datasets")
    op.drop_index("ix_evaluation_datasets_created_by", table_name="evaluation_datasets")
    op.drop_index("ix_evaluation_datasets_status", table_name="evaluation_datasets")
    op.drop_index("ix_evaluation_datasets_assistant_id", table_name="evaluation_datasets")
    op.drop_table("evaluation_datasets")
