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


if __name__ == "__main__":
    unittest.main()
