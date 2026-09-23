# ChatBot Factory Test Cases

Status values: NOT RUN, PASS, FAIL, BLOCKED, SKIPPED. Priorities: P0 Critical, P1 High, P2 Medium, P3 Low.
For every case below use: Actual result = TBD, Status = NOT RUN, Evidence = TBD, Bug ID = TBD.
Default environment is Local unless the case says Azure or Public. Record execution in Qase.

## Field Format

Each row includes: Test Case ID, Module, Feature, Scenario, Test type, Priority, Actor/Role, Preconditions, Environment, Steps, Test data, Expected result, Actual result placeholder, Status placeholder, Evidence placeholder, Bug ID placeholder.

## A. Authentication, Profile, Roles

| ID | Type/Priority | Actor | Preconditions | Steps | Test data | Expected result |
|---|---|---|---|---|---|---|
| AUTH-001 | Positive/P0 | Admin | Active admin | Open `/login`, enter valid credentials, submit | Admin email/password | Login succeeds, HttpOnly cookies set, admin home opens, admin nav visible |
| AUTH-002 | Positive/P0 | Manager | Active manager | Login as manager | Manager credentials | Redirects to `/dashboard/projects`, manager nav visible |
| AUTH-003 | Negative/P0 | Any | User exists | Submit wrong password | Valid email, bad password | 401 safe error, no session |
| AUTH-004 | Validation/P1 | Any | None | Submit blank and malformed credentials | Blank/malformed | Required validation or 422/401; no session |
| AUTH-005 | Negative/P1 | Any | User exists | Fail login repeatedly within rate window | Wrong password | Rate-limit response shown safely |
| AUTH-006 | Positive/P0 | Admin/Manager | Logged in | Logout from account menu | N/A | Backend clears auth/refresh cookies, local user cleared, login page opens |
| AUTH-007 | Permission/P0 | Anonymous | Not logged in | Direct-open `/dashboard/projects`, `/admin/users` | N/A | Redirect to `/login`; APIs return 401 |
| AUTH-008 | Positive/P1 | Manager | Valid refresh cookie | Expire access cookie; request protected API | Cookie state | Interceptor calls `/auth/refresh`, retries, user remains logged in |
| AUTH-009 | Negative/P0 | Manager | Invalid refresh cookie | Trigger 401 and refresh failure | Expired cookies | Session cleared, expired message shown, redirect to login |
| AUTH-010 | Positive/P1 | Public | User email exists | Submit forgot password | Existing email | Generic success, no account enumeration |
| AUTH-011 | Negative/P1 | Public | None | Submit forgot password for unknown email | Unknown email | Same generic success |
| AUTH-012 | Positive/P1 | Public | Valid reset token | Submit strong new password | Strong password | Password updated, token invalidated, login works |
| AUTH-013 | Negative/P1 | Public | Invalid/expired token | Submit reset form | Bad token | 400 safe error, password unchanged |
| AUTH-014 | Validation/P1 | Public | Valid token | Submit weak password | Weak password | Password policy rejects |
| PROF-001 | Positive/P1 | Admin/Manager | Logged in | Open `/dashboard/profile` | N/A | Current user data displayed |
| PROF-002 | Positive/P1 | Admin/Manager | Logged in | Edit name and save | Valid name | `PUT /auth/me` succeeds and stored user updates |
| PROF-003 | Validation/P2 | Admin/Manager | Logged in | Save blank name | Blank name | Client/API rejects |
| PROF-004 | Positive/P1 | Admin/Manager | Logged in | Change password with current password | Strong new password | Password updated; old password rejected |
| PROF-005 | Negative/P1 | Admin/Manager | Logged in | Change password with wrong current password | Wrong current password | 400 current password error |
| PERM-001 | Permission/P0 | Manager | Logged in | Open `/admin/users`; call `/auth/users` | N/A | Frontend denies/redirects; API 403 |
| PERM-002 | Permission/P1 | Admin | Logged in | Open `/dashboard/template-qa` | N/A | Redirects to `/admin/dashboard`; Template QA not allowed |
| PERM-003 | Permission/P0 | Admin | Logged in | Swagger `POST /projects` | Valid project | 403 workspace read-only message |
| PERM-004 | Permission/P0 | Manager B | Manager A owns data | Direct-open Manager A project/assistant/API | Other IDs | 404/403; no cross-manager data leak |
| PERM-005 | Permission/P1 | End User | Logged in | Open dashboard/admin routes | N/A | Denied/redirected; protected APIs fail |

