import unittest
import base64
from io import BytesIO
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
    document_response,
    ingest_document,
    reprocess_document_chunks,
    reprocess_document_embeddings,
    process_document_background,
    sync_document_status,
)
from services import embeddings, rag
from services.document_ingestion import DocumentExtractionError, extract_document_text


def minimal_text_pdf(pages: list[str]) -> bytes:
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
    ]
    page_refs = " ".join(f"{4 + index * 2} 0 R" for index in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{page_refs}] /Count {len(pages)} >>".encode("ascii"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for index, text in enumerate(pages):
        page_object_id = 4 + index * 2
        content_object_id = page_object_id + 1
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 3 0 R >> >> /MediaBox [0 0 612 792] /Contents {content_object_id} 0 R >>".encode("ascii")
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
        )

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_id} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)


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

    def test_processed_document_with_zero_chunks_is_reported_failed(self):
        document = self.add_document(status="processed", raw_text="")

        response = document_response(self.db, document)

        self.assertEqual(response.status, "failed")
        self.assertEqual(response.chunks_count, 0)
        self.assertIn("no searchable chunks", response.error_message.lower())

    def test_text_document_extraction_is_unchanged(self):
        text, size_bytes = extract_document_text(
            filename="doc.txt",
            content_type="text/plain",
            content="alpha beta gamma",
        )

        self.assertEqual(text, "alpha beta gamma")
        self.assertEqual(size_bytes, len("alpha beta gamma".encode("utf-8")))

    def test_text_pdf_extracts_all_pages(self):
        pdf_bytes = minimal_text_pdf([
            "alpha policy page one",
            "beta warranty page two",
        ])
        text, size_bytes = extract_document_text(
            filename="manual.pdf",
            content_type="application/pdf",
            content=base64.b64encode(pdf_bytes).decode("ascii"),
            content_encoding="base64",
        )

        self.assertEqual(size_bytes, len(pdf_bytes))
        self.assertIn("Page 1", text)
        self.assertIn("alpha policy page one", text)
        self.assertIn("Page 2", text)
        self.assertIn("beta warranty page two", text)

    def test_text_pdf_processing_creates_ready_chunks(self):
        pdf_bytes = minimal_text_pdf([
            "alpha policy page one",
            "beta warranty page two",
        ])
        document = Document(
            knowledge_base_id=self.kb.id,
            filename="manual.pdf",
            content_type="application/pdf",
            storage_url="local://manual.pdf",
            status="uploaded",
            chunks_count=0,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)

        class SessionProxy:
            def __getattr__(self, name):
                return getattr(self.db, name)

            def __init__(self, db):
                self.db = db

            def close(self):
                pass

        def fake_embed(chunks):
            for chunk in chunks:
                chunk.embedding_status = "ready"
                chunk.embedding = [0.1]

        with patch.object(knowledge_routes, "SessionLocal", return_value=SessionProxy(self.db)), \
             patch.object(knowledge_routes, "embed_chunks", side_effect=fake_embed):
            process_document_background(
                document.id,
                document.filename,
                document.content_type,
                base64.b64encode(pdf_bytes).decode("ascii"),
                "base64",
            )

        self.db.refresh(document)
        chunks = self.db.query(Chunk).filter(Chunk.document_id == document.id).all()
        self.assertGreater(len(chunks), 0)
        self.assertEqual(document.status, "ready")
        self.assertEqual(document.chunks_count, len(chunks))
        self.assertTrue(all(chunk.embedding_status == "ready" for chunk in chunks))
        self.assertIn("beta warranty page two", document.raw_text)

    def test_empty_pdf_fails_without_ready_status(self):
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        buffer = BytesIO()
        writer.write(buffer)

        with self.assertRaises(DocumentExtractionError) as error:
            extract_document_text(
                filename="empty.pdf",
                content_type="application/pdf",
                content=base64.b64encode(buffer.getvalue()).decode("ascii"),
                content_encoding="base64",
            )

        self.assertIn("no extractable text", str(error.exception).lower())

    def test_corrupted_pdf_fails_without_traceback_message(self):
        with self.assertRaises(DocumentExtractionError) as error:
            extract_document_text(
                filename="broken.pdf",
                content_type="application/pdf",
                content=base64.b64encode(b"not a real pdf").decode("ascii"),
                content_encoding="base64",
            )

        self.assertEqual(str(error.exception), "Could not extract readable text from PDF")

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
