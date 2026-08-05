import unittest
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.flow import Flow, FlowNode, FlowTransition
from models.llm_config import LLMConfig
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from models.version_smoke_test import VersionSmokeTest
from routes.version_routes import get_version_readiness, publish_version, smoke_test_version


class PublicationReadinessTest(unittest.TestCase):
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
            name="Bot",
            project_id=self.project.id,
            language="en",
            is_active=True,
            public_api_key="cp_test",
            public_api_enabled=True,
        )
        self.db.add(self.chatbot)
        self.db.commit()
        self.version = VersionChatbot(
            chatbot_id=self.chatbot.id,
            version_number=1,
            status="draft",
            created_at=datetime.utcnow(),
        )
        self.db.add(self.version)
        self.db.commit()
        self.flow = Flow(version_id=self.version.id, name="Flow")
        self.db.add(self.flow)
        self.db.commit()
        self.db.add_all([
            FlowNode(flow_id=self.flow.id, node_key="start", type="message", label="Start", config={"text": "Hello"}),
            FlowNode(flow_id=self.flow.id, node_key="end", type="end", label="End", config={"message": "Done"}),
            FlowTransition(flow_id=self.flow.id, source_node_key="start", target_node_key="end", label="next"),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_config(self, prompt: str = "You are a helpful assistant") -> None:
        self.db.add(LLMConfig(version_id=self.version.id, model="test", temperature=0.2, system_prompt=prompt))
        self.db.commit()

    def test_blocked_checklist_prevents_publish(self):
        with self.assertRaises(HTTPException) as raised:
            publish_version(self.version.id, db=self.db, current_user=self.manager)

        self.assertEqual(raised.exception.status_code, 400)
        detail = raised.exception.detail
        self.assertEqual(detail["readiness"]["summary"]["blocked"], 1)
        self.assertEqual(self.version.status, "draft")

    def test_warnings_require_confirmation_and_confirmation_publishes(self):
        self.add_config()

        with self.assertRaises(HTTPException) as raised:
            publish_version(self.version.id, db=self.db, current_user=self.manager)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertGreaterEqual(raised.exception.detail["readiness"]["summary"]["warnings"], 1)

        response = publish_version(self.version.id, confirm_warnings=True, db=self.db, current_user=self.manager)
        self.db.refresh(self.version)
        self.assertEqual(response["version"]["status"], "published")
        self.assertEqual(self.version.status, "published")

    def test_deterministic_flow_without_ai_rag_has_no_fallback_warning(self):
        self.add_config()

        readiness = get_version_readiness(self.version.id, db=self.db, current_user=self.manager)
        codes = [check["code"] for check in readiness["checks"]]

        self.assertNotIn("FALLBACK_MESSAGE_CONFIGURED", codes)

    def test_smoke_test_records_result_and_readiness_uses_it(self):
        self.add_config()

        result = smoke_test_version(self.version.id, db=self.db, current_user=self.manager)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(self.db.query(VersionSmokeTest).filter(VersionSmokeTest.version_id == self.version.id).count(), 1)

        readiness = get_version_readiness(self.version.id, db=self.db, current_user=self.manager)
        smoke_check = next(check for check in readiness["checks"] if check["code"] == "RUNTIME_SMOKE_TEST")
        self.assertEqual(smoke_check["status"], "PASSED")


if __name__ == "__main__":
    unittest.main()