## B. Admin

| ID | Type/Priority | Actor | Preconditions | Steps | Test data | Expected result |
|---|---|---|---|---|---|---|
| ADMIN-001 | Positive/P0 | Admin | Logged in | Open `/admin/dashboard`, refresh | N/A | Overview KPIs/runtime/usage sections load or show empty states |
| ADMIN-002 | Error/P1 | Admin | API unavailable | Open admin dashboard | N/A | Error message, no blank/crashed page |
| ADMIN-003 | Positive/P1 | Admin | Users exist | Search/filter users by role/status, page next/previous | Search/status | Matching users, correct pagination |
| ADMIN-004 | Positive/P0 | Admin | Unique email | Add manager user from modal | Name/email/role | User created active; setup email attempted; audit log created |
| ADMIN-005 | Negative/P1 | Admin | Email exists | Add user with duplicate email | Existing email | Error shown; no duplicate |
| ADMIN-006 | Validation/P1 | Admin | Modal open | Submit missing name/email | Blank fields | Client/API validation blocks |
| ADMIN-007 | Positive/P1 | Admin | Non-current user | Suspend then reactivate user | User ID | Status persists; suspended login blocked |
| ADMIN-008 | Negative/P1 | Admin | User owns projects | Delete dependent user | Manager ID | Deletion blocked or dependency summary shown |
| ADMIN-009 | Negative/P0 | Admin | Last active admin | Suspend/delete last active admin | Admin ID | Operation blocked |
| ADMIN-010 | Positive/P1 | Admin | Assistants exist | Filter/sort/page `/admin/chatbots` | Search, owner, project, publication, deployment | Scoped list, stats, empty no-match state |
| ADMIN-011 | Positive/P2 | Admin | Assistant exists | Open details modal; close | Assistant row | Details and version/runtime metrics shown; close works |
| ADMIN-012 | Positive/P1 | Admin | Sessions exist | Filter `/admin/conversations` by chatbot ID; open session | Chatbot ID | Session list and transcript load |
| ADMIN-013 | Positive/P1 | Admin | Runtime logs exist | Apply runtime log filters and pagination | Status/channel/date | Correct logs and empty states |
| ADMIN-014 | Positive/P1 | Admin | Audit logs exist | Search/filter action/resource/date; reset | Filters | Correct audit logs; reset clears filters |
| ADMIN-015 | Positive/P1 | Admin | Logged in | Save valid platform settings | Name/email/page size | Settings persist after reload |
| ADMIN-016 | Validation/P1 | Admin | Logged in | Save invalid support email/page size | Invalid values | Validation blocks save |

## C. Projects and Assistants

