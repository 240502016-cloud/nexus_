from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[2] / "plugins" / "music" / "main.py"
SPEC = importlib.util.spec_from_file_location("test_music_plugin_main", MODULE_PATH)
music = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(music)


class MusicPluginTests(unittest.TestCase):
    def setUp(self):
        music._youtube_sessions.clear()

    def test_youtube_urls_are_normalized_to_video_ids(self):
        self.assertEqual(music._youtube_video_id("https://youtu.be/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(
            music._youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=12"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            music._youtube_video_id("https://youtube.com/shorts/dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )
        self.assertIsNone(music._youtube_video_id("https://example.com/watch?v=dQw4w9WgXcQ"))

    def test_youtube_command_emits_valid_synchronized_state(self):
        context = SimpleNamespace(
            server_id=1,
            channel_id=12,
            bot_id=3,
            bot_name="Nexus Müzik",
            command="youtube",
            args="https://youtu.be/dQw4w9WgXcQ",
        )
        with patch.object(music.time, "time", return_value=1000.0):
            output = music.handle_command(context)

        self.assertTrue(output.startswith(music.YOUTUBE_EVENT_PREFIX))
        self.assertIn('"video_id":"dQw4w9WgXcQ"', output)
        self.assertIn('"playing":true', output)
        self.assertIn(12, music._youtube_sessions)


if __name__ == "__main__":
    unittest.main()
