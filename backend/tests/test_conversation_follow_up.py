import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.conversation import ConversationMessage, ConversationSession
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from routes.chatbot_routes import (
    get_chatbot_conversation_details,
    get_chatbot_conversations,
    update_conversation_follow_up,
)


class ConversationFollowUpPersistenceTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.manager = User(
            name="Manager",
            email="manager@example.com",
            password_hash="x",
            role="manager",
            status="active",
        )
        self.db.add(self.manager)
        self.db.commit()

        self.project = Project(
            name="Project",
            description="Project",
            user_id=self.manager.id,
        )
        self.db.add(self.project)
        self.db.commit()

        self.chatbot = Chatbot(
            name="Assistant",
            project_id=self.project.id,
            language="en",
            is_active=True,
        )
        self.db.add(self.chatbot)
        self.db.commit()

        self.version = VersionChatbot(
            chatbot_id=self.chatbot.id,
            version_number=1,
            status="published",
        )
        self.db.add(self.version)
        self.db.commit()

        self.session_one = self.create_session("First question", datetime(2026, 1, 2, 10, 0))
        self.session_two = self.create_session("Second question", datetime(2026, 1, 2, 11, 0))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create_session(self, message: str, timestamp: datetime) -> ConversationSession:
        session = ConversationSession(
            chatbot_id=self.chatbot.id,
            version_id=self.version.id,
            variables={"lead_email": f"{message.split()[0].lower()}@example.com"},
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.db.add(session)
        self.db.commit()
        self.db.add_all([
            ConversationMessage(
                session_id=session.id,
                role="user",
                content=message,
                created_at=timestamp,
            ),
            ConversationMessage(
                session_id=session.id,
                role="bot",
                content="Answer",
                created_at=timestamp + timedelta(seconds=1),
            ),
        ])
        self.db.commit()
        return session

    def test_follow_up_metadata_persists_per_conversation_session(self):
        saved = update_conversation_follow_up(
            self.chatbot.id,
            self.session_one.id,
            {"status": "scheduled", "note": "Call tomorrow"},
            db=self.db,
            current_user=self.manager,
        )

        self.assertEqual(saved["follow_up_status"], "scheduled")
        self.assertEqual(saved["manager_note"], "Call tomorrow")

        self.db.expire_all()
        stored_one = self.db.query(ConversationSession).filter(
            ConversationSession.id == self.session_one.id
        ).first()
        stored_two = self.db.query(ConversationSession).filter(
            ConversationSession.id == self.session_two.id
        ).first()

        self.assertEqual(stored_one.variables["__manager_status"], "scheduled")
        self.assertEqual(stored_one.variables["__manager_note"], "Call tomorrow")
        self.assertNotIn("__manager_status", stored_two.variables)
        self.assertNotIn("__manager_note", stored_two.variables)

        details = get_chatbot_conversation_details(
            self.chatbot.id,
            self.session_one.id,
            200,
            db=self.db,
            current_user=self.manager,
        )
        self.assertEqual(details["follow_up_status"], "scheduled")
        self.assertEqual(details["manager_note"], "Call tomorrow")

        summaries = get_chatbot_conversations(
            self.chatbot.id,
            limit=10,
            offset=0,
            db=self.db,
            current_user=self.manager,
        )
        by_id = {item["id"]: item for item in summaries}
        self.assertEqual(by_id[self.session_one.id]["follow_up_status"], "scheduled")
        self.assertEqual(by_id[self.session_one.id]["manager_note"], "Call tomorrow")
        self.assertEqual(by_id[self.session_two.id]["follow_up_status"], "new")
        self.assertEqual(by_id[self.session_two.id]["manager_note"], "")


if __name__ == "__main__":
    unittest.main()
