import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.audit_log import AuditLog
from models.chatbot import Chatbot
from models.project import Project
from models.user import User
from models.user_schema import AdminUserCreate, UserLogin, UserStatusUpdate
from routes.auth_routes import create_user, list_users, login, update_user_status
from services.auth import hash_password, require_roles


class AdminUsersTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()
        self.admin = User(name="Admin", email="admin@example.com", password_hash="x", role="admin", status="active")
        self.manager = User(name="Manager", email="manager@example.com", password_hash="x", role="manager", status="active")
        self.disabled = User(name="Disabled", email="disabled@example.com", password_hash="x", role="end_user", status="disabled")
        self.db.add_all([self.admin, self.manager, self.disabled])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_admin_can_list_users_with_pagination_and_global_stats(self):
        payload = list_users(
            search=None,
            role=None,
            status=None,
            page=1,
            page_size=2,
            current_user=self.admin,
            db=self.db,
        )
        self.assertEqual(payload.total, 3)
        self.assertEqual(len(payload.items), 2)
        self.assertEqual(payload.stats.total_users, 3)
        self.assertEqual(payload.stats.active_users, 2)
        self.assertEqual(payload.stats.disabled_users, 1)
        self.assertEqual(payload.stats.managers, 1)

    def test_manager_cannot_access_platform_users(self):
        with self.assertRaises(HTTPException) as raised:
            require_roles("admin")(self.manager)
        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.detail, "You do not have permission to access this resource.")

    def test_search_role_and_status_filters_work(self):
        searched = list_users("manager", None, None, 1, 10, self.admin, self.db)
        self.assertEqual([user.email for user in searched.items], ["manager@example.com"])

        managers = list_users(None, "manager", None, 1, 10, self.admin, self.db)
        self.assertEqual(managers.total, 1)
        self.assertEqual(managers.items[0].role, "manager")

        disabled = list_users(None, None, "disabled", 1, 10, self.admin, self.db)
        self.assertEqual(disabled.total, 1)
        self.assertEqual(disabled.items[0].status, "disabled")

    def test_user_counts_are_aggregated_without_sensitive_fields(self):
        project = Project(name="Project", description="", user_id=self.manager.id)
        self.db.add(project)
        self.db.commit()
        self.db.add(Chatbot(name="Bot", project_id=project.id, language="en"))
        self.db.commit()

        payload = list_users("manager", None, None, 1, 10, self.admin, self.db)
        item = payload.items[0]
        self.assertEqual(item.project_count, 1)
        self.assertEqual(item.chatbot_count, 1)
        self.assertFalse(hasattr(item, "password_hash"))

    def test_create_duplicate_email_and_audit_log(self):
        created = create_user(
            AdminUserCreate(name="New Manager", email="new@example.com", role="manager"),
            current_user=self.admin,
            db=self.db,
        )
        self.assertEqual(created.email, "new@example.com")
        self.assertEqual(self.db.query(AuditLog).order_by(AuditLog.id.desc()).first().action, "USER_CREATED")

        with self.assertRaises(HTTPException) as raised:
            create_user(
                AdminUserCreate(name="Duplicate", email="new@example.com", role="manager"),
                current_user=self.admin,
                db=self.db,
            )
        self.assertEqual(raised.exception.status_code, 400)

    def test_disable_activate_rules_and_audit_logs(self):
        update_user_status(
            self.manager.id,
            UserStatusUpdate(status="disabled"),
            current_user=self.admin,
            db=self.db,
        )
        self.assertEqual(self.db.query(User).filter(User.id == self.manager.id).first().status, "disabled")
        self.assertEqual(self.db.query(AuditLog).order_by(AuditLog.id.desc()).first().action, "USER_DISABLED")

        update_user_status(
            self.manager.id,
            UserStatusUpdate(status="active"),
            current_user=self.admin,
            db=self.db,
        )
        self.assertEqual(self.db.query(User).filter(User.id == self.manager.id).first().status, "active")
        self.assertEqual(self.db.query(AuditLog).order_by(AuditLog.id.desc()).first().action, "USER_ACTIVATED")

    def test_admin_cannot_disable_self_or_last_active_admin(self):
        with self.assertRaises(HTTPException) as self_disable:
            update_user_status(
                self.admin.id,
                UserStatusUpdate(status="disabled"),
                current_user=self.admin,
                db=self.db,
            )
        self.assertEqual(self_disable.exception.status_code, 400)

        other_admin = User(name="Other Admin", email="other@example.com", password_hash="x", role="admin", status="active")
        self.db.add(other_admin)
        self.db.commit()
        update_user_status(other_admin.id, UserStatusUpdate(status="disabled"), current_user=self.admin, db=self.db)

        with self.assertRaises(HTTPException) as last_admin:
            update_user_status(self.admin.id, UserStatusUpdate(status="disabled"), current_user=other_admin, db=self.db)
        self.assertEqual(last_admin.exception.status_code, 400)

    def test_login_updates_last_login(self):
        user = User(
            name="Login User",
            email="login@example.com",
            password_hash=hash_password("Password123"),
            role="manager",
            status="active",
        )
        self.db.add(user)
        self.db.commit()
        self.assertIsNone(user.last_login_at)

        response = login(UserLogin(email="login@example.com", password="Password123"), db=self.db)
        self.assertIsNotNone(response.user.last_login_at)

    def test_disabled_user_login_returns_clear_message(self):
        disabled_user = User(
            name="Disabled Login",
            email="disabled-login@example.com",
            password_hash=hash_password("password123"),
            role="manager",
            status="disabled",
        )
        self.db.add(disabled_user)
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            login(UserLogin(email="disabled-login@example.com", password="password123"), db=self.db)

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(
            raised.exception.detail,
            "Your account has been disabled. Please contact an administrator.",
        )


if __name__ == "__main__":
    unittest.main()
