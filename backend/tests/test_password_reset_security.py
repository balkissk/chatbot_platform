from datetime import datetime, timedelta
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.user import User
from models.user_schema import ResetPasswordRequest
from routes.auth_routes import hash_reset_token, reset_password
from services.auth import hash_password, verify_password


class PasswordResetSecurityTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()
        self.user = User(
            name="Reset User",
            email="reset@example.com",
            password_hash=hash_password("oldpassword123"),
            role="manager",
            status="active",
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def set_reset_token(self, raw_token: str, expires_at: datetime):
        self.user.password_reset_token = hash_reset_token(raw_token)
        self.user.password_reset_expires_at = expires_at
        self.db.commit()

    def test_valid_reset_token_changes_password(self):
        raw_token = "valid-reset-token"
        self.set_reset_token(raw_token, datetime.utcnow() + timedelta(minutes=10))

        response = reset_password(
            ResetPasswordRequest(token=raw_token, new_password="Newpassword123"),
            db=self.db,
        )

        self.db.refresh(self.user)
        self.assertEqual(response["message"], "Password reset successfully. You can now sign in.")
        self.assertTrue(verify_password("Newpassword123", self.user.password_hash))

    def test_expired_reset_token_is_rejected(self):
        raw_token = "expired-reset-token"
        self.set_reset_token(raw_token, datetime.utcnow() - timedelta(minutes=1))

        with self.assertRaises(HTTPException) as raised:
            reset_password(
                ResetPasswordRequest(token=raw_token, new_password="Newpassword123"),
                db=self.db,
            )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail, "Invalid or expired reset token")

    def test_reset_token_cannot_be_reused_after_success(self):
        raw_token = "single-use-reset-token"
        self.set_reset_token(raw_token, datetime.utcnow() + timedelta(minutes=10))

        reset_password(
            ResetPasswordRequest(token=raw_token, new_password="Newpassword123"),
            db=self.db,
        )

        with self.assertRaises(HTTPException) as raised:
            reset_password(
                ResetPasswordRequest(token=raw_token, new_password="Anotherpassword123"),
                db=self.db,
            )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail, "Invalid or expired reset token")


if __name__ == "__main__":
    unittest.main()
