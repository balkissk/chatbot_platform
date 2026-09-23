import unittest
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.flow import Flow, FlowNode
from models.llm_config import LLMConfig
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from routes.version_routes import archive_version, get_versions, restore_version


class VersionLifecycleTest(unittest.TestCase):
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

        self.chatbot = Chatbot(name="Bot", project_id=self.project.id, language="en", is_active=True)
        self.db.add(self.chatbot)
        self.db.commit()

        self.published_version = VersionChatbot(
            chatbot_id=self.chatbot.id,
            version_number=1,
            status="published",
            published_at=datetime.utcnow(),
        )
        self.draft_version = VersionChatbot(
            chatbot_id=self.chatbot.id,
            version_number=2,
            status="draft",
            created_at=datetime.utcnow(),
        )
        self.db.add_all([self.published_version, self.draft_version])
        self.db.commit()

        self.chatbot.active_version_id = self.published_version.id
        self.db.add(LLMConfig(version_id=self.draft_version.id, model="test-model", temperature=0.3, system_prompt="Original prompt"))
        self.flow = Flow(version_id=self.draft_version.id, name="Original flow")
        self.db.add(self.flow)
        self.db.commit()
        self.db.add(FlowNode(flow_id=self.flow.id, node_key="start", type="message", label="Start", config={"text": "Original text"}))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_archive_and_restore_version_preserves_content_and_active_version(self):
        archived = archive_version(self.draft_version.id, db=self.db, current_user=self.manager)

        self.db.refresh(self.draft_version)
        self.db.refresh(self.chatbot)
        self.assertEqual(archived["version"]["status"], "archived")
        self.assertEqual(self.draft_version.status, "archived")
        self.assertIsNotNone(self.draft_version.archived_at)
        self.assertEqual(self.draft_version.archived_by, self.manager.id)
        self.assertEqual(self.chatbot.active_version_id, self.published_version.id)

        archived_again = archive_version(self.draft_version.id, db=self.db, current_user=self.manager)
        self.assertEqual(archived_again["message"], "Version already archived")
        listed_after_archive = get_versions(self.chatbot.id, db=self.db, current_user=self.manager)
        archived_list_item = next(version for version in listed_after_archive if version["id"] == self.draft_version.id)
        self.assertEqual(archived_list_item["status"], "archived")
        self.assertIsNotNone(archived_list_item["archived_at"])

        restored = restore_version(self.draft_version.id, db=self.db, current_user=self.manager)

        self.db.refresh(self.draft_version)
        self.db.refresh(self.chatbot)
        self.assertEqual(restored["version"]["status"], "draft")
        self.assertEqual(self.draft_version.status, "draft")
        self.assertIsNone(self.draft_version.archived_at)
        self.assertIsNone(self.draft_version.archived_by)
        self.assertEqual(self.chatbot.active_version_id, self.published_version.id)

        config = self.db.query(LLMConfig).filter(LLMConfig.version_id == self.draft_version.id).one()
        flow = self.db.query(Flow).filter(Flow.version_id == self.draft_version.id).one()
        node = self.db.query(FlowNode).filter(FlowNode.flow_id == flow.id).one()
        self.assertEqual(config.system_prompt, "Original prompt")
        self.assertEqual(flow.name, "Original flow")
        self.assertEqual(node.config, {"text": "Original text"})

        restored_again = restore_version(self.draft_version.id, db=self.db, current_user=self.manager)
        self.assertEqual(restored_again["message"], "Version already restored")
        listed_after_restore = get_versions(self.chatbot.id, db=self.db, current_user=self.manager)
        restored_list_item = next(version for version in listed_after_restore if version["id"] == self.draft_version.id)
        self.assertEqual(restored_list_item["status"], "draft")
        self.assertIsNone(restored_list_item["archived_at"])

    def test_archive_rejects_active_version(self):
        with self.assertRaises(HTTPException) as raised:
            archive_version(self.published_version.id, db=self.db, current_user=self.manager)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail, "Cannot archive the active version. Publish another version first.")


if __name__ == "__main__":
    unittest.main()
