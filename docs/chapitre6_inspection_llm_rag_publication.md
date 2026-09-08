# Chapter 6 — Code Inspection Report
## « Intégration des modèles de langage, RAG et publication des assistants »

Read-only inspection. No source file was modified. No test, build, linter, Docker,
CI/CD or Git command was executed during this inspection.

---

# 1. EXECUTIVE SUMMARY

ChatBot Factory **integrates external, pre-trained LLM and embedding services**. It does
not train, fine-tune or host a model itself. Two providers are implemented behind a single
abstraction: **Ollama** (local, default in code) and **Azure OpenAI** (the provider used in
`backend/.env.example`, deployment `gpt-5-mini` + `text-embedding-3-small`).

**Part I is genuinely implemented end-to-end**: document upload → text extraction (pypdf /
UTF-8) → structure-aware word-based chunking → embedding generation with retry →
storage in PostgreSQL with **pgvector** → cosine similarity retrieval → prompt assembly with
retrieved context → LLM generation (blocking and streaming) → source references.
The knowledge base is **one per chatbot version**, created lazily.

**Part II is also implemented**, with a rich pre-publication readiness checklist
(`readiness_report`), a real runtime smoke test, an assertion-based Evaluation Center that
can act as a publish gate, and three public delivery surfaces (hosted public chat page,
embeddable JavaScript widget, API-key REST endpoint).

The most important nuances for an honest report:

1. **RAG evaluation is deterministic and assertion-based, not academic.** There is no
   groundedness, faithfulness, context-relevance, precision/recall or MRR computation.
   LLM-as-judge is present as a field but explicitly disabled.
2. **Publication archives every other version, including drafts**, and **no new draft is
   created automatically**. There is no unpublish and no rollback endpoint.
3. **A published version is not immutable**: flow node/transition CRUD and the LLM config
   endpoint do not check version status, so a live version can be edited in place.
4. **`ChatbotChannel` rows are descriptive metadata only.** The public runtime never reads
   them; it resolves the version from `chatbot.active_version_id`. Channel status,
   `deployed_version_id` and the "test channel" action have no runtime effect.
5. **Admin is read-only on the workspace** (`require_workspace_manager`), **except on flow
   node/transition endpoints**, which still accept admin — an authorization inconsistency.
6. **`/llm-config` has no ownership check**, so any manager can read or overwrite the LLM
   configuration of any version by numeric id.
7. **Public web/widget access is identified only by a numeric `chatbot_id`** with no token,
   no slug and no rate limiting.

---

# 2. CHAPTER 6 FEATURE STATUS

| Feature | Status | Backend | Frontend | Notes |
|---|---|---|---|---|
| **A. LLM integration** | IMPLEMENTED | `services/ai_provider.py`, `routes/chat_routes.py` | `pages/versions` (Instructions block) | Ollama + Azure OpenAI; blocking + streaming |
| **A. LLM configuration** | PARTIAL | `models/llm_config.py`, `routes/llm_config_routes.py` | `pages/versions/versions.component.ts` | Only `model`, `temperature`, `system_prompt`; `model` not exposed in UI and ignored under Azure |
| **B. Knowledge Base** | PARTIAL | `models/knowledge_base.py`, `services/rag.get_or_create_knowledge_base` | `pages/knowledge-base` | Auto-created per version; no create/rename/delete KB action |
| **C. Document processing** | IMPLEMENTED | `services/document_ingestion.py`, `routes/knowledge_routes.process_document_background` | `pages/knowledge-base` (+ status polling) | pypdf for PDF, UTF-8 otherwise; no OCR |
| **C. Chunking** | IMPLEMENTED (fixed) | `services/rag.chunk_document` | — | Word-based, 90 words / 12 overlap, hard-coded |
| **D. Embeddings / vectorization** | IMPLEMENTED | `services/embeddings.py`, `services/embedding_config.py`, `services/rag.embed_chunks` | status/counters only | Batch + retry + dimension validation |
| **D. Vector storage** | IMPLEMENTED | `models/chunk.py`, `models/vector_type.PgVector` | — | pgvector `VECTOR(1536)` + JSON copy for dev fallback |
| **E. Semantic retrieval** | IMPLEMENTED | `services/rag.retrieve_pgvector_chunks`, `retrieve_relevant_chunks_with_mode` | `pages/knowledge-base` retrieval tester | Cosine via `<=>`; keyword fallback |
| **F. RAG execution** | IMPLEMENTED | `routes/chat_routes.prepare_rag_generation` / `build_rag_response` | `flow-test`, `public-chat`, widget | Node-level overrides; `continue_rag` loop |
| **F. Source references** | IMPLEMENTED | backend-enforced in `prepare_rag_generation` | `flow-test` panel | Always stripped on public web/widget |
| **G. RAG evaluation** | PARTIAL (assertion-based) | `services/evaluation_engine.py`, `routes/evaluation_routes.py` | `pages/evaluations` | Deterministic assertions only; judge disabled |
| **H. Version management** | IMPLEMENTED | `routes/version_routes.py`, `models/version.py` | `pages/versions` | Create / duplicate / archive / delete |
| **H. Rollback / unpublish** | NOT IMPLEMENTED | — | label only in `project-overview` | No endpoint; UI label is a computed count |
| **I. Flow validation** | IMPLEMENTED | `services/flow_validation.validate_flow_version` | `flow-builder` | Chapter 5 |
| **I. Publication readiness** | IMPLEMENTED | `services/publication_readiness.readiness_report` | `pages/versions`, `pages/evaluations` | 9–11 checks, BLOCKED / WARNING / PASSED |
| **I. Runtime smoke test** | IMPLEMENTED | `publication_readiness.run_version_smoke_test`, `models/version_smoke_test.py` | `pages/versions` | Real 3-turn runtime execution |
| **J. Publication** | IMPLEMENTED | `version_routes.publish_version` | `pages/versions`, `pages/evaluations` | Gated + audited |
| **K. Channel: public chat page** | IMPLEMENTED | `routes/public_routes.py` | `pages/public-chat` | Anonymous, numeric id |
| **K. Channel: web widget** | IMPLEMENTED | `public_routes.widget_script` | snippet in `chatbot-deployment` | Self-contained JS, streaming |
| **K. Channel: public REST API** | IMPLEMENTED | `public_routes` `/public/api/chat*` | curl snippet only | `x-chatbot-api-key` header |
| **K. Channel records / status** | CONFIG-ONLY | `routes/channel_routes.py`, `models/chatbot_channel.py` | read-only in `chatbot-deployment` | Runtime ignores them entirely |
| **L. Public access / version resolution** | IMPLEMENTED | `public_routes.get_active_version`, `unified_runtime.get_active_version` | — | Published-only, drafts unreachable |
| **L. Public rate limiting / origin restriction** | NOT IMPLEMENTED | — | — | Only global CORS + auth-route rate limiting |
| **M. Runtime logging** | IMPLEMENTED | `models/runtime_log.py`, `unified_runtime.persist_runtime_log` | `admin-runtime-logs` | Latency, rag_used, failure category |
| **M. Audit logging** | IMPLEMENTED | `services/audit.record_audit_log`, `models/audit_log.py` | `admin-audit-logs` | Partial coverage (see §20) |
| **N. Admin supervision** | IMPLEMENTED | `routes/admin_analytics_routes.py` | `admin-*` pages | Admin-only, global scope |
| **N. Health diagnostics** | IMPLEMENTED | `routes/health_routes.py` | — | `/health/ai`, `/health/rag`, `/health/database` |

---

# 3. PART I — LLM AND RAG (VERIFIED INSPECTION)

## 3.1 Pre-trained LLM integration

### Providers and models — IMPLEMENTED

`backend/services/ai_provider.py`

| Item | Evidence |
|---|---|
| Provider switch | `AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama")` (line ~14) |
| Supported values | `ollama`, `azure_openai`; anything else raises `AIProviderError` in `validate_ai_configuration()` (~158–163) |
| Ollama model | `OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")` |
| Azure deployment | `AZURE_OPENAI_DEPLOYMENT`, resolved by `azure_openai_config()` (~90–114) |
| Effective model | `configured_chat_model(requested_model)` (~55–58): under Azure it **returns the deployment and ignores the per-version `model` column** |
| Reasoning models | `is_reasoning_chat_deployment()` matches `gpt-5*`, `o1*`, `o3*`, `o4*` → sends `max_completion_tokens` + `reasoning_effort`, **omits `temperature`** (~117–133, 321–328) |
| Startup validation | `backend/main.py::validate_external_ai_configuration` (~128–137) — the API refuses to start on invalid AI/embedding configuration |
| Reference environment | `backend/.env.example`: `AI_PROVIDER=azure_openai`, `AZURE_OPENAI_DEPLOYMENT=gpt-5-mini`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small`, `EMBEDDING_DIMENSIONS=1536` |

There is **one active provider at a time**, chosen by environment variable — not per project,
not per assistant, not selectable at runtime.

### Configuration entity — PARTIAL

`backend/models/llm_config.py` — `class LLMConfig`, table `llm_configs`:

- `version_id` (FK `versions.id`, **unique** → one config per version)
- `model` (String, default `"llama3"`)
- `temperature` (Float, default `0.7`)
- `system_prompt` (String)

**Scope = chatbot version.** There is no global, project, chatbot, flow or node-level LLM
config table.

Fields that **do not exist**: `max_tokens`, API key reference, timeout, retry count,
fallback text, top_p, presence/frequency penalty, provider selector.

Where the missing behaviour actually comes from:

| Concept | Real source |
|---|---|
| Max tokens | `response_profile_for(response_length)` in `routes/chat_routes.py` (~221–236): `short`→80, `normal`→140, `detailed`→240 `num_predict` |
| Timeout | `AZURE_OPENAI_TIMEOUT_SECONDS` (default 60) for Azure; `timeout=120` hard-coded for Ollama (`_ollama_generate`, ~284) |
| Retry | `AZURE_OPENAI_MAX_RETRIES` (default 2), applied by the OpenAI SDK client (~238–250). **Ollama has no retry.** |
| Fallback text | per-node `config["fallback"]` on `rag_answer` / `knowledge_search` |
| Source visibility | `chatbot.rag_settings.show_sources` + node `show_sources` |
| Response caching | optional in-process dict, `AI_RESPONSE_CACHE_ENABLED` (default off), TTL 120 s, max 256 entries (~61–87) |

Node/assistant-level generation behaviour lives in `Chatbot.rag_settings` (JSON) normalized
by `services/rag_settings.normalize_rag_settings`:
`retrieval_mode` (`auto|semantic|keyword`), `max_chunks` (1–8), `min_score` (0–1),
`show_sources`, `strict_context`, `response_length` (`short|normal|detailed`).
**This is per chatbot, not per version** — see §19/§6 discrepancies.

### Backend execution path — IMPLEMENTED

Authenticated / test path:

```
POST /chat/stream  (routes/chat_routes.py::chat_stream, ~596)
  → get_chat_version()               resolve version (draft allowed for admin/manager)
  → LLMConfig lookup by version_id   404 "No config" if missing
  → get_or_create_session()          ConversationSession state
  → execute_flow(..., rag_answer=…)  services/flow_runtime.py (Chapter 5 engine)
       └─ on rag_answer/knowledge_search node → rag_answer callback
            → prepare_rag_generation()      chat_routes.py ~293
                 → retrieve_relevant_chunks_with_mode()   services/rag.py ~596
                 → prompt assembly
  → stream_ai_answer(generation)     chat_routes.py ~489
       → stream_chat_completion()    ai_provider.py ~360
  → SSE events: start / token / final
```

Public path: `routes/public_routes.py::public_chat_stream` (~222) — identical structure,
`mode_used="public_flow_rag"`, plus `persist_runtime_log` on success and failure.
Non-streaming public path: `services/unified_runtime.run_chatbot_message` (~225).

Error handling:
- `AIProviderError` → `HTTPException(502, "LLM service error: …")` in `build_rag_response`
  (~457–461) and `stream_ai_answer` (~502).
- Azure errors are translated to safe, non-leaking messages by `_safe_openai_error`
  (~178–220) which maps 401/403/404/429, `max_tokens`/`max_completion_tokens` mismatch,
  unsupported `temperature`, and API-version problems, and redacts the API key.
- An empty Azure completion is treated as an error (~343–349).

### Prompt handling — IMPLEMENTED

`prepare_rag_generation` (`routes/chat_routes.py` ~293–425) composes, in this order:

1. `LLMConfig.system_prompt` (or `"You are a helpful assistant"`)
2. language instruction derived from `chatbot.language`
3. `"Use the knowledge context to answer the user directly."`
4. node instructions (`node_config["prompt"]` or `["instructions"]`)
5. response-length instruction from `response_profile_for`
6. anti-meta-commentary guardrails and a feedback-retry instruction
7. `missing_context_instruction` — differs depending on `strict_context`

then appends four labelled blocks: **Conversation history**, **Variables**,
**Previous AI answer**, **Feedback**, **Knowledge context**, **User question**.

Context blocks are formatted `[Source i: <filename>, score=<0.00>]` + compacted chunk text
(~326–332). Duplicate instruction lines are removed by `unique_prompt_lines`.
History comes from `session_history()` / `format_history()`; the latest user message is
excluded from history to avoid duplication (`exclude_latest_user_message`).

Node-level overrides are merged by `merge_node_rag_settings` (~258–290):
`use_knowledge_base`, `answer_only_from_documents` → `strict_context`,
`show_sources` (**ANDed** with the assistant setting), `response_length`, `fallback`,
`prompt`/`instructions`.

### Frontend LLM configuration — PARTIAL

| Item | Evidence |
|---|---|
| Route | `/dashboard/projects/:projectId/chatbots/:chatbotId/versions` (`app.routes.ts` ~82) |
| Component | `pages/versions/versions.component.ts` — `loadLlmConfig` (~255), `saveLlmConfig` (~277), `parseSystemPrompt` (~301), `buildSystemPrompt` (~318) |
| API | `GET /llm-config/{version_id}`, `POST /llm-config` |
| Visible fields | System Instructions (textarea), Tone (select), Language (select), Response style (select), Temperature (number 0–1) — `versions.component.html` ~120–170 |
| Role gate | route open to `admin` + `manager`; buttons disabled via `canManageWorkspace()`; backend `POST /llm-config` requires `require_workspace_manager` (manager only) |

**Important for the report:** *Tone*, *Language* and *Response style* are **not database
columns**. `buildSystemPrompt()` appends them as `Tone: …`, `Language: …`,
`Response style: …` lines inside `system_prompt`, and `extractPromptValue()` parses them
back out when loading. The `model` field exists in the component state but **has no input in
the template** — it is always submitted as the default `"llama3"`, and is ignored anyway when
`AI_PROVIDER=azure_openai`.

`Chatbot.rag_settings` is edited from a different page: `pages/knowledge-base` →
`updateChatbotRagSettings` → `PUT /chatbots/{id}/rag-settings`
(`knowledge-base.component.html` ~292–360: Retrieval mode, Max chunks, Min score,
Show source references, `strict_context`).

## 3.2 Knowledge Base

### Data model — IMPLEMENTED

| Model | Table | Key fields | Relationships |
|---|---|---|---|
| `KnowledgeBase` (`models/knowledge_base.py`) | `knowledge_bases` | `id`, `name`, `version_id` **unique**, `created_at` | `documents` 1-N |
| `Document` (`models/document.py`) | `documents` | `knowledge_base_id`, `filename`, `content_type`, `storage_url`, `raw_text`, `content_hash`, `size_bytes`, `status`, `error_message`, `processed_at`, `chunks_count`, `created_at` | `knowledge_base` N-1, `chunks` 1-N |
| `Chunk` (`models/chunk.py`) | `chunks` | `document_id`, `order`, `title`, `section_type`, `metadata_json`, `text`, `embedding_id`, `embedding` (JSON), `embedding_vector` (`PgVector`), `embedding_model`, `embedding_status`, `embedding_error`, `retry_count`, `last_error`, `last_attempt_at`, `embedded_at`, `embedding_dimensions`, `retrieval_score` | `document` N-1 |

Linkage chain: `Project → Chatbot → VersionChatbot → KnowledgeBase → Document → Chunk`.

- There is **no** direct `KnowledgeBase.project_id` or `.chatbot_id`.
- There is **no** join table between a flow node and a knowledge base. A `rag_answer` /
  `knowledge_search` node uses `use_knowledge_base: true|false` only; retrieval always
  targets the KB of the executing version.
- `Chunk.retrieval_score` is declared but no writer was found in the inspected code
  (uncertain — would need a repository-wide check of `retrieval_score` assignments).

### Lifecycle — IMPLEMENTED (with naming caveats)

There is **no explicit "create knowledge base" action**. `get_or_create_knowledge_base`
(`services/rag.py` ~193–208) creates it lazily on first document upload or first
`GET /versions/{id}/documents` by a manager, with the auto-name
`f"Version {version_id} knowledge base"`. There is no rename and no delete-KB endpoint; the
KB is removed only as a side effect of `DELETE /versions/{version_id}`
(`version_routes.delete_version` ~378–388).

**Document statuses actually present in code** (`routes/knowledge_routes.py`
`status_from_counts` ~115–130, `sync_document_status` ~133–148):

| Status | Meaning |
|---|---|
| `uploaded` | row created, background task not finished, no chunks yet |
| `processing` | extraction/chunking/embedding in progress, or partial embeddings |
| `ready` | all chunks have a usable embedding |
| `partially_ready` | some chunks ready, some failed, none pending → `error_message = "Some chunks failed embedding generation"` |
| `failed` | extraction failed, or all chunks failed embedding |
| `processed` | **legacy default** of `Document.status`; still accepted as "ready" by retrieval (`_ready_document_statuses()` in `services/rag.py` ~488) |

**Chunk `embedding_status`**: `pending` → `processing` → `ready` | `failed`
(`_mark_chunk_processing` / `_mark_chunk_ready` / `_mark_chunk_failed`, `services/rag.py`
~336–363).

So the pipeline `Uploaded → Processing → Chunking → Embedding → Ready` **is** supported, with
the accurate wording being: *uploaded → processing (extraction, chunking, embedding) →
ready / partially_ready / failed*, where the document status is **derived** from chunk
embedding states rather than set by an explicit stage machine.

### File management — PARTIAL

| Question | Answer | Evidence |
|---|---|---|
| Accepted types | PDF via pypdf, everything else treated as UTF-8 text. Frontend `accept=".txt,.md,.csv,.json,.pdf,application/pdf"` | `services/document_ingestion.py`; `knowledge-base.component.html` ~67 |
| MIME validation | **None enforced.** `is_pdf()` only decides the extraction strategy from content-type *or* `.pdf` extension | `document_ingestion.py` ~10–14 |
| Size limit | **None** in backend or frontend | no limit found in `ingest_document` |
| Storage | **No file storage.** `storage_url = f"local://version-{version_id}/{filename}"` is a synthetic string; the extracted text is stored in `documents.raw_text` | `knowledge_routes.ingest_document` ~292 |
| Transport | JSON body; PDFs sent as base64 data URL (`readAsDataURL`), text via `readAsText` | `knowledge-base.component.ts` ~203–246 |
| Filename | trimmed, required, non-unique | `ingest_document` ~270–272 |
| Duplicates | SHA-256 of decoded bytes; identical content in the same KB → **HTTP 409** | `document_content_hash` ~71, duplicate check ~278–286 |
| Delete | chunks deleted, then document; audit `DOCUMENT_DELETED` | `delete_document` ~556–579 |
| Reprocess embeddings | only chunks lacking a searchable embedding | `reprocess_document_embeddings` ~398–434 |
| Reprocess chunks | re-chunks from `raw_text`; **requires `raw_text`** (400 for legacy rows); replaces old chunks **only if every new chunk embedded successfully**, otherwise the previous index is preserved | `reprocess_document_chunks` ~437–507 |
| Extraction failures | `status="failed"`, `error_message`, `chunks_count=0`; scanned/image-only PDFs are rejected with an explicit OCR message | `process_document_background` ~210–216; `extract_pdf_text` ~66–69 |

### Knowledge Base permissions — see §8 for the full matrix

Write operations use `require_workspace_manager` → **manager only, admin receives 403**
("Admins have read-only access to projects and assistants.", `services/auth.py` ~33, 305–312).
Read operations use `require_roles("admin", "manager")`.
Ownership is enforced by `ensure_version_access` / `ensure_document_access`
(`knowledge_routes.py` ~36–68), which restricts managers to `Project.user_id == current_user.id`.

## 3.3 Document processing pipeline

### Text extraction — IMPLEMENTED
`services/document_ingestion.py`
- `extract_document_text(filename, content_type, content, content_encoding)` (~74)
- PDF → `extract_pdf_text` uses **pypdf** `PdfReader`; per-page text is prefixed
  `Page {n}` and pages are joined by blank lines (~56–65). Encrypted PDFs get one
  empty-password `decrypt("")` attempt.
- Missing dependency → `DocumentExtractionError("PDF text extraction dependency is not installed")`.
- No extractable text → explicit error mentioning OCR. **There is no OCR.**
- Non-PDF → base64/data-URL decode when needed, then UTF-8 decode; invalid UTF-8 raises.

### Cleaning / preprocessing — IMPLEMENTED
`services/rag.py`
- `normalize_text` (~44): CRLF→LF, collapse spaces/tabs, collapse 3+ newlines, trim.
- `clean_title` (~51), `section_type_for` (~59) → `epic` | `heading` | `numbered_section` | `section`.
- `embedding_text` (~70): `"{title}\n\n{text}"` when a title exists — **titles are embedded
  with the chunk text**, which is a report-worthy design detail.

### Chunking — IMPLEMENTED, FIXED PARAMETERS
`services/rag.chunk_document(text, max_words=90, overlap=12)` (~162)

1. `split_structured_sections` detects headings with three regexes: `EPIC \d+`,
   markdown `#{1,6}`, numbered `1.2.3` style (~121–148).
