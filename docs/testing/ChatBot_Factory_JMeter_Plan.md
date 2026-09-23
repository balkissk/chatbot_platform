# ChatBot Factory JMeter Plan

Scope: focused performance testing only. Do not load test every endpoint.
No official SLA was found in the inspected code. Thresholds below are recommendations only and must be confirmed by the project owner.

## Shared Setup

- Base URL: local/staging/Azure backend.
- Use a published assistant with a valid active version.
- Use one non-RAG assistant and one RAG assistant with ready chunks.
- For public REST API tests, set header `x-chatbot-api-key` to a valid regenerated test key.
- Record average, median, P90, P95, throughput, error rate, failed requests, and response sizes.
- Treat 4xx from bad setup as test defects, not performance failures.

## Scenarios

| ID | Target | Method/Endpoint | Payload | Auth | Users | Ramp-up | Duration/Loops | Recommended success criteria |
|---|---|---|---|---|---:|---:|---|---|
| JM-01 | Public REST API session | POST `/public/api/chat/sessions` | `{ "chatbot_id": <id>, "language":"en" }` | API key header | 10 | 60s | 5 loops | Error rate <1%, P95 <2s recommended |
| JM-02 | Public REST API chat | POST `/public/api/chat` | `{ "chatbot_id": <id>, "session_id": <id>, "message":"Hello" }` | API key header | 10 | 60s | 5 min | Error rate <2%, no 500s, P95 <8s recommended |
| JM-03 | Public REST API chat | POST `/public/api/chat` | Same as JM-02 with unique sessions | API key header | 25 | 120s | 5 min | Error rate <3%, stable throughput |
| JM-04 | Public REST API chat | POST `/public/api/chat` | Same as JM-02 with unique sessions | API key header | 50 | 180s | 5 min | Observe saturation; no data corruption or secret leakage |
| JM-05 | RAG runtime chat | POST `/public/chat` or `/public/api/chat` | Known KB question | Public or API key | 5 | 60s | 5 min | Error rate <2%, retrieval succeeds for known answer, P95 <12s recommended |
| JM-06 | RAG runtime chat | POST `/public/chat` or `/public/api/chat` | Mixed relevant/irrelevant questions | Public or API key | 10 | 120s | 5 min | Error rate <3%, safe fallback for irrelevant queries |
| JM-07 | RAG runtime chat | POST `/public/chat` or `/public/api/chat` | Known KB question with sources enabled | Public or API key | 20 | 180s | 5 min | No sustained 500s; P95 and throughput recorded for capacity planning |
| JM-08 | Login light check | POST `/auth/login` | Manager credentials | None | 5 | 30s | 1 loop | Optional only; verify no rate-limit side effects during runtime tests |

## JMeter Implementation Notes

- Use a setup thread group to create or load session IDs before chat load, or create session per virtual user.
- Add HTTP Cookie Manager for public chat session flows where needed.
- Add CSV Data Set Config for varied messages: greeting, known KB question, irrelevant question, long question.
- Add Response Assertions: status 200, JSON contains `response` or `messages`; for API-key failures in negative sampler assert 401.
- Add JSON Extractor for `session_id` from session creation.
- Use Constant Throughput Timer only after baseline runs; initial tests should reveal natural capacity.

## Reporting

For each run report:
- Environment and deployment version.
- Assistant/version/document data used.
- Concurrent users, ramp-up, duration.
- Average, median, P90, P95, throughput, error rate, failed requests.
- Top error messages and whether any internal details were exposed.
