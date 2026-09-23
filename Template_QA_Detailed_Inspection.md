# Template QA Detailed Inspection

Inspection date: 2026-09-18  
Repository: `C:\Users\21628\chatbot_platform`  
Scope: existing Template QA implementation only. This report is based on repository source inspection and does not infer unimplemented behavior.

## 1. Template QA — Purpose and Role

### Confirmed implementation

Template QA is a quality inspection and runtime-confidence feature for flow templates. In the UI it is named **Template QA** and the page title is **Template readiness**. The page description says: "Validate code-defined starter templates before they are used to create assistant draft flows."

It solves the problem of checking reusable starter templates before they are used to initialize or replace assistant draft flows. It gives a template-level readiness report across built-in code-defined templates and custom manager-created templates. The feature is used before or around assistant creation and template selection, not after a production assistant has already been published.

Template QA currently supports:

- Listing all visible built-in and custom templates.
- Computing static readiness indicators: `valid`, `warning`, or `invalid`.
- Filtering templates by search, status, creation exposure, and ownership view.
- Opening a template detail panel.
- Inspecting template metadata, block counts, path counts, block types, issues, revisions, nodes, and transitions.
- Editing metadata and saved test scenarios for editable custom templates.
- Running a template-level test runner against a template graph.

### Lifecycle stage

Template QA is used at the template/library stage of the assistant lifecycle. It validates generic starter flows before they are applied to a concrete assistant draft. It is separate from publishing and production execution.

In assistant creation/template selection, templates are later applied through the endpoint `POST /flows/{flow_id}/template`, which replaces only the current assistant draft flow.

### Intended users

Template QA is accessible to both `admin` and `manager` users:

- Frontend route group `/dashboard` is guarded with `authGuard` and `roleGuard`, with roles `['admin', 'manager']`.
- Backend Template QA read endpoints use `require_roles("admin", "manager")`.
- Template editing and template creation from a flow use `require_workspace_manager`, which only allows `manager`.

### Difference from Flow validation

Template QA validates reusable template definitions. Flow validation validates a concrete assistant version's saved flow from the database.

Template QA performs static template checks such as missing start block, unsupported block type, missing prompts, button paths, condition true/false paths, invalid connector references, duplicate connectors, missing RAG fallback, and invalid canvas positions.

Flow validation is broader for concrete flows. It checks database-backed `Flow`, `FlowNode`, and `FlowTransition` entities and includes checks not present in Template QA, such as reachability from start, isolated nodes, missing next steps, silent machine-only cycles, API request URL/method/timeout validation, handoff contact configuration, AI router routes, AI classifier categories, and RAG continuation behavior.

### Difference from Test Flow

Test Flow is an interactive chat test for a concrete assistant draft/version. It creates a chat session and calls the authenticated chat streaming runtime. Template QA's test runner executes a generic template graph directly from template nodes/transitions, with no assistant-specific version, no persisted conversation session, and a stubbed RAG answer function.

### Difference from Evaluation Center

Evaluation Center validates a concrete assistant version against persisted datasets and test cases. It records evaluation runs and case results in database tables. Template QA validates generic templates and returns transient test results; it does not persist runtime test results.

Evaluation Center has datasets, cases, assertion results, scoring, run history, run comparison, and publish policy integration. Template QA has template structural checks and a lightweight runtime confidence runner.

## 2. Actors and Access Control

### Frontend routes

The frontend routes are defined in `frontend/src/app/app.routes.ts`:

- `/dashboard/template-qa`
- `/dashboard/template-qa/:templateKey`

Both routes live under the `/dashboard` parent route. The parent route has:

- `canActivate: [authGuard, roleGuard]`
- `data: { roles: ['admin', 'manager'] }`

Therefore, both admin and manager users can route to Template QA.

### Sidebar/menu entry

The sidebar entries are in `frontend/src/app/layouts/dashboard-layout/dashboard-layout.component.html`:

- Admin users see **Template QA** under the **Configuration** section.
- Non-admin dashboard users, effectively managers because `/dashboard` is role guarded, see **Template QA** under the **Workspace** section.

### Backend endpoints used

Template QA and related template-library endpoints are implemented in `backend/routes/flow_routes.py`:

- `GET /flow-templates/qa`
- `GET /flow-templates/{template_key}`
- `PATCH /flow-templates/{template_key}`
- `POST /flow-templates/{template_key}/test`
- `GET /flow-templates/{template_key}/revisions`
- `GET /flow-templates`
- `POST /flows/{flow_id}/template-library`
- `POST /flows/{flow_id}/template-library/{template_key}/revisions`
- `POST /flows/{flow_id}/template`

The frontend API methods are in `frontend/src/app/services/api.ts`:

- `getFlowTemplateQa()`
- `getFlowTemplate(templateKey, revision?)`
- `updateFlowTemplate(templateKey, data)`
- `runFlowTemplateTest(templateKey, data = {})`
- `getFlowTemplates(filters)`
- `createFlowTemplateFromFlow(flowId, data)`
- `createFlowTemplateRevisionFromFlow(flowId, templateKey, data = {})`
- `applyFlowTemplate(flowId, templateKey, purpose?, templateRevision?)`

### Permission checks

Read access:

- `GET /flow-templates/qa`: `require_roles("admin", "manager")`
- `GET /flow-templates/{template_key}`: `require_roles("admin", "manager")`
- `POST /flow-templates/{template_key}/test`: `require_roles("admin", "manager")`
- `GET /flow-templates/{template_key}/revisions`: `require_roles("admin", "manager")`
- `GET /flow-templates`: `require_roles("admin", "manager")`

