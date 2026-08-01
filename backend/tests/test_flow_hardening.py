import unittest
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.flow import Flow, FlowNode, FlowTransition
from models.flow_schema import FlowNodeCreate, FlowTransitionCreate
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from routes.flow_routes import create_node, create_transition
from services.flow_limits import MAX_FLOW_NODES, MAX_FLOW_TRANSITIONS, MAX_RUNTIME_STEPS
from services.flow_runtime import execute_flow
from services.flow_validation import validate_flow_version


class FlowHardeningTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.manager = User(name="Manager", email="manager@example.com", password_hash="x", role="manager", status="active")
        self.db.add(self.manager)
        self.db.commit()
        self.project = Project(name="Project", description="Test", user_id=self.manager.id, created_at=datetime.utcnow())
        self.db.add(self.project)
        self.db.commit()
        self.chatbot = Chatbot(name="Bot", project_id=self.project.id, language="en", is_active=True)
        self.db.add(self.chatbot)
        self.db.commit()
        self.version = VersionChatbot(chatbot_id=self.chatbot.id, version_number=1, status="draft")
        self.db.add(self.version)
        self.db.commit()
        self.flow = Flow(version_id=self.version.id, name="Flow")
        self.db.add(self.flow)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _node(self, key, node_type="message", config=None, x=100, y=100):
        node = FlowNode(
            flow_id=self.flow.id,
            node_key=key,
            type=node_type,
            label=key.title(),
            config=config or {},
            position_x=x,
            position_y=y,
        )
        self.db.add(node)
        self.db.commit()
        return node

    def _transition(self, source, target, label=None, condition=None):
        transition = FlowTransition(
            flow_id=self.flow.id,
            source_node_key=source,
            target_node_key=target,
            label=label,
            condition=condition,
        )
        self.db.add(transition)
        self.db.commit()
        return transition

    def _codes(self):
        result = validate_flow_version(self.db, self.version.id)
        return {item["code"] for item in result["validation_errors"]}, result

    def test_node_and_transition_limits_are_rejected_at_mutation_time(self):
        for index in range(MAX_FLOW_NODES):
            self._node(f"n{index}", "end")

        with self.assertRaises(HTTPException) as node_error:
            create_node(
                self.flow.id,
                FlowNodeCreate(type="message", label="Overflow", config={}, position_x=100, position_y=100),
                db=self.db,
                current_user=self.manager,
            )
        self.assertEqual(node_error.exception.status_code, 400)

        self.db.query(FlowNode).delete()
        self.db.commit()
        self._node("start")
        self._node("end", "end")
        for index in range(MAX_FLOW_TRANSITIONS):
            self._transition("start", "end", label=f"path-{index}")

        with self.assertRaises(HTTPException) as transition_error:
            create_transition(
                self.flow.id,
                FlowTransitionCreate(source_node_key="start", target_node_key="end", label="overflow", condition=None),
                db=self.db,
                current_user=self.manager,
            )
        self.assertEqual(transition_error.exception.status_code, 400)

    def test_duplicate_transitions_are_rejected_and_reported(self):
        self._node("start")
        self._node("end", "end")
        self._transition("start", "end", label="yes")

        with self.assertRaises(HTTPException) as duplicate_error:
            create_transition(
                self.flow.id,
                FlowTransitionCreate(source_node_key="start", target_node_key="end", label="yes", condition=None),
                db=self.db,
                current_user=self.manager,
            )
        self.assertEqual(duplicate_error.exception.status_code, 400)

        self._transition("start", "end", label="yes")
        codes, result = self._codes()
        self.assertIn("DUPLICATE_TRANSITION", codes)
        duplicate = next(item for item in result["validation_errors"] if item["code"] == "DUPLICATE_TRANSITION")
        self.assertEqual(duplicate["severity"], "error")
        self.assertIsNotNone(duplicate["transition_id"])

    def test_runtime_loop_protection_returns_structured_error(self):
        self._node("start", "set_variable", {"field": "a", "value": "1"})
        self._node("loop", "set_variable", {"field": "b", "value": "2"})
        self._transition("start", "loop")
        self._transition("loop", "start")

        result = execute_flow(self.db, self.version.id, "", "start", {})
        self.assertEqual(result["mode_used"], "flow_error")
        self.assertEqual(result["runtime_error"]["code"], "MAX_RUNTIME_STEPS_EXCEEDED")
        self.assertEqual(result["runtime_error"]["severity"], "error")
        self.assertLessEqual(MAX_RUNTIME_STEPS, 100)

    def test_cycle_validation_rejects_machine_only_cycles_and_allows_question_loops(self):
        self._node("start", "message", {"text": "Hi"})
        self._node("a", "set_variable", {"field": "a", "value": "1"})
        self._node("b", "set_variable", {"field": "b", "value": "2"})
        self._transition("start", "a")
        self._transition("a", "b")
        self._transition("b", "a")

        codes, _ = self._codes()
        self.assertIn("SILENT_MACHINE_CYCLE", codes)

        self.db.query(FlowTransition).delete()
        self.db.query(FlowNode).delete()
        self.db.commit()
        self._node("start", "message", {"text": "Hi"})
        self._node("question", "question", {"prompt": "Ask", "field": "answer"})
        self._transition("start", "question")
        self._transition("question", "question")

        codes, _ = self._codes()
        self.assertNotIn("SILENT_MACHINE_CYCLE", codes)

    def test_block_configuration_validation_and_structured_errors(self):
        self._node("start", "message", {"text": "Hi"})
        self._node("buttons", "buttons", {"buttons": []})
        self._node("condition", "condition", {"field": "x"})
        self._node("rag", "rag_answer", {})
        self._node("api", "api_request", {"method": "PUT", "url": "not-a-url", "timeout": 0})
        self._node("handoff", "handoff", {})
        self._node("router", "ai_router", {"routes": []})
        self._node("classifier", "ai_classifier", {"categories": []})
        self._node("setvar", "set_variable", {})
        self._node("badpos", "end", {}, x=999999, y=100)

        self._transition("start", "buttons")
        self._transition("buttons", "condition", label="next")
        self._transition("condition", "rag", label="true")
        self._transition("rag", "api")
        self._transition("api", "handoff")
        self._transition("handoff", "router")
        self._transition("router", "classifier")
        self._transition("classifier", "setvar")
        self._transition("setvar", "badpos")

        codes, result = self._codes()
        self.assertTrue({
            "BUTTONS_EMPTY",
            "CONDITION_FALSE_MISSING",
            "RAG_FALLBACK_MISSING",
            "API_METHOD_INVALID",
            "API_URL_INVALID",
            "API_TIMEOUT_INVALID",
            "HANDOFF_CONTACT_MISSING",
            "AI_ROUTER_ROUTES_MISSING",
            "AI_CLASSIFIER_CATEGORIES_MISSING",
            "SET_VARIABLE_NAME_MISSING",
            "SET_VARIABLE_VALUE_MISSING",
            "INVALID_CANVAS_POSITION",
        }.issubset(codes))

        for item in result["validation_errors"]:
            self.assertEqual(set(item.keys()), {
                "code",
                "severity",
                "node_id",
                "transition_id",
                "message",
                "suggested_fix",
            })
        self.assertIsInstance(result["errors"][0], str)


if __name__ == "__main__":
    unittest.main()
