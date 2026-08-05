import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.project import Project
from models.user import User
from services.generated_flow import (
    SUPPORTED_FLOW_NODE_TYPES,
    ensure_generated_flow_is_valid,
    normalize_generated_flow,
    validate_generated_flow_candidate,
)


class FlowBlockCoverageTest(unittest.TestCase):
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
            name="Project",
            description="Block test project",
            user_id=self.manager.id,
            created_at=datetime.utcnow(),
        )
        self.db.add(self.project)
        self.db.commit()

        self.chatbot = Chatbot(
            name="Assistant",
            project_id=self.project.id,
            language="en",
            is_active=True,
        )
        self.db.add(self.chatbot)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def node(self, key, node_type, config=None, x=100, y=120):
        return {
            "key": key,
            "type": node_type,
            "label": key.replace("_", " ").title(),
            "config": config or {},
            "position_x": x,
            "position_y": y,
        }

    def transition(self, source, target, label=None, condition=None):
        return {
            "source_node_key": source,
            "target_node_key": target,
            "label": label,
            "condition": condition,
        }

    def assert_flow_valid(self, nodes, transitions, flow_name="Block coverage"):
        normalized_nodes, normalized_transitions = ensure_generated_flow_is_valid(
            self.db,
            self.chatbot.id,
            nodes,
            transitions,
            flow_name,
        )
        self.assertEqual(
            1,
            sum(1 for node in normalized_nodes if node.key == "start"),
            "Generated flows must use one canonical start node.",
        )
        node_keys = {node.key for node in normalized_nodes}
        for transition in normalized_transitions:
            self.assertIn(transition.source_node_key, node_keys)
            self.assertIn(transition.target_node_key, node_keys)
        return normalized_nodes, normalized_transitions

    def validation_codes(self, nodes, transitions):
        normalized_nodes, normalized_transitions = normalize_generated_flow(nodes, transitions)
        result = validate_generated_flow_candidate(
            self.db,
            self.chatbot.id,
            normalized_nodes,
            normalized_transitions,
            "Invalid block candidate",
        )
        return {item["code"] for item in result["validation_errors"]}, result

    def solo_flow_for(self, node_type):
        start = self.node("start", "message", {"text": "Start"}, 80, 120)
        block = self.node("block", node_type, self.valid_config_for(node_type), 340, 120)

        if node_type == "end":
            return [start, block], [self.transition("start", "block", "next")]

        if node_type == "handoff":
            return [start, block], [self.transition("start", "block", "next")]

        end = self.node("end", "end", {"message": "Done"}, 600, 120)
        transitions = [self.transition("start", "block", "next")]

        if node_type == "buttons":
            transitions.extend([
                self.transition("block", "end", "Yes"),
                self.transition("block", "end", "No"),
            ])
        elif node_type == "condition":
            transitions.extend([
                self.transition("block", "end", "true", "true"),
                self.transition("block", "end", "false", "false"),
            ])
        else:
            transitions.append(self.transition("block", "end", "next"))

        return [start, block, end], transitions

    def valid_config_for(self, node_type):
        configs = {
            "message": {"text": "Here is a helpful message."},
            "question": {"prompt": "What do you need?", "field": "request"},
            "buttons": {"text": "Choose a path.", "buttons": ["Yes", "No"], "field": "choice"},
            "end": {"message": "Thanks, the conversation is complete."},
            "rag_answer": {
                "prompt": "Answer from configured knowledge.",
                "fallback": "I could not find a confirmed answer.",
                "use_knowledge_base": True,
                "show_sources": True,
                "continue_rag": True,
            },
            "knowledge_search": {
                "query_field": "request",
                "result_field": "knowledge_results",
                "fallback": "No relevant source was found.",
                "top_k": 4,
            },
            "ai_router": {"routes": ["support", "sales"]},
            "ai_classifier": {"categories": ["billing", "technical"]},
            "collect_name": {"prompt": "What is your full name?", "field": "user_name"},
            "collect_email": {"prompt": "What email should we use?", "field": "user_email"},
            "collect_phone": {"prompt": "What phone number can we use?", "field": "user_phone"},
            "condition": {"field": "choice", "operator": "equals", "value": "Yes"},
            "confidence_check": {"field": "confidence", "threshold": 0.7},
            "lead_score": {"field": "lead_score", "rules": [{"field": "budget", "score": 10}]},
            "set_variable": {"field": "segment", "value": "qualified", "message": "Saved."},
            "meeting_scheduler": {"prompt": "What time works?", "field": "preferred_meeting_time"},
            "api_request": {
                "method": "POST",
                "url": "https://example.com/webhook",
                "timeout": 8,
                "response_field": "api_response",
                "success_message": "The request was sent.",
                "error_message": "The request could not be sent.",
            },
            "handoff": {
                "message": "A teammate will follow up.",
                "department": "Support",
                "email_field": "user_email",
            },
            "action": {"action_type": "set_variable", "field": "ticket_status", "value": "ready"},
        }
        return configs[node_type]

    def test_every_supported_block_type_can_be_used_as_a_valid_solo_block(self):
        self.assertIn("buttons", SUPPORTED_FLOW_NODE_TYPES)
        self.assertIn("condition", SUPPORTED_FLOW_NODE_TYPES)
        self.assertIn("api_request", SUPPORTED_FLOW_NODE_TYPES)
        self.assertIn("meeting_scheduler", SUPPORTED_FLOW_NODE_TYPES)

        for node_type in sorted(SUPPORTED_FLOW_NODE_TYPES):
            with self.subTest(node_type=node_type):
                nodes, transitions = self.solo_flow_for(node_type)
                normalized_nodes, _ = self.assert_flow_valid(
                    nodes,
                    transitions,
                    f"Solo {node_type}",
                )
                self.assertIn(node_type, {node.type for node in normalized_nodes})

    def test_buttons_condition_and_variable_flow_is_valid(self):
        nodes = [
            self.node("start", "message", {"text": "Welcome."}, 80, 120),
            self.node(
                "intent",
                "buttons",
                {"text": "What do you need?", "buttons": ["Support", "Docs"], "field": "intent"},
                320,
                120,
            ),
            self.node("mark_support", "set_variable", {"field": "route", "value": "support"}, 580, 40),
            self.node("mark_docs", "set_variable", {"field": "route", "value": "docs"}, 580, 200),
            self.node("route_check", "condition", {"field": "route", "operator": "equals", "value": "support"}, 840, 120),
            self.node("handoff", "handoff", {"department": "Support", "email_field": "user_email"}, 1100, 40),
            self.node("docs_message", "message", {"text": "I can point you to documentation."}, 1100, 200),
            self.node("end", "end", {"message": "Done."}, 1360, 120),
        ]
        transitions = [
            self.transition("start", "intent", "next"),
            self.transition("intent", "mark_support", "Support"),
            self.transition("intent", "mark_docs", "Docs"),
            self.transition("mark_support", "route_check", "next"),
            self.transition("mark_docs", "route_check", "next"),
            self.transition("route_check", "handoff", "true", "route == support"),
            self.transition("route_check", "docs_message", "false", "route != support"),
            self.transition("docs_message", "end", "next"),
        ]

        self.assert_flow_valid(nodes, transitions, "Buttons condition set-variable workflow")

    def test_capture_api_condition_handoff_flow_is_valid(self):
        nodes = [
            self.node("start", "message", {"text": "I will create a request."}, 80, 120),
            self.node("name", "collect_name", {"prompt": "Your name?", "field": "user_name"}, 320, 120),
            self.node("email", "collect_email", {"prompt": "Your email?", "field": "user_email"}, 560, 120),
            self.node(
                "api",
                "api_request",
                {
                    "method": "POST",
                    "url": "https://example.com/tickets",
                    "timeout": 10,
                    "response_field": "ticket_response",
                },
                800,
                120,
            ),
            self.node("created", "condition", {"field": "ticket_response.status", "operator": "equals", "value": "created"}, 1040, 120),
            self.node("success", "message", {"text": "Your ticket is ready."}, 1280, 40),
            self.node("handoff", "handoff", {"department": "Support", "email_field": "user_email"}, 1280, 200),
            self.node("end", "end", {"message": "Thanks."}, 1520, 120),
        ]
        transitions = [
            self.transition("start", "name", "next"),
            self.transition("name", "email", "next"),
            self.transition("email", "api", "next"),
            self.transition("api", "created", "next"),
            self.transition("created", "success", "true", "status created"),
            self.transition("created", "handoff", "false", "status failed"),
            self.transition("success", "end", "next"),
        ]

        self.assert_flow_valid(nodes, transitions, "Capture API condition handoff workflow")

    def test_meeting_and_lead_scoring_flow_is_valid(self):
        nodes = [
            self.node("start", "message", {"text": "Let us qualify your request."}, 80, 120),
            self.node("name", "collect_name", {"prompt": "Your name?", "field": "user_name"}, 320, 120),
            self.node("budget", "question", {"prompt": "What budget range?", "field": "budget"}, 560, 120),
            self.node("score", "lead_score", {"field": "lead_score", "rules": [{"field": "budget", "score": 10}]}, 800, 120),
            self.node("qualified", "condition", {"field": "lead_score", "operator": "greater_than", "value": "5"}, 1040, 120),
            self.node("meeting", "meeting_scheduler", {"prompt": "When should we meet?", "field": "meeting_time"}, 1280, 40),
            self.node("nurture", "message", {"text": "We will send resources first."}, 1280, 200),
            self.node("end", "end", {"message": "Thanks."}, 1520, 120),
        ]
        transitions = [
            self.transition("start", "name", "next"),
            self.transition("name", "budget", "next"),
            self.transition("budget", "score", "next"),
            self.transition("score", "qualified", "next"),
            self.transition("qualified", "meeting", "true", "score > 5"),
            self.transition("qualified", "nurture", "false", "score <= 5"),
            self.transition("meeting", "end", "next"),
            self.transition("nurture", "end", "next"),
        ]

        self.assert_flow_valid(nodes, transitions, "Meeting scheduler lead-score workflow")

    def test_ai_router_classifier_and_confidence_flow_is_valid(self):
        nodes = [
            self.node("start", "message", {"text": "I will route your question."}, 80, 120),
            self.node("ask", "question", {"prompt": "What do you need?", "field": "request"}, 320, 120),
            self.node("router", "ai_router", {"routes": ["technical", "billing", "general"]}, 560, 120),
            self.node("classifier", "ai_classifier", {"categories": ["urgent", "normal"]}, 800, 120),
            self.node("confidence", "confidence_check", {"field": "confidence", "threshold": 0.75}, 1040, 120),
            self.node("answer", "message", {"text": "I found the right path."}, 1280, 120),
            self.node("end", "end", {"message": "Done."}, 1520, 120),
        ]
        transitions = [
            self.transition("start", "ask", "next"),
            self.transition("ask", "router", "next"),
            self.transition("router", "classifier", "next"),
            self.transition("classifier", "confidence", "next"),
            self.transition("confidence", "answer", "next"),
            self.transition("answer", "end", "next"),
        ]

        self.assert_flow_valid(nodes, transitions, "AI router classifier confidence workflow")

    def test_invalid_solo_block_configs_report_specific_codes(self):
        cases = [
            (
                "buttons_empty",
                self.node("block", "buttons", {"buttons": []}),
                [self.transition("start", "block", "next")],
                {"BUTTONS_EMPTY"},
            ),
            (
                "buttons_missing_option_transition",
                self.node("block", "buttons", {"buttons": ["Yes", "No"], "field": "choice"}),
                [self.transition("start", "block", "next"), self.transition("block", "end", "Yes")],
                {"BUTTON_TRANSITION_MISSING"},
            ),
            (
                "condition_missing_false",
                self.node("block", "condition", {"field": "choice"}),
                [self.transition("start", "block", "next"), self.transition("block", "end", "true", "true")],
                {"CONDITION_FALSE_MISSING"},
            ),
            (
                "api_bad_config",
                self.node("block", "api_request", {"method": "PUT", "url": "not-a-url", "timeout": 0}),
                [self.transition("start", "block", "next"), self.transition("block", "end", "next")],
                {"API_METHOD_INVALID", "API_URL_INVALID", "API_TIMEOUT_INVALID"},
            ),
            (
                "meeting_missing_field",
                self.node("block", "meeting_scheduler", {"prompt": "When?"}),
                [self.transition("start", "block", "next"), self.transition("block", "end", "next")],
                {"MEETING_VARIABLE_MISSING"},
            ),
            (
                "handoff_missing_contact",
                self.node("block", "handoff", {}),
                [self.transition("start", "block", "next")],
                {"HANDOFF_CONTACT_MISSING"},
            ),
            (
                "router_missing_routes",
                self.node("block", "ai_router", {"routes": []}),
                [self.transition("start", "block", "next"), self.transition("block", "end", "next")],
                {"AI_ROUTER_ROUTES_MISSING"},
            ),
            (
                "classifier_missing_categories",
                self.node("block", "ai_classifier", {"categories": []}),
                [self.transition("start", "block", "next"), self.transition("block", "end", "next")],
                {"AI_CLASSIFIER_CATEGORIES_MISSING"},
            ),
            (
                "set_variable_missing_name_and_value",
                self.node("block", "set_variable", {}),
                [self.transition("start", "block", "next"), self.transition("block", "end", "next")],
                {"SET_VARIABLE_NAME_MISSING", "SET_VARIABLE_VALUE_MISSING"},
            ),
            (
                "collect_email_missing_variable",
                self.node("block", "collect_email", {"prompt": "Email?"}),
                [self.transition("start", "block", "next"), self.transition("block", "end", "next")],
                {"INPUT_VARIABLE_MISSING", "EMAIL_VARIABLE_MISSING"},
            ),
            (
                "rag_missing_fallback_and_continuation",
                self.node("block", "rag_answer", {}),
                [self.transition("start", "block", "next")],
                {"RAG_FALLBACK_MISSING", "RAG_CONTINUATION_MISSING"},
            ),
        ]

        for name, block, extra_transitions, expected_codes in cases:
            with self.subTest(name=name):
                nodes = [
                    self.node("start", "message", {"text": "Start"}),
                    block,
                    self.node("end", "end", {"message": "Done"}),
                ]
                codes, result = self.validation_codes(nodes, extra_transitions)
                self.assertFalse(result["valid"])
                self.assertTrue(
                    expected_codes.issubset(codes),
                    f"Expected {expected_codes}, got {codes}",
                )


if __name__ == "__main__":
    unittest.main()