| ID | Type/Priority | Actor | Preconditions | Steps | Test data | Expected result |
|---|---|---|---|---|---|---|
| PROJ-001 | Empty/P1 | Manager | No projects | Open `/dashboard/projects` | N/A | Empty state and create action shown |
| PROJ-002 | Positive/P0 | Manager | Logged in | Create project with name/description | Unique project | Project appears and opens overview |
| PROJ-003 | Validation/P1 | Manager | Create form open | Submit blank name | Blank | Required-name error; no project |
| PROJ-004 | Positive/P1 | Manager/Admin | Projects exist | Search/filter status/owner/date and clear filters | Filters | Results match role scope and filters |
| PROJ-005 | Positive/P2 | Manager/Admin | More than page size | Use next/previous/page controls | N/A | Correct page labels and disabled states |
| PROJ-006 | Positive/P1 | Manager | Project exists | Duplicate project | Project A | Unique copy created with expected copied data |
| PROJ-007 | Positive/P1 | Manager | Active project | Archive, filter archived, restore | Project ID | Status changes persist |
| PROJ-008 | Positive/P1 | Manager | Disposable project | Delete: cancel then confirm | Project ID | Cancel preserves; confirm removes/soft-deletes |
| PROJ-009 | Negative/P1 | Manager/Admin | Logged in | Open invalid project URL/API | 999999 | Safe not-found/error state |
| PROJ-010 | Positive/P1 | Manager/Admin | Project has data | Open project overview | Project ID | Metrics, readiness center, recommendations, knowledge gaps display |
| PROJ-011 | Positive/P1 | Manager/Admin | Project has data | Open project analytics | Project ID | Conversations/messages/runtime/channel metrics display |
| PROJ-012 | Positive/P1 | Manager | Project exists | Update project settings/name/description | Valid values | Changes persist |
| ASST-001 | Empty/P1 | Manager | Project has no assistants | Open assistant list | Project ID | Empty state and create entry point |
| ASST-002 | Positive/P0 | Manager | Project exists | Create scratch assistant | Name/language/channel/purpose | Assistant, draft version, and starter flow created |
| ASST-003 | Positive/P0 | Manager | Templates exist | Create assistant from template | Template key | Flow populated from selected template |
| ASST-004 | Positive/P1 | Manager | Azure OpenAI configured | Generate AI assistant draft | Goal/business/KB context | Generated setup/flow can be applied |
| ASST-005 | Validation/P1 | Manager | Wizard open | Submit missing name | Blank name | Validation/API error |
| ASST-006 | Positive/P2 | Manager/Admin | Assistants exist | Search/filter assistant list | Search text | Matching scoped assistants or no-results state |
| ASST-007 | Positive/P1 | Manager | Assistant exists | Edit assistant settings | Name/description/channel/language | Persisted and reflected in overview/deployment |
| ASST-008 | Positive/P1 | Manager | Assistant exists | Disable then enable assistant | Boolean | Status persists; inactive public runtime unavailable |
| ASST-009 | Positive/P1 | Manager | Disposable assistant | Delete: cancel then confirm | Assistant ID | Related versions/flows/KB/conversations cleaned per backend |
| ASST-010 | Permission/P0 | Admin | Assistant exists | API `PUT /chatbots/{id}` | Update payload | 403 read-only workspace |

## D. Templates, Template QA, Flow Builder