Write/manage access:

- `PATCH /flow-templates/{template_key}`: `require_workspace_manager`
- `POST /flows/{flow_id}/template-library`: `require_workspace_manager`
- `POST /flows/{flow_id}/template-library/{template_key}/revisions`: `require_workspace_manager`
- `POST /flows/{flow_id}/template`: `require_workspace_manager`

`require_workspace_manager` depends on `require_roles("admin", "manager")` and then calls `ensure_workspace_write_access`, which requires `current_user.role == "manager"`. This means admins can read Template QA but cannot perform manager-only workspace write operations.

Custom template visibility:

- Admin can read all custom templates.
- Manager can read custom templates they own or templates marked `is_shared`.
- Manager can update/version only templates they own.

## 3. Template QA Dashboard

### Data source

The dashboard calls `GET /flow-templates/qa` through `ApiService.getFlowTemplateQa()`. The backend response contains:

- `summary`
- `items`

Built-in template data comes from `backend/services/templates.py`, specifically `TEMPLATES` and `TEMPLATE_METADATA`. Custom template data comes from the database table `flow_templates`.

### Total

`Total` displays `summary.total`. It is calculated as `len(items)` after combining:

- all built-in templates from `TEMPLATES`
- all custom templates visible to the current user

### Valid

`Valid` displays `summary.valid`. It counts items with `item["status"] == "valid"`.

Functionally, a valid template has no Template QA issues with severity `error` or `warning`.

### Warnings

`Warnings` displays `summary.warning`. It counts items with `item["status"] == "warning"`.

Functionally, a warning template has at least one warning issue and no error issues.

### Invalid

`Invalid` displays `summary.invalid`. It counts items with `item["status"] == "invalid"`.

Functionally, an invalid template has at least one error issue.

### Custom

`Custom` displays `summary.custom`. It counts items where `item.get("source") == "custom"`.

Custom templates are persisted in the `flow_templates` table.

### Mine

`Mine` displays `summary.mine`. It counts items where `item.get("ownership_scope") == "mine"`.

For custom templates, `ownership_scope` is computed by comparing `template.owner_id` with `current_user.id`. Built-in templates are assigned `ownership_scope = "builtin"`.

### Search

The dashboard search input is frontend-only filtering. It does not call a backend search endpoint. The component filters the already-loaded `items` array.

Search matches:

- template key
- template name
- block type names in `block_types`

The comparison is case-insensitive because the query and fields are converted to lowercase.

### Status filter

The status filter is frontend-only. It filters loaded items by:

- `valid`
- `warning`
- `invalid`

### Creation exposure

The creation exposure filter is frontend-only. It filters by `item.exposed`:

- `Shown in creation`: `exposed === true`
- `Backend only`: `exposed === false`

Functionally, exposed templates can appear in assistant template selection when `exposed_only=true` is used. Backend-only templates remain available for backend/template-library use but are not shown in the assistant creation marketplace when exposed-only filtering is active.

### View / visibility filter

The View filter is frontend-only and filters by ownership scope:

- `All visible`
- `My templates`
- `Shared templates`
- `Built-in templates`

For custom templates, the backend computes `ownership_scope` as `mine` if the current user owns it, otherwise `shared`. Built-in templates are set to `builtin`.

### Refresh

The Refresh button calls the component `load()` method, which calls `GET /flow-templates/qa` again and replaces `items` and `summary`.

### Other controls

The dashboard also implements:

- `Search` button: applies current frontend filters.
- `Reset` button: clears all frontend filters and reapplies.
- `Open` button on each template row: loads detail through `GET /flow-templates/{template_key}` and opens the detail panel.

The table header also shows `summary.hidden_block_templates`, labeled as "`n` use hidden blocks". This is calculated by counting items where `item["hidden_blocks"]` is non-empty.

## 4. Template Readiness Indicators

### Status values

Template QA uses three readiness statuses:

- `valid`
- `warning`
- `invalid`

These are produced in `analyze_template_quality()` in `backend/routes/flow_routes.py`.

### Status calculation

The backend builds an `issues` list. Each issue has:

- `severity`
- `message`
- optional `node_key`

The status is calculated by severity:

- Any `error` issue => `invalid`
- No errors but at least one `warning` => `warning`
- No errors or warnings => `valid`

### Dashboard row metrics

Each template row displays:

- Blocks: `template.nodes_count`
- Paths: `template.transitions_count`
- Errors: number of issues where `issue.severity === "error"`
- Warnings: number of issues where `issue.severity === "warning"`

The block strip displays each block type and count from `block_types`, which is computed during backend analysis.

## 5. Validation Rules

### Confirmed Template QA checks

Template QA validation is implemented by `analyze_template_quality(template_key, template)` in `backend/routes/flow_routes.py`.

Structural checks:

- Template has at least one block.
- Template has no duplicate block keys.
- Template has a block key named `start`.
- Each block has a supported canvas position using `is_valid_canvas_position`.
- Each block has a readable label; missing label is a warning.

Supported block checks:

- Visible/supported block types are:
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
  - `meeting_scheduler`
  - `handoff`
- Hidden/legacy block types are warning-level:
  - `api_request`
  - `ai_router`
  - `ai_classifier`
  - `confidence_check`
  - `lead_score`
  - `action`
