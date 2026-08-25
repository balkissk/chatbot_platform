import time
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from models.user import User
from services import auth
from services.auth import create_access_token, get_current_user


class JwtExpirationTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        self.engine = engine
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()
        self.user = User(
            name="Manager",
            email="manager@example.com",
            password_hash="x",
            role="manager",
            status="active",
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_valid_jwt_allows_protected_user_lookup(self):
        token = create_access_token(self.user)

        current_user = get_current_user(session_token=token, db=self.db)

        self.assertEqual(current_user.email, "manager@example.com")

    def test_expired_jwt_is_rejected_with_401(self):
        with patch.object(auth, "JWT_EXPIRES_SECONDS", -1):
            token = create_access_token(self.user)

        time.sleep(1)
        with self.assertRaises(HTTPException) as raised:
            get_current_user(session_token=token, db=self.db)

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail, "Token expired")


if __name__ == "__main__":
    unittest.main()
