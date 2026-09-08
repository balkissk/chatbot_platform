import unittest

from fastapi import HTTPException
from fastapi.routing import APIRoute

from models.user import User
from routes import (
    channel_routes,
    chatbot_routes,
    evaluation_routes,
    flow_routes,
    knowledge_routes,
    llm_config_routes,
    project_routes,
    version_routes,
)
from services.auth import require_workspace_manager


class WorkspaceReadOnlyPermissionsTest(unittest.TestCase):
    def test_workspace_manager_dependency_allows_manager_and_rejects_admin(self):
        manager = User(role="manager")
        admin = User(role="admin")

        self.assertIs(require_workspace_manager(current_user=manager), manager)

        with self.assertRaises(HTTPException) as raised:
            require_workspace_manager(current_user=admin)

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.detail, "Admins have read-only access to projects and assistants.")

    def test_project_write_routes_require_workspace_manager(self):
        self.assert_write_dependency(project_routes.router, "POST", "/projects")
        self.assert_write_dependency(project_routes.router, "PUT", "/projects/{project_id}/archive")
        self.assert_write_dependency(project_routes.router, "PUT", "/projects/{project_id}/restore")
        self.assert_write_dependency(project_routes.router, "POST", "/projects/{project_id}/duplicate")
        self.assert_write_dependency(project_routes.router, "PUT", "/projects/{project_id}")
        self.assert_write_dependency(project_routes.router, "DELETE", "/projects/{project_id}")

    def test_assistant_write_routes_require_workspace_manager(self):
        self.assert_write_dependency(chatbot_routes.router, "POST", "/chatbots")
        self.assert_write_dependency(chatbot_routes.router, "PATCH", "/chatbots/{id}/conversations/{session_id}/follow-up")
        self.assert_write_dependency(chatbot_routes.router, "PATCH", "/chatbots/{id}/setup")
        self.assert_write_dependency(chatbot_routes.router, "POST", "/chatbots/{id}/setup/template-draft")
        self.assert_write_dependency(chatbot_routes.router, "POST", "/chatbots/{id}/setup/ai-draft")
        self.assert_write_dependency(chatbot_routes.router, "PUT", "/chatbots/{id}/api-key/regenerate")
        self.assert_write_dependency(chatbot_routes.router, "PUT", "/chatbots/{id}/rag-settings")
        self.assert_write_dependency(chatbot_routes.router, "PUT", "/chatbots/{id}")
        self.assert_write_dependency(chatbot_routes.router, "PUT", "/chatbots/{id}/status")
        self.assert_write_dependency(chatbot_routes.router, "DELETE", "/chatbots/{id}")

    def test_assistant_subresource_write_routes_require_workspace_manager(self):
        self.assert_write_dependency(version_routes.router, "POST", "/versions")
        self.assert_write_dependency(version_routes.router, "POST", "/versions/{version_id}/duplicate")
        self.assert_write_dependency(version_routes.router, "POST", "/versions/{version_id}/smoke-test")
        self.assert_write_dependency(version_routes.router, "PUT", "/versions/{version_id}/publish")
        self.assert_write_dependency(version_routes.router, "PUT", "/versions/{version_id}/archive")
        self.assert_write_dependency(version_routes.router, "DELETE", "/versions/{version_id}")
        self.assert_write_dependency(llm_config_routes.router, "POST", "/llm-config")
        self.assert_write_dependency(channel_routes.router, "POST", "/chatbots/{chatbot_id}/channels/{channel_type}")
        self.assert_write_dependency(channel_routes.router, "PUT", "/chatbots/{chatbot_id}/channels/{channel_type}")
        self.assert_write_dependency(channel_routes.router, "POST", "/chatbots/{chatbot_id}/channels/{channel_type}/test")
        self.assert_write_dependency(channel_routes.router, "PATCH", "/chatbots/{chatbot_id}/channels/{channel_type}/clear-error")
        self.assert_write_dependency(channel_routes.router, "DELETE", "/chatbots/{chatbot_id}/channels/{channel_type}")
        self.assert_write_dependency(knowledge_routes.router, "POST", "/versions/{version_id}/documents")
        self.assert_write_dependency(knowledge_routes.router, "PUT", "/documents/{document_id}")
        self.assert_write_dependency(knowledge_routes.router, "POST", "/documents/{document_id}/embeddings/reprocess")
        self.assert_write_dependency(knowledge_routes.router, "POST", "/documents/{document_id}/chunks/reprocess")
        self.assert_write_dependency(knowledge_routes.router, "DELETE", "/documents/{document_id}")
        self.assert_write_dependency(flow_routes.router, "PATCH", "/flow-templates/{template_key}")
        self.assert_write_dependency(flow_routes.router, "POST", "/flows/{flow_id}/template-library")
        self.assert_write_dependency(flow_routes.router, "POST", "/flows/{flow_id}/template-library/{template_key}/revisions")
        self.assert_write_dependency(flow_routes.router, "POST", "/flows/{flow_id}/template")
        self.assert_write_dependency(flow_routes.router, "POST", "/flows/{flow_id}/generated")
        self.assert_write_dependency(flow_routes.router, "POST", "/flows/{flow_id}/nodes")
        self.assert_write_dependency(flow_routes.router, "PUT", "/flow-nodes/{node_id}")
        self.assert_write_dependency(flow_routes.router, "DELETE", "/flow-nodes/{node_id}")
        self.assert_write_dependency(flow_routes.router, "POST", "/flows/{flow_id}/transitions")
        self.assert_write_dependency(flow_routes.router, "PUT", "/flow-transitions/{transition_id}")
        self.assert_write_dependency(flow_routes.router, "DELETE", "/flow-transitions/{transition_id}")
        self.assert_write_dependency(flow_routes.router, "POST", "/assistants/ai-generate")

    def test_evaluation_write_routes_require_workspace_manager(self):
        self.assert_write_dependency(evaluation_routes.router, "POST", "/evaluations/assistants/{assistant_id}/datasets")
        self.assert_write_dependency(evaluation_routes.router, "PUT", "/evaluations/datasets/{dataset_id}")
        self.assert_write_dependency(evaluation_routes.router, "POST", "/evaluations/datasets/{dataset_id}/archive")
        self.assert_write_dependency(evaluation_routes.router, "POST", "/evaluations/datasets/{dataset_id}/restore")
        self.assert_write_dependency(evaluation_routes.router, "DELETE", "/evaluations/datasets/{dataset_id}")
        self.assert_write_dependency(evaluation_routes.router, "POST", "/evaluations/datasets/{dataset_id}/cases")
        self.assert_write_dependency(evaluation_routes.router, "PUT", "/evaluations/cases/{case_id}")
        self.assert_write_dependency(evaluation_routes.router, "POST", "/evaluations/cases/{case_id}/duplicate")
        self.assert_write_dependency(evaluation_routes.router, "POST", "/evaluations/datasets/{dataset_id}/cases/reorder")
        self.assert_write_dependency(evaluation_routes.router, "POST", "/evaluations/cases/{case_id}/enabled")
        self.assert_write_dependency(evaluation_routes.router, "DELETE", "/evaluations/cases/{case_id}")
        self.assert_write_dependency(evaluation_routes.router, "POST", "/evaluations/datasets/{dataset_id}/import")
        self.assert_write_dependency(evaluation_routes.router, "POST", "/evaluations/runs")
        self.assert_write_dependency(evaluation_routes.router, "POST", "/evaluations/runs/{run_id}/cancel")
        self.assert_write_dependency(evaluation_routes.router, "PUT", "/evaluations/assistants/{assistant_id}/policy")

    def assert_write_dependency(self, router, method: str, path: str) -> None:
        route = next(
            (
                item for item in router.routes
                if isinstance(item, APIRoute) and item.path == path and method in item.methods
            ),
            None,
        )
        self.assertIsNotNone(route, f"Missing route {method} {path}")
        dependencies = {getattr(dependency.call, "__name__", "") for dependency in route.dependant.dependencies}
        self.assertIn("require_workspace_manager", dependencies, f"{method} {path} is not manager-only")


if __name__ == "__main__":
    unittest.main()
