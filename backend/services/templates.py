from copy import deepcopy

from sqlalchemy.orm import Session

from models.flow import Flow, FlowNode, FlowTransition
from models.chatbot_schema import safe_chatbot_language


TEMPLATES = {
    "blank": {
        "name": "Blank flow",
        "nodes": [
            ("start", "message", "Starting message", {"text": "Welcome! How can I help you today?"}, 80, 120),
            ("end", "end", "End", {"message": "Thanks for your visit."}, 340, 120)
        ],
        "transitions": [
            ("start", "end", "next", None)
        ]
    },
    "support_faq": {
        "name": "Customer support FAQ",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Hi! I can help answer questions from our knowledge base. Ask me anything."}, 80, 120),
            ("rag_answer", "rag_answer", "Answer from knowledge", {"top_k": 3, "fallback": "I could not find this in the knowledge base.", "use_knowledge_base": True, "show_sources": True, "continue_rag": True}, 360, 120)
        ],
        "transitions": [
            ("start", "rag_answer", "next", None)
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
            ("nurture", "message", "Nurture lead", {"text": "Thanks. Our team will send helpful resources."}, 1380, 220),
            ("end", "end", "End", {"message": "Thanks for your interest."}, 1640, 120)
        ],
        "transitions": [
            ("start", "name", "next", None),
            ("name", "email", "next", None),
            ("email", "budget", "next", None),
            ("budget", "score", "next", None),
            ("score", "book", "true", "budget > 1000"),
            ("score", "nurture", "false", "budget <= 1000"),
            ("book", "end", "next", None),
            ("nurture", "end", "next", None)
        ]
    },
    "booking": {
        "name": "Appointment booking",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Hi! I can help you request an appointment."}, 80, 120),
            ("service", "question", "Choose service", {"field": "service", "prompt": "Which service are you interested in?"}, 360, 120),
            ("date", "question", "Preferred date", {"field": "preferred_date", "prompt": "What date works best?"}, 660, 120),
            ("contact", "question", "Contact info", {"field": "phone", "prompt": "What phone number should we use?"}, 960, 120),
            ("confirm", "end", "Confirm request", {"message": "Thanks. We received your appointment request."}, 1240, 120)
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
    },
    "customer_support_basic": {
        "name": "Customer Support Basic",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Hi. I can help answer support questions. Ask me anything."}, 80, 120),
            ("question", "question", "Customer Question", {"field": "support_question", "silent_input": True}, 340, 120),
            ("answer", "rag_answer", "AI Answer", {"prompt": "Answer clearly and helpfully using general support knowledge. Do not rely on uploaded documents.", "fallback": "I could not generate a helpful answer for that question.", "use_knowledge_base": False, "show_sources": False}, 600, 120)
        ],
        "transitions": [
            ("start", "question", "next", None),
            ("question", "answer", "next", None),
            ("answer", "question", "next", None)
        ]
    },
    "customer_support_rag": {
        "name": "Customer Support + RAG",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Hi. I can answer using your support knowledge base. Ask me anything."}, 80, 120),
            ("question", "question", "Customer Question", {"field": "support_question", "silent_input": True}, 340, 120),
            ("answer", "rag_answer", "AI/RAG Answer", {"prompt": "Use uploaded support knowledge base documents first and give practical support steps.", "fallback": "I could not confirm this from the uploaded documents.", "use_knowledge_base": True, "show_sources": True}, 600, 120)
        ],
        "transitions": [
            ("start", "question", "next", None),
            ("question", "answer", "next", None),
            ("answer", "question", "next", None)
        ]
    },
    "customer_support_handoff": {
        "name": "Customer Support + Human Handoff",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Hi. I can help or connect you to support."}, 80, 120),
            ("question", "question", "Support Request", {"prompt": "What issue are you facing?", "field": "support_question"}, 340, 120),
            ("answer", "rag_answer", "AI/RAG Answer", {"prompt": "Answer with support guidance.", "fallback": "I could not find a confirmed support answer.", "use_knowledge_base": True, "show_sources": True}, 600, 120),
            ("handoff", "handoff", "Human Handoff", {"message": "A support teammate will follow up.", "department": "Support", "email_field": "user_email", "phone_field": "user_phone", "collect_email_if_missing": True}, 860, 120),
            ("end", "end", "End", {"message": "Thanks. We will take it from here."}, 1120, 120)
        ],
        "transitions": [
            ("start", "question", "next", None),
            ("question", "answer", "next", None),
            ("answer", "handoff", "next", None),
            ("handoff", "end", "next", None)
        ]
    },
    "customer_support_ticket_creation": {
        "name": "Customer Support + Ticket Creation",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Hi. I can collect the details needed to create a support ticket."}, 80, 120),
            ("issue", "question", "Issue Details", {"prompt": "Please describe the issue you need help with.", "field": "support_issue"}, 340, 120),
            ("email", "collect_email", "Contact Email", {"prompt": "What email should support use for follow-up?", "field": "user_email"}, 600, 120),
            ("priority", "buttons", "Priority", {"text": "How urgent is this request?", "buttons": ["Low", "Normal", "Urgent"], "field": "ticket_priority"}, 860, 120),
            ("ticket", "set_variable", "Create Ticket Draft", {"field": "ticket_status", "value": "ready_to_create", "message": "I saved your ticket details."}, 1120, 120),
            ("handoff", "handoff", "Support Ticket Handoff", {"message": "Support will review your ticket request.", "department": "Support", "email_field": "user_email"}, 1380, 120)
        ],
        "transitions": [
            ("start", "issue", "next", None),
            ("issue", "email", "next", None),
            ("email", "priority", "next", None),
            ("priority", "ticket", "Low", None),
            ("priority", "ticket", "Normal", None),
            ("priority", "ticket", "Urgent", None),
            ("ticket", "handoff", "next", None)
        ]
    },
    "hr_knowledge_bot": {
        "name": "HR Knowledge Bot",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can help with HR policies, benefits, leave, and employee procedures. Ask me anything."}, 80, 120),
            ("answer", "rag_answer", "HR Knowledge Answer", {"prompt": "Answer from HR knowledge documents in a clear and professional way.", "fallback": "I could not find this HR information in the knowledge base.", "use_knowledge_base": True, "show_sources": True, "continue_rag": True}, 340, 120)
        ],
        "transitions": [
            ("start", "answer", "next", None)
        ]
    },
    "it_helpdesk_bot": {
        "name": "IT Helpdesk Bot",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can help with common IT support requests."}, 80, 120),
            ("category", "buttons", "Issue Category", {"text": "What kind of IT issue do you have?", "buttons": ["Account access", "Device", "Microsoft 365", "Security"], "field": "it_category"}, 340, 120),
            ("details", "question", "Issue Details", {"prompt": "Please describe the issue.", "field": "it_issue"}, 600, 120),
            ("answer", "rag_answer", "Helpdesk Answer", {"prompt": "Give practical IT helpdesk guidance from the knowledge base.", "fallback": "I could not find a confirmed IT helpdesk answer.", "use_knowledge_base": True, "show_sources": True}, 860, 120),
            ("handoff", "handoff", "IT Handoff", {"message": "The IT team can review this request.", "department": "Technical", "collect_email_if_missing": True, "email_field": "user_email"}, 1120, 120)
        ],
        "transitions": [
            ("start", "category", "next", None),
            ("category", "details", "Account access", None),
            ("category", "details", "Device", None),
            ("category", "details", "Microsoft 365", None),
            ("category", "details", "Security", None),
            ("details", "answer", "next", None),
            ("answer", "handoff", "next", None)
        ]
    },
    "company_policies_bot": {
        "name": "Company Policies Bot",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Ask me about company policies and internal procedures."}, 80, 120),
            ("answer", "rag_answer", "Policy Answer", {"prompt": "Answer using company policy documents. Be concise and cite sources when available.", "fallback": "I could not find that policy in the knowledge base.", "use_knowledge_base": True, "show_sources": True, "continue_rag": True}, 340, 120)
        ],
        "transitions": [
            ("start", "answer", "next", None)
        ]
    },
    "employee_onboarding_bot": {
        "name": "Employee Onboarding Bot",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Welcome. I can guide new employees through onboarding resources."}, 80, 120),
            ("role", "question", "Employee Role", {"prompt": "What is your role or department?", "field": "employee_role"}, 340, 120),
            ("topic", "buttons", "Onboarding Topic", {"text": "What do you need first?", "buttons": ["Accounts", "Tools", "Policies", "Training"], "field": "onboarding_topic"}, 600, 120),
            ("answer", "rag_answer", "Onboarding Answer", {"prompt": "Answer with practical onboarding steps from internal documents.", "fallback": "I could not find onboarding guidance for that topic.", "use_knowledge_base": True, "show_sources": True}, 860, 120),
            ("end", "end", "End", {"message": "Welcome aboard."}, 1120, 120)
        ],
        "transitions": [
            ("start", "role", "next", None),
            ("role", "topic", "next", None),
            ("topic", "answer", "Accounts", None),
            ("topic", "answer", "Tools", None),
            ("topic", "answer", "Policies", None),
            ("topic", "answer", "Training", None),
            ("answer", "end", "next", None)
        ]
    },
    "microsoft_certification_advisor": {
        "name": "Microsoft Certification Advisor",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can recommend Microsoft certification paths based on your goals."}, 80, 120),
            ("goal", "buttons", "Career Goal", {"text": "Which area are you focused on?", "buttons": ["Azure", "Microsoft 365", "Security", "Data & AI"], "field": "certification_goal"}, 340, 120),
            ("level", "buttons", "Experience Level", {"text": "What is your current level?", "buttons": ["Beginner", "Intermediate", "Advanced"], "field": "experience_level"}, 600, 120),
            ("recommendation", "rag_answer", "Certification Recommendation", {"prompt": "Recommend relevant Microsoft certifications and learning steps.", "fallback": "I could not find a matching certification recommendation.", "use_knowledge_base": True, "show_sources": True}, 860, 120),
            ("end", "end", "End", {"message": "Good luck with your certification path."}, 1120, 120)
        ],
        "transitions": [
            ("start", "goal", "next", None),
            ("goal", "level", "Azure", None),
            ("goal", "level", "Microsoft 365", None),
            ("goal", "level", "Security", None),
            ("goal", "level", "Data & AI", None),
            ("level", "recommendation", "Beginner", None),
            ("level", "recommendation", "Intermediate", None),
            ("level", "recommendation", "Advanced", None),
            ("recommendation", "end", "next", None)
        ]
    },
    "azure_training_assistant": {
        "name": "Azure Training Assistant",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can help you choose an Azure training path."}, 80, 120),
            ("topic", "buttons", "Azure Topic", {"text": "Which Azure topic interests you?", "buttons": ["Fundamentals", "Administration", "Development", "Architecture"], "field": "azure_topic"}, 340, 120),
            ("background", "question", "Background", {"prompt": "Tell me briefly about your current background.", "field": "learner_background"}, 600, 120),
            ("recommendation", "rag_answer", "Training Recommendation", {"prompt": "Recommend Azure training based on the selected topic and learner background.", "fallback": "I could not find a matching Azure training recommendation.", "use_knowledge_base": True, "show_sources": True}, 860, 120),
            ("end", "end", "End", {"message": "You can continue with Knowledge Base resources or contact training advisors."}, 1120, 120)
        ],
        "transitions": [
            ("start", "topic", "next", None),
            ("topic", "background", "Fundamentals", None),
            ("topic", "background", "Administration", None),
            ("topic", "background", "Development", None),
            ("topic", "background", "Architecture", None),
            ("background", "recommendation", "next", None),
            ("recommendation", "end", "next", None)
        ]
    },
    "cybersecurity_learning_assistant": {
        "name": "Cybersecurity Learning Assistant",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can recommend cybersecurity learning paths."}, 80, 120),
            ("track", "buttons", "Security Track", {"text": "Which security area do you want to learn?", "buttons": ["Fundamentals", "Cloud Security", "SOC", "Identity"], "field": "security_track"}, 340, 120),
            ("level", "buttons", "Experience Level", {"text": "What is your current level?", "buttons": ["Beginner", "Intermediate", "Advanced"], "field": "security_level"}, 600, 120),
            ("recommendation", "rag_answer", "Learning Recommendation", {"prompt": "Recommend cybersecurity courses, labs, and certifications.", "fallback": "I could not find a matching cybersecurity recommendation.", "use_knowledge_base": True, "show_sources": True}, 860, 120),
            ("end", "end", "End", {"message": "Keep practicing with labs and real scenarios."}, 1120, 120)
        ],
        "transitions": [
            ("start", "track", "next", None),
            ("track", "level", "Fundamentals", None),
            ("track", "level", "Cloud Security", None),
            ("track", "level", "SOC", None),
            ("track", "level", "Identity", None),
            ("level", "recommendation", "Beginner", None),
            ("level", "recommendation", "Intermediate", None),
            ("level", "recommendation", "Advanced", None),
            ("recommendation", "end", "next", None)
        ]
    },
    "course_recommendation_bot": {
        "name": "Course Recommendation Bot",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can recommend courses based on your needs."}, 80, 120),
            ("name", "collect_name", "Learner Name", {"prompt": "What is your name?", "field": "user_name"}, 340, 120),
            ("interest", "question", "Learning Interest", {"prompt": "What topic do you want to learn?", "field": "course_interest"}, 600, 120),
            ("recommendation", "rag_answer", "Course Recommendation", {"prompt": "Recommend relevant courses and next steps.", "fallback": "I could not find a matching course recommendation.", "use_knowledge_base": True, "show_sources": True}, 860, 120),
            ("end", "end", "End", {"message": "A training advisor can help finalize your learning plan."}, 1120, 120)
        ],
        "transitions": [
            ("start", "name", "next", None),
            ("name", "interest", "next", None),
            ("interest", "recommendation", "next", None),
            ("recommendation", "end", "next", None)
        ]
    },
    "lead_capture": {
        "name": "Lead Capture",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Hi. I can collect your contact details for our team."}, 80, 120),
            ("name", "collect_name", "Collect Name", {"prompt": "What is your name?", "field": "user_name"}, 340, 120),
            ("email", "collect_email", "Collect Email", {"prompt": "What is your email?", "field": "user_email"}, 600, 120),
            ("phone", "collect_phone", "Collect Phone", {"prompt": "What phone number can we use?", "field": "user_phone"}, 860, 120),
            ("end", "end", "End", {"message": "Thanks. Our team will contact you soon."}, 1120, 120)
        ],
        "transitions": [
            ("start", "name", "next", None),
            ("name", "email", "next", None),
            ("email", "phone", "next", None),
            ("phone", "end", "next", None)
        ]
    },
    "contact_collection": {
        "name": "Contact Collection",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Please share your contact information."}, 80, 120),
            ("name", "collect_name", "Name", {"prompt": "What is your full name?", "field": "user_name"}, 340, 120),
            ("email", "collect_email", "Email", {"prompt": "What email should we use?", "field": "user_email"}, 600, 120),
            ("phone", "collect_phone", "Phone", {"prompt": "What phone number should we use?", "field": "user_phone"}, 860, 120),
            ("end", "end", "End", {"message": "Your contact information was received."}, 1120, 120)
        ],
        "transitions": [
            ("start", "name", "next", None),
            ("name", "email", "next", None),
            ("email", "phone", "next", None),
            ("phone", "end", "next", None)
        ]
    },
    "sales_qualification": {
        "name": "Sales Qualification",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can help understand your needs and route you to sales."}, 80, 120),
            ("name", "collect_name", "Name", {"prompt": "What is your name?", "field": "user_name"}, 340, 120),
            ("email", "collect_email", "Email", {"prompt": "What is your work email?", "field": "user_email"}, 600, 120),
            ("need", "question", "Need", {"prompt": "What are you looking for?", "field": "customer_need"}, 860, 120),
            ("handoff", "handoff", "Sales Handoff", {"message": "A sales specialist will follow up.", "department": "Support", "email_field": "user_email"}, 1120, 120)
        ],
        "transitions": [
            ("start", "name", "next", None),
            ("name", "email", "next", None),
            ("email", "need", "next", None),
            ("need", "handoff", "next", None)
        ]
    },
    "simple_lead_capture": {
        "name": "Simple Lead Capture",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Hi. I can collect your details so our team can contact you."}, 80, 120),
            ("name", "collect_name", "Name", {"prompt": "What is your name?", "field": "user_name"}, 340, 120),
            ("email", "collect_email", "Email", {"prompt": "What is your email?", "field": "user_email"}, 600, 120),
            ("phone", "collect_phone", "Phone", {"prompt": "What phone number can we use?", "field": "user_phone"}, 860, 120),
            ("end", "end", "End", {"message": "Thanks. Our team will contact you soon."}, 1120, 120)
        ],
        "transitions": [
            ("start", "name", "next", None),
            ("name", "email", "next", None),
            ("email", "phone", "next", None),
            ("phone", "end", "next", None)
        ]
    },
    "consultation_booking": {
        "name": "Consultation Booking",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can help you request a consultation."}, 80, 120),
            ("name", "collect_name", "Name", {"prompt": "What is your name?", "field": "user_name"}, 340, 120),
            ("email", "collect_email", "Email", {"prompt": "What email should we use?", "field": "user_email"}, 600, 120),
            ("topic", "question", "Consultation Topic", {"prompt": "What would you like to discuss?", "field": "consultation_topic"}, 860, 120),
            ("date", "question", "Preferred Date", {"prompt": "What date or time works best for you?", "field": "preferred_time"}, 1120, 120),
            ("handoff", "handoff", "Consultation Handoff", {"message": "A consultant will follow up with you.", "department": "Support", "email_field": "user_email"}, 1380, 120)
        ],
        "transitions": [
            ("start", "name", "next", None),
            ("name", "email", "next", None),
            ("email", "topic", "next", None),
            ("topic", "date", "next", None),
            ("date", "handoff", "next", None)
        ]
    },
    "cloud_assessment_lead_form": {
        "name": "Cloud Assessment Lead Form",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can help qualify your Microsoft Cloud assessment request."}, 80, 120),
            ("name", "collect_name", "Name", {"prompt": "What is your name?", "field": "user_name"}, 340, 120),
            ("email", "collect_email", "Email", {"prompt": "What is your work email?", "field": "user_email"}, 600, 120),
            ("cloud_area", "buttons", "Cloud Area", {"text": "Which area do you want to assess?", "buttons": ["Azure", "Microsoft 365", "Security", "Data & AI"], "field": "cloud_area"}, 860, 120),
            ("company_size", "question", "Company Size", {"prompt": "How many employees or users are in your organization?", "field": "company_size"}, 1120, 120),
            ("handoff", "handoff", "Cloud Assessment Handoff", {"message": "A cloud consultant will review your request.", "department": "Technical", "email_field": "user_email"}, 1380, 120)
        ],
        "transitions": [
            ("start", "name", "next", None),
            ("name", "email", "next", None),
            ("email", "cloud_area", "next", None),
            ("cloud_area", "company_size", "Azure", None),
            ("cloud_area", "company_size", "Microsoft 365", None),
            ("cloud_area", "company_size", "Security", None),
            ("cloud_area", "company_size", "Data & AI", None),
            ("company_size", "handoff", "next", None)
        ]
    },
    "training_registration_bot": {
        "name": "Training Registration Bot",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can collect your training registration request."}, 80, 120),
            ("name", "collect_name", "Name", {"prompt": "What is your name?", "field": "user_name"}, 340, 120),
            ("email", "collect_email", "Email", {"prompt": "What email should we use for registration?", "field": "user_email"}, 600, 120),
            ("course", "question", "Course Interest", {"prompt": "Which course or certification are you interested in?", "field": "course_interest"}, 860, 120),
            ("schedule", "buttons", "Preferred Format", {"text": "Which format do you prefer?", "buttons": ["Online", "In person", "Hybrid"], "field": "training_format"}, 1120, 120),
            ("handoff", "handoff", "Training Handoff", {"message": "A training advisor will contact you.", "department": "Support", "email_field": "user_email"}, 1380, 120)
        ],
        "transitions": [
            ("start", "name", "next", None),
            ("name", "email", "next", None),
            ("email", "course", "next", None),
            ("course", "schedule", "next", None),
            ("schedule", "handoff", "Online", None),
            ("schedule", "handoff", "In person", None),
            ("schedule", "handoff", "Hybrid", None)
        ]
    },
    "internal_knowledge_qa": {
        "name": "Internal Knowledge Q&A",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Ask a company knowledge question."}, 80, 120),
            ("answer", "rag_answer", "AI/RAG Answer", {"prompt": "Answer using internal knowledge.", "fallback": "I could not find this in company knowledge.", "use_knowledge_base": True, "show_sources": True, "continue_rag": True}, 340, 120)
        ],
        "transitions": [
            ("start", "answer", "next", None)
        ]
    },
    "hr_knowledge_assistant": {
        "name": "HR Knowledge Assistant",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can help with HR policy questions. Ask me anything."}, 80, 120),
            ("answer", "rag_answer", "HR Answer", {"prompt": "Answer based on HR documents.", "fallback": "I could not find that HR detail.", "use_knowledge_base": True, "show_sources": True, "continue_rag": True}, 340, 120)
        ],
        "transitions": [
            ("start", "answer", "next", None)
        ]
    },
    "company_documentation_assistant": {
        "name": "Company Documentation Assistant",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Ask about company documentation."}, 80, 120),
            ("answer", "rag_answer", "Documentation Answer", {"prompt": "Answer from company documentation.", "fallback": "I could not find this in the documentation.", "use_knowledge_base": True, "show_sources": True, "continue_rag": True}, 340, 120)
        ],
        "transitions": [
            ("start", "answer", "next", None)
        ]
    },
    "faq_basic": {
        "name": "FAQ Basic",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can answer common questions."}, 80, 120),
            ("question", "question", "FAQ Question", {"prompt": "What question do you have?", "field": "faq_question"}, 340, 120),
            ("choices", "buttons", "FAQ Options", {"text": "Choose another action.", "buttons": ["Ask another question", "End"], "field": "faq_choice"}, 600, 120),
            ("end", "end", "End", {"message": "Thanks for visiting."}, 860, 120)
        ],
        "transitions": [
            ("start", "question", "next", None),
            ("question", "choices", "next", None),
            ("choices", "question", "Ask another question", None),
            ("choices", "end", "End", None)
        ]
    },
    "faq_rag": {
        "name": "FAQ + RAG",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can answer FAQs using uploaded knowledge. Ask me anything."}, 80, 120),
            ("answer", "rag_answer", "FAQ Answer", {"prompt": "Answer the FAQ clearly using the knowledge base.", "fallback": "I could not find a confirmed FAQ answer.", "use_knowledge_base": True, "show_sources": True, "continue_rag": True}, 340, 120)
        ],
        "transitions": [
            ("start", "answer", "next", None)
        ]
    },
    "blank_starter_template": {
        "name": "Blank Starter Template",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Welcome! How can I help you today?"}, 80, 120),
            ("end", "end", "End", {"message": "Thanks for your visit."}, 340, 120)
        ],
        "transitions": [
            ("start", "end", "next", None)
        ]
    },
    "blank_business_bot": {
        "name": "Blank Business Bot",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Welcome. How can I help you today?"}, 80, 120),
            ("end", "end", "End", {"message": "Thanks for your visit."}, 340, 120)
        ],
        "transitions": [
            ("start", "end", "next", None)
        ]
    },
    "ai_assistant_starter": {
        "name": "AI Assistant Starter",
        "nodes": [
            ("start", "message", "Welcome", {"text": "Ask me a question and I will do my best to help."}, 80, 120),
            ("answer", "rag_answer", "AI/RAG Answer", {"prompt": "Answer professionally and use knowledge base sources when available.", "fallback": "I do not have enough information to answer that yet.", "use_knowledge_base": True, "show_sources": True, "continue_rag": True}, 340, 120)
        ],
        "transitions": [
            ("start", "answer", "next", None)
        ]
    },
    "faq_starter": {
        "name": "FAQ Starter",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can help with common questions."}, 80, 120),
            ("topic", "buttons", "FAQ Topic", {"text": "Choose a topic.", "buttons": ["Services", "Pricing", "Training", "Contact"], "field": "faq_topic"}, 340, 120),
            ("answer", "rag_answer", "FAQ Answer", {"prompt": "Answer the selected FAQ topic clearly.", "fallback": "I could not find a confirmed FAQ answer.", "use_knowledge_base": True, "show_sources": True}, 600, 120),
            ("end", "end", "End", {"message": "Thanks for visiting."}, 860, 120)
        ],
        "transitions": [
            ("start", "topic", "next", None),
            ("topic", "answer", "Services", None),
            ("topic", "answer", "Pricing", None),
            ("topic", "answer", "Training", None),
            ("topic", "answer", "Contact", None),
            ("answer", "end", "next", None)
        ]
    },
    "sales_starter": {
        "name": "Sales Starter",
        "nodes": [
            ("start", "message", "Welcome", {"text": "I can help understand your business needs."}, 80, 120),
            ("name", "collect_name", "Name", {"prompt": "What is your name?", "field": "user_name"}, 340, 120),
            ("email", "collect_email", "Email", {"prompt": "What is your work email?", "field": "user_email"}, 600, 120),
            ("need", "question", "Business Need", {"prompt": "What business challenge can we help with?", "field": "business_need"}, 860, 120),
            ("handoff", "handoff", "Sales Handoff", {"message": "A specialist will contact you.", "department": "Support", "email_field": "user_email"}, 1120, 120)
        ],
        "transitions": [
            ("start", "name", "next", None),
            ("name", "email", "next", None),
            ("email", "need", "next", None),
            ("need", "handoff", "next", None)
        ]
    }
}


