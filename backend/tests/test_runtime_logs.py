import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.flow import Flow, FlowNode
from models.llm_config import LLMConfig
from models.project import Project
from models.runtime_log import RuntimeLog
from models.user import User
from models.version import VersionChatbot
from routes.admin_analytics_routes import analytics_runtime_logs, dashboard_usage, system_health
from services.unified_runtime import run_chatbot_message, sanitize_error_message


class RuntimeLogTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()
        self.now = datetime.now(UTC).replace(tzinfo=None)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create_runtime_chatbot(self, node_type: str = "message"):
        owner = User(name="Manager", email="manager@example.com", password_hash="x", role="manager", status="active")
        self.db.add(owner)
        self.db.commit()
        project = Project(name="Project", description="", user_id=owner.id)
        self.db.add(project)
        self.db.commit()
        chatbot = Chatbot(name="Bot", project_id=project.id, language="en", is_active=True)
        self.db.add(chatbot)
        self.db.commit()
        version = VersionChatbot(chatbot_id=chatbot.id, version_number=1, status="published", published_at=self.now)
        self.db.add(version)
        self.db.commit()
        chatbot.active_version_id = version.id
        self.db.add(LLMConfig(version_id=version.id, model="test-model", temperature=0.1))
        flow = Flow(version_id=version.id, name="Flow")
        self.db.add(flow)
        self.db.commit()
        self.db.add(FlowNode(
            flow_id=flow.id,
            node_key="start",
            type=node_type,
            label="Start",
            config={"text": "Hello from flow"},
        ))
        self.db.commit()
        return owner, project, chatbot, version

    def test_successful_runtime_execution_creates_success_log(self):
        _, _, chatbot, version = self.create_runtime_chatbot()
        result = run_chatbot_message(self.db, chatbot.id, "api", None, "hi")

        log = self.db.query(RuntimeLog).one()
        self.assertEqual(log.status, "success")
        self.assertEqual(log.chatbot_id, chatbot.id)
        self.assertEqual(log.version_id, version.id)
        self.assertEqual(log.conversation_id, result["session_id"])
        self.assertEqual(log.channel, "api")
        self.assertFalse(log.rag_used)
        self.assertIsInstance(log.response_time_ms, int)

    def test_failed_runtime_execution_creates_failed_log(self):
        chatbot = Chatbot(name="Broken", project_id=None, language="en", is_active=True)
        self.db.add(chatbot)
        self.db.commit()

        with self.assertRaises(HTTPException):
            run_chatbot_message(self.db, chatbot.id, "web", None, "hi")

        log = self.db.query(RuntimeLog).one()
        self.assertEqual(log.status, "failed")
        self.assertEqual(log.chatbot_id, chatbot.id)
        self.assertEqual(log.channel, "web")
        self.assertEqual(log.error_type, "PublishedVersionNotFound")
        self.assertIsNotNone(log.response_time_ms)

    def test_runtime_log_sets_rag_used_from_actual_rag_path(self):
        _, _, chatbot, _ = self.create_runtime_chatbot(node_type="rag_answer")
        rag_response = {
            "response": "Answer",
            "messages": [{"text": "Answer", "options": []}],
            "mode_used": "test",
            "retrieval_mode": "keyword",
            "model_used": "test-model",
            "version_used": 1,
            "current_node_key": None,
            "variables": {},
            "options": [],
            "sources": [{"title": "Doc"}],
        }

        with patch("services.unified_runtime.build_rag_response", return_value=rag_response):
            run_chatbot_message(self.db, chatbot.id, "widget", "visitor-1", "question")

        log = self.db.query(RuntimeLog).one()
        self.assertEqual(log.channel, "widget")
        self.assertTrue(log.rag_used)

    def test_sensitive_error_message_is_sanitized(self):
        exc = RuntimeError("api_key=secret-token postgresql://user:pass@host/db Bearer abc.def")
        message = sanitize_error_message(exc)
        self.assertNotIn("secret-token", message)
        self.assertNotIn("user:pass", message)
        self.assertNotIn("abc.def", message)

    def test_runtime_time_series_fills_missing_dates(self):
        _, project, chatbot, version = self.create_runtime_chatbot()
        self.db.add(RuntimeLog(
            chatbot_id=chatbot.id,
            version_id=version.id,
            project_id=project.id,
            channel="api",
            status="success",
            rag_used=False,
            response_time_ms=42,
            created_at=self.now - timedelta(days=2),
        ))
        self.db.commit()

        usage = dashboard_usage(self.db, 3)
        self.assertEqual(len(usage["runtime_requests"]), 3)
        self.assertEqual(sum(usage["runtime_requests"]), 1)

    def test_runtime_logs_endpoint_filters_and_paginates(self):
        owner, project, chatbot, version = self.create_runtime_chatbot()
        self.db.add_all([
            RuntimeLog(chatbot_id=chatbot.id, version_id=version.id, project_id=project.id, channel="api", status="success", rag_used=True, created_at=self.now),
            RuntimeLog(chatbot_id=chatbot.id, version_id=version.id, project_id=project.id, channel="web", status="failed", rag_used=False, created_at=self.now),
        ])
        self.db.commit()

        payload = analytics_runtime_logs(
            limit=1,
            offset=0,
            date_from=None,
            date_to=None,
            chatbot_id=chatbot.id,
            project_id=project.id,
            owner_id=owner.id,
            channel="api",
            status="success",
            rag_used=True,
            db=self.db,
            current_user=User(role="admin"),
        )
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["chatbot_name"], "Bot")
        self.assertEqual(payload["items"][0]["project_name"], "Project")
        self.assertEqual(payload["items"][0]["owner_name"], "Manager")
        self.assertEqual(payload["items"][0]["version_label"], "v1")

    def test_system_health_not_monitored_without_logs_and_uses_recent_logs(self):
        health = system_health(self.db)
        self.assertEqual(health["services"]["runtime"]["status"], "not_monitored")

        _, _, chatbot, version = self.create_runtime_chatbot()
        self.db.add(RuntimeLog(
            chatbot_id=chatbot.id,
            version_id=version.id,
            channel="api",
            status="success",
            rag_used=False,
            response_time_ms=35,
            created_at=self.now,
        ))
        self.db.commit()
        health = system_health(self.db)
        self.assertEqual(health["services"]["runtime"]["status"], "healthy")
        self.assertEqual(health["services"]["runtime"]["success_rate_last_24h"], 100.0)


if __name__ == "__main__":
    unittest.main()