2. Sections of ≤ `max_words` become a single chunk.
3. Longer sections → `split_long_section` groups whole paragraphs up to the limit, and only
   falls back to `word_chunks` (sliding window, `step = max_words - overlap`) for oversized
   paragraphs (~76–117).
4. Each chunk carries `title`, `section_type` and `metadata = {"section_index", "part_index"}`.

**Word-based, not token-based. Values are hard-coded defaults** — no API parameter, no UI
control, no environment variable exposes `max_words` or `overlap`.

### Persistence — IMPLEMENTED
Chunks are inserted in `process_document_background`
(`routes/knowledge_routes.py` ~222–239): previous chunks for the document are deleted,
new `Chunk` rows are added with `embedding_status="pending"` and
`embedding_id = f"local-embedding-{document.id}-{index}"`, then `embed_chunks(new_chunks)`
runs, then `sync_document_status` and a single `commit`.

### Embedding generation — IMPLEMENTED
`services/embeddings.py` + `services/rag.py`

| Item | Evidence |
|---|---|
| Provider switch | `EMBEDDING_PROVIDER` (default `ollama`) — `ollama` or `azure_openai` |
| Ollama model | `EMBEDDING_MODEL` default `nomic-embed-text`, `POST /api/embeddings`, `timeout=30` |
| Azure model | `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` (`text-embedding-3-small` in `.env.example`) |
| Batching | `generate_azure_openai_embeddings(values)` sends the whole list in one call (~228); `embed_chunks(batch_size=8)` clamps to 1–32 (`services/rag.py` ~400–409) |
| Batch failure | falls back to per-chunk `embed_chunk` for that batch (~419–423) |
| Retry | `embed_chunk(max_retries=EMBEDDING_MAX_RETRIES=3)`, backoff `min(2**attempt, 4)` s, **only for transient errors** classified by `is_transient_embedding_error` (429 / rate limit / quota / timeout / connection / 5xx vs. 401/403/404/config errors) (~304–397) |
| Dimensions | `expected_embedding_dimensions()` from `EMBEDDING_DIMENSIONS`, else a model→dimension map (`text-embedding-3-small`/`ada-002` = 1536, `3-large` = 3072), else default 1536 |
| Validation | `validate_embedding_vector` raises on dimension mismatch before persisting (`embedding_config.py` ~34–42) |
| Per-chunk logging | `logger.info("knowledge_embedding chunk_id=… operation=embed status=ready retry_count=… latency_ms=…")` (~376–381, 428–434) |

### Processing execution model — PARTIAL (in-process background task)
`ingest_document` returns immediately after `background_tasks.add_task(process_document_background, …)`
(`knowledge_routes.py` ~305–312). This is **FastAPI `BackgroundTasks`**: same process, same
machine, executed after the HTTP response. **There is no Celery, RQ, queue, broker or
external worker.** Consequences worth stating honestly in the report: no retry of the whole
task after a process restart, no concurrency control, no progress percentage.

Progress is observed by **frontend polling**: `documentStatusPoll` (`setInterval`) in
`knowledge-base.component.ts` (~74) re-requesting `GET /versions/{id}/documents`, where
`document_response` recomputes counts on every call.

### Processing states and count divergence — IMPLEMENTED
`chunk_state_counts` (~88–112) returns `{total, ready, failed, pending}`.
`document_response` (~151–178) exposes `chunks_count`, `embeddings_count`,
`failed_embeddings_count`, `pending_embeddings_count`, and a `pages_count` heuristic
(counting `"\n\nPage "` occurrences in `raw_text` for PDFs).

**Chunk count and embedding count legitimately differ** while: chunks exist but are still
`pending`/`processing` (batch loop in progress) → status `processing`; or some chunks are
permanently `failed` → status `partially_ready`. `ready` is only reached when
`ready == total`. Under PostgreSQL, "ready" additionally requires
`embedding_vector IS NOT NULL` (`chunk_has_searchable_embedding` ~80–85).

### Failure and recovery — IMPLEMENTED
- Per-chunk `embedding_status="failed"` + `embedding_error` / `last_error` + `retry_count`.
- Document `failed` / `partially_ready` with explanatory `error_message`.
- Re-running reprocess while `status == "processing"` is a no-op that returns current counts
  (~405–411, 450–457) — a deliberate double-work guard.
- Chunk reprocess never destroys a working index on failure (see table above).
- Partial cleanup on re-processing: old chunks are deleted before new ones are created.

## 3.4 Vector storage and semantic retrieval

### Vector storage — IMPLEMENTED (PostgreSQL + pgvector)
- `models/vector_type.PgVector(UserDefinedType)` renders `VECTOR({dimensions})` and binds
  values through `pgvector_literal` (`[v1,v2,…]`).
- `chunks.embedding_vector` is the searchable column; `chunks.embedding` keeps a **JSON copy**
  of the same vector, used by the non-PostgreSQL code path.
- Migrations: `c1e4f8a7b903_add_chunk_embeddings.py`,
  `f7b8c9d0e1f2_add_pgvector_embedding_column.py`,
  `f6a7b8c9d0e1_add_ingestion_reliability_fields.py`.
  A one-off script exists: `backend/scripts/migrate_local_data_to_pgvector.py`.
- No external vector database (no Pinecone/Qdrant/Weaviate/FAISS).

### Query embedding — IMPLEMENTED
`retrieve_pgvector_chunks` (`services/rag.py` ~505): `generate_embedding(query)` →
`validate_embedding_vector` → `pgvector_literal`, with `query_embedding_ms` measured.

### Similarity search — IMPLEMENTED
```sql
SELECT c.id, 1 - (c.embedding_vector <=> CAST(:query_vector AS vector)) AS similarity
FROM chunks c JOIN documents d ON d.id = c.document_id
WHERE d.knowledge_base_id = :knowledge_base_id
  AND d.status IN ('ready','partially_ready','processed')
  AND c.embedding_status = 'ready'
  AND c.embedding_vector IS NOT NULL
  AND (1 - (c.embedding_vector <=> CAST(:query_vector AS vector))) >= :min_score
ORDER BY c.embedding_vector <=> CAST(:query_vector AS vector)
LIMIT :limit
```
- Operator `<=>` = **cosine distance**; the reported score is **cosine similarity in [0,1]**
  (verified by `backend/tests/test_pgvector_retrieval.py::test_similarity_threshold_semantics_remain_zero_to_one`).
- `limit` = `top_k` clamped 1–10; `min_score` clamped 0–1
  (`retrieve_relevant_chunks_with_mode` ~611–613).
- Ranking = ascending distance; the threshold is applied inside SQL.

Non-PostgreSQL fallback `retrieve_semantic_chunks` (~462–480) is a **hybrid Python score**:
`0.35 × vector_cosine_score + 0.65 × keyword_relevance_score`.
Pure keyword mode uses `keyword_relevance_score` (~245–283): tokenisation with stop-words and
naive suffix stripping, term-count cosine, plus coverage / phrase / heading / specific-term
boosts, capped at 1.0.

Mode strings returned to the caller: `none`, `keyword`, `semantic`, `semantic_error`,
`keyword_fallback`, plus `ai_only` set by `prepare_rag_generation` when
`use_knowledge_base` is false.

### Scope isolation — IMPLEMENTED
Retrieval is filtered by **`knowledge_base_id` only**. Because `KnowledgeBase.version_id` is
unique, this is equivalent to version scoping, and therefore also chatbot- and
project-scoped through the FK chain. Verified by
`test_pgvector_retrieval.py::test_sqlite_compatibility_fallback_enforces_top_k_threshold_and_kb_scope`.

### Retrieved information — IMPLEMENTED
Per selected chunk, retrieval returns `(Chunk, Document, score)`. What is exposed:

| Surface | Fields |
|---|---|
| `POST /versions/{id}/rag-test` (~534–553) | `chunk_id`, `document_id`, `filename`, `order`, `title`, `section_type`, `score`, `embedding_status`, `embedding_model`, `text` |
| RAG `sources` in chat responses (`prepare_rag_generation` ~380–391) | `document_id`, `filename`, `chunk_id`, `title`, `section_type`, `score`, `text` |

**There is no page number field.** Page information only survives as the literal
`Page N` markers inside the extracted text of PDFs.

### Ordered retrieval flow
```
user query
  → normalize_rag_settings(chatbot.rag_settings) + merge_node_rag_settings(node.config)
  → retrieve_relevant_chunks_with_mode(version_id, query, limit, retrieval_mode, min_score)
      → KnowledgeBase lookup by version_id           (none → mode "none", 0 chunks)
      → ready_vector_count()                         (are there usable vectors?)
      → generate_embedding(query) + dimension check
      → pgvector cosine SQL with kb/status/threshold filters, ORDER BY distance, LIMIT k
      → (EmbeddingError/ValueError) → keyword fallback  (or mode "semantic_error")
  → context blocks "[Source i: filename, score=x.xx]"
  → prompt assembly
```

## 3.5 RAG execution

### Flow blocks — IMPLEMENTED
UI-exposed RAG blocks (`pages/flow-builder/flow-builder.component.ts` `blockTypes` ~86–88):
`rag_answer` labelled **"AI Answer"** and `knowledge_search` labelled
**"Knowledge Search"**, both with `status: 'needs-config'`.
`api_request`, `ai_router`, `ai_classifier`, `confidence_check`, `lead_score`, `action` are
`hidden: true` placeholders and must **not** be presented as available AI blocks.

Runtime behaviour (`services/flow_runtime.py`):
- `knowledge_search` with `retrieval_only: true` (~608–658): performs retrieval, stores
  `__knowledge_search_answer`, `__knowledge_search_sources`, `__knowledge_search_mode` in the
  session variables, then continues to the next node. If the next node is `rag_answer` it
  skips its own generation and sets `__knowledge_search_skipped`.
- `rag_answer` and plain `knowledge_search` (~660–755): call the `rag_answer` callback, store
  `__last_ai_answer`, then either loop on themselves (`continue_rag`) or follow the outgoing
  transition; a transition labelled `fallback` / `handoff` / `low_confidence` is taken when
  the user asks for a human (`_requests_human`) or when `mode_used == "fallback"`.

### Exact RAG pipeline with file/function evidence

| Stage | Function | File |
|---|---|---|
| Entry (test/authenticated) | `chat_stream` / `chat` | `routes/chat_routes.py` ~596 / ~527 |
| Entry (public streaming) | `public_chat_stream` | `routes/public_routes.py` ~222 |
| Entry (public non-stream, API) | `run_chatbot_message` | `services/unified_runtime.py` ~225 |
| Flow orchestration | `execute_flow` | `services/flow_runtime.py` ~402 |
| Settings merge | `normalize_rag_settings`, `merge_node_rag_settings` | `services/rag_settings.py`, `chat_routes.py` ~258 |
| Retrieval | `retrieve_relevant_chunks_with_mode` → `retrieve_pgvector_chunks` | `services/rag.py` ~596 / ~505 |
| Prompt build | `prepare_rag_generation` | `chat_routes.py` ~293 |
| Generation (blocking) | `build_rag_response` → `generate_chat_completion` | `chat_routes.py` ~427 → `ai_provider.py` ~293 |
| Generation (streaming) | `stream_ai_answer` → `stream_chat_completion` | `chat_routes.py` ~489 → `ai_provider.py` ~360 |
| Persistence | `add_message`, session `current_node_key`/`variables` | `chat_routes.py` ~201 |
| Observability | `persist_runtime_log` | `services/unified_runtime.py` ~62 |

### Conversation behaviour — IMPLEMENTED
- State: `ConversationSession.current_node_key` + `variables` (JSON), updated after each turn.
- History: `ConversationMessage` rows; `session_history(..., exclude_latest_user_message=…)`.
- Multi-turn is genuinely stateful; internal variables use a `__` prefix
  (`__last_input`, `__last_question`, `__last_ai_answer`, `__feedback`, `__language`,
  `__channel`, `__handoff_collecting`, …) and are filtered out of user-facing views.
- **`continue_rag`** (`_continues_rag`, `flow_runtime.py` ~88–94; accepts
  `continue_rag`, `continue_answering` or `continue_ai_rag`): after answering, the result's
  `current_node_key` is set back to the **same AI node**, so the next user message re-enters
  the same block. This produces the ChatGPT-style behaviour *question → AI/RAG answer →
  question* with **no synthetic "Would you like another question? Yes/No" prompt**.
  New AI blocks are created with `continue_rag: true` by default
  (`flow-builder.component.ts` ~966–985). Caveat: a few shipped FAQ templates still contain
  a `buttons` block with "Ask another question" (`services/templates.py` ~512–518) — that is
  template content, not runtime behaviour.

### Missing-context behaviour — IMPLEMENTED

| Situation | Actual behaviour |
|---|---|
| No KB row for the version | `retrieve_relevant_chunks_with_mode` returns `{"mode": "none", "chunks": []}` → treated as "no chunks" |
| KB with no documents / no ready chunks | 0 chunks → same path |
| Documents not ready | excluded by `d.status IN ('ready','partially_ready','processed')` and `c.embedding_status='ready'` |
| Retrieval returns nothing useful | if `strict_context` → node `fallback` text is returned **without calling the LLM**, `mode_used="fallback"`; else the LLM is called with `"No relevant context was found."` and instructed to answer from general knowledge **and say the answer is not confirmed by the uploaded documents** |
| Query embedding fails | `EmbeddingError`/`ValueError` caught → keyword fallback (`keyword_fallback`); if the mode was forced `semantic` → `semantic_error` with 0 chunks |
| Chunk embedding fails at ingestion | chunk `failed`, document `partially_ready`/`failed`; publication readiness blocks (see §6) |
| LLM fails | `AIProviderError` → HTTP 502 `"LLM service error: …"`; in streaming, an `error` event with the sanitized detail, plus a failed `RuntimeLog` |
| `use_knowledge_base: false` | retrieval skipped entirely, `mode "ai_only"`, pure LLM answer |
| No `LLMConfig` for the version | HTTP 404 `"No config"` / `"Chatbot configuration is missing"` |

`fallback_response` condition, verbatim logic (`chat_routes.py` ~393):
`fallback if (not retrieved_chunks) and strict_context else ""`.

### Source references ("Show source references") — IMPLEMENTED, backend-enforced

- **OFF** → `sources = []` is produced **in the backend** by `prepare_rag_generation`
  (~380–391). Nothing is returned and then hidden; the chunk data never leaves the server.
- Node-level `show_sources` is **ANDed** with the assistant-level setting
  (`merge_node_rag_settings` ~278–280), so a node cannot re-enable sources that the
  assistant disabled.
- **ON** → each source carries `document_id`, `filename`, `chunk_id`, `title`,
  `section_type`, `score`, `text`. No page number, no chunk order index.
- `pages/flow-test` applies an **additional** client-side hide
  (`showSourceReferences()` reads `context().chatbot.rag_settings.show_sources`,
  `flow-test.component.ts` ~249).
