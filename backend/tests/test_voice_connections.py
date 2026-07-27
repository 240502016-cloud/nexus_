from __future__ import annotations

import unittest

from app.core.routers.voice import VoiceConnectionManager


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


if __name__ == "__main__":
    unittest.main()
