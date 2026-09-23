# ChatBot Factory Playwright Plan

Purpose: small automated E2E regression suite only. Do not automate every feature.

Global setup:
- Use seeded admin and manager accounts.
- Use isolated test project/assistant names with timestamp suffix.
- Base URL from environment: local or Azure frontend.
- Prefer UI flows; use API cleanup only if explicitly allowed in the automation phase.

| ID | Journey | Priority | Preconditions | Steps | Assertions | Test data | Cleanup |
|---|---|---|---|---|---|---|---|
| PW-01 | Login/logout/session | P0 | Manager account | Visit `/login`, login, verify projects page, logout | URL changes, user menu visible, logout returns login | Manager credentials | None |
| PW-02 | Create Project | P0 | Manager logged in | Open projects, create project | Project card/row visible; overview route works | Timestamp project | Delete/archive project if safe |
| PW-03 | Create/Open Assistant | P0 | Test project exists | Create scratch assistant and open overview | Assistant name visible; sidebar assistant nav appears | Timestamp assistant | Delete assistant/project |
| PW-04 | Save Flow | P0 | Assistant draft exists | Open flow, add/configure message/question/buttons/end, connect, save | Nodes visible; reload preserves config | Simple flow content | Delete assistant/project |
| PW-05 | Knowledge/RAG | P0 | Assistant draft version exists | Upload text doc, run RAG retrieval test | Document listed; retrieval returns known source text/chunk | Known-answer text file | Delete document/project |
| PW-06 | Test Flow | P0 | Valid simple flow exists | Start test session; send answer/button | Bot response/options visible; variables do not crash UI | Message values | Delete assistant/project |
| PW-07 | Publish | P0 | Valid version with LLM config and flow | Open versions, refresh readiness, publish | Published badge and active marker visible | Prepared valid assistant | Delete/archive test data if safe |
| PW-08 | Public Chat | P0 | Published assistant | Open `/public-chat/:id`, send message | Response appears; no login redirect | Published assistant ID | None |
| PW-09 | Widget | P1 | Published assistant | Load a simple host page with widget script, open bubble, send message | Widget opens/responds; close/reopen works | Widget snippet | Remove temp host file if used |
| PW-10 | Role Restriction | P0 | Admin and manager accounts | As manager open `/admin/users`; as admin attempt project create via UI/API route if exposed | Manager denied admin route; admin workspace write denied | Existing accounts | None |

Recommended assertions:
- Use role-specific text and route URLs, not brittle CSS classes.
- Assert buttons disable during requests for create/publish/upload where feasible.
- Assert no visible raw stack trace or provider secret on public chat/widget failures.