- **Public web and widget always receive `sources: []`** regardless of the setting:
  `hide_public_sources()` is applied to every `/public/chat` and `/public/chat/stream`
  payload (`public_routes.py` ~150–151, 189, 338, 372, 443).
- **`/public/api/chat` does NOT strip sources** (`public_routes.py` ~471–485), so
  API-key consumers receive full chunk text including `score` and `filename`.

---

# 4. PART I — ARCHITECTURE AND DIAGRAM EVIDENCE

No images or PlantUML generated. Content only.

## Figure A — Global LLM + RAG architecture
**Type:** architecture / deployment diagram.

Components (corrected against the code):
1. **Angular 20 SPA** — `flow-test`, `knowledge-base`, `versions`, `evaluations`,
   `public-chat`; single HTTP layer `services/api.ts`; cookie-based auth
   (`services/auth.interceptor.ts`).
2. **Embeddable widget** — plain JS served by the backend at `GET /public/widget.js`
   (not part of the Angular bundle).
3. **FastAPI backend** — routers `chat_routes`, `public_routes`, `knowledge_routes`,
   `flow_routes`, `version_routes`, `evaluation_routes`, `channel_routes`, `health_routes`.
4. **Domain services** — `flow_runtime` (orchestration), `rag` (chunking + retrieval),
   `embeddings`, `ai_provider`, `unified_runtime`, `publication_readiness`,
   `evaluation_engine`.
5. **PostgreSQL + pgvector** — relational tables **and** the vector index in the same
   database (`chunks.embedding_vector`). One datastore, no separate vector DB.
6. **External AI provider** — Azure OpenAI (chat deployment + embedding deployment) or a
   local Ollama server. Two distinct capabilities: *chat completion* and *embeddings*.

Arrows: SPA/widget → FastAPI (HTTPS, JSON + NDJSON/SSE streams) → services → PostgreSQL;
services → provider (HTTPS). The provider is called from two places only:
`ai_provider.generate_chat_completion`/`stream_chat_completion` and
`embeddings.generate_embedding(s)`.

## Figure B — Knowledge Base architecture
**Type:** data/class diagram.
`Project 1─N Chatbot 1─N VersionChatbot 1─1 KnowledgeBase 1─N Document 1─N Chunk`,
plus `VersionChatbot 1─1 LLMConfig` and `VersionChatbot 1─1 Flow`.
Annotate the `1─1` cardinalities with the `unique=True` constraints on
`KnowledgeBase.version_id`, `LLMConfig.version_id`, `Flow.version_id`.
Show `Chunk.embedding_vector : VECTOR(1536)` as the searchable attribute and
`Chunk.embedding : JSON` as the compatibility copy.

## Figure C — Document processing pipeline
**Type:** activity diagram (with a swimlane for the background task).
Real steps:
`POST /versions/{id}/documents` → validate filename → SHA-256 → duplicate check (409) →
`Document(status="uploaded")` → **HTTP 202-style immediate response** ┊ background task:
`status="processing"` → `extract_document_text` (pypdf / UTF-8) → `chunk_document`
(structure split → 90-word windows, overlap 12) → delete previous chunks → insert
`Chunk(embedding_status="pending")` → `embed_chunks` (batch 8, retry ≤3, transient-only) →
`sync_document_status` → `ready` / `partially_ready` / `failed`.
Include the decision nodes: extraction error → `failed`; all ready → `ready`;
some failed & none pending → `partially_ready`.
Show the **frontend polling** loop as a separate lane.

## Figure D — Semantic retrieval process
**Type:** process/activity diagram.
`query` → merge assistant + node RAG settings → KB lookup by `version_id` →
`ready_vector_count > 0 ?` → embed query → dimension validation → cosine SQL with
KB/status/threshold filters → top-k by distance → (empty or embedding error) → keyword
fallback → return `(mode, chunks[])`.
Label the branch outcomes with the real mode strings: `semantic`, `keyword`,
`keyword_fallback`, `semantic_error`, `none`, `ai_only`.

## Figure E — RAG generation architecture
**Type:** architecture / component diagram.
`execute_flow` (AI node) → `rag_answer` callback → `prepare_rag_generation`
{retrieval, context blocks, 7-part instruction stack, history, variables} →
`generate_chat_completion` **or** `stream_chat_completion` → response + `sources`
(gated by `show_sources`) → session state update (`current_node_key`, `variables`) →
`ConversationMessage` rows → `RuntimeLog`.
Include the `strict_context` decision that short-circuits to the node `fallback` **without**
calling the LLM, and the `continue_rag` self-loop.

---

# 5. PART I — SEQUENCE DIAGRAM EVIDENCE

## A. Configuring LLM settings
Participants: **Manager**, `VersionsComponent`, `ApiService`, `FastAPI /llm-config`,
`PostgreSQL`.
1. Manager opens the Versions page → `GET /chatbots/{id}/versions`
2. selects a version → `loadLlmConfig` → `GET /llm-config/{version_id}` → `LLMConfig` row
3. `parseSystemPrompt` extracts Tone/Language/Response style from the prompt text
4. Manager edits instructions/temperature → `saveLlmConfig`
5. `buildSystemPrompt()` recomposes the single `system_prompt` string
6. `POST /llm-config` → `require_workspace_manager` → upsert by `version_id` → commit
7. `alt` — admin actor → **403 "Admins have read-only access…"**
8. Note for the diagram: **no ownership check exists on this endpoint** (see §19).

## B. Creating / configuring a Knowledge Base
Participants: **Manager**, `KnowledgeBaseComponent`, `ApiService`,
`FastAPI /versions/{id}/documents` + `/chatbots/{id}/rag-settings`, `PostgreSQL`.
1. `GET /versions/{id}/documents` → `get_or_create_knowledge_base` **implicitly creates the
   KB** if absent → `[]`
2. Manager edits retrieval settings → `PUT /chatbots/{id}/rag-settings` →
   `normalize_rag_settings` clamps `max_chunks` 1–8 and `min_score` 0–1 → persisted on
   **`Chatbot.rag_settings`** (per assistant, not per version)
3. Manager runs the retrieval tester → `POST /versions/{id}/rag-test` → chunk list with scores

## C. Uploading and processing a document
Participants: **Manager**, `KnowledgeBaseComponent`, `ApiService`, `FastAPI knowledge_routes`,
`BackgroundTask`, `EmbeddingProvider`, `PostgreSQL`.
1. `FileReader` reads the file (base64 for PDF) → `POST /versions/{id}/documents`
2. SHA-256 duplicate check → `alt` 409 "This exact document has already been uploaded…"
3. `Document(status="uploaded")` inserted, response returned immediately
4. `background_tasks.add_task(process_document_background, …)`
5. Background: `status="processing"` → `extract_document_text` → `chunk_document` →
   insert pending chunks → `embed_chunks` → provider call(s) → `_mark_chunk_ready`/`_failed`
   → `sync_document_status` → commit
6. Frontend polls `GET /versions/{id}/documents` until `ready` / `partially_ready` / `failed`
7. `alt` extraction error → `status="failed"` + `error_message`
8. `alt` partial embedding failure → `partially_ready`; Manager triggers
   `POST /documents/{id}/embeddings/reprocess`

## D. Generating a RAG response
Participants: **Manager (Test Flow) or public visitor**, chat component,
`FastAPI /chat/stream` (or `/public/chat/stream`), `execute_flow`, `rag` service,
`EmbeddingProvider`, `PostgreSQL(pgvector)`, `LLM provider`.
1. `POST /chat/sessions` → `session_id`
2. `POST /chat/stream {session_id, message}`
3. `execute_flow` resumes at `current_node_key`; reaches the AI node
4. `prepare_rag_generation` → `retrieve_relevant_chunks_with_mode`
5. embed query → cosine SQL → top-k chunks + scores
6. prompt assembly (instructions + history + variables + context + question)
7. `stream_chat_completion` → SSE `token` events
8. `final` event: response, `mode_used`, `retrieval_mode`, `model_used`, `sources`,
   `current_node_key`, `variables`, `latency`
9. `alt` no chunks + `strict_context` → node `fallback`, **LLM not called**, `mode_used="fallback"`
10. `alt` provider failure → `error` event + failed `RuntimeLog`
11. `alt` `continue_rag` → `current_node_key` unchanged → next message re-enters the same node
12. `alt` public web/widget → `hide_public_sources` empties `sources`

## E. Evaluating RAG — IMPLEMENTED, but as deterministic assertions
Participants: **Manager**, `EvaluationsComponent`, `ApiService`,
`FastAPI /evaluations/runs`, `run_dataset_evaluation`, `execute_flow` + `build_rag_response`,
`PostgreSQL`.
1. `POST /evaluations/runs {dataset_id, version_id}` (manager only)
2. `EvaluationRun(status="running")` + `dataset_snapshot`
3. **loop** per enabled case → `execute_evaluation_case` → multi-turn `execute_flow` with a
   real `build_rag_response` → `evaluate_assertions` → `EvaluationCaseResult`
4. aggregate: `passed/warning/failed/critical_failures`, `overall_score`, `duration_ms`,
   `status="completed"`
5. audit `EVALUATION_RUN_COMPLETED`
6. `GET /evaluations/runs/{id}` → run + per-case results
7. `alt` `GET /evaluations/compare` → `regressions`, `overall_score_delta`
8. Note: the run is **synchronous inside the HTTP request**; `judge_result.enabled = false`.

---

# 6. PART I — RAG EVALUATION AND AVAILABLE STATISTICS

## 6.1 What the evaluation system actually is

There **is** a complete Evaluation Center, but it is a **deterministic,
assertion-based regression-testing system**, not an academic RAG-metrics framework.

Models (`backend/models/evaluation.py`): `EvaluationDataset`, `EvaluationCase`,
`EvaluationRun`, `EvaluationCaseResult`, `EvaluationPolicy`.
Engine: `backend/services/evaluation_engine.py`. API: `backend/routes/evaluation_routes.py`.
UI: `frontend/src/app/pages/evaluations/`.

**Assertions actually computed** (`evaluate_assertions`, ~200–425):

| Code | What it checks |
|---|---|
| `RESPONSE_NOT_EMPTY` | the assistant produced non-empty text |
| `REQUIRED_KEYWORDS` | every `expected_keywords` entry appears (case-insensitive substring) |
| `FORBIDDEN_KEYWORDS` | no `forbidden_keywords` entry appears |
| `RESPONSE_MODE` | `mode_used` / `retrieval_mode` equals `expected_response_mode` |
| `REQUIRED_SOURCE_DOCUMENT` | all `expected_source_document_ids` are among the returned sources |
| `SOURCE_PATTERN` | each regex in `expected_source_patterns` matches the concatenated source text |
| `MINIMUM_SOURCE_COUNT` | `len(sources) >= minimum_source_count` |
| `MINIMUM_RETRIEVAL_SCORE` | `max(source.score) >= minimum_retrieval_score` |
| `EXPECTED_FLOW_NODE` / `FORBIDDEN_FLOW_NODE` | visited-node trace contains / avoids given node keys |
| `EXPECTED_FINAL_NODE` | final `current_node_key` matches |
| `VARIABLE_ASSERTION_n` | variable equals a value, or exists |
| `MAXIMUM_LATENCY` | `latency_ms <= maximum_latency_ms` |
| `EXPECTED_FALLBACK` | `mode_used == "fallback"` matches expectation |
| `EXPECTED_HANDOFF` | handoff variables set as expected |
| `EXPECTED_FAILURE_CATEGORY` / `NO_TECHNICAL_FAILURE` | runtime failure category matches / is absent |

**Scoring** (~411–425): `score = round(earned / total_weight * 100, 2)` with all assertion
weights = 1. Case status: `>= 80` → `passed`, `>= 60` → `warning`, else `failed`;
a `critical` case with any failed assertion → `failed`; an unexpected technical failure →
`error`. Run aggregate (~603–618): `overall_score` = mean of case scores where **critical
cases count twice** (`SCORING_POLICY["critical_case_weight"] = 2`).

**Publish gate** (`EvaluationPolicy` + `publication_readiness.evaluation_readiness_check`
~51–143): `required_before_publish`, `required_dataset_id`, `minimum_score` (default 80),
`maximum_failed_cases`, `critical_failures_allowed`, `block_on_regression`,
`maximum_evaluation_age_hours` (default 72). Regression detection uses
`compare_runs` against the currently published version's latest completed run.
Covered by `backend/tests/test_publication_readiness_regression_gate.py`.

**Explicitly NOT implemented:**
LLM-as-judge (`judge_result = {"enabled": False, "message": "LLM-as-judge is disabled by
default for this run.", "prompt_version": "evaluation-judge-v1"}`, ~539–543;
`evaluator_configuration = {"deterministic_only": True, "judge_enabled": False}`, ~586–590),
groundedness, faithfulness, context relevance, answer relevancy, precision, recall, F1,
hit rate, MRR, nDCG, real token accounting, cost accounting, human rating scales.

Execution model: `run_dataset_evaluation` runs **synchronously inside the HTTP request**
(`POST /evaluations/runs`). `status` values: `queued` (model default), `running`,
`completed`, `failed`; `POST /evaluations/runs/{id}/cancel` only acts on `queued`/`running`.

**Report wording:** call this a *deterministic regression evaluation of assistant behaviour
(with retrieval and latency assertions)*, or an *assistant quality gate*. Do **not** call it
"RAG evaluation with groundedness/faithfulness metrics".

## 6.2 Statistics available for the report

### Category A — already calculated and persisted/returned by the application

| Metric | Source | Where |
|---|---|---|
| Documents per KB, chunks per document, ready / failed / pending embeddings | `chunk_state_counts`, `document_response` | `GET /versions/{id}/documents` |
| PDF page estimate | `pages_count` heuristic on `raw_text` | same |
| Document status distribution | `documents.status` | same / readiness |
| KB readiness aggregate (`documents`, `chunks`, `ready_chunks`, `pending_chunks`, `failed_chunks`, `failed_documents`) | `publication_readiness.knowledge_status` | `GET /versions/{id}/readiness` |
| Retrieval similarity scores per chunk | pgvector `1 - (… <=> …)` | `POST /versions/{id}/rag-test`, `sources[]` |
| Retrieval mode used | `retrieval_mode` | chat responses, rag-test |
| Per-request RAG latency breakdown: `retrieval_ms`, `prompt_build_ms`, `prompt_db_query_ms`, `top_k`, `retrieved_chunks`, `context_chars` | `prepare_rag_generation["metrics"]` | `latency` in `/chat` and `/chat/stream` `final` |
| Estimated token counts: `system_prompt_tokens`, `history_tokens`, `rag_context_tokens`, `variables_tokens`, `prompt_tokens_estimated` | `estimated_token_count` | same — **estimates, not provider usage** |
| Streaming latency: `azure_request_ms`, `azure_first_token_from_request_ms` | `ai_provider` metrics dict | `latency.backend` |
| Frontend latency: request preparation, first chunk, first token render, total | `flow-test.component.ts::logLatency` (~307–311) | browser console only |
| Runtime success/failure counts, `response_time_ms`, `rag_used`, `failure_category`, `retrieval_count`, `provider`, `channel` | `RuntimeLog` | `GET /admin/analytics/runtime-logs`, admin dashboards |
| Smoke-test pass/fail + `latency_ms` + trace | `VersionSmokeTest` | `POST /versions/{id}/smoke-test`, readiness |
| Evaluation: `overall_score`, `total/passed/warning/failed/critical_failures`, `duration_ms`, per-case `score` + `latency_ms` + assertion breakdown | `EvaluationRun`, `EvaluationCaseResult` | `GET /evaluations/assistants/{id}/runs`, `/runs/{id}` |
| Run-to-run regression count and `overall_score_delta` | `compare_runs` | `GET /evaluations/compare` |
| Global vector-store health: `total_chunks`, `ready_chunks`, `ready_vector_chunks`, `failed_chunks`, `best_sample_score`, `expected_embedding_dimensions` | `routes/health_routes.rag_health` | `GET /health/rag` |
| LLM reachability + duration | `routes/health_routes.ai_health` | `GET /health/ai` |

### Category B — raw data present; the report would compute the statistic manually

| Candidate statistic | Raw source |
|---|---|
| Mean embedding latency per chunk | log lines `knowledge_embedding … latency_ms=` |
| End-to-end ingestion duration per document | log lines `knowledge_ingestion … latency_ms=` |
| Retrieval latency split (query embedding vs. SQL) | log lines `rag_retrieval … query_embedding_ms= db_ms=` |
| Chunk-size distribution (words/characters per chunk) | `chunks.text` |
| Chunks per document distribution | `documents.chunks_count` |
| Embedding success rate | `chunks.embedding_status` counts |
| Retry statistics | `chunks.retry_count`, `chunks.last_error` |
| Runtime success rate, p50/p95 latency, RAG-usage rate | `runtime_logs` aggregation |
| Score distribution of retrieved chunks | repeated `rag-test` calls on a fixed question set |
| "Answered vs. fallback" rate | `runtime_logs.execution_mode` / `mode_used` values |

### Category C — not available, must not be claimed
Groundedness, faithfulness, context relevance/precision/recall, hallucination rate,
MRR/nDCG/hit-rate, real provider token usage and cost, human-annotated relevance judgements,
A/B comparison of embedding models, index build time as a stored metric.

**Legitimate report strategy:** present a small manual protocol — a fixed question set of
N questions on a known corpus, measured with `POST /versions/{id}/rag-test` (scores,
retrieved chunk count, retrieval mode) plus one `EvaluationRun` over a hand-written dataset —
and report *retrieval score distribution*, *top-1 score*, *assertion pass rate*,
*latency*, and *ingestion throughput*. All of these are directly measurable today.

---

# 7. PART II — VERSIONING, VALIDATION AND PUBLICATION

## 7.1 Version data model — IMPLEMENTED

`backend/models/version.py` — `class VersionChatbot`, table `versions`:
`id`, `version_number`, `status` (comment: `draft / published / archived`), `created_at`,
`published_at`, `archived_at`, `chatbot_id`, `created_by`, `published_by`, `archived_by`,
`duplicated_from_version_id` (self-FK), relationship `llm_config` (1-1).

Serialized to the frontend by `version_routes.serialize_version` (~57–71), which adds
`is_active = (chatbot.active_version_id == version.id)`.

## 7.2 What belongs to a version

