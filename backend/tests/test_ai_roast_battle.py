from __future__ import annotations
import json
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.models import Server, ServerMember, User
from app.database import Base
from app.modules.ai_roast_battle.models import RoastCandidate, RoastRound, RoastVote
from app.modules.ai_roast_battle.schemas import RoastProfileUpdate, RoastSessionCreate
from app.modules.ai_roast_battle.service import create_roast_session, start_next_round, submit_consent, update_profile, vote
from app.modules.ai_roast_battle.worker import process_roast_job
from app.modules.highlight_generator.models import HighlightMarker, HighlightRecording
from app.platform.models import AiRun, BackgroundJob
from app.platform.worker import process_one as process_platform_one


class AiRoastBattleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.players = [User(username=f"roast-{i}", email=f"roast-{i}@test", hashed_password="x") for i in range(3)]
        self.outsider = User(username="roast-out", email="roast-out@test", hashed_password="x")
        self.db.add_all([*self.players, self.outsider]); self.db.flush()
        self.server = Server(name="Roast Server", owner_id=self.players[0].id); self.db.add(self.server); self.db.flush()
        self.db.add_all([ServerMember(user_id=user.id, server_id=self.server.id) for user in self.players]); self.db.commit()
        for user in self.players:
            update_profile(self.db, server_id=self.server.id, actor=user, payload=RoastProfileUpdate(roast_enabled=True, maximum_intensity=1, allowed_topics=["FUNNY_HIGHLIGHTS"]))

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def session(self):
        return create_roast_session(self.db, server_id=self.server.id, actor=self.players[0], payload=RoastSessionCreate(player_ids=[user.id for user in self.players], requested_intensity=1), idempotency_key="roast-session-001")

    def activate(self):
        session = self.session()
        for user in self.players:
            submit_consent(self.db, session_id=session.id, actor=user, decision="READY", consent_version=1)
        self.db.expire_all()
        return self.db.get(type(session), session.id)

    def add_source(self, target: User):
        recording = HighlightRecording(server_id=self.server.id, uploaded_by_id=self.players[0].id, idempotency_key="roast-recording", source_type="MANUAL_UPLOAD", original_filename="x.mp4", declared_mime_type="video/mp4", declared_byte_size=10, duration_ms=60_000, status="ready")
        self.db.add(recording); self.db.flush()
        self.db.add(HighlightMarker(recording_id=recording.id, created_by_id=self.players[0].id, external_marker_id="roast-marker", source_type="MANUAL", offset_ms=30_000, category_hint="COMEDY", participant_player_ids=[target.id], summary="Oyuncu on dakika hazırlandıktan sonra ilk engelde bütün eşyaları kaybetti.", manual_priority=1)); self.db.commit()

    def test_every_player_must_consent_for_themselves_and_revoke_cancels(self):
        session = self.session()
        with self.assertRaises(HTTPException):
            submit_consent(self.db, session_id=session.id, actor=self.outsider, decision="READY", consent_version=1)
        for user in self.players[:2]:
            session = submit_consent(self.db, session_id=session.id, actor=user, decision="READY", consent_version=1)
            self.assertEqual(session.status, "consent_pending")
        session = submit_consent(self.db, session_id=session.id, actor=self.players[2], decision="READY", consent_version=1)
        self.assertEqual(session.status, "active")
        session = submit_consent(self.db, session_id=session.id, actor=self.players[1], decision="REVOKE", consent_version=1)
        self.assertEqual(session.status, "cancelled")

    def test_generate_review_persists_only_selected_safe_roast_and_votes_close_round(self):
        session = self.activate(); self.add_source(self.players[0])
        round_row = start_next_round(self.db, session_id=session.id, actor=self.players[0])
        calls = []
        def fake_chat(_model, messages, **_kwargs):
            calls.append(messages[0]["content"])
            if "metadata" in messages[0]["content"].casefold():
                raise AssertionError("wrong handler")
            if "Bağımsız" in messages[0]["content"]:
                return {"model": "review", "message": {"content": json.dumps({"allowed": True, "selectedIndex": 1, "riskFlags": []})}}
            return {"model": "generate", "message": {"content": json.dumps({"candidates": [
                {"text": "Hazırlık destansıydı; ilk engel daha kısa konuştu.", "angle": "OVERPREPARATION", "intensity": 1, "confidence": .9, "qualityScore": .8},
                {"text": "Envanter hazırdı; macera ilk engelde izin aldı.", "angle": "OVERPREPARATION", "intensity": 1, "confidence": .92, "qualityScore": .9},
                {"text": "On dakikalık plan, engelle kısa bir toplantı yaptı.", "angle": "PLAN_COLLAPSE", "intensity": 1, "confidence": .88, "qualityScore": .82}]}, ensure_ascii=False)}}
        handler = lambda job_id: process_roast_job(job_id, chat=fake_chat)
        with patch("app.platform.worker.SessionLocal", self.Session), patch("app.modules.ai_roast_battle.worker.SessionLocal", self.Session):
            self.assertTrue(process_platform_one(handlers={("ai_roast_battle", "roast.generate_review"): handler}))
        self.db.expire_all(); candidate = self.db.query(RoastCandidate).one(); round_row = self.db.get(RoastRound, round_row.id)
        self.assertEqual(candidate.roast_text, "Envanter hazırdı; macera ilk engelde izin aldı.")
        self.assertEqual(round_row.status, "voting"); self.assertEqual(len(calls), 2); self.assertEqual(self.db.query(AiRun).count(), 2)
        for user, ballot in zip(self.players, ["FUNNY", "OKAY", "PASS"], strict=True):
            vote(self.db, candidate_id=candidate.id, actor=user, vote_type=ballot)
        self.assertEqual(self.db.query(RoastVote).count(), 3); self.assertEqual(self.db.get(RoastRound, round_row.id).status, "completed")

    def test_no_verified_source_skips_without_ai_job(self):
        session = self.activate()
        round_row = start_next_round(self.db, session_id=session.id, actor=self.players[0])
        self.assertEqual(round_row.status, "skipped")
        self.assertEqual(self.db.query(BackgroundJob).count(), 0)

if __name__ == "__main__": unittest.main()
