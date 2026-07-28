from __future__ import annotations

import unittest
from unittest.mock import patch

from app.config import settings
from app.core.models import User
from app.core.routers.voice import VoiceConnectionManager, voice_ice_servers


class VoiceConnectionManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconnect_does_not_add_user_as_their_own_peer(self):
        manager = VoiceConnectionManager()
        first_socket = object()
        second_socket = object()

        await manager.join(10, 20, {1, 2}, 1, "alice", None, first_socket)
        peers = await manager.join(10, 20, {1, 2}, 1, "alice", None, second_socket)

        self.assertEqual(peers, [])
        self.assertEqual([participant["user_id"] for participant in manager.roster(10)], [1])

    async def test_stale_socket_cannot_remove_replacement_connection(self):
        manager = VoiceConnectionManager()
        first_socket = object()
        second_socket = object()

        await manager.join(10, 20, {1, 2}, 1, "alice", None, first_socket)
        await manager.join(10, 20, {1, 2}, 1, "alice", None, second_socket)

        self.assertFalse(manager.leave(10, 1, first_socket))
        self.assertEqual([participant["user_id"] for participant in manager.roster(10)], [1])
        self.assertTrue(manager.leave(10, 1, second_socket))
        self.assertEqual(manager.roster(10), [])

    def test_hamachi_turn_is_not_advertised_to_public_clients(self):
        user = User(id=1, username="alice", email="alice@example.test", hashed_password="x")
        with (
            patch.object(settings, "turn_domain", "25.49.22.166"),
            patch.object(settings, "turn_external_ip", "25.49.22.166"),
            patch.object(settings, "turn_auth_secret", "secret"),
        ):
            result = voice_ice_servers(current_user=user)

        self.assertEqual(
            result["ice_servers"],
            [{"urls": "stun:stun.cloudflare.com:3478"}],
        )


if __name__ == "__main__":
    unittest.main()
