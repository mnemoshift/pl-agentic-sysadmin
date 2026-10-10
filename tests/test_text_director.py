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
    TagFormat,
    clean_voiceover_text,
    direct_voiceover,
    enrich_voiceover_tags,
    escape_raw_ampersands,
    get_engine_capability,
    prepare_edge_ssml,
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
        # Silniki wspierające tagi w tekście
        self.assertTrue(supports_voice_tags("edge"))
        self.assertTrue(supports_voice_tags("edge-tts"))
        self.assertTrue(supports_voice_tags("chatterbox"))

        # Silniki bez wsparcia tagów w tekście (Qwen używa acting_instruction, Kokoro/Breeze tylko czysty tekst)
        self.assertFalse(supports_voice_tags("qwen"))
        self.assertFalse(supports_voice_tags("kokoro"))
        self.assertFalse(supports_voice_tags("kokoclone"))
        self.assertFalse(supports_voice_tags("breeze"))

        cap_edge = get_engine_capability("edge")
        self.assertIn("break", cap_edge.allowed_tags)
        self.assertIn("prosody", cap_edge.allowed_tags)

        cap_qwen = get_engine_capability("qwen")
        self.assertEqual(cap_qwen.tag_format, TagFormat.NONE)
        self.assertFalse(cap_qwen.supports_tags)
        self.assertEqual(cap_qwen.allowed_tags, ())

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

    def test_escape_raw_ampersands_and_prepare_edge_ssml(self):
        # 1. Zwykły tekst z surowym &
        self.assertEqual(
            escape_raw_ampersands("Tom & Jerry"),
            "Tom &amp; Jerry",
        )
        self.assertEqual(
            prepare_edge_ssml("Tom & Jerry"),
            "Tom &amp; Jerry",
        )
        # 2. Tekst z już poprawną encją &amp; oraz surowym &
        self.assertEqual(
            prepare_edge_ssml("AT&T &amp; C++"),
            "AT&amp;T &amp; C++",
        )
        # 3. Tekst z tagami XML - tagi nie są zmieniane, surowe & w tekście są zamieniane
        ssml_input = '<express-as style="excited">R&D is great</express-as> <break time="300ms"/> Q&A &amp; more'
        expected = '<express-as style="excited">R&amp;D is great</express-as> <break time="300ms"/> Q&amp;A &amp; more'
        self.assertEqual(prepare_edge_ssml(ssml_input), expected)

        # 4. Encje numeryczne
        self.assertEqual(
            prepare_edge_ssml("&#160; & and &#x2F;"),
            "&#160; &amp; and &#x2F;",
        )

    def test_strip_voice_tags_decodes_entities(self):
        # strip_voice_tags usuwa tagi i dekoduje &amp; do & dla czytelnych napisów SRT
        raw = 'Tom &amp; Jerry <break time="300ms"/>'
        self.assertEqual(strip_voice_tags(raw), "Tom & Jerry")

    def test_direct_voiceover_extracts_instruction(self):
        # 1. Poprawne wyciągnięcie acting_instruction z odpowiedzi LLM
        original_text = "Why? Oh no, what happened to our deployment?"

        def mock_llm(_prompt):
            return "<acting_instruction>Deliver with intense curiosity and sudden panicked urgency, fast pacing.</acting_instruction>"

        clean_text, instruction = direct_voiceover(original_text, client_llm=mock_llm)
        self.assertEqual(clean_text, original_text)
        self.assertEqual(instruction, "Deliver with intense curiosity and sudden panicked urgency, fast pacing.")

        # 2. Upewnienie się, że tekst mówiony jest w 100% oczyszczony z tagów, jeśli wejście zawierało tagi
        dirty_input = "[curious] Why? <break time='200ms'/> Oh no! [panicked]"
        clean_text_dirty, instruction_dirty = direct_voiceover(dirty_input, client_llm=mock_llm)
        self.assertEqual(clean_text_dirty, "Why? Oh no!")
        self.assertEqual(instruction_dirty, "Deliver with intense curiosity and sudden panicked urgency, fast pacing.")

    def test_direct_voiceover_fallback(self):
        original = "Automating your workstation gives you peace of mind."
        default_inst = "Speak naturally in a clear, engaging tone."

        # 1. client_llm is None -> zwraca czysty tekst i domyślną instrukcję
        clean_text, instruction = direct_voiceover(original, client_llm=None)
        self.assertEqual(clean_text, original)
        self.assertEqual(instruction, default_inst)

        # 2. client_llm zgłasza błąd -> fallback do domyślnej instrukcji
        def failing_llm(_prompt):
            raise RuntimeError("LLM request failed")

        clean_failing, inst_failing = direct_voiceover(original, client_llm=failing_llm)
        self.assertEqual(clean_failing, original)
        self.assertEqual(inst_failing, default_inst)

        # 3. Pusty tekst wejściowy
        clean_empty, inst_empty = direct_voiceover("", client_llm=None)
        self.assertEqual(clean_empty, "")
        self.assertEqual(inst_empty, default_inst)

    def test_strip_voice_tags_multiword_brackets(self):
        # Weryfikacja całkowitego wycięcia tagów wielowyrazowych ze spacjami dla napisów SRT/ASS
        raw = "[very slowly]Proceed with caution, [clears throat] please."
        stripped = strip_voice_tags(raw)
        self.assertEqual(stripped, "Proceed with caution, please.")
        self.assertNotIn("[clears throat]", stripped)
        self.assertNotIn("[very slowly]", stripped)
        self.assertNotIn("clears throat", stripped)
        self.assertNotIn("very slowly", stripped)

        # Inne złożone tagi Qwen
        raw2 = "[like dracula]Welcome to the castle [deep and loud shouting]everyone!"
        self.assertEqual(strip_voice_tags(raw2), "Welcome to the castle everyone!")


if __name__ == "__main__":
    unittest.main()

