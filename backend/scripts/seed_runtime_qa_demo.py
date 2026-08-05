from __future__ import annotations

from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.chatbot import Chatbot
from models.evaluation import EvaluationCase, EvaluationDataset
from models.flow import Flow, FlowNode, FlowTransition
from models.llm_config import LLMConfig
from models.project import Project
from models.user import User
from models.version import VersionChatbot


PROJECT_NAME = "Runtime QA Demo"
OWNER_EMAIL = "runtime-qa@example.local"


def first_or_create_user(db: Session) -> User:
    user = db.query(User).filter(User.email == OWNER_EMAIL).first()
    if user:
        return user
    user = User(name="Runtime QA", email=OWNER_EMAIL, password_hash="demo-only", role="manager", status="active")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def first_or_create_project(db: Session, owner: User) -> Project:
    project = db.query(Project).filter(Project.name == PROJECT_NAME, Project.user_id == owner.id).first()
    if project:
        return project
    project = Project(name=PROJECT_NAME, description="Development-only runtime QA assistants", user_id=owner.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def clear_flow(db: Session, flow: Flow) -> None:
    db.query(FlowTransition).filter(FlowTransition.flow_id == flow.id).delete()
    db.query(FlowNode).filter(FlowNode.flow_id == flow.id).delete()
    db.commit()


def add_node(db: Session, flow: Flow, key: str, node_type: str, label: str, config: dict, x: int, y: int) -> None:
    db.add(FlowNode(flow_id=flow.id, node_key=key, type=node_type, label=label, config=config, position_x=x, position_y=y))


def add_edge(db: Session, flow: Flow, source: str, target: str, label: str = "next") -> None:
    db.add(FlowTransition(flow_id=flow.id, source_node_key=source, target_node_key=target, label=label))


def upsert_assistant(db: Session, project: Project, name: str, mode: str, published: bool, blocker: bool = False) -> None:
    chatbot = db.query(Chatbot).filter(Chatbot.project_id == project.id, Chatbot.name == name).first()
    if not chatbot:
        chatbot = Chatbot(
            name=name,
            description=f"Development-only {mode} smoke fixture",
            language="en",
            purpose="runtime_qa",
            build_method="template" if mode == "template" else "ai" if "ai" in mode else "scratch",
            public_api_key=f"cp_demo_{name.lower().replace(' ', '_')}",
            public_api_enabled=published,
            project_id=project.id,
            is_active=True,
        )
        db.add(chatbot)
        db.commit()
        db.refresh(chatbot)

    version = db.query(VersionChatbot).filter(VersionChatbot.chatbot_id == chatbot.id).order_by(VersionChatbot.version_number.asc()).first()
    if not version:
        version = VersionChatbot(chatbot_id=chatbot.id, version_number=1, status="published" if published else "draft")
        db.add(version)
        db.commit()
        db.refresh(version)
    version.status = "published" if published else "draft"
    if published:
        chatbot.active_version_id = version.id

    config = db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()
    if not config:
        config = LLMConfig(version_id=version.id)
        db.add(config)
    config.model = "runtime-qa"
    config.temperature = 0.2
    config.system_prompt = "You are a runtime QA demo assistant. Keep answers short."

    flow = db.query(Flow).filter(Flow.version_id == version.id).first()
    if not flow:
        flow = Flow(version_id=version.id, name=f"{name} Flow")
        db.add(flow)
        db.commit()
        db.refresh(flow)
    clear_flow(db, flow)

    add_node(db, flow, "start", "message", "Start", {"text": "Runtime QA ready."}, 80, 120)
    if blocker:
        add_node(db, flow, "broken", "api_request", "Broken API", {"method": "POST", "url": ""}, 340, 120)
        add_edge(db, flow, "start", "broken")
    elif mode == "deterministic":
        add_node(db, flow, "ask", "question", "Question", {"prompt": "What do you need?", "field": "need"}, 340, 120)
        add_node(db, flow, "done", "end", "Done", {"message": "Captured."}, 600, 120)
        add_edge(db, flow, "start", "ask")
        add_edge(db, flow, "ask", "done")
    elif mode == "hybrid":
        add_node(db, flow, "route", "buttons", "Route", {"text": "Choose a path.", "buttons": ["AI", "Handoff"], "field": "path"}, 340, 120)
        add_node(db, flow, "answer", "rag_answer", "AI Answer", {"prompt": "Answer directly.", "fallback": "No answer.", "use_knowledge_base": False, "continue_rag": True}, 600, 60)
        add_node(db, flow, "handoff", "handoff", "Handoff", {"department": "Support", "collect_email_if_missing": True}, 600, 220)
        add_edge(db, flow, "start", "route")
        add_edge(db, flow, "route", "answer", "AI")
        add_edge(db, flow, "route", "handoff", "Handoff")
    elif mode == "rag":
        add_node(db, flow, "answer", "rag_answer", "RAG Answer", {"prompt": "Answer from knowledge.", "fallback": "No matching knowledge.", "use_knowledge_base": True, "show_sources": True, "continue_rag": True}, 340, 120)
        add_edge(db, flow, "start", "answer")
    else:
        add_node(db, flow, "answer", "rag_answer", "AI Answer", {"prompt": "Answer directly.", "fallback": "No answer.", "use_knowledge_base": False, "show_sources": False, "continue_rag": True}, 340, 120)
        add_edge(db, flow, "start", "answer")

    db.commit()


def upsert_customer_support_evaluations(db: Session, project: Project) -> None:
    chatbot = db.query(Chatbot).filter(
        Chatbot.project_id == project.id,
        Chatbot.name == "Healthy RAG assistant",
    ).first()
    if not chatbot:
        return

    dataset = db.query(EvaluationDataset).filter(
        EvaluationDataset.assistant_id == chatbot.id,
        EvaluationDataset.name == "Customer Support Release Suite",
    ).first()
    if not dataset:
        dataset = EvaluationDataset(
            assistant_id=chatbot.id,
            name="Customer Support Release Suite",
            description="Development-only customer support evaluation dataset.",
            created_by=None,
        )
        db.add(dataset)
        db.commit()
        db.refresh(dataset)

    cases = [
        {
            "name": "Return window",
            "input_message": "What is the return window?",
            "expected_keywords": ["30 days"],
            "expected_source_patterns": ["return-policy"],
            "critical": True,
            "tags": ["rag", "returns"],
        },
        {
            "name": "Delivery delay",
            "input_message": "My delivery is late. What should I do?",
            "expected_keywords": ["delivery"],
            "expected_source_patterns": ["delivery"],
            "critical": False,
            "tags": ["rag", "delivery"],
        },
        {
            "name": "Unsupported refund claim",
            "input_message": "Guarantee my refund for a damaged item.",
            "forbidden_keywords": ["guaranteed refund"],
            "critical": True,
            "tags": ["risk", "refund"],
        },
        {
            "name": "Human escalation",
            "input_message": "I want to speak to a human.",
            "expected_handoff": True,
            "expected_flow_node_ids": ["handoff"],
            "critical": True,
            "tags": ["handoff"],
        },
        {
            "name": "Unknown product",
            "input_message": "Tell me about product ZX-UNKNOWN.",
            "expected_fallback": True,
            "critical": False,
            "tags": ["fallback"],
        },
    ]
    for index, item in enumerate(cases):
        case = db.query(EvaluationCase).filter(
            EvaluationCase.dataset_id == dataset.id,
            EvaluationCase.name == item["name"],
        ).first()
        if not case:
            case = EvaluationCase(dataset_id=dataset.id, name=item["name"])
            db.add(case)
        case.order_index = index
        case.description = f"Demo evaluation case for {item['name']}."
        case.input_message = item["input_message"]
        case.expected_keywords = item.get("expected_keywords", [])
        case.forbidden_keywords = item.get("forbidden_keywords", [])
        case.expected_source_patterns = item.get("expected_source_patterns", [])
        case.expected_flow_node_ids = item.get("expected_flow_node_ids", [])
        case.expected_handoff = item.get("expected_handoff")
        case.expected_fallback = item.get("expected_fallback")
        case.critical = item["critical"]
        case.enabled = True
        case.tags = item["tags"]
    db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        owner = first_or_create_user(db)
        project = first_or_create_project(db, owner)
        fixtures = [
            ("Healthy AI-only assistant", "ai_only", True, False),
            ("Healthy RAG assistant", "rag", False, False),
            ("Healthy deterministic flow", "deterministic", True, False),
            ("Healthy hybrid flow", "hybrid", True, False),
            ("Template-created assistant", "template", True, False),
            ("Publicly deployed assistant", "ai_only", True, False),
            ("Assistant with intentional flow blocker", "deterministic", False, True),
            ("Assistant with pending knowledge", "rag", False, False),
            ("Assistant with provider failure simulation", "ai_only", False, False),
        ]
        for name, mode, published, blocker in fixtures:
            upsert_assistant(db, project, name, mode, published, blocker)
        upsert_customer_support_evaluations(db, project)
        print(f"Seeded {len(fixtures)} runtime QA demo assistants and evaluation dataset in project '{PROJECT_NAME}'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
