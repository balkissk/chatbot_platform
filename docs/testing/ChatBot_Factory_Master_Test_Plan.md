# ChatBot Factory Master Test Plan

Inspection date: 2026-09-18
Scope: read-only inspection of the implemented Angular frontend and FastAPI backend.
Source basis: `frontend/src/app/app.routes.ts`, route guards, page components/templates, `frontend/src/app/services/api.ts`, `backend/main.py`, `backend/routes/*`, `backend/services/*`, `backend/models/*`, deployment docs/workflows, and runtime configuration files.

## 1. Inspection Summary

Frontend inspected:
- Public routes: `/`, `/login`, `/forgot-password`, `/reset-password`, `/privacy-policy`, `/public-chat/:chatbotId`, `/chat/:chatbotId` redirect.
- Protected manager/admin shell: `/dashboard` guarded by `authGuard` and `roleGuard` for `admin` and `manager`.
- Manager workspace routes: profile, projects, project overview, project analytics/settings, assistant list, assistant overview, versions, evaluations, analytics, conversations, collected data, deployment, settings, flow builder, template selection, AI generator, flow test, knowledge base, Template QA.
- Admin routes: dashboard, users, chatbots, conversations, runtime logs, analytics, audit logs, platform settings.
- Layout: responsive side navigation, mobile drawer, breadcrumbs, topbar global search, account menu, logout.
- Implemented UI states: loading, empty, error, modals/confirmations, filters, pagination, copy actions, uploads, test panels, drawers/detail panels.

Backend inspected:
- FastAPI app includes routers for auth, projects, chatbots, versions, LLM config, knowledge, flow builder/template QA, authenticated chat test, public runtime API, channels, evaluations, admin analytics/logs, health, legal pages, platform settings, search.
- Auth uses HttpOnly access cookie `chatbot_factory_session` and rotating refresh cookie `chatbot_factory_refresh`; frontend stores only current user metadata in localStorage.
- Roles found: `admin`, `manager`, `end_user`.
- Write access for workspace resources is manager-only via `require_workspace_manager`; admin is read-only for workspace project/assistant operations but has admin-only screens and user/settings management.
- Public runtime supports unauthenticated public chat endpoints and API-key protected public REST endpoints.
- Azure behavior is implemented via profile/env loader, CORS origin configuration, GitHub Actions App Service deployment workflows, Angular runtime config, Azure OpenAI/embedding configuration checks, and production cookie defaults.

Security note: local `.env.*` files contain real-looking secret values. The test plan does not reproduce secrets and treats environment values as sensitive test evidence only.

## 2. Feature Inventory

