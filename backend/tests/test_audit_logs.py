import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.audit_log import AuditLog
from models.chatbot import Chatbot
from models.chatbot_schema import ChatbotCreate
from models.flow import Flow, FlowNode
from models.knowledge_schema import DocumentIngest
from models.llm_config import LLMConfig
from models.project import Project
from models.project_schema import ProjectCreate
from models.user import User
from models.user_schema import UserCreate, UserStatusUpdate
from models.version import VersionChatbot
from models.version_schema import VersionCreate
from routes.admin_analytics_routes import analytics_audit_logs, dashboard_overview_payload, recent_activity
from routes.auth_routes import create_user, update_user_status
from routes.chatbot_routes import create_chatbot
from routes.knowledge_routes import ingest_document
from routes.project_routes import create_project
from routes.version_routes import create_version, publish_version
from services.auth import require_roles
from services.unified_runtime import run_chatbot_message


class AuditLogTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()
        self.admin = User(name="Admin", email="admin@example.com", password_hash="x", role="admin", status="active")
        self.manager = User(name="Manager", email="manager@example.com", password_hash="x", role="manager", status="active")
        self.db.add_all([self.admin, self.manager])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_project_chatbot_version(self):
        project = Project(name="Project", description="", user_id=self.manager.id)
        self.db.add(project)
        self.db.commit()
        chatbot = Chatbot(name="Bot", project_id=project.id, language="en", is_active=True)
        self.db.add(chatbot)
        self.db.commit()
        version = VersionChatbot(chatbot_id=chatbot.id, version_number=1, status="draft", created_at=datetime.now(UTC).replace(tzinfo=None))
        self.db.add(version)
        self.db.commit()
        chatbot.active_version_id = version.id
        self.db.add(LLMConfig(version_id=version.id, model="test"))
        flow = Flow(version_id=version.id, name="Flow")
        self.db.add(flow)
        self.db.commit()
        self.db.add(FlowNode(flow_id=flow.id, node_key="start", type="message", label="Start", config={"text": "Hello"}))
        self.db.commit()
        return project, chatbot, version

    def latest_action(self):
        return self.db.query(AuditLog).order_by(AuditLog.id.desc()).first()

    def test_project_creation_creates_audit_log(self):
        project = create_project(ProjectCreate(name="Trip Project", description="Travel"), db=self.db, current_user=self.manager)
        log = self.latest_action()
        self.assertEqual(log.action, "PROJECT_CREATED")
        self.assertEqual(log.resource_type, "project")
        self.assertEqual(log.resource_id, project["id"])
        self.assertEqual(log.actor_user_id, self.manager.id)

    def test_chatbot_creation_creates_audit_log(self):
        project = Project(name="Project", description="", user_id=self.manager.id)
        self.db.add(project)
        self.db.commit()
        create_chatbot(
            ChatbotCreate(name="TripAssistant", description="", language="en", project_id=project.id),
            db=self.db,
            current_user=self.manager,
        )
        log = self.latest_action()
        self.assertEqual(log.action, "CHATBOT_CREATED")
        self.assertEqual(log.resource_name, "TripAssistant")
        self.assertEqual(log.metadata_json["project_id"], project.id)

    def test_version_creation_and_publish_create_audit_logs(self):
        _, chatbot, version = self.add_project_chatbot_version()
        created = create_version(VersionCreate(chatbot_id=chatbot.id), db=self.db, current_user=self.manager)
        self.assertEqual(self.latest_action().action, "VERSION_CREATED")

        with patch("routes.version_routes.validate_flow_version", return_value={"valid": True, "errors": []}):
            publish_version(created["id"], db=self.db, current_user=self.manager)
        log = self.latest_action()
        self.assertEqual(log.action, "VERSION_PUBLISHED")
        self.assertEqual(log.resource_name, f"v{created['version_number']}")
        self.assertNotEqual(log.resource_id, version.id)

    def test_document_upload_creates_audit_log(self):
        _, _, version = self.add_project_chatbot_version()
        ingest_document(
            version.id,
            DocumentIngest(filename="pricing.pdf", content="hello", content_type="application/pdf"),
            BackgroundTasks(),
            db=self.db,
            current_user=self.manager,
        )
        log = self.latest_action()
        self.assertEqual(log.action, "DOCUMENT_UPLOADED")
        self.assertEqual(log.resource_name, "pricing.pdf")
        self.assertNotIn("content", log.metadata_json)

    def test_user_disable_creates_audit_log(self):
        created = create_user(
            UserCreate(name="Manager 2", email="m2@example.com", password="password123", role="manager"),
            current_user=self.admin,
            db=self.db,
        )
        update_user_status(
            created.id,
            UserStatusUpdate(status="disabled"),
            current_user=self.admin,
            db=self.db,
        )
        log = self.latest_action()
        self.assertEqual(log.action, "USER_DISABLED")
        self.assertEqual(log.resource_type, "user")
        self.assertEqual(log.resource_name, "Manager 2")

    def test_public_chat_messages_do_not_create_audit_logs(self):
        _, chatbot, version = self.add_project_chatbot_version()
        version.status = "published"
        self.db.commit()
        run_chatbot_message(self.db, chatbot.id, "web", None, "hello")
        self.assertEqual(self.db.query(AuditLog).count(), 0)

    def test_audit_metadata_does_not_contain_secrets_or_messages(self):
        create_user(
            UserCreate(name="Secret User", email="secret@example.com", password="password123", role="manager"),
            current_user=self.admin,
            db=self.db,
        )
        log = self.latest_action()
        self.assertNotIn("password", str(log.metadata_json or {}).lower())
        self.assertNotIn("password123", str(log.metadata_json or {}))

    def test_admin_can_access_audit_logs_and_manager_dependency_rejects(self):
        create_project(ProjectCreate(name="Trip Project", description="Travel"), db=self.db, current_user=self.manager)
        payload = analytics_audit_logs(
            limit=25,
            offset=0,
            search=None,
            actor_id=None,
            action=None,
            resource_type=None,
            date_from=None,
            date_to=None,
            db=self.db,
            current_user=self.admin,
        )
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["action"], "Project Created")

        with self.assertRaises(HTTPException) as raised:
            require_roles("admin")(self.manager)
        self.assertEqual(raised.exception.status_code, 403)

    def test_dashboard_recent_activity_uses_audit_logs_and_empty_state_does_not_fallback(self):
        project, chatbot, version = self.add_project_chatbot_version()
        from models.conversation import ConversationSession
        self.db.add(ConversationSession(chatbot_id=chatbot.id, version_id=version.id, user_id=None, variables={}))
        self.db.commit()

        recent = recent_activity(self.db, 10)
        self.assertEqual(recent["source"], "audit_logs")
        self.assertEqual(recent["items"], [])
        payload = dashboard_overview_payload(self.db)
        self.assertEqual(payload["recent_activity"]["items"], [])

        create_project(ProjectCreate(name="Logged Project", description=""), db=self.db, current_user=self.manager)
        recent = recent_activity(self.db, 10)
        self.assertEqual(recent["items"][0]["action"], "Project Created")


if __name__ == "__main__":
    unittest.main()
