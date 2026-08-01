import math
import re
import logging
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from services.embedding_config import (
    expected_embedding_dimensions,
    pgvector_literal,
    validate_embedding_vector,
)
from services.embeddings import EmbeddingError, embedding_model_name, generate_embedding, generate_embeddings

logger = logging.getLogger(__name__)
EMBEDDING_MAX_RETRIES = 3


WORD_PATTERN = re.compile(r"\w+", re.UNICODE)
EPIC_HEADING_PATTERN = re.compile(r"(?im)^\s*(?:[^\w\s]{0,3}\s*)?(?:EPIC|Epic)\s+\d+\b.*$")
MARKDOWN_HEADING_PATTERN = re.compile(r"(?m)^#{1,6}\s+.+$")
NUMBERED_HEADING_PATTERN = re.compile(r"(?m)^\s*\d+(?:\.\d+)*[.)]?\s+[A-Z][^\n]{3,}$")
STOPWORDS = {
    "a", "an", "and", "are", "about", "is", "the", "to", "of", "or", "for",
    "in", "on", "with", "which", "what", "who", "how", "does", "do"
}


@dataclass
class ChunkData:
    text: str
    title: str | None = None
    section_type: str | None = None
    metadata: dict | None = None


def normalize_text(text: str) -> str:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def clean_title(title: str | None) -> str | None:
    if not title:
        return None
    value = re.sub(r"^\s*#+\s*", "", title.strip())
    value = re.sub(r"^\s*[^\w\s]{1,3}\s*", "", value)
    return value.strip() or None


def section_type_for(title: str | None) -> str:
    value = title or ""
    if re.search(r"(?i)\bEPIC\s+\d+\b", value):
        return "epic"
    if value.lstrip().startswith("#"):
        return "heading"
    if re.match(r"^\s*\d+(?:\.\d+)*[.)]?\s+", value):
        return "numbered_section"
    return "section"


def embedding_text(chunk: Chunk | ChunkData) -> str:
    title = getattr(chunk, "title", None)
    text = getattr(chunk, "text", "") or ""
    return f"{title}\n\n{text}".strip() if title else text


def word_chunks(text: str, max_words: int, overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks = []
    step = max(max_words - overlap, 1)

    for start in range(0, len(words), step):
        chunk_words = words[start:start + max_words]
        if chunk_words:
            chunks.append(" ".join(chunk_words))

    return chunks


def split_long_section(section: str, max_words: int, overlap: int) -> list[str]:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", section) if item.strip()]
    if len(paragraphs) <= 1:
        return word_chunks(section, max_words=max_words, overlap=overlap)

    chunks = []
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate.split()) <= max_words:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(paragraph.split()) <= max_words:
            current = paragraph
        else:
            chunks.extend(word_chunks(paragraph, max_words=max_words, overlap=overlap))

    if current:
        chunks.append(current)

    return chunks


def split_structured_sections(text: str) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    matches = []
    for pattern in (EPIC_HEADING_PATTERN, MARKDOWN_HEADING_PATTERN, NUMBERED_HEADING_PATTERN):
        matches.extend(pattern.finditer(normalized))

    if not matches:
        return [normalized]

    matches = sorted(matches, key=lambda match: match.start())
    sections = []

    if matches[0].start() > 0:
        intro = normalized[:matches[0].start()].strip()
        if intro:
            sections.append(intro)

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        section = normalized[start:end].strip()
        if section:
            sections.append(section)

    return sections if len(sections) > 1 else [normalized]


def title_for_section(section: str) -> str | None:
    first_line = section.splitlines()[0].strip() if section.splitlines() else ""
    if (
        EPIC_HEADING_PATTERN.match(first_line)
        or MARKDOWN_HEADING_PATTERN.match(first_line)
        or NUMBERED_HEADING_PATTERN.match(first_line)
    ):
        return clean_title(first_line)
    return None


