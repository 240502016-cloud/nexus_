from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.models import Server, ServerMember, User
from app.database import Base
from app.modules.shared_story.engine import ai_spotlight_choice, initial_state
from app.modules.shared_story.models import StoryCharacter, StoryChoiceVote, StoryState
from app.modules.shared_story.schemas import StoryCreate, StorySafetyUpdate
from app.modules.shared_story.service import create_story, get_safety_profile, story_view, submit_action, submit_vote, update_safety_profile
from app.modules.shared_story.worker import process_story_job
from app.platform.models import AiRun, BackgroundJob, ExperienceEvent
from app.platform.worker import process_one as process_platform_one


class SharedStoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.players = [User(username=f"story-{i}", email=f"story-{i}@test", hashed_password="x") for i in range(3)]
        self.outsider = User(username="story-out", email="story-out@test", hashed_password="x")
        self.db.add_all([*self.players, self.outsider]); self.db.flush()
        self.server = Server(name="Story", owner_id=self.players[0].id); self.db.add(self.server); self.db.flush()
        self.db.add_all([ServerMember(server_id=self.server.id, user_id=user.id) for user in self.players]); self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def _story(self):
        return create_story(self.db, server_id=self.server.id, actor=self.players[0], payload=StoryCreate(player_ids=[user.id for user in self.players], theme="FANTASY", length="SHORT"), idempotency_key="shared-story-001")

    def _play_chapter(self, session):
        for _ in range(3):
            public = story_view(self.db, session_id=session.id, actor=self.players[0])
            active = next(user for user in self.players if user.id == public["active_user_id"])
            view = story_view(self.db, session_id=session.id, actor=active)
            submit_action(self.db, session_id=session.id, actor=active, action_id=view["spotlight_choices"][0]["id"], token=view["action_token"], revision=view["revision"], idempotency_key=f"story-action-{view['chapter']}-{active.id}")
        for user in self.players:
            view = story_view(self.db, session_id=session.id, actor=user)
            submit_vote(self.db, session_id=session.id, actor=user, choice_id="STABILIZE", token=view["action_token"], revision=view["revision"])

    def test_safety_envelope_uses_most_restrictive_profiles(self):
        update_safety_profile(self.db, server_id=self.server.id, actor=self.players[0], payload=StorySafetyUpdate(horror_level=3, violence_level=2, romance="SOFT", player_conflict="CONTROLLED", betrayal="NPC_ONLY", personal_jokes=True, dark_humor=True))
        update_safety_profile(self.db, server_id=self.server.id, actor=self.players[1], payload=StorySafetyUpdate(horror_level=0, violence_level=0))
        self.assertEqual(get_safety_profile(self.db, server_id=self.server.id, actor=self.players[1]).horror_level, 0)
        session = self._story(); view = story_view(self.db, session_id=session.id, actor=self.players[0])
        self.assertEqual(view["safety_envelope"]["horror_level"], 0)
        self.assertEqual(view["safety_envelope"]["romance"], "OFF")
        self.assertFalse(view["safety_envelope"]["personal_jokes"])

    def test_equal_spotlights_sealed_vote_and_deterministic_ending(self):
        session = self._story()
        self._play_chapter(session)
        self._play_chapter(session)
        final = story_view(self.db, session_id=session.id, actor=self.players[0])
        self.assertEqual(final["status"], "COMPLETED")
        self.assertIsNotNone(final["ending_vector"])
        self.assertTrue(all(character["actions_taken"] == 2 for character in final["characters"]))
        self.assertEqual(self.db.query(StoryState).filter_by(is_current=True).count(), 1)
        first_vote = self.db.query(StoryChoiceVote).first()
        self.assertNotIn(b"STABILIZE", first_vote.encrypted_choice)
        with self.assertRaises(HTTPException): story_view(self.db, session_id=session.id, actor=self.outsider)

    def _two_player_story(self, *, ai_players: int, key: str):
        return create_story(self.db, server_id=self.server.id, actor=self.players[0], payload=StoryCreate(player_ids=[self.players[0].id, self.players[1].id], ai_players=ai_players, theme="FANTASY", length="SHORT"), idempotency_key=key)

    def _play_chapter_with(self, session, humans):
        """İnsan koltuklarını sırayla oynatır; AI koltukları kendiliğinden ilerler."""
        for _ in range(len(humans)):
            public = story_view(self.db, session_id=session.id, actor=humans[0])
            active = next(user for user in humans if user.id == public["active_user_id"])
            view = story_view(self.db, session_id=session.id, actor=active)
            submit_action(self.db, session_id=session.id, actor=active, action_id=view["spotlight_choices"][0]["id"], token=view["action_token"], revision=view["revision"], idempotency_key=f"story-action-{view['chapter']}-{active.id}")
        for user in humans:
            view = story_view(self.db, session_id=session.id, actor=user)
            submit_vote(self.db, session_id=session.id, actor=user, choice_id="STABILIZE", token=view["action_token"], revision=view["revision"])

    def test_two_players_can_finish_a_story_without_ai(self):
        session = self._two_player_story(ai_players=0, key="shared-story-2p")
        humans = self.players[:2]
        view = story_view(self.db, session_id=session.id, actor=humans[0])
        self.assertEqual(view["seat_count"], 2)
        self.assertFalse(view["active_is_ai"])
        self._play_chapter_with(session, humans)
        self._play_chapter_with(session, humans)
        final = story_view(self.db, session_id=session.id, actor=humans[0])
        self.assertEqual(final["status"], "COMPLETED")
        self.assertIsNotNone(final["ending_vector"])
        self.assertEqual(len(final["characters"]), 2)
        self.assertTrue(all(character["actions_taken"] == 2 for character in final["characters"]))

    def test_ai_seat_plays_itself_and_keeps_three_scenes_per_chapter(self):
        session = self._two_player_story(ai_players=1, key="shared-story-2p-ai")
        humans = self.players[:2]
        view = story_view(self.db, session_id=session.id, actor=humans[0])
        self.assertEqual(view["seat_count"], 3)
        ai_character = next(item for item in view["characters"] if item["ai"])
        self.assertIsNone(ai_character["user_id"])
        self.assertEqual(ai_character["seat"], 2)
        # AI karakteri story_characters tablosunda satır tutmaz.
        self.assertEqual(self.db.query(StoryCharacter).filter_by(session_id=session.id).count(), 2)
        self._play_chapter_with(session, humans)
        self._play_chapter_with(session, humans)
        final = story_view(self.db, session_id=session.id, actor=humans[0])
        self.assertEqual(final["status"], "COMPLETED")
        # Üç koltuğun da her bölümde bir sahnesi olur; AI kendi sırasını kendisi oynar.
        self.assertTrue(all(character["actions_taken"] == 2 for character in final["characters"]))
        # AI oyu StoryChoiceVote tablosuna yazılmaz: iki bölüm x iki insan = dört satır.
        self.assertEqual(self.db.query(StoryChoiceVote).filter_by(session_id=session.id).count(), 4)

    def test_ai_choice_is_deterministic_and_needs_no_model(self):
        """AI kararı tohumdan türetilir — AI Gateway kapalıyken oyun kilitlenmemeli."""
        state = initial_state([1, 2], ai_seats=[2], theme="FANTASY", chapter_count=2, safety={})
        seed = b"deterministic-seed"
        first, counter_a = ai_spotlight_choice(state, seed, 0)
        second, counter_b = ai_spotlight_choice(state, seed, 0)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(counter_a, counter_b)
        threatened = {**state, "threat": 5}
        self.assertEqual(ai_spotlight_choice(threatened, seed, 0)[0]["id"], "PROTECT")

    def test_four_seats_are_rejected(self):
        with self.assertRaises(ValueError):
            StoryCreate(player_ids=[user.id for user in self.players], ai_players=1)

    def test_ai_prose_is_async_and_does_not_gate_first_action(self):
        session = self._story(); view = story_view(self.db, session_id=session.id, actor=self.players[0])
        self.assertTrue(view["spotlight_choices"])
        def fake_chat(*_args, **_kwargs): return {"model": "test", "message": {"content": json.dumps({"text": "Yankı Geçidi, üç yolcunun önünde sessizce uyandı."}, ensure_ascii=False)}}
        handler = lambda job_id: process_story_job(job_id, chat=fake_chat)
        with patch("app.platform.worker.SessionLocal", self.Session), patch("app.modules.shared_story.worker.SessionLocal", self.Session):
            self.assertTrue(process_platform_one(handlers={("shared_story", "story.scene_write"): handler}))
        self.assertEqual(self.db.query(AiRun).count(), 1)
        self.assertEqual(self.db.query(ExperienceEvent).filter_by(event_type="story.prose_ready").count(), 1)
        self.assertGreater(self.db.query(BackgroundJob).count(), 0)


if __name__ == "__main__": unittest.main()
