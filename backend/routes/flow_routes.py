import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.flow import Flow, FlowNode, FlowTransition
from models.chatbot import Chatbot
from models.flow_schema import BuilderContextResponse, FlowNodeCreate, FlowNodeResponse, FlowNodeUpdate, FlowResponse, FlowTransitionCreate, FlowTransitionResponse, FlowTransitionUpdate
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from services.auth import require_roles
from services.ai_provider import AIProviderError, generate_chat_completion
from services.flow_validation import validate_flow_version
from services.templates import create_starter_flow, replace_flow_with_template, template_options
import uuid

router = APIRouter()


class FlowTemplateApply(BaseModel):
    template_key: str


class AiGenerateRequest(BaseModel):
    assistant_goal: str
    business_context: str
    knowledge_base_description: str | None = None
    assistant_type: str | None = None


class AiGeneratedNode(BaseModel):
    key: str
    type: str
    label: str
    config: dict
    position_x: int
    position_y: int


class AiGeneratedTransition(BaseModel):
    source_node_key: str
    target_node_key: str
    label: str | None = None
    condition: str | None = None


class AiGenerateResponse(BaseModel):
    assistant_name: str
    assistant_description: str
    welcome_message: str
    recommended_template: str
    detected_domain: str
    detected_intents: list[str]
    recommended_flow_type: str
    generated_nodes: list[dict]
    generated_edges: list[dict]
    suggested_variables: list[str]
    suggested_kb_categories: list[str]
    suggested_advanced_blocks: list[str]
    generation_confidence: float
    generation_explanation: str
    initial_flow_structure: dict


class GeneratedFlowApply(BaseModel):
    name: str | None = None
    nodes: list[AiGeneratedNode]
    transitions: list[AiGeneratedTransition]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_chatbot_access(db: Session, chatbot_id: int, current_user: User) -> Chatbot:
    query = db.query(Chatbot).filter(Chatbot.id == chatbot_id)
    if current_user.role == "manager":
        query = query.join(Project, Chatbot.project_id == Project.id).filter(Project.user_id == current_user.id)

    chatbot = query.first()
    if not chatbot:
        raise HTTPException(status_code=404, detail="Chatbot not found")
    return chatbot