| ID | Feature | Frontend route/component | Backend endpoint(s) | Allowed role(s) | Main actions | Testable |
|---|---|---|---|---|---|---|
| A | Authentication login/session | `/login`, `AuthService`, interceptors | `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me` | Public then all authenticated roles | login, refresh, logout, current user, expired token redirect | YES |
| A2 | Password reset | `/forgot-password`, `/reset-password` | `POST /auth/forgot-password`, `/auth/reset-password` | Public | request reset, reset by token | YES |
| B | User profile | `/dashboard/profile` | `GET/PUT /auth/me`, `PUT /auth/me/password` | Admin, Manager | view/update profile, change password | YES |
| C | Roles and route permissions | guards/layout | `require_roles`, `require_workspace_manager` | Admin, Manager, End User | route access, redirects, API enforcement | YES |
| D | Admin dashboard | `/admin/dashboard` | `GET /admin/analytics/overview`, health routes | Admin | platform KPIs, refresh | YES |
| D2 | Admin users | `/admin/users` | `/auth/users*` | Admin | list, search, filter, create invite, status, delete | YES |
| D3 | Admin chatbots | `/admin/chatbots` | `/admin/analytics/chatbots*` | Admin | list, filter, details modal, navigate to logs/conversations | YES |
| D4 | Admin conversations | `/admin/conversations` | `/admin/analytics/sessions*` | Admin | filter by chatbot, open transcript | YES |
| D5 | Admin analytics | `/admin/analytics` | `/admin/analytics/platform`, usage, channels, top-chatbots | Admin | range filter, charts/KPIs, refresh | YES |
| D6 | Runtime logs | `/admin/runtime-logs` | `GET /admin/analytics/runtime-logs` | Admin | filter/paginate runtime logs | YES |
| D7 | Audit logs | `/admin/audit-logs` | `GET /admin/analytics/audit-logs` | Admin | search/filter/date/paginate logs | YES |
| D8 | Platform settings | `/admin/platform-settings` | `GET/PUT /admin/platform-settings` | Admin | view/update platform name, support email, page size | YES |
| E | Projects | `/dashboard/projects`, project actions menu | `/projects`, `/projects/query`, `/projects/summary`, `/projects/{id}` | Admin read, Manager read/write own | create, search, filter, paginate, duplicate, archive, restore, delete, grid/table style UI if present | YES |
| E2 | Project overview/dashboard | `/dashboard/projects/:projectId` | `/projects/{id}/workspace-dashboard` | Admin read, Manager own | metrics, readiness center, knowledge gaps, recommendations, navigation | YES |
| E3 | Project analytics/settings | `/dashboard/projects/:projectId/analytics`, `/settings` | `/projects/{id}/analytics`, `PUT /projects/{id}` | Admin read analytics, Manager write settings | metrics, rename/update settings | YES |
| F | Assistants | `/projects/:projectId/chatbots`, overview/settings | `/chatbots`, `/projects/{project_id}/chatbots`, `/chatbots/{id}` | Admin read, Manager write own | list/search/open/update/delete/status | YES |
| G | Assistant creation | wizard in chatbots page, template/AI routes | `POST /chatbots`, setup/template-draft/ai-draft, `/assistants/ai-generate` | Manager | from scratch, from template, AI-generated setup, drafts | YES |
| H | Templates | `/templates`, shared template options | `/flow-templates`, apply/create template endpoints | Manager | list by purpose, select/apply/reapply, create template from flow | YES |
| I | Template QA | `/dashboard/template-qa`, `/:templateKey` | `/flow-templates/qa`, detail, patch, test, revisions | Manager only | list, filters, detail drawer, expanded view, tests, revision history, edit if owner/custom | YES |
| J | Flow Builder | `/flow` | flow node/transition CRUD, builder, templates | Manager | add/configure/move/delete nodes, transitions, variables, preview, templates | YES |
| K | Flow Validation | Flow builder/versions | `GET /versions/{id}/flow/validate`, readiness | Admin read, Manager | validate structure before test/publish | YES |
| L | Test Flow | `/flow/test`, preview in builder | `POST /chat/sessions`, `/chat`, `/chat/stream` | Admin/Manager authenticated; UI manager route | start session, send, multi-turn, variables, RAG | YES |
| M | Knowledge Base | `/knowledge`, embedded KB panel | `/versions/{id}/documents`, `/documents/*` | Admin read, Manager write | upload, list, inspect chunks, update, delete, reprocess | YES |
| N | Document processing | KB backend | ingestion services, chunk/embedding reprocess | Manager write | text/PDF extraction, chunking, embedding states | YES |
| O | RAG | KB RAG test and runtime | `/versions/{id}/rag-test`, chat runtime | Admin/Manager test, public runtime | retrieval, source references, fallback/settings | YES |
| P | Evaluation Center | `/evaluations` | `/assistants/{id}/datasets`, cases, runs, compare, policy | Manager routes; backend should enforce manager for writes | datasets, cases, assertions, run, compare, policy | YES |
| Q | Versions | `/versions` | `/versions`, duplicate/archive/delete, LLM config | Admin read, Manager write | create, select, duplicate, archive, delete, instructions | YES |
| R | Publishing | `/versions`, deployment | `PUT /versions/{id}/publish`, readiness, smoke-test | Manager | readiness, publish with warnings, active version | YES |
| S | Deployment Center | `/deployment` | channels, API key, public metadata | Manager | public URLs, widget snippet, API key regenerate, channel status/test | YES |
| T | Public Chat | `/public-chat/:chatbotId`, `/chat/:id` | `/public/chatbots/{id}`, `/public/chat*` | Anonymous | hosted chat session, messages, feedback | YES |
| U | Embedded Web Widget | external script | `GET /public/widget.js`, `/public/chat*` | Anonymous | load bubble, open/close, send messages | YES |
| V | Public REST API | no dedicated page except deployment info | `/public/api/chat/sessions`, `/public/api/chat` | API key caller | API-key chat session/message | YES |
| W | Conversations | `/conversations`, admin conversations | `/chatbots/{id}/conversations*`, admin sessions | Admin read all, Manager own | list, detail, filters, follow-up, CSV export if UI button exists | YES |
| X | Knowledge gaps | project overview, unanswered questions | `/chatbots/{id}/conversations/unanswered`, workspace dashboard | Admin/Manager read | unanswered/gap indicators | YES |
| Y | Analytics | project/assistant/admin analytics | `/projects/{id}/analytics`, `/chatbots/{id}/analytics`, `/admin/analytics/*` | Admin/Manager scoped | KPIs, charts, channels, runtime metrics | YES |
| Z | Runtime logs | admin runtime logs | `/admin/analytics/runtime-logs` | Admin | inspect runtime success/failure | YES |
| AA | Audit logs | admin audit logs | `/admin/analytics/audit-logs` | Admin | inspect audit trail | YES |
| AB | Platform settings | admin settings | `/admin/platform-settings` | Admin | edit validation and persistence | YES |
| AC | Global search | layout topbar | `GET /search` | Admin/Manager scoped | project/assistant/knowledge results | YES |
| AD | Responsive/mobile | all layouts/pages | N/A | All UI roles | drawer, overflow, mobile forms/tables | YES |
| AE | Error handling | global/page states | all endpoints | All | 400/401/403/404/409/422/500 states | YES |
| AF | Azure production | deployed frontend/backend | health, API, app runtime | All relevant | CORS, cookies, cold start, public URLs | YES |
| AG | Channels | deployment center | `/chatbots/{id}/channels/*` | Admin read, Manager write | web/widget/api channel create/update/test/delete | YES |
| AH | Legal pages | public | `/privacy-policy`, `/terms`, `/data-deletion` backend; `/privacy-policy` frontend | Public | view legal pages | PARTIAL |