def template_options() -> list[dict]:
    return [{"key": key, "name": value["name"]} for key, value in TEMPLATES.items()]


FRENCH_TEMPLATE_TEXT = {
    "Welcome! How can I help you today?": "Bonjour ! Comment puis-je vous aider aujourd'hui ?",
    "Welcome. How can I help you today?": "Bonjour. Comment puis-je vous aider aujourd'hui ?",
    "Hi! I can help answer questions from our knowledge base. Ask me anything.": "Bonjour ! Je peux repondre aux questions a partir de notre base de connaissances. Posez-moi votre question.",
    "I could not find this in the knowledge base.": "Je n'ai pas trouve cette information dans la base de connaissances.",
    "Hi! I can help you find the right solution.": "Bonjour ! Je peux vous aider a trouver la bonne solution.",
    "What is your name?": "Quel est votre nom ?",
    "What is your work email?": "Quel est votre email professionnel ?",
    "What is your estimated budget?": "Quel est votre budget estime ?",
    "Thanks. Our team will send helpful resources.": "Merci. Notre equipe vous enverra des ressources utiles.",
    "Hi! I can help you request an appointment.": "Bonjour ! Je peux vous aider a demander un rendez-vous.",
    "Which service are you interested in?": "Quel service vous interesse ?",
    "What date works best?": "Quelle date vous convient le mieux ?",
    "What phone number should we use?": "Quel numero de telephone devons-nous utiliser ?",
    "Thanks. We received your appointment request.": "Merci. Nous avons bien recu votre demande de rendez-vous.",
    "Welcome. I can help with admissions questions.": "Bonjour. Je peux vous aider avec les questions d'admission.",
    "What is your full name?": "Quel est votre nom complet ?",
    "What email should admissions use?": "Quel email le service des admissions doit-il utiliser ?",
    "Which program are you interested in?": "Quel programme vous interesse ?",
    "Answer admissions questions clearly.": "Repondez clairement aux questions d'admission.",
    "I could not find that admissions detail in the uploaded documents.": "Je n'ai pas trouve ce detail d'admission dans les documents televerses.",
    "Admissions will follow up with you.": "Le service des admissions vous recontactera.",
    "I can help with internship eligibility and next steps.": "Je peux vous aider avec l'eligibilite aux stages et les prochaines etapes.",
    "What is your student email?": "Quel est votre email etudiant ?",
    "What is your field of study?": "Quel est votre domaine d'etudes ?",
    "Use the internship documents and be practical.": "Utilisez les documents de stage et donnez une reponse pratique.",
    "I could not confirm that from the internship documents.": "Je n'ai pas pu confirmer cela avec les documents de stage.",
    "Good luck with your internship search.": "Bonne chance dans votre recherche de stage.",
    "Hi. I can help troubleshoot or connect you to support.": "Bonjour. Je peux vous aider a resoudre un probleme ou vous mettre en relation avec le support.",
    "What issue are you facing?": "Quel probleme rencontrez-vous ?",
    "Give concise support steps.": "Donnez des etapes de support concises.",
    "I could not find a confirmed support answer.": "Je n'ai pas trouve de reponse de support confirmee.",
    "Did this solve the issue?": "Cela a-t-il resolu le probleme ?",
    "Support will follow up.": "Le support vous recontactera.",
    "Glad I could help.": "Ravi d'avoir pu vous aider.",
    "Hi. I can help route your request to the right team.": "Bonjour. Je peux orienter votre demande vers la bonne equipe.",
    "What is your email?": "Quel est votre email ?",
    "What phone number can we use?": "Quel numero de telephone pouvons-nous utiliser ?",
    "Thanks. I saved your request.": "Merci. J'ai enregistre votre demande.",
    "A specialist will contact you.": "Un specialiste vous contactera.",
    "Hi. I can help answer support questions. Ask me anything.": "Bonjour. Je peux repondre aux questions de support. Posez-moi votre question.",
    "Answer clearly and helpfully using general support knowledge. Do not rely on uploaded documents.": "Repondez clairement et utilement avec les connaissances generales de support. Ne vous appuyez pas sur des documents televerses.",
    "I could not generate a helpful answer for that question.": "Je n'ai pas pu generer de reponse utile a cette question.",
    "Hi. I can answer using your support knowledge base. Ask me anything.": "Bonjour. Je peux repondre a partir de votre base de connaissances de support. Posez-moi votre question.",
    "Use uploaded support knowledge base documents first and give practical support steps.": "Utilisez d'abord les documents de support televerses et donnez des etapes pratiques.",
    "I could not confirm this from the uploaded documents.": "Je n'ai pas pu confirmer cela avec les documents televerses.",
    "Hi. I can help or connect you to support.": "Bonjour. Je peux vous aider ou vous connecter au support.",
    "Answer with support guidance.": "Repondez avec des conseils de support.",
    "A support teammate will follow up.": "Un membre de l'equipe support vous recontactera.",
    "Thanks. We will take it from here.": "Merci. Nous allons prendre le relais.",
    "Hi. I can collect the details needed to create a support ticket.": "Bonjour. Je peux collecter les details necessaires pour creer un ticket de support.",
    "Please describe the issue you need help with.": "Veuillez decrire le probleme pour lequel vous avez besoin d'aide.",
    "What email should support use for follow-up?": "Quel email le support doit-il utiliser pour le suivi ?",
    "How urgent is this request?": "Quel est le niveau d'urgence de cette demande ?",
    "I saved your ticket details.": "J'ai enregistre les details de votre ticket.",
    "Support will review your ticket request.": "Le support examinera votre demande de ticket.",
    "I can help with HR policies, benefits, leave, and employee procedures. Ask me anything.": "Je peux vous aider avec les politiques RH, les avantages, les conges et les procedures employes. Posez-moi votre question.",
    "Answer from HR knowledge documents in a clear and professional way.": "Repondez a partir des documents RH de facon claire et professionnelle.",
    "I could not find this HR information in the knowledge base.": "Je n'ai pas trouve cette information RH dans la base de connaissances.",
    "I can help with common IT support requests.": "Je peux vous aider avec les demandes courantes de support IT.",
    "What kind of IT issue do you have?": "Quel type de probleme IT rencontrez-vous ?",
    "Please describe the issue.": "Veuillez decrire le probleme.",
    "Give practical IT helpdesk guidance from the knowledge base.": "Donnez des conseils pratiques de support IT a partir de la base de connaissances.",
    "I could not find a confirmed IT helpdesk answer.": "Je n'ai pas trouve de reponse IT confirmee.",
    "The IT team can review this request.": "L'equipe IT peut examiner cette demande.",
    "Ask me about company policies and internal procedures.": "Posez-moi vos questions sur les politiques de l'entreprise et les procedures internes.",
    "Answer using company policy documents. Be concise and cite sources when available.": "Repondez avec les documents de politique de l'entreprise. Soyez concis et citez les sources si elles sont disponibles.",
    "I could not find that policy in the knowledge base.": "Je n'ai pas trouve cette politique dans la base de connaissances.",
    "Welcome. I can guide new employees through onboarding resources.": "Bonjour. Je peux guider les nouveaux employes dans les ressources d'integration.",
    "What is your role or department?": "Quel est votre role ou departement ?",
    "What do you need first?": "De quoi avez-vous besoin en premier ?",
    "Answer with practical onboarding steps from internal documents.": "Repondez avec des etapes d'integration pratiques a partir des documents internes.",
    "I could not find onboarding guidance for that topic.": "Je n'ai pas trouve de conseils d'integration pour ce sujet.",
    "Welcome aboard.": "Bienvenue dans l'equipe.",
    "Ask me a question and I will do my best to help.": "Posez-moi une question et je ferai de mon mieux pour vous aider.",
    "Answer professionally and use knowledge base sources when available.": "Repondez professionnellement et utilisez les sources de la base de connaissances lorsqu'elles sont disponibles.",
    "I do not have enough information to answer that yet.": "Je n'ai pas encore assez d'informations pour repondre.",
    "Ask me anything.": "Posez-moi votre question.",
    "Retrieve relevant knowledge base context for the user's question.": "Recuperez le contexte pertinent de la base de connaissances pour la question de l'utilisateur.",
    "I could not find enough relevant knowledge.": "Je n'ai pas trouve assez d'informations pertinentes.",
    "Searching knowledge.": "Recherche dans les connaissances.",
    "Searching knowledge and preparing an answer.": "Recherche dans les connaissances et preparation d'une reponse.",
    "Preparing an answer.": "Preparation d'une reponse.",
}


