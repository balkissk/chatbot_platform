# ChatBot Factory - Current Manager Functionalities

Inspection scope: current implementation only. No future Admin/Manager redesign is included.

## Core Access Rule

Manager access is generally enforced by ownership through:

`Project.user_id == current_user.id`

Verified in:

- `backend/routes/project_routes.py`: `project_query_for_user()` filters Manager projects by `Project.user_id == current_user.id`.
- `backend/routes/chatbot_routes.py`: chatbot access checks the chatbot's project ownership.
- `backend/routes/version_routes.py`, `backend/routes/flow_routes.py`, `backend/routes/knowledge_routes.py`, and `backend/routes/evaluation_routes.py`: versions, flows, documents, and evaluations inherit access through owned chatbot/project.

Important exceptions:

- `backend/routes/llm_config_routes.py`: Manager can read/write LLM config by `version_id`, but there is no ownership check.
- `backend/routes/chat_routes.py`: authenticated chat/version preview is role-gated but does not verify that the Manager owns the chatbot/project. The frontend normally reaches it through owned assistant context, but the backend check itself is weaker.

## Authentication And Profile

Manager can:

- Log in, log out, request password reset, and reset password.
  - Access: Write/session action.
  - Scope: Not project-scoped.
  - Frontend: `login`, `forgot-password`, `reset-password`.
  - Backend: `/auth/login`, `/auth/logout`, `/auth/forgot-password`, `/auth/reset-password`.

- View current profile.
  - Access: Read.
  - Scope: Own account only.
  - Frontend: `profile`.
  - Backend: `GET /auth/me`.

- Update own name and password.
  - Access: Write.
  - Scope: Own account only.
  - Frontend: `profile`.
  - Backend: `PUT /auth/me`, `PUT /auth/me/password`.

Manager cannot:

- Access user administration.
  - Backend user admin endpoints require `admin`.

## Projects

Frontend pages:

- `projects`
- `project-overview`
- `project-settings`
- `project-analytics`

Manager can:

- Create projects.
  - Access: Write.
  - Scope: Created project is assigned to `current_user.id`.
  - Backend: `POST /projects`.

- List, search, filter, sort, and summarize own projects.
  - Access: Read.
  - Scope: Own projects only.
  - Backend: `GET /projects`, `GET /projects/query`, `GET /projects/summary`.

- View project overview and workspace dashboard.
  - Access: Read.
  - Scope: Own projects only.
  - Backend: `GET /projects/{project_id}`, `GET /projects/{project_id}/workspace-dashboard`.

- View project analytics.
  - Access: Read.
  - Scope: Own projects only.
  - Backend: `GET /projects/{project_id}/analytics`.

- Update project name and description.
  - Access: Write.
  - Scope: Own projects only.
  - Backend: `PUT /projects/{project_id}`.

- Archive, restore, delete, and duplicate projects.
  - Access: Write.
  - Scope: Own projects only.
  - Backend: `PUT /projects/{project_id}/archive`, `PUT /projects/{project_id}/restore`, `DELETE /projects/{project_id}`, `POST /projects/{project_id}/duplicate`.

## Assistants

Frontend pages:

- `chatbots`
- `assistant-overview`
- `assistant-settings`
- `ai-generator`

Manager can:

- Create assistant inside an owned project.
  - Access: Write.
  - Scope: Own projects only.
  - Backend: `POST /chatbots`.

- List own assistants globally or by project.
  - Access: Read.
  - Scope: Own assistants only.
  - Backend: `GET /chatbots`, `GET /projects/{project_id}/chatbots`.

- View assistant details, setup, analytics, and operations dashboard.
  - Access: Read.
  - Scope: Own assistants only.
  - Backend: `GET /chatbots/{id}`, `GET /chatbots/{id}/setup`, `GET /chatbots/{id}/analytics`, `GET /chatbots/{id}/operations-dashboard`.

- Update assistant metadata and setup.
  - Access: Write.
  - Scope: Own assistants only.
  - Backend: `PUT /chatbots/{id}`, `PATCH /chatbots/{id}/setup`.

- Regenerate draft from original template or AI provenance.
  - Access: Write.
  - Scope: Own assistants only.
  - Backend: `POST /chatbots/{id}/setup/template-draft`, `POST /chatbots/{id}/setup/ai-draft`.

- Toggle assistant active status.
  - Access: Write.
  - Scope: Own assistants only.
  - Backend: `PUT /chatbots/{id}/status`.

- Delete assistant.
  - Access: Write.
  - Scope: Own assistants only.
  - Backend: `DELETE /chatbots/{id}`.

- Regenerate public API key.
  - Access: Write.
  - Scope: Own assistants only.
  - Backend: `PUT /chatbots/{id}/api-key/regenerate`.

## Flow Builder

Frontend pages:

- `flow-builder`
- `flow-test`
- `template-selection`
- `ai-generator`

Manager can:

- Open builder context and read version flow.
  - Access: Read.
  - Scope: Own assistants/versions only.
  - Backend: `GET /chatbots/{chatbot_id}/builder`, `GET /versions/{version_id}/flow`.