| ID | Type/Priority | Actor | Preconditions | Steps | Test data | Expected result |
|---|---|---|---|---|---|---|
| TPL-001 | Positive/P1 | Manager | Assistant exists | Open template selection; switch purposes | Purpose values | Compatible templates display |
| TPL-002 | Positive/P1 | Manager | Draft flow exists | Apply selected template | Template key | Nodes/transitions persist in builder |
| TPL-003 | Negative/P1 | Manager | Flow exists | Apply invalid/incomplete template via URL/API | Bad key | Safe error; existing flow not corrupted |
| TQA-001 | Positive/P1 | Manager | Templates seeded | Open Template QA | N/A | QA list with status counts loads |
| TQA-002 | Positive/P1 | Manager | Templates exist | Apply search/status/exposure/ownership filters | Filter values | Client-side filtered results; no-results state |
| TQA-003 | Positive/P1 | Manager | Template exists | Open detail drawer, close, reopen direct URL | Template key | Detail drawer loads and URL state works |
| TQA-004 | Positive/P2 | Manager | Drawer open | Expand and restore drawer | N/A | Normal and expanded layouts render correctly |
| TQA-005 | Positive/P2 | Manager | Revisions exist | Open Version History | Template key | Revisions and selected revision shown |
| TQA-006 | Positive/P1 | Manager | Template flow exists | View Flow Preview, Paths, Runtime Confidence | Template key | Nodes/paths/issues/confidence from backend display |
| TQA-007 | Positive/P1 | Manager | Detail open | Run custom test with messages and variables | Lines + JSON | Result response/trace/pass-fail displayed |
| TQA-008 | Positive/P1 | Manager | Saved scenario exists | Run saved/default test | N/A | Test result displayed |
| TQA-009 | Validation/P1 | Manager | Detail open | Enter invalid variables JSON | `{bad` | JSON error; test not run or safe API error |
| TQA-010 | Permission/P1 | Manager | Built-in and owned custom templates | Try editing both | Editable fields | Owned custom saves; built-in/non-owned denied or disabled |
| FLOW-001 | Positive/P0 | Manager | Draft version exists | Open Flow Builder | Assistant ID | Canvas, palette, inspector, tabs load |
| FLOW-002 | Positive/P1 | Manager | Flow open | Add every visible block type | message, question, buttons, end, rag_answer, knowledge_search, collect_name, collect_email, collect_phone, condition, set_variable, handoff | Nodes appear with default config |
| FLOW-003 | Positive/P0 | Manager | Nodes exist | Configure and save message/question/buttons | Text/field/buttons | Config persists after reload |
| FLOW-004 | Positive/P2 | Manager | Node exists | Move node | Drag/position | Position persists and layout stable |
| FLOW-005 | Positive/P1 | Manager | Node exists | Delete node cancel then confirm | Node ID | Cancel preserves; confirm removes related transitions |
| FLOW-006 | Positive/P0 | Manager | Two nodes | Create/update/delete transition | Source/target/label | Transition behavior persists |
| FLOW-007 | Negative/P1 | Manager | Same output exists | Create duplicate output transition | Duplicate label | Validation reports duplicate output key |
| FLOW-008 | Negative/P0 | Manager | Empty flow | Validate | Version ID | Invalid: add at least one block/start path |
| FLOW-009 | Negative/P0 | Manager | No `start` node | Validate | Version ID | `START_NODE_MISSING` error |
| FLOW-010 | Negative/P1 | Manager | Orphan node | Validate | Flow data | Unreachable/orphan error |
| FLOW-011 | Validation/P1 | Manager | Buttons node | Validate with missing button connector | Buttons | Missing transition per button |
| FLOW-012 | Validation/P1 | Manager | Condition node | Validate with missing true/false | Condition | True/false path errors |
| FLOW-013 | Validation/P1 | Manager | RAG node | Validate without fallback/continuation | RAG config | RAG fallback/continuation error or warning |
| FLOW-014 | Positive/P2 | Manager | Valid flow | Save flow as template/revision | Template metadata | Template/revision created and visible in QA |
| FLOW-015 | Positive/P0 | Manager | Valid flow | Start preview and send message/button | Test text | Bot messages/options/variables display |
| FLOW-016 | Positive/P0 | Manager | Draft assistant | Build start->message->collect_email->question->rag_answer->handoff fallback->end; validate; preview | Email and support question | Validation passes; variables, RAG/fallback/handoff path work |

## E. Knowledge Base, Document Processing, RAG, Test Flow

