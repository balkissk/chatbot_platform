import unittest
from http.cookies import SimpleCookie
from datetime import timedelta
from unittest.mock import patch

from fastapi import HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.auth_session import AuthSession, utc_now
from models.user import User
from models.user_schema import UserLogin
from routes import auth_routes
from services import auth
from services.auth import (
    AUTH_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    REFRESH_TOKEN_EXPIRES_SECONDS,
    create_access_token,
    get_current_user,
    hash_password,
    hash_refresh_token,
    require_roles,
)
from database.db import Base


class AuthCookieFlowTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.admin = User(
            name="Admin",
            email="admin@example.com",
            password_hash=hash_password("Adminpass123"),
            role="admin",
            status="active",
        )
        self.manager = User(
            name="Manager",
            email="manager@example.com",
            password_hash=hash_password("Managerpass123"),
            role="manager",
            status="active",
        )
        self.disabled = User(
            name="Disabled",
            email="disabled@example.com",
            password_hash=hash_password("Disabled123"),
            role="manager",
            status="disabled",
        )
        self.db.add_all([self.admin, self.manager, self.disabled])
        self.db.commit()
        auth_routes._rate_limit_attempts.clear()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def login_user(self, email: str = "manager@example.com", password: str = "Managerpass123"):
        response = Response()
        payload = UserLogin(email=email, password=password)
        body = auth_routes.login(payload, request=None, response=response, db=self.db)
        return body, response

    def cookie_values(self, response: Response) -> dict[str, str]:
        parsed = SimpleCookie()
        for key, value in response.raw_headers:
            if key.lower() == b"set-cookie":
                parsed.load(value.decode())
        return {name: cookie.value for name, cookie in parsed.items()}

    def assert_cookie_header(self, response: Response, name: str, *expected_parts: str) -> None:
        headers = [
            value.decode()
            for key, value in response.raw_headers
            if key.lower() == b"set-cookie" and value.decode().startswith(f"{name}=")
        ]
        self.assertTrue(headers, f"Missing Set-Cookie header for {name}")
        header = headers[0]
        for expected in expected_parts:
            self.assertIn(expected, header)

    def test_login_sets_http_only_session_cookie_and_returns_user_only(self):
        body, response = self.login_user()

        self.assertEqual(body.user.email, "manager@example.com")
        self.assertFalse(hasattr(body, "access_token"))

        self.assert_cookie_header(
            response,
            AUTH_COOKIE_NAME,
            "HttpOnly",
            "Max-Age=3600",
            "Path=/",
            "SameSite=lax",
        )
        self.assert_cookie_header(
            response,
            REFRESH_COOKIE_NAME,
            "HttpOnly",
            f"Max-Age={REFRESH_TOKEN_EXPIRES_SECONDS}",
            "Path=/auth",
            "SameSite=lax",
        )
        for _, value in response.raw_headers:
            header = value.decode()
            if "chatbot_factory_" in header:
                self.assertNotIn("Secure", header)
                self.assertNotIn("Domain=", header)
                self.assertNotIn("Expires=", header)

        refresh_token = self.cookie_values(response).get(REFRESH_COOKIE_NAME)
        self.assertIsNotNone(refresh_token)
        session = self.db.query(AuthSession).filter(
            AuthSession.token_hash == hash_refresh_token(refresh_token)
        ).first()
        self.assertIsNotNone(session)
        self.assertEqual(session.user_id, self.manager.id)
        self.assertIsNone(session.revoked_at)

    def test_auth_me_succeeds_after_login_via_cookie(self):
        _, login_response = self.login_user()
        access_token = self.cookie_values(login_response)[AUTH_COOKIE_NAME]

        current_user = get_current_user(session_token=access_token, db=self.db)
        response = auth_routes.me(current_user=current_user)

        self.assertEqual(response.email, "manager@example.com")

    def test_refresh_with_expired_access_cookie_issues_new_access_token(self):
        _, login_response = self.login_user()
        refresh_token = self.cookie_values(login_response)[REFRESH_COOKIE_NAME]

        with patch.object(auth, "JWT_EXPIRES_SECONDS", -1):
            expired_access_token = create_access_token(self.manager)

        with self.assertRaises(HTTPException) as expired:
            get_current_user(session_token=expired_access_token, db=self.db)
        self.assertEqual(expired.exception.status_code, 401)
        self.assertEqual(expired.exception.detail, "Token expired")

        refresh_response = Response()
        body = auth_routes.refresh(response=refresh_response, refresh_token=refresh_token, db=self.db)
        self.assertEqual(body["message"], "Session refreshed")

        new_access_token = self.cookie_values(refresh_response)[AUTH_COOKIE_NAME]
        current_user = get_current_user(session_token=new_access_token, db=self.db)
        self.assertEqual(current_user.email, "manager@example.com")

    def test_refresh_rotates_token_and_rejects_old_refresh_token(self):
        _, login_response = self.login_user()
        old_refresh_token = self.cookie_values(login_response)[REFRESH_COOKIE_NAME]
        self.assertIsNotNone(old_refresh_token)

        refresh_response = Response()
        auth_routes.refresh(response=refresh_response, refresh_token=old_refresh_token, db=self.db)
        new_refresh_token = self.cookie_values(refresh_response)[REFRESH_COOKIE_NAME]
        self.assertIsNotNone(new_refresh_token)
        self.assertNotEqual(old_refresh_token, new_refresh_token)

        old_session = self.db.query(AuthSession).filter(
            AuthSession.token_hash == hash_refresh_token(old_refresh_token)
        ).first()
        self.assertIsNotNone(old_session)
        self.assertIsNotNone(old_session.revoked_at)
        self.assertIsNotNone(old_session.replaced_by_session_id)

        with self.assertRaises(HTTPException) as replay:
            auth_routes.refresh(response=Response(), refresh_token=old_refresh_token, db=self.db)
        self.assertEqual(replay.exception.status_code, 401)
        self.assertEqual(replay.exception.detail, "Not authenticated")

    def test_invalid_refresh_token_is_rejected_and_cookies_are_cleared(self):
        response = Response()

        with self.assertRaises(HTTPException) as raised:
            auth_routes.refresh(response=response, refresh_token="invalid-refresh-token", db=self.db)

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail, "Not authenticated")
        self.assert_cookie_header(response, AUTH_COOKIE_NAME, "Max-Age=0")
        self.assert_cookie_header(response, REFRESH_COOKIE_NAME, "Max-Age=0", "Path=/auth")

    def test_expired_refresh_token_is_rejected(self):
        _, login_response = self.login_user()
        refresh_token = self.cookie_values(login_response)[REFRESH_COOKIE_NAME]
        session = self.db.query(AuthSession).filter(
            AuthSession.token_hash == hash_refresh_token(refresh_token)
        ).first()
        session.expires_at = utc_now() - timedelta(seconds=1)
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            auth_routes.refresh(response=Response(), refresh_token=refresh_token, db=self.db)

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail, "Not authenticated")

    def test_refresh_token_for_disabled_user_is_rejected(self):
        _, login_response = self.login_user()
        refresh_token = self.cookie_values(login_response)[REFRESH_COOKIE_NAME]
        self.manager.status = "disabled"
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            auth_routes.refresh(response=Response(), refresh_token=refresh_token, db=self.db)

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail, "Not authenticated")

    def test_manager_route_accepts_manager_cookie(self):
        _, login_response = self.login_user()
        access_token = self.cookie_values(login_response)[AUTH_COOKIE_NAME]

        current_user = get_current_user(session_token=access_token, db=self.db)
        user = require_roles("manager")(current_user=current_user)

        self.assertEqual(user.role, "manager")

    def test_admin_route_accepts_admin_cookie(self):
        _, login_response = self.login_user("admin@example.com", "Adminpass123")
        access_token = self.cookie_values(login_response)[AUTH_COOKIE_NAME]

        current_user = get_current_user(session_token=access_token, db=self.db)
        user = require_roles("admin")(current_user=current_user)

        self.assertEqual(user.role, "admin")

    def test_logout_clears_cookie_and_protected_route_returns_401(self):
        _, login_response = self.login_user()
        refresh_token = self.cookie_values(login_response)[REFRESH_COOKIE_NAME]

        logout_response = Response()
        body = auth_routes.logout(response=logout_response, refresh_token=refresh_token, db=self.db)
        self.assertEqual(body["message"], "Logged out")
        self.assert_cookie_header(logout_response, AUTH_COOKIE_NAME, "Max-Age=0")
        self.assert_cookie_header(logout_response, REFRESH_COOKIE_NAME, "Max-Age=0", "Path=/auth")

        session = self.db.query(AuthSession).filter(
            AuthSession.token_hash == hash_refresh_token(refresh_token)
        ).first()
        self.assertIsNotNone(session.revoked_at)

        with self.assertRaises(HTTPException) as missing_access:
            get_current_user(session_token=None, db=self.db)
        self.assertEqual(missing_access.exception.status_code, 401)
        self.assertEqual(missing_access.exception.detail, "Not authenticated")

        with self.assertRaises(HTTPException) as replay:
            auth_routes.refresh(response=Response(), refresh_token=refresh_token, db=self.db)
        self.assertEqual(replay.exception.status_code, 401)

    def test_invalid_credentials_fail(self):
        with self.assertRaises(HTTPException) as raised:
            auth_routes.login(
                UserLogin(email="manager@example.com", password="wrongpass123"),
                request=None,
                response=Response(),
                db=self.db,
            )

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail, "Invalid email or password")

    def test_disabled_user_cannot_log_in(self):
        with self.assertRaises(HTTPException) as raised:
            auth_routes.login(
                UserLogin(email="disabled@example.com", password="Disabled123"),
                request=None,
                response=Response(),
                db=self.db,
            )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(
            raised.exception.detail,
            "Your account has been disabled. Please contact an administrator.",
        )


if __name__ == "__main__":
    unittest.main()
