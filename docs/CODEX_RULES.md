# ChatBot Factory Codex Rules

These rules apply by default unless the current prompt explicitly overrides them.

## 1. Inspect before implementing

Before changing code:

* inspect only the files relevant to the requested feature
* identify what already exists
* reuse existing services, APIs, helpers, components, models, and business logic
* do not duplicate functionality
* make the smallest clean implementation
* do not ask questions that can be answered by inspecting the repository

Do NOT scan the entire repository unless genuinely necessary.

## 2. Strict scope control

Only change what the current task requires.

Do NOT automatically:

* refactor unrelated code
* redesign unrelated pages
* rename unrelated files/components
* perform broad cleanup
* fix unrelated warnings
* fix unrelated failing tests
* add speculative features
* add speculative abstractions
* migrate unrelated code
* reformat large unrelated files
* add dependencies unless genuinely required

If an unrelated issue is discovered, mention it briefly in the final report instead of fixing it.

## 3. FRONTEND TEST RULE - IMPORTANT

Do NOT run frontend unit tests by default.

Do NOT run:

* Vitest
* Angular component unit tests
* frontend test suites
* frontend test coverage

unless the current prompt explicitly asks for frontend unit tests or a specific frontend logic bug truly requires them.

For normal Angular/UI/UX work, validation should normally be:

`npm run build`

Then inspect the affected runtime path for obvious integration/state/template issues.

For frontend work, prioritize:

* successful compilation
* Angular template validation
* TypeScript validation
* real browser/runtime behavior
* API/network behavior
* manual workflow validation

Do not spend tokens/time maintaining frontend unit-test infrastructure unless specifically requested.

## 4. TARGETED TESTS ONLY

Never automatically run ALL project tests.

Tests must be proportional to what changed.

If a feature or service was changed, run ONLY:

1. the directly related test file(s)
2. a small number of closely related regression tests when necessary

Examples:

If publication readiness changed:
run publication readiness tests and directly related publish/regression tests.

If Evaluation Engine button handling changed:
run Evaluation Engine/button-flow tests relevant to that behavior.

If authentication changed:
run authentication/authorization tests relevant to that code.

If one backend service changed:
do NOT run every backend test unless there is a strong technical reason.

If a frontend CSS/layout change was made:
do NOT run backend tests.

If only documentation changed:
run no tests.

## 5. Full test suites are exceptional

Do NOT run:

* all backend tests
* all frontend tests
* all repository tests
* broad regression suites

by default.

A full test suite is allowed only when:

* explicitly requested,
* the change affects a broad foundational subsystem,
* multiple modules are tightly coupled and targeted testing is insufficient,
* or there is strong evidence that a broad regression may have occurred.

If considering a full suite, first ask:
"Can this change be validated reliably with focused tests?"

If yes, use focused tests.

## 6. Stop once relevant validation passes

Do not keep running additional tests simply to increase test counts.

Once:

* the directly affected tests pass,
* closely related important regression tests pass where appropriate,
* and the relevant build/runtime validation passes,

stop validation.

Do not run tests unrelated to the changed behavior.

## 7. Do not chase unrelated failures

If a targeted or broader command exposes an unrelated pre-existing failure:

* do not fix it
* do not investigate deeply
* do not expand the task

Report:

"Unrelated pre-existing failure detected: <brief description>."

Continue validating the requested feature using focused tests when possible.

## 8. Avoid repeated commands

Do not repeatedly run the same:

* build
* tests
* repository searches
* package installs
* dependency resolution
* lint commands

without a concrete reason.

If `npm run build` passed and no frontend code changed afterward, do not run it again.

If the relevant backend tests passed and no related backend code changed afterward, do not rerun them.

## 9. Do not run lint/format globally

Do not automatically run:

* full ESLint
* repository-wide Prettier
* global Python formatting
* full static-analysis suites

Only use targeted linting/formatting if required by the current task or build.

Never reformat unrelated files.

## 10. Warnings are not automatically tasks

Do not spend time fixing unrelated warnings such as:

* Python datetime deprecations
* minor CSS warnings
* unrelated lint warnings
* warnings from dependencies