| ID | Type/Priority | Actor | Preconditions | Steps | Test data | Expected result |
|---|---|---|---|---|---|---|
| KB-001 | Empty/P1 | Manager | Version has no docs | Open Knowledge Base | Version ID | Empty document state shown |
| KB-002 | Positive/P0 | Manager | Draft version | Upload valid text document | Known-answer text | Document uploaded; chunks and embeddings attempted; ready/partial/failed status visible |
| KB-003 | Positive/P1 | Manager | PDF support available | Upload extractable PDF | Text PDF | Text extracted, chunks created, embeddings attempted |
| KB-004 | Negative/P1 | Manager | Version exists | Upload blank filename/no readable text | Invalid payload | 400 safe error; no document row |
| KB-005 | Negative/P1 | Manager | Document exists | Upload same document | Same file/hash | 409 duplicate; original unchanged |
| KB-006 | Positive/P1 | Manager/Admin | Documents in multiple states | Refresh KB list | Ready/failed/pending docs | Chunk/embedding counters and statuses correct |
| KB-007 | Positive/P1 | Manager/Admin | Document has chunks | Open chunks | Document ID | Chunks sorted by order with metadata/status |
| KB-008 | Positive/P1 | Manager | Failed/pending embeddings | Reprocess embeddings | Document ID | Embeddings retried; status/counts update |
| KB-009 | Positive/P1 | Manager | Document has raw_text | Reprocess chunks | Document ID | Chunks replaced and embeddings regenerated |
| KB-010 | Positive/P1 | Manager | Disposable doc | Delete cancel then confirm | Document ID | Chunks/doc removed; audit recorded |
| RAG-001 | Positive/P0 | Manager/Admin | Ready document with known fact | Run RAG retrieval test | Matching question | Relevant chunks and scores returned |
| RAG-002 | Negative/P1 | Manager/Admin | Ready docs | Ask irrelevant question | Unrelated text | Empty/low-score results; no crash |
| RAG-003 | Positive/P0 | Manager/Public | show_sources true | Ask known KB question in Test Flow/public chat | Known question | Answer includes sources display/array |
| RAG-004 | Positive/P1 | Manager/Public | show_sources false | Ask same question | Known question | Answer has no source display |
| RAG-005 | Negative/P1 | Manager/Public | No docs | Ask RAG question | Any question | Configured fallback/safe no-knowledge response |
| RAG-006 | Validation/P1 | Manager/Public | Chat available | Send empty and long query | Blank/long | Blank blocked or safe no-op; long query handled without layout break |
| RAG-007 | Error/P1 | Manager/Public | Embedding/LLM failure simulated | Ask RAG question | Known question | Safe fallback/error; runtime log failure; no secret leak |
| TEST-001 | Positive/P0 | Manager | Valid version | Open Test Flow and start session | Assistant ID | Session created and initial bot message shown |
| TEST-002 | Positive/P0 | Manager | Flow with loop | Send multiple turns through Question -> AI/RAG -> Question | Test messages | Current node and variables update; loop continues |
| TEST-003 | Positive/P1 | Manager | Buttons node waiting | Select valid button | Button label | Correct path followed |
| TEST-004 | Negative/P1 | Manager | Buttons node waiting | Send unmatched text | Invalid option | Choose-option prompt or safe fallback |
| TEST-005 | Validation/P1 | Manager | Session active | Submit empty input | Blank | Send disabled or safe validation |

## F. Evaluations, Versions, Publishing, Deployment

| ID | Type/Priority | Actor | Preconditions | Steps | Test data | Expected result |
|---|---|---|---|---|---|---|
| EVAL-001 | Positive/P1 | Manager | Assistant exists | Create dataset | Name/description | Active dataset appears |
| EVAL-002 | Validation/P1 | Manager | Evaluations page | Submit blank dataset name | Blank | Validation/API error |
| EVAL-003 | Positive/P1 | Manager | Dataset exists | Create case with keyword/source/final-node/variable assertions | Case data | Case saved and listed |
| EVAL-004 | Positive/P2 | Manager | Cases exist | Duplicate, reorder, enable/disable | Case IDs | Order/enabled state persists |
| EVAL-005 | Positive/P0 | Manager | Dataset has enabled cases and version LLM config | Run evaluation | Dataset/version | Run completes with pass/warning/fail counts and results |
| EVAL-006 | Negative/P1 | Manager | Dataset has no enabled cases | Run evaluation | Empty dataset | 400 “Dataset has no enabled evaluation cases” |
| EVAL-007 | Positive/P2 | Manager | Completed run | Open run/result detail | Run/result ID | Assertions, actual response, sources, variables shown |
| EVAL-008 | Positive/P1 | Manager | Dataset exists | Enable required-before-publish policy | Policy thresholds | Readiness includes evaluation policy checks |
| EVAL-009 | Positive/P2 | Manager | Two completed runs | Compare runs | Baseline/candidate IDs | Regression/improvement counts returned |
| VER-001 | Positive/P0 | Manager | Assistant exists | Create version | Chatbot ID | Draft version created with default config/flow copy where applicable |
| VER-002 | Positive/P1 | Admin/Manager | Versions exist | Open/select version | Version ID | Version identity, readiness, docs, config load |
| VER-003 | Positive/P1 | Manager | Version selected | Save LLM instructions/tone/language/style/temp | Valid config | Config persists |
| VER-004 | Negative/P0 | Manager | Invalid flow/no instructions | Refresh readiness; attempt publish | Version ID | Publish blocked with actionable errors |
| VER-005 | Positive/P1 | Manager | Valid version | Run smoke test | Version ID | Smoke pass/fail stored and shown |
| PUB-001 | Positive/P0 | Manager | Valid readiness no blockers | Publish version | Version ID | Version published; assistant active version updated; public channel uses it |
| PUB-002 | Positive/P1 | Manager | Warnings only | Publish, cancel warning confirm, then publish anyway | Version ID | Cancel preserves draft; confirm publishes |
| PUB-003 | Permission/P0 | Admin | Draft exists | API `PUT /versions/{id}/publish` | Version ID | 403 read-only workspace |
| PUB-004 | Partial/P3 | Manager | Multiple versions | Look for explicit rollback feature | N/A | SKIPPED/NOT IMPLEMENTED; no rollback endpoint found |
| DEP-001 | Positive/P0 | Manager | Published assistant | Open Deployment public chat section | Assistant ID | Public URL displayed; copy works |
| DEP-002 | Positive/P0 | Manager | Published assistant | Open widget section | Assistant ID | Widget snippet references `/public/widget.js`; copy works |
| DEP-003 | Positive/P0 | Manager | Assistant exists | View/regenerate REST API key | Assistant ID | New `cp_` key generated; old key invalid |
| DEP-004 | Positive/P1 | Manager | Assistant exists | Configure web/widget/api channel, test, clear error, delete | Channel config | Status/logs update; secret config masked |
| DEP-005 | Negative/P0 | Manager | Assistant unpublished | Open deployment/public URL | Assistant ID | Publish requirement shown; runtime unavailable safely |

