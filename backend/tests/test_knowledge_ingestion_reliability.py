import unittest
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks, HTTPException
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
from routes import knowledge_routes
from routes.knowledge_routes import (
    ingest_document,
    reprocess_document_chunks,
    reprocess_document_embeddings,
    sync_document_status,
)
from services import embeddings, rag


class KnowledgeIngestionReliabilityTest(unittest.TestCase):
    def setUp(self):
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

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_document(self, status="uploaded", raw_text="alpha beta gamma") -> Document:
        document = Document(
            knowledge_base_id=self.kb.id,
            filename="doc.txt",
            content_type="text/plain",
            storage_url="local://doc.txt",
            raw_text=raw_text,
            status=status,
        )
        self.db.add(document)
        self.db.commit()
        return document

    def test_all_chunks_ready_marks_document_ready(self):
        document = self.add_document()
        self.db.add_all([
            Chunk(document_id=document.id, order=0, text="alpha", embedding_status="ready", embedding=[0.1]),
            Chunk(document_id=document.id, order=1, text="beta", embedding_status="ready", embedding=[0.2]),
        ])
        self.db.commit()

        counts = sync_document_status(self.db, document, commit=True)

        self.assertEqual(counts["ready"], 2)
        self.assertEqual(document.status, "ready")
        self.assertIsNone(document.error_message)

    def test_partial_failures_preserve_successful_chunks_and_mark_partially_ready(self):
        document = self.add_document()
        ready = Chunk(document_id=document.id, order=0, text="alpha", embedding_status="ready", embedding=[0.1])
        failed = Chunk(document_id=document.id, order=1, text="beta", embedding_status="failed", embedding=None)
        self.db.add_all([ready, failed])
        self.db.commit()

        counts = sync_document_status(self.db, document, commit=True)

        self.assertEqual(counts["ready"], 1)
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(document.status, "partially_ready")
        self.assertEqual(ready.embedding, [0.1])

    def test_embedding_reprocess_retries_only_failed_or_pending_chunks(self):
        document = self.add_document(status="partially_ready")
        ready = Chunk(document_id=document.id, order=0, text="ready", embedding_status="ready", embedding=[0.1])
        failed = Chunk(document_id=document.id, order=1, text="failed", embedding_status="failed")
        pending = Chunk(document_id=document.id, order=2, text="pending", embedding_status="pending")
        self.db.add_all([ready, failed, pending])
        self.db.commit()
        retried_ids = []

        def fake_embed(chunks):
            retried_ids.extend(chunk.id for chunk in chunks)
            for chunk in chunks:
                chunk.embedding = [0.9]
                chunk.embedding_status = "ready"

        with patch.object(knowledge_routes, "embed_chunks", side_effect=fake_embed):
            result = reprocess_document_embeddings(document.id, db=self.db, current_user=self.user)

        self.assertNotIn(ready.id, retried_ids)
        self.assertEqual(set(retried_ids), {failed.id, pending.id})
        self.assertEqual(result["ready_chunks"], 3)
        self.assertEqual(result["failed_chunks"], 0)

    def test_duplicate_upload_detects_same_sha256_in_same_knowledge_base(self):
        payload = knowledge_routes.DocumentIngest(filename="doc.txt", content="same content", content_type="text/plain")
        tasks = BackgroundTasks()
        ingest_document(self.version.id, payload, tasks, db=self.db, current_user=self.user)

        with self.assertRaises(HTTPException) as error:
            ingest_document(self.version.id, payload, BackgroundTasks(), db=self.db, current_user=self.user)

        self.assertEqual(error.exception.status_code, 409)

    def test_repeated_reprocess_while_processing_does_not_start_duplicate_work(self):
        document = self.add_document(status="processing")
        self.db.add(Chunk(document_id=document.id, order=0, text="alpha", embedding_status="processing"))
        self.db.commit()

        with patch.object(knowledge_routes, "embed_chunks", side_effect=AssertionError("should not run")):
            result = reprocess_document_embeddings(document.id, db=self.db, current_user=self.user)

        self.assertEqual(result["total_chunks"], 1)

    def test_chunk_reprocess_failure_preserves_previous_ready_index(self):
        document = self.add_document(status="ready", raw_text="new text for replacement")
        old_chunk = Chunk(document_id=document.id, order=0, text="old", embedding_status="ready", embedding=[0.1])
        self.db.add(old_chunk)
        self.db.commit()

        def fail_replacement(chunks):
            for chunk in chunks:
                chunk.embedding_status = "failed"
                chunk.embedding = None

        with patch.object(knowledge_routes, "embed_chunks", side_effect=fail_replacement):
            result = reprocess_document_chunks(document.id, db=self.db, current_user=self.user)

        stored_chunks = self.db.query(Chunk).filter(Chunk.document_id == document.id).all()
        self.assertEqual(len(stored_chunks), 1)
        self.assertEqual(stored_chunks[0].text, "old")
        self.assertEqual(stored_chunks[0].embedding_status, "ready")
        self.assertEqual(result["ready_chunks"], 1)

    def test_retry_exhaustion_marks_chunk_failed_with_bounded_retry_count(self):
        chunk = Chunk(document_id=1, order=0, text="retry me", embedding_status="pending")

        with patch.object(rag, "generate_embedding", side_effect=rag.EmbeddingError("429 rate limit")), \
             patch.object(rag.time, "sleep", return_value=None):
            rag.embed_chunk(chunk, max_retries=3)

        self.assertEqual(chunk.embedding_status, "failed")
        self.assertEqual(chunk.retry_count, 3)
        self.assertIn("429", chunk.last_error)

    def test_azure_embedding_client_is_reused(self):
        embeddings._azure_embedding_client_cache.clear()
        client = MagicMock()
        config = embeddings.AzureEmbeddingConfig(
            endpoint="https://example.openai.azure.com",
            api_key="key",
            deployment="text-embedding-3-small",
            api_version="2024-10-21",
        )
        with patch("openai.AzureOpenAI", return_value=client) as factory:
            first = embeddings._azure_embedding_client(config)
            second = embeddings._azure_embedding_client(config)

        self.assertIs(first, second)
        self.assertEqual(factory.call_count, 1)


if __name__ == "__main__":
    unittest.main()