| Belongs to the version (1-1 / N) | Does **not** belong to the version |
|---|---|
| `Flow` → `FlowNode`, `FlowTransition` (`Flow.version_id` unique) | `Chatbot.rag_settings` — **per assistant** |
| `LLMConfig` (`version_id` unique) | `ChatbotChannel` rows — **per assistant** |
| `KnowledgeBase` → `Document` → `Chunk` (`version_id` unique) | `Chatbot.public_api_key`, `public_api_enabled` — **per assistant** |
| `ConversationSession.version_id` | `Chatbot.name/description/language/purpose/channel` |
| `EvaluationRun.version_id` | `EvaluationDataset` / `EvaluationCase` / `EvaluationPolicy` — **per assistant** |
| `VersionSmokeTest.version_id` | |

**Report-relevant consequence:** publishing a version freezes the flow, the instructions and
the knowledge base, but **not** the retrieval settings (`max_chunks`, `min_score`,
`show_sources`, `strict_context`, `retrieval_mode`) and **not** the channels or the API key.
Changing RAG settings changes the behaviour of the already-published version immediately.

## 7.3 Version lifecycle — IMPLEMENTED

States present in code: **`draft`**, **`published`**, **`archived`**. No `validated`, no
`pending`, no `deprecated`.

| Transition | Trigger | Guards |
|---|---|---|
| ∅ → `draft` | `POST /versions` (`create_version`) | manager, owns the chatbot |
| ∅ → `draft` | `POST /versions/{id}/duplicate` | manager, owns the source version |
| `draft` → `published` | `PUT /versions/{id}/publish` | no BLOCKED readiness check; warnings need `confirm_warnings=true`; `validate_flow_version` must pass |
| any other version → `archived` | side effect of the same publish call | none — **all other versions are archived, including drafts** |
| `draft`/`published` → `archived` | `PUT /versions/{id}/archive` | cannot archive the active version |
| any → deleted | `DELETE /versions/{id}` | not active, not `published`, not the last remaining version |

Terminal-ish state: `archived` (it can be re-published, since `publish_version` does not
check the current status; the `DRAFT_VERSION_EXISTS` check only downgrades to `WARNING`).

**After publication:** `version.status="published"`, `published_at=now`,
`published_by=user`, `archived_at/by` cleared, `chatbot.active_version_id = version.id`,
every sibling version set to `archived` with `archived_at`/`archived_by`.
**No new draft is created automatically** (verified: `publish_version`
`version_routes.py` ~244–316 contains no version creation).

## 7.4 New version creation — IMPLEMENTED
`create_version` (~136–174):
1. `get_accessible_chatbot` (manager scoped by `Project.user_id`)
2. `version_number = last + 1` (or 1)
3. `VersionChatbot(status="draft", created_by=current_user.id)`
4. `create_default_llm_config` → `LLMConfig(model="llama3", temperature=0.7,
   system_prompt="You are a helpful assistant")`
5. `create_starter_flow(db, version.id, "blank")` → `start` message node + `end` node + one
   `next` transition
6. audit `VERSION_CREATED`

**Nothing is copied from the previous version.** A new version starts empty.

## 7.5 Duplication — IMPLEMENTED, with a gap

Three distinct duplications exist and must not be confused:

| Object | Endpoint / function | What is copied |
|---|---|---|
| **Version** | `POST /versions/{id}/duplicate` → `duplicate_version` (~176–204) | `LLMConfig` (`copy_llm_config`) + `Flow` with all nodes and transitions (`copy_flow`, deep-copied `config`); sets `duplicated_from_version_id`; status `draft`. **Knowledge base, documents and chunks are NOT copied.** |
| **Project** | `duplicate_project` (`routes/project_routes.py` ~1194 audit) | project metadata only — verified by `test_project_isolation.py::test_duplicate_project_copies_only_safe_project_metadata` |
| **Flow → template** | `POST /flows/{id}/template-library` (Chapter 5) | flow structure into the reusable template library |

There is **no chatbot duplication endpoint**.

**Report-critical gap:** duplicating a version produces a draft whose knowledge base is
empty, so a `rag_answer` node with `use_knowledge_base: true` will be **BLOCKED** by the
`KNOWLEDGE_INDEXED` readiness check until documents are re-uploaded to the new version.

## 7.6 Editing a published version — NOT PROTECTED

- `flow_routes` node/transition CRUD (`create_node`, `update_node`, `delete_node`,
  `create_transition`, `update_transition`, `delete_transition`) check **access only**, never
  `version.status`.
- `POST /llm-config` upserts by `version_id` with **no status check**.
- `knowledge_routes` upload/delete/reprocess have **no status check**.
- `PUT /chatbots/{id}/rag-settings` has no version notion at all.

⇒ **A published, live version can be modified in place.** The frontend mitigates this only
partially: `pages/flow-builder` targets the latest **draft** version
(`get_chatbot_builder` prefers `status == "draft"`), and the knowledge/flow routes are
`roleGuard roles: ['manager']`. But the Versions page lets a manager select **any** version
and save LLM instructions and upload documents against it.

## 7.7 Rollback / restore — NOT IMPLEMENTED

- No `unpublish`, `rollback`, `restore-version` or `activate-version` endpoint exists
  (verified by a repository-wide search for `unpublish|rollback|restore`; the only `restore`
  endpoints are `PUT /projects/{id}/restore` and
  `POST /evaluations/datasets/{id}/restore`).
- `rollback_available` in `GET /chatbots/{id}/operations-dashboard` (~920) and in the
  workspace release state (`project_routes.py` ~1113) is computed as
  `len(published_versions) > 1`. Since `publish_version` archives every other version, there
  is normally **at most one** published version, so the UI card in
  `pages/project-overview` ("Rollback: Available / Unavailable") will essentially always show
  *Unavailable*. **This is a label, not a feature.**
- The only real way back to a previous behaviour is the manual sequence:
  *duplicate the old version → it becomes a new draft → validate → publish*, which produces a
  **new version number**. Describe it as **"republication d'une version antérieure par
  duplication"**, never as "rollback".

## 7.8 Archive / delete — IMPLEMENTED

- `PUT /versions/{id}/archive`: blocked with 400 if the version is the active one
  ("Cannot archive the active version. Publish another version first.").
- `DELETE /versions/{id}`: blocked if active or `published`; blocked if it is the last
  version ("Cannot delete the last version of a chatbot."). Cascade performed manually:
  conversation messages + sessions, flow transitions + nodes + flow, `LLMConfig`,
  `KnowledgeBase` + documents + chunks; `duplicated_from_version_id` references are nulled.
- Chatbot-level: `PUT /chatbots/{id}/status` (activate/deactivate → gates public access) and
  `DELETE /chatbots/{id}`. Project-level archive/restore/soft-delete exist in
  `project_routes`.
- **Neither archive nor delete is audited** (no `record_audit_log` in `archive_version` /
  `delete_version`) — see §20.

## 7.9 Validation before publication

### A. Flow validation (Chapter 5, confirmed only as far as Chapter 6 needs it)
`services/flow_validation.validate_flow_version(db, version_id)` returns
`{valid, errors[], validation_errors[]}`. Used by Chapter 6 in two places:
`readiness_report` (check `FLOW_VALID`) and `publish_version` (a second, independent call
that returns 400 with the error list).

### B. Publication readiness — IMPLEMENTED
`services/publication_readiness.readiness_report(db, version, chatbot)` (~215–374).
Each item: `{code, label, status ∈ {PASSED, WARNING, BLOCKED}, message, related_action, metadata}`.
`can_publish = (blocked == 0)`; `requires_confirmation = (warnings > 0)`.

| Code | Rule | Severity |
|---|---|---|
| `DRAFT_VERSION_EXISTS` | selected version is a draft | WARNING if not |
| `INSTRUCTIONS_CONFIGURED` | `LLMConfig.system_prompt` non-empty | **BLOCKED** |
| `FLOW_VALID` | `validate_flow_version().valid` | **BLOCKED** |
| `BLOCK_CONFIGURATION_COMPLETE` | *same* `validation.valid` value | **BLOCKED** (duplicate signal) |
| `KNOWLEDGE_INDEXED` | only if `version_requires_knowledge(nodes)`: failed docs/chunks → BLOCKED; pending chunks → BLOCKED; `ready_chunks > 0` → PASSED; otherwise BLOCKED | **BLOCKED** / PASSED |
| `RETRIEVAL_CONFIGURATION_VALID` | added only when knowledge is required and **hard-coded to PASSED** — no actual verification | PASSED (cosmetic) |
| `PUBLIC_CHANNEL_VALID` | if `public_api_enabled` or an active channel row exists → requires `chatbot.public_api_key`; otherwise WARNING "No active public channel is configured." | **BLOCKED** / WARNING |
| `RUNTIME_SMOKE_TEST` | latest `VersionSmokeTest`: passed & < 24 h → PASSED; passed & older → WARNING; failed → **BLOCKED**; none → WARNING | mixed |
| `EVALUATION_REQUIRED` | only when `EvaluationPolicy.required_before_publish` — missing run, score/failed/critical thresholds, regression vs. published baseline → BLOCKED; stale run → WARNING | **BLOCKED** / WARNING / PASSED |
| `FALLBACK_MESSAGE_CONFIGURED` | AI/RAG nodes exist but none has a `fallback` | WARNING |

`node_requires_knowledge` (~171–177): `knowledge_search` with `retrieval_only` or
`use_knowledge_base` (default true), or `rag_answer` with `use_knowledge_base` (default true).

**Runtime smoke test** — `run_version_smoke_test` (~377–470): executes up to 3 real turns
through `execute_flow` with a real `build_rag_response`, stops as soon as a RAG mode is
reached, records `VersionSmokeTest{status, failure_category, latency_ms, trace, message}`.
This is genuine end-to-end verification, not a mock. Endpoint:
`POST /versions/{id}/smoke-test` (manager only).

Checks that are **not** implemented: channel-specific field validation, allowed-origin
verification, knowledge freshness, prompt-length limits, cost estimation.

### C. Validation UI — IMPLEMENTED
- `pages/versions/versions.component.ts`: `loadReadiness` / `getVersionReadiness` (~132, ~344),
  `runVersionSmokeTest` (~363), `publishVersion(versionId, confirmWarnings)` (~165).
- `pages/evaluations/evaluations.component.ts` also surfaces readiness and can publish
  (`getVersionReadiness` ~819/~837, `publishVersion` ~869) — the evaluation gate and the
  publish action are deliberately co-located.
- The readiness payload's `related_action` field (`versions`, `instructions`, `flow`,
  `knowledge`, `rag-settings`, `deployment`, `smoke-test`, `evaluations`) is the
  navigate-to-fix mechanism.

## 7.10 Publication process — IMPLEMENTED

`PUT /versions/{version_id}/publish?confirm_warnings=<bool>` — `version_routes.publish_version`:

1. `require_workspace_manager` → **manager only** (admin 403)
2. `get_accessible_version` + `get_accessible_chatbot` → ownership
3. `readiness_report(...)`
4. any `BLOCKED` → **400** `{message: "Resolve blocked readiness checks before publishing.", readiness}`
5. any `WARNING` and `confirm_warnings` false → **409** `{message: "Confirm readiness warnings before publishing.", readiness}`
6. `validate_flow_version` → if invalid, **400** with `errors`
7. all sibling versions → `archived` + `archived_at` + `archived_by`
8. this version → `published`, `published_at = now`, `published_by = user`, `archived_*` cleared
9. `chatbot.active_version_id = version.id`
10. commit
11. audit `VERSION_PUBLISHED` (`resource_type="version"`, `resource_name="v{n}"`,
    `metadata={"chatbot_id": …}`)
12. response `{message: "Version published", version: serialize_version(...)}`

Not reversible in one action; no unpublish; no automatic follow-up draft.
Channel rows are **not** touched by publication — `deployed_version_id` is never updated here.

## 7.11 Publication channels

`SUPPORTED_CHANNELS = {"web", "widget", "api"}`, `CHANNEL_ORDER = ("web", "widget", "api")`
(`routes/channel_routes.py` ~18–19). `backend/tests/test_channel_removal.py` asserts that
Meta/WhatsApp/Messenger routes are **not** registered and that only these three types are
accepted. No other channel exists.

| Channel | Backend runtime | Public endpoint | Identifier / security | Origin restriction | Version resolution | Classification |
|---|---|---|---|---|---|---|
| **web** (hosted public chat) | `public_chat_stream`, `public_chat` | `POST /public/chat/stream`, `POST /public/chat`, `POST /public/chat/sessions`, `GET /public/chatbots/{id}`, `POST /public/chat/feedback` | numeric `chatbot_id`, **no token**, anonymous | global CORS allow-list only | `active_version_id` then latest `published` | **IMPLEMENTED** |
| **widget** | same endpoints, `channel: "widget"` | `GET /public/widget.js` serves a self-contained script | `data-chatbot-id` attribute | global CORS allow-list only | same | **IMPLEMENTED** |
| **api** (REST) | `run_chatbot_message` | `POST /public/api/chat`, `POST /public/api/chat/sessions` | `x-chatbot-api-key` header must equal `chatbot.public_api_key`, and `public_api_enabled` must be true | n/a (server-to-server) | same | **IMPLEMENTED** |
| **`ChatbotChannel` records** | **never read by any runtime path** | `GET/POST/PUT/DELETE /chatbots/{id}/channels…` | manager only for writes | — | `deployed_version_id` stored, never used | **CONFIG-ONLY** |

Evidence that channel rows are decorative:
- `serialize_channel` returns `status = "connected"` when no row exists (~115), and
  `channelStatus()` in the frontend defaults the three known types to `connected` (~146).
- `test_chatbot_channel` always returns `{"configured": True, "missing_fields": []}` (~269–272)
  and logs a `test_connection` success event — it validates nothing.
- `public_routes` / `unified_runtime` never query `ChatbotChannel`; `get_active_version` uses
  `chatbot.active_version_id` only. A channel marked `disabled` still answers.
- `readiness_report` reads channel rows only to decide whether to require a
  `public_api_key`.
- The deployment page (`pages/chatbot-deployment`) calls only
  `getChatbotChannels`, `testChatbotChannel`, `regenerateChatbotApiKey` — **no create,
  update or delete** — so the CRUD endpoints have no UI caller.

## 7.12 Public chatbot access — IMPLEMENTED

Flow:
```
public visitor
  → /public-chat/{chatbotId}  (Angular, unauthenticated route)  or widget script  or REST API
  → GET /public/chatbots/{id}            get_public_chatbot: 404 if missing or is_active == false
  → get_active_version()                 published only, else 404 "Chatbot has no published version"
  → POST /public/chat/sessions           anonymous ConversationSession (user_id NULL)
  → POST /public/chat/stream             execute_flow + prepare_rag_generation + stream_ai_answer
  → LLM / RAG when the flow reaches an AI node
  → NDJSON stream: start / token / final     (sources always emptied)
  → persist_runtime_log(source="public_stream")
```

| Property | Finding |
|---|---|
| Public identifier | **numeric `chatbot_id`** — no slug, no UUID, no signed token (`app.routes.ts` ~265) |
| Anonymous access | yes for web/widget; `ConversationSession.user_id = NULL` |
| Authentication | only the REST channel (`x-chatbot-api-key`) |
| Session identifier | sequential integer; re-accepted from the client, filtered only by `chatbot_id` and `user_id IS NULL` (`get_or_create_public_session` ~124–128) → **another visitor could resume someone else's session by guessing the id** |
| Rate limiting | **none** on public endpoints (rate limiting exists only in `routes/auth_routes.py`, tested by `test_auth_rate_limiting.py`) |
| CORS / origin | global `ALLOWED_ORIGINS` from `main.py::allowed_origins()`; wildcard rejected. There is **no per-assistant allowed-domain list**, so a widget hosted on a customer domain requires that domain in the server-wide allow-list (behaviour would need runtime confirmation) |
| Disabled assistant | `is_active == false` → 404 "Chatbot is not available" |
| No published version | 404 "Chatbot has no published version" |
| Archived version | never selected — the query filters `status == "published"` |
| **Draft protection** | **CONFIRMED SAFE.** Both `public_routes.get_active_version` (~74–92) and `unified_runtime.get_active_version` (~111–151) filter `VersionChatbot.status == "published"` in every branch. A draft version is unreachable through any public route. Draft preview requires an authenticated admin/manager and an explicit `version_id` (`chat_routes.get_chat_version` ~54–79, which raises 403 "Version preview is not allowed" for other roles). |
| Feedback | `POST /public/chat/feedback` writes `__feedback` into the session variables; consumed by the RAG prompt ("silently retry … with a clearer answer") |
| Debug output | `unified_runtime` contains `print(...)` statements (~117–118, 137–140, 148–150, 301) that echo chatbot/version/response to stdout — noisy, and it prints response text |

---

# 8. PART II — LIFECYCLE / ARCHITECTURE / DIAGRAM EVIDENCE

## A. Version lifecycle — **state diagram** (recommended)
- Initial: `[*] → draft` via `POST /versions` or `POST /versions/{id}/duplicate`
- `draft → published` via `PUT /versions/{id}/publish`
  guards: `readiness.blocked == 0`; `warnings == 0 or confirm_warnings`; `flow.valid`
- Effect on transition: `published_at`, `published_by`, `chatbot.active_version_id`,
  **and `archived` for every sibling version**
- `draft | published → archived` via `PUT /versions/{id}/archive`
  guard: `chatbot.active_version_id != version.id`
- `archived → published` is technically reachable (publish does not check the source status)
- `draft | archived → [*]` via `DELETE /versions/{id}`
  guards: not active, not `published`, not the last version
- Annotate explicitly on the diagram: **no automatic new draft after publication**,
  **no unpublish transition**, **no rollback transition**

## B. Publication validation workflow — **activity diagram**
`GET /versions/{id}/readiness` → build 9–11 checks → classify
BLOCKED / WARNING / PASSED → `can_publish` / `requires_confirmation` →
Manager fixes via `related_action` links → `PUT …/publish` → 400 (blocked) /
409 (unconfirmed warnings) / 200. Include the second, independent `validate_flow_version`
call inside publish as a distinct decision node.

## C. Publication process — **sequence diagram** (see §9.D)

## D. Public access architecture — **architecture diagram**
Three entry surfaces (Angular public page, third-party site + `widget.js`, external
server + API key) → FastAPI `public_router` → `get_public_chatbot` /
`get_active_version` → `execute_flow` → `prepare_rag_generation` → LLM/embedding provider
→ PostgreSQL(+pgvector) → `RuntimeLog`.
Mark `ChatbotChannel` **outside** the runtime path, connected only to the deployment UI and
to `readiness_report`, with the note "descriptive metadata".