## 3. Partially Implemented / Not Implemented / Not Testable

| Area | Status | Reason |
|---|---|---|
| End-user authenticated workspace | PARTIALLY IMPLEMENTED | Role exists and `homeForRole` routes end users to `/chat/3`, but no broad authenticated end-user dashboard routes exist. Test only redirect/access denial and public chat behavior. |
| Register route | PARTIALLY IMPLEMENTED | Frontend service and route/component exist, but no inspected backend `/auth/register` route is implemented. Mark registration backend tests as not implemented. |
| Knowledge base entity CRUD | PARTIALLY IMPLEMENTED | Backend creates/uses knowledge base per version internally; no standalone create/select KB UI/API beyond document upload/list. |
| Flow node types `api_request`, `confidence_check`, `action` | PARTIALLY IMPLEMENTED | Backend/runtime validation supports legacy/placeholder behavior, but frontend hides these block types. Test API-level validation/runtime only if created by template/API. |
| Meeting scheduler, AI router/classifier, lead score | PARTIALLY IMPLEMENTED | Runtime/validation references exist, but frontend visible block list does not expose them. |
| Rollback published version | NOT IMPLEMENTED | Version duplicate/archive/delete/publish exist, but no explicit rollback endpoint was found. Rollback can be simulated by publishing another existing version only if publish allows it. |
| Dedicated deployment of external channels | PARTIALLY IMPLEMENTED | Channel state/config/test endpoints exist; no real external provider integration beyond public chat/widget/API was found. |
| CSV export in conversation history | PARTIALLY IMPLEMENTED | Evaluation export exists; conversation CSV export must be tested only if the actual conversation page exposes it. If absent in UI, mark SKIPPED. |
| Public REST streaming | NOT IMPLEMENTED | Public API has non-stream API-key chat endpoints; streaming endpoint is for public chat, not API-key REST. |
| OCR for scanned PDFs | NOT IMPLEMENTED | PDF extraction explicitly fails image-only PDFs. |
| Admin Template QA | NOT IMPLEMENTED | Template QA is manager-only in frontend routes. Do not test admin access as allowed. |

## 4. Permission Matrix

| Feature group | Admin | Manager | End User | Anonymous |
|---|---:|---:|---:|---:|
| Login/reset/legal/public chat | Allowed as applicable | Allowed as applicable | Allowed as applicable | Allowed for public/reset/legal |
| Dashboard shell | Allowed | Allowed | Denied/redirect | Denied/redirect |
| Profile | Allowed | Allowed | No dashboard route | Denied |
| Admin dashboard/users/chatbots/conversations/logs/settings | Allowed | Denied | Denied | Denied |
| Template QA | Denied by route redirect | Allowed | Denied | Denied |
| Project/assistant read | Allowed, scoped all | Allowed, scoped own | Denied | Denied |
| Project/assistant write | Denied by `require_workspace_manager` | Allowed own | Denied | Denied |
| Flow/knowledge/version/publish write | Denied by `require_workspace_manager` | Allowed own | Denied | Denied |
| Evaluations | Treat admin as read if backend allows; UI manager-focused | Allowed own | Denied | Denied |
| Public chat/widget | Allowed if public URL | Allowed if public URL | Allowed if public URL | Allowed if published/active |
| Public REST API | Requires assistant API key | Requires assistant API key | Requires assistant API key | Requires assistant API key |
| Global search | Allowed all visible | Allowed own visible | Denied | Denied |

## 5. Implemented Flow Block Types

Visible in the flow builder:
- `message`
- `question`
- `buttons`
- `end`
- `rag_answer`
- `knowledge_search`
- `collect_name`
- `collect_email`
- `collect_phone`
- `condition`
- `set_variable`
- `handoff`

Hidden/placeholder or legacy types present in code:
- `api_request`
- `confidence_check`
- `action`
- Runtime/validation references: `meeting_scheduler`, `ai_router`, `ai_classifier`, `lead_score`.

