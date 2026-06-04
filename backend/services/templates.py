from sqlalchemy.orm import Session

from models.flow import Flow, FlowNode, FlowTransition


TEMPLATES = {
    "blank": {
        "name": "Blank flow",
        "nodes": [
            ("start", "message", "Starting message", {"text": "Welcome! How can I help you today?"}, 80, 120)
        ],
        "transitions": []
    },
    "support_faq": {
        "name": "Customer support FAQ",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Hi! I can help answer questions from our knowledge base."}, 80, 120),
            ("ask_question", "question", "Ask for question", {"field": "user_question", "prompt": "What do you need help with?"}, 360, 120),
            ("rag_answer", "rag_answer", "Answer from knowledge", {"top_k": 3, "fallback": "I could not find this in the knowledge base."}, 660, 120),
            ("solved", "buttons", "Was this solved?", {"buttons": ["Yes", "No"], "field": "issue_solved"}, 960, 120),
            ("handoff", "handoff", "Human handoff", {"message": "A teammate will review this conversation."}, 1240, 40),
            ("end", "end", "Close conversation", {"message": "Glad I could help."}, 1240, 220)
        ],
        "transitions": [
            ("start", "ask_question", "next", None),
            ("ask_question", "rag_answer", "answer", None),
            ("rag_answer", "solved", "next", None),
            ("solved", "end", "yes", "issue_solved == Yes"),
            ("solved", "handoff", "no", "issue_solved == No")
        ]
    },
    "lead_qualification": {
        "name": "Lead qualification",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Hi! I can help you find the right solution."}, 80, 120),
            ("name", "question", "Ask name", {"field": "name", "prompt": "What is your name?"}, 340, 120),
            ("email", "question", "Ask email", {"field": "email", "prompt": "What is your work email?"}, 600, 120),
            ("budget", "question", "Ask budget", {"field": "budget", "prompt": "What is your estimated budget?"}, 860, 120),
            ("score", "condition", "Qualify lead", {"field": "budget", "operator": "greater_than", "value": "1000"}, 1120, 120),
            ("book", "action", "Book meeting", {"action": "calendar_link"}, 1380, 40),
            ("nurture", "message", "Nurture lead", {"text": "Thanks. Our team will send helpful resources."}, 1380, 220)
        ],
        "transitions": [
            ("start", "name", "next", None),
            ("name", "email", "next", None),
            ("email", "budget", "next", None),
            ("budget", "score", "next", None),
            ("score", "book", "qualified", "budget > 1000"),
            ("score", "nurture", "not qualified", "budget <= 1000")
        ]
    },
    "booking": {
        "name": "Appointment booking",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Hi! I can help you request an appointment."}, 80, 120),
            ("service", "question", "Choose service", {"field": "service", "prompt": "Which service are you interested in?"}, 360, 120),
            ("date", "question", "Preferred date", {"field": "preferred_date", "prompt": "What date works best?"}, 660, 120),
            ("contact", "question", "Contact info", {"field": "phone", "prompt": "What phone number should we use?"}, 960, 120),
            ("confirm", "message", "Confirm request", {"text": "Thanks. We received your appointment request."}, 1240, 120)
        ],
        "transitions": [
            ("start", "service", "next", None),
            ("service", "date", "next", None),
            ("date", "contact", "next", None),
            ("contact", "confirm", "next", None)
        ]
    }
}


def create_starter_flow(db: Session, version_id: int, template_key: str | None) -> Flow:
    template = TEMPLATES.get(template_key or "blank", TEMPLATES["blank"])
    flow = Flow(version_id=version_id, name=template["name"])
    db.add(flow)
    db.commit()
    db.refresh(flow)

    for node_key, node_type, label, config, x, y in template["nodes"]:
        db.add(FlowNode(
            flow_id=flow.id,
            node_key=node_key,
            type=node_type,
            label=label,
            config=config,
            position_x=x,
            position_y=y
        ))

    for source, target, label, condition in template["transitions"]:
        db.add(FlowTransition(
            flow_id=flow.id,
            source_node_key=source,
            target_node_key=target,
            label=label,
            condition=condition
        ))

    db.commit()
    db.refresh(flow)

    return flow