## E. Public chatbot execution flow — **activity or sequence diagram** (see §9.E)

---

# 9. PART II — SEQUENCE DIAGRAM EVIDENCE

## A. Creating a new version
**Manager** → `VersionsComponent` → `ApiService` → `POST /versions` → `create_version` →
PostgreSQL.
Steps: ownership check → `version_number = last + 1` → insert `draft` →
`create_default_llm_config` → `create_starter_flow("blank")` → `record_audit_log(VERSION_CREATED)`
→ `serialize_version`. `alt` admin → 403.

## B. Duplicating a version
**Manager** → `VersionsComponent` → `POST /versions/{id}/duplicate` → `duplicate_version` →
`copy_llm_config` → `copy_flow` (nodes + transitions) → PostgreSQL.
Add an explicit note: **knowledge base not copied** → the new draft will be BLOCKED on
`KNOWLEDGE_INDEXED` if it contains a KB-dependent AI node.
(There is no rollback sequence to draw — see §7.7.)

## C. Validating a version before publication
**Manager** → `VersionsComponent` → `GET /versions/{id}/readiness` → `readiness_report` →
`validate_flow_version`, `knowledge_status`, `latest_smoke`, `ChatbotChannel` query,
`evaluation_readiness_check` → checks + summary.
Optional preceding step: `POST /versions/{id}/smoke-test` → `run_version_smoke_test` →
real `execute_flow` + `build_rag_response` → `VersionSmokeTest` row.
`alt` BLOCKED → publish button disabled; `alt` WARNING → confirmation required.

## D. Publishing a version
**Manager** → `VersionsComponent` (or `EvaluationsComponent`) → `ApiService` →
`PUT /versions/{id}/publish?confirm_warnings=` → `publish_version` → `readiness_report` →
`validate_flow_version` → PostgreSQL (archive siblings, publish target, set
`chatbot.active_version_id`) → `record_audit_log(VERSION_PUBLISHED)` → response.
`alt` blocked → 400 with readiness payload; `alt` unconfirmed warnings → 409;
`alt` invalid flow → 400 with error list.
Note on the diagram: **all sibling versions become `archived`**, and no draft is created.

## E. Accessing / interacting with a published assistant
**Public visitor** → `PublicChatComponent` (or `widget.js`) → `GET /public/chatbots/{id}` →
`POST /public/chat/sessions` → `POST /public/chat/stream` → `execute_flow` →
(`rag_answer` → `prepare_rag_generation` → retrieval → `stream_ai_answer`) →
NDJSON `start`/`token`/`final` → `ConversationMessage` rows → `persist_runtime_log`.
`alt` inactive assistant → 404; `alt` no published version → 404;
`alt` provider error → `error` event + failed `RuntimeLog`;
note: **`sources` always emptied by `hide_public_sources`**.

---

# 10. COMPLETE ROLE AND PERMISSION MATRIX

Reference: `services/auth.py`
- `require_roles(*roles)` — role membership only (~294–302)
- `ensure_workspace_write_access` — **`role != "manager"` → 403** "Admins have read-only
  access to projects and assistants." (~305–308)
- `require_workspace_manager = require_roles("admin","manager") + ensure_workspace_write_access`
  (~311–312) ⇒ **effectively manager-only**
- Ownership pattern: `if current_user.role == "manager": join Project on Project.user_id == current_user.id`

| Operation | Manager | Admin | Public | Ownership / scope | Backend enforcement |
|---|---|---|---|---|---|
| LLM config read `GET /llm-config/{version_id}` | ✅ | ✅ | ❌ | **NONE** ⚠ | `require_roles("admin","manager")` only |
| LLM config write `POST /llm-config` | ✅ | ❌ 403 | ❌ | **NONE** ⚠ | `require_workspace_manager`, no version check |
| RAG settings read `GET /chatbots/{id}/rag-settings` | ✅ own | ✅ all | ❌ | `get_accessible_chatbot` | `require_roles` |
| RAG settings write `PUT /chatbots/{id}/rag-settings` | ✅ own | ❌ 403 | ❌ | `get_accessible_chatbot` | `require_workspace_manager` |
| KB implicit create (via first read/upload) | ✅ own | read path does **not** create for admin | ❌ | `ensure_version_access` | `get_or_create_knowledge_base` only when `role == "manager"` |
| KB rename / delete | — | — | — | — | **no endpoint** |
| Document upload `POST /versions/{id}/documents` | ✅ own | ❌ 403 | ❌ | `ensure_version_access` | `require_workspace_manager` |
| Document list / read / chunks | ✅ own | ✅ all | ❌ | `ensure_version_access` / `ensure_document_access` | `require_roles` |
| Document rename `PUT /documents/{id}` | ✅ own | ❌ 403 | ❌ | `ensure_document_access` | `require_workspace_manager` |
| Document delete | ✅ own | ❌ 403 | ❌ | `ensure_document_access` | `require_workspace_manager` |
| Embedding reprocess / chunk reprocess | ✅ own | ❌ 403 | ❌ | `ensure_document_access` | `require_workspace_manager` |
| Retrieval test `POST /versions/{id}/rag-test` | ✅ own | ✅ all | ❌ | `ensure_version_access` | `require_roles` |
| Semantic retrieval at runtime | — | — | ✅ implicit | version-scoped KB | no role check (runtime path) |
| Evaluation dataset/case/run/policy **write** | ✅ own | ❌ 403 | ❌ | `get_accessible_dataset` / `_chatbot` / `_version` | `require_workspace_manager` |
| Evaluation read / export / compare / policy read | ✅ own | ✅ all | ❌ | same helpers | `require_roles` |
| Version list `GET /chatbots/{id}/versions` | ✅ own | ✅ all | ❌ | `get_accessible_chatbot` | `require_roles` |
| Version readiness `GET /versions/{id}/readiness` | ✅ own | ✅ all | ❌ | `get_accessible_version` | `require_roles` |
| Version create | ✅ own | ❌ 403 | ❌ | `get_accessible_chatbot` | `require_workspace_manager` |
| Version duplicate | ✅ own | ❌ 403 | ❌ | `get_accessible_version` | `require_workspace_manager` |
| Smoke test | ✅ own | ❌ 403 | ❌ | `get_accessible_version` | `require_workspace_manager` |
| Publish | ✅ own | ❌ 403 | ❌ | `get_accessible_version` | `require_workspace_manager` |
| Unpublish | — | — | — | — | **no endpoint** |
| Version archive / delete | ✅ own | ❌ 403 | ❌ | `get_accessible_version` | `require_workspace_manager` |
| Channel list | ✅ own | ✅ all | ❌ | `get_accessible_chatbot` | `require_roles` |
| Channel create / update / test / clear-error / delete | ✅ own | ❌ 403 | ❌ | `get_accessible_chatbot` | `require_workspace_manager` |
| Public API key regenerate | ✅ own | ❌ 403 | ❌ | `get_accessible_chatbot` | `require_workspace_manager` |
| **Flow node / transition CRUD** | ✅ own | **✅ (inconsistent)** | ❌ | `ensure_flow_access` | `require_roles("admin","manager")` — **no write gate** ⚠ |
| Public chatbot metadata / session / chat / stream / feedback | ✅ | ✅ | ✅ | published version only | none (anonymous) |
| Public REST API chat | ✅ | ✅ | ✅ with key | `public_api_key` + `public_api_enabled` | `get_api_chatbot` |
| Admin analytics / runtime logs / audit logs / system health | ❌ | ✅ | ❌ | global | `require_roles("admin")` |

**Admin has global scope** on every read path listed above and on all `/admin/analytics/*`
endpoints. **Manager is owner-scoped** on every workspace resource, via
`Project.user_id == current_user.id`.

**Admin-only routes:** `routes/admin_analytics_routes.py` (overview, platform, usage,
channels, top-chatbots, chatbots, recent-activity, audit-logs, system-health, runtime-logs,
sessions), plus `routes/platform_settings_routes.py` writes.
**Manager-only routes:** everything behind `require_workspace_manager`, and the Angular
routes guarded by `roles: ['manager']` (`knowledge`, `deployment`, `settings`, `flow`,
`flow/test`, `templates`, `ai-generator`, evaluation case editors).
**Both roles:** version list/readiness, document/chunk reads, rag-test, evaluation reads,
channel list, chatbot reads, `/chat` and `/chat/stream` with an explicit `version_id`.

**Inconsistencies / gaps (see also §19):**
1. `flow_routes` write endpoints accept admin, contradicting the workspace read-only policy
   enforced everywhere else. `test_workspace_read_only_permissions.py` covers project,
   assistant, sub-resource and evaluation writes — **flow routes are not in that list**.
2. `/llm-config` (both verbs) performs **no ownership check**: manager A can read and
   overwrite the LLM configuration of manager B's version by numeric id. Not covered by
   `test_project_isolation.py` (which covers flow resources).
3. Admin can read documents but `GET /versions/{id}/documents` only auto-creates the KB for
   managers, so an admin may get `[]` where a manager triggers creation — a subtle asymmetry.
4. Anonymous session resumption is filtered only by `chatbot_id` + `user_id IS NULL`.

---

# 11. AUDIT AND RUNTIME LOGGING RELEVANT TO CHAPTER 6

## Audit log (`models/audit_log.py`, `services/audit.record_audit_log`)
Stored per event: `actor_user_id/name/email/role`, `action`, `resource_type`, `resource_id`,
`resource_name`, `status`, `metadata_json` (sanitized by `safe_metadata`, which drops
`password`, `api_key`, `public_api_key`, tokens, secrets), `created_at`.
Failures are swallowed and logged (`except Exception: db.rollback()`), so auditing never
breaks the business operation.

Chapter 6-relevant actions actually emitted:

| Action | Emitted in | Actor |
|---|---|---|
| `DOCUMENT_UPLOADED` | `knowledge_routes.ingest_document` (~317) — metadata `version_id`, `content_type`, `size_bytes` | manager |
| `DOCUMENT_DELETED` | `knowledge_routes.delete_document` (~573) | manager |
| `KNOWLEDGE_BASE_UPDATED` | `knowledge_routes.update_document` (~378) — document rename | manager |
| `VERSION_CREATED` | `version_routes.create_version` (~166) — metadata `chatbot_id` | manager |
| `VERSION_PUBLISHED` | `version_routes.publish_version` (~308) — metadata `chatbot_id` | manager |
| `CHANNEL_ENABLED` / `CHANNEL_DISABLED` | `channel_routes` create/update/delete | manager |
| `CHATBOT_DEPLOYED` | `channel_routes.update_chatbot_channel` when `deployed_version_id` changes (~227) | manager |
| `EVALUATION_DATASET_CREATED/UPDATED/ARCHIVED/RESTORED/DELETED` | `evaluation_routes` | manager |
| `EVALUATION_CASE_CREATED/UPDATED/DELETED` | `evaluation_routes` | manager |
| `EVALUATION_RUN_COMPLETED` (metadata `status`, `score`), `EVALUATION_RUN_CANCELLED` | `evaluation_routes` | manager |
| `EVALUATION_POLICY_CHANGED` (metadata = full policy payload) | `evaluation_routes.update_policy` | manager |

**Not audited** (verified absence of `record_audit_log`): version **duplicate**, version
**archive**, version **delete**, LLM config save, RAG settings update, document
reprocessing, smoke-test execution, public API key regeneration.

## Runtime log (`models/runtime_log.py`, `unified_runtime.persist_runtime_log`)
Per public/channel execution: `chatbot_id`, `version_id`, `conversation_id`, `project_id`,
`user_id`, `channel`, `execution_id` (uuid4), `execution_mode` (= `mode_used`), `status`
(`success`/`failed`), `rag_used`, `response_time_ms`, `failure_category`, `current_block`,
`retrieval_count`, `provider`, `error_type`, `error_message` (sanitized by
`SENSITIVE_PATTERNS` — API keys, DB URLs, bearer tokens), `source`
(`public_stream` | `unified_runtime`), `created_at`, `completed_at`.
Consumed by `GET /admin/analytics/runtime-logs` and the admin dashboards; covered by
`backend/tests/test_runtime_logs.py`.

**Note:** the authenticated `/chat` and `/chat/stream` paths do **not** write `RuntimeLog`
rows — only public/channel executions and the unified runtime do. Statistics drawn from
`runtime_logs` therefore describe **public traffic**, not manager testing.

Application-level structured log lines usable as evidence:
`knowledge_ingestion …`, `knowledge_embedding …`, `rag_retrieval operation=pgvector …`,
plus the Azure failure logs in `ai_provider`/`embeddings`.

---

# 12. DATABASE MODEL INVENTORY (Chapter 6 only)

| Model | File | Purpose | Important fields | Relationships | Used by |
|---|---|---|---|---|---|
| `Chatbot` | `models/chatbot.py` | Assistant; owns publication state | `is_active`, `active_version_id`, `public_api_key`, `public_api_enabled`, `rag_settings` (JSON), `language`, `project_id` | N-1 `Project`; FK → active `VersionChatbot` | publication, public access, RAG settings |
| `VersionChatbot` | `models/version.py` | Version lifecycle | `version_number`, `status`, `created_at`, `published_at`, `archived_at`, `created_by`, `published_by`, `archived_by`, `duplicated_from_version_id` | N-1 `Chatbot`; 1-1 `LLMConfig`/`Flow`/`KnowledgeBase` | H, I, J, L |
| `LLMConfig` | `models/llm_config.py` | Generation configuration | `version_id` (unique), `model`, `temperature`, `system_prompt` | 1-1 `VersionChatbot` | A, F |
| `KnowledgeBase` | `models/knowledge_base.py` | Version knowledge container | `name`, `version_id` (unique) | 1-N `Document` | B, E |
| `Document` | `models/document.py` | Uploaded source | `filename`, `content_type`, `storage_url`, `raw_text`, `content_hash`, `size_bytes`, `status`, `error_message`, `processed_at`, `chunks_count` | N-1 `KnowledgeBase`; 1-N `Chunk` | B, C |
| `Chunk` | `models/chunk.py` | Indexed passage + vector | `order`, `title`, `section_type`, `metadata_json`, `text`, `embedding` (JSON), `embedding_vector` (`VECTOR`), `embedding_model`, `embedding_status`, `embedding_dimensions`, `retry_count`, `embedded_at` | N-1 `Document` | C, D, E |
| `Flow`, `FlowNode`, `FlowTransition` | `models/flow.py` | Orchestration graph (Chapter 5) | `node_key`, `type`, `config` | 1-1 `VersionChatbot` | F, I |
| `ConversationSession` | `models/conversation.py` | Runtime state | `current_node_key`, `variables` (JSON), `user_id` (NULL = anonymous) | N-1 `Chatbot`/`VersionChatbot`; 1-N `ConversationMessage` | F, L |
| `ConversationMessage` | `models/conversation.py` | Transcript | `role`, `content`, `options`, `sources` | N-1 session | F, statistics |
| `ChatbotChannel` | `models/chatbot_channel.py` | Channel metadata (**not runtime**) | `channel_type`, `status`, `config_json`, `deployed_version_id`, `last_tested_at`, `last_error` | N-1 `Chatbot` | K, readiness |
| `ChannelLog` | `models/chatbot_channel.py` | Channel event trail | `event_type`, `message`, `status` | N-1 `Chatbot` | K |
| `VersionSmokeTest` | `models/version_smoke_test.py` | Pre-publish runtime proof | `status`, `failure_category`, `latency_ms`, `trace`, `message`, `tested_by` | N-1 `VersionChatbot` | I |
| `EvaluationDataset` | `models/evaluation.py` | Test dataset (per assistant) | `name`, `status` | 1-N `EvaluationCase` | G |
| `EvaluationCase` | `models/evaluation.py` | One test case | `input_message`, `turns`, `expected_*`, `forbidden_*`, `minimum_*`, `critical`, `enabled` | N-1 dataset | G |
| `EvaluationRun` | `models/evaluation.py` | One execution | `status`, `total/passed/warning/failed/critical_failures`, `overall_score`, `duration_ms`, `dataset_snapshot`, `evaluator_configuration` | N-1 assistant/dataset/version; 1-N results | G, I |
| `EvaluationCaseResult` | `models/evaluation.py` | Per-case outcome | `status`, `score`, `actual_response`, `actual_sources`, `actual_visited_nodes`, `latency_ms`, `assertion_results`, `judge_result` | N-1 run | G |
| `EvaluationPolicy` | `models/evaluation.py` | Publish gate | `required_before_publish`, `required_dataset_id`, `minimum_score`, `maximum_failed_cases`, `critical_failures_allowed`, `block_on_regression`, `maximum_evaluation_age_hours` | 1-1 assistant | I, J |
| `RuntimeLog` | `models/runtime_log.py` | Execution telemetry | `channel`, `status`, `rag_used`, `response_time_ms`, `failure_category`, `retrieval_count`, `provider` | FKs to chatbot/version/session/project | M, statistics |
| `AuditLog` | `models/audit_log.py` | Traceability | `action`, `resource_type/id/name`, `actor_*`, `metadata_json` | — | M |

**Relationships worth drawing** for a class/data figure:
`Project 1─N Chatbot`; `Chatbot 1─N VersionChatbot`; `Chatbot ─1 active VersionChatbot`
(dashed, "active_version_id"); `VersionChatbot 1─1 {Flow, LLMConfig, KnowledgeBase}`;
`KnowledgeBase 1─N Document 1─N Chunk`; `Chatbot 1─N ChatbotChannel` (annotate
"descriptive"); `EvaluationDataset/Policy → Chatbot` and `EvaluationRun → VersionChatbot`.

---

# 13. API ENDPOINT INVENTORY

Role column: **M** = manager, **A** = admin, **P** = public/anonymous.

## LLM
| Method | Route | File | Handler | Role | Ownership | Purpose | Frontend caller | Status |
|---|---|---|---|---|---|---|---|---|
| POST | `/llm-config` | `llm_config_routes.py` | `create_or_update_config` | M | **none ⚠** | upsert model/temperature/system prompt | `versions.component.saveLlmConfig` | IMPLEMENTED |
| GET | `/llm-config/{version_id}` | `llm_config_routes.py` | `get_config` | M, A | **none ⚠** | read config | `versions.component.loadLlmConfig` | IMPLEMENTED |
| GET | `/health/ai` | `health_routes.py` | `ai_health` | P | — | provider reachability + latency | — | IMPLEMENTED |

