import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.flow import Flow, FlowNode, FlowTransition
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from services.flow_runtime import execute_flow


class FlowRuntimeBlocksTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.manager = User(
            name="Manager",
            email="manager@example.com",
            password_hash="x",
            role="manager",
            status="active",
        )
        self.db.add(self.manager)
        self.db.commit()

        self.project = Project(
            name="Runtime Project",
            description="Runtime test project",
            user_id=self.manager.id,
            created_at=datetime.utcnow(),
        )
        self.db.add(self.project)
        self.db.commit()

        self.chatbot = Chatbot(
            name="Runtime Assistant",
            project_id=self.project.id,
            language="en",
            is_active=True,
        )
        self.db.add(self.chatbot)
        self.db.commit()

        self.version = VersionChatbot(chatbot_id=self.chatbot.id, version_number=1, status="draft")
        self.db.add(self.version)
        self.db.commit()
        self.chatbot.active_version_id = self.version.id
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create_flow(self, nodes, transitions):
        flow = Flow(version_id=self.version.id, name="Runtime Flow")
        self.db.add(flow)
        self.db.flush()

        for index, node in enumerate(nodes):
            self.db.add(FlowNode(
                flow_id=flow.id,
                node_key=node["key"],
                type=node["type"],
                label=node.get("label") or node["key"].replace("_", " ").title(),
                config=node.get("config") or {},
                position_x=node.get("position_x", 80 + index * 240),
                position_y=node.get("position_y", 120),
            ))

        for transition in transitions:
            self.db.add(FlowTransition(
                flow_id=flow.id,
                source_node_key=transition["source"],
                target_node_key=transition["target"],
                label=transition.get("label"),
                condition=transition.get("condition"),
            ))

        self.db.commit()
        return flow

    def node(self, key, node_type, config=None, label=None):
        return {"key": key, "type": node_type, "config": config or {}, "label": label}

    def edge(self, source, target, label=None, condition=None):
        return {"source": source, "target": target, "label": label, "condition": condition}

    def test_buttons_condition_set_variable_routes_user_to_expected_branch(self):
        self.create_flow(
            [
                self.node("start", "message", {"text": "Welcome to support."}),
                self.node("intent", "buttons", {"text": "Choose a path.", "buttons": ["Support", "Docs"], "field": "intent"}),
                self.node("set_support", "set_variable", {"field": "route", "value": "support"}),
                self.node("set_docs", "set_variable", {"field": "route", "value": "docs"}),
                self.node("route_check", "condition", {"field": "route", "operator": "equals", "value": "support"}),
                self.node("handoff", "handoff", {"message": "Support will follow up.", "department": "Support", "email_field": "user_email"}),
                self.node("docs", "message", {"text": "Here is the documentation path."}),
                self.node("end", "end", {"message": "Conversation closed."}),
            ],
            [
                self.edge("start", "intent", "next"),
                self.edge("intent", "set_support", "Support"),
                self.edge("intent", "set_docs", "Docs"),
                self.edge("set_support", "route_check", "next"),
                self.edge("set_docs", "route_check", "next"),
                self.edge("route_check", "handoff", "true", "route == support"),
                self.edge("route_check", "docs", "false", "route != support"),
                self.edge("docs", "end", "next"),
            ],
        )

        initial = execute_flow(self.db, self.version.id, "", "start", {})
        self.assertEqual(initial["current_node_key"], "intent")
        self.assertEqual(initial["options"], ["Support", "Docs"])

        docs_result = execute_flow(self.db, self.version.id, "Docs", "intent", initial["variables"])
        self.assertEqual(docs_result["response"], "Here is the documentation path.")
        self.assertEqual(docs_result["current_node_key"], "end")
        self.assertEqual(docs_result["variables"]["intent"], "Docs")
        self.assertEqual(docs_result["variables"]["route"], "docs")

        closed = execute_flow(self.db, self.version.id, "", "end", docs_result["variables"])
        self.assertEqual(closed["mode_used"], "end")
        self.assertTrue(closed["variables"]["__ended"])

    def test_buttons_condition_can_route_to_handoff(self):
        self.create_flow(
            [
                self.node("start", "message", {"text": "Welcome to support."}),
                self.node("intent", "buttons", {"text": "Choose a path.", "buttons": ["Support", "Docs"], "field": "intent"}),
                self.node("set_support", "set_variable", {"field": "route", "value": "support"}),
                self.node("route_check", "condition", {"field": "route", "operator": "equals", "value": "support"}),
                self.node("handoff", "handoff", {"message": "Support will follow up.", "department": "Support", "email_field": "user_email"}),
                self.node("end", "end", {"message": "Conversation closed."}),
            ],
            [
                self.edge("start", "intent", "next"),
                self.edge("intent", "set_support", "Support"),
                self.edge("intent", "end", "Docs"),
                self.edge("set_support", "route_check", "next"),
                self.edge("route_check", "handoff", "true", "route == support"),
                self.edge("route_check", "end", "false", "route != support"),
            ],
        )

        initial = execute_flow(self.db, self.version.id, "", "start", {})
        result = execute_flow(self.db, self.version.id, "Support", "intent", initial["variables"])

        self.assertEqual(result["mode_used"], "handoff")
        self.assertEqual(result["response"], "Support will follow up.")
        self.assertTrue(result["variables"]["__handoff_requested"])
        self.assertEqual(result["variables"]["__handoff_department"], "Support")

    def test_collect_email_rejects_invalid_input_then_accepts_valid_input(self):
        self.create_flow(
            [
                self.node("start", "message", {"text": "I need your email."}),
                self.node("email", "collect_email", {"prompt": "What is your email?", "field": "user_email"}),
                self.node("end", "end", {"message": "Email saved."}),
            ],
            [
                self.edge("start", "email", "next"),
                self.edge("email", "end", "next"),
            ],
        )

        initial = execute_flow(self.db, self.version.id, "", "start", {})
        self.assertEqual(initial["current_node_key"], "email")

        invalid = execute_flow(self.db, self.version.id, "not-an-email", "email", initial["variables"])
        self.assertEqual(invalid["current_node_key"], "email")
        self.assertIn("valid email", invalid["response"])
        self.assertNotIn("user_email", invalid["variables"])

        valid = execute_flow(self.db, self.version.id, "user@example.com", "email", invalid["variables"])
        self.assertEqual(valid["mode_used"], "end")
        self.assertEqual(valid["variables"]["user_email"], "user@example.com")
        self.assertTrue(valid["variables"]["__ended"])

    def test_api_request_block_uses_mocked_http_and_stores_response_payload(self):
        self.create_flow(
            [
                self.node("start", "message", {"text": "Creating ticket."}),
                self.node(
                    "api",
                    "api_request",
                    {
                        "method": "POST",
                        "url": "https://example.com/tickets",
                        "headers": {"X-User": "{{ user_email }}"},
                        "body": {"email": "{{ user_email }}", "issue": "{{ issue }}"},
                        "response_field": "ticket_response",
                        "success_message": "Ticket request sent.",
                    },
                ),
                self.node("end", "end", {"message": "Ticket flow complete."}),
            ],
            [
                self.edge("start", "api", "next"),
                self.edge("api", "end", "next"),
            ],
        )
        response = Mock()
        response.ok = True
        response.status_code = 201
        response.json.return_value = {"ticket_id": "T-100", "status": "created"}

        with patch("services.flow_runtime.requests.request", return_value=response) as request:
            result = execute_flow(
                self.db,
                self.version.id,
                "",
                "api",
                {"user_email": "user@example.com", "issue": "Cannot login"},
            )

        request.assert_called_once()
        _, kwargs = request.call_args
        self.assertEqual(kwargs["headers"], {"X-User": "user@example.com"})
        self.assertEqual(kwargs["json"], {"email": "user@example.com", "issue": "Cannot login"})
        self.assertEqual(result["mode_used"], "end")
        self.assertEqual(result["variables"]["ticket_response"]["ticket_id"], "T-100")
        self.assertEqual(result["messages"][0]["text"], "Ticket request sent.")

    def test_meeting_scheduler_stores_user_selected_time(self):
        self.create_flow(
            [
                self.node("start", "message", {"text": "Let us schedule a meeting."}),
                self.node("meeting", "meeting_scheduler", {"prompt": "What time works?", "field": "meeting_time"}),
            ],
            [self.edge("start", "meeting", "next")],
        )

        initial = execute_flow(self.db, self.version.id, "", "start", {})
        self.assertEqual(initial["current_node_key"], "meeting")

        result = execute_flow(self.db, self.version.id, "Tuesday 10:00", "meeting", initial["variables"])
        self.assertEqual(result["current_node_key"], "meeting")
        self.assertEqual(result["variables"]["meeting_time"], "Tuesday 10:00")

    def test_meeting_scheduler_prompts_then_continues_when_connected(self):
        self.create_flow(
            [
                self.node("start", "message", {"text": "Let us schedule a meeting."}),
                self.node(
                    "meeting",
                    "meeting_scheduler",
                    {
                        "prompt": "What time works?",
                        "field": "meeting_time",
                        "success_message": "Meeting saved.",
                    },
                ),
                self.node("end", "end", {"message": "Meeting flow complete."}),
            ],
            [
                self.edge("start", "meeting", "next"),
                self.edge("meeting", "end", "next"),
            ],
        )

        initial = execute_flow(self.db, self.version.id, "", "start", {})
        self.assertEqual(initial["response"], "Let us schedule a meeting.")
        self.assertEqual(initial["current_node_key"], "meeting")

        prompt = execute_flow(self.db, self.version.id, "", "meeting", initial["variables"])
        self.assertEqual(prompt["response"], "What time works?")
        self.assertEqual(prompt["current_node_key"], "meeting")

        result = execute_flow(self.db, self.version.id, "Tuesday 10:00", "meeting", prompt["variables"])
        self.assertEqual(result["mode_used"], "end")
        self.assertEqual(result["response"], "Meeting flow complete.")
        self.assertEqual(result["variables"]["meeting_time"], "Tuesday 10:00")

    def test_ai_router_classifier_confidence_and_lead_score_run_without_azure_openai(self):
        self.create_flow(
            [
                self.node("start", "message", {"text": "Tell me what you need."}),
                self.node("ask", "question", {"prompt": "What do you need?", "field": "request"}),
                self.node("router", "ai_router", {"routes": ["sales", "support"], "output_variable": "route"}),
                self.node("classifier", "ai_classifier", {"categories": ["urgent", "normal"], "output_variable": "priority"}),
                self.node("score", "lead_score", {"score_variable": "lead_score", "default_score": 80}),
                self.node("end", "end", {"message": "Routing complete."}),
            ],
            [
                self.edge("start", "ask", "next"),
                self.edge("ask", "router", "next"),
                self.edge("router", "classifier", "next"),
                self.edge("classifier", "score", "next"),
                self.edge("score", "end", "next"),
            ],
        )

        initial = execute_flow(self.db, self.version.id, "", "start", {})
        result = execute_flow(self.db, self.version.id, "I need urgent sales help", "ask", initial["variables"])

        self.assertEqual(result["mode_used"], "end")
        self.assertEqual(result["variables"]["request"], "I need urgent sales help")
        self.assertEqual(result["variables"]["route"], "I need urgent sales help")
        self.assertEqual(result["variables"]["priority"], "I need urgent sales help")
        self.assertEqual(result["variables"]["lead_score"], 80)

    def test_rag_answer_block_can_use_injected_callback_without_azure_openai(self):
        self.create_flow(
            [
                self.node("start", "message", {"text": "Ask a knowledge question."}),
                self.node("question", "question", {"prompt": "What do you want to know?", "field": "question"}),
                self.node("answer", "rag_answer", {"fallback": "No source found.", "show_sources": True}),
                self.node("end", "end", {"message": "Done."}),
            ],
            [
                self.edge("start", "question", "next"),
                self.edge("question", "answer", "next"),
                self.edge("answer", "end", "next"),
            ],
        )

        def fake_rag_answer(query, variables, config):
            return {
                "response": f"Mocked answer for: {query}",
                "messages": [{"text": f"Mocked answer for: {query}", "options": []}],
                "mode_used": "rag_mock",
                "current_node_key": None,
                "variables": variables,
                "sources": [{"document": "test.md", "chunk": 1}],
            }

        initial = execute_flow(self.db, self.version.id, "", "start", {})
        result = execute_flow(
            self.db,
            self.version.id,
            "How does billing work?",
            "question",
            initial["variables"],
            rag_answer=fake_rag_answer,
        )

        self.assertEqual(result["mode_used"], "rag_mock")
        self.assertEqual(result["response"], "Mocked answer for: How does billing work?")
        self.assertEqual(result["current_node_key"], "end")
        self.assertEqual(result["variables"]["question"], "How does billing work?")
        self.assertEqual(result["sources"][0]["document"], "test.md")


if __name__ == "__main__":
    unittest.main()