- Any block type not in visible or hidden lists is an error.

Block/configuration checks:

- `message`: requires `config.text`; missing text is an error.
- `question`, `collect_name`, `collect_email`, `collect_phone`, `meeting_scheduler`: require `config.prompt`; missing prompt is an error.
- The same input block group also requires `config.field`; missing variable name is an error.
- `buttons`: requires a non-empty `config.buttons` list; missing options are an error.
- For each button label, there must be a transition from that button node with a matching transition label; missing path is an error.
- `condition`: requires `config.field`; missing field is an error.
- `condition`: requires outgoing labels `true` and `false`; missing either path is an error.
- `rag_answer` and `knowledge_search`: missing `config.fallback` is a warning.
- `end`: missing `config.message` is a warning.

Path/transition checks:

- A connector whose source is not an existing node is an error.
- A connector whose target is not an existing node is an error.
- Duplicate connector with the same source, target, and normalized output key is an error.

### Confirmed checks not implemented in Template QA static readiness

The following are not checked by Template QA's static `analyze_template_quality()` function:

- Reachability from the `start` node.
- Unreachable nodes.
- Isolated nodes.
- Missing next step for ordinary non-terminal nodes.
- Silent machine-only cycles.
- General cycle detection.
- API request URL/method/timeout validation.
- Handoff contact completeness.
- AI router routes.
- AI classifier categories.
- RAG continuation/self-loop behavior.
- Maximum node count and maximum transition count.

Some of these are implemented in separate Flow validation for concrete assistant flows, but not in Template QA static readiness.

### Runtime test checks

The Template QA test runner can reveal runtime failures by executing the template graph through `execute_flow`, but this is distinct from static readiness. It can also check expected variables and expected final node for a scenario.

## 6. Template Types and Ownership

### Built-in templates

Built-in templates are code-defined in `backend/services/templates.py` in the `TEMPLATES` dictionary. Static metadata is stored in `TEMPLATE_METADATA`.

Confirmed counts from static source inspection:

- `TEMPLATES`: 38 code-defined templates.
- `TEMPLATE_METADATA`: 20 templates have explicit metadata.
- All 20 metadata entries have `exposed: True`.

Built-in templates are returned with:

- `source: "builtin"`
- `shared: True`
- `ownership_scope: "builtin"`
- `can_edit: False`

Built-in template detail shows a single revision with:

- `revision_number: 1`
- `change_note: "Built-in template"`
- no creator
- no creation date

Built-in templates are read-only. Attempting to patch one returns a backend error: "Built-in templates are read-only".

### Custom templates

Custom templates are persisted in the database table `flow_templates`. They are created from an existing assistant flow through `POST /flows/{flow_id}/template-library`.

Custom template fields include:

- `key`
- `name`
- `description`
- `purpose`
- `is_exposed`
- `is_shared`
- `owner_id`
- `source_flow_id`
- `nodes`
- `transitions`
- `test_scenarios`
- `current_revision_number`
- timestamps

### Mine

`Mine` means a custom template whose `owner_id` equals the current user's ID. The backend labels it with `ownership_scope: "mine"`.

### Shared templates

For managers, the custom template query returns templates where:

- `owner_id == current_user.id`, or
- `is_shared == True`

If a visible custom template is not owned by the current manager, the frontend labels it as shared.

### Creation visibility / creation exposure

For built-ins, creation exposure comes from `TEMPLATE_METADATA[template_key]["exposed"]`. If a built-in has no metadata entry, `template_metadata()` returns `exposed: False`.

For custom templates, creation exposure comes from `FlowTemplate.is_exposed`.

Assistant template selection calls `GET /flow-templates` with `exposed_only=true`, so only exposed templates are shown in the template marketplace.

### Read-only templates

Built-in templates are read-only. The detail panel displays a read-only note: "Built-in templates can be inspected and applied, but their metadata is managed in code."

Custom templates not editable by the current user are also effectively read-only in the UI because the edit form appears only when `selected.can_edit` is true.

### Editable templates

Custom templates are editable when `_can_manage_custom_template()` returns true:

- admin: allowed by helper, but update endpoint uses `require_workspace_manager`, so admin cannot reach the update operation successfully.
- manager: can edit templates where `owner_id == current_user.id`.

Confirmed editable fields through `PATCH /flow-templates/{template_key}`:

- name
- description
- purpose
- is_exposed
- is_shared
- test_scenarios

The patch endpoint does not update template nodes/transitions. New nodes/transitions are captured by creating a new revision from a flow.

## 7. Template Detail Panel

The detail panel is implemented in `frontend/src/app/pages/template-qa/template-qa.component.html` and loaded by `TemplateQaComponent.openTemplate()`.

### Header

Shown fields:

- Source label: "Manager template" when `selected.source === 'custom'`, otherwise "Built-in template".
- Template name: `selected.name`.
- Description: `selected.description` or fallback "Reusable assistant flow template."
- Status badge: `selected.status`.

### Purpose

Shows `purposeLabel(selected.primary_purpose)`.

For built-ins, `primary_purpose` comes from `TEMPLATE_METADATA`, or `"internal"` when no metadata exists. For custom templates, it comes from `FlowTemplate.purpose`.

### Revision

Shows `v{selectedRevision(selected)} / v{latestRevision(selected)}`.

- Selected revision is `selected.selected_revision_number`.
- Latest revision is `selected.current_revision_number`.

Built-ins always display `v1 / v1`.