def chunk_document(text: str, max_words: int = 90, overlap: int = 12) -> list[ChunkData]:
    sections = split_structured_sections(text)
    chunks = []

    for section_index, section in enumerate(sections):
        title = title_for_section(section)
        section_type = section_type_for(title)
        metadata = {"section_index": section_index}
        if len(section.split()) <= max_words:
            chunks.append(ChunkData(
                text=section,
                title=title,
                section_type=section_type,
                metadata=metadata
            ))
        else:
            for part_index, part in enumerate(split_long_section(section, max_words=max_words, overlap=overlap)):
                chunks.append(ChunkData(
                    text=part,
                    title=title,
                    section_type=section_type,
                    metadata={**metadata, "part_index": part_index}
                ))

    return chunks


def chunk_text(text: str, max_words: int = 90, overlap: int = 12) -> list[str]:
    return [chunk.text for chunk in chunk_document(text, max_words=max_words, overlap=overlap)]


def get_or_create_knowledge_base(db: Session, version_id: int) -> KnowledgeBase:
    knowledge_base = db.query(KnowledgeBase).filter(
        KnowledgeBase.version_id == version_id
    ).first()

    if knowledge_base:
        return knowledge_base

    knowledge_base = KnowledgeBase(
        version_id=version_id,
        name=f"Version {version_id} knowledge base"
    )
    db.add(knowledge_base)
    db.commit()
    db.refresh(knowledge_base)

    return knowledge_base


def tokenize(text: str) -> list[str]:
    tokens = []
    for word in WORD_PATTERN.findall(text):
        token = normalize_token(word)
        if token and token not in STOPWORDS:
            tokens.append(token)
    return tokens


def normalize_token(word: str) -> str:
    token = word.lower().strip()
    if token.endswith("ing") and len(token) > 6:
        token = token[:-3]
    elif token.endswith("s") and len(token) > 4:
        token = token[:-1]
    return token


def cosine_score(query_terms: Counter, chunk_terms: Counter) -> float:
    if not query_terms or not chunk_terms:
        return 0.0

    overlap = set(query_terms) & set(chunk_terms)
    dot_product = sum(query_terms[word] * chunk_terms[word] for word in overlap)
    query_norm = math.sqrt(sum(value * value for value in query_terms.values()))
    chunk_norm = math.sqrt(sum(value * value for value in chunk_terms.values()))

    if query_norm == 0 or chunk_norm == 0:
        return 0.0

    return dot_product / (query_norm * chunk_norm)


def keyword_relevance_score(query: str, text: str) -> float:
    query_terms = Counter(tokenize(query))
    text_terms = Counter(tokenize(text))
    if not query_terms or not text_terms:
        return 0.0

    base_score = cosine_score(query_terms, text_terms)
    unique_query_terms = set(query_terms)
    unique_text_terms = set(text_terms)
    matched_terms = unique_query_terms & unique_text_terms
    coverage = len(matched_terms) / max(len(unique_query_terms), 1)
    phrase_boost = 0.0

    normalized_query = " ".join(tokenize(query))
    normalized_text = " ".join(tokenize(text))
    if normalized_query and normalized_query in normalized_text:
        phrase_boost = 0.35

    heading_text = " ".join((text or "").split()[:14])
    heading_terms = set(tokenize(heading_text))
    heading_boost = 0.0
    for term in matched_terms:
        if len(term) >= 4 and term in heading_terms:
            heading_boost += 0.25

    generic_terms = {"chatbot", "epic", "module", "system"}
    specific_query_terms = {term for term in unique_query_terms if term not in generic_terms and len(term) >= 4}
    specific_match_ratio = len(specific_query_terms & unique_text_terms) / max(len(specific_query_terms), 1)
    specific_heading_ratio = len(specific_query_terms & heading_terms) / max(len(specific_query_terms), 1)

    return min(
        base_score
        + coverage * 0.25
        + specific_match_ratio * 0.45
        + specific_heading_ratio * 0.65
        + phrase_boost
        + heading_boost,
        1.0
    )


def vector_cosine_score(query_vector: list[float], chunk_vector: list[float]) -> float:
    if not query_vector or not chunk_vector or len(query_vector) != len(chunk_vector):
        return 0.0

    dot_product = sum(left * right for left, right in zip(query_vector, chunk_vector))
    query_norm = math.sqrt(sum(value * value for value in query_vector))
    chunk_norm = math.sqrt(sum(value * value for value in chunk_vector))

    if query_norm == 0 or chunk_norm == 0:
        return 0.0

    return dot_product / (query_norm * chunk_norm)


