import unittest

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from main import app
from models.audit_log import AuditLog
from models.platform_settings import PlatformSettings
from models.platform_settings_schema import PlatformSettingsUpdate
from models.user import User
from routes.platform_settings_routes import read_platform_settings, update_platform_settings
from services.auth import require_roles


class PlatformSettingsTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.admin = User(name="Admin", email="admin@example.com", password_hash="x", role="admin", status="active")
        self.manager = User(name="Manager", email="manager@example.com", password_hash="x", role="manager", status="active")
        self.db.add_all([self.admin, self.manager])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def valid_payload(self, **overrides):
        payload = {
            "platform_name": "ChatBot Factory Enterprise",
            "support_email": "support@example.com",
            "default_page_size": 25,
        }
        payload.update(overrides)
        return PlatformSettingsUpdate.model_validate(payload)

    def test_admin_can_read_default_settings(self):
        response = read_platform_settings(db=self.db, current_user=self.admin)
        self.assertEqual(response.platform_name, "ChatBot Factory")
        self.assertEqual(response.support_email, "support@chatbotfactory.com")
        self.assertEqual(response.default_page_size, 10)

    def test_admin_can_update_and_persist_settings(self):
        response = update_platform_settings(self.valid_payload(), db=self.db, current_user=self.admin)
        self.assertEqual(response.platform_name, "ChatBot Factory Enterprise")
        self.assertEqual(response.support_email, "support@example.com")
        self.assertEqual(response.default_page_size, 25)
        self.assertEqual(response.updated_by, self.admin.id)

        persisted = self.db.query(PlatformSettings).first()
        self.assertEqual(persisted.platform_name, "ChatBot Factory Enterprise")
        self.assertEqual(persisted.updated_by, self.admin.id)

    def test_manager_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            require_roles("admin")(self.manager)
        self.assertEqual(raised.exception.status_code, 403)

    def test_unauthenticated_user_is_rejected(self):
        client = TestClient(app)
        response = client.get("/admin/platform-settings")
        self.assertIn(response.status_code, {401, 403})

    def test_invalid_support_email_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.valid_payload(support_email="not-an-email")

    def test_empty_platform_name_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.valid_payload(platform_name="   ")

    def test_invalid_default_page_size_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.valid_payload(default_page_size=5)
        with self.assertRaises(ValidationError):
            self.valid_payload(default_page_size=101)

    def test_only_one_platform_settings_record_exists(self):
        self.db.add(PlatformSettings(id=2, platform_name="Duplicate", support_email="duplicate@example.com", default_page_size=10))
        self.db.commit()

        update_platform_settings(self.valid_payload(), db=self.db, current_user=self.admin)
        update_platform_settings(self.valid_payload(platform_name="Updated"), db=self.db, current_user=self.admin)
        self.assertEqual(self.db.query(PlatformSettings).count(), 1)
        self.assertEqual(self.db.query(PlatformSettings).first().platform_name, "Updated")

    def test_audit_log_created_after_successful_update(self):
        update_platform_settings(self.valid_payload(), db=self.db, current_user=self.admin)
        audit = self.db.query(AuditLog).filter(AuditLog.action == "PLATFORM_SETTINGS_UPDATED").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.resource_type, "platform_settings")
        self.assertIn("platform_name", audit.metadata_json["changed_fields"])
        self.assertNotIn("secret", str(audit.metadata_json).lower())

    def test_audit_log_not_created_after_failed_validation(self):
        with self.assertRaises(ValidationError):
            self.valid_payload(default_page_size=1)
        self.assertEqual(self.db.query(AuditLog).count(), 0)

    def test_unsupported_fields_cannot_be_mass_assigned(self):
        with self.assertRaises(ValidationError):
            PlatformSettingsUpdate.model_validate({
                "platform_name": "ChatBot Factory",
                "support_email": "support@example.com",
                "default_page_size": 25,
                "jwt_secret": "do-not-store",
            })

    def test_response_does_not_return_secret_fields(self):
        response = update_platform_settings(self.valid_payload(), db=self.db, current_user=self.admin)
        serialized = response.model_dump()
        self.assertNotIn("jwt_secret", serialized)
        self.assertNotIn("database_url", serialized)
        self.assertNotIn("llm_key", serialized)


if __name__ == "__main__":
    unittest.main()
