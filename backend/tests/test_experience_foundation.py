from __future__ import annotations

import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.models import Server, ServerMember, User
from app.database import Base
from app.platform.events import append_event, event_is_visible
from app.platform.jobs import enqueue_job
from app.platform.models import (
    BackgroundJob,
    ExperienceEvent,
    ExperienceSession,
    OutboxEvent,
)
from app.platform.sessions import (
    consume_ws_ticket,
    create_session,
    issue_ws_ticket,
    join_session,
    set_ready,
    start_session,
)
from app.platform.router import list_experience_events


class ExperienceFoundationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.owner = User(username="owner", email="owner@test", hashed_password="x")
        self.second = User(username="second", email="second@test", hashed_password="x")
        self.third = User(username="third", email="third@test", hashed_password="x")
        self.outsider = User(username="outside", email="outside@test", hashed_password="x")
        self.db.add_all([self.owner, self.second, self.third, self.outsider])
        self.db.flush()
        self.server = Server(name="Game Server", owner_id=self.owner.id)
        self.db.add(self.server)
        self.db.flush()
        self.db.add_all(
            [
                ServerMember(user_id=self.owner.id, server_id=self.server.id),
                ServerMember(user_id=self.second.id, server_id=self.server.id),
                ServerMember(user_id=self.third.id, server_id=self.server.id),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create_game(self) -> ExperienceSession:
        return create_session(
            self.db,
            server_id=self.server.id,
            module_type="ai_board_game",
            owner=self.owner,
            idempotency_key="create-board-001",
        )

    def test_three_player_lobby_is_revisioned_replayable_and_idempotent(self):
        session = self.create_game()
        repeated = self.create_game()
        self.assertEqual(repeated.id, session.id)
        self.assertEqual(self.db.query(ExperienceSession).count(), 1)

        session = join_session(self.db, session.id, self.second, expected_revision=0)
        session = join_session(self.db, session.id, self.third, expected_revision=1)
        session = set_ready(self.db, session.id, self.owner, expected_revision=2, ready=True)
        session = set_ready(self.db, session.id, self.second, expected_revision=3, ready=True)
        session = set_ready(self.db, session.id, self.third, expected_revision=4, ready=True)
        session = start_session(self.db, session.id, self.owner, expected_revision=5)

        self.assertEqual(session.status, "active")
        self.assertEqual(session.revision, 6)
        self.assertEqual([player.seat for player in session.players], [0, 1, 2])
        self.assertTrue(all(player.ready for player in session.players))
        events = (
            self.db.query(ExperienceEvent)
            .filter(ExperienceEvent.session_id == session.id)
            .order_by(ExperienceEvent.sequence)
            .all()
        )
        self.assertEqual([event.sequence for event in events], list(range(1, 8)))
        self.assertEqual(events[-1].event_type, "session.started")
        self.assertEqual(self.db.query(OutboxEvent).count(), len(events))

    def test_stale_revision_and_non_member_are_rejected(self):
        session = self.create_game()
        join_session(self.db, session.id, self.second, expected_revision=0)
        with self.assertRaises(HTTPException) as stale:
            join_session(self.db, session.id, self.third, expected_revision=0)
        self.assertEqual(stale.exception.status_code, 409)
        with self.assertRaises(HTTPException) as forbidden:
            join_session(self.db, session.id, self.outsider, expected_revision=1)
        self.assertEqual(forbidden.exception.status_code, 403)

    def test_private_events_are_filtered_by_audience(self):
        session = self.create_game()
        session = join_session(self.db, session.id, self.second, expected_revision=0)
        private = append_event(
            self.db,
            session,
            "hidden.private_clue",
            {"clue": "only owner"},
            audience=f"USER:{self.owner.id}",
        )
        self.db.commit()
        self.assertTrue(event_is_visible(private, self.owner.id))
        self.assertFalse(event_is_visible(private, self.second.id))

        page = list_experience_events(
            session.id,
            after=0,
            limit=200,
            current_user=self.second,
            db=self.db,
        )
        self.assertNotIn("hidden.private_clue", [event["type"] for event in page["items"]])
        self.assertEqual(page["last_sequence"], private.sequence)

    def test_websocket_ticket_is_single_use(self):
        session = self.create_game()
        raw, _expires = issue_ws_ticket(self.db, session, self.owner)
        self.assertEqual(consume_ws_ticket(self.db, session.id, raw), self.owner.id)
        self.assertIsNone(consume_ws_ticket(self.db, session.id, raw))

    def test_background_jobs_are_idempotent(self):
        session = self.create_game()
        first = enqueue_job(
            self.db,
            module="ai_board_game",
            job_type="board.narrate",
            session_id=session.id,
            actor_id=self.owner.id,
            idempotency_key="narrate-event-1",
            input_ref={"event_sequence": 1},
        )
        second = enqueue_job(
            self.db,
            module="ai_board_game",
            job_type="board.narrate",
            session_id=session.id,
            actor_id=self.owner.id,
            idempotency_key="narrate-event-1",
            input_ref={"event_sequence": 1},
        )
        self.db.commit()
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.query(BackgroundJob).count(), 1)


if __name__ == "__main__":
    unittest.main()