def _safe_embedding_error(exc: Exception) -> str:
    return str(exc)[:1000]


def is_transient_embedding_error(exc: Exception) -> bool:
    message = str(exc).lower()
    transient_markers = [
        "429",
        "rate limit",
        "quota exceeded",
        "timeout",
        "timed out",
        "temporarily",
        "temporary",
        "connection",
        "503",
        "502",
        "504",
        "500 internal",
    ]
    permanent_markers = [
        "401",
        "403",
        "404",
        "authentication failed",
        "authorization failed",
        "deployment was not found",
        "configuration is incomplete",
        "api version incompatibility",
        "unsupported embedding provider",
    ]
    if any(marker in message for marker in permanent_markers):
        return False
    return any(marker in message for marker in transient_markers)


def _mark_chunk_processing(chunk: Chunk) -> None:
    chunk.embedding_status = "processing"
    chunk.last_attempt_at = datetime.utcnow()
    chunk.embedding_error = None
    chunk.last_error = None


def _mark_chunk_ready(chunk: Chunk, vector: list[float], model_name: str) -> None:
    validate_embedding_vector(vector)
    chunk.embedding = vector
    chunk.embedding_vector = pgvector_literal(vector)
    chunk.embedding_model = model_name
    chunk.embedding_status = "ready"
    chunk.embedding_error = None
    chunk.last_error = None
    chunk.embedding_dimensions = len(vector)
    chunk.embedded_at = datetime.utcnow()


def _mark_chunk_failed(chunk: Chunk, exc: Exception) -> None:
    safe_error = _safe_embedding_error(exc)
    chunk.embedding = None
    chunk.embedding_vector = None
    chunk.embedding_model = embedding_model_name()
    chunk.embedding_status = "failed"
    chunk.embedding_error = safe_error
    chunk.last_error = safe_error
    chunk.embedding_dimensions = None


def embed_chunk(chunk: Chunk, max_retries: int = EMBEDDING_MAX_RETRIES) -> None:
    max_retries = max(1, int(max_retries or EMBEDDING_MAX_RETRIES))
    try:
        for attempt in range(max_retries):
            _mark_chunk_processing(chunk)
            chunk.retry_count = int(chunk.retry_count or 0) + 1
            try:
                started_at = time.perf_counter()
                embedding = generate_embedding(embedding_text(chunk))
                _mark_chunk_ready(chunk, embedding, embedding_model_name())
                logger.info(
                    "knowledge_embedding chunk_id=%s operation=embed status=ready retry_count=%s latency_ms=%s",
                    getattr(chunk, "id", None),
                    chunk.retry_count,
                    round((time.perf_counter() - started_at) * 1000),
                )
                return
            except (EmbeddingError, ValueError) as exc:
                _mark_chunk_failed(chunk, exc)
                transient = is_transient_embedding_error(exc)
                logger.warning(
                    "knowledge_embedding chunk_id=%s operation=embed status=failed retry_count=%s transient=%s error=%s",
                    getattr(chunk, "id", None),
                    chunk.retry_count,
                    transient,
                    chunk.last_error,
                )
                if not transient or attempt >= max_retries - 1:
                    return
                time.sleep(min(2 ** attempt, 4))
    except (EmbeddingError, ValueError) as exc:
        _mark_chunk_failed(chunk, exc)


def embed_chunks(chunks: list[Chunk], batch_size: int = 8, max_retries: int = EMBEDDING_MAX_RETRIES) -> None:
    pending_chunks = [
        chunk
        for chunk in chunks
        if chunk.embedding_status != "ready" or not chunk.embedding or not getattr(chunk, "embedding_vector", None)
    ]
    if not pending_chunks:
        return

    batch_size = max(1, min(int(batch_size or 8), 32))
    for start in range(0, len(pending_chunks), batch_size):
        batch = pending_chunks[start:start + batch_size]
        for chunk in batch:
            _mark_chunk_processing(chunk)
            chunk.retry_count = int(chunk.retry_count or 0) + 1

        try:
            started_at = time.perf_counter()
            vectors = generate_embeddings([embedding_text(chunk) for chunk in batch])
        except EmbeddingError as exc:
            for chunk in batch:
                chunk.retry_count = max(int(chunk.retry_count or 1) - 1, 0)
                embed_chunk(chunk, max_retries=max_retries)
            continue

        model_name = embedding_model_name()
        for chunk, vector in zip(batch, vectors):
            try:
                _mark_chunk_ready(chunk, vector, model_name)
                logger.info(
                    "knowledge_embedding chunk_id=%s operation=batch_embed status=ready retry_count=%s latency_ms=%s",
                    getattr(chunk, "id", None),
                    chunk.retry_count,
                    round((time.perf_counter() - started_at) * 1000),
                )
            except ValueError as exc:
                _mark_chunk_failed(chunk, exc)
                logger.warning(
                    "knowledge_embedding chunk_id=%s operation=batch_embed status=failed retry_count=%s error=%s",
                    getattr(chunk, "id", None),
                    chunk.retry_count,
                    chunk.last_error,
                )


