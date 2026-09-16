# Chapter 5 Implementation Inspection: Assistant Creation Modes After Assistant Creation

Scope: focused inspection of the three creation-mode continuations after an assistant record has already been created: Start From Scratch, Use Template, and Build With AI.

Constraints followed: no tests, builds, linters, Docker, Git commands, deployments, or source modifications. Only directly related frontend components, API methods, backend routes/services, schemas, and models were inspected.

## Verified Feature Entry Point

The creation modal is `frontend/src/app/pages/chatbots/assistant-creation-wizard.component.ts` and `.html`.

The wizard has three steps:

- Step 1: assistant purpose, stored as `assistant_type`.
- Step 2: creation mode, stored as `creation_mode`.
- Step 3: basic configuration: `name`, `description`, `language`, `channel`.

Implemented purpose options:

- UI label `Customer Support Assistant`, backend value `customer_support`.
- UI label `Employee Knowledge Assistant`, backend value `employee_knowledge`.
- UI label `Training & Certification Assistant`, backend value `training_certification`.
- UI label `Lead Generation Assistant`, backend value `lead_generation`.
- UI label `Custom Assistant`, backend value `custom`.

Implemented creation mode options:

- UI label `Start From Scratch`, backend value `scratch`.
- UI label `Use Template`, backend value `template`.
- UI label `Build With AI`, backend value `ai`.

Implemented language options from `frontend/src/app/shared/assistant-options.ts`:

- `English`, value `en`.
- `French`, value `fr`.

Implemented channel options:

- `Public Chat`, value `public_chat`.
- `Web Widget`, value `web_widget`.
- `REST Public API`, value `rest_public_api`.

The assistant is created by `ChatbotsComponent.finishWizard()` in `frontend/src/app/pages/chatbots/chatbots.component.ts`. It calls `ApiService.createChatbot()` in `frontend/src/app/services/api.ts`, which sends `POST /chatbots`.

The backend route is `create_chatbot()` in `backend/routes/chatbot_routes.py`. It validates `creation_mode/build_method` against `scratch`, `template`, `ai`, and legacy `blank`. It creates:

- a `Chatbot` row;
- a first `VersionChatbot` row with `version_number=1` and `status="draft"`;
- an `LLMConfig` row with `model="phi3"`, `temperature=0.7`, and a language-specific system prompt;
- a starter flow by calling `create_starter_flow(db, first_version.id, "blank", new_chatbot.language)`.

Important implementation detail: the backend always creates the same `blank` starter flow first, even when the selected mode is Template or AI. The selected continuation page then replaces or edits that draft.

After creation, `ChatbotsComponent.navigateAfterCreation()` redirects by mode:

- `scratch` -> `/dashboard/projects/:projectId/chatbots/:chatbotId/flow`
- `template` -> `/dashboard/projects/:projectId/chatbots/:chatbotId/templates`
- `ai` -> `/dashboard/projects/:projectId/chatbots/:chatbotId/ai-generator`

## A. Start From Scratch

### What Happens After Selection

After the user selects `Start From Scratch` and finishes the wizard, the frontend creates the assistant with `creation_mode: "scratch"` and `build_method: "scratch"`.

The backend still creates a `blank` starter flow through `create_starter_flow()`.

The Manager is redirected directly to the Flow Builder route:

`/dashboard/projects/:projectId/chatbots/:chatbotId/flow`

Frontend page/component opened:

- `FlowBuilderComponent` in `frontend/src/app/pages/flow-builder/flow-builder.component.ts`
- template: `frontend/src/app/pages/flow-builder/flow-builder.component.html`

### Initial Flow Created

The initial flow is the built-in `blank` template in `backend/services/templates.py`.

Initial flow name:

- `Blank flow`

Initial nodes:

- `start`
  - type: `message`
  - label: `Starting message`
  - config: `{ "text": "Welcome! How can I help you today?" }`
  - position: `x=80`, `y=120`
- `end`
  - type: `end`
  - label: `End`
  - config: `{ "message": "Thanks for your visit." }`
  - position: `x=340`, `y=120`

Initial transition:

- `start -> end`
  - label: `next`
  - condition: `null`

If the assistant language is French, template text can be localized by `localize_config()` in `backend/services/templates.py`.

### Immediate Flow Builder Capabilities

The Flow Builder loads its data through `FlowBuilderComponent.loadBuilder()`, which calls:

- `ApiService.getChatbotBuilder(chatbotId)`
- backend `GET /chatbots/{chatbot_id}/builder`
- route function `get_chatbot_builder()` in `backend/routes/flow_routes.py`

The Manager can immediately:

- view the draft flow canvas;
- add blocks from the left block palette;
- select a node and edit its inspector settings;
- save node label/config/position;
- drag nodes on the canvas;
- configure next-step routing;
- configure button routes;
- configure condition true/false routes;
- delete non-start nodes and connectors;
- upload/delete knowledge documents in the Flow Builder knowledge panel;
- run flow validation;
- use preview/QA panels.

The start block cannot be deleted in the UI: `FlowBuilderComponent.requestDeleteNode()` blocks deletion when `node.node_key === "start"`.

### Available Block Types

Visible block palette from `FlowBuilderComponent.blockTypes`:

- Basic: `message` (`Message`), `question` (`Question`), `buttons` (`Buttons`), `end` (`End`)
- AI: `rag_answer` (`AI Answer`), `knowledge_search` (`Knowledge Search`)
- Data Collection: `collect_name` (`Collect Name`), `collect_email` (`Collect Email`), `collect_phone` (`Collect Phone`)
- Logic: `condition` (`Condition`), `set_variable` (`Set Variable`)
- Integration: `meeting_scheduler` (`Meeting Preference`), `handoff` (`Human Handoff`)

