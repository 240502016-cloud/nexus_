from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.models import Server, ServerMember, User
from app.database import Base
from app.modules.meme_generator.models import (
    GeneratedMeme,
    MemeCaptionCandidate,
    MemeFeedback,
    MemeGeneration,
)
from app.modules.meme_generator.schemas import (
    MemeEventCreate,
    MemeFact,
    MemeGameContext,
    MemeGenerationCreate,
    MemeFeedbackCreate,
    MemePreferenceUpdate,
    RenderMemeRequest,
)
from app.modules.meme_generator.service import (
    create_generation,
    delete_meme,
    render_generation,
    resolve_asset,
    submit_feedback,
    update_preference,
)
from app.modules.meme_generator.worker import process_meme_job
from app.modules.party_lore.models import LoreUsage
from app.modules.party_lore.schemas import LoreCandidateCreate
from app.modules.party_lore.service import create_candidate, review_candidate
from app.platform.models import AiRun, BackgroundJob, MediaAsset, utcnow
from app.platform.worker import process_one as process_platform_one


class MemeGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.owner = User(username="meme-owner", email="meme-owner@test", hashed_password="x")
        self.friend = User(username="meme-friend", email="meme-friend@test", hashed_password="x")
        self.third = User(username="meme-third", email="meme-third@test", hashed_password="x")
        self.outsider = User(username="meme-out", email="meme-out@test", hashed_password="x")
        self.db.add_all([self.owner, self.friend, self.third, self.outsider])
        self.db.flush()
        self.server = Server(name="Meme Server", owner_id=self.owner.id)
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
        self.media_dir = tempfile.TemporaryDirectory()
        self.media_patch = patch.object(settings, "generated_media_dir", self.media_dir.name)
        self.media_patch.start()

    def tearDown(self):
        self.media_patch.stop()
        self.media_dir.cleanup()
        self.db.close()
        self.engine.dispose()

    def payload(
        self,
        *,
        event_id: str = "meme-event-001",
        confidence: float = 0.99,
        target_ids: list[int] | None = None,
    ) -> MemeGenerationCreate:
        return MemeGenerationCreate(
            event=MemeEventCreate(
                schema_version="1.0",
                event_id=event_id,
                server_id=self.server.id,
                source="MANUAL",
                occurred_at=utcnow(),
                moment_type="PREPARATION",
                actor_player_ids=[self.owner.id],
                target_player_ids=target_ids if target_ids is not None else [self.owner.id],
                game=MemeGameContext(game_key="survival", match_id="match-1"),
                summary="Owner on dakika eşya topladıktan sonra ilk engelde hepsini kaybetti.",
                setup="On dakika boyunca eşya topladı.",
                payoff="İlk engelde bütün eşyaları kaybetti.",
                importance=0.95,
                confidence=confidence,
                facts=[MemeFact(key="durationSeconds", value=600)],
            ),
            desired_harshness=1,
        )

    def create(self, **kwargs) -> MemeGeneration:
        return create_generation(
            self.db,
            server_id=self.server.id,
            actor=self.owner,
            payload=self.payload(**kwargs),
            idempotency_key="meme-request-001",
        )

    def fake_chat(self, _model, messages, **_kwargs):
        prompt = messages[-1]["content"]
        self.assertIn("allowedTemplateKeys", prompt)
        return {
            "model": "test-meme-model",
            "prompt_eval_count": 210,
            "eval_count": 80,
            "message": {
                "content": json.dumps(
                    {
                        "candidates": [
                            {
                                "templateKey": "expectation_reality",
                                "captions": {"TITLE": "On dakika hazırlık", "SUBTITLE": "İlk engelde ekonomi kapandı"},
                                "targetPlayerId": self.owner.id,
                                "loreReferences": [],
                                "harshness": 1,
                                "qualityScore": 0.91,
                            },
                            {
                                "templateKey": "expectation_reality",
                                "captions": {"TITLE": "Envanter hazır", "SUBTITLE": "Macera on saniye sürdü"},
                                "targetPlayerId": self.owner.id,
                                "loreReferences": [],
                                "harshness": 1,
                                "qualityScore": 0.86,
                            },
                            {
                                "templateKey": "expectation_reality",
                                "captions": {"TITLE": "Hazırlık tamam", "SUBTITLE": "İlk engel teşekkür etti"},
                                "targetPlayerId": self.owner.id,
                                "loreReferences": [],
                                "harshness": 1,
                                "qualityScore": 0.8,
                            },
                        ]
                    },
                    ensure_ascii=False,
                )
            },
        }

    def run_worker(self, chat=None):
        handler = lambda job_id: process_meme_job(job_id, chat=chat or self.fake_chat)
        with patch("app.platform.worker.SessionLocal", self.Session), patch(
            "app.modules.meme_generator.worker.SessionLocal", self.Session
        ):
            return process_platform_one(handlers={("meme_generator", "meme.caption"): handler})

    def test_generation_is_idempotent_and_low_confidence_never_queues(self):
        generation = self.create()
        repeated = self.create()
        self.assertEqual(generation.id, repeated.id)
        self.assertEqual(generation.status, "queued")
        self.assertEqual(self.db.query(BackgroundJob).count(), 1)

        filtered = create_generation(
            self.db,
            server_id=self.server.id,
            actor=self.owner,
            payload=self.payload(event_id="meme-event-low", confidence=0.4),
            idempotency_key="meme-request-low",
        )
        self.assertEqual(filtered.status, "filtered")
        self.assertEqual(filtered.reasoning_code, "LOW_CONFIDENCE")
        self.assertEqual(self.db.query(BackgroundJob).count(), 1)

    def test_player_target_preference_is_a_hard_gate(self):
        update_preference(
            self.db,
            server_id=self.server.id,
            actor=self.friend,
            payload=MemePreferenceUpdate(allow_as_target=False),
        )
        with self.assertRaises(HTTPException) as rejected:
            self.create(event_id="meme-event-target", target_ids=[self.friend.id])
        self.assertEqual(rejected.exception.status_code, 409)

    def test_worker_stores_three_allowlisted_candidates_and_ai_run(self):
        generation = self.create()
        self.assertTrue(self.run_worker())
        self.db.expire_all()
        generation = self.db.get(MemeGeneration, generation.id)
        self.assertEqual(generation.status, "candidates_ready")
        self.assertEqual(self.db.query(MemeCaptionCandidate).count(), 3)
        self.assertEqual(self.db.query(AiRun).one().logical_profile, "meme-text")
        self.assertEqual(self.db.query(BackgroundJob).one().status, "succeeded")

    def test_invalid_model_target_fails_closed_without_candidates(self):
        generation = self.create()

        def invalid_chat(*args, **kwargs):
            response = self.fake_chat(*args, **kwargs)
            payload = json.loads(response["message"]["content"])
            payload["candidates"][0]["targetPlayerId"] = self.outsider.id
            response["message"]["content"] = json.dumps(payload)
            return response

        self.assertTrue(self.run_worker(invalid_chat))
        self.db.expire_all()
        generation = self.db.get(MemeGeneration, generation.id)
        self.assertEqual(generation.status, "failed")
        self.assertEqual(generation.error_code, "TARGET_NOT_ALLOWED")
        self.assertEqual(self.db.query(MemeCaptionCandidate).count(), 0)

    def test_render_creates_private_media_feedback_and_owner_delete(self):
        generation = self.create()
        self.run_worker()
        self.db.expire_all()
        candidate = self.db.query(MemeCaptionCandidate).order_by(MemeCaptionCandidate.rank).first()
        meme = render_generation(
            self.db,
            generation_id=generation.id,
            actor=self.owner,
            payload=RenderMemeRequest(
                candidate_id=candidate.id,
                caption_overrides={"SUBTITLE": "İlk engel bütün planı kapattı"},
            ),
        )
        asset, path = resolve_asset(self.db, asset_id=meme.asset_id, actor=self.friend)
        self.assertEqual(path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(asset.kind, "generated_meme")
        with self.assertRaises(HTTPException) as forbidden:
            resolve_asset(self.db, asset_id=meme.asset_id, actor=self.outsider)
        self.assertEqual(forbidden.exception.status_code, 403)

        feedback = submit_feedback(
            self.db,
            meme_id=meme.id,
            actor=self.friend,
            payload=MemeFeedbackCreate(feedback_type="FUNNY"),
        )
        self.assertEqual(feedback.feedback_type, "FUNNY")
        self.assertEqual(self.db.query(MemeFeedback).count(), 1)
        with self.assertRaises(HTTPException):
            delete_meme(self.db, meme_id=meme.id, actor=self.friend)
        delete_meme(self.db, meme_id=meme.id, actor=self.owner)
        self.assertFalse(path.exists())
        self.assertEqual(self.db.get(MediaAsset, asset.id).status, "deleted")

    def test_manual_caption_override_cannot_bypass_safety(self):
        generation = self.create()
        self.run_worker()
        self.db.expire_all()
        candidate = self.db.query(MemeCaptionCandidate).filter(MemeCaptionCandidate.rank == 1).one()
        with self.assertRaises(HTTPException) as unsafe:
            render_generation(
                self.db,
                generation_id=generation.id,
                actor=self.owner,
                payload=RenderMemeRequest(
                    candidate_id=candidate.id,
                    caption_overrides={"SUBTITLE": "Tam bir aptal hareketi"},
                ),
            )
        self.assertEqual(unsafe.exception.status_code, 422)
        self.assertEqual(self.db.query(GeneratedMeme).count(), 0)

    def test_party_lore_is_recorded_only_after_selected_candidate_is_rendered(self):
        lore_candidate = create_candidate(
            self.db,
            server_id=self.server.id,
            actor=self.owner,
            payload=LoreCandidateCreate(
                title="On dakikalık hazırlık",
                summary="Owner uzun hazırlıktan sonra ilk engelde bütün eşyaları kaybetti.",
                participant_ids=[self.owner.id],
                allowed_modules=["meme_generator"],
            ),
            idempotency_key="meme-lore-001",
        )
        review_candidate(
            self.db,
            candidate_id=lore_candidate.id,
            actor=self.owner,
            decision="approved",
        )
        lore_id = lore_candidate.entry.id
        generation = self.create()

        def lore_chat(*args, **kwargs):
            response = self.fake_chat(*args, **kwargs)
            payload = json.loads(response["message"]["content"])
            payload["candidates"][0]["loreReferences"] = [lore_id]
            response["message"]["content"] = json.dumps(payload, ensure_ascii=False)
            return response

        self.run_worker(lore_chat)
        self.assertEqual(self.db.query(LoreUsage).count(), 0)
        self.db.expire_all()
        selected = self.db.query(MemeCaptionCandidate).filter(MemeCaptionCandidate.rank == 1).one()
        render_generation(
            self.db,
            generation_id=generation.id,
            actor=self.owner,
            payload=RenderMemeRequest(candidate_id=selected.id),
        )
        self.assertEqual(self.db.query(LoreUsage).count(), 1)
        self.assertEqual(self.db.query(GeneratedMeme).count(), 1)


if __name__ == "__main__":
    unittest.main()
