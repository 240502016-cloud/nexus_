from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import schemas

os.environ.setdefault("AVATAR_DIR", tempfile.gettempdir())

from app.core.routers.users import create_user
from app.database import Base


class RegistrationResilienceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.payload = schemas.UserCreate(
            username="alice",
            email="alice@example.com",
            password="correct-horse-battery-staple",
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @patch("app.core.routers.users.matrix_client.register_user")
    def test_lost_registration_response_can_be_retried(self, register_user):
        register_user.return_value = {
            "user_id": "@alice:test",
            "access_token": "matrix-token",
        }

        created = create_user(self.payload, db=self.db)
        repeated = create_user(self.payload, db=self.db)

        self.assertEqual(repeated.id, created.id)
        self.assertEqual(register_user.call_count, 1)

    @patch("app.core.routers.users.matrix_client.register_user")
    def test_retry_does_not_hide_different_credentials(self, register_user):
        register_user.return_value = {
            "user_id": "@alice:test",
            "access_token": "matrix-token",
        }
        create_user(self.payload, db=self.db)

        with self.assertRaises(HTTPException) as raised:
            create_user(
                schemas.UserCreate(
                    username="alice",
                    email="alice@example.com",
                    password="a-different-password",
                ),
                db=self.db,
            )

        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
