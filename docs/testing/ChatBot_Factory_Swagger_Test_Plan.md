# ChatBot Factory Swagger Test Plan

Tool: Swagger UI for the FastAPI backend. Do not use Postman for this suite.
Headers:
- Authenticated endpoints: browser session cookies from `/auth/login` in Swagger-enabled browser.
- Public REST API endpoints: `x-chatbot-api-key: <assistant public_api_key>`.
- Public chat/widget endpoints: no auth unless endpoint requires API key.

For every critical endpoint category below execute these variants when applicable: valid request, missing required field, invalid payload, invalid ID, unauthorized request, forbidden role, not found, duplicate/conflict.

## Critical Endpoint Matrix

| ID | Category | Method URL | Body example | Expected success | Negative/permission checks |
|---|---|---|---|---|---|
| SW-AUTH-01 | Authentication | POST `/auth/login` | `{ "email":"manager@example.com", "password":"Password1" }` | 200 user object and auth cookies | Missing email/password 422; bad password 401; rate limit after repeated failures |
| SW-AUTH-02 | Authentication | POST `/auth/refresh` | `{}` | 200 message and rotated refresh cookie | Missing/invalid refresh cookie 401 |
| SW-AUTH-03 | Authentication | POST `/auth/logout` | `{}` | 200 and cookies cleared | Repeated logout safe |
| SW-AUTH-04 | Authentication | POST `/auth/forgot-password` | `{ "email":"user@example.com" }` | 200 generic message | Unknown email same message; rate limit |
| SW-AUTH-05 | Authentication | POST `/auth/reset-password` | `{ "token":"token", "new_password":"StrongPass1" }` | 200 message | Invalid token 400; weak password 422/400 |
| SW-PROF-01 | Profile | GET `/auth/me` | none | 200 current user | Unauthenticated 401 |
| SW-PROF-02 | Profile | PUT `/auth/me` | `{ "name":"New Name" }` | 200 updated user | Blank name 400/422; unauth 401 |
| SW-PROF-03 | Profile | PUT `/auth/me/password` | `{ "current_password":"OldPass1", "new_password":"NewPass1" }` | 200 message | Wrong current 400; weak new 422/400 |
| SW-USR-01 | Users/Admin | GET `/auth/users?page=1&page_size=10&role=manager&status=active` | none | 200 paged list | Manager 403; unauth 401; invalid role 400 |
| SW-USR-02 | Users/Admin | POST `/auth/users` | `{ "name":"QA Manager", "email":"qa@example.com", "role":"manager" }` | 200 user | Duplicate email 400/409; invalid role 400; manager 403 |
| SW-USR-03 | Users/Admin | PUT `/auth/users/{user_id}/status` | `{ "status":"inactive" }` | 200 user | Invalid ID 404; last admin blocked; manager 403 |
| SW-USR-04 | Users/Admin | DELETE `/auth/users/{user_id}` | none | 200/delete message | Dependency blocked; last admin/self checks; manager 403 |
| SW-PROJ-01 | Projects | POST `/projects` | `{ "name":"QA Project", "description":"Smoke" }` | 200 project | Admin 403; blank name 400; unauth 401 |
| SW-PROJ-02 | Projects | GET `/projects?search=qa&status=active&page=1&page_size=10` | none | 200 list | Invalid status/sort 400; unauth 401 |
| SW-PROJ-03 | Projects | GET `/projects/query?...` | none | 200 paged response | Manager owner_id for other user 403; invalid page 422 |
| SW-PROJ-04 | Projects | GET `/projects/{project_id}` | none | 200 overview | Other manager/invalid ID 404; unauth 401 |
| SW-PROJ-05 | Projects | PUT `/projects/{project_id}` | `{ "name":"Renamed", "description":"Updated" }` | 200 project | Admin 403; blank name 400; invalid ID 404 |
| SW-PROJ-06 | Projects | POST `/projects/{project_id}/duplicate` | none | 200 copy | Admin 403; not found 404 |
| SW-PROJ-07 | Projects | PUT `/projects/{project_id}/archive` then `/restore` | none | 200 project | Admin 403; not found 404 |
| SW-PROJ-08 | Projects | DELETE `/projects/{project_id}` | none | 200 message | Admin 403; other manager 404/403 |
| SW-ASST-01 | Assistants | POST `/chatbots` | `{ "name":"QA Bot", "project_id":1, "language":"en", "channel":"web_widget", "purpose":"custom" }` | 200 chatbot | Admin 403; invalid language/channel 400; missing project 404 |
| SW-ASST-02 | Assistants | GET `/projects/{project_id}/chatbots` | none | 200 list | Other manager 404/empty scoped; unauth 401 |
| SW-ASST-03 | Assistants | GET `/chatbots/{id}` and `/setup` | none | 200 details/setup | Invalid ID 404; unauth 401 |
| SW-ASST-04 | Assistants | PATCH `/chatbots/{id}/setup` | Setup fields | 200 setup | Blank name 400; admin 403 |
| SW-ASST-05 | Assistants | PUT `/chatbots/{id}` | `{ "name":"New", "description":"D", "language":"fr", "channel":"public_chat" }` | 200 | Attempt creation mode change 400; admin 403 |
| SW-ASST-06 | Assistants | PUT `/chatbots/{id}/status` | `{ "is_active":false }` | 200 | Admin 403; invalid ID 404 |
| SW-ASST-07 | Assistants | PUT `/chatbots/{id}/api-key/regenerate` | none | 200 new key | Admin 403; invalid ID 404 |
| SW-ASST-08 | Assistants | DELETE `/chatbots/{id}` | none | 200 deleted | Admin 403; invalid ID 404 |
| SW-CHAN-01 | Deployment | GET `/chatbots/{id}/channels` | none | 200 channels web/widget/api | Unauth 401; invalid bot 404 |
| SW-CHAN-02 | Deployment | POST/PUT `/chatbots/{id}/channels/{channel_type}` | `{ "status":"connected", "config_json":{} }` | 200 channel | Unsupported channel 400; duplicate POST 409; admin 403 |
| SW-CHAN-03 | Deployment | POST `/chatbots/{id}/channels/{type}/test` | none | 200 test status | Admin 403; invalid type 400 |
| SW-CHAN-04 | Deployment | PATCH clear-error / DELETE channel | none | 200 | Missing channel clear-error 404; admin 403 |
| SW-VER-01 | Versions | POST `/versions` | `{ "chatbot_id":1 }` | 200 draft version | Admin 403; invalid bot 404 |
| SW-VER-02 | Versions | GET `/chatbots/{id}/versions` | none | 200 list | Invalid bot 404; unauth 401 |
| SW-VER-03 | Versions | GET `/versions/{id}/readiness` | none | 200 checks | Invalid version 404 |
| SW-VER-04 | Versions | POST `/versions/{id}/smoke-test` | none | 200 smoke result | Admin 403; invalid version 404 |
| SW-VER-05 | Versions | PUT `/versions/{id}/publish?confirm_warnings=false` | none | 200 published | Blockers 400; warnings require confirm; admin 403 |
| SW-VER-06 | Versions | POST duplicate / PUT archive / DELETE version | none | 200 | Published/active delete blocked; admin 403 |
| SW-LLM-01 | LLM Config | POST `/llm-config` | `{ "version_id":1, "model":"gpt-5-mini", "temperature":0.2, "system_prompt":"..." }` | 200 config | Admin 403; invalid version 404 |
| SW-LLM-02 | LLM Config | GET `/llm-config/{version_id}` | none | 200 config | Invalid version 404 |
| SW-FLOW-01 | Flow | GET `/chatbots/{id}/builder` | none | 200 builder context | Invalid bot 404; unauth 401 |
| SW-FLOW-02 | Flow | GET `/versions/{id}/flow` and `/flow/validate` | none | 200 flow/validation | Invalid version 404 |
| SW-FLOW-03 | Flow | POST `/flows/{flow_id}/nodes` | Node create payload | 200 node | Invalid type/config 400/422; admin 403 |
| SW-FLOW-04 | Flow | PUT/DELETE `/flow-nodes/{node_id}` | Node update | 200/delete | Invalid node 404; admin 403 |
| SW-FLOW-05 | Flow | POST `/flows/{id}/transitions` | `{ "source_node_key":"start", "target_node_key":"node_1", "label":"next" }` | 200 transition | Invalid source/target 400/404; duplicate output validation later |
| SW-FLOW-06 | Flow | PUT/DELETE `/flow-transitions/{id}` | Transition update | 200/delete | Invalid ID 404; admin 403 |
| SW-TPL-01 | Templates | GET `/flow-templates?exposed_only=true` | none | 200 list | Unauth 401 |
| SW-TPL-02 | Template QA | GET `/flow-templates/qa` and `/flow-templates/{key}` | none | 200 report/detail | Admin 403; invalid key 404 |
| SW-TPL-03 | Template QA | PATCH `/flow-templates/{key}` | Template updates | 200 detail | Non-editable/built-in denied; invalid payload 400 |
| SW-TPL-04 | Template QA | POST `/flow-templates/{key}/test` | Scenario messages/variables | 200 test result | Invalid JSON/payload 422; invalid key 404 |
| SW-KB-01 | Knowledge | POST `/versions/{id}/documents` | `{ "filename":"faq.txt", "content":"Known answer", "content_type":"text/plain" }` | 200 document | Blank filename 400; duplicate 409; admin 403 |
| SW-KB-02 | Knowledge | GET `/versions/{id}/documents`, `/documents/{id}`, `/documents/{id}/chunks` | none | 200 docs/chunks | Invalid IDs 404; unauth 401 |
| SW-KB-03 | Knowledge | PUT `/documents/{id}` | `{ "filename":"renamed.txt" }` | 200 doc | Blank filename 400; admin 403 |
| SW-KB-04 | Knowledge | POST `/documents/{id}/embeddings/reprocess` and `/chunks/reprocess` | none | 200 counts | Missing raw_text 400; admin 403 |
| SW-KB-05 | Knowledge | POST `/versions/{id}/rag-test` | `{ "question":"Known answer?", "limit":4 }` | 200 chunks | Empty question 400; invalid version 404 |
| SW-KB-06 | Knowledge | DELETE `/documents/{id}` | none | 200 | Admin 403; invalid ID 404 |
| SW-CHAT-01 | Test Chat | POST `/chat/sessions` | `{ "chatbot_id":1, "version_id":1, "language":"en" }` | 200 session | Invalid version/bot 404; unauth 401 |
| SW-CHAT-02 | Test Chat | POST `/chat` | `{ "chatbot_id":1, "session_id":1, "message":"hello" }` | 200 response | Other user session 403; invalid session 404 |
| SW-EVAL-01 | Evaluations | POST/GET `/assistants/{id}/datasets` | `{ "name":"QA Dataset", "description":"" }` | 200 dataset/list | Admin/wrong role as implemented; invalid assistant 404 |
| SW-EVAL-02 | Evaluations | POST/PUT/DELETE cases and reorder/enabled | Case payload | 200 | Invalid case 404; missing input 422; archived dataset behavior |
| SW-EVAL-03 | Evaluations | POST `/runs`, GET `/runs/{id}`, GET `/results/{id}` | `{ "assistant_id":1, "dataset_id":1, "version_id":1 }` | 200 run/result | Empty dataset 400; invalid version 404 |
| SW-EVAL-04 | Evaluations | GET `/compare`, GET/PUT `/assistants/{id}/policy` | Query/body | 200 | Invalid run IDs 404; bad policy 422 |
| SW-PUBLIC-01 | Public Chat | GET `/public/chatbots/{id}` | none | 200 public metadata | Unpublished/inactive/invalid 404 |
| SW-PUBLIC-02 | Public Chat | POST `/public/chat/sessions`, `/public/chat`, `/public/chat/feedback`, `/public/chat/stream` | Public payload | 200/stream | Invalid bot/session 404; empty message behavior |
| SW-PUBLIC-03 | Public REST API | POST `/public/api/chat/sessions` | `{ "chatbot_id":1 }` + API key header | 200 session | Missing/bad key 401; disabled API/unpublished 404 |
| SW-PUBLIC-04 | Public REST API | POST `/public/api/chat` | `{ "chatbot_id":1, "session_id":1, "message":"hello" }` + key | 200 response | Missing/bad key 401; invalid session 404 |
| SW-PUBLIC-05 | Widget | GET `/public/widget.js` | none | 200 JS | CORS/Content-Type usable by browser |
| SW-AN-01 | Analytics | GET `/projects/{id}/analytics`, `/chatbots/{id}/analytics`, operations dashboard | none | 200 metrics | Other manager 404; unauth 401 |
| SW-ADMIN-01 | Admin analytics/logs | GET `/admin/analytics/*` | query filters | 200 | Manager 403; invalid filters safe |
| SW-SET-01 | Platform Settings | GET/PUT `/admin/platform-settings` | Settings body | 200 | Manager 403; invalid email/page size 422/400 |
| SW-SEARCH-01 | Search | GET `/search?q=term&limit=6` | none | 200 results | End user/anonymous denied; short/empty query returns safe result |
| SW-HEALTH-01 | Health | GET `/health/database`, `/health/ai`, `/health/rag` | none | 200/diagnostic | Provider misconfig returns safe diagnostic |

Swagger evidence to capture:
- Request URL, role/session used, payload, response status, response body.
- For negative tests, capture that no sensitive config, token, stack trace, or raw provider key is exposed.