## Knowledge Base / documents
| Method | Route | Handler | Role | Ownership | Purpose | Frontend caller | Status |
|---|---|---|---|---|---|---|---|
| POST | `/versions/{version_id}/documents` | `ingest_document` | M | `ensure_version_access` | upload + async processing | `uploadDocument` (knowledge-base, versions) | IMPLEMENTED |
| GET | `/versions/{version_id}/documents` | `get_documents` | M, A | idem | list + live counters | `getDocuments` | IMPLEMENTED |
| GET | `/documents/{document_id}` | `get_document` | M, A | `ensure_document_access` | single document | — | IMPLEMENTED |
| PUT | `/documents/{document_id}` | `update_document` | M | idem | rename / content-type | `updateDocument` | IMPLEMENTED |
| DELETE | `/documents/{document_id}` | `delete_document` | M | idem | delete + chunks | `deleteDocument` | IMPLEMENTED |
| GET | `/documents/{document_id}/chunks` | `get_chunks` | M, A | idem | chunk explorer | `getDocumentChunks` | IMPLEMENTED |
| POST | `/documents/{id}/embeddings/reprocess` | `reprocess_document_embeddings` | M | idem | retry failed/pending embeddings | `reprocessDocumentEmbeddings` | IMPLEMENTED |
| POST | `/documents/{id}/chunks/reprocess` | `reprocess_document_chunks` | M | idem | re-chunk from `raw_text` | `reprocessDocumentChunks` | IMPLEMENTED |
| GET | `/chatbots/{id}/rag-settings` | `get_chatbot_rag_settings` | M, A | `get_accessible_chatbot` | read retrieval settings | `getChatbot` payload | IMPLEMENTED |
| PUT | `/chatbots/{id}/rag-settings` | `update_chatbot_rag_settings` | M | idem | write retrieval settings | `updateChatbotRagSettings` | IMPLEMENTED |

## Retrieval / RAG
| Method | Route | Handler | Role | Purpose | Frontend caller | Status |
|---|---|---|---|---|---|---|
| POST | `/versions/{version_id}/rag-test` | `test_rag_retrieval` | M, A | retrieval-only probe with scores | `testRagRetrieval` | IMPLEMENTED |
| POST | `/chat/sessions` | `start_chat_session` | authenticated | create test session | `startChatSession` | IMPLEMENTED |
| POST | `/chat` | `chat` | authenticated | blocking turn | `api.chat` (versions page) | IMPLEMENTED |
| POST | `/chat/stream` | `chat_stream` | authenticated | streaming turn (SSE) | `chatStream` (flow-test, flow-builder QA) | IMPLEMENTED |
| GET | `/health/rag` | `rag_health` | P | vector store + retrieval diagnostics | — | IMPLEMENTED |

## Evaluation (prefix `/evaluations`)
| Method | Route | Handler | Role | Status |
|---|---|---|---|---|
| POST | `/assistants/{id}/datasets` | `create_dataset` | M | IMPLEMENTED |
| GET | `/assistants/{id}/datasets` | `list_datasets` | M, A | IMPLEMENTED |
| GET / PUT | `/datasets/{id}` | `read_dataset` / `update_dataset` | M, A / M | IMPLEMENTED |
| POST | `/datasets/{id}/archive` · `/restore` | `archive_dataset` / `restore_dataset` | M | IMPLEMENTED |
| DELETE | `/datasets/{id}` | `delete_dataset` | M | IMPLEMENTED (blocked if runs exist) |
| POST | `/datasets/{id}/cases` | `create_case` | M | IMPLEMENTED |
| PUT / DELETE | `/cases/{id}` | `update_case` / `delete_case` | M | IMPLEMENTED |
| POST | `/cases/{id}/duplicate` · `/enabled` | `duplicate_case` / `set_case_enabled` | M | IMPLEMENTED |
| POST | `/datasets/{id}/cases/reorder` | `reorder_cases` | M | IMPLEMENTED |
| POST | `/datasets/{id}/import` | `import_cases` | M | IMPLEMENTED (json, csv) |
| GET | `/datasets/{id}/export` | `export_dataset` | M, A | IMPLEMENTED (json, csv) |
| POST | `/runs` | `run_evaluation` | M | IMPLEMENTED (synchronous) |
| GET | `/assistants/{id}/runs` · `/runs/{id}` · `/results/{id}` | list/read | M, A | IMPLEMENTED |
| POST | `/runs/{id}/cancel` | `cancel_run` | M | PARTIAL (only queued/running) |
| GET | `/compare` | `compare_evaluation_runs` | M, A | IMPLEMENTED |
| GET / PUT | `/assistants/{id}/policy` | `read_policy` / `update_policy` | M, A / M | IMPLEMENTED |

## Versioning / validation / publication
| Method | Route | Handler | Role | Purpose | Frontend caller | Status |
|---|---|---|---|---|---|---|
| POST | `/versions` | `create_version` | M | new draft | `createVersion` | IMPLEMENTED |
| POST | `/versions/{id}/duplicate` | `duplicate_version` | M | copy flow + LLM config | `duplicateVersion` | PARTIAL (no KB copy) |
| GET | `/chatbots/{id}/versions` | `get_versions` | M, A | version history | `getVersionsByChatbot` | IMPLEMENTED |
| GET | `/versions/{id}/readiness` | `get_version_readiness` | M, A | readiness checklist | `getVersionReadiness` | IMPLEMENTED |
| POST | `/versions/{id}/smoke-test` | `smoke_test_version` | M | real runtime probe | `runVersionSmokeTest` | IMPLEMENTED |
| PUT | `/versions/{id}/publish` | `publish_version` | M | publish + archive siblings | `publishVersion` | IMPLEMENTED |
| PUT | `/versions/{id}/archive` | `archive_version` | M | archive | `archiveVersion` | IMPLEMENTED |
| DELETE | `/versions/{id}` | `delete_version` | M | delete + cascade | `deleteVersion` | IMPLEMENTED |
| — | unpublish / rollback | — | — | — | — | **NOT IMPLEMENTED** |
| GET | `/versions/{id}/flow/validate` | `validate_flow` (`flow_routes`) | M, A | flow validation | `validateFlow` | IMPLEMENTED (Ch.5) |

## Channels / public runtime
| Method | Route | Handler | Role | Purpose | Frontend caller | Status |
|---|---|---|---|---|---|---|
| GET | `/chatbots/{id}/channels` | `list_chatbot_channels` | M, A | channel cards | `getChatbotChannels` | IMPLEMENTED |
| POST | `/chatbots/{id}/channels/{type}` | `create_chatbot_channel` | M | create row | **none** | CONFIG-ONLY, no UI caller |
| PUT | `/chatbots/{id}/channels/{type}` | `update_chatbot_channel` | M | status/config/deployed version | **none** | CONFIG-ONLY, no UI caller |
| POST | `/chatbots/{id}/channels/{type}/test` | `test_chatbot_channel` | M | always `configured: true` | `testChatbotChannel` | PARTIAL (validates nothing) |
| PATCH | `/chatbots/{id}/channels/{type}/clear-error` | `clear_channel_error` | M | clear error | **none** | CONFIG-ONLY |
| DELETE | `/chatbots/{id}/channels/{type}` | `delete_chatbot_channel` | M | delete row | **none** | CONFIG-ONLY |
| PUT | `/chatbots/{id}/api-key/regenerate` | `regenerate_chatbot_api_key` | M | new public API key | `regenerateChatbotApiKey` | IMPLEMENTED |
| GET | `/public/chatbots/{id}` | `public_chatbot` | P | public metadata | `getPublicChatbot` | IMPLEMENTED |
| POST | `/public/chat/sessions` | `start_public_chat_session` | P | anonymous session | — | IMPLEMENTED |
| POST | `/public/chat` | `public_chat` | P | blocking turn, sources stripped | — | IMPLEMENTED |
| POST | `/public/chat/stream` | `public_chat_stream` | P | streaming turn, sources stripped | `publicChatStream`, widget | IMPLEMENTED |
| POST | `/public/chat/feedback` | `public_chat_feedback` | P | helpful / not_helpful | `submitPublicFeedback` | IMPLEMENTED |
| POST | `/public/api/chat/sessions` | `start_public_api_chat_session` | P + API key | session | — | IMPLEMENTED |
| POST | `/public/api/chat` | `public_api_chat` | P + API key | turn, **sources included** | — | IMPLEMENTED |
| GET | `/public/widget.js` | `widget_script` | P | embeddable script | snippet in deployment page | IMPLEMENTED |

---

# 14. FRONTEND ROUTE AND COMPONENT INVENTORY

| Feature | Angular route | Component | Service | API calls | Guard / role | Visible actions | Status |
|---|---|---|---|---|---|---|---|
| Knowledge Base management | `/dashboard/projects/:projectId/chatbots/:chatbotId/knowledge` | `KnowledgeBaseComponent` | `ApiService` | `getChatbot`, `updateChatbotRagSettings`, `getDocuments`, `uploadDocument`, `getDocumentChunks`, `updateDocument`, `deleteDocument`, `reprocessDocumentEmbeddings`, `reprocessDocumentChunks`, `testRagRetrieval` | `roleGuard` **manager** | upload, health strip, document list + status, chunk explorer with search, rename, delete, reprocess embeddings, reprocess chunks, retrieval settings, retrieval tester | IMPLEMENTED |
| LLM instructions + version management | `…/:chatbotId/versions` | `VersionsComponent` | `ApiService` | `getVersionsByChatbot`, `createVersion`, `duplicateVersion`, `archiveVersion`, `deleteVersion`, `getVersionReadiness`, `publishVersion`, `runVersionSmokeTest`, `getLlmConfig`, `saveLlmConfig`, `getDocuments`, `uploadDocument`, `deleteDocument`, `chat` | `admin` + `manager`; writes gated by `canManageWorkspace()` | version list with status, create, duplicate, archive, delete, readiness checklist, smoke test, publish (+ warning confirmation), AI instructions editor, quick document upload, inline chat test | IMPLEMENTED |
| Evaluation Center | `…/:chatbotId/evaluations` (+ `…/datasets/:datasetId/cases/new`, `…/cases/:caseId/edit` = manager) | `EvaluationsComponent` | `ApiService` | datasets/cases/runs/policy/compare + `getVersionReadiness`, `publishVersion`, `getFlow` | list `admin` + `manager`; case editors **manager** | dataset CRUD, case editor, enable/disable, duplicate, run, run detail with assertions, compare runs, policy (publish gate), readiness + publish | IMPLEMENTED |
| Deployment / channels | `…/:chatbotId/deployment` | `ChatbotDeploymentComponent` | `ApiService` | `getProject`, `getChatbot`, `getChatbotChannels`, `testChatbotChannel`, `regenerateChatbotApiKey` | `roleGuard` **manager** | public link, widget `<script>` snippet, curl example, API key copy/regenerate, test channel | PARTIAL (read-only view of channel state) |
| Flow test (RAG in context) | `…/:chatbotId/flow/test` | `FlowTestComponent` | `ApiService` | `getChatbotBuilder`, `startChatSession`, `chatStream` | `roleGuard` **manager** | conversation, restart, quick replies, runtime trace, source panel gated by `show_sources` | IMPLEMENTED |
| Public chat page | `/public-chat/:chatbotId` | `PublicChatComponent` | `ApiService` | `getPublicChatbot`, `publicChatStream`, `submitPublicFeedback` | none (anonymous) | chat, feedback, **sources panel that can never populate** | PARTIAL |
| Assistant settings | `…/:chatbotId/settings` | `AssistantSettingsComponent` | `ApiService` | `getChatbot`, `updateChatbot`, `updateChatbotStatus`, `deleteChatbot` | `roleGuard` **manager** | rename/describe, activate/deactivate (gates public access), delete | IMPLEMENTED |
| Admin runtime logs | `/admin/runtime-logs` | `AdminRuntimeLogsComponent` | `ApiService` | `/admin/analytics/runtime-logs` | `roleGuard` **admin** | filter/paginate executions, latency, failures | IMPLEMENTED |
| Admin audit logs | `/admin/audit-logs` | `AdminAuditLogsComponent` | `ApiService` | `/admin/analytics/audit-logs` | `roleGuard` **admin** | audit trail incl. `VERSION_PUBLISHED`, `DOCUMENT_UPLOADED` | IMPLEMENTED |
| Admin analytics / dashboard | `/admin/analytics`, `/admin/dashboard`, `/admin/chatbots` | respective components | `ApiService` | `/admin/analytics/*` | `roleGuard` **admin** | platform KPIs, channels, top chatbots, system health | IMPLEMENTED |

---

# 15. EXISTING TEST / VALIDATION EVIDENCE

**No test was executed during this inspection.** The following files exist and were read for
their declared intent only.

## Automated tests (`backend/tests/`)

| File | Verifies |
|---|---|
| `test_azure_openai_provider.py` | GPT-5/reasoning deployments use `max_completion_tokens` and omit `temperature` (chat + streaming); empty completion raises; embeddings use the configured embedding deployment |
| `test_knowledge_ingestion_reliability.py` | all-ready → `ready`; partial failures → `partially_ready` while keeping successful chunks; embedding reprocess retries only failed/pending; SHA-256 duplicate detection in the same KB; repeated reprocess while `processing` does not duplicate work; chunk reprocess failure preserves the previous ready index; bounded retry exhaustion; Azure embedding client reuse |
| `test_pgvector_retrieval.py` | `pgvector_literal` dimension validation; `_mark_chunk_ready` writes both JSON and vector; fallback path enforces top-k, threshold and KB scope; similarity semantics stay in [0,1] |
| `test_publication_readiness.py` | BLOCKED checklist prevents publish; WARNING requires confirmation then publishes; deterministic flow without AI/RAG has no fallback warning; smoke test result is recorded and consumed by readiness |
| `test_publication_readiness_regression_gate.py` | publish blocked on evaluation regression when the policy is enabled; allowed when disabled; first publication is not blocked without a baseline; warning-only publish requires confirmation |
| `test_evaluation_center.py` | required/forbidden keyword scoring; run persists dataset snapshot and uses the real runtime; regression comparison; required-evaluation policy blocks/allows readiness; multi-turn state preservation; legacy text-only turns; button-selection turns and rejection of invalid ones |
| `test_runtime_logs.py` | success/failure log creation; `rag_used` reflects the actual RAG path; sensitive error messages sanitized; time-series gap filling; endpoint filtering/pagination; system-health behaviour without logs |
| `test_channel_removal.py` | Meta/WhatsApp/Messenger routes are not registered; only `web`, `widget`, `api` accepted |
| `test_workspace_read_only_permissions.py` | `require_workspace_manager` allows manager and rejects admin; project, assistant, assistant sub-resource and evaluation **write** routes all use it (**flow routes are not asserted**) |
| `test_project_isolation.py` | manager scoping across projects, assistants and **flow resources**; admin global read; `admin_get_flow` does not create a missing flow; project duplication copies metadata only |
| `test_cors.py` | comma/JSON origin parsing; wildcard rejected with credentials; localhost defaults; production origin configuration; login preflight |
| `test_flow_blocks.py`, `test_flow_runtime_blocks.py`, `test_flow_hardening.py` | runtime block behaviour incl. RAG-node paths (Chapter 5) |
| `test_admin_dashboard.py`, `test_admin_analytics_platform.py`, `test_admin_chatbots.py`, `test_audit_logs.py` | admin aggregation and audit surfaces |

**No automated test found for:** the `/llm-config` endpoints, chunking parameters
(`chunk_document` boundaries), `hide_public_sources` on the public runtime,
`show_sources` end-to-end gating, public session-id isolation, publish → sibling archiving
side effect, `duplicate_version` knowledge-base omission.

## Runtime / operational validation (not unit tests)
- `main.py::validate_external_ai_configuration` — startup gate on AI + embedding config.
- `GET /health/database`, `GET /health/ai`, `GET /health/rag` — live diagnostics, including
  pgvector extension and schema presence and a real similarity probe.
- `POST /versions/{id}/smoke-test` — real 3-turn runtime execution stored as evidence.
- `GET /versions/{id}/readiness` — 9–11 rule checklist.
- `POST /versions/{id}/rag-test` — retrieval probe with scores.

## Frontend validation
- Route guards `authGuard` + `roleGuard` with `data.roles`.
- `canManageWorkspace()` disables write controls for admin on shared pages.
- File input `accept` filter; duplicate-upload modal; confirmation modals for delete and
  chunk reprocess; document status polling.
- Publish warning confirmation dialog in `versions` and `evaluations`.

## Manual-test-friendly behaviour worth using in the report
Document status transitions are observable through the UI; `rag-test` gives reproducible
retrieval scores; the flow-test runtime trace exposes `current_node_key`, `mode_used` and
`retrieval_mode`; `/health/rag` gives a one-shot vector-store snapshot; the widget snippet can
be pasted into a static HTML page.

---

# 16. RECOMMENDED CHAPTER 6 STRUCTURE

Verdict per subsection you proposed. Numbering intentionally omitted.

## PART I — Intégration des modèles de langage et du système RAG

| Proposed subsection | Verdict | Why |
|---|---|---|
| Introduction | **KEEP** | State plainly: integration of pre-trained models, no training |
| Backlog | **KEEP** | Real deliverables: LLM integration, KB, ingestion, retrieval, RAG, evaluation gate |
| Analyse — Use case diagram | **KEEP** | See §17 |
| Analyse — textual use cases | **KEEP**, limit to 3–4 | Configure LLM, ingest document, generate RAG answer, run evaluation |
| Conception — Global LLM/RAG architecture | **KEEP** | Figure A |
| Conception — Knowledge Base architecture | **MERGE** into the data model figure | KB is a thin 1-1 table; a standalone architecture figure would be padding. Merge into a "modèle de données de la base de connaissances" figure (Figure B) |
| Conception — Document processing pipeline | **KEEP** | Strongest technical content of Part I (Figure C) |
| Conception — Semantic retrieval process | **KEEP** | Figure D; include the pgvector cosine formula and the fallback branch |
| Conception — RAG architecture | **RENAME** → "Architecture de génération augmentée par récupération (RAG)" | Distinguish it clearly from the global architecture; centre it on prompt assembly + `strict_context` + `continue_rag` |
| Conception — Sequence diagrams | **KEEP**, limit to 3 | §18 |
| Réalisation — LLM integration/configuration | **RENAME** → "Configuration du modèle et des instructions système" | The UI configures instructions/temperature, **not** the model; the honest title avoids over-claiming |
| Réalisation — Knowledge Base management | **KEEP** | Real page with real actions |
| Réalisation — document processing/vectorization | **KEEP** | Chunking + embeddings + statuses + reprocessing |
| Réalisation — semantic retrieval | **MERGE** with the retrieval tester interface | The visible deliverable is the retrieval tester; a separate subsection would repeat Conception |
| Réalisation — RAG implementation | **KEEP** | Node behaviour, `strict_context`, fallback, `continue_rag`, sources |
| Réalisation — interfaces | **KEEP** | Screenshots (§19) |
| RAG Evaluation — method | **RENAME** → "Évaluation déterministe du comportement de l'assistant (jeux de tests et assertions)" | Prevents an unsupported academic claim |
| RAG Evaluation — real results/statistics | **KEEP** with an explicit measurement protocol | Only Category A/B data from §6.2 |
| RAG Evaluation — analysis | **KEEP** | Discuss limits: no groundedness, judge disabled, keyword-based assertions |
| Tests and validation | **KEEP** | §15; add "aucun test automatisé exécuté dans le cadre de cette inspection" if you reuse this report |

