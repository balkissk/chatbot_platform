import unittest
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.conversation import ConversationMessage, ConversationSession
from models.document import Document
from models.chunk import Chunk
from models.knowledge_base import KnowledgeBase
from models.project import Project
from models.runtime_log import RuntimeLog
from models.user import User
from models.version import VersionChatbot
from routes.admin_analytics_routes import (
    dashboard_channels,
    dashboard_overview_payload,
    dashboard_usage,
    system_health,
    top_chatbots_rows,
)
from services.auth import require_roles
from fastapi import HTTPException


class AdminDashboardDataTest(unittest.TestCase):
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

    def add_platform_data(self):
        admin = User(name="Admin", email="admin@example.com", password_hash="x", role="admin", status="active", created_at=self.now)
        manager = User(name="Manager", email="manager@example.com", password_hash="x", role="manager", status="active", created_at=self.now)
        disabled = User(name="Disabled", email="disabled@example.com", password_hash="x", role="end_user", status="disabled", created_at=self.now)
        self.db.add_all([admin, manager, disabled])
        self.db.commit()

        project = Project(name="Project A", description="", user_id=manager.id, created_at=self.now)
        self.db.add(project)
        self.db.commit()

        bot_a = Chatbot(name="Bot A", project_id=project.id, language="en", is_active=True, created_at=self.now)
        bot_b = Chatbot(name="Bot B", project_id=project.id, language="en", is_active=False, created_at=self.now)
        self.db.add_all([bot_a, bot_b])
        self.db.commit()

        version_a = VersionChatbot(chatbot_id=bot_a.id, version_number=2, status="published", published_at=self.now, created_at=self.now)
        version_b = VersionChatbot(chatbot_id=bot_b.id, version_number=1, status="draft", created_at=self.now)
        self.db.add_all([version_a, version_b])
        self.db.commit()
        bot_a.active_version_id = version_a.id

        session_a = ConversationSession(chatbot_id=bot_a.id, version_id=version_a.id, user_id=manager.id, variables={}, created_at=self.now, updated_at=self.now)
        session_b = ConversationSession(chatbot_id=bot_a.id, version_id=version_a.id, user_id=None, variables={"__channel": "api"}, created_at=self.now - timedelta(days=1), updated_at=self.now)
        self.db.add_all([session_a, session_b])
        self.db.commit()

        self.db.add_all([
            ConversationMessage(session_id=session_a.id, role="user", content="Hi", created_at=self.now),
            ConversationMessage(session_id=session_a.id, role="bot", content="Hello", created_at=self.now),
            ConversationMessage(session_id=session_b.id, role="user", content="API hi", created_at=self.now),
        ])
        kb = KnowledgeBase(name="KB", version_id=version_a.id, created_at=self.now)
        self.db.add(kb)
        self.db.commit()
        doc = Document(knowledge_base_id=kb.id, filename="doc.pdf", status="processed", chunks_count=1, created_at=self.now)
        self.db.add(doc)
        self.db.commit()
        self.db.add(Chunk(document_id=doc.id, order=1, text="chunk", embedding_status="ready", embedding=[0.1]))
        self.db.commit()

        self.db.add_all([
            RuntimeLog(
                chatbot_id=bot_a.id,
                version_id=version_a.id,
                conversation_id=session_a.id,
                project_id=project.id,
                user_id=manager.id,
                channel="web",
                status="success",
                rag_used=True,
                response_time_ms=120,
                created_at=self.now,
            ),
            RuntimeLog(
                chatbot_id=bot_a.id,
                version_id=version_a.id,
                conversation_id=session_b.id,
                project_id=project.id,
                channel="api",
                status="failed",
                rag_used=False,
                response_time_ms=80,
                error_type="LLMProviderError",
                error_message="Provider unavailable",
                created_at=self.now - timedelta(hours=1),
            ),
        ])
        self.db.commit()

        return {"admin": admin, "manager": manager, "bot_a": bot_a, "bot_b": bot_b}

    def test_admin_authorization_dependency(self):
        dependency = require_roles("admin")
        admin = User(role="admin")
        manager = User(role="manager")
        self.assertIs(dependency(admin), admin)
        with self.assertRaises(HTTPException) as raised:
            dependency(manager)
        self.assertEqual(raised.exception.status_code, 403)

    def test_overview_counts_and_runtime_metrics(self):
        self.add_platform_data()
        payload = dashboard_overview_payload(self.db)
        self.assertEqual(payload["users"]["total"], 3)
        self.assertEqual(payload["users"]["active"], 2)
        self.assertEqual(payload["users"]["disabled"], 1)
        self.assertEqual(payload["users"]["active_managers"], 1)
        self.assertEqual(payload["chatbots"]["total"], 2)
        self.assertEqual(payload["chatbots"]["published"], 1)
        self.assertEqual(payload["chatbots"]["draft"], 1)
        self.assertEqual(payload["conversations"]["today"], 1)
        self.assertEqual(payload["conversations"]["total_messages"], 3)
        self.assertEqual(payload["knowledge_base"]["total_documents"], 1)
        self.assertEqual(payload["knowledge_base"]["total_chunks"], 1)
        self.assertEqual(payload["knowledge_base"]["total_embeddings"], 1)
        self.assertEqual(payload["runtime"]["total_requests"], 2)
        self.assertEqual(payload["runtime"]["successful_requests"], 1)
        self.assertEqual(payload["runtime"]["failed_requests"], 1)
        self.assertEqual(payload["runtime"]["success_rate"], 50.0)
        self.assertEqual(payload["runtime"]["average_response_time_ms"], 100)
        self.assertEqual(payload["runtime"]["rag_usage_rate"], 50.0)

    def test_channel_distribution(self):
        data = self.add_platform_data()
        legacy_session = ConversationSession(
            chatbot_id=data["bot_a"].id,
            version_id=data["bot_a"].active_version_id,
            user_id=None,
            variables={"__channel": "whatsapp"},
            created_at=self.now,
            updated_at=self.now,
        )
        self.db.add(legacy_session)
        self.db.commit()
        channels = dashboard_channels(self.db)
        self.assertEqual(channels["api"], 1)
        self.assertEqual(channels["unknown"], 1)
        self.assertEqual(channels["legacy_other"], 1)
        self.assertNotIn("whatsapp", channels)
        self.assertNotIn("messenger", channels)

    def test_top_chatbots_join_owner_project_and_version(self):
        rows = top_chatbots_rows(self.db, 5)
        self.assertEqual(rows, [])
        self.add_platform_data()
        rows = top_chatbots_rows(self.db, 5)
        self.assertEqual(rows[0]["chatbot_name"], "Bot A")
        self.assertEqual(rows[0]["owner_name"], "Manager")
        self.assertEqual(rows[0]["project_name"], "Project A")
        self.assertEqual(rows[0]["published_version_label"], "v2")
        self.assertEqual(rows[0]["conversation_count"], 2)

    def test_usage_fills_missing_days_and_runtime_series(self):
        self.add_platform_data()
        usage = dashboard_usage(self.db, 3)
        self.assertEqual(len(usage["labels"]), 3)
        self.assertEqual(len(usage["conversations"]), 3)
        self.assertEqual(len(usage["runtime_requests"]), 3)
        self.assertGreaterEqual(sum(usage["runtime_requests"]), 2)
        self.assertGreaterEqual(sum(usage["conversations"]), 2)

    def test_database_health(self):
        health = system_health(self.db)
        self.assertEqual(health["services"]["database"]["status"], "healthy")
        self.assertIsInstance(health["services"]["database"]["response_time_ms"], int)

    def test_runtime_health_uses_persisted_logs(self):
        self.add_platform_data()
        health = system_health(self.db)
        self.assertIn(health["services"]["runtime"]["status"], {"healthy", "warning"})
        self.assertEqual(health["services"]["runtime"]["failures_last_24h"], 1)

    def test_empty_database_behavior(self):
        payload = dashboard_overview_payload(self.db)
        self.assertEqual(payload["users"]["total"], 0)
        self.assertEqual(payload["chatbots"]["published"], 0)
        self.assertEqual(payload["top_chatbots"], [])
        self.assertEqual(payload["channels"]["public_chat"], 0)
        self.assertIsNone(payload["runtime"]["success_rate"])
        self.assertIsNone(payload["usage"]["runtime_requests"])
        self.assertEqual(payload["system_health"]["services"]["runtime"]["status"], "not_monitored")


if __name__ == "__main__":
    unittest.main()