def retrieve_keyword_chunks(
    rows: list[tuple[Chunk, Document]],
    query: str,
    limit: int
) -> list[tuple[Chunk, Document, float]]:
    query_terms = Counter(tokenize(query))
    scored_rows = []

    for chunk, document in rows:
        score = keyword_relevance_score(query, embedding_text(chunk))
        if score > 0:
            scored_rows.append((chunk, document, score))

    scored_rows.sort(key=lambda item: item[2], reverse=True)
    return scored_rows[:limit]


def retrieve_semantic_chunks(
    rows: list[tuple[Chunk, Document]],
    query: str,
    limit: int
) -> list[tuple[Chunk, Document, float]]:
    query_embedding = generate_embedding(query)
    scored_rows = []

    for chunk, document in rows:
        if chunk.embedding_status != "ready" or not chunk.embedding:
            continue
        semantic_score = vector_cosine_score(query_embedding, chunk.embedding)
        keyword_score = keyword_relevance_score(query, embedding_text(chunk))
        score = (semantic_score * 0.35) + (keyword_score * 0.65)
        if score > 0:
            scored_rows.append((chunk, document, score))

    scored_rows.sort(key=lambda item: item[2], reverse=True)
    return scored_rows[:limit]


def _is_postgresql_session(db: Session) -> bool:
    bind = db.get_bind()
    return bool(bind and bind.dialect.name == "postgresql")


def _ready_document_statuses() -> tuple[str, ...]:
    return ("ready", "partially_ready", "processed")


def ready_vector_count(db: Session, knowledge_base_id: int) -> int:
    query = db.query(Chunk.id).join(
        Document,
        Chunk.document_id == Document.id,
    ).filter(
        Document.knowledge_base_id == knowledge_base_id,
        Document.status.in_(_ready_document_statuses()),
        Chunk.embedding_status == "ready",
        Chunk.embedding_vector.isnot(None),
    )
    return query.count()


def retrieve_pgvector_chunks(
    db: Session,
    knowledge_base_id: int,
    query: str,
    limit: int,
    min_score: float = 0.0,
) -> list[tuple[Chunk, Document, float]]:
    if not _is_postgresql_session(db):
        raise RuntimeError("pgvector retrieval requires PostgreSQL")

    started_at = time.perf_counter()
    query_embedding = generate_embedding(query)
    validate_embedding_vector(query_embedding)
    embedding_ms = round((time.perf_counter() - started_at) * 1000)

    vector_literal = pgvector_literal(query_embedding)
    sql = text("""
        SELECT
            c.id AS chunk_id,
            1 - (c.embedding_vector <=> CAST(:query_vector AS vector)) AS similarity
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.knowledge_base_id = :knowledge_base_id
          AND d.status IN ('ready', 'partially_ready', 'processed')
          AND c.embedding_status = 'ready'
          AND c.embedding_vector IS NOT NULL
          AND (1 - (c.embedding_vector <=> CAST(:query_vector AS vector))) >= :min_score
        ORDER BY c.embedding_vector <=> CAST(:query_vector AS vector)
        LIMIT :limit
    """)

    db_started_at = time.perf_counter()
    scored = db.execute(sql, {
        "query_vector": vector_literal,
        "knowledge_base_id": knowledge_base_id,
        "min_score": min_score,
        "limit": limit,
    }).fetchall()
    db_ms = round((time.perf_counter() - db_started_at) * 1000)

    chunk_ids = [row.chunk_id for row in scored]
    if not chunk_ids:
        logger.info(
            "rag_retrieval operation=pgvector knowledge_base_id=%s top_k=%s min_score=%s query_embedding_ms=%s db_ms=%s rows=0 dimensions=%s",
            knowledge_base_id,
            limit,
            min_score,
            embedding_ms,
            db_ms,
            expected_embedding_dimensions(),
        )
        return []

    rows = db.query(Chunk, Document).join(
        Document,
        Chunk.document_id == Document.id,
    ).filter(
        Chunk.id.in_(chunk_ids)
    ).all()
    by_chunk_id = {chunk.id: (chunk, document) for chunk, document in rows}
    result = [
        (by_chunk_id[row.chunk_id][0], by_chunk_id[row.chunk_id][1], float(row.similarity or 0.0))
        for row in scored
        if row.chunk_id in by_chunk_id
    ]

    logger.info(
        "rag_retrieval operation=pgvector knowledge_base_id=%s top_k=%s min_score=%s query_embedding_ms=%s db_ms=%s rows=%s dimensions=%s",
        knowledge_base_id,
        limit,
        min_score,
        embedding_ms,
        db_ms,
        len(result),
        expected_embedding_dimensions(),
    )
    return result


