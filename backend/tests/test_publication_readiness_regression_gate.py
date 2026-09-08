import unittest
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.evaluation import EvaluationCase, EvaluationCaseResult, EvaluationDataset, EvaluationPolicy, EvaluationRun
from models.flow import Flow, FlowNode, FlowTransition
from models.llm_config import LLMConfig
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from models.version_smoke_test import VersionSmokeTest
from routes.version_routes import get_version_readiness, publish_version


class PublishRouteRegressionGateTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.manager = User(name="Manager", email="manager@example.com", password_hash="x", role="manager", status="active")
        self.db.add(self.manager)
        self.db.commit()

        self.project = Project(name="Project", description="", user_id=self.manager.id)
        self.db.add(self.project)
        self.db.commit()

        self.chatbot = Chatbot(
            name="Eval Bot",
            project_id=self.project.id,
            language="en",
            is_active=True,
            public_api_enabled=True,
            public_api_key="cp_test",
        )
        self.db.add(self.chatbot)
        self.db.commit()

        self.published_version = self._create_version(1, "published", published=True)
        self.candidate_version = self._create_version(2, "draft")
        self.chatbot.active_version_id = self.published_version.id
        self.db.commit()

        self._add_linear_flow(self.published_version.id)
        self._add_linear_flow(self.candidate_version.id)
        self._add_config(self.published_version.id)
        self._add_config(self.candidate_version.id)
        self._add_smoke(self.candidate_version.id)

        self.dataset = EvaluationDataset(assistant_id=self.chatbot.id, name="Release Suite", created_by=self.manager.id)
        self.db.add(self.dataset)
        self.db.commit()

        self.case = EvaluationCase(
            dataset_id=self.dataset.id,
            name="Return policy path",
            input_message="What is the return policy?",
            expected_keywords=["30 days"],
            expected_flow_node_ids=["start", "end"],
            critical=True,
            enabled=True,
        )
        self.db.add(self.case)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _create_version(self, version_number: int, status: str, published: bool = False) -> VersionChatbot:
        now = datetime.utcnow()
        version = VersionChatbot(
            chatbot_id=self.chatbot.id,
            version_number=version_number,
            status=status,
            created_at=now,
            published_at=now if published else None,
        )
        self.db.add(version)
        self.db.commit()
        return version

    def _add_linear_flow(self, version_id: int) -> None:
        flow = Flow(version_id=version_id, name=f"Flow {version_id}")
        self.db.add(flow)
        self.db.commit()
        self.db.add_all([
            FlowNode(flow_id=flow.id, node_key="start", type="message", label="Start", config={"text": "Returns are accepted within 30 days."}),
            FlowNode(flow_id=flow.id, node_key="end", type="end", label="End", config={"message": "Done"}),
            FlowTransition(flow_id=flow.id, source_node_key="start", target_node_key="end", label="next"),
        ])
        self.db.commit()

    def _add_config(self, version_id: int) -> None:
        self.db.add(LLMConfig(version_id=version_id, model="test", temperature=0.2, system_prompt="Test assistant"))
        self.db.commit()

    def _add_smoke(self, version_id: int, status: str = "passed") -> None:
        self.db.add(VersionSmokeTest(
            version_id=version_id,
            chatbot_id=self.chatbot.id,
            tested_by=self.manager.id,
            test_mode="auto",
            status=status,
            message="Smoke passed." if status == "passed" else "Smoke failed.",
            latency_ms=20,
        ))
        self.db.commit()

    def _set_policy(self, *, required_before_publish: bool, block_on_regression: bool) -> None:
        self.db.add(EvaluationPolicy(
            assistant_id=self.chatbot.id,
            required_before_publish=required_before_publish,
            required_dataset_id=self.dataset.id,
            minimum_score=80,
            maximum_failed_cases=0,
            critical_failures_allowed=0,
            block_on_regression=block_on_regression,
            maximum_evaluation_age_hours=72,
            updated_by=self.manager.id,
        ))
        self.db.commit()

    def _create_completed_run(
        self,
        version: VersionChatbot,
        *,
        overall_score: float,
        passed_cases: int,
        warning_cases: int,
        failed_cases: int,
        critical_failures: int,
        case_status: str,
        case_score: float,
    ) -> EvaluationRun:
        now = datetime.utcnow()
        run = EvaluationRun(
            assistant_id=self.chatbot.id,
            dataset_id=self.dataset.id,
            version_id=version.id,
            status="completed",
            triggered_by=self.manager.id,
            trigger_type="manual",
            total_cases=1,
            passed_cases=passed_cases,
            warning_cases=warning_cases,
            failed_cases=failed_cases,
            critical_failures=critical_failures,
            overall_score=overall_score,
            started_at=now,
            completed_at=now,
            duration_ms=50,
            runtime_mode="flow",
            dataset_snapshot={"name": self.dataset.name},
        )
        self.db.add(run)
        self.db.commit()

        self.db.add(EvaluationCaseResult(
            run_id=run.id,
            case_id=self.case.id,
            status=case_status,
            score=case_score,
            case_snapshot={"name": self.case.name},
            actual_response="Returns are accepted within 30 days.",
            actual_response_mode="flow",
            actual_sources=[],
            actual_visited_nodes=[{"node_key": "start"}, {"node_key": "end"}],
            actual_variables={},
            latency_ms=25,
            assertion_results=[],
        ))
        self.db.commit()
        return run

    def test_publish_route_blocks_regression_when_policy_enabled(self):
        self._set_policy(required_before_publish=True, block_on_regression=True)
        self._create_completed_run(
            self.published_version,
            overall_score=100,
            passed_cases=1,
            warning_cases=0,
            failed_cases=0,
            critical_failures=0,
            case_status="passed",
            case_score=100,
        )
        self._create_completed_run(
            self.candidate_version,
            overall_score=90,
            passed_cases=0,
            warning_cases=1,
            failed_cases=0,
            critical_failures=0,
            case_status="warning",
            case_score=90,
        )

        readiness = get_version_readiness(self.candidate_version.id, db=self.db, current_user=self.manager)
        evaluation_check = next(check for check in readiness["checks"] if check["code"] == "EVALUATION_REQUIRED")
        self.assertEqual(evaluation_check["status"], "BLOCKED")
        self.assertEqual(evaluation_check["metadata"]["comparison_regressions"], 1)

        with self.assertRaises(HTTPException) as raised:
            publish_version(self.candidate_version.id, confirm_warnings=True, db=self.db, current_user=self.manager)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail["readiness"]["summary"]["blocked"], 1)
        self.db.refresh(self.chatbot)
        self.db.refresh(self.published_version)
        self.db.refresh(self.candidate_version)
        self.assertEqual(self.chatbot.active_version_id, self.published_version.id)
        self.assertEqual(self.published_version.status, "published")
        self.assertEqual(self.candidate_version.status, "draft")

    def test_publish_route_allows_regression_when_gate_disabled(self):
        self._set_policy(required_before_publish=True, block_on_regression=False)
        self._create_completed_run(
            self.published_version,
            overall_score=100,
            passed_cases=1,
            warning_cases=0,
            failed_cases=0,
            critical_failures=0,
            case_status="passed",
            case_score=100,
        )
        self._create_completed_run(
            self.candidate_version,
            overall_score=90,
            passed_cases=0,
            warning_cases=1,
            failed_cases=0,
            critical_failures=0,
            case_status="warning",
            case_score=90,
        )

        response = publish_version(self.candidate_version.id, db=self.db, current_user=self.manager)

        self.assertEqual(response["version"]["status"], "published")
        self.db.refresh(self.chatbot)
        self.db.refresh(self.published_version)
        self.db.refresh(self.candidate_version)
        self.assertEqual(self.chatbot.active_version_id, self.candidate_version.id)
        self.assertEqual(self.published_version.status, "archived")
        self.assertEqual(self.candidate_version.status, "published")

    def test_first_publication_is_not_blocked_without_baseline(self):
        self.chatbot.active_version_id = None
        self.published_version.status = "archived"
        self.db.commit()

        self._set_policy(required_before_publish=True, block_on_regression=True)
        self._create_completed_run(
            self.candidate_version,
            overall_score=90,
            passed_cases=0,
            warning_cases=1,
            failed_cases=0,
            critical_failures=0,
            case_status="warning",
            case_score=90,
        )

        readiness = get_version_readiness(self.candidate_version.id, db=self.db, current_user=self.manager)
        evaluation_check = next(check for check in readiness["checks"] if check["code"] == "EVALUATION_REQUIRED")
        self.assertEqual(evaluation_check["status"], "PASSED")

        response = publish_version(self.candidate_version.id, db=self.db, current_user=self.manager)

        self.assertEqual(response["version"]["status"], "published")
        self.db.refresh(self.chatbot)
        self.db.refresh(self.candidate_version)
        self.assertEqual(self.chatbot.active_version_id, self.candidate_version.id)
        self.assertEqual(self.candidate_version.status, "published")

    def test_warning_only_publish_requires_confirmation_and_then_succeeds(self):
        warning_candidate = self._create_version(3, "draft")
        self._add_linear_flow(warning_candidate.id)
        self._add_config(warning_candidate.id)
        self.chatbot.public_api_enabled = False
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            publish_version(warning_candidate.id, db=self.db, current_user=self.manager)

        self.assertEqual(raised.exception.status_code, 409)
        readiness = raised.exception.detail["readiness"]
        self.assertEqual(readiness["summary"]["blocked"], 0)
        self.assertGreaterEqual(readiness["summary"]["warnings"], 1)

        response = publish_version(warning_candidate.id, confirm_warnings=True, db=self.db, current_user=self.manager)

        self.assertEqual(response["version"]["status"], "published")
        self.db.refresh(self.chatbot)
        self.db.refresh(warning_candidate)
        self.assertEqual(self.chatbot.active_version_id, warning_candidate.id)
        self.assertEqual(warning_candidate.status, "published")


if __name__ == "__main__":
    unittest.main()
