from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import schemas
from app.core.models import Channel, ChannelType, Server, ServerMember, User
from app.core.routers.messages import (
    list_pinned_messages,
    pin_message,
    send_message,
    toggle_reaction,
)
from app.database import Base


class MessageFeatureTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.owner = User(
            username="owner",
            email="owner@example.test",
            hashed_password="x",
            matrix_user_id="@owner:test",
            matrix_access_token="owner-token",
        )
        self.member = User(
            username="member",
            email="member@example.test",
            hashed_password="x",
            matrix_user_id="@member:test",
            matrix_access_token="member-token",
        )
        self.db.add_all([self.owner, self.member])
        self.db.flush()
        self.server = Server(name="Mesaj Testi", owner_id=self.owner.id)
        self.db.add(self.server)
        self.db.flush()
        self.db.add(ServerMember(server_id=self.server.id, user_id=self.member.id))
        self.channel = Channel(
            server_id=self.server.id,
            name="genel",
            type=ChannelType.TEXT,
            matrix_room_id="!message:test",
        )
        self.db.add(self.channel)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @patch("app.core.routers.messages.notify_channel_message")
    @patch("app.core.routers.messages.handle_message_event", return_value=[])
    @patch("app.core.routers.messages.matrix_client.send_message", return_value="$message")
    def test_mention_is_sent_to_matrix_and_returned_as_core_user_id(
        self,
        send_matrix_message,
        _handle_message,
        _notify,
    ):
        result = send_message(
            self.channel.id,
            schemas.MessageCreate(content="@owner bakar mısın", client_id="mention-1"),
            current_user=self.member,
            db=self.db,
        )

        self.assertEqual(result.mentioned_user_ids, [self.owner.id])
        self.assertEqual(
            send_matrix_message.call_args.kwargs["mention_user_ids"],
            ["@owner:test"],
        )

    @patch("app.core.routers.messages.notify_channel_meta")
    @patch("app.core.routers.messages.matrix_client.send_reaction", return_value="$reaction")
    @patch("app.core.routers.messages.matrix_client.get_event")
    @patch("app.core.routers.messages.matrix_client.get_reactions")
    def test_reaction_toggle_adds_and_broadcasts_authoritative_summary(
        self,
        get_reactions,
        get_event,
        send_reaction,
        notify_meta,
    ):
        get_event.return_value = {
            "event_id": "$message",
            "type": "m.room.message",
            "content": {"body": "merhaba"},
        }
        get_reactions.side_effect = [
            [],
            [
                {
                    "event_id": "$reaction",
                    "sender": "@member:test",
                    "type": "m.reaction",
                    "content": {
                        "m.relates_to": {
                            "rel_type": "m.annotation",
                            "event_id": "$message",
                            "key": "👍",
                        }
                    },
                }
            ],
        ]

        result = toggle_reaction(
            self.channel.id,
            "$message",
            schemas.MessageReactionToggle(emoji="👍"),
            current_user=self.member,
            db=self.db,
        )

        send_reaction.assert_called_once()
        self.assertEqual(result.reactions[0].count, 1)
        self.assertTrue(result.reactions[0].me)
        notify_meta.assert_called_once()

    @patch("app.core.routers.messages.notify_channel_meta")
    @patch("app.core.routers.messages.matrix_client.set_pinned_event_ids")
    @patch("app.core.routers.messages.matrix_client.get_pinned_event_ids", return_value=[])
    @patch(
        "app.core.routers.messages.matrix_client.get_event",
        return_value={
            "event_id": "$message",
            "type": "m.room.message",
            "content": {"body": "sabitle"},
        },
    )
    def test_owner_can_pin_but_plain_member_cannot(
        self,
        _get_event,
        _get_pins,
        set_pins,
        _notify_meta,
    ):
        pin_message(
            self.channel.id,
            "$message",
            current_user=self.owner,
            db=self.db,
        )
        set_pins.assert_called_once_with("owner-token", "!message:test", ["$message"])

        with self.assertRaises(HTTPException) as denied:
            pin_message(
                self.channel.id,
                "$other",
                current_user=self.member,
                db=self.db,
            )
        self.assertEqual(denied.exception.status_code, 403)
        self.assertEqual(set_pins.call_count, 1)

    @patch(
        "app.core.routers.messages.matrix_client.get_event",
        side_effect=[
            {"event_id": "$deleted", "type": "m.room.message", "content": {}},
            {
                "event_id": "$visible",
                "sender": "@member:test",
                "type": "m.room.message",
                "origin_server_ts": 3,
                "content": {"body": "görünür"},
            },
        ],
    )
    @patch(
        "app.core.routers.messages.matrix_client.get_pinned_event_ids",
        return_value=["$deleted", "$visible"],
    )
    def test_deleted_pin_does_not_break_the_pin_list(self, _get_pins, _get_event):
        result = list_pinned_messages(
            self.channel.id,
            current_user=self.owner,
            db=self.db,
        )
        self.assertEqual([item.event_id for item in result.items], ["$visible"])
        self.assertTrue(result.can_manage)


if __name__ == "__main__":
    unittest.main()