- Validate flow.
  - Access: Read.
  - Scope: Own versions only.
  - Backend: `GET /versions/{version_id}/flow/validate`.

- Create, update, and delete flow nodes.
  - Access: Write.
  - Scope: Own flows only.
  - Backend: `POST /flows/{flow_id}/nodes`, `PUT /flow-nodes/{node_id}`, `DELETE /flow-nodes/{node_id}`.

- Create, update, and delete transitions.
  - Access: Write.
  - Scope: Own flows only.
  - Backend: `POST /flows/{flow_id}/transitions`, `PUT /flow-transitions/{transition_id}`, `DELETE /flow-transitions/{transition_id}`.

- Apply built-in/custom templates or generated AI flow to own flow.
  - Access: Write.
  - Scope: Own flows only.
  - Backend: `POST /flows/{flow_id}/template`, `POST /flows/{flow_id}/generated`.

- Generate assistant flow with AI.
  - Access: Write/generation action.
  - Scope: Role-gated to Manager/Admin, not directly project-scoped because it generates a payload before applying.
  - Backend: `POST /assistants/ai-generate`.

## Knowledge Base / RAG

Frontend page:

- `knowledge-base`

Manager can:

- Upload documents to a version knowledge base.
  - Access: Write.
  - Scope: Own versions only.
  - Backend: `POST /versions/{version_id}/documents`.

- List documents, read document metadata, and read chunks.
  - Access: Read.
  - Scope: Own versions/documents only.
  - Backend: `GET /versions/{version_id}/documents`, `GET /documents/{document_id}`, `GET /documents/{document_id}/chunks`.

- Rename or update document metadata.
  - Access: Write.
  - Scope: Own documents only.
  - Backend: `PUT /documents/{document_id}`.

- Reprocess embeddings or chunks.
  - Access: Write.
  - Scope: Own documents only.
  - Backend: `POST /documents/{document_id}/embeddings/reprocess`, `POST /documents/{document_id}/chunks/reprocess`.

- Delete documents.
  - Access: Write.
  - Scope: Own documents only.
  - Backend: `DELETE /documents/{document_id}`.

- Test RAG retrieval.
  - Access: Read/test action.
  - Scope: Own versions only.
  - Backend: `POST /versions/{version_id}/rag-test`.

- Read and update chatbot RAG settings.
  - Access: Read/Write.
  - Scope: Own assistant only.
  - Backend: `GET /chatbots/{id}/rag-settings`, `PUT /chatbots/{id}/rag-settings`.

## Testing / Evaluations

Frontend pages:

- `flow-test`
- `evaluations`

Manager can:

- Start authenticated chat sessions and test assistant flow.
  - Access: Write conversation session/messages.
  - Scope: Frontend normally uses owned assistant context; backend ownership is not verified in `chat_routes.py`.
  - Backend: `POST /chat/sessions`, `POST /chat`, `POST /chat/stream`.

- Create, list, read, update, archive, restore, and delete evaluation datasets.
  - Access: Read/Write.
  - Scope: Own assistants only.
  - Backend: `/evaluations/assistants/{assistant_id}/datasets`, `/evaluations/datasets/{dataset_id}`.

- Create, update, duplicate, reorder, enable, delete, import, and export evaluation cases.
  - Access: Read/Write.
  - Scope: Own datasets only.
  - Backend: `/evaluations/datasets/{dataset_id}/cases`, `/evaluations/cases/{case_id}`, import/export endpoints.

- Run, cancel, read, and compare evaluation runs/results.
  - Access: Read/Write.
  - Scope: Own assistant/run/version only.
  - Backend: `/evaluations/runs`, `/evaluations/runs/{run_id}`, `/evaluations/results/{result_id}`, `/evaluations/compare`.

- Read and update evaluation publish policy.
  - Access: Read/Write.
  - Scope: Own assistant only.
  - Backend: `GET /evaluations/assistants/{assistant_id}/policy`, `PUT /evaluations/assistants/{assistant_id}/policy`.

## Versions / Validation / Publication

Frontend page:

- `versions`

Manager can:

- Create a version.
  - Access: Write.
  - Scope: Own assistant only.
  - Backend: `POST /versions`.

- Duplicate a version.
  - Access: Write.
  - Scope: Own version only.
  - Backend: `POST /versions/{version_id}/duplicate`.

- List versions.
  - Access: Read.
  - Scope: Own assistant only.
  - Backend: `GET /chatbots/{chatbot_id}/versions`.

- Read publication readiness.
  - Access: Read.
  - Scope: Own version only.
  - Backend: `GET /versions/{version_id}/readiness`.

- Run smoke test.
  - Access: Write/test result.
  - Scope: Own version only.
  - Backend: `POST /versions/{version_id}/smoke-test`.

- Publish version.
  - Access: Write.
  - Scope: Own version only.
  - Restrictions: Blocked by readiness checks and flow validation.
  - Backend: `PUT /versions/{version_id}/publish`.