unless they affect correctness, security, production behavior, or the requested feature.

Mention relevant warnings briefly if necessary.

## 11. Backend business logic requires focused validation

When changing important backend business rules, targeted tests ARE required.

Examples:

* publication readiness
* evaluation scoring
* regression blocking
* authentication
* authorization
* project isolation
* version publishing
* RAG/retrieval
* database state transitions

Run focused tests covering:

* intended successful behavior
* important blocking/failure behavior
* preservation of important state/invariants

Do not replace meaningful backend validation with only compilation.

## 12. Frontend vs backend validation

Frontend UI/UX-only change:

* `npm run build`
* runtime/manual inspection
* no frontend unit tests by default
* no backend tests unless backend behavior changed

Backend business-logic change:

* focused relevant backend tests
* no frontend tests unless frontend contract changed

Frontend + backend feature:

* backend targeted tests for changed business logic
* frontend build
* targeted real workflow inspection

## 13. No unnecessary dependencies

Before adding an npm/Python package:

* check existing dependencies
* prefer Angular/Python/native functionality
* only add the dependency if genuinely justified

Do not add libraries for simple UI behavior that can be implemented cleanly with existing tools.

## 14. API/business-rule ownership

Do not recreate backend business rules in the frontend.

Backend remains source of truth for:

* authentication
* authorization
* publication readiness
* regression blocking
* evaluation scoring
* version state
* assistant/project permissions
* RAG/runtime behavior

Frontend should display and interact with backend state.

Reuse existing endpoints before creating new ones.

## 15. Database discipline

Do not create migrations for frontend-only work.

Do not reset/delete/recreate development data unless specifically requested.

Create Alembic migrations only when the actual persisted model/schema needs to change.

## 16. UI/UX discipline

For UI tasks:

* prioritize hierarchy and clarity
* keep visual design restrained
* avoid excessive cards
* avoid excessive nesting
* avoid saturated screens
* use neutral surfaces
* brand accent for interactions
* green only for success
* red for failure/destructive states
* amber for warnings
* preserve existing functionality
* prefer incremental redesigns over large rewrites

Do not redesign unrelated pages.

## 17. Token/time efficiency

Optimize work for useful engineering value.

Spend tokens/time on:

* understanding relevant architecture
* implementation
* correctness
* real workflow
* backend invariants
* production-impacting bugs
* meaningful UX

Avoid spending tokens/time on:

* frontend tests for simple UI changes
* unrelated tests
* full suites without justification
* fixing unrelated warnings
* broad repository exploration
* speculative refactors
* excessive final reports
* repeatedly explaining known architecture
* cosmetic cleanup outside scope

## 18. Validation decision examples

### CSS/UI layout change

Run:

* `npm run build`

Do not run:

* Vitest
* backend tests
* full test suite

### Angular API integration change

Run:

* `npm run build`
* inspect/test the affected runtime/API workflow

Do not automatically run frontend unit tests.

### Publication readiness backend change

Run:

* publication readiness tests
* directly related publish tests
* regression-gate tests if affected

Do NOT automatically run the entire backend suite.

### Evaluation Engine change

Run:

* directly affected Evaluation Engine tests
* closely related runtime tests only when necessary

Do not run unrelated project/admin/RAG tests.

### Documentation change

Run:

* nothing unless validation is genuinely necessary

## 19. Final report

Keep the final report concise.

Normally include only:

* what changed
* files changed
* important behavior
* validation performed
* result
* relevant unresolved issue if one exists

Do not list every command/search/read operation.

## 20. Definition of Done

Frontend task:

* requested behavior implemented
* existing behavior preserved
* no unnecessary backend change
* `npm run build` passes
* relevant runtime path checked

Backend task:

* requested logic implemented
* directly related focused tests pass
* important state/invariants verified
* unrelated systems untouched

Mixed task:

* relevant backend focused tests pass
* frontend build passes
* end-to-end interaction path checked

Once the above is satisfied, STOP.

Do not continue running unrelated tests or performing cleanup simply because additional work is possible.
