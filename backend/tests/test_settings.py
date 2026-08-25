import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from config import settings as settings_module
from models.user import User
from routes.auth_routes import create_password_reset_link


class SettingsEnvironmentLoadingTest(unittest.TestCase):
    def load_settings_from(self, backend_dir: Path):
        with patch.dict("os.environ", {}, clear=True), \
             patch.object(settings_module, "BACKEND_DIR", backend_dir), \
             patch.object(settings_module, "_LOADED", False):
            return settings_module.get_settings()

    def test_development_uses_local_frontend_base_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backend_dir = Path(tmpdir)
            (backend_dir / ".env").write_text("ENVIRONMENT=development\n", encoding="utf-8")
            (backend_dir / ".env.development").write_text(
                "DATABASE_URL=postgresql://postgres:postgres@localhost:5432/chatbot_db\n"
                "FRONTEND_URL=http://localhost:4200\n",
                encoding="utf-8",
            )

            settings = self.load_settings_from(backend_dir)

        self.assertEqual(settings.environment, "development")
        self.assertEqual(settings.frontend_base_url, "http://localhost:4200")

    def test_password_reset_link_uses_development_frontend_base_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backend_dir = Path(tmpdir)
            (backend_dir / ".env").write_text("ENVIRONMENT=development\n", encoding="utf-8")
            (backend_dir / ".env.development").write_text(
                "DATABASE_URL=postgresql://postgres:postgres@localhost:5432/chatbot_db\n"
                "FRONTEND_BASE_URL=http://localhost:4200\n"
                "FRONTEND_URL=http://localhost:4200\n",
                encoding="utf-8",
            )
            user = User(email="user@example.com")
            db = Mock()

            with patch.dict("os.environ", {}, clear=True), \
                 patch.object(settings_module, "BACKEND_DIR", backend_dir), \
                 patch.object(settings_module, "_LOADED", False):
                reset_link = create_password_reset_link(user, db)

        self.assertTrue(reset_link.startswith("http://localhost:4200/reset-password?token="))
        db.commit.assert_called_once()

    def test_profile_file_overrides_dotenv_for_frontend_base_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backend_dir = Path(tmpdir)
            (backend_dir / ".env").write_text(
                "ENVIRONMENT=production\n"
                "DATABASE_URL=postgresql://user:pass@db.example.com:5432/chatbot_db?sslmode=require\n"
                "FRONTEND_BASE_URL=http://localhost:4200\n",
                encoding="utf-8",
            )
            (backend_dir / ".env.production").write_text(
                "DATABASE_URL=postgresql://user:pass@db.example.com:5432/chatbot_db?sslmode=require\n"
                "FRONTEND_BASE_URL=https://frontend.azurewebsites.net\n",
                encoding="utf-8",
            )

            settings = self.load_settings_from(backend_dir)

        self.assertEqual(settings.environment, "production")
        self.assertEqual(settings.frontend_base_url, "https://frontend.azurewebsites.net")

    def test_production_does_not_use_frontend_url_for_reset_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backend_dir = Path(tmpdir)
            (backend_dir / ".env").write_text(
                "ENVIRONMENT=production\n"
                "DATABASE_URL=postgresql://user:pass@db.example.com:5432/chatbot_db?sslmode=require\n",
                encoding="utf-8",
            )
            (backend_dir / ".env.production").write_text(
                "DATABASE_URL=postgresql://user:pass@db.example.com:5432/chatbot_db?sslmode=require\n"
                "FRONTEND_URL=https://frontend.azurewebsites.net\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "FRONTEND_BASE_URL"):
                self.load_settings_from(backend_dir)


if __name__ == "__main__":
    unittest.main()