**Subsection to ADD to Part I:** *"Fiabilité de l'ingestion : états, reprise et
réindexation"* — the retry/transient classification, `partially_ready`, and the two
reprocess endpoints are implemented, well tested, and are genuinely distinctive work.

## PART II — Validation, gestion des versions et publication des assistants

| Proposed subsection | Verdict | Why |
|---|---|---|
| Introduction | **KEEP** | |
| Product Backlog | **KEEP** | |
| Analyse — Use case diagram | **KEEP** | §17 |
| Analyse — textual use cases | **KEEP**, limit to 3 | Publish a version, validate before publication, consume the published assistant |
| Conception — version lifecycle | **KEEP** | State diagram (§8.A) — the highest-value figure of Part II |
| Conception — publication validation process | **KEEP** | Activity diagram (§8.B) |
| Conception — publication/public access architecture | **KEEP**, but **split** the figure | One architecture figure for the three public surfaces; keep the publication process as a sequence diagram |
| Conception — sequence diagrams | **KEEP**, limit to 2 | Publish, public interaction |
| Réalisation — version management | **KEEP** | |
| Réalisation — creation/duplication | **KEEP** | State explicitly that duplication does not copy the knowledge base |
| Réalisation — archive/delete | **MERGE** into version management | Two guarded endpoints; not enough for a standalone subsection |
| Réalisation — validation before publication | **KEEP** | Readiness checklist + smoke test — strong content |
| Réalisation — publication | **KEEP** | Gates, archiving side effect, audit |
| Réalisation — channels | **RENAME** → "Canaux de diffusion : page publique, widget web et API REST" and state that channel records are descriptive | Avoids claiming a channel-management feature |
| Réalisation — public access | **KEEP** | Version resolution + draft protection |
| Réalisation — interfaces | **KEEP** | |
| Tests and validation | **KEEP** | |
| Chapter conclusion | **KEEP** | |

**Subsections to ADD to Part II:**
- *"Limites de la gestion des versions"* — no unpublish, no rollback endpoint, a published
  version is not immutable, RAG settings are not version-scoped. Presenting these as
  identified limitations with proposed remediations is stronger academically than hiding them.
- *"Traçabilité : journaux d'audit et journaux d'exécution"* — `AuditLog` +
  `RuntimeLog` are real, tested, and directly serve the publication story.

**REMOVE from any plan:** a "rollback / restore" subsection, an "LLM fine-tuning /
model training" subsection, a "multi-provider selection per assistant" subsection, and any
"WhatsApp / Messenger / social channels" subsection.

---

# 17. RECOMMENDED USE CASES

## Part I — principal actor: **Manager**
Secondary actors: **Administrateur** (read-only supervision), **Fournisseur LLM/Embeddings**
(external system), **Visiteur public** (indirect consumer of RAG answers).

Principal use cases:
1. Configurer les instructions système et la température d'une version
2. Téléverser un document dans la base de connaissances
   — `«include»` *Extraire et découper le document*, `«include»` *Générer les embeddings*
3. Suivre l'état d'indexation d'un document
   — `«extend»` *Relancer la génération des embeddings*, `«extend»` *Redécouper le document*
4. Configurer les paramètres de récupération (mode, top-k, seuil, sources, contexte strict)
5. Tester la récupération sémantique sur une question
6. Obtenir une réponse augmentée par récupération (RAG)
   — `«include»` *Rechercher les passages pertinents*, `«include»` *Interroger le modèle*
   — `«extend»` *Répondre par message de repli* (when `strict_context` and no context)
7. Gérer un jeu de tests d'évaluation (dataset + cas)
8. Exécuter une évaluation sur une version — `«include»` *Exécuter le flux*
9. Comparer deux exécutions d'évaluation
10. Consulter les diagnostics IA/RAG (Administrateur, `GET /health/*`)

## Part II — principal actor: **Manager**
Secondary actors: **Administrateur** (supervision, audit), **Visiteur public**,
**Système externe** (API key consumer).

Principal use cases:
1. Créer une nouvelle version
2. Dupliquer une version — `«extend»` of *Créer une nouvelle version*
3. Consulter l'état de préparation à la publication
   — `«include»` *Valider le flux*, `«include»` *Vérifier l'indexation des connaissances*,
     `«extend»` *Vérifier la politique d'évaluation*
4. Exécuter un test de fumée d'exécution
5. Publier une version — `«include»` *Consulter l'état de préparation*,
   `«include»` *Valider le flux*, `«extend»` *Confirmer les avertissements*
6. Archiver / supprimer une version
7. Récupérer le lien public, le code du widget et la clé d'API
   — `«extend»` *Régénérer la clé d'API publique*
8. Activer / désactiver l'assistant (gates public availability)
9. Dialoguer avec l'assistant publié (Visiteur public)
   — `«include»` *Résoudre la version publiée*, `«extend»` *Donner un avis (utile / pas utile)*
10. Appeler l'assistant via l'API REST publique (Système externe)
    — `«include»` *Authentifier par clé d'API*
11. Superviser les exécutions et l'audit (Administrateur)

**Do not put on the diagram:** "Annuler la publication", "Restaurer une version antérieure
(rollback)", "Configurer un canal", "Déployer une version sur un canal".

## Textual use cases recommended for full description

**Part I**
- *Téléverser et indexer un document* — pre: manager owns the project, a draft version
  exists; post: document `ready` and chunks searchable; alternatives: duplicate (409),
  partial embedding failure → `partially_ready` + reprocess; exception: unextractable
  PDF → `failed` with an OCR message.
- *Obtenir une réponse RAG* — pre: version has an `LLMConfig` and ready chunks; post: answer
  persisted with sources and updated session state; alternative: `continue_rag` keeps the
  same node; exceptions: no context + `strict_context` → fallback without an LLM call;
  provider failure → 502 / `error` event.
- *Exécuter une évaluation* — pre: dataset with enabled cases, target version has an
  `LLMConfig`; post: `EvaluationRun` completed with score and per-case assertions;
  alternative: comparison with a baseline run; exception: archived dataset → 400.

**Part II**
- *Publier une version* — pre: manager owns the assistant, no BLOCKED check;
  post: version `published`, siblings `archived`, `active_version_id` updated, audit written;
  alternative: warnings → confirmation; exceptions: BLOCKED → 400, invalid flow → 400.
- *Valider une version avant publication* — pre: version exists; post: checklist with
  BLOCKED/WARNING/PASSED and remediation targets; alternative: run a smoke test first;
  exception: evaluation policy blocks on regression.
- *Dialoguer avec l'assistant publié* — pre: assistant active with a published version;
  post: answer returned, transcript and runtime log persisted; alternative: widget or REST
  API; exceptions: inactive → 404, no published version → 404, provider error → error event.

---

# 18. RECOMMENDED SEQUENCE DIAGRAMS

Keep **three for Part I** and **two for Part II**.

| # | Title | Participants | Justification |
|---|---|---|---|
| I-1 | Téléversement et indexation d'un document | Manager → `KnowledgeBaseComponent` → `ApiService` → `knowledge_routes` → `BackgroundTask` → `EmbeddingProvider` → PostgreSQL | Only figure that shows the asynchronous pipeline, the immediate response and the polling loop |
| I-2 | Génération d'une réponse RAG en streaming | Manager/Visiteur → chat component → `ApiService` → `chat_routes`/`public_routes` → `flow_runtime.execute_flow` → `rag` service → PostgreSQL(pgvector) → LLM provider | Core of the chapter; carries `alt` blocks for fallback, error and `continue_rag` |
| I-3 | Exécution d'une évaluation | Manager → `EvaluationsComponent` → `ApiService` → `evaluation_routes` → `evaluation_engine` → `flow_runtime` + `build_rag_response` → PostgreSQL | Shows the loop over cases and the assertion/scoring step |
| II-1 | Publication d'une version | Manager → `VersionsComponent` → `ApiService` → `version_routes.publish_version` → `publication_readiness` → `flow_validation` → PostgreSQL → `AuditLog` | Shows the double gate (400 / 409) and the sibling-archiving side effect |
| II-2 | Interaction avec un assistant publié | Visiteur public → `PublicChatComponent`/`widget.js` → `public_routes` → `get_active_version` → `execute_flow` → RAG/LLM → PostgreSQL → `RuntimeLog` | Shows draft protection and source stripping |

Drop: a separate "create version" sequence (trivial), a "configure LLM" sequence (a 3-message
CRUD round trip — describe it in prose or fold it into an interface figure), and any
"configure channel" sequence (no runtime effect).

---

# 19. RECOMMENDED TECHNICAL FIGURES AND SCREENSHOTS

## Technical figures

| Figure | Type | Section | Shows | Why a figure rather than text | Evidence |
|---|---|---|---|---|---|
| Architecture globale LLM + RAG | architecture | Part I – Conception | SPA + widget, FastAPI, services, PostgreSQL/pgvector, external provider | Text cannot convey that the vector index lives inside the main database and that the provider is contacted from exactly two services | `main.py`, `ai_provider.py`, `embeddings.py`, `models/chunk.py` |
| Modèle de données connaissances & versions | class / data | Part I – Conception | `Chatbot → Version → {Flow, LLMConfig, KnowledgeBase} → Document → Chunk` with the 1-1 uniqueness constraints | The 1-1 constraints and what is *not* version-scoped are the source of several report claims | the model files |
| Pipeline de traitement documentaire | activity | Part I – Conception | upload → extraction → chunking → embedding → statuses, with the background-task lane | Multiple branches and derived statuses; prose would be long and unclear | `knowledge_routes.process_document_background`, `services/rag.py` |
| Processus de récupération sémantique | process | Part I – Conception | query → embedding → cosine SQL → filters → top-k → fallback | Shows the decision that selects `semantic` vs `keyword_fallback` | `services/rag.py` ~505–665 |
| Assemblage du prompt RAG | annotated diagram | Part I – Conception/Réalisation | the 7 instruction lines + history/variables/context/question blocks | Communicates prompt engineering compactly | `chat_routes.prepare_rag_generation` |
| Cycle de vie d'une version | **state diagram** | Part II – Conception | draft / published / archived, guards, publish side effects | Best possible use of a state diagram; also the natural place to annotate the missing unpublish/rollback | `version_routes.py`, `models/version.py` |
| Processus de validation avant publication | activity | Part II – Conception | readiness checks → BLOCKED/WARNING/PASSED → 400/409/200 | A decision-heavy workflow | `publication_readiness.readiness_report`, `publish_version` |
| Architecture d'accès public | architecture | Part II – Conception | three public surfaces → `public_router` → version resolution → runtime → logs; `ChatbotChannel` drawn outside the runtime path | The single clearest way to convey that channel records are not in the execution path | `public_routes.py`, `unified_runtime.py` |
| Répartition des scores de similarité | chart | Part I – Évaluation | histogram of retrieval scores on a fixed question set | Real measurable data | `POST /versions/{id}/rag-test` |
| Résultats d'une exécution d'évaluation | chart / table | Part I – Évaluation | passed/warning/failed per case + overall score + latency | Directly produced by the app | `EvaluationRun`, `EvaluationCaseResult` |

## Interface screenshots, in Manager journey order

| # | Page / component | Illustrates | What must be visible | Framing | Report subsection |
|---|---|---|---|---|---|
| 1 | Versions — AI Instructions block | LLM configuration | System instructions, tone, language, response style, temperature, Save | targeted | Part I – Réalisation (configuration du modèle) |
| 2 | Knowledge Base — upload + health strip | KB entry point | upload zone, accepted formats, index health indicator | targeted | Part I – Réalisation (gestion de la base de connaissances) |
| 3 | Knowledge Base — document list with statuses | ingestion pipeline result | one `ready`, one `processing` or `partially_ready`, chunk/embedding counters | targeted | Part I – Réalisation (traitement documentaire) |
| 4 | Knowledge Base — chunk explorer | chunking result | chunk list with titles/section types and one chunk body | targeted | Part I – Réalisation (découpage et vectorisation) |
| 5 | Knowledge Base — retrieval settings panel | RAG configuration | Retrieval mode, Max chunks, Min score, Show source references, strict context | targeted | Part I – Réalisation (configuration de la récupération) |
| 6 | Knowledge Base — retrieval tester | semantic retrieval | question, resulting chunks with scores, `retrieval mode` pill | targeted | Part I – Réalisation (récupération sémantique) |
| 7 | Flow Test — RAG answer with sources | RAG end-to-end | user question, AI answer, source references with filename and score | full page | Part I – Réalisation (implémentation RAG) |
| 8 | Evaluations — dataset and cases | evaluation datasets | dataset, case list, expected/forbidden keywords on one case | targeted | Part I – Évaluation |
| 9 | Evaluations — run detail with assertions | evaluation results | overall score, per-case status, assertion breakdown, latency | full page | Part I – Évaluation (résultats) |
| 10 | Evaluations — comparison / policy | regression gate | compare result or the publish-gate policy form | targeted | Part I – Évaluation / Part II – Validation |
| 11 | Versions — version history | version management | several versions with `draft` / `published` / `archived` and the active marker | full page | Part II – Réalisation (gestion des versions) |
| 12 | Versions — readiness checklist | publication validation | mixed PASSED / WARNING / BLOCKED items with messages | targeted | Part II – Réalisation (validation avant publication) |
| 13 | Versions — publish confirmation | publication | the warning confirmation dialog | targeted | Part II – Réalisation (publication) |
| 14 | Deployment — public link, widget snippet, API key | channels | public URL, `<script>` snippet, curl example, masked API key | full page | Part II – Réalisation (canaux de diffusion) |
| 15 | Public chat page | public access | anonymous conversation with a RAG answer | full page | Part II – Réalisation (accès public) |
| 16 | Widget on an external HTML page | widget channel | the launcher and an open panel over third-party content | targeted | Part II – Réalisation (widget) |
| 17 | Admin — runtime logs | supervision | executions with channel, status, latency, `rag_used` | full page | Part II – Traçabilité |
| 18 | Admin — audit logs | traceability | `VERSION_PUBLISHED`, `DOCUMENT_UPLOADED` entries | targeted | Part II – Traçabilité |

Avoid as redundant: the flow builder canvas (Chapter 5), the assistant creation wizard
(Chapter 4), a second chat screenshot that shows nothing new, and any screenshot of the
public chat "sources" panel (it can never be populated).

---

# 20. RECOMMENDED STATISTICS AND EVALUATION RESULTS

| Proposed statistic | Source data | Calculation | App already computes? | Manual measurement needed? | Academically meaningful? |
|---|---|---|---|---|---|
| Corpus indexed: documents, chunks, ready embeddings | `documents`, `chunks` via `GET /versions/{id}/documents` | direct counters | **Yes** | no | Yes — describes the experimental corpus |
| Chunks per document (mean / min / max) | `documents.chunks_count` | descriptive stats | partially (per document) | light aggregation | Yes |
| Chunk size distribution (words) | `chunks.text` | word count per chunk | no | yes (SQL/script) | Yes — validates the 90-word target |
| Embedding success rate | `chunks.embedding_status` | ready / total | **Yes** (per document) | light aggregation | Yes |
| Ingestion duration per document | log `knowledge_ingestion … latency_ms` | direct read | logged, not stored | yes | Yes — pipeline performance |
| Mean embedding latency per chunk | log `knowledge_embedding … latency_ms` | mean | logged, not stored | yes | Yes |
| Retrieval latency (query embedding vs. SQL) | log `rag_retrieval … query_embedding_ms= db_ms=` | mean per component | logged, not stored | yes | Yes — justifies pgvector |
| Top-1 and top-k similarity scores on a fixed question set | `POST /versions/{id}/rag-test` | mean, distribution | scores computed per call | yes (protocol) | Yes — the core Part I measurement |
| Share of questions with at least one chunk above the threshold | same | count / N | no | yes | Yes — retrieval coverage |
| Fallback rate (`mode_used == "fallback"`) | chat responses / `runtime_logs.execution_mode` | count / total | partially | light aggregation | Yes — honest proxy for "unanswerable" |
| End-to-end response latency (public traffic) | `runtime_logs.response_time_ms` | p50 / p95 | stored | light aggregation | Yes |
| Runtime success rate | `runtime_logs.status` | success / total | stored | light aggregation | Yes |
| RAG usage rate | `runtime_logs.rag_used` | true / total | stored | light aggregation | Yes |
| Streaming responsiveness (time to first token) | `latency.backend.azure_first_token_from_request_ms` | mean | computed, returned | capture needed | Yes |
| Estimated prompt tokens and context size | `latency.rag_context_tokens`, `context_chars` | mean | computed | capture needed | Yes — **must be labelled "estimated"** |
| Evaluation: overall score, pass/warning/fail, per-case latency | `EvaluationRun`, `EvaluationCaseResult` | provided | **Yes** | no | Yes — with the correct framing |
| Assertion pass rate by assertion type | `EvaluationCaseResult.assertion_results` | count per code | stored raw | light aggregation | Yes — a genuinely interesting table |
| Regression count between two versions | `GET /evaluations/compare` | provided | **Yes** | no | Yes |
| Smoke-test latency and outcome per version | `VersionSmokeTest` | provided | **Yes** | no | Yes |
| Publication funnel: versions created vs. published | `versions.status`, `published_at` | counts | no | light aggregation | Moderate |
| Groundedness / faithfulness / precision / recall / MRR | — | — | **No** | **would require building an annotated ground truth and new code** | Yes but **NOT AVAILABLE** — present only as future work |
| Real token usage and cost | — | — | **No** (only estimates) | provider-side data needed | Yes but **NOT AVAILABLE** |

