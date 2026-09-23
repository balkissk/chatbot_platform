import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.llm_config import LLMConfig, effective_system_prompt, split_structured_prompt_metadata
from models.llm_config_schema import LLMConfigCreate
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from routes.llm_config_routes import create_or_update_config, get_config
from routes.version_routes import duplicate_version


class LLMConfigPersistenceTest(unittest.TestCase):
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

        self.version = VersionChatbot(chatbot_id=self.chatbot.id, version_number=1, status="draft", created_by=self.manager.id)
        self.db.add(self.version)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_structured_settings_persist_separately_from_system_prompt(self):
        payload = LLMConfigCreate(
            version_id=self.version.id,
            model="llama3",
            temperature=0.7,
            system_prompt="Always answer in French and keep responses concise and professional.",
            tone="Friendly",
            language="French",
            response_style="Concise",
        )

        saved = create_or_update_config(payload, db=self.db, current_user=self.manager)
        loaded = get_config(self.version.id, db=self.db, current_user=self.manager)

        self.assertEqual(saved.system_prompt, payload.system_prompt)
        self.assertEqual(loaded.system_prompt, payload.system_prompt)
        self.assertEqual(loaded.tone, "Friendly")
        self.assertEqual(loaded.language, "French")
        self.assertEqual(loaded.response_style, "Concise")
        self.assertEqual(
            effective_system_prompt(loaded),
            "\n".join([
                payload.system_prompt,
                "Tone: Friendly",
                "Language: French",
                "Response style: Concise",
            ]),
        )

    def test_trailing_bug_metadata_is_parsed_without_losing_free_text(self):
        body, metadata = split_structured_prompt_metadata(
            "\n".join([
                "Always answer in French.",
                "Tone: Friendly",
                "Language: French",
                "Response style: Concise",
            ])
        )

        self.assertEqual(body, "Always answer in French.")
        self.assertEqual(metadata["tone"], "Friendly")
        self.assertEqual(metadata["language"], "French")
        self.assertEqual(metadata["response style"], "Concise")

    def test_single_user_authored_metadata_like_line_is_preserved(self):
        body, metadata = split_structured_prompt_metadata("Use this literal line:\nTone: Friendly")

        self.assertEqual(body, "Use this literal line:\nTone: Friendly")
        self.assertEqual(metadata, {})

    def test_duplicate_version_preserves_structured_settings(self):
        self.db.add(LLMConfig(
            version_id=self.version.id,
            model="llama3",
            temperature=0.5,
            system_prompt="Original instructions",
            tone="Supportive",
            language="English",
            response_style="Detailed",
        ))
        self.db.commit()

        duplicate = duplicate_version(self.version.id, db=self.db, current_user=self.manager)
        copied = self.db.query(LLMConfig).filter(LLMConfig.version_id == duplicate["id"]).one()

        self.assertEqual(copied.system_prompt, "Original instructions")
        self.assertEqual(copied.tone, "Supportive")
        self.assertEqual(copied.language, "English")
        self.assertEqual(copied.response_style, "Detailed")


if __name__ == "__main__":
    unittest.main()
