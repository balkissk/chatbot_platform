import unittest

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from main import app
from models.audit_log import AuditLog
from models.user import User
from models.user_schema import UserPasswordUpdate, UserProfileUpdate
from routes.auth_routes import me, update_password, update_profile
from services.auth import hash_password, verify_password


class ProfileTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.admin = User(
            name="Admin",
            email="admin@example.com",
            password_hash=hash_password("adminpass123"),
            role="admin",
            status="active",
        )
        self.manager = User(
            name="Manager",
            email="manager@example.com",
            password_hash=hash_password("managerpass123"),
            role="manager",
            status="active",
        )
        self.db.add_all([self.admin, self.manager])
        self.db.commit()
        self.db.refresh(self.admin)
        self.db.refresh(self.manager)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_admin_can_load_shared_profile_without_sensitive_fields(self):
        response = me(current_user=self.admin)
        self.assertEqual(response.email, "admin@example.com")
        self.assertEqual(response.role, "admin")
        self.assertFalse(hasattr(response, "password_hash"))

    def test_manager_profile_behavior_is_preserved(self):
        response = me(current_user=self.manager)
        self.assertEqual(response.email, "manager@example.com")
        self.assertEqual(response.role, "manager")

    def test_update_profile_uses_current_user_and_creates_audit_log(self):
        response = update_profile(
            UserProfileUpdate(name="  Platform Admin  "),
            current_user=self.admin,
            db=self.db,
        )
        self.assertEqual(response.name, "Platform Admin")

        persisted = self.db.query(User).filter(User.id == self.admin.id).first()
        self.assertEqual(persisted.name, "Platform Admin")

        audit = self.db.query(AuditLog).filter(AuditLog.action == "PROFILE_UPDATED").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor_user_id, self.admin.id)
        self.assertEqual(audit.resource_type, "user")
        self.assertEqual(audit.metadata_json, {"changed_fields": ["name"]})

    def test_unchanged_profile_does_not_create_audit_log(self):
        update_profile(UserProfileUpdate(name="Admin"), current_user=self.admin, db=self.db)
        self.assertEqual(self.db.query(AuditLog).count(), 0)

    def test_profile_payload_rejects_mass_assignment(self):
        with self.assertRaises(ValidationError):
            UserProfileUpdate.model_validate({
                "name": "Admin",
                "role": "manager",
                "status": "disabled",
            })

    def test_password_change_validates_current_password_and_creates_audit_log(self):
        update_password(
            UserPasswordUpdate(current_password="adminpass123", new_password="Newpass123"),
            current_user=self.admin,
            db=self.db,
        )
        persisted = self.db.query(User).filter(User.id == self.admin.id).first()
        self.assertTrue(verify_password("Newpass123", persisted.password_hash))

        audit = self.db.query(AuditLog).filter(AuditLog.action == "PASSWORD_CHANGED").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor_user_id, self.admin.id)
        self.assertIsNone(audit.metadata_json)

    def test_failed_password_change_does_not_create_audit_log(self):
        with self.assertRaises(HTTPException) as raised:
            update_password(
                UserPasswordUpdate(current_password="wrongpass123", new_password="Newpass123"),
                current_user=self.admin,
                db=self.db,
            )
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(self.db.query(AuditLog).count(), 0)

    def test_password_payload_rejects_short_password_and_mass_assignment(self):
        with self.assertRaises(ValidationError):
            UserPasswordUpdate.model_validate({
                "current_password": "adminpass123",
                "new_password": "short",
            })

        with self.assertRaises(ValidationError):
            UserPasswordUpdate.model_validate({
                "current_password": "adminpass123",
                "new_password": "Newpass123",
                "role": "admin",
            })

    def test_unauthenticated_profile_request_is_rejected(self):
        client = TestClient(app)
        response = client.get("/auth/me")
        self.assertIn(response.status_code, {401, 403})


if __name__ == "__main__":
    unittest.main()