def retrieve_relevant_chunks(
    db: Session,
    version_id: int,
    query: str,
    limit: int = 4,
    retrieval_mode: str = "auto",
    min_score: float = 0.0
) -> list[tuple[Chunk, Document, float]]:
    result = retrieve_relevant_chunks_with_mode(db, version_id, query, limit, retrieval_mode, min_score)
    return result["chunks"]


def retrieve_relevant_chunks_with_mode(
    db: Session,
    version_id: int,
    query: str,
    limit: int = 4,
    retrieval_mode: str = "auto",
    min_score: float = 0.0
) -> dict:
    knowledge_base = db.query(KnowledgeBase).filter(
        KnowledgeBase.version_id == version_id
    ).first()

    if not knowledge_base:
        return {"mode": "none", "chunks": []}

    limit = max(1, min(int(limit or 4), 10))
    retrieval_mode = retrieval_mode if retrieval_mode in {"auto", "semantic", "keyword"} else "auto"
    min_score = max(0.0, min(float(min_score or 0), 1.0))

    rows_cache: list[tuple[Chunk, Document]] | None = None

    def load_rows() -> list[tuple[Chunk, Document]]:
        nonlocal rows_cache
        if rows_cache is None:
            rows_cache = db.query(Chunk, Document).join(
                Document,
                Chunk.document_id == Document.id
            ).filter(
                Document.knowledge_base_id == knowledge_base.id
            ).all()
        return rows_cache

    def filter_by_score(items: list[tuple[Chunk, Document, float]]) -> list[tuple[Chunk, Document, float]]:
        return [item for item in items if item[2] >= min_score]

    has_vectors = ready_vector_count(db, knowledge_base.id) > 0 if _is_postgresql_session(db) else False
    has_json_embeddings = (
        False
        if _is_postgresql_session(db)
        else any(chunk.embedding_status == "ready" and chunk.embedding for chunk, _ in load_rows())
    )
    has_embeddings = has_vectors or has_json_embeddings
    if retrieval_mode == "keyword":
        return {
            "mode": "keyword",
            "chunks": filter_by_score(retrieve_keyword_chunks(load_rows(), query, limit))
        }

    if has_embeddings and retrieval_mode in {"auto", "semantic"}:
        try:
            if _is_postgresql_session(db) and has_vectors:
                semantic_rows = retrieve_pgvector_chunks(
                    db,
                    knowledge_base.id,
                    query,
                    limit,
                    min_score=min_score,
                )
            else:
                semantic_rows = filter_by_score(retrieve_semantic_chunks(load_rows(), query, limit))
            if semantic_rows or retrieval_mode == "semantic":
                return {"mode": "semantic", "chunks": semantic_rows}
        except (EmbeddingError, ValueError):
            if retrieval_mode == "semantic":
                return {"mode": "semantic_error", "chunks": []}

    return {
        "mode": "keyword_fallback" if has_embeddings else "keyword",
        "chunks": filter_by_score(retrieve_keyword_chunks(load_rows(), query, limit))
    }