Hidden in the Flow Builder palette but present in the code/runtime schema:

- `api_request` (`API Call`)
- `ai_router` (`AI Router`)
- `ai_classifier` (`AI Classifier`)
- `confidence_check` (`Confidence Check`)
- `lead_score` (`Lead Score`)
- `action` (`Action`)

These hidden blocks are marked `hidden: true` in the frontend block catalog. They can exist in generated/backend flows but are not selectable from the normal palette.

### Important Configurable Properties By Block Type

Common property:

- every selected node exposes `Label`.

`message`

- `Text` -> stored in `config.text`
- `Then go to` -> transition with label `next`

`question`

- `Text` writes to `config.prompt`
- `Variable name` -> `config.field`
- `Then go to`

`buttons`

- `Text` -> `config.text`
- `Variable name` -> `config.field`
- `Button labels` -> `config.buttons`
- Button path per label -> one transition per button label

`end`

- `Text` -> `config.message`
- terminal; no next-step selector

`rag_answer` / UI label `AI Answer`

- `Prompt / instructions` -> `config.prompt`
- `Use knowledge base` -> `config.use_knowledge_base`
- `Answer only from documents` -> `config.answer_only_from_documents`
- `Show sources` -> `config.show_sources`
- `Response length` -> `config.response_length`, options `short`, `medium`, `long`
- `Fallback` -> `config.fallback`
- `Continue AI/RAG at this block` -> `config.continue_rag`
- `Then go to`

`knowledge_search`

- Same inspector as `rag_answer`
- Default differs: `use_knowledge_base=true`, `answer_only_from_documents=true`, `show_sources=true`, `message="Searching knowledge."`

`collect_name`

- `Text` -> `config.prompt`
- `Variable name` -> `config.field`
- `Then go to`

`collect_email`

- `Text` -> `config.prompt`
- `Variable name` -> `config.field`
- `Validation message` -> `config.invalid_message`
- `Then go to`

`collect_phone`

- `Text` -> `config.prompt`
- `Variable name` -> `config.field`
- `Validation message` -> `config.invalid_message`
- `Then go to`

`condition`

- `Check variable` -> `config.field`
- `Rule` -> `config.operator`
- operators: `equals`, `not_equals`, `contains`, `not_contains`, `exists`, `not_exists`, `greater_than`, `greater_or_equal`, `less_than`, `less_or_equal`
- `Expected value` -> `config.value`, hidden for `exists` and `not_exists`
- true path and false path -> transitions labelled `true` and `false`

`set_variable`

- `Variable name` -> `config.field`
- `Value` -> `config.value`
- `Confirmation message` -> `config.message`
- `Then go to`

`meeting_scheduler` / UI label `Meeting Preference`

- `Prompt` -> `config.prompt`
- `Meeting variable` -> `config.field`
- `Timezone` -> `config.timezone`
- `Saved message` -> `config.success_message`
- `Then go to`
- Implementation note: UI text says this captures a preferred time and does not create calendar meetings.

`handoff` / UI label `Human Handoff`

- `Department` -> `config.department`, options `Admissions`, `Finance`, `Support`, `Technical`
- `Email variable` -> `config.email_field`
- `Phone variable` -> `config.phone_field`
- `Require email if missing` -> `config.collect_email_if_missing`
- `Require phone if missing` -> `config.collect_phone_if_missing`
- `Message` -> `config.message`
- terminal in the Flow Builder: no next-step selector

Hidden placeholder/legacy blocks have inspector support only if present in a flow:

- `api_request`: method `GET/POST`, URL, headers JSON, response variable, timeout, JSON body, success message, error message.
- `ai_router`: runtime message, instructions, output variable, routes JSON.
- `ai_classifier`: runtime message, instructions, output variable, categories JSON.
- `confidence_check`: runtime message, confidence variable, threshold.
- `lead_score`: runtime message, score variable, input variables JSON.
- `action`: terminal when `action_type` is `handoff` or `end`.

### Persistence

Database models:

- `backend/models/flow.py`
  - `Flow`: `id`, `version_id`, `name`, `created_at`
  - `FlowNode`: `flow_id`, `node_key`, `type`, `label`, `config`, `position_x`, `position_y`
  - `FlowTransition`: `flow_id`, `source_node_key`, `target_node_key`, `label`, `condition`
- `backend/models/chatbot.py`
  - `Chatbot`: includes `build_method`, `template_key`, `source_template_key`, `source_template_version`, `ai_assistant_goal`, `ai_business_context`, `ai_knowledge_base_description`

API methods:

- `ApiService.getChatbotBuilder()`
- `ApiService.createFlowNode()`
- `ApiService.updateFlowNode()`
- `ApiService.deleteFlowNode()`
- `ApiService.createFlowTransition()`
- `ApiService.updateFlowTransition()`
- `ApiService.deleteFlowTransition()`

Backend routes:

- `GET /chatbots/{chatbot_id}/builder` -> `get_chatbot_builder()`
- `POST /flows/{flow_id}/nodes` -> `create_node()`
- `PUT /flow-nodes/{node_id}` -> `update_node()`
- `DELETE /flow-nodes/{node_id}` -> `delete_node()`
- `POST /flows/{flow_id}/transitions` -> `create_transition()`
- `PUT /flow-transitions/{transition_id}` -> `update_transition()`
- `DELETE /flow-transitions/{transition_id}` -> `delete_transition()`

Position persistence:

- On drag end, `FlowBuilderComponent.onPointerUp()` calls `updateFlowNode()` with rounded `position_x` and `position_y`.
- Backend validates positions through `_ensure_canvas_position()` in `backend/routes/flow_routes.py`.
- Bounds come from `backend/services/flow_limits.py`: integer positions only, `0 <= value <= 50000`.

