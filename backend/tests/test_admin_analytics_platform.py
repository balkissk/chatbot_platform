import unittest
from datetime import datetime, timedelta

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from main import app
from models.chatbot import Chatbot
from models.conversation import ConversationSession
from models.project import Project
from models.runtime_log import RuntimeLog
from models.user import User
from models.version import VersionChatbot
from routes.admin_analytics_routes import analytics_platform, platform_analytics_payload
from services.auth import require_roles


class AdminPlatformAnalyticsTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()
        self.now = datetime.utcnow()

        self.admin = User(name="Admin", email="admin@example.com", password_hash="x", role="admin", status="active")
        self.manager = User(name="Manager", email="manager@example.com", password_hash="x", role="manager", status="active")
        self.db.add_all([self.admin, self.manager])
        self.db.commit()

        self.project = Project(name="Support", description="", user_id=self.manager.id)
        self.db.add(self.project)
        self.db.commit()

        self.support_bot = Chatbot(name="Support Bot", project_id=self.project.id, is_active=True)
        self.training_bot = Chatbot(name="Training Bot", project_id=self.project.id, is_active=True)
        self.disabled_bot = Chatbot(name="Disabled Bot", project_id=self.project.id, is_active=False)
        self.db.add_all([self.support_bot, self.training_bot, self.disabled_bot])
        self.db.commit()

        self.support_version = VersionChatbot(chatbot_id=self.support_bot.id, version_number=1, status="published")
        self.training_version = VersionChatbot(chatbot_id=self.training_bot.id, version_number=1, status="draft")
        self.db.add_all([self.support_version, self.training_version])
        self.db.commit()
        self.support_bot.active_version_id = self.support_version.id

        self.add_session(self.support_bot.id, self.support_version.id, 1, "web")
        self.add_session(self.support_bot.id, self.support_version.id, 2, "widget")
        self.add_session(self.support_bot.id, self.support_version.id, 3, "api")
        self.add_session(self.training_bot.id, self.training_version.id, 3, "web")
        self.add_session(self.training_bot.id, self.training_version.id, 4, "whatsapp")
        self.add_session(self.support_bot.id, self.support_version.id, 40, "web")

        self.add_runtime(self.support_bot.id, self.support_version.id, 1, "web", "success", 100)
        self.add_runtime(self.support_bot.id, self.support_version.id, 2, "widget", "success", 200)
        self.add_runtime(self.support_bot.id, self.support_version.id, 3, "api", "failed", 300)
        self.add_runtime(self.training_bot.id, self.training_version.id, 3, "messenger", "failed", 400)
        self.add_runtime(self.support_bot.id, self.support_version.id, 40, "web", "success", 500)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_session(self, chatbot_id: int, version_id: int, days_ago: int, channel: str):
        created_at = self.now - timedelta(days=days_ago)
        self.db.add(ConversationSession(
            chatbot_id=chatbot_id,
            version_id=version_id,
            variables={"__channel": channel},
            created_at=created_at,
            updated_at=created_at,
        ))

    def add_runtime(self, chatbot_id: int, version_id: int, days_ago: int, channel: str, status: str, response_time_ms: int):
        created_at = self.now - timedelta(days=days_ago)
        self.db.add(RuntimeLog(
            chatbot_id=chatbot_id,
            version_id=version_id,
            project_id=self.project.id,
            channel=channel,
            status=status,
            rag_used=False,
            response_time_ms=response_time_ms,
            created_at=created_at,
        ))

    def test_admin_can_access_analytics_payload(self):
        payload = analytics_platform(range="30d", db=self.db, current_user=self.admin)
        self.assertEqual(payload["period"], "30d")
        self.assertEqual(payload["kpis"]["total_conversations"], 5)

    def test_manager_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            require_roles("admin")(self.manager)
        self.assertEqual(raised.exception.status_code, 403)

    def test_unauthenticated_request_is_rejected(self):
        client = TestClient(app)
        response = client.get("/admin/analytics/platform?range=30d")
        self.assertIn(response.status_code, {401, 403})

    def test_supported_ranges_return_expected_label_counts(self):
        self.assertEqual(len(platform_analytics_payload(self.db, "7d")["conversations_over_time"]["labels"]), 7)
        self.assertEqual(len(platform_analytics_payload(self.db, "30d")["conversations_over_time"]["labels"]), 30)
        self.assertEqual(len(platform_analytics_payload(self.db, "90d")["conversations_over_time"]["labels"]), 90)

    def test_kpis_runtime_metrics_and_zero_division(self):
        payload = platform_analytics_payload(self.db, "30d")
        self.assertEqual(payload["kpis"]["total_conversations"], 5)
        self.assertEqual(payload["kpis"]["runtime_requests"], 4)
        self.assertEqual(payload["runtime_performance"]["successful_requests"], 2)
        self.assertEqual(payload["runtime_performance"]["failed_requests"], 2)
        self.assertEqual(payload["runtime_performance"]["success_rate"], 50.0)
        self.assertEqual(payload["runtime_performance"]["average_response_time_ms"], 250)

        self.db.query(RuntimeLog).delete()
        self.db.commit()
        empty = platform_analytics_payload(self.db, "7d")
        self.assertEqual(empty["kpis"]["runtime_requests"], 0)
        self.assertIsNone(empty["kpis"]["runtime_success_rate"])

    def test_conversation_and_runtime_time_series_group_by_day(self):
        payload = platform_analytics_payload(self.db, "7d")
        self.assertEqual(sum(payload["conversations_over_time"]["conversations"]), 5)
        self.assertEqual(sum(payload["runtime_requests_over_time"]["successful_requests"]), 2)
        self.assertEqual(sum(payload["runtime_requests_over_time"]["failed_requests"]), 2)
        self.assertEqual(sum(payload["runtime_requests_over_time"]["total_requests"]), 4)

    def test_legacy_channels_are_excluded_from_supported_usage(self):
        payload = platform_analytics_payload(self.db, "30d")
        channels = {item["channel"]: item for item in payload["channel_usage"]}
        self.assertEqual(set(channels.keys()), {"public_chat", "widget", "api"})
        self.assertEqual(channels["public_chat"]["conversations"], 2)
        self.assertEqual(channels["widget"]["conversations"], 1)
        self.assertEqual(channels["api"]["conversations"], 1)
        self.assertGreater(payload["legacy_channels_excluded"], 0)

    def test_top_chatbots_rank_by_conversation_sessions_without_duplicate_inflation(self):
        payload = platform_analytics_payload(self.db, "30d")
        self.assertEqual(payload["top_chatbots"][0]["chatbot_name"], "Support Bot")
        self.assertEqual(payload["top_chatbots"][0]["conversations"], 3)
        self.assertEqual(payload["top_chatbots"][0]["publication_status"], "published")
        self.assertEqual(payload["top_chatbots"][1]["chatbot_name"], "Training Bot")
        self.assertEqual(payload["top_chatbots"][1]["conversations"], 2)
        self.assertEqual(payload["top_chatbots"][1]["publication_status"], "draft_only")

    def test_invalid_range_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            platform_analytics_payload(self.db, "365d")
        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
