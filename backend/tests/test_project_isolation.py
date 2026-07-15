import unittest
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.conversation import ConversationSession
from models.flow import Flow, FlowNode, FlowTransition
from models.project import Project
from models.project_schema import ProjectCreate, ProjectUpdate
from models.runtime_log import RuntimeLog
from models.user import User
from models.version import VersionChatbot
from routes.flow_routes import get_flow, update_node, update_transition
from routes.project_routes import create_project, delete_project, get_project, get_projects, get_projects_summary, update_project


class ProjectIsolationTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.manager_a = User(name="Manager A", email="a@example.com", password_hash="x", role="manager", status="active")
        self.manager_b = User(name="Manager B", email="b@example.com", password_hash="x", role="manager", status="active")
        self.admin = User(name="Admin", email="admin@example.com", password_hash="x", role="admin", status="active")
        self.db.add_all([self.manager_a, self.manager_b, self.admin])
        self.db.commit()

        self.project_a1 = Project(name="Alpha One", description="A1", user_id=self.manager_a.id, created_at=datetime.utcnow())
        self.project_a2 = Project(name="Alpha Two", description="A2", user_id=self.manager_a.id, created_at=datetime.utcnow())
        self.project_b1 = Project(name="Beta One", description="B1", user_id=self.manager_b.id, created_at=datetime.utcnow())
        self.project_b2 = Project(name="Beta Two", description="B2", user_id=self.manager_b.id, created_at=datetime.utcnow())
        self.db.add_all([self.project_a1, self.project_a2, self.project_b1, self.project_b2])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_manager_a_sees_only_manager_a_projects(self):
        projects = get_projects(
            search=None,
            limit=50,
            offset=0,
            db=self.db,
            current_user=self.manager_a,
        )
        self.assertEqual({project["id"] for project in projects}, {self.project_a1.id, self.project_a2.id})

    def test_manager_b_sees_only_manager_b_projects(self):
        projects = get_projects(
            search=None,
            limit=50,
            offset=0,
            db=self.db,
            current_user=self.manager_b,
        )
        self.assertEqual({project["id"] for project in projects}, {self.project_b1.id, self.project_b2.id})

    def test_manager_cannot_read_update_or_delete_other_manager_project(self):
        with self.assertRaises(HTTPException) as read_error:
            get_project(self.project_b1.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(read_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as update_error:
            update_project(
                self.project_b1.id,
                ProjectUpdate(name="Changed", description="Changed"),
                db=self.db,
                current_user=self.manager_a,
            )
        self.assertEqual(update_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as delete_error:
            delete_project(self.project_b1.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(delete_error.exception.status_code, 404)

    def test_project_creation_assigns_current_manager_and_ignores_frontend_owner(self):
        payload = ProjectCreate(name="New Project", description="Owned by current user", user_id=self.manager_b.id)
        project = create_project(payload, db=self.db, current_user=self.manager_a)
        self.assertEqual(project["user_id"], self.manager_a.id)

    def test_admin_can_access_all_projects(self):
        projects = get_projects(
            search=None,
            limit=50,
            offset=0,
            db=self.db,
            current_user=self.admin,
        )
        self.assertEqual(len(projects), 4)

    def test_project_counts_and_search_are_scoped_to_manager(self):
        chatbot_a = Chatbot(name="A Bot", project_id=self.project_a1.id, language="en", is_active=True)
        chatbot_b = Chatbot(name="B Bot", project_id=self.project_b1.id, language="en", is_active=True)
        self.db.add_all([chatbot_a, chatbot_b])
        self.db.commit()
        self.db.add_all([
            VersionChatbot(chatbot_id=chatbot_a.id, version_number=1, status="published"),
            VersionChatbot(chatbot_id=chatbot_b.id, version_number=1, status="published"),
        ])
        self.db.commit()

        projects = get_projects(
            search="Beta",
            limit=50,
            offset=0,
            db=self.db,
            current_user=self.manager_a,
        )
        self.assertEqual(projects, [])

        projects = get_projects(
            search="Alpha",
            limit=50,
            offset=0,
            db=self.db,
            current_user=self.manager_a,
        )
        self.assertEqual({project["id"] for project in projects}, {self.project_a1.id, self.project_a2.id})
        published = sum(project["published_version_count"] for project in projects)
        self.assertEqual(published, 1)

    def test_manager_project_summary_uses_assistant_publication_rules(self):
        published_bot = Chatbot(name="Published", project_id=self.project_a1.id, language="en", is_active=True)
        draft_bot = Chatbot(name="Draft", project_id=self.project_a1.id, language="en", is_active=True)
        disabled_bot = Chatbot(name="Disabled", project_id=self.project_a1.id, language="en", is_active=False)
        other_manager_bot = Chatbot(name="Other", project_id=self.project_b1.id, language="en", is_active=True)
        self.db.add_all([published_bot, draft_bot, disabled_bot, other_manager_bot])
        self.db.commit()

        published_version = VersionChatbot(chatbot_id=published_bot.id, version_number=1, status="published")
        self.db.add(published_version)
        self.db.commit()
        published_bot.active_version_id = published_version.id
        self.db.add_all([
            VersionChatbot(chatbot_id=published_bot.id, version_number=2, status="published"),
            VersionChatbot(chatbot_id=draft_bot.id, version_number=1, status="draft"),
            VersionChatbot(chatbot_id=other_manager_bot.id, version_number=1, status="published"),
        ])
        self.db.commit()

        summary = get_projects_summary(db=self.db, current_user=self.manager_a)
        self.assertEqual(summary.projects, 2)
        self.assertEqual(summary.assistants, 3)
        self.assertEqual(summary.published_assistants, 1)
        self.assertEqual(summary.draft_only, 1)

        projects = get_projects(None, 50, 0, self.db, self.manager_a)
        project = next(item for item in projects if item["id"] == self.project_a1.id)
        self.assertEqual(project["assistant_count"], 3)
        self.assertEqual(project["published_assistant_count"], 1)
        self.assertEqual(project["draft_only_assistant_count"], 1)

    def test_project_last_activity_uses_real_persisted_activity(self):
        chatbot = Chatbot(
            name="Activity Bot",
            project_id=self.project_a1.id,
            language="en",
            is_active=True,
            created_at=datetime(2026, 1, 1),
        )
        self.db.add(chatbot)
        self.db.commit()
        version = VersionChatbot(chatbot_id=chatbot.id, version_number=1, status="published")
        self.db.add(version)
        self.db.commit()

        self.db.add_all([
            ConversationSession(chatbot_id=chatbot.id, version_id=version.id, updated_at=datetime(2026, 1, 10)),
            RuntimeLog(
                chatbot_id=chatbot.id,
                version_id=version.id,
                project_id=self.project_a1.id,
                channel="public_chat",
                status="success",
                created_at=datetime(2026, 1, 12),
            ),
        ])
        self.db.commit()

        project = get_project(self.project_a1.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(project["last_activity_at"], datetime(2026, 1, 12))

    def test_manager_cannot_access_other_manager_flow_resources(self):
        chatbot = Chatbot(name="B Bot", project_id=self.project_b1.id, language="en", is_active=True)
        self.db.add(chatbot)
        self.db.commit()
        version = VersionChatbot(chatbot_id=chatbot.id, version_number=1, status="draft")
        self.db.add(version)
        self.db.commit()
        flow = Flow(version_id=version.id, name="B Flow")
        self.db.add(flow)
        self.db.commit()
        node = FlowNode(flow_id=flow.id, node_key="start", type="message", label="Start", config={})
        transition = FlowTransition(flow_id=flow.id, source_node_key="start", target_node_key="end")
        self.db.add_all([node, transition])
        self.db.commit()

        with self.assertRaises(HTTPException) as flow_error:
            get_flow(version.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(flow_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as node_error:
            update_node(node.id, payload=type("Payload", (), {"label": "X", "config": None, "position_x": None, "position_y": None})(), db=self.db, current_user=self.manager_a)
        self.assertEqual(node_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as transition_error:
            update_transition(
                transition.id,
                payload=type("Payload", (), {"source_node_key": None, "target_node_key": None, "label": "X", "condition": None})(),
                db=self.db,
                current_user=self.manager_a,
            )
        self.assertEqual(transition_error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