Node config persistence:

- Inspector edits mutate the selected node locally.
- The user clicks `Save`.
- `FlowBuilderComponent.saveNode()` calls `PUT /flow-nodes/{node_id}` with `label`, `config`, `position_x`, `position_y`.

Transition persistence:

- Normal next-step routing calls `createOrUpdateTransition(sourceKey, targetKey, "next")`.
- Button routes call it with the button label.
- Condition routes call it with normalized labels `true` or `false`.
- Backend ensures referenced nodes exist and prevents duplicate transitions with the same source, target, and output key.

Flow size limits:

- `MAX_FLOW_NODES = 200`
- `MAX_FLOW_TRANSITIONS = 400`

## B. Use Template

### What Happens After Selection

After `Use Template` is selected and the wizard is finished:

- frontend creates the assistant with `creation_mode: "template"` and `build_method: "template"`;
- `template_key` is sent as `null` from the initial wizard;
- backend creates the assistant, version, LLM config, and blank starter flow;
- frontend redirects to:

`/dashboard/projects/:projectId/chatbots/:chatbotId/templates`

Frontend page/component opened:

- `TemplateSelectionComponent` in `frontend/src/app/pages/template-selection/template-selection.component.ts`
- template: `frontend/src/app/pages/template-selection/template-selection.component.html`

### How Templates Are Loaded And Filtered

`TemplateSelectionComponent.ngOnInit()` calls `loadAssistant()`.

`loadAssistant()` calls:

- `ApiService.getChatbot(chatbotId)`
- backend `GET /chatbots/{id}`

It resolves the selected purpose using:

- URL query param `purpose`, if present;
- otherwise `chatbot.assistant_type`;
- otherwise `chatbot.purpose`;
- otherwise `custom`.

Then `loadTemplates(purpose)` calls:

- `ApiService.getFlowTemplates({ purpose, exposed_only: true })`
- backend `GET /flow-templates?purpose=<purpose>&exposed_only=true`
- route function `list_flow_templates()` in `backend/routes/flow_routes.py`

Backend filtering:

- built-in templates come from `template_options(purpose, exposed_only)` in `backend/services/templates.py`;
- templates are included only if `purpose` is in template metadata `purposes`;
- `exposed_only=true` hides templates with no metadata or `exposed=false`;
- custom DB templates from `FlowTemplate` are also appended when readable, purpose-compatible, and exposed.

### Complete Creation-Marketplace Template List

The following list is the complete built-in list exposed by the current code for assistant creation. Additional backend-only templates exist but are not exposed when `exposed_only=true`.

#### Customer Support Templates

1. `customer_support_basic`
   - Displayed name: `Customer Support Basic`
   - Purpose/category: `customer_support`
   - Functional goal: message, customer question, AI answer, loop back for another question.
   - Nodes: `start:message`, `question:question`, `answer:rag_answer`
   - Important config:
     - `start.config.text`: support welcome message
     - `question.config.field`: `support_question`
     - `question.config.silent_input`: `true`
     - `answer.config.prompt`: answer using general support knowledge and do not rely on uploaded documents
     - `answer.config.use_knowledge_base`: `false`
     - `answer.config.show_sources`: `false`
   - Transitions: `start -> question [next]`, `question -> answer [next]`, `answer -> question [next]`
   - Uses: LLM through `rag_answer`, no RAG, data collection through `question`, no handoff, no condition.

2. `customer_support_rag`
   - Displayed name: `Customer Support + RAG`
   - Purpose/category: `customer_support`
   - Functional goal: answer repeated support questions from uploaded knowledge.
   - Nodes: `start:message`, `question:question`, `answer:rag_answer`
   - Important config:
     - `question.config.field`: `support_question`
     - `question.config.silent_input`: `true`
     - `answer.config.use_knowledge_base`: `true`
     - `answer.config.show_sources`: `true`
   - Transitions: `start -> question [next]`, `question -> answer [next]`, `answer -> question [next]`
   - Uses: LLM/RAG, data collection, no handoff, no condition.

3. `customer_support_handoff`
   - Displayed name: `Customer Support + Human Handoff`
   - Purpose/category: `customer_support`
   - Functional goal: collect support request, generate AI/RAG answer, then route to human support.
   - Nodes: `start:message`, `question:question`, `answer:rag_answer`, `handoff:handoff`, `end:end`
   - Important config:
     - `question.config.field`: `support_question`
     - `answer.config.use_knowledge_base`: `true`
     - `answer.config.show_sources`: `true`
     - `handoff.config.department`: `Support`
     - `handoff.config.email_field`: `user_email`
     - `handoff.config.phone_field`: `user_phone`
     - `handoff.config.collect_email_if_missing`: `true`
   - Transitions: `start -> question [next]`, `question -> answer [next]`, `answer -> handoff [next]`, `handoff -> end [next]`
   - Uses: LLM/RAG, data collection, human handoff, no condition.

4. `customer_support_ticket_creation`
   - Displayed name: `Customer Support + Ticket Creation`
   - Purpose/category: `customer_support`
   - Functional goal: collect ticket details and mark a ticket draft ready for support handoff.
   - Nodes: `start:message`, `issue:question`, `email:collect_email`, `priority:buttons`, `ticket:set_variable`, `handoff:handoff`
   - Important config:
     - `issue.config.field`: `support_issue`
     - `email.config.field`: `user_email`
     - `priority.config.buttons`: `Low`, `Normal`, `Urgent`
     - `priority.config.field`: `ticket_priority`
     - `ticket.config.field`: `ticket_status`
     - `ticket.config.value`: `ready_to_create`
     - `handoff.config.department`: `Support`
   - Transitions: `start -> issue [next]`, `issue -> email [next]`, `email -> priority [next]`, each priority -> `ticket`, `ticket -> handoff [next]`
   - Uses: data collection, set variable, human handoff. No LLM/RAG in this template.

