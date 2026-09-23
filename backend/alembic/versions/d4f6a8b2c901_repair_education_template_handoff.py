"""repair education template handoff

Revision ID: d4f6a8b2c901
Revises: cf3a1b2d4e68
Create Date: 2026-09-21 00:00:00.000000

"""
from typing import Union

import json
import sqlalchemy as sa
from alembic import op


revision: str = "d4f6a8b2c901"
down_revision: Union[str, None] = "cf3a1b2d4e68"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


EDUCATION_TEMPLATE_NODES = [
    {
        "key": "start",
        "type": "message",
        "label": "Welcome",
        "config": {
            "text": "Bonjour. Je peux vous aider avec les questions de formation, de cours et de certification. Comment puis-je vous aider ?"
        },
        "position_x": 80,
        "position_y": 120,
    },
    {
        "key": "collect_name",
        "type": "collect_name",
        "label": "Collect Name",
        "config": {"prompt": "Quel est votre nom ?", "field": "user_name"},
        "position_x": 340,
        "position_y": 120,
    },
    {
        "key": "collect_email",
        "type": "collect_email",
        "label": "Collect Email",
        "config": {"prompt": "Quel email devons-nous utiliser ?", "field": "user_email"},
        "position_x": 600,
        "position_y": 120,
    },
    {
        "key": "question",
        "type": "question",
        "label": "Learner Question",
        "config": {
            "prompt": "Posez-moi votre question sur les cours, les parcours de formation ou les certifications.",
            "field": "education_question",
            "silent": True,
            "hide_prompt": True,
        },
        "position_x": 860,
        "position_y": 120,
    },
    {
        "key": "knowledge_search",
        "type": "knowledge_search",
        "label": "Knowledge Search",
        "config": {
            "prompt": "Recuperez le contexte pertinent de la base de connaissances pour la question de formation de l'utilisateur.",
            "fallback": "Je n'ai pas trouve assez d'informations pertinentes.",
            "use_knowledge_base": True,
            "show_sources": True,
            "continue_rag": False,
            "retrieval_only": True,
            "message": "Recherche dans les connaissances de formation.",
        },
        "position_x": 1120,
        "position_y": 120,
    },
    {
        "key": "answer",
        "type": "rag_answer",
        "label": "Education Answer",
        "config": {
            "prompt": "Repondez toujours en francais. Aidez l'utilisateur avec les cours, la formation, les certifications, les prerequis et les prochaines etapes. Utilisez la base de connaissances disponible en priorite. Donnez une reponse claire, professionnelle et pratique.",
            "fallback": "Je n'ai pas encore assez d'informations pour repondre.",
            "use_knowledge_base": True,
            "show_sources": True,
            "continue_rag": False,
            "message": "Recherche dans les connaissances et preparation d'une reponse.",
        },
        "position_x": 1380,
        "position_y": 120,
    },
    {
        "key": "needs_follow_up",
        "type": "buttons",
        "label": "Follow-up Needed",
        "config": {
            "text": "Souhaitez-vous poser une autre question ou recevoir les prochaines etapes par email ?",
            "buttons": ["Autre question", "Recevoir les prochaines etapes"],
            "field": "education_next_step",
        },
        "position_x": 1640,
        "position_y": 120,
    },
    {
        "key": "follow_up_note",
        "type": "set_variable",
        "label": "Save Follow-up Request",
        "config": {
            "field": "education_follow_up_requested",
            "value": "true",
            "message": "Votre demande de suivi formation a ete enregistree.",
        },
        "position_x": 1900,
        "position_y": 220,
    },
    {
        "key": "end",
        "type": "end",
        "label": "Close",
        "config": {
            "message": "Merci. Un conseiller formation pourra utiliser vos coordonnees si un suivi est necessaire."
        },
        "position_x": 2160,
        "position_y": 220,
    },
]

EDUCATION_TEMPLATE_TRANSITIONS = [
    {"source_node_key": "start", "target_node_key": "collect_name", "label": "next", "condition": None},
    {"source_node_key": "collect_name", "target_node_key": "collect_email", "label": "next", "condition": None},
    {"source_node_key": "collect_email", "target_node_key": "question", "label": "next", "condition": None},
    {"source_node_key": "question", "target_node_key": "knowledge_search", "label": "next", "condition": None},
    {"source_node_key": "knowledge_search", "target_node_key": "answer", "label": "next", "condition": None},
    {"source_node_key": "answer", "target_node_key": "needs_follow_up", "label": "next", "condition": None},
    {"source_node_key": "answer", "target_node_key": "follow_up_note", "label": "fallback", "condition": "low_confidence_or_human_requested"},
    {"source_node_key": "needs_follow_up", "target_node_key": "question", "label": "Autre question", "condition": None},
    {"source_node_key": "needs_follow_up", "target_node_key": "follow_up_note", "label": "Recevoir les prochaines etapes", "condition": None},
    {"source_node_key": "follow_up_note", "target_node_key": "end", "label": "next", "condition": None},
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        nodes_value = sa.text("CAST(:nodes AS JSON)")
        transitions_value = sa.text("CAST(:transitions AS JSON)")
        stale_handoff_guard = "nodes::text ILIKE :handoff_pattern"
    else:
        nodes_value = sa.text(":nodes")
        transitions_value = sa.text(":transitions")
        stale_handoff_guard = "nodes LIKE :handoff_pattern"

    params = {
        "nodes": json.dumps(EDUCATION_TEMPLATE_NODES),
        "transitions": json.dumps(EDUCATION_TEMPLATE_TRANSITIONS),
        "name": "Education Assistant template",
        "handoff_pattern": '%"type": "handoff"%',
    }

    bind.execute(
        sa.text(
            """
            UPDATE flow_templates
            SET nodes = {nodes}, transitions = {transitions}
            WHERE name = :name
              AND {stale_handoff_guard}
            """.format(
                nodes=nodes_value.text,
                transitions=transitions_value.text,
                stale_handoff_guard=stale_handoff_guard,
            )
        ),
        params,
    )
    bind.execute(
        sa.text(
            """
            UPDATE flow_template_revisions
            SET nodes = {nodes}, transitions = {transitions}
            WHERE template_id IN (
                SELECT id FROM flow_templates WHERE name = :name
            )
              AND {stale_handoff_guard}
            """.format(
                nodes=nodes_value.text,
                transitions=transitions_value.text,
                stale_handoff_guard=stale_handoff_guard,
            )
        ),
        params,
    )


def downgrade() -> None:
    pass
