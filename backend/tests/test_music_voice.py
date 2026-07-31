import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


MODULE_PATH = Path(__file__).resolve().parents[2] / "plugins" / "music" / "voice_session.py"
SPEC = importlib.util.spec_from_file_location("test_music_voice_session", MODULE_PATH)
voice_session = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(voice_session)


class MusicVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_join_uses_current_voice_contract_and_offers_to_existing_peers(self):
        db = Mock()
        db.get.return_value = SimpleNamespace(
            owner_id=7,
            members=[SimpleNamespace(user_id=8), SimpleNamespace(user_id=9)],
        )
        session = voice_session.MusicSession(server_id=2, channel_id=3, bot_id=4, bot_name="Müzik")
        session._offer_to = AsyncMock()

        with (
            patch.object(voice_session, "SessionLocal", return_value=db),
            patch.object(
                voice_session.voice_manager,
                "join",
                new=AsyncMock(return_value=[{"user_id": 8}, {"user_id": 9}]),
            ) as join,
            patch.object(voice_session.voice_manager, "broadcast", new=AsyncMock()) as broadcast,
            patch.object(voice_session, "notify_voice_state", new=AsyncMock()) as notify,
        ):
            await session.join()

        join.assert_awaited_once_with(3, 2, {7, 8, 9}, -4, "Müzik", None, session._client)
        broadcast.assert_awaited_once()
        notify.assert_awaited_once_with(3)
        self.assertEqual(
            [call.args[0] for call in session._offer_to.await_args_list],
            [8, 9],
        )

    def test_private_or_local_audio_url_is_rejected(self):
        with patch.object(
            voice_session.socket,
            "getaddrinfo",
            return_value=[(voice_session.socket.AF_INET, 1, 6, "", ("127.0.0.1", 80))],
        ):
            with self.assertRaisesRegex(ValueError, "Yerel, özel"):
                voice_session._validate_public_host("example.test", 80)

    def test_invalid_audio_url_port_is_rejected_cleanly(self):
        with self.assertRaisesRegex(ValueError, "port geçerli değil"):
            voice_session.resolve_remote_track("https://media.example.test:invalid/song.mp3")

    def test_direct_audio_url_is_preflighted_without_downloading_body(self):
        response = Mock()
        response.is_redirect = False
        response.is_permanent_redirect = False
        response.headers = {"content-type": "audio/mpeg"}
        response.raise_for_status = Mock()
        response.close = Mock()
        with (
            patch.object(voice_session, "_validate_public_host"),
            patch.object(voice_session.requests, "get", return_value=response) as get,
        ):
            track = voice_session.resolve_remote_track("https://media.example.test/music/song.mp3")

        self.assertEqual(track.url, "https://media.example.test/music/song.mp3")
        self.assertEqual(track.label, "song")
        self.assertTrue(get.call_args.kwargs["stream"])
        response.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