#### Employee Knowledge Templates

5. `hr_knowledge_bot`
   - Displayed name: `HR Knowledge Bot`
   - Purpose/category: `employee_knowledge`
   - Functional goal: answer HR policy and employee procedure questions from knowledge.
   - Nodes: `start:message`, `answer:rag_answer`
   - Important config: `answer.use_knowledge_base=true`, `show_sources=true`, `continue_rag=true`
   - Transitions: `start -> answer [next]`
   - Uses: LLM/RAG, no explicit data collection, no handoff, no condition.

6. `it_helpdesk_bot`
   - Displayed name: `IT Helpdesk Bot`
   - Purpose/category: `employee_knowledge`
   - Functional goal: categorize IT issue, collect details, answer from KB, hand off to IT.
   - Nodes: `start:message`, `category:buttons`, `details:question`, `answer:rag_answer`, `handoff:handoff`
   - Important config:
     - `category.config.buttons`: `Account access`, `Device`, `Microsoft 365`, `Security`
     - `category.config.field`: `it_category`
     - `details.config.field`: `it_issue`
     - `answer.config.use_knowledge_base`: `true`
     - `handoff.config.department`: `Technical`
   - Transitions: `start -> category [next]`, each category -> `details`, `details -> answer [next]`, `answer -> handoff [next]`
   - Uses: LLM/RAG, data collection, human handoff, button branching.

7. `company_policies_bot`
   - Displayed name: `Company Policies Bot`
   - Purpose/category: `employee_knowledge`
   - Functional goal: answer company policy questions from uploaded knowledge.
   - Nodes: `start:message`, `answer:rag_answer`
   - Important config: `answer.use_knowledge_base=true`, `show_sources=true`, `continue_rag=true`
   - Transitions: `start -> answer [next]`
   - Uses: LLM/RAG.

8. `employee_onboarding_bot`
   - Displayed name: `Employee Onboarding Bot`
   - Purpose/category: `employee_knowledge`
   - Functional goal: collect employee role, route onboarding topic, answer from internal documents.
   - Nodes: `start:message`, `role:question`, `topic:buttons`, `answer:rag_answer`, `end:end`
   - Important config:
     - `role.config.field`: `employee_role`
     - `topic.config.buttons`: `Accounts`, `Tools`, `Policies`, `Training`
     - `topic.config.field`: `onboarding_topic`
     - `answer.config.use_knowledge_base`: `true`
   - Transitions: `start -> role [next]`, `role -> topic [next]`, each topic -> `answer`, `answer -> end [next]`
   - Uses: LLM/RAG, data collection, button branching.

#### Training & Certification Templates

9. `microsoft_certification_advisor`
   - Displayed name: `Microsoft Certification Advisor`
   - Purpose/category: `training_certification`
   - Functional goal: recommend Microsoft certification paths from learner goals and level.
   - Nodes: `start:message`, `goal:buttons`, `level:buttons`, `recommendation:rag_answer`, `end:end`
   - Important config:
     - `goal.config.buttons`: `Azure`, `Microsoft 365`, `Security`, `Data & AI`
     - `level.config.buttons`: `Beginner`, `Intermediate`, `Advanced`
     - `recommendation.config.use_knowledge_base`: `true`
   - Transitions: `start -> goal [next]`, each goal -> `level`, each level -> `recommendation`, `recommendation -> end [next]`
   - Uses: LLM/RAG, data collection via buttons, branching.

10. `azure_training_assistant`
    - Displayed name: `Azure Training Assistant`
    - Purpose/category: `training_certification`
    - Functional goal: recommend Azure training path based on topic and background.
    - Nodes: `start:message`, `topic:buttons`, `background:question`, `recommendation:rag_answer`, `end:end`
    - Important config:
      - `topic.config.buttons`: `Fundamentals`, `Administration`, `Development`, `Architecture`
      - `background.config.field`: `learner_background`
      - `recommendation.config.use_knowledge_base`: `true`
    - Transitions: `start -> topic [next]`, each topic -> `background`, `background -> recommendation [next]`, `recommendation -> end [next]`
    - Uses: LLM/RAG, data collection, branching.

11. `cybersecurity_learning_assistant`
    - Displayed name: `Cybersecurity Learning Assistant`
    - Purpose/category: `training_certification`
    - Functional goal: recommend cybersecurity learning tracks and certifications.
    - Nodes: `start:message`, `track:buttons`, `level:buttons`, `recommendation:rag_answer`, `end:end`
    - Important config:
      - `track.config.buttons`: `Fundamentals`, `Cloud Security`, `SOC`, `Identity`
      - `level.config.buttons`: `Beginner`, `Intermediate`, `Advanced`
      - `recommendation.config.use_knowledge_base`: `true`
    - Transitions: `start -> track [next]`, each track -> `level`, each level -> `recommendation`, `recommendation -> end [next]`
    - Uses: LLM/RAG, data collection, branching.

12. `course_recommendation_bot`
    - Displayed name: `Course Recommendation Bot`
    - Purpose/category: `training_certification`
    - Functional goal: collect learner name and learning interest, then recommend courses.
    - Nodes: `start:message`, `name:collect_name`, `interest:question`, `recommendation:rag_answer`, `end:end`
    - Important config:
      - `name.config.field`: `user_name`
      - `interest.config.field`: `course_interest`
      - `recommendation.config.use_knowledge_base`: `true`
    - Transitions: `start -> name [next]`, `name -> interest [next]`, `interest -> recommendation [next]`, `recommendation -> end [next]`
    - Uses: LLM/RAG, data collection.

