import unittest

from app.core.matrix_client import MatrixClient


class FakeResponse:
    ok = True
    status_code = 200
    text = ""

    def json(self):
        return {
            "chunk": [
                {
                    "event_id": "$new",
                    "sender": "@aylin:nexus",
                    "type": "m.room.message",
                    "origin_server_ts": 2,
                    "content": {"body": "yeni"},
                },
                {
                    "event_id": "$redacted",
                    "sender": "@aylin:nexus",
                    "type": "m.room.message",
                    "origin_server_ts": 1,
                    "content": {"body": "silindi"},
                    "unsigned": {"redacted_because": {}},
                },
            ],
            "end": "next-page-token",
        }


class MatrixPaginationTests(unittest.TestCase):
    def test_send_message_uses_matrix_reply_relation_and_preview(self):
        client = MatrixClient(base_url="http://matrix.invalid", shared_secret="test")
        captured = {}

        class SendResponse(FakeResponse):
            def json(self):
                return {"event_id": "$reply"}

        def fake_request(method, path, **kwargs):
            captured.update({"method": method, "path": path, **kwargs})
            return SendResponse()

        client._request = fake_request  # type: ignore[method-assign]
        event_id = client.send_message(
            "token",
            "!room:nexus",
            "yanıt",
            txn_id="reply-transaction",
            reply_to={
                "event_id": "$original",
                "sender": "@aylin:nexus",
                "content": "ilk mesaj",
            },
        )

        self.assertEqual(event_id, "$reply")
        self.assertEqual(
            captured["json"]["m.relates_to"],
            {"m.in_reply_to": {"event_id": "$original"}},
        )
        self.assertEqual(
            captured["json"]["io.nexus.reply_preview"]["content"],
            "ilk mesaj",
        )

    def test_send_message_includes_matrix_mentions(self):
        client = MatrixClient(base_url="http://matrix.invalid", shared_secret="test")
        captured = {}

        class SendResponse(FakeResponse):
            def json(self):
                return {"event_id": "$mentioned"}

        def fake_request(method, path, **kwargs):
            captured.update({"method": method, "path": path, **kwargs})
            return SendResponse()

        client._request = fake_request  # type: ignore[method-assign]
        client.send_message(
            "token",
            "!room:nexus",
            "@berk merhaba",
            mention_user_ids=["@berk:nexus"],
        )

        self.assertEqual(
            captured["json"]["m.mentions"],
            {"user_ids": ["@berk:nexus"]},
        )

    def test_cursor_is_forwarded_and_redacted_events_are_filtered(self):
        client = MatrixClient(base_url="http://matrix.invalid", shared_secret="test")
        captured = {}

        def fake_request(method, path, **kwargs):
            captured.update({"method": method, "path": path, **kwargs})
            return FakeResponse()

        client._request = fake_request  # type: ignore[method-assign]
        page = client.get_message_page("token", "!room:nexus", limit=25, cursor="page-1")

        self.assertEqual(captured["params"], {"dir": "b", "limit": 25, "from": "page-1"})
        self.assertEqual([item["event_id"] for item in page["items"]], ["$new"])
        self.assertEqual(page["next_cursor"], "next-page-token")
        self.assertTrue(page["has_more"])

    def test_replacement_event_updates_original_without_becoming_a_second_message(self):
        client = MatrixClient(base_url="http://matrix.invalid", shared_secret="test")

        class EditResponse(FakeResponse):
            def json(self):
                return {
                    "chunk": [
                        {
                            "event_id": "$edit",
                            "sender": "@aylin:nexus",
                            "type": "m.room.message",
                            "origin_server_ts": 3,
                            "content": {
                                "body": "* düzenlendi",
                                "m.new_content": {"msgtype": "m.text", "body": "düzenlendi"},
                                "m.relates_to": {"rel_type": "m.replace", "event_id": "$original"},
                            },
                        },
                        {
                            "event_id": "$original",
                            "sender": "@aylin:nexus",
                            "type": "m.room.message",
                            "origin_server_ts": 2,
                            "content": {"body": "ilk metin"},
                        },
                    ],
                    "end": None,
                }

        client._request = lambda *_args, **_kwargs: EditResponse()  # type: ignore[method-assign]
        page = client.get_message_page("token", "!room:nexus")

        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["items"][0]["event_id"], "$original")
        self.assertEqual(page["items"][0]["content"], "düzenlendi")
        self.assertTrue(page["items"][0]["edited"])

    def test_reply_preview_is_resolved_from_the_same_history_page(self):
        client = MatrixClient(base_url="http://matrix.invalid", shared_secret="test")

        class ReplyResponse(FakeResponse):
            def json(self):
                return {
                    "chunk": [
                        {
                            "event_id": "$reply",
                            "sender": "@berk:nexus",
                            "type": "m.room.message",
                            "origin_server_ts": 3,
                            "content": {
                                "body": "katılıyorum",
                                "m.relates_to": {
                                    "m.in_reply_to": {"event_id": "$original"},
                                },
                            },
                        },
                        {
                            "event_id": "$original",
                            "sender": "@aylin:nexus",
                            "type": "m.room.message",
                            "origin_server_ts": 2,
                            "content": {"body": "ilk mesaj"},
                        },
                    ],
                    "end": None,
                }

        client._request = lambda *_args, **_kwargs: ReplyResponse()  # type: ignore[method-assign]
        page = client.get_message_page("token", "!room:nexus")

        self.assertEqual(
            page["items"][0]["reply_to"],
            {
                "event_id": "$original",
                "sender": "@aylin:nexus",
                "content": "ilk mesaj",
            },
        )

    def test_history_restores_reaction_counts_own_reaction_and_mentions(self):
        client = MatrixClient(base_url="http://matrix.invalid", shared_secret="test")

        class ReactionResponse(FakeResponse):
            def json(self):
                return {
                    "chunk": [
                        {
                            "event_id": "$reaction",
                            "sender": "@berk:nexus",
                            "type": "m.reaction",
                            "origin_server_ts": 3,
                            "content": {
                                "m.relates_to": {
                                    "rel_type": "m.annotation",
                                    "event_id": "$message",
                                    "key": "👍",
                                }
                            },
                        },
                        {
                            "event_id": "$message",
                            "sender": "@aylin:nexus",
                            "type": "m.room.message",
                            "origin_server_ts": 2,
                            "content": {
                                "body": "@berk tamam",
                                "m.mentions": {"user_ids": ["@berk:nexus"]},
                            },
                            "unsigned": {
                                "m.relations": {
                                    "m.annotation": {
                                        "chunk": [{"key": "👍", "count": 3}]
                                    }
                                }
                            },
                        },
                    ],
                    "end": None,
                }

        client._request = lambda *_args, **_kwargs: ReactionResponse()  # type: ignore[method-assign]
        page = client.get_message_page(
            "token",
            "!room:nexus",
            current_matrix_user_id="@berk:nexus",
        )

        self.assertEqual(
            page["items"][0]["reactions"],
            [{"emoji": "👍", "count": 3, "me": True}],
        )
        self.assertEqual(page["items"][0]["mention_user_ids"], ["@berk:nexus"])

    def test_search_is_scoped_to_room_and_optional_sender(self):
        client = MatrixClient(base_url="http://matrix.invalid", shared_secret="test")
        captured = {}

        class SearchResponse(FakeResponse):
            def json(self):
                return {
                    "search_categories": {
                        "room_events": {
                            "results": [
                                {
                                    "result": {
                                        "event_id": "$found",
                                        "type": "m.room.message",
                                        "content": {"body": "sunucu sorunu"},
                                    }
                                }
                            ]
                        }
                    }
                }

        def fake_request(method, path, **kwargs):
            captured.update({"method": method, "path": path, **kwargs})
            return SearchResponse()

        client._request = fake_request  # type: ignore[method-assign]
        results = client.search_messages(
            "token",
            "!room:nexus",
            "sunucu",
            sender="@berk:nexus",
            limit=12,
        )

        event_filter = captured["json"]["search_categories"]["room_events"]["filter"]
        self.assertEqual(captured["path"], "/_matrix/client/v3/search")
        self.assertEqual(event_filter["rooms"], ["!room:nexus"])
        self.assertEqual(event_filter["senders"], ["@berk:nexus"])
        self.assertEqual(event_filter["limit"], 12)
        self.assertEqual(results[0]["event_id"], "$found")

    def test_missing_pin_state_is_an_empty_list(self):
        client = MatrixClient(base_url="http://matrix.invalid", shared_secret="test")

        class MissingStateResponse(FakeResponse):
            ok = False
            status_code = 404

        client._request = lambda *_args, **_kwargs: MissingStateResponse()  # type: ignore[method-assign]
        self.assertEqual(client.get_pinned_event_ids("token", "!room:nexus"), [])

    def test_reaction_relations_use_the_stable_v1_endpoint(self):
        client = MatrixClient(base_url="http://matrix.invalid", shared_secret="test")
        captured = {}

        class RelationResponse(FakeResponse):
            def json(self):
                return {"chunk": []}

        def fake_request(method, path, **kwargs):
            captured.update({"method": method, "path": path, **kwargs})
            return RelationResponse()

        client._request = fake_request  # type: ignore[method-assign]
        self.assertEqual(client.get_reactions("token", "!room:nexus", "$message"), [])
        self.assertEqual(
            captured["path"],
            "/_matrix/client/v1/rooms/!room:nexus/relations/$message/m.annotation/m.reaction",
        )


if __name__ == "__main__":
    unittest.main()
