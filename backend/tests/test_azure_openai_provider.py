import unittest
from unittest.mock import patch

from services import ai_provider, embeddings
from services.ai_provider import AIProviderError, generate_chat_completion, stream_chat_completion
from services.embeddings import generate_embedding


class _Message:
    content = "ok"


class _Choice:
    message = _Message()


class _CompletionResponse:
    choices = [_Choice()]


class _EmptyMessage:
    content = ""


class _EmptyChoice:
    message = _EmptyMessage()


class _EmptyCompletionResponse:
    choices = [_EmptyChoice()]


class _EmbeddingItem:
    index = 0
    embedding = [0.1, 0.2, 0.3]


class _EmbeddingResponse:
    data = [_EmbeddingItem()]


class _ChatCompletions:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or _CompletionResponse()

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return iter([])
        return self.response


class _Embeddings:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _EmbeddingResponse()


class _Chat:
    def __init__(self, response=None):
        self.completions = _ChatCompletions(response)


class _Client:
    def __init__(self, response=None):
        self.chat = _Chat(response)
        self.embeddings = _Embeddings()


class AzureOpenAIProviderTest(unittest.TestCase):
    def azure_env(self):
        return {
            "AI_PROVIDER": "azure_openai",
            "EMBEDDING_PROVIDER": "azure_openai",
            "AZURE_OPENAI_ENDPOINT": "https://example-resource.openai.azure.com/",
            "AZURE_OPENAI_API_KEY": "test-key",
            "AZURE_OPENAI_DEPLOYMENT": "gpt-5-mini",
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-small",
            "AZURE_OPENAI_API_VERSION": "2024-10-21",
        }

    def test_gpt5_chat_completion_uses_max_completion_tokens_without_temperature(self):
        client = _Client()
        with patch.dict("os.environ", self.azure_env(), clear=False), \
             patch.object(ai_provider, "AI_PROVIDER", "azure_openai"), \
             patch.object(ai_provider, "_azure_client", return_value=client):
            response = generate_chat_completion("Hello", model=None, temperature=0.7, max_tokens=123)

        self.assertEqual(response, "ok")
        request = client.chat.completions.calls[0]
        self.assertEqual(request["model"], "gpt-5-mini")
        self.assertEqual(request["max_completion_tokens"], 512)
        self.assertEqual(request["reasoning_effort"], "minimal")
        self.assertNotIn("max_tokens", request)
        self.assertNotIn("temperature", request)

    def test_gpt5_streaming_uses_max_completion_tokens_without_temperature(self):
        client = _Client()
        with patch.dict("os.environ", self.azure_env(), clear=False), \
             patch.object(ai_provider, "AI_PROVIDER", "azure_openai"), \
             patch.object(ai_provider, "_azure_client", return_value=client):
            list(stream_chat_completion("Hello", model=None, temperature=0.7, max_tokens=45))

        request = client.chat.completions.calls[0]
        self.assertTrue(request["stream"])
        self.assertEqual(request["max_completion_tokens"], 512)
        self.assertEqual(request["reasoning_effort"], "minimal")
        self.assertNotIn("max_tokens", request)
        self.assertNotIn("temperature", request)

    def test_empty_gpt5_response_is_reported_as_error(self):
        client = _Client(_EmptyCompletionResponse())
        with patch.dict("os.environ", self.azure_env(), clear=False), \
             patch.object(ai_provider, "AI_PROVIDER", "azure_openai"), \
             patch.object(ai_provider, "_azure_client", return_value=client):
            with self.assertRaises(AIProviderError) as error:
                generate_chat_completion("Hello", model=None, temperature=0.7, max_tokens=123)

        self.assertIn("empty assistant response", str(error.exception))

    def test_embedding_uses_configured_embedding_deployment(self):
        client = _Client()
        with patch.dict("os.environ", self.azure_env(), clear=False), \
             patch.object(embeddings, "EMBEDDING_PROVIDER", "azure_openai"), \
             patch("openai.AzureOpenAI", return_value=client):
            vector = generate_embedding("Knowledge base content")

        self.assertEqual(vector, [0.1, 0.2, 0.3])
        request = client.embeddings.calls[0]
        self.assertEqual(request["model"], "text-embedding-3-small")
        self.assertEqual(request["input"], "Knowledge base content")


if __name__ == "__main__":
    unittest.main()