#### Lead Generation Templates

13. `simple_lead_capture`
    - Displayed name: backend `Simple Lead Capture`; frontend static catalog has same key displayed as `Contact Capture`.
    - Purpose/category: `lead_generation`
    - Functional goal: collect contact details and end.
    - Nodes: `start:message`, `name:collect_name`, `email:collect_email`, `phone:collect_phone`, `end:end`
    - Important config: fields `user_name`, `user_email`, `user_phone`
    - Transitions: linear `start -> name -> email -> phone -> end`
    - Uses: data collection only.

14. `sales_starter`
    - Displayed name: backend `Sales Starter`; frontend static catalog lists it as `Qualification Bot` under lead generation and `Sales Starter` under custom. The runtime template-selection page uses the backend name.
    - Purpose/category: `lead_generation`, `custom`
    - Functional goal: collect contact details and business need, then hand off to sales/support.
    - Nodes: `start:message`, `name:collect_name`, `email:collect_email`, `need:question`, `handoff:handoff`
    - Important config: `need.config.field=business_need`, `handoff.email_field=user_email`
    - Transitions: `start -> name -> email -> need -> handoff`
    - Uses: data collection, human handoff.

15. `consultation_booking`
    - Displayed name: `Consultation Booking`; frontend static catalog has same key displayed as `Meeting Preference`.
    - Purpose/category: `lead_generation`
    - Functional goal: collect contact details, consultation topic, meeting preference, and hand off.
    - Nodes: `start:message`, `name:collect_name`, `email:collect_email`, `topic:question`, `date:meeting_scheduler`, `handoff:handoff`
    - Important config: `topic.field=consultation_topic`, `date.field=preferred_time`, `date.timezone=local`, `handoff.email_field=user_email`
    - Transitions: `start -> name -> email -> topic -> date -> handoff`
    - Uses: data collection, meeting preference, human handoff.

16. `cloud_assessment_lead_form`
    - Displayed name: `Cloud Assessment Lead Form`
    - Purpose/category: `lead_generation`
    - Functional goal: qualify Microsoft Cloud assessment requests.
    - Nodes: `start:message`, `name:collect_name`, `email:collect_email`, `cloud_area:buttons`, `company_size:question`, `handoff:handoff`
    - Important config:
      - `cloud_area.buttons`: `Azure`, `Microsoft 365`, `Security`, `Data & AI`
      - `company_size.field`: `company_size`
      - `handoff.department`: `Technical`
    - Transitions: `start -> name -> email -> cloud_area`, each cloud area -> `company_size`, `company_size -> handoff`
    - Uses: data collection, button branching, human handoff.

17. `training_registration_bot`
    - Displayed name: `Training Registration Bot`
    - Purpose/category: `lead_generation`
    - Functional goal: collect training registration interest and route to training advisor.
    - Nodes: `start:message`, `name:collect_name`, `email:collect_email`, `course:question`, `schedule:buttons`, `handoff:handoff`
    - Important config:
      - `course.field`: `course_interest`
      - `schedule.buttons`: `Online`, `In person`, `Hybrid`
      - `schedule.field`: `training_format`
    - Transitions: `start -> name -> email -> course -> schedule`, each schedule option -> `handoff`
    - Uses: data collection, button branching, human handoff.

#### Custom Templates

18. `blank_business_bot`
    - Displayed name: `Blank Business Bot`
    - Purpose/category: `custom`
    - Functional goal: minimal message-to-end starter flow.
    - Nodes: `start:message`, `end:end`
    - Important config: welcome text and closing message
    - Transitions: `start -> end [next]`
    - Uses: no LLM, no RAG, no handoff, no condition.

19. `ai_assistant_starter`
    - Displayed name: `AI Assistant Starter`
    - Purpose/category: `custom`
    - Functional goal: start with an AI/RAG answer structure.
    - Nodes: `start:message`, `answer:rag_answer`
    - Important config: `answer.use_knowledge_base=true`, `show_sources=true`, `continue_rag=true`
    - Transitions: `start -> answer [next]`
    - Uses: LLM/RAG.

20. `faq_starter`
    - Displayed name: `FAQ Starter`
    - Purpose/category: `custom`
    - Functional goal: guided FAQ topic selection and answer.
    - Nodes: `start:message`, `topic:buttons`, `answer:rag_answer`, `end:end`
    - Important config:
      - `topic.buttons`: `Services`, `Pricing`, `Training`, `Contact`
      - `topic.field`: `faq_topic`
      - `answer.use_knowledge_base`: `true`
      - `answer.show_sources`: `true`
    - Transitions: `start -> topic [next]`, each topic -> `answer`, `answer -> end [next]`
    - Uses: LLM/RAG, data collection via buttons, branching.

21. `sales_starter`
    - Same backend template as item 14.
    - It is also exposed for `custom`.

### Backend-Only Templates Not Exposed In Creation

The following built-in templates exist in `backend/services/templates.py` but do not have `exposed=true` metadata, so they are not loaded by the creation template page with `exposed_only=true`:

`blank`, `support_faq`, `lead_qualification`, `booking`, `university_assistant`, `admissions_bot`, `internship_bot`, `customer_support_bot`, `lead_generation_bot`, `lead_capture`, `contact_collection`, `sales_qualification`, `internal_knowledge_qa`, `hr_knowledge_assistant`, `company_documentation_assistant`, `faq_basic`, `faq_rag`, `blank_starter_template`.

### Selecting And Applying A Template

The Manager selects a template card in `TemplateSelectionComponent.selectTemplate(templateKey)`.

The selected key is persisted in the URL query string:

`?template=<templateKey>`

Clicking `Replace Draft` opens a confirmation modal. The confirmation text states that applying the template will replace the current draft flow and published versions will not be modified.