### Blocks

Shows `selected.nodes_count`, computed by Template QA analysis from the number of nodes.

### Paths

Shows `selected.transitions_count`, computed from the number of transitions.

### Visibility

Shows:

- `Creation` when `selected.exposed` is true.
- `Library only` when `selected.exposed` is false.

### Version history

Shows `selected.revisions?.length || 1` revisions and "Latest v...".

Each revision button displays:

- revision number
- `change_note` or revision name
- block count
- path count

Clicking a revision reloads template detail with query parameter `revision`.

### Edit form

Shown only when `selected.can_edit` is true.

Fields:

- Template name
- Purpose
- Description
- Show in assistant creation
- Share with other managers

The form calls `PATCH /flow-templates/{template_key}`.

### Read-only note

Shown when `selected.can_edit` is false.

### Flow preview

Shows:

- A summary of block types and counts.
- Each node's type, label, and key.

The data comes from `selected.nodes`.

### Paths panel

Shows each transition as:

`source_node_key -> target_node_key`

If the transition has a label, it displays the label in parentheses.

### Runtime confidence / test panel

Contains:

- Scenario name
- Expected final node
- Test messages
- Expected variables JSON
- Run ad hoc test
- Run saved/default
- Save scenario and run, only for editable templates
- Test result status badge
- Path
- Scenario transcript
- Errors

## 8. Revision and Version History

### Confirmed implementation

Custom template revisions are persisted in `flow_template_revisions`.

Revision fields:

- `template_id`
- `revision_number`
- `name`
- `description`
- `purpose`
- `nodes`
- `transitions`
- `test_scenarios`
- `change_note`
- `created_by`
- `created_at`

Creating a template from a flow creates an initial revision. Creating a revision from a flow increments the revision number and updates the current template payload.

The detail endpoint can load a selected revision:

`GET /flow-templates/{template_key}?revision={number}`

### Latest revision

For custom templates, latest revision is queried by `revision_number.desc()`. The template also stores `current_revision_number`.

### Previous revisions

Previous custom revisions are listed in the detail panel. Selecting a previous revision reloads the detail panel for that revision.

### Restore/rollback

Not implemented as a dedicated Template QA action. There is no endpoint to restore a previous template revision as current. Selecting a previous revision is inspection-only.

### Comparison

Not implemented. There is no template revision diff/compare feature.

### Immutable built-in revisions

Built-in templates are code-defined and read-only. The UI represents each built-in template as one synthetic revision, `v1`, with change note "Built-in template".

## 9. Flow Preview

### Generation

For built-in templates, the backend calls `template_generated_payload(template_key)` to convert code-defined tuple templates into node and transition dictionaries.

For custom templates, nodes and transitions come from the selected `FlowTemplate` or `FlowTemplateRevision` JSON payload.

### Information shown

The Flow Preview shows:

- block type summary, e.g. `message x1 · question x2`
- node cards with type, label, and key

The Paths panel shows:

- source node key
- target node key
- optional transition label

### Block types displayed

The preview displays whatever node types are present in `selected.nodes`. It does not limit display to only supported block types.

### Executable or visual

The Flow Preview itself is visual inspection only. Execution happens only through the Runtime Confidence / Template Test Runner section.

## 10. Runtime Confidence / Template Test Runner

### Scenario name

The scenario name is edited in the detail panel and sent as `name` in `FlowTemplateTestRun`. If empty, the frontend sends "Smoke test". The backend result falls back to "Ad hoc test" if the scenario object has no name.

### Expected final node

The expected final node is sent as `expected_final_node_key`. If provided, the backend compares it to the final `current_node_key` after execution.

If they differ, the scenario fails with an error message like:

`Expected final node 'x', got 'completed'.`

### Test messages

The UI accepts one user message per line. The frontend trims blank lines and sends a `messages` array.

If the user runs an ad hoc test with the field empty, the frontend sends `messages: []`.

### Expected variables JSON

The UI accepts JSON. The frontend parses it before calling the API. If invalid JSON is entered, the frontend does not call the backend and shows: "Expected variables must be valid JSON."

The backend compares each expected variable key with the final variables dictionary using equality.

### Run ad hoc test

`Run ad hoc test` calls `POST /flow-templates/{template_key}/test` with the current scenario payload.

Important behavior:

- Because the frontend always includes `messages` as an array, an empty ad hoc message textarea sends `messages: []`.
- The backend treats a payload with `messages is not None` as an explicit ad hoc scenario.
- Therefore, empty ad hoc messages execute only the startup turn and do not trigger the backend auto-drive loop.

### Run saved/default

`Run saved/default` calls `POST /flow-templates/{template_key}/test` with `{}`.

Backend behavior:

- If the template has saved `test_scenarios`, it runs those saved scenarios.
- If no saved scenarios exist, it creates one default scenario: `FlowTemplateTestRun(name="Auto path smoke test")`.
- In that default case, `messages` is `None`, so the backend auto-drives the first path using default messages generated from current node type.

### Save scenario and run

Shown only for editable templates. It replaces `detailForm.test_scenarios` with the current scenario and calls `saveDetail()`, then still calls the test endpoint with the same scenario. This saves the scenario metadata on the custom template and runs it.

### Execution mechanism

The backend builds an in-memory runtime graph:

- `Flow(id=0, version_id=0, name="Template Test")`
- `FlowNode` instances from template nodes
- `FlowTransition` instances from template transitions

