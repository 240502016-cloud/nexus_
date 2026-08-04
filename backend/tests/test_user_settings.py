from __future__ import annotations

import os
import tempfile
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import schemas

os.environ.setdefault("AVATAR_DIR", tempfile.gettempdir())

from app.core.models import User
from app.core.auth import claims_match_user, create_access_token, decode_user_claims
from app.core.routers.users import change_password, update_me
from app.core.security import hash_password, verify_password
from app.database import Base


class UserSettingsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            username="alice",
            email="alice@example.com",
            display_name="Alice",
            hashed_password=hash_password("current-password"),
        )
        self.other = User(
            username="bob",
            email="bob@example.com",
            hashed_password=hash_password("bob-password"),
        )
        self.db.add_all([self.user, self.other])
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_display_name_can_change_without_sending_password(self):
        updated = update_me(
            schemas.UserUpdate(display_name="  Yeni Ad  "),
            current_user=self.user,
            db=self.db,
        )

        self.assertEqual(updated.display_name, "Yeni Ad")
        self.assertEqual(updated.email, "alice@example.com")

    def test_email_change_requires_current_password(self):
        with self.assertRaises(HTTPException) as raised:
            update_me(
                schemas.UserUpdate(email="new@example.com", current_password="wrong-password"),
                current_user=self.user,
                db=self.db,
            )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(self.user.email, "alice@example.com")

    def test_email_change_is_normalized_and_does_not_clear_display_name(self):
        updated = update_me(
            schemas.UserUpdate(
                email="New.Address@Example.com",
                current_password="current-password",
            ),
            current_user=self.user,
            db=self.db,
        )

        self.assertEqual(updated.email, "new.address@example.com")
        self.assertEqual(updated.display_name, "Alice")

    def test_email_uniqueness_is_case_insensitive(self):
        with self.assertRaises(HTTPException) as raised:
            update_me(
                schemas.UserUpdate(email="BOB@example.com", current_password="current-password"),
                current_user=self.user,
                db=self.db,
            )

        self.assertEqual(raised.exception.status_code, 409)

    def test_password_change_rejects_same_password(self):
        with self.assertRaises(HTTPException) as raised:
            change_password(
                schemas.PasswordChange(
                    current_password="current-password",
                    new_password="current-password",
                ),
                current_user=self.user,
                db=self.db,
            )

        self.assertEqual(raised.exception.status_code, 400)

    def test_password_change_replaces_hash(self):
        old_hash = self.user.hashed_password
        old_token = create_access_token(self.user.id, self.user.auth_version)

        credentials = change_password(
            schemas.PasswordChange(
                current_password="current-password",
                new_password="a-secure-new-password",
            ),
            current_user=self.user,
            db=self.db,
        )

        self.assertNotEqual(self.user.hashed_password, old_hash)
        self.assertEqual(self.user.auth_version, 1)
        self.assertTrue(verify_password("a-secure-new-password", self.user.hashed_password))
        self.assertFalse(verify_password("current-password", self.user.hashed_password))
        self.assertFalse(claims_match_user(decode_user_claims(old_token), self.user))
        self.assertTrue(
            claims_match_user(decode_user_claims(credentials["access_token"]), self.user)
        )


if __name__ == "__main__":
    unittest.main()