`TemplateSelectionComponent.confirmApplyTemplate()` then:

1. Calls `ApiService.getChatbotBuilder(chatbotId)` to find the current draft `flow.id`.
2. Calls `ApiService.applyFlowTemplate(flowId, templateKey, selectedPurpose)`.
3. Backend handles `POST /flows/{flow_id}/template` in `apply_flow_template()`.
4. The backend validates flow size, canvas positions, transition uniqueness, and generated-flow validity.
5. The backend deletes existing `FlowTransition` rows and `FlowNode` rows for that `flow.id`.
6. It writes the template nodes/transitions into the same draft flow.
7. For assistants whose `build_method == "template"`, it updates `Chatbot.template_key`, `Chatbot.source_template_key`, `Chatbot.source_template_version`, and optionally `Chatbot.purpose`.
8. Frontend redirects to the Flow Builder:

`/dashboard/projects/:projectId/chatbots/:chatbotId/flow?template=<templateKey>&refresh=<timestamp>`

Answer to replacement question: yes, applying a template replaces the current draft flow. Existing nodes and transitions in that draft flow are deleted. Published versions are not modified by this route.

The Manager can modify the resulting flow afterward in Flow Builder because it is persisted as normal `FlowNode` and `FlowTransition` rows.

Database entities:

- Built-in templates: code dictionary `TEMPLATES` and `TEMPLATE_METADATA` in `backend/services/templates.py`
- Custom templates: `FlowTemplate` and `FlowTemplateRevision` in `backend/models/flow_template.py`
- Applied flow: `Flow`, `FlowNode`, `FlowTransition`
- Assistant provenance: `Chatbot.template_key`, `source_template_key`, `source_template_version`

## C. Build With AI

### Page/Component Opened

After selecting `Build With AI`, the Manager is redirected to:

`/dashboard/projects/:projectId/chatbots/:chatbotId/ai-generator`

Frontend page/component:

- `AiGeneratorComponent` in `frontend/src/app/pages/ai-generator/ai-generator.component.ts`
- template: `frontend/src/app/pages/ai-generator/ai-generator.component.html`

### Fields And Options Visible To The Manager

The AI generator page displays:

- Header eyebrow: `Build With AI`
- Page title: `Generate your assistant`
- A back button: `Back to assistants`
- Form card title: `Assistant brief`
- Submit button: `Generate Assistant`
- Preview card title: `Generated Output`

Input fields exactly implemented:

1. `Assistant Goal`
   - frontend model: `form.assistant_goal`
   - textarea rows: `5`
   - placeholder: `Example: Help customers troubleshoot Microsoft 365 support issues and answer common service questions.`
   - required by `canGenerate()` and backend validation

2. `Business Context`
   - frontend model: `form.business_context`
   - textarea rows: `5`
   - placeholder: `Example: INSOMEA provides Microsoft Cloud, Azure, cybersecurity and training services for enterprise customers.`
   - required by `canGenerate()` and backend validation

3. `Optional Knowledge Base Description`
   - frontend model: `form.knowledge_base_description`
   - textarea rows: `4`
   - placeholder: `Example: Product documentation, support procedures, course catalogs, policies or FAQs.`
   - optional

No frontend selectable options are implemented on the initial AI generator page. There is no field for tone, number of steps, explicit objective separate from `Assistant Goal`, assistant purpose selector, model selector, or instruction preset. Assistant type and language are read from the already-created assistant.

The request payload adds:

- `assistant_type`: from `chatbot.assistant_type || chatbot.purpose || "custom"`
- `language`: normalized from `chatbot.language || "en"`

### Generation Flow

When the Manager clicks `Generate Assistant`, `AiGeneratorComponent.generateAssistant()`:

1. Verifies `assistant_goal` and `business_context` are non-empty and not already loading.
2. Calls `ApiService.getChatbot(chatbotId)`.
3. Calls `ApiService.generateAssistantWithAi(payload)`.
4. API method posts to `POST /assistants/ai-generate`.
5. Backend route `generate_assistant_with_ai()` in `backend/routes/flow_routes.py` builds an LLM prompt asking for valid JSON.
6. On response, backend normalizes the AI output through `_normalize_ai_generation()`.
7. Frontend stores the generated response in `generated`.
8. Frontend immediately updates the assistant metadata with `ApiService.updateChatbot()`, setting:
   - `name` from `generated.assistant_name`
   - `description` from `generated.assistant_description`
   - `build_method: "ai"`
   - `creation_mode: "ai"`
   - `template_key: null`
9. Frontend calls `ApiService.getChatbotBuilder(chatbotId)` to get the draft flow id.
10. Frontend calls `ApiService.applyGeneratedFlow(flowId, { name, nodes, transitions })`.
11. Backend route `POST /flows/{flow_id}/generated` deletes existing nodes/transitions for the draft flow and inserts generated ones.
12. Frontend redirects to:

`/dashboard/projects/:projectId/chatbots/:chatbotId/flow?generated=ai`

Important behavior: the preview card exists, but there is no separate accept/apply confirmation after generation. The generated flow is applied immediately in the same `generateAssistant()` method.

### LLM Provider And Model

The AI generation endpoint uses:

- `generate_chat_completion(prompt, None, 0.2, 700)` from `backend/services/ai_provider.py`

Provider selection is environment-driven:

- `AI_PROVIDER`, default `ollama`
- if `AI_PROVIDER=ollama`, model is `OLLAMA_MODEL`, default `llama3`
- if `AI_PROVIDER=azure_openai`, model/deployment is `AZURE_OPENAI_DEPLOYMENT`

The initial assistant draft also receives an `LLMConfig` row with `model="phi3"`, but that is separate from the AI generation provider call.

### Expected AI Output

