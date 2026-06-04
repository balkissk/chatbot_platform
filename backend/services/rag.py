import math
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from services.embeddings import EmbeddingError, embedding_model_name, generate_embedding


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


def embed_chunk(chunk: Chunk) -> None:
    try:
        embedding = generate_embedding(embedding_text(chunk))
        chunk.embedding = embedding
        chunk.embedding_model = embedding_model_name()
        chunk.embedding_status = "ready"
        chunk.embedding_error = None
        chunk.embedding_dimensions = len(embedding)
    except EmbeddingError as exc:
        chunk.embedding = None
        chunk.embedding_model = embedding_model_name()
        chunk.embedding_status = "failed"
        chunk.embedding_error = str(exc)[:1000]
        chunk.embedding_dimensions = None


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

    rows = db.query(Chunk, Document).join(
        Document,
        Chunk.document_id == Document.id
    ).filter(
        Document.knowledge_base_id == knowledge_base.id
    ).all()

    limit = max(1, min(int(limit or 4), 10))
    retrieval_mode = retrieval_mode if retrieval_mode in {"auto", "semantic", "keyword"} else "auto"
    min_score = max(0.0, min(float(min_score or 0), 1.0))

    def filter_by_score(items: list[tuple[Chunk, Document, float]]) -> list[tuple[Chunk, Document, float]]:
        return [item for item in items if item[2] >= min_score]

    has_embeddings = any(chunk.embedding_status == "ready" and chunk.embedding for chunk, _ in rows)
    if retrieval_mode == "keyword":
        return {
            "mode": "keyword",
            "chunks": filter_by_score(retrieve_keyword_chunks(rows, query, limit))
        }

    if has_embeddings and retrieval_mode in {"auto", "semantic"}:
        try:
            semantic_rows = retrieve_semantic_chunks(rows, query, limit)
            semantic_rows = filter_by_score(semantic_rows)
            if semantic_rows or retrieval_mode == "semantic":
                return {"mode": "semantic", "chunks": semantic_rows}
        except EmbeddingError:
            if retrieval_mode == "semantic":
                return {"mode": "semantic_error", "chunks": []}

    return {
        "mode": "keyword_fallback" if has_embeddings else "keyword",
        "chunks": filter_by_score(retrieve_keyword_chunks(rows, query, limit))
    }
