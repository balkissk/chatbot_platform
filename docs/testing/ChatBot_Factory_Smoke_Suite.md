# ChatBot Factory Smoke Suite

Target duration: under 45 minutes. Execute first in local validation and repeat in Azure before deeper testing.

| ID | Priority | Module | Actor | Preconditions | Steps | Expected result | Status |
|---|---|---|---|---|---|---|---|
| SMK-01 | P0 | Login | Admin | Admin active | Login through `/login` | Admin dashboard/users area reachable | NOT RUN |
| SMK-02 | P0 | Login | Manager | Manager active | Login through `/login` | `/dashboard/projects` reachable | NOT RUN |
| SMK-03 | P0 | Projects | Manager | Logged in | Create project with unique name | Project appears and opens overview | NOT RUN |
| SMK-04 | P0 | Assistants | Manager | Project exists | Create scratch assistant | Assistant workspace opens with draft/version | NOT RUN |
| SMK-05 | P0 | Flow | Manager | Assistant exists | Open Flow Builder; validate starter flow or add simple start->message->end | Validation can be run and reports expected result | NOT RUN |
| SMK-06 | P0 | Knowledge | Manager | Draft version exists | Upload small text document with known answer | Document status/chunks shown without fatal error | NOT RUN |
| SMK-07 | P0 | Test Flow | Manager | Valid assistant flow | Start test session and send message | Bot response shown | NOT RUN |
| SMK-08 | P0 | Versions/Publish | Manager | Readiness blockers resolved | Run readiness/smoke test, publish version | Version becomes published/active | NOT RUN |
| SMK-09 | P0 | Public Chat | Anonymous | Assistant published | Open public chat URL, send message | Public response shown without login | NOT RUN |
| SMK-10 | P0 | Widget/Public API | Anonymous/API client | Assistant published and API key available | Load widget script and call public API session/message | Widget script loads; API responds with valid key | NOT RUN |
| SMK-11 | P0 | Permissions | Manager/Admin | Both roles available | Manager direct admin route; admin direct project create API | Manager admin denied; admin workspace write denied | NOT RUN |
| SMK-12 | P0 | Admin Monitoring | Admin | Runtime activity exists | Open admin dashboard/runtime logs | Data or empty states load without crash | NOT RUN |

Exit criteria:
- No P0 smoke test is FAIL or BLOCKED.
- Public chat and authenticated manager workflow both work.
- No browser console error blocks core workflows.
- No secrets, stack traces, or raw provider errors are exposed in public UI.