def localize_text(value: str, language: str | None) -> str:
    if safe_chatbot_language(language) != "fr":
        return value
    return FRENCH_TEMPLATE_TEXT.get(value, value)


def localize_config(config: dict, node_type: str, language: str | None) -> dict:
    localized = deepcopy(config)
    if safe_chatbot_language(language) != "fr":
        return localized

    for key in (
        "text",
        "prompt",
        "fallback",
        "message",
        "invalid_message",
        "invalid_email_message",
        "invalid_phone_message",
        "collect_email_prompt",
        "collect_phone_prompt",
        "error_message",
        "success_message",
    ):
        if isinstance(localized.get(key), str):
            localized[key] = localize_text(localized[key], language)

    if node_type in {"rag_answer", "knowledge_search", "ai_router", "ai_classifier"}:
        instruction = "Repondez toujours en francais."
        current_prompt = str(localized.get("prompt") or localized.get("instructions") or "").strip()
        if current_prompt and instruction not in current_prompt:
            localized["prompt"] = f"{instruction} {current_prompt}"
        elif not current_prompt:
            localized["prompt"] = instruction

    return localized


def localized_template_nodes(template: dict, language: str | None) -> list[tuple]:
    return [
        (key, node_type, label, localize_config(config, node_type, language), x, y)
        for key, node_type, label, config, x, y in template["nodes"]
    ]


