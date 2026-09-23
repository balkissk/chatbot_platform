# ChatBot Factory Traceability Matrix

Tool values: Manual Browser, Chrome DevTools, Swagger, Playwright, JMeter, Qase, Azure.

| Feature | Test Case IDs | Role | Tool | Environment |
|---|---|---|---|---|
| Authentication | AUTH-001..014, SMK-01..02, SW-AUTH-01..05, PW-01 | Admin, Manager, End User, Public | Manual Browser, Swagger, Playwright, Qase | Local, Azure |
| User Profile | PROF-001..005, SW-PROF-01..03 | Admin, Manager | Manual Browser, Swagger, Qase | Local |
| Roles and Permissions | PERM-001..005, SMK-11, PW-10, AZ-22 | Admin, Manager, End User, Anonymous | Manual Browser, Swagger, Playwright, Qase, Azure | Local, Azure |
| Admin Dashboard | ADMIN-001..002, SMK-12, SW-ADMIN-01, AZ-21 | Admin | Manual Browser, Swagger, Qase, Azure | Local, Azure |
| Admin Users | ADMIN-003..009, SW-USR-01..04 | Admin | Manual Browser, Swagger, Qase | Local |
| Admin Chatbots | ADMIN-010..011, SW-ADMIN-01 | Admin | Manual Browser, Swagger, Qase | Local |
| Admin Conversations | ADMIN-012, SW-ADMIN-01 | Admin | Manual Browser, Swagger, Qase | Local |
| Runtime Logs | ADMIN-013, SW-ADMIN-01, AZ-21 | Admin | Manual Browser, Swagger, Azure, Qase | Local, Azure |
| Audit Logs | ADMIN-014, SW-ADMIN-01 | Admin | Manual Browser, Swagger, Qase | Local |
| Platform Settings | ADMIN-015..016, SW-SET-01 | Admin | Manual Browser, Swagger, Qase | Local |
| Projects | PROJ-001..012, SMK-03, SW-PROJ-01..08, PW-02, AZ-06 | Admin read, Manager write | Manual Browser, Swagger, Playwright, Qase, Azure | Local, Azure |
| Project Overview/Analytics | PROJ-010..011, ANALYT-003, SW-AN-01 | Admin, Manager | Manual Browser, Swagger, Qase | Local |
| Assistants | ASST-001..010, SMK-04, SW-ASST-01..08, PW-03, AZ-07 | Admin read, Manager write | Manual Browser, Swagger, Playwright, Qase, Azure | Local, Azure |
| Assistant Creation | ASST-002..005, SW-ASST-01, PW-03 | Manager | Manual Browser, Swagger, Playwright, Qase | Local, Azure |
| Templates | TPL-001..003, SW-TPL-01, PW-04 | Manager | Manual Browser, Swagger, Qase | Local |
| Template QA | TQA-001..010, SW-TPL-02..04 | Manager | Manual Browser, Swagger, Qase | Local |
| Flow Builder | FLOW-001..007, FLOW-014..016, SMK-05, SW-FLOW-01..06, PW-04, AZ-08 | Manager | Manual Browser, Swagger, Playwright, Qase, Azure | Local, Azure |
| Flow Validation | FLOW-008..013, VER-004, SW-FLOW-02 | Manager | Manual Browser, Swagger, Qase | Local |
| Test Flow | TEST-001..005, SMK-07, SW-CHAT-01..02, PW-06, AZ-11 | Manager | Manual Browser, Swagger, Playwright, Qase, Azure | Local, Azure |
| Knowledge Base | KB-001..010, SMK-06, SW-KB-01..06, PW-05, AZ-09 | Admin read, Manager write | Manual Browser, Swagger, Playwright, Qase, Azure | Local, Azure |
| Document Processing | KB-002..010, SW-KB-01..06 | Manager | Manual Browser, Swagger, Qase | Local |
| RAG | RAG-001..007, SMK-06..09, SW-KB-05, PW-05, JM-05..07, AZ-10 | Admin, Manager, Public/API | Manual Browser, Swagger, Playwright, JMeter, Qase, Azure | Local, Azure, Perf |
| Evaluation Center | EVAL-001..009, SW-EVAL-01..04 | Manager | Manual Browser, Swagger, Qase | Local |
| Versions | VER-001..005, SW-VER-01..06 | Admin read, Manager write | Manual Browser, Swagger, Qase | Local |
| Publishing | PUB-001..004, SMK-08, SW-VER-05, PW-07, AZ-12 | Manager | Manual Browser, Swagger, Playwright, Qase, Azure | Local, Azure |
| Deployment Center | DEP-001..005, SW-CHAN-01..04, PW-09, AZ-14..16 | Manager | Manual Browser, Swagger, Playwright, Chrome DevTools, Qase, Azure | Local, Azure |
| Public Chat | PUBCHAT-001..007, SMK-09, SW-PUBLIC-01..02, PW-08, JM-05..07, AZ-13 | Anonymous | Manual Browser, Swagger, Playwright, JMeter, Qase, Azure | Local, Azure, Perf |
| Embedded Web Widget | WIDGET-001..004, SMK-10, SW-PUBLIC-05, PW-09, AZ-14 | Anonymous | Manual Browser, Chrome DevTools, Swagger, Playwright, Qase, Azure | Local, Azure |
| Public REST API | REST-001..003, SMK-10, SW-PUBLIC-03..04, JM-01..04, AZ-15..16 | API Client | Swagger, JMeter, Qase, Azure | Local, Azure, Perf |
| Conversations | CONV-001..006, ADMIN-012, SW-ASST analytics/conversation endpoints | Admin, Manager | Manual Browser, Swagger, Qase | Local |
| Knowledge Gaps | PROJ-010, RAG-002, CONV-002 | Admin, Manager | Manual Browser, Swagger, Qase | Local |
| Analytics | ANALYT-001..003, ADMIN-001, ADMIN-010, SW-AN-01, SW-ADMIN-01 | Admin, Manager | Manual Browser, Swagger, Qase | Local |
| Global Search | SEARCH-001..003, SW-SEARCH-01 | Admin, Manager | Manual Browser, Swagger, Qase | Local |
| Responsive/Mobile | RESP-001..003, PUBCHAT mobile, WIDGET mobile, AZ-24 | All UI roles | Manual Browser, Chrome DevTools, Qase, Azure | Local, Azure |
| Error Handling | ERR-001..005, endpoint negative cases, AZ-19, AZ-23 | All | Manual Browser, Swagger, Chrome DevTools, Qase, Azure | Local, Azure |
| Azure Production | AZ-01..24, SMK-01..12 | Admin, Manager, Public, API Client | Azure, Manual Browser, Chrome DevTools, Swagger, Qase | Azure |
| Legal Pages | LEGAL-001..002 | Public | Manual Browser, Swagger, Qase | Local, Azure optional |

## Quick Regression Suite

Run after any release candidate or high-risk fix:
- AUTH-001, AUTH-002, AUTH-006, PERM-001, PERM-003
- PROJ-002, ASST-002, FLOW-003, FLOW-015
- KB-002, RAG-003, TEST-001
- PUB-001, PUBCHAT-001, PUBCHAT-002, WIDGET-001, REST-002
- ADMIN-001, ADMIN-013

Estimated time: 2.5 to 4 hours depending on RAG/LLM latency.

## Full Regression Suite

Run before final PFE validation or major deployment:
- All P0/P1 cases in `ChatBot_Factory_Test_Cases.md`.
- All Swagger critical endpoint rows.
- Playwright PW-01 through PW-10 after implementation.
- JMeter JM-02, JM-04, JM-05, JM-07 for runtime capacity snapshots.
- Azure AZ-01 through AZ-24 for production acceptance.

Estimated time: 1.5 to 2.5 days after test data is prepared.