Backend prompt asks the AI to return only valid JSON with these keys:

- `assistant_name`
- `assistant_description`
- `welcome_message`
- `recommended_template`
- `rag_prompt`
- `use_knowledge_base`
- `detected_domain`
- `detected_intents`
- `recommended_flow_type`
- `suggested_variables`
- `suggested_kb_categories`
- `suggested_advanced_blocks`
- `generation_confidence`
- `generation_explanation`

The API response model is `AiGenerateResponse` in `backend/routes/flow_routes.py`. It returns:

- `assistant_name`
- `assistant_description`
- `welcome_message`
- `recommended_template`
- `detected_domain`
- `detected_intents`
- `recommended_flow_type`
- `generated_nodes`
- `generated_edges`
- `suggested_variables`
- `suggested_kb_categories`
- `suggested_advanced_blocks`
- `generation_confidence`
- `generation_explanation`
- `initial_flow_structure`

The frontend preview shows:

- generated assistant name;
- generated assistant description;
- detected domain;
- flow type;
- confidence;
- detected intents;
- suggested knowledge categories;
- suggested variables;
- suggested advanced blocks;
- generation reasoning;
- generated node labels and types.

### Parsing, Validation, And Fallback

Parsing:

- `_json_object_from_text()` first tries `json.loads(value)`.
- If that fails, it extracts the first `{ ... }` object with a regex and parses that.

Provider/JSON failure handling:

- In `generate_assistant_with_ai()`, `AIProviderError`, `json.JSONDecodeError`, `TypeError`, and `ValueError` are caught.
- On those failures, the backend uses `_fallback_ai_generation(payload)`.
- Therefore many generation failures still return a generated flow rather than surfacing an error to the frontend.

Required-field validation:

- Backend rejects empty `assistant_goal` with `400 "Assistant Goal is required"`.
- Backend rejects empty `business_context` with `400 "Business Context is required"`.

Generated-flow validation:

- Applying a generated flow uses `ensure_generated_flow_is_valid()` from `backend/services/generated_flow.py`.
- It normalizes nodes/transitions, requires exactly one canonical start node with key `start`, rejects unsupported node types, rejects duplicate node keys, and verifies transitions reference generated nodes.
- It creates a nested transaction/savepoint with temporary `VersionChatbot`, `Flow`, `FlowNode`, and `FlowTransition` rows, then calls `validate_flow_version()`.
- The savepoint is rolled back.
- If invalid, it raises `ValueError("Generated flow is invalid: ...")`.
- `POST /flows/{flow_id}/generated` returns HTTP 400 with that message.

Canvas and size validation:

- `POST /flows/{flow_id}/generated` checks node/transition counts and positions before writing.
- Limits: `MAX_FLOW_NODES=200`, `MAX_FLOW_TRANSITIONS=400`.
- Positions must be integers from `0` to `50000`.
- Duplicate transitions with the same source, target, and output key are rejected.

Frontend failure handling:

- If any request in `generateAssistant()` fails, the catch block displays `errorMessage(err)`.
- The loading state is cleared in `finally`.
- There is no regenerate-specific UI, cancel-in-progress control, or manual confirmation on the initial AI generator page.

### Which Node Types AI Can Generate

The normalization service supports these node types:

`message`, `question`, `buttons`, `end`, `rag_answer`, `knowledge_search`, `ai_router`, `ai_classifier`, `collect_name`, `collect_email`, `collect_phone`, `condition`, `confidence_check`, `lead_score`, `set_variable`, `meeting_scheduler`, `api_request`, `handoff`, `action`.

However, the actual AI generation route does not allow the LLM to directly specify arbitrary nodes. It asks the LLM for high-level JSON fields, then `_normalize_ai_generation()` builds the final flow through `_build_generated_flow()`.

Actually generated by `_build_generated_flow()` depending on heuristics:

- Always: `start:message`, `question:question`, `answer:rag_answer`
- If `needs_routing`: `router:ai_router`
- If `needs_lead`, `needs_booking`, or `needs_handoff`: `collect_name`, `collect_email`
- If `needs_lead` or `needs_booking`: `collect_phone`
- If `needs_condition`: `lead_score`, `confidence_check`
- If `needs_booking`: `meeting_scheduler`
- If `needs_rag`: `knowledge_search`
- If `needs_handoff`: `handoff`

Implemented heuristic flags in `_analyze_generation_context()`:

- `needs_rag`: knowledge description present or text mentions documents, knowledge base, policy, manual, FAQ, catalog, documentation, uploaded.
- `needs_lead`: text mentions lead, sales, prospect, qualify, capture, contact, quote, consultation.
- `needs_handoff`: text mentions handoff, human, agent, escalate, complex, support team, advisor.
- `needs_routing`: text mentions multiple, topics, route, routing, department, category, intent.
- `needs_booking`: text mentions appointment, booking, schedule, meeting, reservation, consultation.
- `needs_condition`: lead flow or text mentions if, score, eligibility, qualify, decision.
- `needs_api` and `suggests_api` are forced to `false` in current implementation.

### Position Generation

Generated positions are deterministic in `_build_generated_flow()`:

- `start`: `x=80`, `y=120`
- Subsequent main-line blocks start at `x=340`, `y=120`, then advance by `260` on each added block.
- Optional `handoff` is placed at current `x`, `y=300`.

If a submitted generated node lacks coordinates, `normalize_generated_flow()` has a fallback of `position_x = 80 + index * 260` and `position_y = 120`, but the current `_build_generated_flow()` supplies coordinates.

### Transition Generation

Generated transitions are deterministic:

- Main-line nodes are connected with `label="next"`.
- `answer -> question [next]` is always added, creating a loop for further questions.
- If handoff is generated, `answer -> handoff` is added with:
  - label: `fallback`
  - condition: `low_confidence_or_human_requested`

