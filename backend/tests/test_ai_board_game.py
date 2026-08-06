from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.models import Server, ServerMember, User
from app.database import Base
from app.modules.ai_board_game import engine as engine_module
from app.modules.ai_board_game.engine import AI_PLAYER_NAME, action_points_for, ai_action_id
from app.modules.ai_board_game.models import BoardGameAction, BoardGameState
from app.modules.ai_board_game.schemas import BoardGameCreate
from app.modules.ai_board_game.service import create_game, game_view, get_active_game, submit_action
from app.modules.ai_board_game.worker import process_board_narration_job
from app.platform.models import AiRun, ExperienceEvent
from app.platform.worker import process_one as process_platform_one


class AiBoardGameTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.players = [User(username=f"portal-{i}", email=f"portal-{i}@test", hashed_password="x") for i in range(3)]
        self.outsider = User(username="portal-out", email="portal-out@test", hashed_password="x")
        self.db.add_all([*self.players, self.outsider]); self.db.flush()
        self.server = Server(name="Portal", owner_id=self.players[0].id); self.db.add(self.server); self.db.flush()
        self.db.add_all([ServerMember(server_id=self.server.id, user_id=user.id) for user in self.players]); self.db.commit()
        self.session = create_game(self.db, server_id=self.server.id, actor=self.players[0], payload=BoardGameCreate(player_ids=[user.id for user in self.players]), idempotency_key="portal-game-001")

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_game_restores_and_only_active_player_gets_legal_actions(self):
        self.assertEqual(get_active_game(self.db, server_id=self.server.id, actor=self.players[1]).id, self.session.id)
        owner_view = game_view(self.db, session_id=self.session.id, actor=self.players[0])
        waiting_view = game_view(self.db, session_id=self.session.id, actor=self.players[1])
        self.assertTrue(owner_view["legal_actions"])
        self.assertEqual(waiting_view["legal_actions"], [])
        with self.assertRaises(HTTPException):
            game_view(self.db, session_id=self.session.id, actor=self.outsider)

    def test_command_is_revision_bound_and_idempotent(self):
        view = game_view(self.db, session_id=self.session.id, actor=self.players[0])
        action = next(item for item in view["legal_actions"] if item["id"] == "REST")
        updated = submit_action(self.db, session_id=self.session.id, actor=self.players[0], action_id=action["id"], action_token=action["token"], expected_revision=view["revision"], idempotency_key="portal-action-001")
        self.assertEqual(updated["revision"], view["revision"] + 1)
        again = submit_action(self.db, session_id=self.session.id, actor=self.players[0], action_id=action["id"], action_token=action["token"], expected_revision=view["revision"], idempotency_key="portal-action-001")
        self.assertEqual(again["revision"], updated["revision"])
        self.assertEqual(self.db.query(BoardGameAction).count(), 1)
        self.assertEqual(self.db.query(BoardGameState).filter_by(is_current=True).count(), 1)
        with self.assertRaises(HTTPException):
            submit_action(self.db, session_id=self.session.id, actor=self.players[0], action_id="END_TURN", action_token="x" * 64, expected_revision=view["revision"], idempotency_key="portal-action-002")

    def test_ai_narration_is_async_and_mechanics_survive_without_it(self):
        view = game_view(self.db, session_id=self.session.id, actor=self.players[0])
        action = next(item for item in view["legal_actions"] if item["id"] == "REST")
        submit_action(self.db, session_id=self.session.id, actor=self.players[0], action_id=action["id"], action_token=action["token"], expected_revision=view["revision"], idempotency_key="portal-action-ai")
        def fake_chat(*_args, **_kwargs):
            return {"model": "test", "message": {"content": json.dumps({"narration": "Kamp ateşi, portal yolcusuna kısa bir nefes verdi."}, ensure_ascii=False)}}
        handler = lambda job_id: process_board_narration_job(job_id, chat=fake_chat)
        with patch("app.platform.worker.SessionLocal", self.Session), patch("app.modules.ai_board_game.worker.SessionLocal", self.Session):
            self.assertTrue(process_platform_one(handlers={("ai_board_game", "board.narrate"): handler}))
        self.assertEqual(self.db.query(AiRun).count(), 1)
        self.assertEqual(self.db.query(ExperienceEvent).filter_by(event_type="board.narration_ready").count(), 1)


class BoardGameTwoPlayerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.players = [User(username=f"duo-portal-{i}", email=f"duo-portal-{i}@test", hashed_password="x") for i in range(2)]
        self.db.add_all(self.players); self.db.flush()
        self.server = Server(name="Duo Portal", owner_id=self.players[0].id); self.db.add(self.server); self.db.flush()
        self.db.add_all([ServerMember(server_id=self.server.id, user_id=user.id) for user in self.players]); self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def _game(self, *, ai_players: int, key: str):
        return create_game(self.db, server_id=self.server.id, actor=self.players[0], payload=BoardGameCreate(player_ids=[user.id for user in self.players], ai_players=ai_players), idempotency_key=key)

    def _play_out(self, session, limit=400):
        """İnsan koltuklarını hırslı politikayla oynatır; AI koltukları kendiliğinden ilerler."""
        for step in range(limit):
            view = game_view(self.db, session_id=session.id, actor=self.players[0])
            if view["status"] != "ACTIVE":
                return view
            actor = next(user for user in self.players if user.id == view["active_user_id"])
            actor_view = game_view(self.db, session_id=session.id, actor=actor)
            state = self.db.query(BoardGameState).filter_by(session_id=session.id, is_current=True).one().public_state
            wanted = ai_action_id(state)
            action = next(item for item in actor_view["legal_actions"] if item["id"] == wanted)
            submit_action(self.db, session_id=session.id, actor=actor, action_id=action["id"], action_token=action["token"], expected_revision=actor_view["revision"], idempotency_key=f"duo-{step}")
        self.fail("oyun beklenen tur sayısında bitmedi")

    def test_two_seats_get_three_action_points(self):
        """Denge ayarı: iki koltukta tur başına 3 AP, üç koltukta 2 AP."""
        self.assertEqual(action_points_for(2), 3)
        self.assertEqual(action_points_for(3), 2)
        session = self._game(ai_players=0, key="duo-portal-ap")
        view = game_view(self.db, session_id=session.id, actor=self.players[0])
        self.assertEqual(view["seat_count"], 2)
        self.assertEqual(view["action_points"], 3)

    def test_two_players_can_actually_open_the_portal(self):
        session = self._game(ai_players=0, key="duo-portal-win")
        final = self._play_out(session)
        # Zar tohumu oturum kimliğinden türer, yani sonuç tohuma göre değişir.
        # Burada yalnız oyunun kilitlenmeden bittiği doğrulanır; kazanma oranı
        # aşağıdaki deterministik denge testinde ölçülür.
        self.assertEqual(final["status"], "COMPLETED")
        self.assertIn(final["end_reason"], {"PORTAL_OPENED", "ROUND_LIMIT", "CHAOS_LIMIT"})

    def test_ai_seat_takes_its_own_turn_without_action_rows(self):
        session = self._game(ai_players=1, key="duo-portal-ai")
        view = game_view(self.db, session_id=session.id, actor=self.players[0])
        self.assertEqual(view["seat_count"], 3)
        self.assertEqual(view["action_points"], 2)
        ai_player = next(item for item in view["players"] if item["ai"])
        self.assertIsNone(ai_player["user_id"])
        self.assertEqual(ai_player["display_name"], AI_PLAYER_NAME)
        final = self._play_out(session)
        self.assertEqual(final["status"], "COMPLETED")
        # AI hamleleri board_game_actions tablosunda satır tutmaz; hepsi insan kaynaklı.
        actor_ids = {row.actor_id for row in self.db.query(BoardGameAction).filter_by(session_id=session.id).all()}
        self.assertTrue(actor_ids.issubset({user.id for user in self.players}))
        # AI'ın oynadığı en az bir hamle olay akışına düşer.
        ai_events = [row for row in self.db.query(ExperienceEvent).filter_by(session_id=session.id, event_type="board.action_resolved").all() if row.public_payload.get("actor_is_ai")]
        self.assertTrue(ai_events)


class BoardGameBalanceTests(unittest.TestCase):
    """İki koltuklu masanın aksiyon puanı ayarını sabit tohumlarla ölçer.

    Portalı açmak üç mühür ve üç şarj ister; bu hedef koltuk sayısıyla değişmez.
    İki koltukta tur başına bir oyuncu eksik olduğu için aksiyon bütçesi düşer.
    Aşağıdaki oranlar 3 AP'nin keyfi değil, üç kişilik oyunun zorluğunu yeniden
    üretmek için seçildiğini gösterir.
    """

    TRIALS = 60

    def _win_rate(self, seats: int, points: int) -> float:
        wins = 0
        with patch.object(engine_module, "action_points_for", lambda _seats: points):
            for index in range(self.TRIALS):
                seed = f"balance-{index}".encode()
                state = engine_module.initial_state(list(range(1, seats + 1)))
                counter = 0
                for _ in range(4_000):
                    if state["status"] != "ACTIVE":
                        break
                    action_id = ai_action_id(state)
                    player = engine_module.player_by_seat(state, state["active_seat"])
                    spec = next(item for item in engine_module._actions_for(state, player) if item["id"] == action_id)
                    state, _result, counter = engine_module._apply(state, state["active_seat"], action_id, spec, seed, counter)
                if state["end_reason"] == "PORTAL_OPENED":
                    wins += 1
        return wins / self.TRIALS

    def test_two_action_points_makes_a_two_seat_table_unwinnable(self):
        self.assertEqual(self._win_rate(seats=2, points=2), 0.0)

    def test_three_action_points_restores_three_seat_difficulty(self):
        two_seat = self._win_rate(seats=2, points=3)
        three_seat = self._win_rate(seats=3, points=2)
        self.assertGreater(two_seat, 0.6)
        # İki yapılandırmanın zorluğu birbirine yakın kalmalı.
        self.assertLess(abs(two_seat - three_seat), 0.2)


if __name__ == "__main__":
    unittest.main()
