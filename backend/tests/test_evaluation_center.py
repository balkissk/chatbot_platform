import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.evaluation import EvaluationCase, EvaluationDataset, EvaluationPolicy
from models.flow import Flow, FlowNode, FlowTransition
from models.llm_config import LLMConfig
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from services.evaluation_engine import compare_runs, evaluate_assertions, run_dataset_evaluation
from services.publication_readiness import readiness_report


class EvaluationCenterTest(unittest.TestCase):
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
        self.chatbot = Chatbot(name="Eval Bot", project_id=self.project.id, language="en", is_active=True)
        self.db.add(self.chatbot)
        self.db.commit()
        self.version = VersionChatbot(chatbot_id=self.chatbot.id, version_number=1, status="draft", created_at=datetime.utcnow())
        self.db.add(self.version)
        self.db.commit()
        self.db.add(LLMConfig(version_id=self.version.id, model="test", temperature=0.2, system_prompt="Test assistant"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create_message_flow(self, text: str):
        flow = Flow(version_id=self.version.id, name="Eval Flow")
        self.db.add(flow)
        self.db.commit()
        self.db.add(FlowNode(flow_id=flow.id, node_key="start", type="message", label="Start", config={"text": text}))
        self.db.commit()

    def create_dataset_with_case(self, expected_keywords=None, critical=True):
        dataset = EvaluationDataset(assistant_id=self.chatbot.id, name="Release Suite", created_by=self.manager.id)
        self.db.add(dataset)
        self.db.commit()
        case = EvaluationCase(
            dataset_id=dataset.id,
            name="Return window",
            input_message="What is the return window?",
            expected_keywords=expected_keywords or ["30 days"],
            expected_flow_node_ids=["start"],
            critical=critical,
            enabled=True,
        )
        self.db.add(case)
        self.db.commit()
        return dataset, case

    def test_deterministic_assertions_score_required_and_forbidden_keywords(self):
        case = EvaluationCase(
            name="Keyword check",
            input_message="x",
            expected_keywords=["30 days"],
            forbidden_keywords=["guaranteed refund"],
            maximum_latency_ms=100,
            critical=True,
        )
        status, score, assertions = evaluate_assertions(
            case,
            {"response": "Returns are accepted within 30 days.", "variables": {}, "sources": [], "mode_used": "flow"},
            latency_ms=25,
            trace={"visited_nodes": []},
        )

        self.assertEqual(status, "passed")
        self.assertGreaterEqual(score, 80)
        self.assertIn("REQUIRED_KEYWORDS", [item["code"] for item in assertions])
        self.assertIn("FORBIDDEN_KEYWORDS", [item["code"] for item in assertions])

    def test_run_dataset_uses_runtime_and_persists_snapshot(self):
        self.create_message_flow("Returns are accepted within 30 days.")
        dataset, case = self.create_dataset_with_case()

        run = run_dataset_evaluation(self.db, dataset, self.version, self.chatbot, self.manager.id)

        self.assertEqual(run.status, "completed")
        self.assertEqual(run.passed_cases, 1)
        self.assertEqual(run.critical_failures, 0)
        result = run.results[0]
        self.assertEqual(result.case_snapshot["name"], case.name)
        self.assertEqual(result.actual_visited_nodes[0]["node_key"], "start")

        case.name = "Edited after run"
        self.db.commit()
        self.assertEqual(result.case_snapshot["name"], "Return window")

    def test_comparison_detects_regression(self):
        self.create_message_flow("Returns are accepted within 30 days.")
        dataset, case = self.create_dataset_with_case()
        baseline = run_dataset_evaluation(self.db, dataset, self.version, self.chatbot, self.manager.id)

        case.expected_keywords = ["60 days"]
        self.db.commit()
        candidate = run_dataset_evaluation(self.db, dataset, self.version, self.chatbot, self.manager.id)

        comparison = compare_runs(self.db, baseline, candidate)

        self.assertEqual(comparison["regressions"], 1)
        self.assertEqual(comparison["cases"][0]["state"], "regressed")

    def test_required_evaluation_policy_blocks_and_allows_publish_readiness(self):
        self.create_message_flow("Returns are accepted within 30 days.")
        dataset, _ = self.create_dataset_with_case()
        self.db.add(EvaluationPolicy(
            assistant_id=self.chatbot.id,
            required_before_publish=True,
            required_dataset_id=dataset.id,
            minimum_score=80,
            maximum_failed_cases=0,
            critical_failures_allowed=0,
        ))
        self.db.commit()

        missing = readiness_report(self.db, self.version, self.chatbot)
        evaluation_check = next(check for check in missing["checks"] if check["code"] == "EVALUATION_REQUIRED")
        self.assertEqual(evaluation_check["status"], "BLOCKED")

        run_dataset_evaluation(self.db, dataset, self.version, self.chatbot, self.manager.id)
        ready = readiness_report(self.db, self.version, self.chatbot)
        evaluation_check = next(check for check in ready["checks"] if check["code"] == "EVALUATION_REQUIRED")
        self.assertEqual(evaluation_check["status"], "PASSED")

    def test_multi_turn_flow_case_preserves_runtime_state(self):
        flow = Flow(version_id=self.version.id, name="Support Flow")
        self.db.add(flow)
        self.db.commit()
        self.db.add_all([
            FlowNode(flow_id=flow.id, node_key="start", type="message", label="Start", config={"text": "Choose a path."}),
            FlowNode(flow_id=flow.id, node_key="choice", type="buttons", label="Choice", config={"text": "Choose.", "buttons": ["Support"], "field": "path"}),
            FlowNode(flow_id=flow.id, node_key="name", type="collect_name", label="Name", config={"prompt": "Name?", "field": "customer_name"}),
            FlowNode(flow_id=flow.id, node_key="email", type="collect_email", label="Email", config={"prompt": "Email?", "field": "customer_email"}),
            FlowNode(flow_id=flow.id, node_key="phone", type="collect_phone", label="Phone", config={"prompt": "Phone?", "field": "customer_phone"}),
            FlowNode(flow_id=flow.id, node_key="end", type="end", label="End", config={"message": "Saved."}),
            FlowTransition(flow_id=flow.id, source_node_key="start", target_node_key="choice", label="next"),
            FlowTransition(flow_id=flow.id, source_node_key="choice", target_node_key="name", label="Support"),
            FlowTransition(flow_id=flow.id, source_node_key="name", target_node_key="email", label="next"),
            FlowTransition(flow_id=flow.id, source_node_key="email", target_node_key="phone", label="next"),
            FlowTransition(flow_id=flow.id, source_node_key="phone", target_node_key="end", label="next"),
        ])
        self.db.commit()
        dataset = EvaluationDataset(assistant_id=self.chatbot.id, name="Flow Suite", created_by=self.manager.id)
        self.db.add(dataset)
        self.db.commit()
        case = EvaluationCase(
            dataset_id=dataset.id,
            name="Support path",
            input_message="Support",
            turns=[
                {"message": ""},
                {"message": "Support"},
                {"message": "Alex"},
                {"message": "alex@example.com"},
                {"message": "+21612345678"},
            ],
            expected_flow_node_ids=["start", "choice", "name", "email", "phone", "end"],
            expected_final_node_id="end",
            expected_variable_assertions=[
                {"field": "customer_name", "operator": "equals", "value": "Alex"},
                {"field": "customer_email", "operator": "equals", "value": "alex@example.com"},
                {"field": "customer_phone", "operator": "equals", "value": "+21612345678"},
            ],
            critical=True,
            enabled=True,
        )
        self.db.add(case)
        self.db.commit()

        run = run_dataset_evaluation(self.db, dataset, self.version, self.chatbot, self.manager.id)

        self.assertEqual(run.status, "completed")
        self.assertEqual(run.passed_cases, 1)
        result = run.results[0]
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.case_snapshot["turns"][1]["message"], "Support")
        self.assertEqual(result.actual_variables["customer_email"], "alex@example.com")


if __name__ == "__main__":
    unittest.main()
