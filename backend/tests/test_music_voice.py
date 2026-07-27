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
    async def test_join_uses_current_voice_contract_and_waits_for_browser_offer(self):
        db = Mock()
        db.get.return_value = SimpleNamespace(
            owner_id=7,
            members=[SimpleNamespace(user_id=8), SimpleNamespace(user_id=9)],
        )
        session = voice_session.MusicSession(server_id=2, channel_id=3, bot_id=4, bot_name="Müzik")
        session._offer_to = AsyncMock()

        with (
            patch.object(voice_session, "SessionLocal", return_value=db),
            patch.object(voice_session.voice_manager, "join", new=AsyncMock(return_value=[])) as join,
            patch.object(voice_session.voice_manager, "broadcast", new=AsyncMock()) as broadcast,
            patch.object(voice_session, "notify_voice_state", new=AsyncMock()) as notify,
        ):
            await session.join()

        join.assert_awaited_once_with(3, 2, {7, 8, 9}, -4, "Müzik", None, session._client)
        broadcast.assert_awaited_once()
        notify.assert_awaited_once_with(3)
        session._offer_to.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
