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
    },
    "university_assistant": {
        "name": "University Assistant",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Bonjour. Je suis l'assistant officiel de l'universite. Comment puis-je vous aider ?"}, 80, 120),
            ("topic", "buttons", "Choose topic", {"text": "Choisissez un sujet.", "buttons": ["Admissions", "Finance", "Internships", "Support"], "field": "subject"}, 360, 120),
            ("rag", "rag_answer", "Answer from documents", {"prompt": "Answer professionally in French.", "fallback": "Je n'ai pas trouve cette information dans les documents.", "use_knowledge_base": True, "show_sources": True, "continue_rag": True}, 660, 120),
            ("handoff", "handoff", "Human handoff", {"message": "Un conseiller va examiner votre demande.", "department": "Admissions", "email_field": "user_email", "phone_field": "user_phone", "collect_email_if_missing": True}, 960, 40),
            ("end", "end", "End", {"message": "Merci pour votre visite."}, 960, 220)
        ],
        "transitions": [
            ("start", "topic", "next", None),
            ("topic", "rag", "Admissions", None),
            ("topic", "rag", "Finance", None),
            ("topic", "rag", "Internships", None),
            ("topic", "handoff", "Support", None),
            ("rag", "end", "next", None)
        ]
    },
    "admissions_bot": {
        "name": "Admissions Bot",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Welcome. I can help with admissions questions."}, 80, 120),
            ("name", "collect_name", "Collect Name", {"prompt": "What is your full name?", "field": "user_name"}, 340, 120),
            ("email", "collect_email", "Collect Email", {"prompt": "What email should admissions use?", "field": "user_email"}, 600, 120),
            ("program", "question", "Program Interest", {"prompt": "Which program are you interested in?", "field": "program_interest"}, 860, 120),
            ("rag", "rag_answer", "Admissions Answer", {"prompt": "Answer admissions questions clearly.", "fallback": "I could not find that admissions detail in the uploaded documents.", "use_knowledge_base": True, "show_sources": True}, 1120, 120),
            ("handoff", "handoff", "Admissions Follow-up", {"message": "Admissions will follow up with you.", "department": "Admissions", "email_field": "user_email"}, 1380, 120)
        ],
        "transitions": [
            ("start", "name", "next", None),
            ("name", "email", "next", None),
            ("email", "program", "next", None),
            ("program", "rag", "next", None),
            ("rag", "handoff", "next", None)
        ]
    },
    "internship_bot": {
        "name": "Internship Bot",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can help with internship eligibility and next steps."}, 80, 120),
            ("email", "collect_email", "Student Email", {"prompt": "What is your student email?", "field": "user_email"}, 340, 120),
            ("field", "question", "Study Field", {"prompt": "What is your field of study?", "field": "study_field"}, 600, 120),
            ("rag", "rag_answer", "Internship Answer", {"prompt": "Use the internship documents and be practical.", "fallback": "I could not confirm that from the internship documents.", "use_knowledge_base": True, "show_sources": True}, 860, 120),
            ("end", "end", "Close", {"message": "Good luck with your internship search."}, 1120, 120)
        ],
        "transitions": [
            ("start", "email", "next", None),
            ("email", "field", "next", None),
            ("field", "rag", "next", None),
            ("rag", "end", "next", None)
        ]
    },
    "customer_support_bot": {
        "name": "Customer Support Bot",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Hi. I can help troubleshoot or connect you to support."}, 80, 120),
            ("issue", "question", "Issue", {"prompt": "What issue are you facing?", "field": "support_issue"}, 340, 120),
            ("rag", "rag_answer", "Support Answer", {"prompt": "Give concise support steps.", "fallback": "I could not find a confirmed support answer.", "use_knowledge_base": True, "show_sources": True}, 600, 120),
            ("solved", "buttons", "Solved?", {"text": "Did this solve the issue?", "buttons": ["Helpful", "Not Helpful"], "field": "support_feedback"}, 860, 120),
            ("handoff", "handoff", "Support Handoff", {"message": "Support will follow up.", "department": "Support", "email_field": "user_email", "phone_field": "user_phone", "collect_email_if_missing": True}, 1120, 40),
            ("end", "end", "Close", {"message": "Glad I could help."}, 1120, 220)
        ],
        "transitions": [
            ("start", "issue", "next", None),
            ("issue", "rag", "next", None),
            ("rag", "solved", "next", None),
            ("solved", "end", "Helpful", None),
            ("solved", "handoff", "Not Helpful", None)
        ]
    },
    "lead_generation_bot": {
        "name": "Lead Generation Bot",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Hi. I can help route your request to the right team."}, 80, 120),
            ("name", "collect_name", "Name", {"prompt": "What is your name?", "field": "user_name"}, 340, 120),
            ("email", "collect_email", "Email", {"prompt": "What is your email?", "field": "user_email"}, 600, 120),
            ("phone", "collect_phone", "Phone", {"prompt": "What phone number can we use?", "field": "user_phone"}, 860, 120),
            ("department", "set_variable", "Set Department", {"field": "department", "value": "Sales", "message": "Thanks. I saved your request."}, 1120, 120),
            ("handoff", "handoff", "Sales Handoff", {"message": "A specialist will contact you.", "department": "Support", "email_field": "user_email", "phone_field": "user_phone"}, 1380, 120)
        ],
        "transitions": [
            ("start", "name", "next", None),
            ("name", "email", "next", None),
            ("email", "phone", "next", None),
            ("phone", "department", "next", None),
            ("department", "handoff", "next", None)
        ]
    }
}


def template_options() -> list[dict]:
    return [{"key": key, "name": value["name"]} for key, value in TEMPLATES.items()]


def replace_flow_with_template(db: Session, flow: Flow, template_key: str) -> Flow:
    template = TEMPLATES.get(template_key)
    if not template:
        raise ValueError("Unknown flow template")

    db.query(FlowTransition).filter(FlowTransition.flow_id == flow.id).delete()
    db.query(FlowNode).filter(FlowNode.flow_id == flow.id).delete()
    flow.name = template["name"]
    db.flush()

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