### Preview, Regenerate, Edit, Cancel, Apply

Initial AI generator page:

- Preview panel exists.
- Generated output is displayed after backend generation.
- No separate `Apply` button.
- No separate confirmation modal.
- No `Regenerate` button label; clicking `Generate Assistant` again is possible only while still on the page, but successful generation redirects immediately to Flow Builder.
- `Back to assistants` navigates back to the assistants list.
- Generated flow can be manually edited afterward in Flow Builder.

Assistant setup/edit mode in Flow Builder has a separate AI regeneration path:

- `FlowBuilderComponent.openAssistantSetup()`
- fields: `What should this assistant do?`, `Business context`, `Knowledge base notes`
- requires goal and context;
- opens confirmation via `requestAiDraftRegeneration()`;
- calls `generateAssistantWithAi()`, then `regenerateAssistantAiDraft()`;
- backend route: `POST /chatbots/{id}/setup/ai-draft`;
- backend creates a new draft version and new flow, preserving older/published versions.

This regeneration path exists only for assistants originally created with AI: backend checks `chatbot.build_method == "ai"`.

Initial AI apply behavior:

- `POST /flows/{flow_id}/generated` replaces the current draft flow in-place.
- Existing nodes and transitions for that draft flow are deleted.
- The Manager is redirected to Flow Builder.
- The generated flow is editable afterward.

## D. Report Structure Recommendation For Chapter 5

### Analysis

Document the user need and business problem:

- Managers need three ways to initialize a conversation flow after creating an assistant.
- Scratch supports full manual control.
- Template supports faster reuse of validated business patterns.
- AI supports natural-language initialization from a business brief.
- Good use-case grouping: `Initialiser un flux conversationnel` is appropriate for Scratch / Template / AI because all three lead to an initial draft `Flow` that the Manager can edit in the Flow Builder.

Keep implementation details out of Analysis except for high-level actors and goals.

### Conception

Document the functional design and data model:

- Actor: Manager.
- Use case: `Initialiser un flux conversationnel`.
- Sub-scenarios:
  - `Initialiser depuis zéro`
  - `Initialiser à partir d'un modèle`
  - `Initialiser avec l'IA`
- Mention that all modes produce or modify a draft flow composed of nodes and transitions.
- Include conceptual classes/entities:
  - `Chatbot`
  - `VersionChatbot`
  - `Flow`
  - `FlowNode`
  - `FlowTransition`
  - `LLMConfig`
  - `FlowTemplate`
  - `FlowTemplateRevision`
- Include activity/sequence diagrams:
  - assistant creation and redirection by creation mode;
  - template selection and draft replacement;
  - AI generation, normalization, validation, and draft replacement.

### Réalisation

Document the implemented screens, routes, services, and persistence:

- Creation wizard component and options.
- Flow Builder component, palette, inspector, node/transition CRUD.
- Template selection component, template filtering, `Replace Draft` confirmation, and backend replacement.
- AI generator component, exact fields, endpoint, provider wrapper, fallback generation, validation, and immediate apply.
- Explicitly mention implemented limitations:
  - Template and AI modes still start with a backend blank flow at creation, then replace it later.
  - AI generator has no separate apply confirmation on the initial page.
  - AI prompt does not expose tone, step count, or model selection in the UI.
  - `api_request`, `ai_router`, `ai_classifier`, `confidence_check`, `lead_score`, and `action` are hidden from the normal block palette; some can be generated or exist in backend-supported flows.
  - `needs_api` and `suggests_api` are forced to `false`, so API-call generation is not active.

### Useful Screenshots

Recommended screenshots for Chapter 5:

- Assistant creation wizard Step 1: purpose selection.
- Assistant creation wizard Step 2: the three modes.
- Assistant creation wizard Step 3: name, description, language, channel.
- Flow Builder after Start From Scratch, showing the blank `start -> end` draft.
- Flow Builder block palette and inspector for one AI/RAG block.
- Template selection page filtered for one purpose, with `Replace Draft`.
- Template replacement confirmation modal.
- Flow Builder after applying a template, showing generated blocks and branches.
- Build With AI page showing the three input fields.
- AI generated output preview card, if captured before redirect or through a delayed/debug flow.
- Flow Builder after AI generation.

### Evidence File Index

Frontend:

- `frontend/src/app/pages/chatbots/assistant-creation-wizard.component.ts`
- `frontend/src/app/pages/chatbots/assistant-creation-wizard.component.html`
- `frontend/src/app/pages/chatbots/chatbots.component.ts`
- `frontend/src/app/pages/chatbots/chatbots.component.html`
- `frontend/src/app/pages/template-selection/template-selection.component.ts`
- `frontend/src/app/pages/template-selection/template-selection.component.html`
- `frontend/src/app/pages/ai-generator/ai-generator.component.ts`
- `frontend/src/app/pages/ai-generator/ai-generator.component.html`
- `frontend/src/app/pages/flow-builder/flow-builder.component.ts`
- `frontend/src/app/pages/flow-builder/flow-builder.component.html`
- `frontend/src/app/services/api.ts`
- `frontend/src/app/shared/assistant-options.ts`
- `frontend/src/app/app.routes.ts`

Backend:

- `backend/routes/chatbot_routes.py`
- `backend/routes/flow_routes.py`
- `backend/services/templates.py`
- `backend/services/generated_flow.py`
- `backend/services/ai_provider.py`
- `backend/services/flow_limits.py`
- `backend/services/flow_validation.py`
- `backend/models/chatbot.py`
- `backend/models/chatbot_schema.py`
- `backend/models/flow.py`
- `backend/models/flow_schema.py`
- `backend/models/flow_template.py`
