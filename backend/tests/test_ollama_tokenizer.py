from __future__ import annotations

import unittest

from app.services.ollama.tokenizer import (
    build_token_limited_context,
    estimate_message_tokens,
)


class OllamaTokenizerTests(unittest.TestCase):
    def test_oversized_latest_message_is_bounded_without_mutating_source(self):
        original = "TALİMAT: yalnız verilen metni özetle.\n" + ("eski " * 500) + "EN YENİ MESAJ"
        history = [{"role": "user", "content": original}]

        result = build_token_limited_context(
            history,
            system_prompt="Güvenli ve kısa cevap ver.",
            token_budget=128,
        )

        self.assertEqual(history[0]["content"], original)
        self.assertTrue(result[1]["content"].startswith("TALİMAT:"))
        self.assertTrue(result[1]["content"].endswith("EN YENİ MESAJ"))
        self.assertIn("bağlam kısaltıldı", result[1]["content"])
        self.assertLessEqual(sum(estimate_message_tokens(item) for item in result), 128)

    def test_newest_complete_messages_are_kept_when_they_fit(self):
        history = [
            {"role": "user", "content": "a" * 600},
            {"role": "assistant", "content": "kısa yanıt"},
            {"role": "user", "content": "son soru"},
        ]

        result = build_token_limited_context(
            history,
            system_prompt="Kısa cevap ver.",
            token_budget=128,
        )

        self.assertEqual([item["content"] for item in result[1:]], ["kısa yanıt", "son soru"])


if __name__ == "__main__":
    unittest.main()
