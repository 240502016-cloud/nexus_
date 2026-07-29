from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import schemas
from app.core.matrix_client import MatrixError
from app.core.models import (
    Channel,
    ChannelType,
    Friendship,
    Role,
    Server,
    ServerInvite,
    ServerMember,
    User,
)
from app.core.permissions import Permission
from app.core.routers.channels import list_channels
from app.core.routers.direct import list_direct_messages, send_direct_message
from app.core.routers.friends import (
    accept_request,
    create_request,
    list_friends,
    list_requests,
    remove_friendship,
)
from app.core.routers.join_codes import (
    create_join_code,
    join_server,
    revoke_join_code,
    rotate_join_code,
)
from app.core.routers.members import add_member
from app.core.routers.messages import send_message
from app.core.routers.server_invites import accept_server_invite, decline_or_cancel_server_invite
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

    @patch("app.core.routers.server_invites.matrix_client.join_room")
    @patch("app.core.routers.server_invites.matrix_client.invite_user")
    def test_friend_request_acceptance_and_friend_only_server_invite(
        self,
        invite_matrix_user,
        join_matrix_room,
    ):
        friendship = self.accept_friendship()
        alice_friends = list_friends(current_user=self.alice, db=self.db)
        self.assertEqual([item.user.username for item in alice_friends], ["bob"])

        server = Server(name="Test", owner_id=self.alice.id)
        self.db.add(server)
        self.db.commit()
        channel = Channel(
            server_id=server.id,
            name="genel",
            type=ChannelType.TEXT,
            matrix_room_id="!server:test",
        )
        self.db.add(channel)
        self.db.commit()
        invite = add_member(
            server.id,
            schemas.MemberInvite(user_id=self.bob.id),
            current_user=self.alice,
            db=self.db,
        )
        repeated_invite = add_member(
            server.id,
            schemas.MemberInvite(user_id=self.bob.id),
            current_user=self.alice,
            db=self.db,
        )
        self.assertEqual(repeated_invite.id, invite.id)
        self.assertIsNone(
            self.db.get(ServerMember, {"user_id": self.bob.id, "server_id": server.id})
        )
        self.assertEqual(invite.status, "pending")

        accepted_server = accept_server_invite(
            invite.id,
            current_user=self.bob,
            db=self.db,
        )
        accepted_server_again = accept_server_invite(
            invite.id,
            current_user=self.bob,
            db=self.db,
        )
        self.assertEqual(accepted_server.id, server.id)
        self.assertEqual(accepted_server_again.id, server.id)
        self.assertIsNotNone(
            self.db.get(ServerMember, {"user_id": self.bob.id, "server_id": server.id})
        )
        self.assertEqual(self.db.get(ServerInvite, invite.id).status, "accepted")
        self.assertEqual(friendship.status, "accepted")
        invite_matrix_user.assert_called_once()
        join_matrix_room.assert_called_once()

    def test_server_invite_can_be_rejected_without_membership(self):
        self.accept_friendship()
        server = Server(name="Reject", owner_id=self.alice.id)
        self.db.add(server)
        self.db.commit()
        invite = add_member(
            server.id,
            schemas.MemberInvite(user_id=self.bob.id),
            current_user=self.alice,
            db=self.db,
        )

        decline_or_cancel_server_invite(invite.id, current_user=self.bob, db=self.db)
        decline_or_cancel_server_invite(invite.id, current_user=self.bob, db=self.db)

        self.assertEqual(self.db.get(ServerInvite, invite.id).status, "rejected")
        self.assertIsNone(
            self.db.get(ServerMember, {"user_id": self.bob.id, "server_id": server.id})
        )

    def test_friend_request_survives_reloads_and_duplicate_send_is_idempotent(self):
        first = create_request(
            schemas.FriendRequestCreate(username="bob"),
            current_user=self.alice,
            db=self.db,
        )
        repeated = create_request(
            schemas.FriendRequestCreate(username="bob"),
            current_user=self.alice,
            db=self.db,
        )

        self.assertEqual(repeated.id, first.id)
        self.assertEqual(
            [request.id for request in list_requests(current_user=self.bob, db=self.db).incoming],
            [first.id],
        )
        self.assertEqual(self.db.query(Friendship).count(), 1)

    def test_friend_request_accept_and_delete_retries_are_idempotent(self):
        request = create_request(
            schemas.FriendRequestCreate(username="bob"),
            current_user=self.alice,
            db=self.db,
        )

        accepted = accept_request(request.id, current_user=self.bob, db=self.db)
        accepted_again = accept_request(request.id, current_user=self.bob, db=self.db)
        self.assertEqual(accepted_again.friendship_id, accepted.friendship_id)
        self.assertEqual(self.db.get(Friendship, request.id).status, "accepted")

        remove_friendship(request.id, current_user=self.alice, db=self.db)
        remove_friendship(request.id, current_user=self.alice, db=self.db)
        self.assertIsNone(self.db.get(Friendship, request.id))

    @patch(
        "app.core.routers.join_codes.invite_and_join",
        side_effect=MatrixError("matrix temporarily unavailable"),
    )
    def test_share_code_joins_server_and_voice_without_friendship(self, _invite_and_join):
        server = Server(name="Ses Ekibi", owner_id=self.alice.id)
        self.db.add(server)
        self.db.flush()
        default_role = Role(
            server_id=server.id,
            name="@everyone",
            is_default=True,
            permissions=int(Permission.default()),
        )
        self.db.add(default_role)
        self.db.add(ServerMember(user_id=self.alice.id, server_id=server.id))
        self.db.add_all(
            [
                Channel(
                    server_id=server.id,
                    name="genel",
                    type=ChannelType.TEXT,
                    matrix_room_id="!join-code:test",
                ),
                Channel(server_id=server.id, name="Ses", type=ChannelType.VOICE),
            ]
        )
        self.db.commit()

        record = create_join_code(server.id, current_user=self.alice, db=self.db)
        joined = join_server(
            schemas.ServerJoinRequest(code=record.code.lower()),
            current_user=self.bob,
            db=self.db,
        )
        joined_again = join_server(
            schemas.ServerJoinRequest(code=record.code),
            current_user=self.bob,
            db=self.db,
        )

        self.assertEqual(joined.id, server.id)
        self.assertEqual(joined_again.id, server.id)
        self.assertIsNone(
            self.db.query(Friendship)
            .filter(
                Friendship.user_low_id == min(self.alice.id, self.bob.id),
                Friendship.user_high_id == max(self.alice.id, self.bob.id),
            )
            .first()
        )
        self.assertIsNotNone(
            self.db.get(ServerMember, {"user_id": self.bob.id, "server_id": server.id})
        )
        self.assertIn(default_role, self.bob.roles)
        self.assertEqual(
            [channel.name for channel in list_channels(server.id, current_user=self.bob, db=self.db)],
            ["genel", "Ses"],
        )

        rotated = rotate_join_code(server.id, current_user=self.alice, db=self.db)
        self.assertNotEqual(rotated.code, record.code)
        with self.assertRaises(HTTPException) as invalid:
            join_server(
                schemas.ServerJoinRequest(code=record.code),
                current_user=self.bob,
                db=self.db,
            )
        self.assertEqual(invalid.exception.status_code, 404)

        revoke_join_code(server.id, current_user=self.alice, db=self.db)
        with self.assertRaises(HTTPException) as revoked:
            join_server(
                schemas.ServerJoinRequest(code=rotated.code),
                current_user=self.bob,
                db=self.db,
            )
        self.assertEqual(revoked.exception.status_code, 404)

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

    @patch("app.core.routers.messages.handle_message_event", return_value=[])
    @patch("app.core.routers.messages.matrix_client.send_message", return_value="$reply")
    @patch(
        "app.core.routers.messages.matrix_client.get_event",
        return_value={
            "event_id": "$original",
            "type": "m.room.message",
            "sender": "@alice:test",
            "content": {"body": "ilk mesaj"},
        },
    )
    def test_channel_reply_is_validated_and_returned(
        self,
        _get_event,
        send_matrix_message,
        _handle_message_event,
    ):
        server = Server(name="Reply", owner_id=self.alice.id)
        self.db.add(server)
        self.db.flush()
        self.db.add(ServerMember(user_id=self.bob.id, server_id=server.id))
        channel = Channel(
            server_id=server.id,
            name="genel",
            type=ChannelType.TEXT,
            matrix_room_id="!reply:test",
        )
        self.db.add(channel)
        self.db.commit()

        result = send_message(
            channel.id,
            schemas.MessageCreate(
                content="katılıyorum",
                client_id="client_reply",
                reply_to_event_id="$original",
            ),
            current_user=self.bob,
            db=self.db,
        )

        self.assertEqual(result.reply_to.event_id, "$original")
        self.assertEqual(result.reply_to.content, "ilk mesaj")
        self.assertEqual(
            send_matrix_message.call_args.kwargs["reply_to"],
            {
                "event_id": "$original",
                "sender": "@alice:test",
                "content": "ilk mesaj",
            },
        )


if __name__ == "__main__":
    unittest.main()
