from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.models import (
    Bot,
    BotPluginLink,
    BotServerLink,
    ChanceGameSession,
    ChanceWheel,
    Channel,
    ChannelType,
    Plugin,
    Server,
    ServerMember,
    User,
)
from app.bot_engine.dispatcher import MessageEvent, is_private_message_event, parse_colon_command
from app.database import Base
from app.plugins_engine.context import PluginContext
from app.plugins_engine.loader import discover_manifests, plugin_registry
from app.services.chance_games import EVENT_PREFIX, handle_chance_command


class ChanceGameTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.alice = User(
            username="alice",
            email="alice@example.test",
            hashed_password="x",
            matrix_user_id="@alice:test",
        )
        self.bob = User(
            username="bob",
            email="bob@example.test",
            hashed_password="x",
            matrix_user_id="@bob:test",
        )
        self.db.add_all([self.alice, self.bob])
        self.db.flush()
        self.server = Server(name="Test", owner_id=self.alice.id)
        self.db.add(self.server)
        self.db.flush()
        self.channel = Channel(
            server_id=self.server.id,
            name="genel",
            type=ChannelType.TEXT,
            matrix_room_id="!room:test",
        )
        self.db.add(self.channel)
        self.db.add(ServerMember(user_id=self.bob.id, server_id=self.server.id))
        self.db.commit()

    def tearDown(self):
        plugin_registry.unload("chance_games")
        self.db.close()
        self.engine.dispose()

    def context(self, user: User, command: str, args: str = "") -> PluginContext:
        return PluginContext(
            command=command,
            args=args,
            user_id=user.id,
            username=user.username,
            channel_id=self.channel.id,
            matrix_room_id=self.channel.matrix_room_id,
            server_id=self.server.id,
            bot_id=1,
            bot_name="sans-ustasi",
        )

    @staticmethod
    def envelope(output: str) -> dict:
        first_line = output.splitlines()[0]
        return json.loads(first_line[len(EVENT_PREFIX) :])

    def test_rps_keeps_first_move_secret_until_second_player_moves(self):
        invitation = handle_chance_command(self.db, self.context(self.alice, "takama", "@bob"))
        invitation_event = self.envelope(invitation)
        challenge_id = invitation_event["challenge_id"]

        accepted = handle_chance_command(self.db, self.context(self.bob, "kabul", challenge_id))
        self.assertEqual(self.envelope(accepted)["type"], "accepted")

        first = handle_chance_command(self.db, self.context(self.alice, "taş"))
        self.assertEqual(self.envelope(first)["type"], "move_locked")
        self.assertNotIn("TAŞ", first)

        result = handle_chance_command(self.db, self.context(self.bob, "makas"))
        result_event = self.envelope(result)
        self.assertEqual(result_event["type"], "result")
        self.assertEqual(result_event["winner"], "alice")
        self.assertEqual(result_event["challenger_move"], "taş")
        self.assertEqual(result_event["opponent_move"], "makas")

        game = self.db.query(ChanceGameSession).filter_by(public_id=challenge_id).one()
        self.assertEqual(game.status, "completed")

    def test_coin_duel_assigns_declared_faces_and_uses_secure_result(self):
        invitation = handle_chance_command(self.db, self.context(self.alice, "yazıtura", "@bob"))
        challenge_id = self.envelope(invitation)["challenge_id"]

        with patch("app.services.chance_games.secrets.choice", return_value="tura"):
            result = handle_chance_command(self.db, self.context(self.bob, "kabul", challenge_id))

        event = self.envelope(result)
        self.assertEqual(event["result"], "tura")
        self.assertEqual(event["winner"], "bob")

    def test_weighted_wheel_persists_entries_and_spins(self):
        handle_chance_command(self.db, self.context(self.alice, "ekleçark", "elma | 3"))
        handle_chance_command(self.db, self.context(self.alice, "ekleçark", "armut"))

        wheel = self.db.query(ChanceWheel).one()
        self.assertEqual(wheel.entries, [{"label": "elma", "weight": 3}, {"label": "armut", "weight": 1}])

        with patch("app.services.chance_games.secrets.randbelow", return_value=3):
            result = handle_chance_command(self.db, self.context(self.alice, "çark"))
        self.assertEqual(self.envelope(result)["result"], "armut")

    def test_move_commands_are_private_only_for_the_linked_game_bot(self):
        manifest = discover_manifests()["chance_games"]
        plugin_registry.load(manifest)
        self.db.add(Plugin(name="chance_games", version="1.0.0", enabled=True))
        bot = Bot(name="sans-ustasi", command_prefix="/", is_active=True)
        self.db.add(bot)
        self.db.flush()
        self.db.add_all(
            [
                BotServerLink(bot_id=bot.id, server_id=self.server.id),
                BotPluginLink(bot_id=bot.id, plugin_name="chance_games"),
            ]
        )
        self.db.commit()

        hidden_move = MessageEvent(
            channel=self.channel,
            sender_id=self.alice.id,
            sender_username=self.alice.username,
            content="/taş",
        )
        public_invite = MessageEvent(
            channel=self.channel,
            sender_id=self.alice.id,
            sender_username=self.alice.username,
            content="/takama @bob",
        )
        self.assertTrue(is_private_message_event(self.db, hidden_move))
        self.assertFalse(is_private_message_event(self.db, public_invite))
        self.assertEqual(parse_colon_command("ekleçark: elma"), ("ekleçark", "elma"))


if __name__ == "__main__":
    unittest.main()
    Plugin,
