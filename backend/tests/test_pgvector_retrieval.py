import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.chatbot import Chatbot
from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from services import rag
from services.embedding_config import pgvector_literal, validate_embedding_vector


class PgVectorRetrievalTest(unittest.TestCase):
    def setUp(self):
        self.previous_dimensions = os.environ.get("EMBEDDING_DIMENSIONS")
        os.environ["EMBEDDING_DIMENSIONS"] = "3"

        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.user = User(name="Manager", email="m@example.com", password_hash="x", role="manager", status="active")
        self.db.add(self.user)
        self.db.commit()
        self.project = Project(name="Project", description="Demo", user_id=self.user.id)
        self.db.add(self.project)
        self.db.commit()
        self.chatbot = Chatbot(name="Assistant", project_id=self.project.id, language="en", is_active=True)
        self.db.add(self.chatbot)
        self.db.commit()
        self.version = VersionChatbot(chatbot_id=self.chatbot.id, version_number=1, status="draft")
        self.db.add(self.version)
        self.db.commit()
        self.kb = KnowledgeBase(name="KB", version_id=self.version.id)
        self.db.add(self.kb)
        self.db.commit()
        self.document = Document(
            knowledge_base_id=self.kb.id,
            filename="doc.txt",
            content_type="text/plain",
            storage_url="local://doc.txt",
            status="ready",
        )
        self.db.add(self.document)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        if self.previous_dimensions is None:
            os.environ.pop("EMBEDDING_DIMENSIONS", None)
        else:
            os.environ["EMBEDDING_DIMENSIONS"] = self.previous_dimensions

    def add_chunk(self, text: str, embedding: list[float], status: str = "ready", document: Document | None = None):
        chunk = Chunk(
            document_id=(document or self.document).id,
            order=0,
            text=text,
            embedding=embedding,
            embedding_status=status,
            embedding_vector=pgvector_literal(embedding) if status == "ready" else None,
            embedding_dimensions=len(embedding),
        )
        self.db.add(chunk)
        self.db.commit()
        return chunk

    def test_pgvector_literal_validates_expected_dimension(self):
        self.assertEqual(pgvector_literal([1, 0.5, 0]), "[1,0.5,0]")

        with self.assertRaises(ValueError):
            validate_embedding_vector([1, 0])

    def test_mark_chunk_ready_persists_json_and_vector_value(self):
        chunk = Chunk(document_id=self.document.id, order=0, text="alpha", embedding_status="pending")

        rag._mark_chunk_ready(chunk, [0.1, 0.2, 0.3], "text-embedding-3-small")

        self.assertEqual(chunk.embedding, [0.1, 0.2, 0.3])
        self.assertEqual(chunk.embedding_vector, "[0.1,0.2,0.3]")
        self.assertEqual(chunk.embedding_dimensions, 3)
        self.assertEqual(chunk.embedding_status, "ready")

    def test_sqlite_compatibility_fallback_enforces_top_k_threshold_and_kb_scope(self):
        best = self.add_chunk("alpha answer", [1.0, 0.0, 0.0])
        self.add_chunk("alpha weaker answer", [0.7, 0.7, 0.0])
        self.add_chunk("alpha failed answer", [1.0, 0.0, 0.0], status="failed")

        other_version = VersionChatbot(chatbot_id=self.chatbot.id, version_number=2, status="draft")
        self.db.add(other_version)
        self.db.commit()
        other_kb = KnowledgeBase(name="Other KB", version_id=other_version.id)
        self.db.add(other_kb)
        self.db.commit()
        other_document = Document(
            knowledge_base_id=other_kb.id,
            filename="other.txt",
            content_type="text/plain",
            storage_url="local://other.txt",
            status="ready",
        )
        self.db.add(other_document)
        self.db.commit()
        self.add_chunk("alpha cross kb", [1.0, 0.0, 0.0], document=other_document)

        with patch.object(rag, "generate_embedding", return_value=[1.0, 0.0, 0.0]) as embedding:
            result = rag.retrieve_relevant_chunks_with_mode(
                self.db,
                self.version.id,
                "alpha",
                limit=1,
                retrieval_mode="semantic",
                min_score=0.8,
            )

        self.assertEqual(result["mode"], "semantic")
        self.assertEqual(len(result["chunks"]), 1)
        self.assertEqual(result["chunks"][0][0].id, best.id)
        self.assertEqual(embedding.call_count, 1)

    def test_similarity_threshold_semantics_remain_zero_to_one(self):
        self.add_chunk("unrelated", [1.0, 0.0, 0.0])

        with patch.object(rag, "generate_embedding", return_value=[0.0, 1.0, 0.0]):
            result = rag.retrieve_relevant_chunks_with_mode(
                self.db,
                self.version.id,
                "zzz",
                limit=3,
                retrieval_mode="semantic",
                min_score=0.5,
            )

        self.assertEqual(result["chunks"], [])


if __name__ == "__main__":
    unittest.main()
