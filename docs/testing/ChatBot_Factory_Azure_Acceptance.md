# ChatBot Factory Azure Production Acceptance

Do not modify Azure configuration during this suite. Use deployed frontend/backend URLs and browser DevTools.

## Production Smoke Journey

| ID | Priority | Area | Steps | Expected result | Tool |
|---|---|---|---|---|---|
| AZ-01 | P0 | Frontend URL | Open production frontend root and `/login` | Pages load over HTTPS, no console-blocking errors | Azure/Chrome DevTools |
| AZ-02 | P0 | Backend URL | Open backend `/health/database`, `/health/ai`, `/health/rag` | Health/diagnostic responses are safe and expected for configured services | Azure/Swagger |
| AZ-03 | P0 | Login | Login as manager | Auth cookies set with production-safe attributes; dashboard opens | Manual Browser/DevTools |
| AZ-04 | P0 | Browser refresh | Refresh `/dashboard/projects`, assistant deep links, admin deep links | SSR/routing handles refresh; no 404 from App Service | Manual Browser |
| AZ-05 | P0 | CORS | From frontend, call protected and public APIs | Requests succeed only from allowed frontend origin; credentials included | Chrome DevTools |
| AZ-06 | P0 | Project | Create production test project | Project persists and is scoped to manager | Manual Browser |
| AZ-07 | P0 | Assistant | Create scratch assistant | Assistant workspace opens with draft version | Manual Browser |
| AZ-08 | P0 | Flow | Configure simple flow and validate | Flow saves and validation result displays | Manual Browser |
| AZ-09 | P0 | Knowledge Base | Upload small text doc | Document chunks/embeddings reach ready/partial/failed state with safe errors | Manual Browser |
| AZ-10 | P0 | RAG | Run RAG retrieval on known text | Relevant chunk/source returned | Manual Browser/Swagger |
| AZ-11 | P0 | Test Flow | Start test and send message | Runtime response shown; logs created | Manual Browser |
| AZ-12 | P0 | Publish | Run readiness/smoke and publish | Version becomes published/active | Manual Browser |
| AZ-13 | P0 | Public Chat | Open public chat URL as anonymous, send first and second message | No login required; responses shown; no internal details | Manual Browser |
| AZ-14 | P0 | Widget | Load widget snippet on a test host page | Script loads over HTTPS; bubble opens and responds | Chrome DevTools |
| AZ-15 | P0 | REST API | Start API session and send message with key | 200 responses; missing/bad key returns 401 | Swagger |
| AZ-16 | P1 | API Keys | Regenerate public API key | New key works, old key fails | Manual Browser/Swagger |
| AZ-17 | P1 | Cold start | After idle period, hit frontend and backend | First request may be slower; no timeout beyond platform tolerance | Azure/DevTools |
| AZ-18 | P1 | Warm requests | Repeat login/public chat/RAG after cold start | Normal latency improves; no repeated failures | Azure/DevTools |
| AZ-19 | P1 | Network errors | Temporarily simulate browser offline or block backend in DevTools | UI shows safe error states | Chrome DevTools |
| AZ-20 | P1 | Console errors | Execute main flows with console open | No uncaught errors blocking workflows | Chrome DevTools |
| AZ-21 | P1 | Admin | Login admin; open users, logs, analytics, settings | Admin surfaces load; manager-only Template QA remains denied | Manual Browser |
| AZ-22 | P1 | Permissions | Manager cannot access admin URLs; admin cannot workspace-write | Frontend and backend enforcement match matrix | Manual Browser/Swagger |
| AZ-23 | P1 | Public invalid IDs | Open invalid public chat and call invalid public API chatbot | Safe 404/unavailable, no stack trace | Manual Browser/Swagger |
| AZ-24 | P1 | Responsive | Run public chat/widget/dashboard on mobile viewport | Layout usable, no overlapping controls | Chrome DevTools |

## Acceptance Criteria

- All AZ P0 cases pass.
- No CORS failure blocks frontend-to-backend calls.
- Auth cookies work across production frontend/backend origins.
- Public chat, widget, REST API, and RAG work on the published version.
- No response exposes secrets, raw stack traces, Azure OpenAI keys, database URLs, or internal filesystem paths.
