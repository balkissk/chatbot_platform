import unittest

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.audit_log import AuditLog
from models.chatbot import Chatbot
from models.chatbot_schema import ChatbotAiDraftRegenerate, ChatbotCreate, ChatbotSetupUpdate, ChatbotUpdate
from models.chunk import Chunk
from models.conversation import ConversationMessage, ConversationSession
from models.document import Document
from models.flow import Flow, FlowNode, FlowTransition
from models.knowledge_base import KnowledgeBase
from models.llm_config import LLMConfig
from models.project import Project
from models.runtime_log import RuntimeLog
from models.user import User
from models.version import VersionChatbot
from routes.chat_routes import prepare_rag_generation
from routes.chatbot_routes import create_chatbot, get_chatbot_setup, regenerate_ai_draft, reapply_template_to_new_draft, update_chatbot, update_chatbot_setup
from routes.flow_routes import AiGenerateRequest, FlowTemplateApply, FlowTemplateCreate, FlowTemplateRevisionCreate, FlowTemplateTestRun, FlowTemplateUpdate, GeneratedFlowApply, _normalize_ai_generation, apply_flow_template, apply_generated_flow, create_flow_template_from_flow, create_flow_template_revision_from_flow, get_flow_template_detail, list_flow_templates, run_flow_template_test, update_flow_template
from services.auth import require_roles
from services.generated_flow import ensure_generated_flow_is_valid, normalize_generated_flow
from services.templates import TEMPLATES, template_generated_payload, template_metadata, template_options