## G. Public Chat, Widget, Public API, Conversations, Analytics, Search

| ID | Type/Priority | Actor | Preconditions | Steps | Test data | Expected result |
|---|---|---|---|---|---|---|
| PUBCHAT-001 | Positive/P0 | Anonymous | Published active assistant | Open `/public-chat/:id` | Chatbot ID | Chat page loads without login |
| PUBCHAT-002 | Positive/P0 | Anonymous | Public chat open | Send first message | Text | Loading/typing state then response |
| PUBCHAT-003 | Positive/P1 | Anonymous | Public session | Send 10+ turns | Messages | Scroll/history remain stable |
| PUBCHAT-004 | Navigation/P1 | Anonymous | Session active | Refresh browser | N/A | Page reloads safely; no crash |
| PUBCHAT-005 | Negative/P0 | Anonymous | None | Open invalid public chatbot | 999999 | Safe unavailable/not found, no stack trace |
| PUBCHAT-006 | Negative/P0 | Anonymous | Assistant unpublished | Open URL/send | Chatbot ID | Safe unavailable response, no internal details |
| PUBCHAT-007 | Positive/P1 | Anonymous | RAG public assistant | Ask known KB question with sources on/off | Known question | Source behavior matches settings |
| WIDGET-001 | Positive/P0 | Anonymous | Backend running | Load `/public/widget.js` or host page snippet | Chatbot ID | Script loads without CORS/JS error |
| WIDGET-002 | Positive/P1 | Anonymous | Widget loaded | Open, close, minimize, reopen repeatedly | N/A | Bubble/widget state stable; host page usable |
| WIDGET-003 | Positive/P0 | Anonymous | Published widget assistant | Send widget message | Text | Response, scroll, loading state work |
| WIDGET-004 | Error/P1 | Anonymous | Invalid/unpublished assistant | Load widget/send | Bad ID | Safe error, no technical leak |
| REST-001 | Positive/P0 | API Client | API key available | Call `/public/api/chat/sessions` | `x-chatbot-api-key`, chatbot_id | Session ID returned |
| REST-002 | Positive/P0 | API Client | Session/key | Call `/public/api/chat` | Key, chatbot_id, message | Response/messages/options/sources per runtime |
| REST-003 | Permission/P0 | API Client | Published assistant | Call public API without/bad key | Bad/missing key | 401 invalid API key |
| CONV-001 | Positive/P1 | Admin/Manager | Conversations exist | Open assistant conversations | Assistant ID | Session list loads |
| CONV-002 | Positive/P1 | Admin/Manager | Conversations exist | Apply search/date/channel/response filters if present | Filters | Results match filters; note DB-side/client-side from network behavior |
| CONV-003 | Validation/P1 | Admin/Manager | Page open | Set From date after To date | Dates | Rejected or clear empty/error state |
| CONV-004 | Positive/P1 | Admin/Manager | Session exists | Open transcript | Session ID | Transcript, options, sources shown |
| CONV-005 | Positive/P2 | Manager | Conversation exists | Toggle follow-up | Payload | Follow-up persists |
| CONV-006 | Partial/P3 | Admin/Manager | Export button present | Export CSV after filters | Current filters | CSV downloads if implemented; otherwise SKIPPED |
| ANALYT-001 | Positive/P1 | Admin/Manager | Runtime data exists | Open assistant analytics | Assistant ID | Conversations/messages/response time/RAG/chart data displays |
| ANALYT-002 | Empty/P1 | Manager | New assistant no traffic | Open analytics | Assistant ID | No-data state shown |
| ANALYT-003 | Positive/P1 | Admin/Manager | Project data exists | Open project analytics | Project ID | Project metrics/channels/failures display |
| SEARCH-001 | Positive/P1 | Manager/Admin | Matching project exists | Use topbar search and select project | Partial/case-insensitive term | Navigates to project; role scoped |
| SEARCH-002 | Positive/P1 | Manager/Admin | Matching assistant/document exists | Search assistant/document | Name/filename | Correct destination; no stale-result crash |
| SEARCH-003 | Empty/P2 | Manager/Admin | Logged in | Search random text | Random | “No results found” |