## 6. Test Strategy

Test levels:
- Manual browser: primary end-to-end validation for UI workflows.
- Swagger: API contract/security testing for critical FastAPI endpoints.
- Chrome DevTools: CORS, cookies, console/network errors, responsive inspection, public widget script loading.
- Playwright: small automated regression set for the most valuable journeys only.
- JMeter: focused load tests for runtime chat/RAG and public API endpoints only.
- Azure: production smoke and acceptance checks without changing Azure configuration.
- Qase: recommended system of record for test case execution, evidence, status, and defects.

Manual status values: NOT RUN, PASS, FAIL, BLOCKED, SKIPPED.
Priorities: P0 - Critical, P1 - High, P2 - Medium, P3 - Low.

## 7. Test Data

Prepare these records before execution:
- Admin account: active `admin` user.
- Manager A account: active `manager` with own projects.
- Manager B account: active `manager` for isolation/forbidden tests.
- End-user account: active `end_user` for denied-route checks.
- Project A: clean active project owned by Manager A.
- Assistant A: active assistant in Project A, created from scratch.
- Assistant B: assistant from template `customer_support_rag` or equivalent implemented template.
- Assistant C: assistant created by AI draft if Azure OpenAI is configured.
- Draft version with valid simple flow: start -> message -> question -> rag_answer -> end.
- Uploaded text document with known answer sentence, and optional PDF with extractable text.
- Published version for public chat/widget/API testing.
- Evaluation dataset with at least one passing case, one failing keyword case, and one RAG source assertion case.

## 8. Environment Coverage

| Environment | Purpose |
|---|---|
| Local development | Core manual functional, Swagger, quick Playwright planning validation. |
| Azure production | Smoke, CORS/cookie/public URL/API/widget/RAG acceptance and cold/warm behavior. |
| Performance test environment | JMeter runtime tests, preferably production-like data and isolated rate limits. |

## 9. Defect Severity

| Severity | Definition |
|---|---|
| BLOCKER | Application or critical workflow cannot continue. |
| CRITICAL | Major critical functionality fails with no acceptable workaround. |
| MAJOR | Important functionality fails but workaround exists. |
| MINOR | Small functional/UI issue. |
| COSMETIC | Visual issue only. |

## 10. Recommended Execution Order

1. Phase 1 - Smoke
2. Phase 2 - Manual Functional
3. Phase 3 - Permissions / Negative
4. Phase 4 - Swagger APIs
5. Phase 5 - Azure Production
6. Phase 6 - Playwright Regression
7. Phase 7 - JMeter Performance
8. Phase 8 - Final Regression

## 11. Practical Time Estimate

Estimated generated coverage: 172 manual functional/negative/permission cases, 64 Swagger endpoint tests, 10 Playwright scenarios, 7 JMeter scenarios, 24 Azure production acceptance checks.

Recommended PFE execution schedule:
- Day 1: P0 smoke, authentication, admin/users, projects, assistant creation, flow builder, basic Test Flow.
- Day 2: knowledge/RAG, versions/publish/deployment, public chat/widget/API, conversations, analytics/logs, Template QA, Swagger API suite, Azure smoke.
- Half Day 3: Playwright regression execution, JMeter focused runtime tests, quick regression, defect review, final evidence cleanup.

Honest estimate: 2.5 to 3.5 days depending on data setup, Azure OpenAI availability, and whether document embedding/RAG calls are rate-limited.

## 12. Documentation Set

Detailed test cases: `ChatBot_Factory_Test_Cases.md`
Smoke suite: `ChatBot_Factory_Smoke_Suite.md`
Swagger API suite: `ChatBot_Factory_Swagger_Test_Plan.md`
Playwright plan: `ChatBot_Factory_Playwright_Plan.md`
JMeter plan: `ChatBot_Factory_JMeter_Plan.md`
Azure acceptance: `ChatBot_Factory_Azure_Acceptance.md`
Traceability matrix: `ChatBot_Factory_Traceability_Matrix.md`

## 13. Regression Suites

Quick Regression:
- AUTH-001, AUTH-002, AUTH-006, PERM-001, PERM-003
- PROJ-002, ASST-002, FLOW-003, FLOW-015
- KB-002, RAG-003, TEST-001
- PUB-001, PUBCHAT-001, PUBCHAT-002, WIDGET-001, REST-002
- ADMIN-001, ADMIN-013

Full Regression:
- All P0/P1 manual cases in `ChatBot_Factory_Test_Cases.md`.
- All critical Swagger rows in `ChatBot_Factory_Swagger_Test_Plan.md`.
- Playwright PW-01 through PW-10 after automation is implemented.
- JMeter JM-02, JM-04, JM-05, JM-07 for runtime capacity snapshots.
- Azure AZ-01 through AZ-24 for production acceptance.