def template_generated_payload(template_key: str, language: str | None = None) -> tuple[list[dict], list[dict]]:
    template = TEMPLATES.get(template_key)
    if not template:
        raise ValueError("Unknown flow template")

    nodes = [
        {
            "key": key,
            "type": node_type,
            "label": label,
            "config": config,
            "position_x": x,
            "position_y": y,
        }
        for key, node_type, label, config, x, y in localized_template_nodes(template, language)
    ]
    transitions = [
        {
            "source_node_key": source,
            "target_node_key": target,
            "label": label,
            "condition": condition,
        }
        for source, target, label, condition in template.get("transitions", [])
    ]
    return nodes, transitions


def replace_flow_with_template(db: Session, flow: Flow, template_key: str, language: str | None = None) -> Flow:
    template = TEMPLATES.get(template_key)
    if not template:
        raise ValueError("Unknown flow template")

    db.query(FlowTransition).filter(FlowTransition.flow_id == flow.id).delete()
    db.query(FlowNode).filter(FlowNode.flow_id == flow.id).delete()
    flow.name = template["name"]
    db.flush()

    for node_key, node_type, label, config, x, y in localized_template_nodes(template, language):
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


def create_starter_flow(db: Session, version_id: int, template_key: str | None, language: str | None = None) -> Flow:
    template = TEMPLATES.get(template_key or "blank", TEMPLATES["blank"])
    flow = Flow(version_id=version_id, name=template["name"])
    db.add(flow)
    db.commit()
    db.refresh(flow)

    for node_key, node_type, label, config, x, y in localized_template_nodes(template, language):
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