It calls the real `execute_flow()` function from `services.flow_runtime`, passing:

- `db=None`
- `version_id=0`
- `message`
- `current_node_key`
- `variables`
- `rag_answer=_test_rag_answer`
- `allow_rag_fallback=True`
- `_runtime_graph=runtime_graph`

### LLM/RAG behavior

The Template QA test runner does not call the real LLM or real RAG retrieval. It passes `_test_rag_answer`, which returns:

- `response`: configured `test_response` or `Test AI answer for: ...`
- `mode_used`: `template_test_rag`
- `sources`: empty list

This means Runtime Confidence is deterministic with respect to the template graph and provided messages; it is not an LLM quality test.

### What happens if no user messages are provided

Two cases exist:

- Saved/default with no saved scenarios: backend auto-drives up to 12 turns using `_default_message_for_node()`.
- Ad hoc empty textarea: frontend sends `messages: []`, so backend does not auto-drive beyond the initial start execution.

Default messages by node type include:

- `collect_email`: `test@example.com`
- `collect_phone`: `+21612345678`
- `collect_name`: `Test User`
- `meeting_scheduler`: `Tomorrow at 10:00`
- `buttons`: first button option or first labeled outgoing transition
- `question`: email/phone/budget-aware defaults or `Test question`
- `rag_answer` / `knowledge_search`: `Test question`

### Expected variables checking

The backend loops through `expected_variables`. For each key, it checks:

`variables.get(key) == expected`

If not equal, it appends an error and the scenario fails.

### Expected final node checking

If `expected_final_node_key` is not `None`, the backend compares it with final `current_node_key`. If they differ, the scenario fails.

### Result/status returned

The endpoint returns:

- `template_key`
- `template_name`
- overall `status`: `passed` or `failed`
- `scenario_count`
- `results`

Each scenario result contains:

- `name`
- `status`
- `errors`
- `path`
- `final_node_key`
- `variables`
- `transcript`

Each transcript turn contains:

- input
- response
- messages
- current node key
- mode used

### Persistence

Runtime test results are not persisted. They are returned directly to the frontend.

Saved/default scenarios can be persisted only for custom editable templates through the template's `test_scenarios` JSON field. Built-in templates have no persisted saved scenarios in Template QA.

### Determinism

The Template QA test runner is deterministic for supported deterministic block behavior because it does not call real LLM/RAG. However, it still depends on the behavior of `execute_flow()` and template configuration.

### Limitations

Confirmed limitations:

- It does not call real LLM generation.
- It does not call real RAG retrieval.
- It does not persist test run history.
- It has only simple assertions: expected variables and expected final node.
- It does not calculate scores.
- It does not run datasets.
- It does not compare runs.

## 11. Backend Architecture

### Main route file

Template QA is implemented inside:

`backend/routes/flow_routes.py`

Important functions/classes:

- `FlowTemplateApply`
- `FlowTemplateCreate`
- `FlowTemplateUpdate`
- `FlowTemplateTestRun`
- `FlowTemplateRevisionCreate`
- `analyze_template_quality()`
- `_analyze_payload_template()`
- `_runtime_graph_from_payload()`
- `_test_rag_answer()`
- `_default_message_for_node()`
- `_run_template_scenario()`
- `_template_test_result()`
- `_custom_template_query()`
- `_template_from_db()`
- `_create_template_revision()`
- `template_quality_report()`
- `get_flow_template_detail()`
- `update_flow_template()`
- `run_flow_template_test()`
- `list_flow_template_revisions()`
- `create_flow_template_from_flow()`
- `create_flow_template_revision_from_flow()`
- `apply_flow_template()`

### Services

`backend/services/templates.py`:

- Defines built-in `TEMPLATES`.
- Defines `TEMPLATE_METADATA`.
- Provides `template_metadata()`.
- Provides `template_options()`.
- Provides `template_generated_payload()`.
- Provides `replace_flow_with_template()`.
- Provides `create_starter_flow()`.
- Handles language localization for built-in template nodes.

`backend/services/flow_runtime.py`:

- Provides `execute_flow()`, used by Template QA runtime tests and by real assistant chat runtime.

`backend/services/flow_validation.py`:

- Provides `validate_flow_version()`, used for concrete assistant flow validation, not directly used by Template QA static readiness.

`backend/services/generated_flow.py`:

- Provides `ensure_generated_flow_is_valid()`, used when creating custom templates from flows, creating template revisions from flows, applying templates, and applying generated flows.

### Models/entities

`backend/models/flow_template.py`:

- `FlowTemplate`
- `FlowTemplateRevision`

`backend/models/flow.py`:

- `Flow`
- `FlowNode`
- `FlowTransition`

Related models:

- `Chatbot`
- `Project`
- `VersionChatbot`
- `User`

### Database tables involved

Template QA custom templates:

- `flow_templates`
- `flow_template_revisions`

Assistant flow application:

- `flows`
- `flow_nodes`
- `flow_transitions`
- `versions`
- `chatbots`

Built-in templates:

- Not persisted in the database.
- Defined in Python code in `backend/services/templates.py`.

### Persistence vs dynamic computation

Template QA readiness data is computed dynamically when the QA endpoint is called. The readiness status and issue list are not stored in database columns.

Persisted data:

- custom template metadata and payloads
- custom template revisions
- saved test scenarios for custom templates

Computed dynamically:

- status
- issue list
- block type counts
- hidden block counts
- dashboard summary counts
- runtime test results

