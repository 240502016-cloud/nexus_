from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.bot_engine.dispatcher import MessageEvent, _send_bot_message_with_room_repair
from app.core.matrix_client import MatrixError


class BotRoomRepairTests(unittest.TestCase):
    def test_missing_bot_room_membership_is_repaired_before_retry(self):
        bot = SimpleNamespace(matrix_access_token="bot-token", matrix_user_id="@bot:nexus.test")
        owner = SimpleNamespace(matrix_access_token="owner-token")
        channel = SimpleNamespace(
            id=4,
            matrix_room_id="!room:nexus.test",
            server=SimpleNamespace(owner=owner),
        )
        event = MessageEvent(channel=channel, sender_id=2, sender_username="alice", content="/test")

        with (
            patch("app.bot_engine.dispatcher.matrix_client.send_message") as send,
            patch("app.bot_engine.dispatcher.matrix_client.invite_user") as invite,
            patch("app.bot_engine.dispatcher.matrix_client.join_room") as join,
        ):
            send.side_effect = [MatrixError("not joined"), "$event"]
            result = _send_bot_message_with_room_repair(bot, event, "yanıt")

        self.assertEqual(result, "$event")
        invite.assert_called_once_with("owner-token", "!room:nexus.test", "@bot:nexus.test")
        join.assert_called_once_with("bot-token", "!room:nexus.test")
        self.assertEqual(send.call_count, 2)


if __name__ == "__main__":
    unittest.main()