**Suggested honest protocol to state in the report:** build a corpus of *N* documents, write
*M* reference questions, run each through `POST /versions/{id}/rag-test` and one
`EvaluationRun`, and report: corpus size (documents/chunks/embeddings), ingestion time,
embedding success rate, top-1 similarity distribution, retrieval coverage above the
threshold, assertion pass rate, fallback rate, and end-to-end latency. Every one of these is
obtainable from the current implementation without writing new code.

---

# 21. IMPLEMENTATION DISCREPANCIES AND RISKS

## Frontend / backend mismatches
1. **Public chat sources panel is dead UI.** `pages/public-chat` maintains a `sources` signal
   and a styled sources section, but `hide_public_sources` empties `sources` on every
   `/public/chat` and `/public/chat/stream` response. The panel can never render content.
2. **Channel CRUD endpoints have no UI caller.** `POST`, `PUT`, `PATCH .../clear-error` and
   `DELETE` on `/chatbots/{id}/channels/{type}` exist and are audited, but
   `pages/chatbot-deployment` only lists, tests and regenerates the API key.
3. **"Test channel" validates nothing.** It always returns
   `{"configured": true, "missing_fields": []}` and logs a success event, yet the UI
   presents it as a configuration check.
4. **"Rollback: Available/Unavailable"** in `pages/project-overview` is derived from
   `len(published_versions) > 1`. Because publishing archives all siblings, this is
   effectively always "Unavailable", and no rollback action exists anywhere.
5. **The `model` field is a phantom control.** `versions.component.ts` keeps
   `aiInstructions.model` and sends it, but there is no input in the template, and under
   `AI_PROVIDER=azure_openai` the backend ignores it (`configured_chat_model`).
6. **Tone / Language / Response style look like structured settings** but are serialized into
   the free-text `system_prompt` and re-parsed by string matching (`extractPromptValue`).
   Renaming a label breaks the round trip.
7. **Admin sees version and evaluation pages but cannot act**; write attempts return 403
   with a workspace-read-only message. The frontend mostly disables the controls
   (`canManageWorkspace()`), but the two policies are maintained in parallel rather than
   derived from one source.

## UI options without runtime support
- Channel `status` and `deployed_version_id` are stored but never consulted by any runtime
  path; a channel marked `disabled` still serves traffic.
- `RETRIEVAL_CONFIGURATION_VALID` in the readiness checklist is hard-coded to `PASSED` and
  verifies nothing.
- Hidden flow block types (`ai_router`, `ai_classifier`, `confidence_check`, `lead_score`,
  `api_request`, `action`) exist in the runtime but are placeholders.

## Incomplete functionality
- `duplicate_version` copies the flow and the LLM config but **not** the knowledge base, so a
  duplicated KB-dependent version is immediately BLOCKED on `KNOWLEDGE_INDEXED`.
- No unpublish, no rollback, no "create draft from published version" convenience action.
- A published version is **not immutable**: flow CRUD, `/llm-config` and document endpoints
  ignore `version.status`.
- `Chatbot.rag_settings` is not version-scoped, so retrieval behaviour of a published version
  can change without a new version.
- Document processing uses in-process `BackgroundTasks`: an application restart mid-processing
  leaves a document stuck in `processing` with no automatic recovery (manual reprocess only).
- `POST /evaluations/runs` runs synchronously in the request; large datasets risk HTTP
  timeouts. `status="queued"` and the cancel endpoint suggest asynchronous execution that
  does not exist.
- Chunking parameters (90 words / 12 overlap) are not configurable anywhere.
- No OCR, so scanned PDFs are rejected.
- No document file is stored; only the extracted text (`raw_text`). Documents cannot be
  re-downloaded, and pre-`raw_text` rows cannot be re-chunked (explicit 400).
- `BLOCK_CONFIGURATION_COMPLETE` duplicates `FLOW_VALID` (same boolean), inflating the
  checklist without adding a check.

## Misleading naming
| Name in code/UI | Reality | Suggested report wording |
|---|---|---|
| "Rollback available" | count of published versions > 1 | "republication par duplication" |
| "Test channel" | always succeeds | "vérification de présence de configuration" (or omit) |
| `ChatbotChannel.deployed_version_id` | never read at runtime | "métadonnée de canal, non utilisée par l'exécution" |
| `storage_url = local://…` | no file is stored | "identifiant logique du document" |
| `judge_result` / `judge_prompt_version` | judge disabled | do not mention, or state "désactivé" |
| `Document.status = "processed"` | legacy default treated as ready | use `ready` in the report |
| "RAG evaluation" | deterministic assertions | "évaluation déterministe du comportement" |
| `retrieval_only` on `knowledge_search` | retrieval without generation | "récupération sans génération" |

## Role / permission inconsistencies
- `flow_routes` write endpoints use `require_roles("admin","manager")` while every comparable
  workspace write uses `require_workspace_manager`. Admin can therefore modify flow nodes and
  transitions despite the documented read-only policy, and
  `test_workspace_read_only_permissions.py` does not assert these routes.
- `GET /versions/{id}/documents` auto-creates the KB only for managers, producing
  role-dependent side effects on a read endpoint.

## Security concerns relevant to Chapter 6
1. **`/llm-config` has no ownership check** (both verbs). Any authenticated manager can read
   or overwrite the system prompt, temperature and model of **any** version by numeric id.
   This is the most serious finding: the system prompt directly controls assistant behaviour.
2. **Anonymous session resumption.** `get_or_create_public_session` accepts a client-supplied
   integer `session_id` filtered only by `chatbot_id` and `user_id IS NULL`, so sequential
   ids allow reading/continuing another visitor's conversation.
3. **No rate limiting on public endpoints.** `/public/chat/stream` triggers embedding and LLM
   calls; unlimited anonymous access is a cost and availability risk.
4. **Enumerable public identifier.** `chatbot_id` is a sequential integer; any active
   assistant with a published version is publicly reachable by guessing.
5. **Full chunk text in `/public/api/chat` sources.** The API channel returns complete chunk
   text, filenames and scores without applying `hide_public_sources`, which can leak internal
   document content to API consumers.
6. **`print()` of response text in `unified_runtime`** writes conversation content to stdout.
7. **No per-assistant allowed-origin list.** Widget embedding depends on the server-wide
   `ALLOWED_ORIGINS`; there is no way to restrict a given assistant to a given domain.
8. Positive counterweights worth stating: API keys and DB URLs are redacted in provider
   errors (`_safe_openai_error`, `_redact_secret`) and in runtime logs
   (`SENSITIVE_PATTERNS`); audit metadata drops sensitive keys (`safe_metadata`);
   channel `api_key` values are masked (`mask_config`); wildcard CORS is rejected when
   credentials are enabled; **draft versions are provably unreachable publicly**.

## Versioning limitations (summary)
No unpublish, no rollback, published versions mutable, duplication loses the knowledge base,
publish archives drafts, RAG settings/channels/API key outside the version scope, archive and
delete not audited.

## Publication limitations
`RETRIEVAL_CONFIGURATION_VALID` is cosmetic; no channel field validation; no allowed-origin
verification; publication does not update channel `deployed_version_id`; publication cannot be
scheduled or staged.

## RAG limitations
Fixed word-based chunking; no OCR; no re-ranking; no query rewriting or expansion; no
multi-KB or cross-version retrieval; keyword scoring is a hand-tuned heuristic; retrieval is
version-scoped only; no `ivfflat`/`hnsw` index creation was observed in the inspected
migrations (retrieval may be doing exact scans — **uncertain, would require checking
`backend/alembic/versions/f7b8c9d0e1f2_add_pgvector_embedding_column.py` and the live schema
for an index on `chunks.embedding_vector`**).

## Evaluation limitations
Keyword-substring correctness checks; no semantic answer comparison; judge disabled;
synchronous execution; `queued`/cancel semantics not backed by a queue; no
groundedness/precision/recall; retrieval quality assessed only through `MINIMUM_RETRIEVAL_SCORE`
and `MINIMUM_SOURCE_COUNT`.

---

# 22. SAFE TO CLAIM IN THE PFE REPORT

1. ChatBot Factory **integrates pre-trained language models** through a provider abstraction
   supporting **Azure OpenAI** and **Ollama**, selected by environment configuration; the
   application does not train or fine-tune any model.
2. Chat generation is available in **blocking and token-streaming** modes
   (`generate_chat_completion`, `stream_chat_completion`), with **provider-specific handling
   of reasoning deployments** (`max_completion_tokens`, `reasoning_effort`, no `temperature`).
3. External AI configuration is **validated at application startup**; a misconfiguration
   prevents the API from starting.
4. Each assistant version owns exactly one **generation configuration** (`LLMConfig`:
   model, temperature, system prompt) and exactly one **knowledge base**.
5. Uploaded documents are processed by a real pipeline: **text extraction** (pypdf for PDF,
   UTF-8 otherwise), **normalization**, **structure-aware chunking** (~90 words, 12-word
   overlap, heading detection), **embedding generation** (batched, with bounded retry limited
   to transient errors and dimension validation), and **status derivation**
   (`uploaded → processing → ready | partially_ready | failed`).
6. Vectors are stored in **PostgreSQL with the pgvector extension**
   (`chunks.embedding_vector VECTOR(1536)`), in the same database as the relational data.
7. Semantic retrieval is performed **in SQL using cosine similarity** (`1 - (v <=> q)`),
   filtered by knowledge base and document/chunk readiness, with a **configurable top-k and
   minimum score**, and a **keyword fallback** when no vector search is possible or the
   query embedding fails.
8. **RAG generation** assembles a structured prompt from system instructions, node
   instructions, language and length directives, conversation history, session variables and
   the retrieved context, then calls the model and returns the answer with **source
   references**.
9. **Source visibility is enforced server-side**: when disabled, source data is never
   included in the response payload.
10. **Strict context mode** returns a configured fallback message **without calling the
    model** when no relevant context is retrieved; otherwise the model is instructed to state
    that the answer is not confirmed by the uploaded documents.
11. Ingestion reliability features are implemented and covered by automated tests:
    SHA-256 duplicate detection, partial-readiness preservation, targeted embedding
    reprocessing, and chunk reprocessing that preserves the previous working index on failure.
12. An **assertion-based evaluation system** exists (datasets, multi-turn cases, runs,
    per-case results, comparison) that executes the **real runtime** including RAG, produces
    a weighted score, and can act as a **publication gate** with score, failure-count,
    critical-failure, freshness and **regression** conditions.
13. Assistants follow a **three-state version lifecycle** (`draft`, `published`, `archived`)
    with recorded actors and timestamps for creation, publication and archiving.
14. Publication is protected by a **readiness checklist** (instructions, flow validity, block
    configuration, knowledge indexing, public channel, runtime smoke test, optional
    evaluation policy, fallback message) classifying items as **BLOCKED / WARNING / PASSED**;
    BLOCKED items prevent publication (HTTP 400) and WARNING items require explicit
    confirmation (HTTP 409).
15. A **runtime smoke test** executes up to three real conversation turns against the version
    and persists the outcome, latency and trace as pre-publication evidence.
16. Publication sets the version as the assistant's **active version**, archives the other
    versions, and writes an **audit entry**.
17. Published assistants are reachable through **three implemented surfaces**: a hosted public
    chat page, an **embeddable JavaScript widget** served by the backend, and a
    **REST API protected by a per-assistant API key**.
18. **Only published versions are ever served publicly**: every public version-resolution
    path filters on `status == "published"`, so draft content cannot leak to end users.
    Draft preview requires an authenticated admin or manager.
19. Public executions are **logged** (`RuntimeLog`: channel, status, latency, `rag_used`,
    failure category, provider) with **sanitized error messages**, and sensitive-action
    **audit logs** are recorded for document upload/deletion, version creation and publication,
    channel changes and evaluation operations.
20. **Manager access is owner-scoped** to their own projects; **administrators have global
    read access and are denied workspace writes** by a dedicated dependency
    (`require_workspace_manager`), which is covered by automated tests.
21. Operational diagnostics endpoints exist for the database, the LLM provider and the RAG
    stack, including a live pgvector extension/schema check and a real similarity probe.

---

# 23. DO NOT CLAIM IN THE PFE REPORT

**Absent features — do not mention as existing**
- Unpublishing a version; rollback or restoring a previous version as a feature.
- Immutability of a published version.
- Version-scoped RAG settings, channels or public API key.
- Knowledge base copy on version duplication.
- Chatbot duplication.
- Renaming or deleting a knowledge base.
- WhatsApp, Messenger, Instagram, Slack, Teams, SMS or any social/messaging channel.
- A task queue, message broker, Celery worker or distributed ingestion pipeline.
- OCR, table extraction, DOCX/XLSX/PPTX parsing, image understanding.
- Re-ranking, query rewriting, query expansion, HyDE, multi-query retrieval, hybrid BM25+vector
  search in PostgreSQL, multi-knowledge-base or cross-version retrieval.
- Per-assistant model selection, per-assistant provider selection, model fallback chains.
- Per-assistant allowed-domain restriction, public rate limiting, CAPTCHA, abuse protection.
- Real provider token accounting or cost tracking.
- Conversation memory beyond the persisted session transcript (no summarization, no vector
  memory).

**Planned/partial — do not describe as complete**
- Channel management: the records and endpoints exist, but they do not influence runtime
  behaviour and have no UI for create/update/delete. Describe the **three delivery surfaces**,
  not a "channel deployment system".
- The channel test action: it does not verify configuration.
- `RETRIEVAL_CONFIGURATION_VALID`: it always passes.
- Asynchronous evaluation execution: runs are synchronous despite the `queued` status and the
  cancel endpoint.
- Asynchronous document processing: it is an in-process background task, not a worker; there
  is no automatic recovery after a restart.
- LLM-as-judge: present as a disabled field only.
- The `model` field of `LLMConfig`: not editable in the UI and ignored under Azure OpenAI.

**Unsupported technical claims**
- "We developed / trained / fine-tuned an AI model." → integration of pre-trained models.
- "We measured groundedness / faithfulness / hallucination rate / precision / recall / MRR."
  → none are computed.
- "We implemented a vector database." → PostgreSQL + pgvector extension.
- "Token-based chunking with tiktoken." → word-based chunking.
- "Configurable chunk size and overlap." → hard-coded.
- "Real token usage measured." → heuristic estimates (`estimated_token_count`).
- "Fully automated RAG quality evaluation with academic metrics." → deterministic assertions.
- "Zero-downtime deployment / blue-green publication." → a single `active_version_id` switch.
- "Complete audit trail." → archive, delete, LLM config, RAG settings and API key
  regeneration are **not** audited.

---

# 24. FILES TO REVISIT LATER (short list)

Backend — Part I
1. `backend/services/ai_provider.py` — providers, streaming, reasoning deployments, errors
2. `backend/services/embeddings.py` + `backend/services/embedding_config.py` — embedding providers, dimensions
3. `backend/services/rag.py` — chunking, embedding orchestration, retrieval (pgvector + keyword)
4. `backend/services/document_ingestion.py` — extraction
5. `backend/routes/knowledge_routes.py` — KB/document API, statuses, reprocessing
6. `backend/routes/chat_routes.py` — `prepare_rag_generation`, `build_rag_response`, streaming
7. `backend/services/rag_settings.py` — retrieval defaults and clamping
8. `backend/models/{knowledge_base,document,chunk,vector_type,llm_config}.py`
9. `backend/services/evaluation_engine.py` + `backend/routes/evaluation_routes.py` + `backend/models/evaluation.py`
10. `backend/routes/health_routes.py` — RAG/AI diagnostics
11. `backend/routes/llm_config_routes.py` — **and the missing ownership check**

Backend — Part II
12. `backend/routes/version_routes.py` — lifecycle, publish, archive, delete, duplication
13. `backend/services/publication_readiness.py` — readiness checks + smoke test
14. `backend/routes/public_routes.py` — public chat, widget script, public REST API
15. `backend/services/unified_runtime.py` — version resolution, runtime logging
16. `backend/routes/channel_routes.py` + `backend/models/chatbot_channel.py`
17. `backend/models/version.py`, `backend/models/chatbot.py`, `backend/models/version_smoke_test.py`
18. `backend/services/auth.py` — `require_roles`, `require_workspace_manager`
19. `backend/services/audit.py` + `backend/models/audit_log.py` + `backend/models/runtime_log.py`
20. `backend/main.py` — router registration, CORS, startup validation
21. `backend/.env.example` — reference provider configuration

Frontend
22. `frontend/src/app/pages/knowledge-base/` — KB, RAG settings, retrieval tester
23. `frontend/src/app/pages/versions/` — LLM instructions, versions, readiness, publish
24. `frontend/src/app/pages/evaluations/` — evaluation center
25. `frontend/src/app/pages/chatbot-deployment/` — public link, widget, API key
26. `frontend/src/app/pages/public-chat/` — anonymous runtime
27. `frontend/src/app/services/api.ts` + `frontend/src/app/app.routes.ts`

Tests (read, never executed here)
28. `backend/tests/test_knowledge_ingestion_reliability.py`
29. `backend/tests/test_pgvector_retrieval.py`
30. `backend/tests/test_publication_readiness.py` + `test_publication_readiness_regression_gate.py`
31. `backend/tests/test_evaluation_center.py`
32. `backend/tests/test_runtime_logs.py`, `test_channel_removal.py`, `test_workspace_read_only_permissions.py`, `test_azure_openai_provider.py`

---

# 25. OPEN UNCERTAINTIES (verify before final writing)

| Question | File / function to check |
|---|---|
| Is there an ANN index (`ivfflat` / `hnsw`) on `chunks.embedding_vector`, or is retrieval an exact scan? | `backend/alembic/versions/f7b8c9d0e1f2_add_pgvector_embedding_column.py` and the live PostgreSQL schema |
| Is `Chunk.retrieval_score` ever written? | repository-wide search for `retrieval_score =` |
| Does the widget actually work cross-origin in the deployed configuration? | `ALLOWED_ORIGINS` in the deployment environment vs. `main.py::allowed_origins` |
| Are `queued` evaluation runs ever created (i.e. does any caller rely on the queued state)? | `evaluation_routes.run_evaluation`, `models/evaluation.EvaluationRun.status` default |
| Does any code path still write `Document.status = "processed"` (legacy), or is it only the column default? | `models/document.py` default vs. `sync_document_status` |

---

*End of Chapter 6 inspection report. Read-only: no source file modified, no test/build/lint/Docker/CI/deployment/Git command executed.*
