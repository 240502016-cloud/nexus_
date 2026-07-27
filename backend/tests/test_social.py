from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import schemas
from app.core.matrix_client import MatrixError
from app.core.models import Channel, ChannelType, Friendship, Server, ServerMember, User
from app.core.routers.direct import list_direct_messages, send_direct_message
from app.core.routers.friends import accept_request, create_request, list_friends
from app.core.routers.members import add_member
from app.core.routers.messages import send_message
from app.database import Base


class SocialFlowTests(unittest.TestCase):
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
            matrix_access_token="alice-token",
        )
        self.bob = User(
            username="bob",
            email="bob@example.test",
            hashed_password="x",
            matrix_user_id="@bob:test",
            matrix_access_token="bob-token",
        )
        self.db.add_all([self.alice, self.bob])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def accept_friendship(self) -> Friendship:
        request = create_request(
            schemas.FriendRequestCreate(username="bob"),
            current_user=self.alice,
            db=self.db,
        )
        accept_request(request.id, current_user=self.bob, db=self.db)
        return self.db.get(Friendship, request.id)

    def test_friend_request_acceptance_and_friend_only_server_invite(self):
        friendship = self.accept_friendship()
        alice_friends = list_friends(current_user=self.alice, db=self.db)
        self.assertEqual([item.user.username for item in alice_friends], ["bob"])

        server = Server(name="Test", owner_id=self.alice.id)
        self.db.add(server)
        self.db.commit()
        add_member(
            server.id,
            schemas.MemberInvite(user_id=self.bob.id),
            current_user=self.alice,
            db=self.db,
        )
        self.assertIsNotNone(
            self.db.get(ServerMember, {"user_id": self.bob.id, "server_id": server.id})
        )
        self.assertEqual(friendship.status, "accepted")

    @patch("app.core.routers.direct.matrix_client.send_message", return_value="$dm")
    @patch("app.core.routers.direct.matrix_client.join_room")
    @patch("app.core.routers.direct.matrix_client.invite_user")
    @patch("app.core.routers.direct.matrix_client.create_room", return_value="!dm:test")
    def test_private_conversation_is_created_and_persists_messages(
        self,
        create_room,
        invite_user,
        join_room,
        send_matrix_message,
    ):
        friendship = self.accept_friendship()
        sent = send_direct_message(
            friendship.id,
            schemas.MessageCreate(content="özel merhaba", client_id="client_123"),
            current_user=self.alice,
            db=self.db,
        )
        self.assertEqual(sent.event_id, "$dm")
        self.assertEqual(self.db.get(Friendship, friendship.id).matrix_room_id, "!dm:test")
        create_room.assert_called_once()
        invite_user.assert_called_once()
        join_room.assert_called_once()
        send_matrix_message.assert_called_once()

        with patch(
            "app.core.routers.direct.matrix_client.get_message_page",
            return_value={"items": [sent.model_dump()], "next_cursor": None, "has_more": False},
        ):
            page = list_direct_messages(
                friendship.id,
                limit=50,
                cursor=None,
                current_user=self.bob,
                db=self.db,
            )
        self.assertEqual(page["items"][0]["content"], "özel merhaba")

    @patch("app.core.routers.messages.handle_message_event", return_value=[])
    @patch("app.core.routers.messages.repair_room_membership")
    @patch(
        "app.core.routers.messages.matrix_client.send_message",
        side_effect=[MatrixError("403 M_FORBIDDEN user not in room"), "$repaired"],
    )
    def test_channel_message_repairs_missing_matrix_membership(
        self,
        send_matrix_message,
        repair_membership,
        _handle_message_event,
    ):
        server = Server(name="Repair", owner_id=self.alice.id)
        self.db.add(server)
        self.db.flush()
        self.db.add(ServerMember(user_id=self.bob.id, server_id=server.id))
        channel = Channel(
            server_id=server.id,
            name="genel",
            type=ChannelType.TEXT,
            matrix_room_id="!repair:test",
        )
        self.db.add(channel)
        self.db.commit()

        result = send_message(
            channel.id,
            schemas.MessageCreate(content="yeniden dene", client_id="client_repair"),
            current_user=self.bob,
            db=self.db,
        )

        self.assertEqual(result.event_id, "$repaired")
        self.assertEqual(send_matrix_message.call_count, 2)
        repair_membership.assert_called_once_with("!repair:test", self.alice, self.bob)


if __name__ == "__main__":
    unittest.main()