## 12. Frontend Architecture

### Component

Main component:

`frontend/src/app/pages/template-qa/template-qa.component.ts`

Template:

`frontend/src/app/pages/template-qa/template-qa.component.html`

Styles:

`frontend/src/app/pages/template-qa/template-qa.component.css`

### Routing

Routes:

- `/dashboard/template-qa`
- `/dashboard/template-qa/:templateKey`

### State

The component uses Angular signals:

- `items`
- `summary`
- `loading`
- `error`
- `detail`
- `detailLoading`
- `detailSaving`
- `detailError`
- `detailSuccess`
- `testLoading`
- `testResult`
- `testError`
- `appliedFilters`

Regular component fields hold form/filter values:

- `detailForm`
- `scenarioMessages`
- `scenarioName`
- `expectedVariables`
- `expectedFinalNode`
- `search`
- `status`
- `exposure`
- `ownershipView`

### API calls

The component calls:

- `getFlowTemplateQa()`
- `getFlowTemplate(templateKey, revision?)`
- `updateFlowTemplate(templateKey, data)`
- `runFlowTemplateTest(templateKey, data)`

### Loading/error states

Implemented states:

- Dashboard loading text: "Loading template QA report..."
- Dashboard error banner from `error`
- Empty state: "No templates match these filters."
- Detail loading text: "Loading template detail..."
- Detail error banner from `detailError`
- Save success banner: "Template updated"
- Runtime test error banner from `testError`
- Test button loading label: "Running..."

## 13. Relationship with Assistant Creation

### How a verified template is later used

Template QA itself does not apply templates to assistants. It inspects templates and can run template-level tests.

Assistant template usage happens in:

- `frontend/src/app/pages/template-selection/template-selection.component.ts`
- `frontend/src/app/pages/template-selection/template-selection.component.html`
- backend endpoint `POST /flows/{flow_id}/template`

Template selection loads templates with:

`GET /flow-templates?purpose={purpose}&exposed_only=true`

When a manager selects and confirms a template, the frontend:

1. Loads the assistant builder context.
2. Gets the draft flow ID.
3. Calls `POST /flows/{flow_id}/template`.
4. Navigates back to Flow Builder with template query parameters.

### Whether Template QA changes templates

Template QA can change only editable custom template metadata and saved test scenarios through the detail form. It does not edit built-in templates and does not edit custom template nodes/transitions.

Nodes/transitions are changed by creating a new custom template revision from an existing flow, not directly inside the Template QA panel.

### Use template / template selection behavior

Template selection applies the selected template to an assistant draft flow and replaces the current draft. The UI warns: "Applying it replaces only the current draft flow."

### Are invalid templates blocked from creation?

No direct evidence was found that Template QA status blocks a template from appearing in template selection.

Template selection filters by purpose and `exposed_only=true`, not by QA status. However, when applying a template, the backend calls `ensure_generated_flow_is_valid()`. If the selected template contains an incomplete workflow configuration, the apply request can fail and the frontend shows: "The selected template contains an incomplete workflow configuration."

### Do warnings still allow creation?

Template QA warning status is not directly checked by template selection. A warning template can appear if exposed and purpose-compatible. Whether application succeeds depends on backend apply-time validation, not Template QA's warning status.

## 14. Relationship with Flow Validation and Test Flow

### Flow Validation

Flow validation endpoint:

`GET /versions/{version_id}/flow/validate`

Backend function:

`validate_flow_version()` in `backend/services/flow_validation.py`

Target:

- concrete assistant version
- persisted flow in database

Checks include:

- flow exists
- non-empty nodes
- max nodes/transitions
- start node exists
- canvas position validity
- broken transition source/target
- duplicate transitions
- reachability from start
- isolated nodes
- silent machine-only cycles
- missing next steps
- buttons without options or without paths
- condition true/false paths
- RAG fallback and continuation
- input variable names
- set variable config
- API method/URL/timeout
- meeting variable
- handoff contact method
- AI router routes
- AI classifier categories

### Test Flow

Frontend route:

`/dashboard/projects/:projectId/chatbots/:chatbotId/flow/test`

Frontend component:

`frontend/src/app/pages/flow-test/flow-test.component.ts`

Backend routes used:

- `POST /chat/sessions`
- `POST /chat/stream`

Target:

- concrete assistant draft/version
- actual chat session
- runtime stream

Test Flow starts a persisted session, sends `__start__`, streams responses, tracks debug state, and can use real runtime behavior including configured LLM/RAG paths.

### Template QA

Target:

- generic template payload
- built-in or custom template
- in-memory runtime graph

It is not tied to one assistant version unless a custom template originated from a flow.

## 15. Relationship with Evaluation Center

### Evaluation Center target

Evaluation Center targets concrete assistant versions and datasets.

Routes and services:

- `backend/routes/evaluation_routes.py`
- `backend/services/evaluation_engine.py`
- frontend page `frontend/src/app/pages/evaluations`

Database tables:

- `evaluation_datasets`
- `evaluation_cases`
- `evaluation_runs`
- `evaluation_case_results`
- `evaluation_policies`

### What Evaluation Center validates

Evaluation Center evaluates runtime behavior against persisted cases and assertions, including:

- expected response mode
- expected keywords
- forbidden keywords
- expected source document IDs
- expected source patterns
- minimum source count
- minimum retrieval score
- expected/forbidden flow nodes
- expected final node
- variable assertions
- maximum latency
- fallback expectation
- handoff expectation
- expected failure category
- runtime technical failure status

