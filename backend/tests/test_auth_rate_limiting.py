import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.user import User
from models.user_schema import ForgotPasswordRequest, UserLogin
from routes import auth_routes
from routes.auth_routes import forgot_password, login
from services.auth import hash_password


class _Client:
    def __init__(self, host: str):
        self.host = host


class _Request:
    def __init__(self, host: str):
        self.client = _Client(host)


class AuthRateLimitingTest(unittest.TestCase):
    def setUp(self):
        auth_routes._rate_limit_attempts.clear()
        self.now = 1000.0
        self.time_patch = patch.object(auth_routes, "_rate_limit_time", lambda: self.now)
        self.time_patch.start()

        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()
        self.user = User(
            name="Manager",
            email="manager@example.com",
            password_hash=hash_password("password123"),
            role="manager",
            status="active",
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.time_patch.stop()
        auth_routes._rate_limit_attempts.clear()
        self.db.close()
        self.engine.dispose()

    def test_login_requests_under_limit_are_allowed(self):
        request = _Request("203.0.113.10")

        for _ in range(auth_routes.LOGIN_RATE_LIMIT):
            with self.assertRaises(HTTPException) as raised:
                login(UserLogin(email="manager@example.com", password="wrong-password"), request=request, db=self.db)
            self.assertEqual(raised.exception.status_code, 401)

    def test_login_over_limit_returns_429(self):
        request = _Request("203.0.113.11")

        for _ in range(auth_routes.LOGIN_RATE_LIMIT):
            with self.assertRaises(HTTPException):
                login(UserLogin(email="manager@example.com", password="wrong-password"), request=request, db=self.db)

        with self.assertRaises(HTTPException) as raised:
            login(UserLogin(email="manager@example.com", password="wrong-password"), request=request, db=self.db)

        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.detail, "Too many requests. Please try again later.")

    def test_login_rate_limit_expires_after_window(self):
        request = _Request("203.0.113.12")

        for _ in range(auth_routes.LOGIN_RATE_LIMIT):
            with self.assertRaises(HTTPException):
                login(UserLogin(email="manager@example.com", password="wrong-password"), request=request, db=self.db)

        self.now += auth_routes.LOGIN_RATE_WINDOW_SECONDS + 1
        response = login(UserLogin(email="manager@example.com", password="password123"), request=request, db=self.db)

        self.assertEqual(response.user.email, "manager@example.com")

    def test_forgot_password_requests_under_limit_are_allowed(self):
        request = _Request("203.0.113.20")

        with patch.object(auth_routes, "send_password_reset_email", Mock()):
            for _ in range(auth_routes.FORGOT_PASSWORD_RATE_LIMIT):
                response = forgot_password(
                    ForgotPasswordRequest(email="manager@example.com"),
                    request=request,
                    db=self.db,
                )
                self.assertEqual(response["message"], auth_routes.PASSWORD_RESET_RESPONSE)

    def test_forgot_password_over_limit_returns_429(self):
        request = _Request("203.0.113.21")

        with patch.object(auth_routes, "send_password_reset_email", Mock()):
            for _ in range(auth_routes.FORGOT_PASSWORD_RATE_LIMIT):
                forgot_password(ForgotPasswordRequest(email="manager@example.com"), request=request, db=self.db)

            with self.assertRaises(HTTPException) as raised:
                forgot_password(ForgotPasswordRequest(email="manager@example.com"), request=request, db=self.db)

        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.detail, "Too many requests. Please try again later.")

    def test_forgot_password_rate_limit_expires_after_window(self):
        request = _Request("203.0.113.22")

        with patch.object(auth_routes, "send_password_reset_email", Mock()):
            for _ in range(auth_routes.FORGOT_PASSWORD_RATE_LIMIT):
                forgot_password(ForgotPasswordRequest(email="manager@example.com"), request=request, db=self.db)

            self.now += auth_routes.FORGOT_PASSWORD_RATE_WINDOW_SECONDS + 1
            response = forgot_password(
                ForgotPasswordRequest(email="manager@example.com"),
                request=request,
                db=self.db,
            )

        self.assertEqual(response["message"], auth_routes.PASSWORD_RESET_RESPONSE)


if __name__ == "__main__":
    unittest.main()
