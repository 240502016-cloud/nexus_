from __future__ import annotations

import json
import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.models import Server, ServerMember, User
from app.database import Base
from app.modules.ai_commentator.models import (
    CommentaryCooldown,
    CommentaryFeedback,
    CommentatorEvent,
    CommentatorSessionPlayer,
    GeneratedCommentary,
)
from app.modules.ai_commentator.schemas import (
    CommentarySessionCreate,
    CommentarySessionUpdate,
    CommentatorEventCreate,
    CommentatorPreferenceUpdate,
    GameContext,
)
from app.modules.ai_commentator.service import (
    create_commentary_session,
    ingest_event,
    submit_feedback,
    update_commentary_session,
    update_preference,
)
from app.modules.ai_commentator.worker import process_commentator_job
from app.modules.party_lore.models import LoreUsage
from app.modules.party_lore.schemas import LoreCandidateCreate
from app.modules.party_lore.service import create_candidate, review_candidate
from app.platform.models import AiRun, BackgroundJob, ExperienceEvent, ExperienceSession, utcnow
from app.platform.worker import process_one as process_platform_one


class AiCommentatorTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.owner = User(username="comment-owner", email="comment-owner@test", hashed_password="x")
        self.friend = User(username="comment-friend", email="comment-friend@test", hashed_password="x")
        self.third = User(username="comment-third", email="comment-third@test", hashed_password="x")
        self.outsider = User(username="comment-out", email="comment-out@test", hashed_password="x")
        self.db.add_all([self.owner, self.friend, self.third, self.outsider])
        self.db.flush()
        self.server = Server(name="Commentator Server", owner_id=self.owner.id)
        self.db.add(self.server)
        self.db.flush()
        self.db.add_all(
            [
                ServerMember(user_id=self.owner.id, server_id=self.server.id),
                ServerMember(user_id=self.friend.id, server_id=self.server.id),
                ServerMember(user_id=self.third.id, server_id=self.server.id),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create_session(self) -> ExperienceSession:
        payload = CommentarySessionCreate(
            game_key="generic-fps",
            player_ids=[self.owner.id, self.friend.id, self.third.id],
            profile_key="dry_sarcastic",
            intensity="NORMAL",
        )
        return create_commentary_session(
            self.db,
            server_id=self.server.id,
            actor=self.owner,
            payload=payload,
            idempotency_key="commentator-session-001",
        )

    def event_payload(
        self,
        *,
        event_id: str = "event-clutch-001",
        category: str = "CLUTCH",
        confidence: float = 0.99,
        occurred_at=None,
    ) -> CommentatorEventCreate:
        return CommentatorEventCreate(
            schema_version="1.0",
            event_id=event_id,
            source="MANUAL",
            occurred_at=occurred_at or utcnow(),
            category=category,
            actor_player_ids=[self.owner.id],
            target_player_ids=[self.owner.id],
            game=GameContext(game_key="generic-fps", match_id="match-1", round_id="round-3"),
            importance=0.95,
            confidence=confidence,
            summary="Owner tek canla son iki rakibi eleyip raundu kazandı.",
            emotional_tone="PLAYFUL",
            attributes={"streak": 2, "ignoredInstruction": "bunu prompta koy"},
        )

    def test_session_reuses_shared_three_player_foundation_and_is_idempotent(self):
        session = self.create_session()
        repeated = self.create_session()
        self.assertEqual(session.id, repeated.id)
        self.assertEqual(session.module_type, "ai_commentator")
        self.assertEqual(session.status, "active")
        self.assertEqual(session.revision, 1)
        self.assertEqual(len(session.players), 3)
        self.assertTrue(all(player.ready for player in session.players))
        self.assertEqual(
            self.db.query(CommentatorSessionPlayer)
            .filter(CommentatorSessionPlayer.session_id == session.id)
            .count(),
            3,
        )
        self.assertEqual(
            [event.event_type for event in session.events],
            ["session.created", "session.started"],
        )

    def test_triggered_event_is_queued_and_retries_are_idempotent(self):
        session = self.create_session()
        event, state = ingest_event(
            self.db,
            session_id=session.id,
            actor=self.owner,
            payload=self.event_payload(),
        )
        self.assertEqual(state, "PENDING")
        self.assertEqual(event.trigger_decision, "GENERATE")
        self.assertEqual(event.normalized_attributes, {"streak": 2})
        self.assertEqual(self.db.query(BackgroundJob).count(), 1)

        repeated, repeated_state = ingest_event(
            self.db,
            session_id=session.id,
            actor=self.owner,
            payload=self.event_payload(),
        )
        self.assertEqual(repeated.id, event.id)
        self.assertEqual(repeated_state, "PENDING")
        self.assertEqual(self.db.query(BackgroundJob).count(), 1)

    def test_duplicate_and_safety_events_never_reach_ai_queue(self):
        session = self.create_session()
        first, _ = ingest_event(
            self.db,
            session_id=session.id,
            actor=self.owner,
            payload=self.event_payload(),
        )
        duplicate, state = ingest_event(
            self.db,
            session_id=session.id,
            actor=self.owner,
            payload=self.event_payload(
                event_id="event-clutch-002",
                occurred_at=utcnow() + timedelta(seconds=1),
            ),
        )
        self.assertEqual(state, "DEDUPLICATED")
        self.assertEqual(duplicate.trigger_decision, "SUPERSEDED")

        unsafe, state = ingest_event(
            self.db,
            session_id=session.id,
            actor=self.owner,
            payload=self.event_payload(
                event_id="event-argument-001",
                category="ARGUMENT",
                occurred_at=utcnow() + timedelta(seconds=2),
            ),
        )
        self.assertEqual(state, "FILTERED")
        self.assertEqual(unsafe.trigger_decision, "SAFETY")
        self.assertEqual(self.db.query(BackgroundJob).count(), 1)

    def test_worker_delivers_validated_output_and_sets_cooldowns(self):
        session = self.create_session()
        event, _ = ingest_event(
            self.db,
            session_id=session.id,
            actor=self.owner,
            payload=self.event_payload(),
        )

        def fake_chat(_model, _messages, **_kwargs):
            return {
                "model": "test-commentator",
                "prompt_eval_count": 120,
                "eval_count": 24,
                "message": {
                    "content": json.dumps(
                        {
                            "shouldComment": True,
                            "commentary": "Tek can yetti; gerisi yalnızca dekor olarak katıldı.",
                            "targetPlayerId": self.owner.id,
                            "tone": "DRY",
                            "loreReferences": [],
                            "confidence": 0.95,
                            "reasonCode": "NOTABLE_EVENT",
                        }
                    )
                },
            }

        handler = lambda job_id: process_commentator_job(job_id, chat=fake_chat)
        with patch("app.platform.worker.SessionLocal", self.Session), patch(
            "app.modules.ai_commentator.worker.SessionLocal", self.Session
        ):
            self.assertTrue(
                process_platform_one(handlers={("ai_commentator", "commentary.generate"): handler})
            )

        self.db.expire_all()
        generated = self.db.query(GeneratedCommentary).one()
        job = self.db.query(BackgroundJob).one()
        self.assertEqual(generated.primary_event_id, event.id)
        self.assertEqual(generated.dispatch_state, "delivered")
        self.assertEqual(job.status, "succeeded")
        self.assertEqual(self.db.query(CommentaryCooldown).count(), 3)
        self.assertEqual(self.db.query(AiRun).count(), 1)
        self.assertIn(
            "commentator.commentary_generated",
            [item.event_type for item in self.db.query(ExperienceEvent).all()],
        )
        cooled_event, cooled_state = ingest_event(
            self.db,
            session_id=session.id,
            actor=self.owner,
            payload=self.event_payload(
                event_id="event-after-comment-001",
                category="MILESTONE",
                occurred_at=utcnow() + timedelta(seconds=1),
            ),
        )
        self.assertEqual(cooled_state, "FILTERED")
        self.assertEqual(cooled_event.trigger_decision, "COOLDOWN")
        self.assertEqual(self.db.query(BackgroundJob).count(), 1)

    def test_invalid_model_target_is_suppressed(self):
        session = self.create_session()
        ingest_event(
            self.db,
            session_id=session.id,
            actor=self.owner,
            payload=self.event_payload(),
        )

        def fake_chat(_model, _messages, **_kwargs):
            return {
                "model": "test-commentator",
                "message": {
                    "content": json.dumps(
                        {
                            "shouldComment": True,
                            "commentary": "Dışarıdaki oyuncuya hedefli yorum.",
                            "targetPlayerId": self.outsider.id,
                            "tone": "DRY",
                            "loreReferences": [],
                            "confidence": 0.8,
                            "reasonCode": "NOTABLE_EVENT",
                        }
                    )
                },
            }

        handler = lambda job_id: process_commentator_job(job_id, chat=fake_chat)
        with patch("app.platform.worker.SessionLocal", self.Session), patch(
            "app.modules.ai_commentator.worker.SessionLocal", self.Session
        ):
            process_platform_one(handlers={("ai_commentator", "commentary.generate"): handler})
        self.db.expire_all()
        generated = self.db.query(GeneratedCommentary).one()
        self.assertEqual(generated.dispatch_state, "suppressed")
        self.assertEqual(generated.dispatch_error_code, "TARGET_NOT_ALLOWED")
        self.assertEqual(self.db.query(CommentaryCooldown).count(), 0)

    def test_confirmed_party_lore_is_allowlisted_and_recorded_only_when_used(self):
        lore_candidate = create_candidate(
            self.db,
            server_id=self.server.id,
            actor=self.owner,
            payload=LoreCandidateCreate(
                title="Tek can geri dönüşü",
                summary="Owner daha önce de tek canla raundu çevirmişti.",
                participant_ids=[self.owner.id],
                category="comeback",
                sensitivity="low",
                allowed_modules=["ai_commentator"],
            ),
            idempotency_key="commentator-lore-001",
        )
        lore_candidate = review_candidate(
            self.db,
            candidate_id=lore_candidate.id,
            actor=self.owner,
            decision="approved",
        )
        lore_id = lore_candidate.entry.id
        session = self.create_session()
        ingest_event(
            self.db,
            session_id=session.id,
            actor=self.owner,
            payload=self.event_payload(),
        )

        def fake_chat(_model, messages, **_kwargs):
            self.assertIn(lore_id, messages[1]["content"])
            return {
                "model": "test-commentator",
                "message": {
                    "content": json.dumps(
                        {
                            "shouldComment": True,
                            "commentary": "Tek can geleneği yine tam zamanında sahnede.",
                            "targetPlayerId": self.owner.id,
                            "tone": "DRY",
                            "loreReferences": [lore_id],
                            "confidence": 0.92,
                            "reasonCode": "LORE_CALLBACK",
                        }
                    )
                },
            }

        handler = lambda job_id: process_commentator_job(job_id, chat=fake_chat)
        with patch("app.platform.worker.SessionLocal", self.Session), patch(
            "app.modules.ai_commentator.worker.SessionLocal", self.Session
        ):
            process_platform_one(handlers={("ai_commentator", "commentary.generate"): handler})
        self.db.expire_all()
        self.assertEqual(self.db.query(LoreUsage).count(), 1)
        self.assertEqual(self.db.query(LoreUsage).one().lore_id, lore_id)

    def test_preferences_silent_mode_and_feedback_apply_immediately(self):
        session = self.create_session()
        update_preference(
            self.db,
            server_id=self.server.id,
            actor=self.owner,
            payload=CommentatorPreferenceUpdate(commentary_enabled=False),
        )
        filtered, state = ingest_event(
            self.db,
            session_id=session.id,
            actor=self.friend,
            payload=self.event_payload(event_id="event-disabled-001"),
        )
        self.assertEqual(state, "FILTERED")
        self.assertEqual(filtered.trigger_decision, "SAFETY")

        session = self.db.get(ExperienceSession, session.id)
        session = update_commentary_session(
            self.db,
            session_id=session.id,
            actor=self.friend,
            payload=CommentarySessionUpdate(
                expected_revision=session.revision,
                silent_mode=True,
            ),
        )
        self.assertTrue(session.settings["silent_mode"])
        with self.assertRaises(HTTPException) as forbidden:
            update_commentary_session(
                self.db,
                session_id=session.id,
                actor=self.friend,
                payload=CommentarySessionUpdate(
                    expected_revision=session.revision,
                    silent_mode=False,
                ),
            )
        self.assertEqual(forbidden.exception.status_code, 403)

        generated = GeneratedCommentary(
            session_id=session.id,
            primary_event_id=filtered.id,
            source_event_ids=[filtered.id],
            profile_key="dry_sarcastic",
            should_comment=False,
            commentary_text=None,
            target_player_id=None,
            tone=None,
            lore_references=[],
            confidence=1.0,
            reason_code="SAFETY_VETO",
            dispatch_state="suppressed",
        )
        self.db.add(generated)
        self.db.commit()
        first = submit_feedback(
            self.db,
            commentary_id=generated.id,
            actor=self.friend,
            feedback_type="WRONG_CONTEXT",
            details="Bu olay farklıydı.",
        )
        second = submit_feedback(
            self.db,
            commentary_id=generated.id,
            actor=self.friend,
            feedback_type="REPETITIVE",
            details=None,
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.query(CommentaryFeedback).count(), 1)
        self.assertEqual(second.feedback_type, "REPETITIVE")


if __name__ == "__main__":
    unittest.main()