It computes case scores and overall run scores.

### LLM-as-judge behavior

The code contains judge-related configuration fields, but run results set:

- `enabled: False`
- message: "LLM-as-judge is disabled by default for this run."

Therefore, based on current implementation, Evaluation Center should not be described as actively using LLM-as-judge by default.

### Difference from Template QA

Template QA validates generic templates. Evaluation Center validates concrete assistant versions with datasets and persisted results.

Template QA runtime tests are transient. Evaluation Center runs are persisted and can be listed, read, cancelled, compared, and used by publication policy.

## 16. Current Confirmed Limitations

Confirmed Template QA limitations:

- No direct editing of built-in templates.
- No direct editing of template nodes/transitions in the Template QA UI.
- No dedicated rollback/restore endpoint for template revisions.
- No template revision comparison/diff.
- Template QA static readiness does not check reachability or unreachable nodes.
- Template QA static readiness does not check isolated nodes.
- Template QA static readiness does not check cycles.
- Template QA static readiness does not check missing next steps for ordinary non-terminal blocks.
- Template QA static readiness does not validate API request URL/method/timeout details.
- Template QA static readiness does not validate handoff contact completeness.
- Template QA static readiness does not validate AI router routes or AI classifier categories.
- Template QA runtime tests do not use real LLM generation.
- Template QA runtime tests do not use real RAG retrieval.
- Template QA runtime test results are not persisted.
- Runtime Confidence assertions are limited to expected variables and expected final node.
- Template selection does not appear to filter templates by Template QA readiness status.
- Built-in templates do not have persisted saved test scenarios.

Unknown / cannot be confirmed from inspected code:

- Whether all existing production data has matching migrations applied.
- Whether every built-in template is valid in a live database/runtime without executing all template tests.
- Whether hidden/internal templates are intentionally exposed elsewhere outside the inspected routes.

## 17. PFE Report — Functional Description

Template QA is a template-readiness module in ChatBot Factory that allows administrators and managers to inspect reusable assistant flow templates before they are used to create or replace assistant draft flows. It centralizes the verification of built-in and custom templates by displaying readiness indicators, structural issues, block/path counts, visibility metadata, ownership information, revision history, and a visual flow preview. It also includes a lightweight runtime-confidence runner that executes the template graph with deterministic test messages and checks expected variables or final node outcomes.

The feature helps reduce the risk of starting an assistant from an incomplete or structurally incorrect template. It is used before the template is applied to an assistant draft, while Flow Validation, Test Flow, and Evaluation Center operate on concrete assistant versions.

## 18. PFE Report — Analysis / Use Case

Use case: **Vérifier un modèle prédéfini**

Primary actor:

- Admin or Manager

Preconditions:

- The actor is authenticated.
- The actor has access to the dashboard.
- At least one built-in or custom template exists.

Main scenario:

1. The actor opens **Template QA** from the sidebar.
2. The system loads the template readiness report.
3. The actor reviews global indicators: Total, Valid, Warnings, Invalid, Custom, and Mine.
4. The actor filters templates by status, exposure, ownership, or search text.
5. The actor opens a template detail panel.
6. The system displays template metadata, revision information, blocks, paths, issues, and a flow preview.
7. The actor runs an ad hoc or saved/default runtime-confidence test.
8. The system executes the template graph and returns a passed/failed result with transcript, path, variables, and errors.
9. If the template is custom and editable, the actor can update metadata or saved test scenarios.

Postconditions:

- No assistant is modified by inspection alone.
- If metadata is saved for an editable custom template, the custom template record is updated.
- Runtime test results are displayed but not persisted as run history.

Alternative scenario:

- If the selected template is built-in, the system displays it as read-only.
- If a test scenario fails, the system displays errors but does not automatically block template use in the template marketplace.

## 19. PFE Report — Conception Description

Template QA is designed as a dashboard and inspection workflow around reusable flow templates. The conception separates three concerns:

1. Template source management:
   - built-in templates are defined in backend code
   - custom templates are persisted in database tables
   - template revisions are persisted separately

2. Readiness analysis:
   - the backend computes structural status dynamically
   - each template receives a status: valid, warning, or invalid
   - issues identify errors and warnings at template or node level

3. Runtime confidence:
   - the backend transforms a template payload into an in-memory runtime graph
   - the existing flow runtime is reused
   - real LLM/RAG calls are replaced by deterministic test responses

The frontend presents this information as a dashboard with filters and a detail drawer. Admins and managers can inspect templates, while only managers can perform workspace-write operations such as custom template updates.

## 20. PFE Report — Réalisation Description

The implementation is split between Angular frontend components and FastAPI backend endpoints.

On the frontend, `TemplateQaComponent` loads the QA report using `ApiService.getFlowTemplateQa()`, filters the loaded result in memory, and opens template details with `ApiService.getFlowTemplate()`. The UI displays summary cards, filter controls, readiness rows, issue lists, revision history, read-only/editable state, flow preview, paths, and runtime test results.

On the backend, `flow_routes.py` exposes Template QA endpoints. Built-in templates are read from `services/templates.py`, while custom templates are read from `flow_templates` and `flow_template_revisions`. The function `analyze_template_quality()` computes static readiness by checking node structure, supported block types, required configuration fields, and transition consistency. The runtime test endpoint builds an in-memory graph and calls `execute_flow()` with a test RAG function, returning transient pass/fail scenario results.

