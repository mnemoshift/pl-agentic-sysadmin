#!/usr/bin/env python3
"""
Testy jednostkowe dla modułu Reżysera tekstu (scripts/media/text_director.py).
Weryfikują:
- clean_voiceover_text (odcięcie PACING BUDGET, wyciąganie z <voiceover>, usuwanie meta-komentarzy)
- strip_voice_tags (usuwanie tagów SSML, XML i nawiasowych)
- TTSEngineCapability & supports_voice_tags (macierz wsparcia silników)
- enrich_voiceover_tags (Two-Pass generation, walidacja słów, obsługa fallbacku)
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "media"))

from text_director import (  # noqa: E402
    clean_voiceover_text,
    enrich_voiceover_tags,
    get_engine_capability,
    strip_voice_tags,
    supports_voice_tags,
)


class TestTextDirector(unittest.TestCase):
    def test_clean_voiceover_text_cuts_pacing_budget(self):
        # Weryfikacja odcięcia PACING BUDGET (Speech window: 19.2s): ...
        raw = (
            "\"This is the clean spoken line.\" PACING BUDGET (Speech window: 19.2s): "
            "- Target voiceover length: ~12 words (acceptable range: 10 to 14 words)."
        )
        cleaned = clean_voiceover_text(raw)
        self.assertEqual(cleaned, "This is the clean spoken line.")
        self.assertNotIn("PACING BUDGET", cleaned)
        self.assertNotIn("Speech window", cleaned)

    def test_clean_voiceover_text_extracts_voiceover_tag(self):
        # Weryfikacja wyciągania treści z <voiceover>Przykładowy tekst</voiceover>
        raw = (
            "Here is the voiceover:\n"
            "<voiceover>Przykładowy tekst</voiceover>\n"
            "PACING BUDGET (Speech window: 15.0s): 10 words"
        )
        cleaned = clean_voiceover_text(raw)
        self.assertEqual(cleaned, "Przykładowy tekst")

    def test_clean_voiceover_text_removes_meta_comments(self):
        # Weryfikacja usuwania meta-komentarzy w nawiasach (Target voiceover length: ~66 words)
        raw = (
            "Automating your workstation gives you peace of mind. "
            "(Target voiceover length: ~66 words)"
        )
        cleaned = clean_voiceover_text(raw)
        self.assertEqual(cleaned, "Automating your workstation gives you peace of mind.")
        self.assertNotIn("Target voiceover length", cleaned)

    def test_strip_voice_tags_removes_all_tags(self):
        # Weryfikacja usunięcia <break time="300ms"/>, <express-as style="excited">, [sigh], <breath>
        raw = (
            '<express-as style="excited">Welcome everyone!</express-as> '
            '<break time="300ms"/> [sigh] <breath> It has been an incredible journey.'
        )
        stripped = strip_voice_tags(raw)
        self.assertEqual(stripped, "Welcome everyone! It has been an incredible journey.")
        self.assertNotIn("<break", stripped)
        self.assertNotIn("<express-as", stripped)
        self.assertNotIn("[sigh]", stripped)
        self.assertNotIn("<breath>", stripped)

    def test_strip_voice_tags_brackets_and_xml(self):
        raw = "[pause] Let us begin <strong>right now</strong>. [chuckle] [gasp]"
        stripped = strip_voice_tags(raw)
        self.assertEqual(stripped, "Let us begin right now.")

    def test_supports_voice_tags_capability_matrix(self):
        # Silniki wspierające tagi
        self.assertTrue(supports_voice_tags("edge"))
        self.assertTrue(supports_voice_tags("edge-tts"))
        self.assertTrue(supports_voice_tags("qwen"))
        self.assertTrue(supports_voice_tags("chatterbox"))

        # Silniki bez wsparcia tagów
        self.assertFalse(supports_voice_tags("kokoro"))
        self.assertFalse(supports_voice_tags("kokoclone"))
        self.assertFalse(supports_voice_tags("breeze"))

        cap_edge = get_engine_capability("edge")
        self.assertIn("break", cap_edge.allowed_tags)
        self.assertIn("prosody", cap_edge.allowed_tags)

    def test_enrich_voiceover_tags_unsupported_engine_strips_tags(self):
        # Silnik Kokoro/Breeze zawsze otrzymuje czysty tekst bez tagów
        raw = 'Hello <break time="300ms"/> [pause] world'
        res = enrich_voiceover_tags(raw, engine_type="kokoro")
        self.assertEqual(res, "Hello world")

    def test_enrich_voiceover_tags_with_mock_llm_supported_engine(self):
        original = "Automating your workstation gives you peace of mind."

        def mock_llm(_prompt):
            return "<directed_text>Automating your workstation <break time=\"300ms\"/> gives you peace of mind.</directed_text>"

        res = enrich_voiceover_tags(original, engine_type="edge", client_llm=mock_llm)
        self.assertEqual(
            res,
            'Automating your workstation <break time="300ms"/> gives you peace of mind.',
        )

    def test_enrich_voiceover_tags_fidelity_guardrail_reverts_on_hallucination(self):
        # Jeśli LLM podmienił słowa, następuje bezpieczny fallback do oryginału
        original = "Automating your workstation gives you peace of mind."

        def hallucinating_llm(_prompt):
            return "<directed_text>Building automated tools is really cool and awesome.</directed_text>"

        res = enrich_voiceover_tags(original, engine_type="edge", client_llm=hallucinating_llm)
        self.assertEqual(res, original)

    def test_enrich_voiceover_tags_llm_failure_fallback(self):
        original = "Automating your workstation gives you peace of mind."

        def failing_llm(_prompt):
            raise RuntimeError("Ollama connection timed out")

        res = enrich_voiceover_tags(original, engine_type="edge", client_llm=failing_llm)
        self.assertEqual(res, original)


if __name__ == "__main__":
    unittest.main()
