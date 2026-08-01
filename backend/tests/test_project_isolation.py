import unittest
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.conversation import ConversationMessage, ConversationSession
from models.knowledge_base import KnowledgeBase
from models.llm_config import LLMConfig
from models.document import Document
from models.chunk import Chunk
from models.flow import Flow, FlowNode, FlowTransition
from models.project import Project, ProjectStatus
from models.project_schema import ProjectCreate, ProjectUpdate
from models.runtime_log import RuntimeLog
from models.user import User
from models.version import VersionChatbot
from routes.flow_routes import get_flow, update_node, update_transition
from routes.project_routes import (
    archive_project,
    create_project,
    delete_project,
    duplicate_project,
    get_project,
    get_project_analytics,
    get_project_workspace_dashboard,
    get_projects,
    get_projects_summary,
    query_projects,
    restore_project,
    update_project,
)


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
        self.assertEqual(project["status"], ProjectStatus.active.value)

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
        self.assertEqual(project["last_activity"], datetime(2026, 1, 12))

    def test_archive_and_restore_project_preserve_data(self):
        chatbot = Chatbot(name="Keep Bot", project_id=self.project_a1.id, language="en", is_active=True)
        self.db.add(chatbot)
        self.db.commit()

        archived = archive_project(self.project_a1.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(archived["status"], ProjectStatus.archived.value)
        self.assertIsNotNone(archived["archived_at"])
        self.assertEqual(self.db.query(Chatbot).filter(Chatbot.project_id == self.project_a1.id).count(), 1)

        projects = get_projects(status="archived", db=self.db, current_user=self.manager_a)
        self.assertEqual([project["id"] for project in projects], [self.project_a1.id])

        restored = restore_project(self.project_a1.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(restored["status"], ProjectStatus.active.value)
        self.assertIsNone(restored["archived_at"])

    def test_manager_cannot_archive_restore_or_duplicate_other_manager_project(self):
        for action in (archive_project, restore_project, duplicate_project):
            with self.assertRaises(HTTPException) as error:
                action(self.project_b1.id, db=self.db, current_user=self.manager_a)
            self.assertEqual(error.exception.status_code, 404)

    def test_duplicate_project_copies_only_safe_project_metadata(self):
        chatbot = Chatbot(name="Source Bot", project_id=self.project_a1.id, language="en", is_active=True)
        self.db.add(chatbot)
        self.db.commit()

        duplicate = duplicate_project(self.project_a1.id, db=self.db, current_user=self.manager_a)
        self.assertNotEqual(duplicate["id"], self.project_a1.id)
        self.assertEqual(duplicate["name"], "Alpha One Copy")
        self.assertEqual(duplicate["description"], self.project_a1.description)
        self.assertEqual(duplicate["status"], ProjectStatus.active.value)
        self.assertEqual(duplicate["assistant_count"], 0)
        self.assertEqual(self.db.query(Chatbot).filter(Chatbot.project_id == duplicate["id"]).count(), 0)

        second_duplicate = duplicate_project(self.project_a1.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(second_duplicate["name"], "Alpha One Copy 2")

    def test_soft_delete_excludes_project_and_preserves_related_data(self):
        chatbot = Chatbot(name="Preserved Bot", project_id=self.project_a1.id, language="en", is_active=True)
        self.db.add(chatbot)
        self.db.commit()

        response = delete_project(self.project_a1.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(response["message"], "Project deleted")

        stored = self.db.query(Project).filter(Project.id == self.project_a1.id).first()
        self.assertEqual(stored.status, ProjectStatus.disabled.value)
        self.assertIsNotNone(stored.deleted_at)
        self.assertEqual(self.db.query(Chatbot).filter(Chatbot.project_id == self.project_a1.id).count(), 1)

        projects = get_projects(db=self.db, current_user=self.manager_a)
        self.assertNotIn(self.project_a1.id, {project["id"] for project in projects})

        with self.assertRaises(HTTPException) as read_error:
            get_project(self.project_a1.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(read_error.exception.status_code, 404)

    def test_project_list_filters_sorting_pagination_and_aggregate_aliases(self):
        self.project_a1.status = ProjectStatus.archived.value
        self.project_a1.archived_at = datetime(2026, 1, 3)
        self.project_a1.created_at = datetime(2026, 1, 1)
        self.project_a2.created_at = datetime(2026, 1, 2)
        self.db.commit()

        bot_one = Chatbot(name="One", project_id=self.project_a1.id, language="en", is_active=True)
        bot_two = Chatbot(name="Two", project_id=self.project_a1.id, language="en", is_active=True)
        bot_other = Chatbot(name="Other", project_id=self.project_a2.id, language="en", is_active=True)
        self.db.add_all([bot_one, bot_two, bot_other])
        self.db.commit()

        version = VersionChatbot(chatbot_id=bot_one.id, version_number=1, status="published")
        self.db.add(version)
        self.db.commit()
        bot_one.active_version_id = version.id
        self.db.add(RuntimeLog(
            chatbot_id=bot_other.id,
            project_id=self.project_a2.id,
            channel="api",
            status="success",
            created_at=datetime(2026, 1, 10),
        ))
        self.db.commit()

        archived = get_projects(status="archived", db=self.db, current_user=self.manager_a)
        self.assertEqual([project["id"] for project in archived], [self.project_a1.id])

        created_range = get_projects(
            created_from=datetime(2026, 1, 2).date(),
            created_to=datetime(2026, 1, 2).date(),
            db=self.db,
            current_user=self.manager_a,
        )
        self.assertEqual([project["id"] for project in created_range], [self.project_a2.id])

        by_assistants = get_projects(sort="assistants", db=self.db, current_user=self.manager_a)
        self.assertEqual(by_assistants[0]["id"], self.project_a1.id)
        self.assertEqual(by_assistants[0]["assistants_count"], 2)
        self.assertEqual(by_assistants[0]["published_assistants_count"], 1)
        self.assertEqual(by_assistants[0]["draft_assistants_count"], 1)

        by_activity = get_projects(sort="recent_activity", db=self.db, current_user=self.manager_a)
        self.assertEqual(by_activity[0]["id"], self.project_a2.id)

        page_two = get_projects(sort="name", page=2, page_size=1, db=self.db, current_user=self.manager_a)
        self.assertEqual(len(page_two), 1)

    def test_project_query_returns_enterprise_pagination_metadata(self):
        self.project_a1.status = ProjectStatus.archived.value
        self.project_a2.status = ProjectStatus.active.value
        self.db.commit()

        default_page = query_projects(db=self.db, current_user=self.manager_a, page=1, page_size=1, sort="name")
        self.assertEqual(default_page.total, 1)
        self.assertEqual(default_page.items[0].id, self.project_a2.id)
        self.assertFalse(default_page.has_next)
        self.assertFalse(default_page.has_previous)

        archived_page = query_projects(
            status="archived",
            db=self.db,
            current_user=self.manager_a,
            page=1,
            page_size=10,
        )
        self.assertEqual(archived_page.total, 1)
        self.assertEqual(archived_page.items[0].id, self.project_a1.id)

    def test_manager_cannot_filter_by_another_owner(self):
        with self.assertRaises(HTTPException) as error:
            get_projects(owner_id=self.manager_b.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(error.exception.status_code, 403)

    def test_workspace_dashboard_uses_project_scope_and_real_runtime_metrics(self):
        published_bot = Chatbot(name="Published", project_id=self.project_a1.id, language="en", is_active=True)
        draft_bot = Chatbot(name="Draft", project_id=self.project_a1.id, language="en", is_active=True)
        other_manager_bot = Chatbot(name="Other", project_id=self.project_b1.id, language="en", is_active=True)
        self.db.add_all([published_bot, draft_bot, other_manager_bot])
        self.db.commit()

        published_version = VersionChatbot(
            chatbot_id=published_bot.id,
            version_number=1,
            status="published",
            published_at=datetime(2026, 1, 5),
        )
        draft_version = VersionChatbot(chatbot_id=draft_bot.id, version_number=1, status="draft")
        other_version = VersionChatbot(chatbot_id=other_manager_bot.id, version_number=1, status="published")
        self.db.add_all([published_version, draft_version, other_version])
        self.db.commit()
        published_bot.active_version_id = published_version.id

        flow = Flow(version_id=published_version.id, name="Flow")
        self.db.add(flow)
        self.db.commit()
        self.db.add_all([
            FlowNode(flow_id=flow.id, node_key="start", type="message", label="Start", config={"text": "Hi"}),
            FlowNode(flow_id=flow.id, node_key="end", type="end", label="End", config={}),
            FlowTransition(flow_id=flow.id, source_node_key="start", target_node_key="end"),
            LLMConfig(version_id=published_version.id, model="test-model"),
        ])
        kb = KnowledgeBase(name="KB", version_id=published_version.id)
        self.db.add(kb)
        self.db.commit()
        document = Document(knowledge_base_id=kb.id, filename="guide.txt", content_type="text/plain", storage_url="", status="processed")
        self.db.add(document)
        self.db.commit()
        self.db.add(Chunk(document_id=document.id, order=1, text="answer", embedding_status="ready", embedding=[0.1]))
        self.db.commit()

        session = ConversationSession(
            chatbot_id=published_bot.id,
            version_id=published_version.id,
            updated_at=datetime(2026, 1, 8),
        )
        self.db.add(session)
        self.db.commit()
        self.db.add_all([
            ConversationMessage(session_id=session.id, role="user", content="Question?", created_at=datetime(2026, 1, 8, 10, 0)),
            ConversationMessage(session_id=session.id, role="bot", content="Answer", sources=[{"chunk_id": 1}], created_at=datetime(2026, 1, 8, 10, 0, 1)),
            RuntimeLog(
                chatbot_id=published_bot.id,
                version_id=published_version.id,
                project_id=self.project_a1.id,
                conversation_id=session.id,
                channel="public_chat",
                status="success",
                rag_used=True,
                response_time_ms=120,
                created_at=datetime(2026, 1, 8, 10, 0, 2),
            ),
            RuntimeLog(
                chatbot_id=draft_bot.id,
                version_id=draft_version.id,
                project_id=self.project_a1.id,
                channel="api",
                status="failed",
                response_time_ms=240,
                error_type="InternalRuntimeError",
                error_message="Runtime failed",
                created_at=datetime(2026, 1, 8, 10, 2),
            ),
            RuntimeLog(
                chatbot_id=other_manager_bot.id,
                version_id=other_version.id,
                project_id=self.project_b1.id,
                channel="api",
                status="success",
                response_time_ms=10,
                created_at=datetime(2026, 1, 8, 10, 3),
            ),
        ])
        self.db.commit()

        dashboard = get_project_workspace_dashboard(self.project_a1.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(dashboard["summary"]["total_assistants"], 2)
        self.assertEqual(dashboard["summary"]["published_assistants"], 1)
        self.assertEqual(dashboard["summary"]["draft_only_assistants"], 1)

        metrics = {metric["label"]: metric for metric in dashboard["metrics"]}
        self.assertEqual(metrics["Knowledge Answer Coverage"]["value"], 100)
        self.assertEqual(metrics["Runtime Requests"]["value"], 2)
        self.assertEqual(metrics["Runtime Success Rate"]["value"], 50)
        self.assertEqual(dashboard["release_state"]["latest_version"]["version_number"], 1)
        self.assertEqual(dashboard["release_state"]["published_version"]["version_number"], 1)
        self.assertEqual(len(dashboard["operational_alerts"]), 1)

    def test_workspace_dashboard_denies_other_manager_project(self):
        with self.assertRaises(HTTPException) as error:
            get_project_workspace_dashboard(self.project_b1.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(error.exception.status_code, 404)

    def test_workspace_dashboard_zero_data_is_not_misleading(self):
        dashboard = get_project_workspace_dashboard(self.project_a1.id, db=self.db, current_user=self.manager_a)
        metrics = {metric["label"]: metric for metric in dashboard["metrics"]}
        self.assertEqual(metrics["Runtime Requests"]["value"], 0)
        self.assertIsNone(metrics["Runtime Success Rate"]["value"])
        self.assertIsNone(metrics["Knowledge Answer Coverage"]["value"])
        self.assertIsNone(dashboard["release_state"]["published_version"])

    def test_workspace_dashboard_excludes_small_talk_from_knowledge_coverage(self):
        chatbot = Chatbot(name="RAG Bot", project_id=self.project_a1.id, language="en", is_active=True)
        self.db.add(chatbot)
        self.db.commit()
        version = VersionChatbot(chatbot_id=chatbot.id, version_number=1, status="published")
        self.db.add(version)
        self.db.commit()
        chatbot.active_version_id = version.id
        kb = KnowledgeBase(name="KB", version_id=version.id)
        self.db.add(kb)
        self.db.commit()
        document = Document(knowledge_base_id=kb.id, filename="guide.txt", content_type="text/plain", storage_url="", status="ready")
        self.db.add(document)
        self.db.commit()
        self.db.add(Chunk(document_id=document.id, order=1, text="answer", embedding_status="ready", embedding=[0.1]))
        session = ConversationSession(chatbot_id=chatbot.id, version_id=version.id, updated_at=datetime(2026, 1, 8))
        self.db.add(session)
        self.db.commit()
        self.db.add_all([
            ConversationMessage(session_id=session.id, role="user", content="bonjour", created_at=datetime(2026, 1, 8, 10, 0)),
            ConversationMessage(session_id=session.id, role="bot", content="Bonjour", sources=[], created_at=datetime(2026, 1, 8, 10, 0, 1)),
        ])
        self.db.commit()

        dashboard = get_project_workspace_dashboard(self.project_a1.id, db=self.db, current_user=self.manager_a)
        metrics = {metric["label"]: metric for metric in dashboard["metrics"]}

        self.assertIsNone(metrics["Knowledge Answer Coverage"]["value"])
        self.assertEqual(dashboard["quality_signals"], [])

    def test_workspace_dashboard_classifies_no_published_version_as_publication_blocker(self):
        chatbot = Chatbot(name="Draft Bot", project_id=self.project_a1.id, language="en", is_active=True)
        self.db.add(chatbot)
        self.db.commit()
        version = VersionChatbot(chatbot_id=chatbot.id, version_number=1, status="draft")
        self.db.add(version)
        self.db.commit()
        self.db.add(RuntimeLog(
            chatbot_id=chatbot.id,
            version_id=version.id,
            project_id=self.project_a1.id,
            channel="public_chat",
            status="failed",
            error_message="Chatbot has no published version",
            created_at=datetime(2026, 1, 8, 10, 0),
        ))
        self.db.commit()

        dashboard = get_project_workspace_dashboard(self.project_a1.id, db=self.db, current_user=self.manager_a)

        self.assertEqual(dashboard["operational_alerts"][0]["title"], "Publication blocker")
        self.assertEqual(dashboard["operational_alerts"][0]["category"], "publication")
        self.assertEqual(dashboard["operational_alerts"][0]["affected_assistant_id"], chatbot.id)

    def test_project_analytics_uses_real_project_scoped_data(self):
        chatbot = Chatbot(name="Analytics Bot", project_id=self.project_a1.id, language="en", is_active=True)
        other_chatbot = Chatbot(name="Other Bot", project_id=self.project_b1.id, language="en", is_active=True)
        self.db.add_all([chatbot, other_chatbot])
        self.db.commit()
        version = VersionChatbot(chatbot_id=chatbot.id, version_number=1, status="published")
        other_version = VersionChatbot(chatbot_id=other_chatbot.id, version_number=1, status="published")
        self.db.add_all([version, other_version])
        self.db.commit()
        chatbot.active_version_id = version.id
        self.db.commit()

        session = ConversationSession(chatbot_id=chatbot.id, version_id=version.id)
        self.db.add(session)
        self.db.commit()
        self.db.add_all([
            ConversationMessage(session_id=session.id, role="user", content="Question"),
            ConversationMessage(session_id=session.id, role="bot", content="I don't know"),
            RuntimeLog(
                chatbot_id=chatbot.id,
                version_id=version.id,
                project_id=self.project_a1.id,
                conversation_id=session.id,
                channel="web_widget",
                status="success",
                response_time_ms=100,
            ),
            RuntimeLog(
                chatbot_id=chatbot.id,
                version_id=version.id,
                project_id=self.project_a1.id,
                channel="web_widget",
                status="failed",
                response_time_ms=200,
                error_message="Failure",
            ),
            RuntimeLog(
                chatbot_id=other_chatbot.id,
                version_id=other_version.id,
                project_id=self.project_b1.id,
                channel="api",
                status="failed",
            ),
        ])
        self.db.commit()

        analytics = get_project_analytics(self.project_a1.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(analytics["kpis"]["conversations_count"], 1)
        self.assertEqual(analytics["kpis"]["messages_count"], 2)
        self.assertEqual(analytics["kpis"]["runtime_request_count"], 2)
        self.assertEqual(analytics["kpis"]["runtime_success_rate"], 50)
        self.assertEqual(analytics["kpis"]["runtime_failure_count"], 1)
        self.assertEqual(analytics["kpis"]["fallback_count"], 1)
        self.assertEqual(analytics["usage_by_channel"][0]["channel"], "web_widget")
        self.assertEqual(len(analytics["recent_errors"]), 1)

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
