import unittest
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.chatbot_channel import ChatbotChannel
from models.conversation import ConversationMessage, ConversationSession
from models.project import Project
from models.runtime_log import RuntimeLog
from models.user import User
from models.version import VersionChatbot
from routes.admin_analytics_routes import (
    admin_chatbot_list_payload,
    analytics_chatbot_details,
)
from services.auth import require_roles


class AdminChatbotsTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()
        self.now = datetime.utcnow()

        self.admin = User(name="Admin", email="admin@example.com", password_hash="x", role="admin", status="active")
        self.manager_a = User(name="Manager A", email="a@example.com", password_hash="x", role="manager", status="active")
        self.manager_b = User(name="Manager B", email="b@example.com", password_hash="x", role="manager", status="active")
        self.db.add_all([self.admin, self.manager_a, self.manager_b])
        self.db.commit()

        self.project_a = Project(name="Support", description="", user_id=self.manager_a.id)
        self.project_b = Project(name="Training", description="", user_id=self.manager_b.id)
        self.db.add_all([self.project_a, self.project_b])
        self.db.commit()

        self.published_bot = Chatbot(
            name="Support Bot",
            description="Customer support",
            language="en",
            project_id=self.project_a.id,
            is_active=True,
            public_api_key="cp_secret_should_not_leak",
        )
        self.draft_bot = Chatbot(name="Training Bot", language="fr", project_id=self.project_b.id, is_active=True)
        self.disabled_bot = Chatbot(name="Disabled Bot", language="en", project_id=self.project_b.id, is_active=False)
        self.db.add_all([self.published_bot, self.draft_bot, self.disabled_bot])
        self.db.commit()

        self.draft_v1 = VersionChatbot(chatbot_id=self.published_bot.id, version_number=1, status="archived")
        self.published_v2 = VersionChatbot(
            chatbot_id=self.published_bot.id,
            version_number=2,
            status="published",
            published_at=self.now,
        )
        self.draft_only_v1 = VersionChatbot(chatbot_id=self.draft_bot.id, version_number=1, status="draft")
        self.disabled_v1 = VersionChatbot(chatbot_id=self.disabled_bot.id, version_number=1, status="draft")
        self.db.add_all([self.draft_v1, self.published_v2, self.draft_only_v1, self.disabled_v1])
        self.db.commit()
        self.published_bot.active_version_id = self.published_v2.id

        session_1 = ConversationSession(
            chatbot_id=self.published_bot.id,
            version_id=self.published_v2.id,
            updated_at=self.now - timedelta(minutes=10),
        )
        session_2 = ConversationSession(
            chatbot_id=self.published_bot.id,
            version_id=self.published_v2.id,
            updated_at=self.now - timedelta(minutes=5),
        )
        self.db.add_all([session_1, session_2])
        self.db.commit()
        self.db.add_all([
            ConversationMessage(session_id=session_1.id, role="user", content="hello"),
            ConversationMessage(session_id=session_1.id, role="bot", content="hi"),
            RuntimeLog(
                chatbot_id=self.published_bot.id,
                version_id=self.published_v2.id,
                project_id=self.project_a.id,
                conversation_id=session_1.id,
                channel="api",
                status="success",
                rag_used=False,
                created_at=self.now - timedelta(minutes=3),
            ),
            ChatbotChannel(
                chatbot_id=self.published_bot.id,
                channel_type="api",
                status="connected",
                deployed_version_id=self.published_v2.id,
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_platform_admin_can_list_all_chatbots_with_stats(self):
        payload = admin_chatbot_list_payload(self.db, page=1, page_size=10)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["stats"], {
            "total": 3,
            "published": 1,
            "draft_only": 1,
            "disabled": 1,
        })

    def test_manager_cannot_access_admin_chatbot_endpoint(self):
        with self.assertRaises(HTTPException) as raised:
            require_roles("admin")(self.manager_a)
        self.assertEqual(raised.exception.status_code, 403)

    def test_pagination_and_search_work(self):
        page = admin_chatbot_list_payload(self.db, page=1, page_size=1)
        self.assertEqual(page["total"], 3)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["total_pages"], 3)

        searched = admin_chatbot_list_payload(self.db, search="Support", page=1, page_size=10)
        self.assertEqual(searched["total"], 1)
        self.assertEqual(searched["items"][0]["chatbot_name"], "Support Bot")

    def test_owner_project_and_status_filters_work(self):
        owner_payload = admin_chatbot_list_payload(self.db, owner_id=self.manager_a.id, page=1, page_size=10)
        self.assertEqual(owner_payload["total"], 1)
        self.assertEqual(owner_payload["items"][0]["owner_name"], "Manager A")

        project_payload = admin_chatbot_list_payload(self.db, project_id=self.project_b.id, page=1, page_size=10)
        self.assertEqual(project_payload["total"], 2)

        published_payload = admin_chatbot_list_payload(self.db, publication_status="published", page=1, page_size=10)
        self.assertEqual(published_payload["total"], 1)
        self.assertEqual(published_payload["items"][0]["publication_status"], "published")

        draft_payload = admin_chatbot_list_payload(self.db, publication_status="draft_only", page=1, page_size=10)
        self.assertEqual(draft_payload["total"], 1)
        self.assertEqual(draft_payload["items"][0]["publication_status"], "draft_only")

        disabled_payload = admin_chatbot_list_payload(self.db, publication_status="disabled", page=1, page_size=10)
        self.assertEqual(disabled_payload["total"], 1)
        self.assertEqual(disabled_payload["items"][0]["publication_status"], "disabled")

    def test_counts_and_published_version_are_not_inflated_by_joins(self):
        payload = admin_chatbot_list_payload(self.db, search="Support", page=1, page_size=10)
        item = payload["items"][0]
        self.assertEqual(item["versions_count"], 2)
        self.assertEqual(item["published_version_id"], self.published_v2.id)
        self.assertEqual(item["published_version_label"], "v2")
        self.assertEqual(item["conversations_count"], 2)
        self.assertEqual(item["runtime_request_count"], 1)
        self.assertEqual(item["deployment_status"], "deployed")
        self.assertEqual(item["enabled_channels"], ["api"])
        self.assertNotIn("public_api_key", item)

    def test_details_endpoint_returns_safe_chatbot_details(self):
        details = analytics_chatbot_details(self.published_bot.id, db=self.db, current_user=self.admin)
        self.assertEqual(details["chatbot_name"], "Support Bot")
        self.assertEqual(details["owner_email"], "a@example.com")
        self.assertEqual(details["project_name"], "Support")
        self.assertNotIn("public_api_key", details)
        self.assertNotIn("rag_settings", details)

    def test_invalid_chatbot_id_returns_404(self):
        with self.assertRaises(HTTPException) as raised:
            analytics_chatbot_details(9999, db=self.db, current_user=self.admin)
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