def ensure_version_access(db: Session, version_id: int, current_user: User) -> VersionChatbot:
    version = db.query(VersionChatbot).filter(VersionChatbot.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    ensure_chatbot_access(db, version.chatbot_id, current_user)
    return version


def ensure_flow_access(db: Session, flow_id: int, current_user: User) -> Flow:
    flow = db.query(Flow).filter(Flow.id == flow_id).first()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    ensure_version_access(db, flow.version_id, current_user)
    return flow


def ensure_node_access(db: Session, node_id: int, current_user: User) -> FlowNode:
    node = db.query(FlowNode).filter(FlowNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    ensure_flow_access(db, node.flow_id, current_user)
    return node


def ensure_transition_access(db: Session, transition_id: int, current_user: User) -> FlowTransition:
    transition = db.query(FlowTransition).filter(FlowTransition.id == transition_id).first()
    if not transition:
        raise HTTPException(status_code=404, detail="Transition not found")
    ensure_flow_access(db, transition.flow_id, current_user)
    return transition


def _compact(value: str | None, fallback: str = "") -> str:
    return " ".join((value or fallback).strip().split())


def _json_object_from_text(value: str) -> dict:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _string_list(value) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[,;\n]", value)
    elif isinstance(value, list):
        items = value
    else:
        items = []
    clean = [_compact(str(item)) for item in items if _compact(str(item))]
    return clean or ["general assistance"]


def _has_any(text: str, terms: set[str]) -> bool:
    for term in terms:
        clean = term.strip().lower()
        if not clean:
            continue
        if " " in clean or "-" in clean:
            if clean in text:
                return True
            continue
        if re.search(rf"\b{re.escape(clean)}\b", text):
            return True
    return False


def _analyze_generation_context(goal: str, context: str, knowledge: str) -> dict:
    text = f"{goal} {context} {knowledge}".lower()
    domain_terms = {
        "education": {"education", "school", "university", "student", "course", "training", "certification", "learning"},
        "healthcare": {"health", "clinic", "patient", "doctor", "medical", "appointment", "care"},
        "banking": {"bank", "loan", "credit", "account", "payment", "finance", "insurance"},
        "e-commerce": {"shop", "store", "order", "product", "cart", "delivery", "refund", "ecommerce", "e-commerce"},
        "HR": {"employee", "hr", "policy", "onboarding", "leave", "benefits", "internal"},
        "IT helpdesk": {"it", "helpdesk", "technical", "device", "password", "microsoft", "cloud", "azure", "security"},
        "sales": {"lead", "sales", "prospect", "quote", "consultation", "qualify", "customer"},
        "legal": {"legal", "contract", "law", "compliance", "case"},
        "real estate": {"real estate", "property", "rent", "buyer", "listing"},
        "tourism": {"tourism", "travel", "hotel", "booking", "trip", "tour"},
    }
    detected_domain = "custom business"
    for domain, terms in domain_terms.items():
        if _has_any(text, terms):
            detected_domain = domain
            break

    needs_rag = bool(knowledge) or _has_any(text, {"document", "knowledge base", "policy", "manual", "faq", "catalog", "documentation", "uploaded"})
    needs_lead = _has_any(text, {"lead", "sales", "prospect", "qualify", "capture", "contact", "quote", "consultation"})
    needs_handoff = _has_any(text, {"handoff", "human", "agent", "escalate", "complex", "support team", "advisor"})
    needs_routing = _has_any(text, {"multiple", "topics", "route", "routing", "department", "category", "intent"})
    needs_booking = _has_any(text, {"appointment", "booking", "schedule", "meeting", "reservation", "consultation"})
    needs_api = _has_any(text, {"api", "webhook", "external", "ticket", "crm", "create request", "system"})
    needs_condition = needs_lead or _has_any(text, {"if", "score", "eligibility", "qualify", "decision"})

    intents = ["answer questions"]
    if needs_routing:
        intents.append("route users by intent")
    if needs_lead:
        intents.append("capture and qualify leads")
    if needs_booking:
        intents.append("schedule meetings")
    if needs_handoff:
        intents.append("escalate to a human")
    if needs_api:
        intents.append("trigger external actions")

    variables = ["user_question"]
    if needs_lead or needs_handoff or needs_booking:
        variables.extend(["user_name", "user_email"])
    if needs_lead or needs_booking:
        variables.append("user_phone")
    if needs_routing:
        variables.append("detected_intent")
    if needs_condition:
        variables.append("lead_score")
    if needs_booking:
        variables.append("preferred_time")

    blocks = []
    if needs_routing:
        blocks.extend(["AI Router", "AI Classifier"])
    if needs_rag:
        blocks.append("Knowledge Search")
    if needs_condition:
        blocks.extend(["Confidence Check", "Lead Score"])
    if needs_booking:
        blocks.append("Meeting Scheduler")
    if needs_api:
        blocks.append("API Call")
    if needs_handoff:
        blocks.append("Human Handoff")

    flow_type = "simple_ai_chat"
    if needs_lead:
        flow_type = "lead_qualification"
    elif needs_booking:
        flow_type = "booking_assistant"
    elif needs_routing:
        flow_type = "intent_routing_assistant"
    elif needs_rag:
        flow_type = "knowledge_assistant"

    confidence = 0.62
    confidence += 0.1 if detected_domain != "custom business" else 0
    confidence += 0.08 if needs_rag else 0
    confidence += 0.05 if len(intents) > 1 else 0

    return {
        "domain_label": detected_domain,
        "domain_title": detected_domain.title().replace("-", " "),
        "detected_domain": detected_domain,
        "detected_intents": intents,
        "recommended_flow_type": flow_type,
        "needs_rag": needs_rag,
        "needs_lead": needs_lead,
        "needs_handoff": needs_handoff,
        "needs_routing": needs_routing,
        "needs_booking": needs_booking,
        "needs_api": needs_api,
        "needs_condition": needs_condition,
        "suggested_variables": list(dict.fromkeys(variables)),
        "suggested_kb_categories": [
            f"{detected_domain} FAQs",
            "Policies and procedures",
            "Product or service documentation",
            "Escalation guidelines",
        ] if needs_rag else [],
        "suggested_advanced_blocks": list(dict.fromkeys(blocks)),
        "generation_confidence": min(confidence, 0.92),
        "generation_explanation": (
            f"Generated a {flow_type.replace('_', ' ')} because the goal/context indicate "
            f"{', '.join(intents)} for the {detected_domain} domain."
        ),
        "use_knowledge_base": needs_rag,
    }


def _node(key: str, node_type: str, label: str, config: dict, x: int, y: int) -> dict:
    return {
        "key": key,
        "type": node_type,
        "label": label,
        "config": config,
        "position_x": x,
        "position_y": y,
    }


def _edge(source: str, target: str, label: str = "next", condition: str | None = None) -> dict:
    return {
        "source_node_key": source,
        "target_node_key": target,
        "label": label,
        "condition": condition,
    }


def _build_generated_flow(welcome_message: str, rag_prompt: str, analysis: dict) -> tuple[list[dict], list[dict]]:
    needs_rag = bool(analysis.get("needs_rag"))
    nodes = [_node("start", "message", "Welcome", {"text": welcome_message}, 80, 120)]
    edges = []
    previous = "start"
    x = 340

    def add(key: str, node_type: str, label: str, config: dict):
        nonlocal previous, x
        nodes.append(_node(key, node_type, label, config, x, 120))
        edges.append(_edge(previous, key))
        previous = key
        x += 260

    if analysis.get("needs_routing"):
        add("router", "ai_router", "AI Router", {
            "instructions": "Classify the user's intent and route the conversation to the best next step.",
            "output_variable": "detected_intent",
            "routes": analysis.get("detected_intents", []),
            "message": "Let me route your request."
        })

    if analysis.get("needs_lead") or analysis.get("needs_booking") or analysis.get("needs_handoff"):
        add("collect_name", "collect_name", "Collect Name", {"prompt": "What is your name?", "field": "user_name"})
        add("collect_email", "collect_email", "Collect Email", {"prompt": "What email should we use?", "field": "user_email"})

    if analysis.get("needs_lead") or analysis.get("needs_booking"):
        add("collect_phone", "collect_phone", "Collect Phone", {"prompt": "What phone number can we use?", "field": "user_phone"})

    if analysis.get("needs_condition"):
        add("lead_score", "lead_score", "Lead Score", {
            "input_variables": ["user_question", "user_email"],
            "score_variable": "lead_score",
            "message": "I am qualifying this request."
        })
        add("confidence", "confidence_check", "Confidence Check", {
            "threshold": 0.65,
            "variable": "lead_score",
            "message": "Checking confidence."
        })

    if analysis.get("needs_booking"):
        add("scheduler", "meeting_scheduler", "Meeting Scheduler", {
            "field": "preferred_time",
            "message": "Share your preferred meeting time.",
            "timezone": "local"
        })

    if analysis.get("needs_api"):
        add("api", "api_request", "API Call", {
            "method": "POST",
            "url": "",
            "headers": {},
            "body": {},
            "response_field": "api_response",
            "success_message": "The request was sent.",
            "error_message": "The request could not be sent."
        })

    add("question", "question", "User Question", {
        "prompt": "Ask me anything.",
        "field": "user_question",
        "silent": True,
        "hide_prompt": True
    })

    if needs_rag:
        add("knowledge_search", "knowledge_search", "Knowledge Search", {
            "prompt": "Retrieve relevant knowledge base context for the user's question.",
            "fallback": "I could not find enough relevant knowledge.",
            "use_knowledge_base": True,
            "show_sources": True,
            "continue_rag": False,
            "retrieval_only": True,
            "message": "Searching knowledge."
        })

    add("answer", "rag_answer", "AI Answer", {
        "prompt": rag_prompt,
        "fallback": "I do not have enough information to answer that yet.",
        "use_knowledge_base": needs_rag,
        "show_sources": needs_rag,
        "continue_rag": False,
        "message": "Searching knowledge and preparing an answer." if needs_rag else "Preparing an answer."
    })

    edges.append(_edge("answer", "question"))

    if analysis.get("needs_handoff"):
        nodes.append(_node("handoff", "handoff", "Human Handoff", {
            "message": "A teammate will review this request and follow up.",
            "department": "Support",
            "email_field": "user_email",
            "phone_field": "user_phone",
            "collect_email_if_missing": True
        }, x, 300))
        edges.append(_edge("answer", "handoff", "fallback", "low_confidence_or_human_requested"))

    return nodes, edges


def _fallback_ai_generation(payload: AiGenerateRequest) -> dict:
    goal = _compact(payload.assistant_goal, "Help users get accurate answers")
    context = _compact(payload.business_context, "the organization")
    knowledge = _compact(payload.knowledge_base_description)
    analysis = _analyze_generation_context(goal, context, knowledge)
    assistant_name = f"{analysis['domain_title']} Assistant"

    return {
        "assistant_name": assistant_name,
        "assistant_description": f"Assistant designed to {goal.lower()} for {context}.",
        "welcome_message": f"Hi. I can help with {analysis['domain_label']} questions and requests. How can I help?",
        "recommended_template": analysis["recommended_flow_type"],
        "rag_prompt": (
            f"Use the available knowledge base to answer questions about {context}. "
            f"Assistant goal: {goal}. Be clear, professional, and practical."
        ) if analysis["needs_rag"] else (
            f"Answer questions for {context}. Assistant goal: {goal}. "
            "Be clear, professional, and practical."
        ),
        "use_knowledge_base": analysis["needs_rag"],
        **analysis,
    }


def _normalize_ai_generation(raw: dict, payload: AiGenerateRequest) -> AiGenerateResponse:
    fallback = _fallback_ai_generation(payload)
    assistant_name = _compact(raw.get("assistant_name"), fallback["assistant_name"])[:120]
    assistant_description = _compact(raw.get("assistant_description"), fallback["assistant_description"])[:500]
    welcome_message = _compact(raw.get("welcome_message"), fallback["welcome_message"])[:300]
    recommended_template = _compact(raw.get("recommended_template"), fallback["recommended_template"])[:80]
    rag_prompt = _compact(raw.get("rag_prompt"), fallback["rag_prompt"])[:700]
    analysis = {**fallback, **raw}
    use_knowledge_base = bool(analysis.get("use_knowledge_base", fallback["use_knowledge_base"]))
    analysis["needs_rag"] = use_knowledge_base
    nodes, transitions = _build_generated_flow(welcome_message, rag_prompt, analysis)
    detected_domain = _string_list(analysis.get("detected_domain") or analysis.get("domain_label") or fallback["domain_label"])[0]
    detected_intents = _string_list(analysis.get("detected_intents") or fallback["detected_intents"])
    suggested_variables = _string_list(analysis.get("suggested_variables") or fallback["suggested_variables"])
    suggested_kb_categories = _string_list(analysis.get("suggested_kb_categories") or fallback["suggested_kb_categories"])
    suggested_advanced_blocks = _string_list(analysis.get("suggested_advanced_blocks") or fallback["suggested_advanced_blocks"])
    generation_confidence = max(0.1, min(float(analysis.get("generation_confidence") or fallback["generation_confidence"]), 0.98))
    explanation = _compact(analysis.get("generation_explanation"), fallback["generation_explanation"])[:800]

    return AiGenerateResponse(
        assistant_name=assistant_name,
        assistant_description=assistant_description,
        welcome_message=welcome_message,
        recommended_template=recommended_template,
        detected_domain=detected_domain,
        detected_intents=detected_intents,
        recommended_flow_type=_compact(analysis.get("recommended_flow_type"), fallback["recommended_flow_type"])[:80],
        generated_nodes=nodes,
        generated_edges=transitions,
        suggested_variables=suggested_variables,
        suggested_kb_categories=suggested_kb_categories,
        suggested_advanced_blocks=suggested_advanced_blocks,
        generation_confidence=generation_confidence,
        generation_explanation=explanation,
        initial_flow_structure={
            "nodes": nodes,
            "transitions": transitions,
        },
    )


@router.post("/assistants/ai-generate", response_model=AiGenerateResponse)
def generate_assistant_with_ai(
    payload: AiGenerateRequest,
    current_user=Depends(require_roles("admin", "manager"))
):
    goal = _compact(payload.assistant_goal)
    context = _compact(payload.business_context)
    knowledge = _compact(payload.knowledge_base_description)
    if not goal:
        raise HTTPException(status_code=400, detail="Assistant Goal is required")
    if not context:
        raise HTTPException(status_code=400, detail="Business Context is required")

    prompt = f"""
Generate a chatbot assistant plan for an enterprise manager.

Return only valid JSON with these keys:
- assistant_name
- assistant_description
- welcome_message
- recommended_template
- rag_prompt
- use_knowledge_base
- detected_domain
- detected_intents
- recommended_flow_type
- suggested_variables
- suggested_kb_categories
- suggested_advanced_blocks
- generation_confidence
- generation_explanation

Rules:
- assistant_name must be concise.
- assistant_description must explain the assistant's business purpose.
- welcome_message must be generated from the provided goal and business context.
- recommended_template must be a short snake_case label.
- rag_prompt must be instructions for the AI or AI/RAG answer node based on the context.
- use_knowledge_base must be true only when uploaded documents are useful.
- Do not assume any company, industry, or use case that is not provided.
- Infer whether routing, lead capture, handoff, booking, API actions, or conditions are useful.

Assistant goal:
{goal}

Business context:
{context}

Optional knowledge base description:
{knowledge or "None"}

Assistant type:
{payload.assistant_type or "custom"}
"""

    try:
        content = generate_chat_completion(prompt, None, 0.2, 700)
        generated = _json_object_from_text(content)
    except (AIProviderError, json.JSONDecodeError, TypeError, ValueError):
        generated = _fallback_ai_generation(payload)

    return _normalize_ai_generation(generated, payload)


@router.get("/versions/{version_id}/flow", response_model=FlowResponse)
def get_flow(
    version_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    ensure_version_access(db, version_id, current_user)

    flow = db.query(Flow).filter(Flow.version_id == version_id).first()
    if not flow:
        flow = create_starter_flow(db, version_id, "blank")

    return flow


@router.get("/versions/{version_id}/flow/validate")
def validate_flow(
    version_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    ensure_version_access(db, version_id, current_user)

    result = validate_flow_version(db, version_id)
    return result


@router.get("/flow-templates")
def list_flow_templates(
    current_user=Depends(require_roles("admin", "manager"))
):
    return template_options()


@router.post("/flows/{flow_id}/template", response_model=FlowResponse)
def apply_flow_template(
    flow_id: int,
    payload: FlowTemplateApply,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    flow = ensure_flow_access(db, flow_id, current_user)

    try:
        return replace_flow_with_template(db, flow, payload.template_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/flows/{flow_id}/generated", response_model=FlowResponse)
def apply_generated_flow(
    flow_id: int,
    payload: GeneratedFlowApply,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    flow = ensure_flow_access(db, flow_id, current_user)

    node_keys = {node.key for node in payload.nodes}
    if "start" not in node_keys:
        raise HTTPException(status_code=400, detail="Generated flow must include a start node")

    for transition in payload.transitions:
        if transition.source_node_key not in node_keys or transition.target_node_key not in node_keys:
            raise HTTPException(status_code=400, detail="Generated transitions must reference generated nodes")

    db.query(FlowTransition).filter(FlowTransition.flow_id == flow.id).delete()
    db.query(FlowNode).filter(FlowNode.flow_id == flow.id).delete()
    flow.name = payload.name or "AI Generated Assistant"
    db.flush()

    for node in payload.nodes:
        db.add(FlowNode(
            flow_id=flow.id,
            node_key=node.key,
            type=node.type,
            label=node.label,
            config=node.config or {},
            position_x=node.position_x,
            position_y=node.position_y,
        ))

    for transition in payload.transitions:
        db.add(FlowTransition(
            flow_id=flow.id,
            source_node_key=transition.source_node_key,
            target_node_key=transition.target_node_key,
            label=transition.label,
            condition=transition.condition,
        ))

    db.commit()
    db.refresh(flow)
    return flow


@router.get("/chatbots/{chatbot_id}/builder", response_model=BuilderContextResponse)
def get_chatbot_builder(
    chatbot_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    chatbot = ensure_chatbot_access(db, chatbot_id, current_user)

    version = db.query(VersionChatbot).filter(
        VersionChatbot.chatbot_id == chatbot_id,
        VersionChatbot.status == "draft"
    ).order_by(VersionChatbot.version_number.desc()).first()

    if not version:
        version = db.query(VersionChatbot).filter(
            VersionChatbot.chatbot_id == chatbot_id
        ).order_by(VersionChatbot.version_number.desc()).first()

    if not version:
        raise HTTPException(status_code=404, detail="No version found for chatbot")

    flow = db.query(Flow).filter(Flow.version_id == version.id).first()
    if not flow:
        flow = create_starter_flow(db, version.id, "blank")

    return {
        "chatbot": {
            "id": chatbot.id,
            "name": chatbot.name,
            "description": chatbot.description,
            "purpose": chatbot.purpose,
            "mode": chatbot.mode,
            "channel": chatbot.channel
        },
        "version": {
            "id": version.id,
            "version_number": version.version_number,
            "status": version.status
        },
        "flow": flow
    }


@router.post("/flows/{flow_id}/nodes", response_model=FlowNodeResponse)
def create_node(
    flow_id: int,
    payload: FlowNodeCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    flow = ensure_flow_access(db, flow_id, current_user)

    node = FlowNode(
        flow_id=flow_id,
        node_key=f"{payload.type}_{uuid.uuid4().hex[:8]}",
        type=payload.type,
        label=payload.label,
        config=payload.config or {},
        position_x=payload.position_x,
        position_y=payload.position_y
    )

    db.add(node)
    db.commit()
    db.refresh(node)

    return node


@router.put("/flow-nodes/{node_id}", response_model=FlowNodeResponse)
def update_node(
    node_id: int,
    payload: FlowNodeUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    node = ensure_node_access(db, node_id, current_user)

    if payload.label is not None:
        node.label = payload.label
    if payload.config is not None:
        node.config = payload.config
    if payload.position_x is not None:
        node.position_x = payload.position_x
    if payload.position_y is not None:
        node.position_y = payload.position_y

    db.commit()
    db.refresh(node)

    return node


@router.delete("/flow-nodes/{node_id}")
def delete_node(
    node_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    node = ensure_node_access(db, node_id, current_user)

    db.query(FlowTransition).filter(
        FlowTransition.flow_id == node.flow_id,
        (
            (FlowTransition.source_node_key == node.node_key)
            | (FlowTransition.target_node_key == node.node_key)
        )
    ).delete(synchronize_session=False)
    db.delete(node)
    db.commit()

    return {"message": "Node deleted"}


@router.post("/flows/{flow_id}/transitions", response_model=FlowTransitionResponse)
def create_transition(
    flow_id: int,
    payload: FlowTransitionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    flow = ensure_flow_access(db, flow_id, current_user)

    source = db.query(FlowNode).filter(
        FlowNode.flow_id == flow_id,
        FlowNode.node_key == payload.source_node_key
    ).first()
    target = db.query(FlowNode).filter(
        FlowNode.flow_id == flow_id,
        FlowNode.node_key == payload.target_node_key
    ).first()
    if not source or not target:
        raise HTTPException(status_code=400, detail="Source and target nodes must exist")

    transition = FlowTransition(
        flow_id=flow_id,
        source_node_key=payload.source_node_key,
        target_node_key=payload.target_node_key,
        label=payload.label,
        condition=payload.condition
    )
    db.add(transition)
    db.commit()
    db.refresh(transition)

    return transition


@router.put("/flow-transitions/{transition_id}", response_model=FlowTransitionResponse)
def update_transition(
    transition_id: int,
    payload: FlowTransitionUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    transition = ensure_transition_access(db, transition_id, current_user)

    if payload.source_node_key is not None:
        transition.source_node_key = payload.source_node_key
    if payload.target_node_key is not None:
        transition.target_node_key = payload.target_node_key
    if payload.label is not None:
        transition.label = payload.label
    if payload.condition is not None:
        transition.condition = payload.condition

    db.commit()
    db.refresh(transition)

    return transition


@router.delete("/flow-transitions/{transition_id}")
def delete_transition(
    transition_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    transition = ensure_transition_access(db, transition_id, current_user)

    db.delete(transition)
    db.commit()

    return {"message": "Transition deleted"}
