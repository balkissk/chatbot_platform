import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.health_routes import router


class HealthWarmupTest(unittest.TestCase):
    def make_client(self):
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_warmup_returns_ready_when_database_responds(self):
        db = Mock()
        db.execute.return_value.scalar_one.return_value = 1

        with patch("routes.health_routes.SessionLocal", return_value=db):
            response = self.make_client().get("/health/warmup")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready"})
        db.execute.assert_called_once()
        db.close.assert_called_once()

    def test_warmup_returns_503_when_database_check_fails(self):
        db = Mock()
        db.execute.side_effect = RuntimeError("database unavailable")

        with patch("routes.health_routes.SessionLocal", return_value=db):
            response = self.make_client().get("/health/warmup")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Backend is not ready"})
        self.assertNotIn("database unavailable", response.text)
        db.close.assert_called_once()

    def test_warmup_does_not_require_authentication(self):
        db = Mock()
        db.execute.return_value.scalar_one.return_value = 1

        with patch("routes.health_routes.SessionLocal", return_value=db):
            response = self.make_client().get("/health/warmup")

        self.assertEqual(response.status_code, 200)

    def test_warmup_does_not_call_ai_or_embeddings(self):
        db = Mock()
        db.execute.return_value.scalar_one.return_value = 1

        with patch("routes.health_routes.SessionLocal", return_value=db), \
             patch("routes.health_routes.generate_chat_completion") as chat_completion, \
             patch("routes.health_routes.generate_embedding") as embedding:
            response = self.make_client().get("/health/warmup")

        self.assertEqual(response.status_code, 200)
        chat_completion.assert_not_called()
        embedding.assert_not_called()


if __name__ == "__main__":
    unittest.main()