## H. Responsive, Error, Legal, Azure-oriented Manual Checks

| ID | Type/Priority | Actor | Preconditions | Steps | Test data | Expected result |
|---|---|---|---|---|---|---|
| RESP-001 | Responsive/P1 | Admin/Manager | Logged in | Test 1440/1024/390 widths and nav drawer | Viewports | No overlap; drawer, breadcrumbs, search usable |
| RESP-002 | Responsive/P1 | Admin/Manager | Tables with data | Open users/logs/conversations on mobile | Mobile | Tables scroll/reflow and actions remain usable |
| RESP-003 | Responsive/P1 | Admin/Manager | Modals/drawers available | Open add-user, details, Template QA, version confirm on mobile | Mobile | Fits viewport; close/cancel reachable |
| ERR-001 | Error/P1 | Admin/Manager | DevTools/Swagger | Submit invalid payloads | Invalid data | 400/422 displayed clearly; no crash |
| ERR-002 | Error/P0 | Any | Wrong/missing auth | Call protected APIs/direct URLs | N/A | 401/403 safe handling |
| ERR-003 | Error/P1 | Admin/Manager/Public | Logged in/public | Use invalid project/chatbot/version/document/session IDs | 999999 | 404/unavailable safely handled |
| ERR-004 | Error/P1 | Manager/Admin | Duplicate resource exists | Duplicate doc/channel/user/email | Duplicate payload | 409/400 conflict shown safely |
| ERR-005 | Error/P1 | Any | Controlled server failure | Trigger safe 500 in test env | N/A | Generic error; logs/audit record failure; no secrets |
| LEGAL-001 | Positive/P3 | Public | None | Open frontend `/privacy-policy` | N/A | Page renders without auth |
| LEGAL-002 | Positive/P3 | Public | Backend running | Open backend `/privacy-policy`, `/terms`, `/data-deletion`; send HEAD | N/A | HTML and HEAD responses work |
| AZ-MAN-001 | Azure/P0 | Admin/Manager/Public | Production deployed | Execute full production smoke: login -> project -> assistant -> flow -> KB -> test -> publish -> public chat | Production test data | Workflow works on deployed URLs |
| AZ-MAN-002 | Azure/P0 | Public/API Client | Production deployed | Verify frontend URL, backend `/health`, CORS, cookies, widget, REST API key chat | Production URLs/key | No CORS/console/network errors; cold then warm requests succeed |