class ChatbotSetupTest(unittest.TestCase):
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

        self.project_a = Project(name="A", description="", user_id=self.manager_a.id)
        self.project_b = Project(name="B", description="", user_id=self.manager_b.id)
        self.db.add_all([self.project_a, self.project_b])
        self.db.commit()

        self.chatbot = Chatbot(
            name="Support Bot",
            description="Old description",
            language="fr",
            purpose="customer_support",
            build_method="template",
            channel="web_widget",
            template_key="customer_support_basic",
            source_template_key="customer_support_basic",
            project_id=self.project_a.id,
            is_active=True,
        )
        self.other_chatbot = Chatbot(name="Other", language="en", project_id=self.project_b.id, is_active=True)
        self.db.add_all([self.chatbot, self.other_chatbot])
        self.db.commit()

        self.version = VersionChatbot(chatbot_id=self.chatbot.id, version_number=1, status="draft")
        self.db.add(self.version)
        self.db.commit()
        self.chatbot.active_version_id = self.version.id

        self.flow = Flow(version_id=self.version.id, name="Flow")
        self.db.add(self.flow)
        self.db.commit()
        self.db.add_all([
            FlowNode(flow_id=self.flow.id, node_key="start", type="message", label="Start", config={"text": "Hello"}),
            FlowTransition(flow_id=self.flow.id, source_node_key="start", target_node_key="end"),
        ])
        self.kb = KnowledgeBase(name="KB", version_id=self.version.id)
        self.db.add(self.kb)
        self.db.commit()
        self.document = Document(
            knowledge_base_id=self.kb.id,
            filename="policy.txt",
            content_type="text/plain",
            storage_url="",
            raw_text="Synthetic test text",
            status="processed",
        )
        self.db.add(self.document)
        self.db.commit()
        self.db.add(Chunk(document_id=self.document.id, order=1, text="chunk", embedding_status="ready"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def audit_logs(self):
        return self.db.query(AuditLog).order_by(AuditLog.id.asc()).all()

    def test_manager_can_load_own_setup_with_current_values(self):
        setup = get_chatbot_setup(self.chatbot.id, db=self.db, current_user=self.manager_a)

        self.assertEqual(setup["name"], "Support Bot")
        self.assertEqual(setup["description"], "Old description")
        self.assertEqual(setup["language"], "fr")
        self.assertEqual(setup["purpose"], "customer_support")
        self.assertEqual(setup["assistant_type"], "customer_support")
        self.assertEqual(setup["creation_mode"], "template")
        self.assertEqual(setup["template_key"], "customer_support_basic")
        self.assertEqual(setup["source_template_key"], "customer_support_basic")
        self.assertEqual(setup["template_name"], "Customer Support Basic")
        self.assertTrue(setup["template_update_available"])
        self.assertFalse(setup["ai_regeneration_available"])

    def test_creation_template_provenance_rules(self):
        template_bot = create_chatbot(
            ChatbotCreate(
                name="Template Bot",
                description="",
                language="en",
                assistant_type="customer_support",
                creation_mode="template",
                project_id=self.project_a.id,
                template_key="customer_support_rag",
            ),
            db=self.db,
            current_user=self.manager_a,
        )
        scratch_bot = create_chatbot(
            ChatbotCreate(
                name="Scratch Bot",
                description="",
                language="en",
                assistant_type="custom",
                creation_mode="scratch",
                project_id=self.project_a.id,
                template_key="customer_support_rag",
            ),
            db=self.db,
            current_user=self.manager_a,
        )
        ai_bot = create_chatbot(
            ChatbotCreate(
                name="AI Bot",
                description="",
                language="en",
                assistant_type="custom",
                creation_mode="ai",
                project_id=self.project_a.id,
                template_key="customer_support_rag",
            ),
            db=self.db,
            current_user=self.manager_a,
        )

        self.assertEqual(template_bot["source_template_key"], "customer_support_rag")
        self.assertEqual(scratch_bot["source_template_key"], None)
        self.assertEqual(ai_bot["source_template_key"], None)

        with self.assertRaises(HTTPException) as error:
            create_chatbot(
                ChatbotCreate(
                    name="Bad Template Bot",
                    description="",
                    language="en",
                    assistant_type="customer_support",
                    creation_mode="template",
                    project_id=self.project_a.id,
                    template_key="missing_template",
                ),
                db=self.db,
                current_user=self.manager_a,
            )
        self.assertEqual(error.exception.status_code, 400)

    def test_all_builtin_templates_pass_flow_validation(self):
        for template_key in sorted(TEMPLATES):
            with self.subTest(template=template_key):
                nodes, transitions = template_generated_payload(template_key, "en")
                ensure_generated_flow_is_valid(
                    self.db,
                    self.chatbot.id,
                    nodes,
                    transitions,
                    template_key,
                )

    def test_manager_cannot_load_or_update_other_manager_setup(self):
        with self.assertRaises(HTTPException) as load_error:
            get_chatbot_setup(self.other_chatbot.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(load_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as update_error:
            update_chatbot_setup(
                self.other_chatbot.id,
                ChatbotSetupUpdate(name="Changed"),
                db=self.db,
                current_user=self.manager_a,
            )
        self.assertEqual(update_error.exception.status_code, 404)

    def test_admin_cannot_use_manager_setup_endpoint(self):
        with self.assertRaises(HTTPException) as error:
            require_roles("manager")(current_user=self.admin)
        self.assertEqual(error.exception.status_code, 403)

    def test_update_supported_fields_preserves_flow_versions_and_knowledge_base(self):
        node_count = self.db.query(FlowNode).count()
        transition_count = self.db.query(FlowTransition).count()
        version_count = self.db.query(VersionChatbot).count()
        document_count = self.db.query(Document).count()
        chunk_count = self.db.query(Chunk).count()

        setup = update_chatbot_setup(
            self.chatbot.id,
            ChatbotSetupUpdate(
                name="Updated Bot",
                description="Updated description",
                language="en",
                purpose="lead_generation",
                channel="rest_public_api",
            ),
            db=self.db,
            current_user=self.manager_a,
        )

        self.assertEqual(setup["name"], "Updated Bot")
        self.assertEqual(setup["purpose"], "lead_generation")
        self.assertEqual(setup["creation_mode"], "template")
        self.assertEqual(setup["channel"], "rest_public_api")
        self.assertEqual(self.db.query(FlowNode).count(), node_count)
        self.assertEqual(self.db.query(FlowTransition).count(), transition_count)
        self.assertEqual(self.db.query(VersionChatbot).count(), version_count)
        self.assertEqual(self.db.query(Document).count(), document_count)
        self.assertEqual(self.db.query(Chunk).count(), chunk_count)

        log = self.audit_logs()[-1]
        self.assertEqual(log.action, "ASSISTANT_SETUP_UPDATED")
        self.assertEqual(log.resource_id, self.chatbot.id)
        self.assertEqual(log.metadata_json["changed_fields"], ["name", "description", "language", "purpose", "channel"])

    def test_unsupported_and_protected_fields_are_rejected_by_schema(self):
        for field in ["creation_mode", "build_method", "owner_id", "project_id", "active_version_id", "status"]:
            with self.assertRaises(ValidationError):
                ChatbotSetupUpdate(**{field: "malicious"})

    def test_language_and_channel_schema_values_are_normalized(self):
        created = ChatbotCreate(
            name="Channel Bot",
            description="",
            language="English",
            assistant_type="custom",
            creation_mode="scratch",
            project_id=self.project_a.id,
            channel="REST Public API",
        )
        self.assertEqual(created.language, "en")
        self.assertEqual(created.channel, "rest_public_api")

        updated = ChatbotUpdate(
            name="Channel Bot",
            description="",
            language="French",
            type="builder",
            purpose="custom",
            mode="builder",
            channel="api",
        )
        self.assertEqual(updated.language, "fr")
        self.assertEqual(updated.channel, "rest_public_api")

    def test_invalid_language_and_channel_are_rejected_by_schema(self):
        with self.assertRaises(ValidationError):
            ChatbotCreate(
                name="Invalid Language",
                description="",
                language="ar",
                assistant_type="custom",
                creation_mode="scratch",
                project_id=self.project_a.id,
                channel="web_widget",
            )

        with self.assertRaises(ValidationError):
            ChatbotSetupUpdate(channel="sms")

    def test_create_chatbot_persists_french_and_localizes_starter_flow(self):
        result = create_chatbot(
            ChatbotCreate(
                name="French Bot",
                description="",
                language="fr",
                assistant_type="custom",
                creation_mode="scratch",
                project_id=self.project_a.id,
                channel="web_widget",
            ),
            db=self.db,
            current_user=self.manager_a,
        )

        self.assertEqual(result["language"], "fr")
        bot = self.db.query(Chatbot).filter(Chatbot.id == result["id"]).first()
        self.assertEqual(bot.language, "fr")
        version = self.db.query(VersionChatbot).filter(VersionChatbot.chatbot_id == bot.id).first()
        config = self.db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()
        self.assertIn("French", config.system_prompt)
        flow = self.db.query(Flow).filter(Flow.version_id == version.id).first()
        start = self.db.query(FlowNode).filter(FlowNode.flow_id == flow.id, FlowNode.node_key == "start").first()
        self.assertIn("Bonjour", start.config["text"])

    def test_create_chatbot_persists_english_and_keeps_english_starter_flow(self):
        result = create_chatbot(
            ChatbotCreate(
                name="English Bot",
                description="",
                language="en",
                assistant_type="custom",
                creation_mode="scratch",
                project_id=self.project_a.id,
                channel="web_widget",
            ),
            db=self.db,
            current_user=self.manager_a,
        )

        self.assertEqual(result["language"], "en")
        bot = self.db.query(Chatbot).filter(Chatbot.id == result["id"]).first()
        version = self.db.query(VersionChatbot).filter(VersionChatbot.chatbot_id == bot.id).first()
        config = self.db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()
        self.assertIn("English", config.system_prompt)
        flow = self.db.query(Flow).filter(Flow.version_id == version.id).first()
        start = self.db.query(FlowNode).filter(FlowNode.flow_id == flow.id, FlowNode.node_key == "start").first()
        self.assertIn("Welcome", start.config["text"])

    def test_template_apply_respects_assistant_language(self):
        legacy = Chatbot(
            name="French Template",
            language="fr",
            purpose="customer_support",
            build_method="template",
            project_id=self.project_a.id,
            is_active=True,
        )
        self.db.add(legacy)
        self.db.commit()
        version = VersionChatbot(chatbot_id=legacy.id, version_number=1, status="draft")
        self.db.add(version)
        self.db.commit()
        flow = Flow(version_id=version.id, name="Blank")
        self.db.add(flow)
        self.db.commit()

        apply_flow_template(
            flow.id,
            FlowTemplateApply(template_key="customer_support_basic"),
            db=self.db,
            current_user=self.manager_a,
        )

        start = self.db.query(FlowNode).filter(FlowNode.flow_id == flow.id, FlowNode.node_key == "start").first()
        answer = self.db.query(FlowNode).filter(FlowNode.flow_id == flow.id, FlowNode.node_key == "answer").first()
        self.assertIn("Bonjour", start.config["text"])
        self.assertIn("Repondez toujours en francais", answer.config["prompt"])

    def test_ai_generation_respects_selected_french_language(self):
        generated = _normalize_ai_generation(
            {},
            AiGenerateRequest(
                assistant_goal="Help customers",
                business_context="support",
                knowledge_base_description="",
                assistant_type="customer_support",
                language="fr",
            ),
        )

        self.assertIn("Bonjour", generated.welcome_message)
        start = generated.initial_flow_structure["nodes"][0]
        answer = next(node for node in generated.initial_flow_structure["nodes"] if node["key"] == "answer")
        self.assertIn("Bonjour", start["config"]["text"])
        self.assertIn("Always answer in French", answer["config"]["prompt"])
        self.assertIn("Je n'ai pas encore assez", answer["config"]["fallback"])

    def test_ai_generation_does_not_create_api_block_without_url(self):
        generated = _normalize_ai_generation(
            {},
            AiGenerateRequest(
                assistant_goal="Answer questions and trigger external actions",
                business_context="Create CRM tickets through an external system",
                knowledge_base_description="",
                assistant_type="custom",
                language="en",
            ),
        )

        node_types = [node["type"] for node in generated.initial_flow_structure["nodes"]]
        self.assertNotIn("api_request", node_types)
        self.assertNotIn("API Call", generated.suggested_advanced_blocks)

    def test_ai_generation_does_not_create_api_block_when_url_is_provided(self):
        generated = _normalize_ai_generation(
            {},
            AiGenerateRequest(
                assistant_goal="Answer questions and trigger an API action",
                business_context="Send a CRM request to https://example.com/webhook",
                knowledge_base_description="",
                assistant_type="custom",
                language="en",
            ),
        )

        node_types = [node["type"] for node in generated.initial_flow_structure["nodes"]]
        self.assertNotIn("api_request", node_types)
        self.assertNotIn("API Call", generated.suggested_advanced_blocks)

    def test_runtime_rag_prompt_enforces_french_language(self):
        config = LLMConfig(
            version_id=self.version.id,
            model="phi3",
            temperature=0.7,
            system_prompt="You are a helpful assistant",
        )
        self.db.add(config)
        self.db.commit()

        generation = prepare_rag_generation(
            db=self.db,
            version=self.version,
            config=config,
            message="Bonjour",
            variables={"__language": "fr"},
            history=[],
            node_config={
                "use_knowledge_base": True,
                "strict_context": True,
                "fallback": "I do not have enough information to answer that yet.",
            },
        )

        self.assertIn("Always respond in French", generation["prompt"])
        self.assertIn("Je n'ai pas encore assez", generation["fallback_response"])

    def test_ai_only_answer_node_does_not_short_circuit_to_fallback(self):
        config = LLMConfig(
            version_id=self.version.id,
            model="phi3",
            temperature=0.7,
            system_prompt="You are a helpful assistant",
        )
        self.db.add(config)
        self.chatbot.rag_settings = {"strict_context": True}
        self.db.commit()

        generation = prepare_rag_generation(
            db=self.db,
            version=self.version,
            config=config,
            message="Bonjour",
            variables={"__language": "fr"},
            history=[],
            node_config={
                "use_knowledge_base": False,
                "show_sources": False,
                "fallback": "I could not generate a helpful answer for that question.",
            },
        )

        self.assertEqual(generation["retrieval_mode"], "ai_only")
        self.assertEqual(generation["fallback_response"], "")
        self.assertEqual(generation["sources"], [])

    def test_noop_update_does_not_create_audit_log(self):
        update_chatbot_setup(
            self.chatbot.id,
            ChatbotSetupUpdate(name="Support Bot", description="Old description", language="fr"),
            db=self.db,
            current_user=self.manager_a,
        )
        self.assertEqual(self.audit_logs(), [])

    def test_invalid_values_do_not_create_audit_log(self):
        with self.assertRaises(HTTPException):
            update_chatbot_setup(
                self.chatbot.id,
                ChatbotSetupUpdate(name=""),
                db=self.db,
                current_user=self.manager_a,
            )
        self.assertEqual(self.audit_logs(), [])

    def test_template_update_requires_persisted_available_template_provenance(self):
        self.chatbot.template_key = None
        self.chatbot.source_template_key = None
        self.db.commit()

        setup = get_chatbot_setup(self.chatbot.id, db=self.db, current_user=self.manager_a)
        self.assertFalse(setup["template_update_available"])
        self.assertIsNone(setup["source_template_key"])

        with self.assertRaises(HTTPException) as error:
            reapply_template_to_new_draft(self.chatbot.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(self.audit_logs(), [])

    def test_missing_catalog_template_disables_template_update(self):
        self.chatbot.source_template_key = "removed_template"
        self.chatbot.template_key = "removed_template"
        self.db.commit()

        setup = get_chatbot_setup(self.chatbot.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(setup["source_template_key"], "removed_template")
        self.assertIsNone(setup["template_name"])
        self.assertFalse(setup["template_update_available"])

        with self.assertRaises(HTTPException) as error:
            reapply_template_to_new_draft(self.chatbot.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(error.exception.status_code, 400)

    def test_manager_cannot_manually_change_template_provenance(self):
        update_chatbot(
            self.chatbot.id,
            ChatbotUpdate(
                name="Renamed",
                description="Still safe",
                language="fr",
                type="builder",
                purpose="customer_support",
                mode="builder",
                channel="web_widget",
                build_method="template",
                creation_mode="template",
                template_key="sales_starter",
                source_template_key="sales_starter",
            ),
            db=self.db,
            current_user=self.manager_a,
        )

        self.db.refresh(self.chatbot)
        self.assertEqual(self.chatbot.source_template_key, "customer_support_basic")
        self.assertEqual(self.chatbot.template_key, "customer_support_basic")

        with self.assertRaises(HTTPException) as error:
            update_chatbot(
                self.chatbot.id,
                ChatbotUpdate(
                    name="Bad Mode",
                    description="",
                    language="fr",
                    type="builder",
                    purpose="customer_support",
                    mode="builder",
                    channel="web_widget",
                    build_method="ai",
                    creation_mode="ai",
                ),
                db=self.db,
                current_user=self.manager_a,
            )
        self.assertEqual(error.exception.status_code, 400)

    def test_template_update_creates_new_draft_without_touching_published_or_data(self):
        self.version.status = "published"
        self.chatbot.active_version_id = self.version.id
        session = ConversationSession(chatbot_id=self.chatbot.id, version_id=self.version.id)
        self.db.add(session)
        self.db.commit()
        self.db.add(ConversationMessage(session_id=session.id, role="user", content="Hello"))
        self.db.add(RuntimeLog(
            chatbot_id=self.chatbot.id,
            version_id=self.version.id,
            conversation_id=session.id,
            project_id=self.project_a.id,
            channel="public_chat",
            status="success",
            rag_used=False,
            response_time_ms=120,
        ))
        self.db.commit()

        version_count = self.db.query(VersionChatbot).count()
        original_flow_node_count = self.db.query(FlowNode).filter(FlowNode.flow_id == self.flow.id).count()
        document_count = self.db.query(Document).count()
        conversation_count = self.db.query(ConversationSession).count()
        runtime_count = self.db.query(RuntimeLog).count()

        result = reapply_template_to_new_draft(self.chatbot.id, db=self.db, current_user=self.manager_a)

        self.db.refresh(self.chatbot)
        self.db.refresh(self.version)
        self.assertEqual(self.chatbot.active_version_id, self.version.id)
        self.assertEqual(self.version.status, "published")
        self.assertEqual(self.db.query(VersionChatbot).count(), version_count + 1)
        self.assertEqual(self.db.query(FlowNode).filter(FlowNode.flow_id == self.flow.id).count(), original_flow_node_count)
        self.assertEqual(self.db.query(Document).count(), document_count)
        self.assertEqual(self.db.query(ConversationSession).count(), conversation_count)
        self.assertEqual(self.db.query(RuntimeLog).count(), runtime_count)
        self.assertEqual(result["draft_version"]["status"], "draft")
        self.assertGreater(result["flow_id"], 0)

        log = self.audit_logs()[-1]
        self.assertEqual(log.action, "ASSISTANT_TEMPLATE_REAPPLIED")
        self.assertEqual(log.metadata_json["draft_version_id"], result["draft_version"]["id"])
        self.assertEqual(log.metadata_json["template_key"], "customer_support_basic")

    def test_initial_template_apply_persists_source_template_key(self):
        legacy = Chatbot(
            name="Legacy Apply",
            language="en",
            purpose="customer_support",
            build_method="template",
            project_id=self.project_a.id,
            is_active=True,
        )
        self.db.add(legacy)
        self.db.commit()
        version = VersionChatbot(chatbot_id=legacy.id, version_number=1, status="draft")
        self.db.add(version)
        self.db.commit()
        flow = Flow(version_id=version.id, name="Blank")
        self.db.add(flow)
        self.db.commit()

        apply_flow_template(
            flow.id,
            FlowTemplateApply(template_key="customer_support_rag"),
            db=self.db,
            current_user=self.manager_a,
        )

        self.db.refresh(legacy)
        self.assertEqual(legacy.source_template_key, "customer_support_rag")
        setup = get_chatbot_setup(legacy.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(setup["template_name"], "Customer Support + RAG")
        self.assertTrue(setup["template_update_available"])

    def test_change_template_updates_existing_template_provenance(self):
        self.chatbot.template_key = "customer_support_basic"
        self.chatbot.source_template_key = "customer_support_basic"
        self.db.commit()

        result = apply_flow_template(
            self.flow.id,
            FlowTemplateApply(template_key="simple_lead_capture", purpose="lead_generation"),
            db=self.db,
            current_user=self.manager_a,
        )

        self.db.refresh(self.chatbot)
        self.db.refresh(self.version)
        self.assertEqual(self.chatbot.template_key, "simple_lead_capture")
        self.assertEqual(self.chatbot.source_template_key, "simple_lead_capture")
        self.assertEqual(self.chatbot.purpose, "lead_generation")
        self.assertEqual(self.version.status, "draft")

        setup = get_chatbot_setup(self.chatbot.id, db=self.db, current_user=self.manager_a)
        self.assertEqual(setup["template_name"], "Simple Lead Capture")
        self.assertEqual(setup["source_template_key"], "simple_lead_capture")
        self.assertEqual(result.name, "Simple Lead Capture")

    def test_invalid_template_catalog_flow_is_not_persisted_on_reapply(self):
        TEMPLATES["broken_test_template"] = {
            "name": "Broken Test Template",
            "nodes": [
                ("intro", "message", "Intro", {"text": "Hi"}, 80, 120),
            ],
            "transitions": [],
        }
        self.chatbot.source_template_key = "broken_test_template"
        self.chatbot.template_key = "broken_test_template"
        self.db.commit()
        version_count = self.db.query(VersionChatbot).count()
        flow_count = self.db.query(Flow).count()

        try:
            with self.assertRaises(HTTPException) as error:
                reapply_template_to_new_draft(self.chatbot.id, db=self.db, current_user=self.manager_a)
            self.assertEqual(error.exception.status_code, 400)
            self.assertEqual(self.db.query(VersionChatbot).count(), version_count)
            self.assertEqual(self.db.query(Flow).count(), flow_count)
            self.assertEqual(self.audit_logs(), [])
        finally:
            TEMPLATES.pop("broken_test_template", None)

    def test_template_update_is_ownership_scoped(self):
        with self.assertRaises(HTTPException) as error:
            reapply_template_to_new_draft(self.chatbot.id, db=self.db, current_user=self.manager_b)
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(self.audit_logs(), [])

    def test_ai_regeneration_creates_new_draft_and_preserves_existing_state(self):
        self.chatbot.build_method = "ai"
        self.chatbot.template_key = None
        self.version.status = "published"
        self.chatbot.active_version_id = self.version.id
        session = ConversationSession(chatbot_id=self.chatbot.id, version_id=self.version.id)
        self.db.add(session)
        self.db.commit()
        self.db.add(RuntimeLog(
            chatbot_id=self.chatbot.id,
            version_id=self.version.id,
            conversation_id=session.id,
            project_id=self.project_a.id,
            channel="api",
            status="success",
            rag_used=True,
            response_time_ms=180,
        ))
        self.db.commit()

        version_count = self.db.query(VersionChatbot).count()
        document_count = self.db.query(Document).count()
        conversation_count = self.db.query(ConversationSession).count()
        runtime_count = self.db.query(RuntimeLog).count()
        original_flow_nodes = self.db.query(FlowNode).filter(FlowNode.flow_id == self.flow.id).count()
        payload = ChatbotAiDraftRegenerate(
            assistant_goal="Support students",
            business_context="University admissions",
            knowledge_base_description="Policies",
            generated_name="AI Support Bot",
            generated_description="Generated draft description",
            nodes=[
                {"key": "start", "type": "message", "label": "Start", "config": {"text": "Hi"}, "position_x": 80, "position_y": 80},
                {
                    "key": "answer",
                    "type": "rag_answer",
                    "label": "Answer",
                    "config": {
                        "prompt": "Answer clearly",
                        "fallback": "I do not have enough information.",
                        "continue_rag": True,
                    },
                    "position_x": 360,
                    "position_y": 80,
                },
            ],
            transitions=[
                {"source_node_key": "start", "target_node_key": "answer", "label": "next"},
            ],
        )

        result = regenerate_ai_draft(self.chatbot.id, payload, db=self.db, current_user=self.manager_a)

        self.db.refresh(self.chatbot)
        self.db.refresh(self.version)
        self.assertEqual(self.chatbot.active_version_id, self.version.id)
        self.assertEqual(self.version.status, "published")
        self.assertEqual(self.chatbot.name, "AI Support Bot")
        self.assertEqual(self.db.query(VersionChatbot).count(), version_count + 1)
        self.assertEqual(self.db.query(FlowNode).filter(FlowNode.flow_id == self.flow.id).count(), original_flow_nodes)
        self.assertEqual(self.db.query(Document).count(), document_count)
        self.assertEqual(self.db.query(ConversationSession).count(), conversation_count)
        self.assertEqual(self.db.query(RuntimeLog).count(), runtime_count)
        self.assertEqual(result["draft_version"]["status"], "draft")

        new_flow_nodes = self.db.query(FlowNode).filter(FlowNode.flow_id == result["flow_id"]).all()
        self.assertEqual({node.node_key for node in new_flow_nodes}, {"start", "answer"})
        log = self.audit_logs()[-1]
        self.assertEqual(log.action, "ASSISTANT_AI_DRAFT_REGENERATED")
        self.assertEqual(log.metadata_json["draft_version_id"], result["draft_version"]["id"])
        self.assertNotIn("Support students", str(log.metadata_json))

    def test_ai_regeneration_rejects_wrong_mode_and_other_manager(self):
        payload = ChatbotAiDraftRegenerate(
            assistant_goal="Goal",
            business_context="Context",
            nodes=[
                {"key": "start", "type": "message", "label": "Start", "config": {}, "position_x": 0, "position_y": 0},
            ],
            transitions=[],
        )

        with self.assertRaises(HTTPException) as wrong_mode_error:
            regenerate_ai_draft(self.chatbot.id, payload, db=self.db, current_user=self.manager_a)
        self.assertEqual(wrong_mode_error.exception.status_code, 400)

        self.chatbot.build_method = "ai"
        self.db.commit()
        with self.assertRaises(HTTPException) as ownership_error:
            regenerate_ai_draft(self.chatbot.id, payload, db=self.db, current_user=self.manager_b)
        self.assertEqual(ownership_error.exception.status_code, 404)
        self.assertEqual(self.audit_logs(), [])

    def test_generated_flow_normalization_requires_one_canonical_start_and_valid_edges(self):
        nodes, transitions = normalize_generated_flow(
            [
                {"key": "start", "type": "message", "label": "Start", "config": {"text": "Hi"}, "position_x": 80, "position_y": 80},
                {
                    "key": "answer",
                    "type": "rag_answer",
                    "label": "Answer",
                    "config": {"prompt": "Answer", "fallback": "Fallback", "continue_rag": True},
                    "position_x": 360,
                    "position_y": 80,
                },
            ],
            [{"source_node_key": "start", "target_node_key": "answer", "label": "next"}],
        )

        self.assertEqual([node.key for node in nodes].count("start"), 1)
        node_keys = {node.key for node in nodes}
        self.assertTrue(all(edge.source_node_key in node_keys and edge.target_node_key in node_keys for edge in transitions))

        with self.assertRaises(ValueError):
            normalize_generated_flow(
                [{"key": "intro", "type": "message", "label": "Intro", "config": {}, "position_x": 0, "position_y": 0}],
                [],
            )
        with self.assertRaises(ValueError):
            normalize_generated_flow(
                [
                    {"key": "start", "type": "message", "label": "Start", "config": {}, "position_x": 0, "position_y": 0},
                    {"key": "start", "type": "message", "label": "Duplicate", "config": {}, "position_x": 1, "position_y": 1},
                ],
                [],
            )
        with self.assertRaises(ValueError):
            normalize_generated_flow(
                [{"key": "start", "type": "unknown", "label": "Start", "config": {}, "position_x": 0, "position_y": 0}],
                [],
            )

    def test_invalid_ai_output_does_not_create_draft_or_change_existing_flow(self):
        self.chatbot.build_method = "ai"
        self.version.status = "published"
        self.chatbot.active_version_id = self.version.id
        self.db.commit()

        version_count = self.db.query(VersionChatbot).count()
        flow_count = self.db.query(Flow).count()
        node_count = self.db.query(FlowNode).filter(FlowNode.flow_id == self.flow.id).count()
        payload = ChatbotAiDraftRegenerate(
            assistant_goal="Goal",
            business_context="Context",
            nodes=[
                {"key": "intro", "type": "message", "label": "Intro", "config": {}, "position_x": 0, "position_y": 0},
            ],
            transitions=[],
        )

        with self.assertRaises(HTTPException) as error:
            regenerate_ai_draft(self.chatbot.id, payload, db=self.db, current_user=self.manager_a)

        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("canonical start node", error.exception.detail)
        self.assertEqual(self.db.query(VersionChatbot).count(), version_count)
        self.assertEqual(self.db.query(Flow).count(), flow_count)
        self.assertEqual(self.db.query(FlowNode).filter(FlowNode.flow_id == self.flow.id).count(), node_count)
        self.assertEqual(self.audit_logs(), [])

    def test_initial_ai_apply_and_setup_regeneration_use_same_canonical_rules(self):
        generated_nodes = [
            {"key": "start", "type": "message", "label": "Start", "config": {"text": "Hi"}, "position_x": 80, "position_y": 80},
            {
                "key": "answer",
                "type": "rag_answer",
                "label": "Answer",
                "config": {"prompt": "Answer", "fallback": "Fallback", "continue_rag": True},
                "position_x": 360,
                "position_y": 80,
            },
        ]
        generated_edges = [{"source_node_key": "start", "target_node_key": "answer", "label": "next"}]

        apply_generated_flow(
            self.flow.id,
            GeneratedFlowApply(name="Initial AI Flow", nodes=generated_nodes, transitions=generated_edges),
            db=self.db,
            current_user=self.manager_a,
        )
        self.chatbot.build_method = "ai"
        self.db.commit()
        result = regenerate_ai_draft(
            self.chatbot.id,
            ChatbotAiDraftRegenerate(
                assistant_goal="Goal",
                business_context="Context",
                nodes=generated_nodes,
                transitions=generated_edges,
            ),
            db=self.db,
            current_user=self.manager_a,
        )

        self.assertEqual(result["draft_version"]["status"], "draft")
        draft_nodes = self.db.query(FlowNode).filter(FlowNode.flow_id == result["flow_id"]).all()
        self.assertEqual([node.node_key for node in draft_nodes].count("start"), 1)

    def test_template_catalog_filters_creation_exposure_by_purpose(self):
        lead_templates = template_options(purpose="lead_generation", exposed_only=True)
        lead_keys = {template["key"] for template in lead_templates}

        self.assertIn("simple_lead_capture", lead_keys)
        self.assertIn("sales_starter", lead_keys)
        self.assertNotIn("lead_capture", lead_keys)
        self.assertTrue(all(template["exposed"] for template in lead_templates))
        self.assertEqual(template_metadata("lead_capture")["primary_purpose"], "internal")

    def test_manager_can_create_private_template_and_share_it(self):
        self.db.add(FlowNode(flow_id=self.flow.id, node_key="end", type="end", label="End", config={"message": "Done"}))
        self.db.commit()
        created = create_flow_template_from_flow(
            self.flow.id,
            FlowTemplateCreate(
                name="Reusable Support Intake",
                description="Tested support flow.",
                purpose="customer_support",
                is_exposed=False,
                is_shared=False,
            ),
            db=self.db,
            current_user=self.manager_a,
        )

        self.assertEqual(created["source"], "custom")
        self.assertTrue(created["can_edit"])
        self.assertFalse(created["exposed"])
        private_keys_for_owner = {item["key"] for item in list_flow_templates(db=self.db, current_user=self.manager_a)}
        private_keys_for_other = {item["key"] for item in list_flow_templates(db=self.db, current_user=self.manager_b)}
        self.assertIn(created["key"], private_keys_for_owner)
        self.assertNotIn(created["key"], private_keys_for_other)

        updated = update_flow_template(
            created["key"],
            FlowTemplateUpdate(is_shared=True, is_exposed=True),
            db=self.db,
            current_user=self.manager_a,
        )
        self.assertTrue(updated["shared"])
        self.assertTrue(updated["exposed"])
        shared_keys_for_other = {
            item["key"]
            for item in list_flow_templates(
                purpose="customer_support",
                exposed_only=True,
                db=self.db,
                current_user=self.manager_b,
            )
        }
        self.assertIn(created["key"], shared_keys_for_other)

    def test_manager_cannot_edit_another_manager_template(self):
        self.db.add(FlowNode(flow_id=self.flow.id, node_key="end", type="end", label="End", config={"message": "Done"}))
        self.db.commit()
        created = create_flow_template_from_flow(
            self.flow.id,
            FlowTemplateCreate(name="Private Template", purpose="custom"),
            db=self.db,
            current_user=self.manager_a,
        )

        with self.assertRaises(HTTPException) as not_found:
            get_flow_template_detail(created["key"], db=self.db, current_user=self.manager_b)
        self.assertEqual(not_found.exception.status_code, 404)

        update_flow_template(
            created["key"],
            FlowTemplateUpdate(is_shared=True),
            db=self.db,
            current_user=self.manager_a,
        )
        with self.assertRaises(HTTPException) as forbidden:
            update_flow_template(
                created["key"],
                FlowTemplateUpdate(name="Changed"),
                db=self.db,
                current_user=self.manager_b,
            )
        self.assertEqual(forbidden.exception.status_code, 403)

    def test_template_runner_auto_drives_custom_template(self):
        self.db.add(FlowNode(flow_id=self.flow.id, node_key="end", type="end", label="End", config={"message": "Done"}))
        self.db.commit()
        created = create_flow_template_from_flow(
            self.flow.id,
            FlowTemplateCreate(name="Runnable Template", purpose="custom"),
            db=self.db,
            current_user=self.manager_a,
        )

        result = run_flow_template_test(created["key"], None, db=self.db, current_user=self.manager_a)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["scenario_count"], 1)
        self.assertTrue(result["results"][0]["transcript"])

    def test_template_runner_reports_expectation_failures(self):
        result = run_flow_template_test(
            "customer_support_basic",
            FlowTemplateTestRun(
                name="Expectation failure",
                messages=["hello"],
                expected_variables={"missing": "value"},
            ),
            db=self.db,
            current_user=self.manager_a,
        )

        self.assertEqual(result["status"], "failed")
        self.assertIn("Expected variable", result["results"][0]["errors"][0])

    def test_custom_template_revisions_are_immutable_and_apply_records_revision(self):
        self.db.add(FlowNode(flow_id=self.flow.id, node_key="end", type="end", label="End", config={"message": "Done"}))
        self.db.commit()
        created = create_flow_template_from_flow(
            self.flow.id,
            FlowTemplateCreate(name="Versioned Template", purpose="customer_support"),
            db=self.db,
            current_user=self.manager_a,
        )
        self.assertEqual(created["current_revision_number"], 1)

        start = self.db.query(FlowNode).filter(FlowNode.flow_id == self.flow.id, FlowNode.node_key == "start").first()
        start.config = {"text": "Changed welcome"}
        self.db.commit()
        revision_payload = create_flow_template_revision_from_flow(
            self.flow.id,
            created["key"],
            FlowTemplateRevisionCreate(change_note="Changed welcome copy"),
            db=self.db,
            current_user=self.manager_a,
        )

        self.assertEqual(revision_payload["revision"]["revision_number"], 2)
        revision_one = get_flow_template_detail(created["key"], revision=1, db=self.db, current_user=self.manager_a)
        revision_two = get_flow_template_detail(created["key"], revision=2, db=self.db, current_user=self.manager_a)
        self.assertEqual(revision_one["nodes"][0]["config"]["text"], "Hello")
        self.assertEqual(revision_two["nodes"][0]["config"]["text"], "Changed welcome")

        self.chatbot.build_method = "template"
        self.db.commit()
        apply_flow_template(
            self.flow.id,
            FlowTemplateApply(template_key=created["key"], template_revision=2),
            db=self.db,
            current_user=self.manager_a,
        )
        self.assertEqual(self.chatbot.source_template_key, created["key"])
        self.assertEqual(self.chatbot.source_template_version, "2")


if __name__ == "__main__":
    unittest.main()