Template application is implemented separately through `POST /flows/{flow_id}/template`. This endpoint validates the selected template and replaces the assistant draft flow. Template QA does not itself create assistants or publish versions.

## 21. Recommended Screenshots for the PFE Report

Recommended screenshots:

1. Template QA sidebar entry for Admin or Manager.
2. Template QA dashboard header and summary indicators: Total, Valid, Warnings, Invalid, Custom, Mine.
3. Filter bar showing Search, Status, Creation exposure, and View filters.
4. Readiness report list with at least one valid template and, if available, one warning/invalid template.
5. Template detail panel header showing purpose, revision, blocks, paths, and visibility.
6. Version history section in the detail panel.
7. Flow Preview section showing block cards.
8. Paths section showing source-to-target transitions.
9. Runtime Confidence / Template Test Runner form.
10. Runtime test result transcript showing status, path, and variables/errors.
11. Read-only built-in template note.
12. Editable custom template form, if a custom owned template exists.
13. Template marketplace screen to show where exposed templates are later selected.

## 22. Comparison Table: Template QA vs Flow Validation vs Test Flow vs Evaluation Center

| Feature | Template QA | Flow Validation | Test Flow | Evaluation Center |
|---|---|---|---|---|
| Primary target | Generic flow templates | Concrete assistant version flow | Concrete assistant draft/version chat runtime | Concrete assistant version |
| Main purpose | Inspect template readiness before use | Detect structural/publish blockers in a saved flow | Manually test conversation behavior | Run datasets and assertions against a version |
| Stage | Before applying templates to assistants | During flow building/publishing readiness | During assistant testing | Pre-release/regression/quality evaluation |
| Data source | Built-in code templates and custom template tables | `flows`, `flow_nodes`, `flow_transitions` | Chat session and selected version | Evaluation datasets/cases and version runtime |
| Persistence | Custom templates/revisions/scenarios persisted; readiness computed dynamically; test results not persisted | Validation result computed dynamically | Conversation session/messages persisted by chat runtime | Datasets, cases, runs, case results, policies persisted |
| Runtime execution | Optional in-memory `execute_flow` with stub RAG | No runtime conversation execution | Real chat stream endpoint | Runtime execution per case |
| LLM/RAG | Stubbed RAG response; no real LLM/RAG | Not applicable | Can use configured runtime behavior | Uses runtime; judge disabled by default in inspected code |
| Assertions | Expected variables and expected final node | Structural validity errors | Manual human observation | Many persisted assertions with scoring |
| Revision/history | Custom template revisions listed | Version flow only | Session transcript | Run history and run comparison |
| Blocks invalid templates? | Not directly in template selection; apply-time validation may fail | Blocks publish/test paths where used | Not a blocker itself | Can affect publication policy |
| Main users | Admin read, Manager read/manage own custom templates | Admin/Manager read; manager workflows | Manager route | Admin/Manager read; Manager write/run |

## 23. Relevant Source Files / Components / Routes

### Frontend

- `frontend/src/app/pages/template-qa/template-qa.component.ts`
- `frontend/src/app/pages/template-qa/template-qa.component.html`
- `frontend/src/app/pages/template-qa/template-qa.component.css`
- `frontend/src/app/services/api.ts`
- `frontend/src/app/app.routes.ts`
- `frontend/src/app/layouts/dashboard-layout/dashboard-layout.component.html`
- `frontend/src/app/pages/template-selection/template-selection.component.ts`
- `frontend/src/app/pages/template-selection/template-selection.component.html`
- `frontend/src/app/pages/flow-test/flow-test.component.ts`
- `frontend/src/app/pages/evaluations/evaluations.component.ts`

### Backend

- `backend/routes/flow_routes.py`
- `backend/services/templates.py`
- `backend/services/flow_runtime.py`
- `backend/services/flow_validation.py`
- `backend/services/generated_flow.py`
- `backend/routes/evaluation_routes.py`
- `backend/services/evaluation_engine.py`
- `backend/services/auth.py`

### Models and migrations

- `backend/models/flow_template.py`
- `backend/models/flow.py`
- `backend/models/evaluation.py`
- `backend/alembic/versions/4c8b2f1a6d90_add_flow_templates.py`
- `backend/alembic/versions/5d7e2c9a1b44_repair_flow_template_test_scenarios.py`
- `backend/alembic/versions/6f1a9d2b3c45_repair_flow_template_revision_number.py`
- `backend/alembic/versions/9e3b6c1d2045_add_evaluation_center.py`

### API endpoints

- `GET /flow-templates/qa`
- `GET /flow-templates/{template_key}`
- `PATCH /flow-templates/{template_key}`
- `POST /flow-templates/{template_key}/test`
- `GET /flow-templates/{template_key}/revisions`
- `GET /flow-templates`
- `POST /flows/{flow_id}/template-library`
- `POST /flows/{flow_id}/template-library/{template_key}/revisions`
- `POST /flows/{flow_id}/template`
- `GET /versions/{version_id}/flow/validate`
- `POST /chat/sessions`
- `POST /chat/stream`
- `POST /evaluations/runs`

### Confirmed not implemented in Template QA

- Built-in template editing.
- Dedicated template rollback/restore.
- Template revision comparison.
- Historical Template QA test run storage.
- LLM-as-judge for Template QA.
- Real RAG retrieval for Template QA runtime tests.
- Template QA readiness filtering in assistant template selection.