- Archive or delete version.
  - Access: Write.
  - Scope: Own version only.
  - Restrictions: Cannot archive active version; cannot delete active, published, or last version.
  - Backend: `PUT /versions/{version_id}/archive`, `DELETE /versions/{version_id}`.

## Deployment / Public Channels

Frontend page:

- `chatbot-deployment`

Manager can:

- List deployment channels.
  - Access: Read.
  - Scope: Own assistant only.
  - Backend: `GET /chatbots/{chatbot_id}/channels`.

- Create, update, delete, and test channels.
  - Access: Write.
  - Scope: Own assistant only.
  - Supported channels: `web`, `widget`, `api`.
  - Backend: channel routes.

- Clear channel errors.
  - Access: Write.
  - Scope: Own assistant only.
  - Backend: `PATCH /chatbots/{chatbot_id}/channels/{channel_type}/clear-error`.

- Assign `deployed_version_id` on a channel.
  - Access: Write.
  - Scope: Own assistant only through channel update.
  - Ownership of `deployed_version_id` itself: not verified.

Public runtime endpoints are not Manager-specific.

## Conversations / Collected Data

Frontend pages:

- `chatbot-conversations`
- `collected-data`

Manager can:

- List assistant conversations with filters.
  - Access: Read.
  - Scope: Own assistant only.
  - Backend: `GET /chatbots/{id}/conversations`.

- View conversation details, messages, and variables.
  - Access: Read.
  - Scope: Own assistant only.
  - Backend: `GET /chatbots/{id}/conversations/{session_id}`.

- View unanswered questions.
  - Access: Read.
  - Scope: Own assistant only.
  - Backend: `GET /chatbots/{id}/conversations/unanswered`.

- View collected user variables/data.
  - Access: Read.
  - Scope: Own assistant only.
  - Backend: `GET /chatbots/{id}/collected-data`.

- Update follow-up status and Manager note on a conversation.
  - Access: Write.
  - Scope: Own assistant/session only.
  - Backend: `PATCH /chatbots/{id}/conversations/{session_id}/follow-up`.

## Analytics / Logs

Manager can access scoped analytics:

- Project analytics.
  - Access: Read.
  - Scope: Own project only.

- Assistant analytics and operations dashboard.
  - Access: Read.
  - Scope: Own assistant only.

- Conversation-derived quality signals, runtime failures, fallback/coverage information in project and assistant dashboards.
  - Access: Read.
  - Scope: Own project/assistant only.

Manager cannot access global admin analytics/logs:

- `/admin/**` frontend routes require `admin`.
- Backend admin analytics and platform settings endpoints require `admin`.

## Templates

Frontend pages:

- `template-selection`
- `template-qa`

Manager can:

- List/read built-in and accessible custom flow templates.
  - Access: Read.
  - Scope: Built-ins plus own/shared custom templates.
  - Backend: `GET /flow-templates`, `GET /flow-templates/{template_key}`.

- Run template QA/tests.
  - Access: Read/test action.
  - Scope: Accessible templates.
  - Backend: `GET /flow-templates/qa`, `POST /flow-templates/{template_key}/test`.

- Create a custom template from an owned flow.
  - Access: Write.
  - Scope: Own flow only; owner becomes current Manager.
  - Backend: `POST /flows/{flow_id}/template-library`.

- Update own custom template metadata/test scenarios.
  - Access: Write.
  - Scope: Own templates only.
  - Restrictions: Built-in templates are read-only; shared templates not owned are not editable.
  - Backend: `PATCH /flow-templates/{template_key}`.

- Create template revisions from an owned flow into an owned template.
  - Access: Write.
  - Scope: Own flow and own template only.
  - Backend: `POST /flows/{flow_id}/template-library/{template_key}/revisions`.

- Apply accessible template to owned flow.
  - Access: Write.
  - Scope: Own flow only.
  - Backend: `POST /flows/{flow_id}/template`.

## Simplified Chapter Summary

Chapter 3:

- Manager functionalities related to authentication/access: login/logout, password reset, view/update own profile, change own password; no user administration; no admin area.

Chapter 4:

- Manager functionalities related to projects and assistants: create/list/view/update/archive/restore/delete/duplicate own projects; create/list/view/update/delete/toggle own assistants; manage setup, API key, assistant status.

Chapter 5:

- Manager functionalities related to conversational flows: build/read/validate/edit own flows; manage nodes/transitions; apply templates; generate/apply AI flows; test chat through dashboard, with backend ownership caveat.

Chapter 6:

- Manager functionalities related to LLM, Knowledge Base, RAG, testing, versions, validation and publication: manage documents/chunks/RAG settings for own assistants; run RAG tests; manage versions; run readiness/smoke tests; publish valid versions; manage evaluations and evaluation policies. LLM config endpoint is role-gated but not ownership-gated in current backend.

Chapter 7:

- Manager functionalities related to deployment or production: configure `web`, `widget`, and `api` channels for own assistants, test channels, clear channel errors, regenerate public API key, and assign deployed versions. Public runtime endpoints themselves are not Manager-specific.
