from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.models import Server, ServerMember, User
from app.database import Base
from app.modules.hidden_role_game.content import SCENARIOS
from app.modules.hidden_role_game.models import HiddenRoleAssignment, HiddenRoleDeduction, HiddenRoleVote
from app.modules.hidden_role_game.schemas import HiddenGameCreate
from app.modules.hidden_role_game.service import _assignment, create_game, game_view, submit_claim, submit_deduction, submit_vote
from app.modules.hidden_role_game.worker import process_hidden_recap_job
from app.platform.models import AiRun, ExperienceEvent
from app.platform.worker import process_one as process_platform_one


class HiddenRoleGameTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.players = [User(username=f"seal-{i}", email=f"seal-{i}@test", hashed_password="x") for i in range(3)]
        self.outsider = User(username="seal-out", email="seal-out@test", hashed_password="x")
        self.db.add_all([*self.players, self.outsider]); self.db.flush()
        self.server = Server(name="Three Seals", owner_id=self.players[0].id); self.db.add(self.server); self.db.flush()
        self.db.add_all([ServerMember(server_id=self.server.id, user_id=user.id) for user in self.players]); self.db.commit()
        self.session = create_game(self.db, server_id=self.server.id, actor=self.players[0], payload=HiddenGameCreate(player_ids=[user.id for user in self.players]), idempotency_key="three-seals-001")

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def _claim_all(self):
        for user in self.players:
            view = game_view(self.db, session_id=self.session.id, actor=user)
            submit_claim(self.db, session_id=self.session.id, actor=user, subject=view["crisis"]["options"][0]["id"], proposition="RISK_HIGH", flavor="Bu seçenek bana güvenli görünmüyor.", token=view["legal_action"]["token"], revision=view["revision"])

    def _vote_all_safe(self):
        round_number = game_view(self.db, session_id=self.session.id, actor=self.players[0])["round"]
        safe = SCENARIOS[round_number - 1]["safe"]
        for user in self.players:
            view = game_view(self.db, session_id=self.session.id, actor=user)
            submit_vote(self.db, session_id=self.session.id, actor=user, option_id=safe, token=view["legal_action"]["token"], revision=view["revision"])

    def test_assignments_and_votes_are_encrypted_and_self_scoped(self):
        first = game_view(self.db, session_id=self.session.id, actor=self.players[0])
        second = game_view(self.db, session_id=self.session.id, actor=self.players[1])
        self.assertNotEqual(first["own_private"]["office"], second["own_private"]["office"])
        assignment_blob = self.db.query(HiddenRoleAssignment).filter_by(user_id=self.players[0].id).one().encrypted_payload
        self.assertNotIn(first["own_private"]["office"].encode(), assignment_blob)
        with self.assertRaises(HTTPException):
            game_view(self.db, session_id=self.session.id, actor=self.outsider)
        self._claim_all()
        first = game_view(self.db, session_id=self.session.id, actor=self.players[0])
        submit_vote(self.db, session_id=self.session.id, actor=self.players[0], option_id="A", token=first["legal_action"]["token"], revision=first["revision"])
        public_other = game_view(self.db, session_id=self.session.id, actor=self.players[1])
        self.assertEqual(public_other["submitted_vote_count"], 1)
        self.assertIsNone(public_other["own_private"]["own_vote"])
        self.assertNotIn(b'"A"', self.db.query(HiddenRoleVote).one().encrypted_payload)

    def test_four_crises_final_deduction_reveal_and_ai_recap(self):
        for _ in range(4):
            self._claim_all(); self._vote_all_safe()
        view = game_view(self.db, session_id=self.session.id, actor=self.players[0])
        self.assertEqual(view["phase"], "FINAL_DEDUCTION")
        assignments = {str(user.id): _assignment(self.db, self.session.id, user.id) for user in self.players}
        for user in self.players:
            view = game_view(self.db, session_id=self.session.id, actor=user)
            others = [str(other.id) for other in self.players if other.id != user.id]
            submit_deduction(self.db, session_id=self.session.id, actor=user, offices={other: assignments[other]["office"] for other in others}, mandates={other: assignments[other]["mandate"] for other in others}, token=view["legal_action"]["token"], revision=view["revision"])
        final = game_view(self.db, session_id=self.session.id, actor=self.players[0])
        self.assertEqual(final["status"], "COMPLETED")
        self.assertIn("assignments", final["result"])
        def fake_chat(*_args, **_kwargs):
            return {"model": "test", "message": {"content": json.dumps({"recap": "Üç Mühür çözüldü; güvenli kararlar istikrarı korudu."}, ensure_ascii=False)}}
        handler = lambda job_id: process_hidden_recap_job(job_id, chat=fake_chat)
        with patch("app.platform.worker.SessionLocal", self.Session), patch("app.modules.hidden_role_game.worker.SessionLocal", self.Session):
            self.assertTrue(process_platform_one(handlers={("hidden_role_game", "hidden.end_recap"): handler}))
        self.assertEqual(self.db.query(AiRun).count(), 1)
        self.assertEqual(self.db.query(ExperienceEvent).filter_by(event_type="hidden.recap_ready").count(), 1)


class HiddenRoleTwoPlayerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.players = [User(username=f"duo-{i}", email=f"duo-{i}@test", hashed_password="x") for i in range(2)]
        self.db.add_all(self.players); self.db.flush()
        self.server = Server(name="Duo Seals", owner_id=self.players[0].id); self.db.add(self.server); self.db.flush()
        self.db.add_all([ServerMember(server_id=self.server.id, user_id=user.id) for user in self.players]); self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def _game(self, *, ai_players: int, key: str):
        return create_game(self.db, server_id=self.server.id, actor=self.players[0], payload=HiddenGameCreate(player_ids=[user.id for user in self.players], ai_players=ai_players), idempotency_key=key)

    def _play_round(self, session, option_id=None):
        for user in self.players:
            view = game_view(self.db, session_id=session.id, actor=user)
            submit_claim(self.db, session_id=session.id, actor=user, subject=view["crisis"]["options"][0]["id"], proposition="RISK_HIGH", flavor="Şüpheliyim.", token=view["legal_action"]["token"], revision=view["revision"])
        round_number = game_view(self.db, session_id=session.id, actor=self.players[0])["round"]
        safe = option_id or SCENARIOS[round_number - 1]["safe"]
        for user in self.players:
            view = game_view(self.db, session_id=session.id, actor=user)
            submit_vote(self.db, session_id=session.id, actor=user, option_id=safe, token=view["legal_action"]["token"], revision=view["revision"])

    def _deduce_all(self, session):
        for user in self.players:
            view = game_view(self.db, session_id=session.id, actor=user)
            others = [item["key"] for item in view["players"] if item["key"] != str(user.id)]
            submit_deduction(self.db, session_id=session.id, actor=user, offices={key: "SENTINEL" for key in others}, mandates={key: "SEAL" for key in others}, token=view["legal_action"]["token"], revision=view["revision"])

    def test_two_players_complete_a_game_without_ai(self):
        session = self._game(ai_players=0, key="duo-seals-001")
        view = game_view(self.db, session_id=session.id, actor=self.players[0])
        self.assertEqual(view["human_player_count"], 2)
        self.assertEqual(len(view["players"]), 2)
        for _ in range(4):
            self._play_round(session)
        self.assertEqual(game_view(self.db, session_id=session.id, actor=self.players[0])["phase"], "FINAL_DEDUCTION")
        self._deduce_all(session)
        final = game_view(self.db, session_id=session.id, actor=self.players[0])
        self.assertEqual(final["status"], "COMPLETED")
        self.assertEqual(len(final["result"]["scores"]), 2)

    def test_two_players_disagreeing_falls_back_to_the_arbiter_seat(self):
        """İki koltukta çoğunluk ancak ikisi de aynı seçeneği seçerse oluşur."""
        session = self._game(ai_players=0, key="duo-seals-tie")
        for user in self.players:
            view = game_view(self.db, session_id=session.id, actor=user)
            submit_claim(self.db, session_id=session.id, actor=user, subject="A", proposition="RISK_HIGH", flavor="", token=view["legal_action"]["token"], revision=view["revision"])
        for index, user in enumerate(self.players):
            view = game_view(self.db, session_id=session.id, actor=user)
            submit_vote(self.db, session_id=session.id, actor=user, option_id="A" if index == 0 else "B", token=view["legal_action"]["token"], revision=view["revision"])
        result = game_view(self.db, session_id=session.id, actor=self.players[0])["round_results"][0]
        # 1. tur hakemi koltuk 0'dır; beraberlikte onun oyu geçerli olur.
        self.assertEqual(result["selected_option_id"], "A")

    def test_ai_seat_claims_votes_and_is_scored_without_table_rows(self):
        session = self._game(ai_players=1, key="duo-seals-ai")
        view = game_view(self.db, session_id=session.id, actor=self.players[0])
        self.assertEqual(len(view["players"]), 3)
        self.assertEqual(view["human_player_count"], 2)
        ai_player = next(item for item in view["players"] if item["ai"])
        self.assertEqual(ai_player["key"], "ai:2")
        self.assertIsNone(ai_player["user_id"])
        # AI'ın gizli ataması hidden_role_assignments tablosunda satır tutmaz.
        self.assertEqual(self.db.query(HiddenRoleAssignment).filter_by(session_id=session.id).count(), 2)
        for _ in range(4):
            self._play_round(session)
        view = game_view(self.db, session_id=session.id, actor=self.players[0])
        self.assertEqual(view["phase"], "FINAL_DEDUCTION")
        # AI koltuğu her turda iddiasını açar ve oyu tabloya yazılmaz.
        self.assertEqual(self.db.query(HiddenRoleVote).filter_by(session_id=session.id).count(), 8)
        self._deduce_all(session)
        final = game_view(self.db, session_id=session.id, actor=self.players[0])
        self.assertEqual(final["status"], "COMPLETED")
        self.assertEqual(len(final["result"]["scores"]), 3)
        self.assertTrue(any(score["ai"] for score in final["result"]["scores"]))
        self.assertEqual(self.db.query(HiddenRoleDeduction).filter_by(session_id=session.id).count(), 2)


if __name__ == "__main__":
    unittest.main()
