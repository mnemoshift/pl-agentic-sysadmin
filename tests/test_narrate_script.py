#!/usr/bin/env python3
"""
Testy jednostkowe dla modułu narracji skryptu Markdown (scripts/media/narrate_script.py).
Weryfikują:
1. test_markdown_cleaning: usuwanie znaczników Markdown, linków, kodów i nagłówków bez utraty słów.
2. test_semantic_chunking: podział na zdania, ochronę skrótów (np., tzn., m.in., 3.14) i flagę is_paragraph_end.
3. test_srt_generation: poprawność i precyzję kalkulacji timecodów SRT przy zadanych sztucznych długościach i pauzach.
4. test_cli_argument_defaults: domyślne parametry CLI i parsera argumentów.
5. test_detect_script_language: autodetekcję języka tekstu (PL vs EN).
6. test_pipeline_integration_mocked: pełny przebieg pipeline'u z syntetycznym silnikiem TTS.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys_path = str(REPO_ROOT / "scripts" / "media")
if sys_path not in os.sys.path:
    os.sys.path.insert(0, sys_path)

from narrate_script import (  # noqa: E402
    ScriptChunk,
    ScriptChunker,
    create_argument_parser,
    detect_script_language,
    generate_srt_content,
    run_script_narration,
    sec_to_srt_time,
)


class TestNarrateScript(unittest.TestCase):
    def setUp(self):
        self.chunker = ScriptChunker()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_markdown_cleaning(self):
        """Sprawdza, czy usuwane są gwiazdki, linki, kody i formatowanie nagłówków bez utraty słów."""
        raw_markdown = (
            "### Tytuł Rozdziału Pierwszego\n\n"
            "Oto **ważny tekst**, który zawiera *kursywę*, a także `kod inline` oraz "
            "[odnośnik do dokumentacji](https://example.com/docs).\n\n"
            "```python\n"
            "def ignorowany_kod():\n"
            "    pass\n"
            "```\n\n"
            "> Cytat blokowy z cenną myślą.\n\n"
            "---"
        )

        chunks = self.chunker.parse(raw_markdown)
        self.assertGreater(len(chunks), 0)

        all_text = " ".join(c.text for c in chunks)

        # Słowa kluczowe muszą być zachowane
        self.assertIn("Tytuł Rozdziału Pierwszego", all_text)
        self.assertIn("ważny tekst", all_text)
        self.assertIn("kursywę", all_text)
        self.assertIn("kod inline", all_text)
        self.assertIn("odnośnik do dokumentacji", all_text)
        self.assertIn("Cytat blokowy z cenną myślą", all_text)

        # Składnia Markdown musi być usunięta
        self.assertNotIn("**", all_text)
        self.assertNotIn("`", all_text)
        self.assertNotIn("https://example.com", all_text)
        self.assertNotIn("def ignorowany_kod", all_text)
        self.assertNotIn("###", all_text)
        self.assertNotIn("---", all_text)

    def test_semantic_chunking(self):
        """Sprawdza, czy podział na zdania nie rozbija skrótów i poprawnie oznacza granice akapitów."""
        text_with_abbr = (
            "# Nagłówek Sekcji\n\n"
            "Mamy np. trzy opcje wyboru, tzn. pierwszą, drugą i trzecią. "
            "Liczba Pi to w przybliżeniu 3.14, co jest ciekawe. "
            "W 2026 r. wprowadzono m.in. nowoczesne algorytmy oraz inne usprawnienia!\n\n"
            "Drugi samodzielny akapit tekstu."
        )

        chunks = self.chunker.parse(text_with_abbr)

        # Sprawdzenie pierwszego chunka (nagłówek jako osobny blok)
        self.assertEqual(chunks[0].text, "Nagłówek Sekcji.")
        self.assertTrue(chunks[0].is_paragraph_end)

        # Sprawdzenie ochrony skrótów - zdania nie mogą być pocięte wewnątrz skrótów
        sentences_p1 = [c.text for c in chunks if "Mamy np." in c.text or "Liczba Pi" in c.text or "W 2026 r." in c.text]
        self.assertEqual(len(sentences_p1), 3)

        self.assertIn("Mamy np. trzy opcje wyboru, tzn. pierwszą, drugą i trzecią.", sentences_p1[0])
        self.assertIn("Liczba Pi to w przybliżeniu 3.14, co jest ciekawe.", sentences_p1[1])
        self.assertIn("W 2026 r. wprowadzono m.in. nowoczesne algorytmy oraz inne usprawnienia!", sentences_p1[2])

        # Weryfikacja flagi is_paragraph_end
        # W akapicie 1: zdanie 1 (False), zdanie 2 (False), zdanie 3 (True)
        chunk_map = {c.text: c.is_paragraph_end for c in chunks}
        self.assertFalse(chunk_map[sentences_p1[0]])
        self.assertFalse(chunk_map[sentences_p1[1]])
        self.assertTrue(chunk_map[sentences_p1[2]])

        # W akapicie 2: pojedyncze zdanie (True)
        self.assertTrue(chunk_map["Drugi samodzielny akapit tekstu."])

    def test_semantic_chunking_long_sentence(self):
        """Sprawdza bezpieczne dzielenie zdań przekraczających limit 350 znaków."""
        long_sentence = (
            "Architektura stacji roboczej opiera się na wielu niezależnych warstwach, "
            "w tym na automatyzacji środowiska użytkownika, precyzyjnym monitorowaniu procesów systemowych, "
            "zaawansowanym zarządzaniu profilami monitorów i doku emisyjnego, a także na w pełni autonomicznym "
            "przetwarzaniu sygnałów audio z wykorzystaniem lokalnych modeli sztucznej inteligencji, co pozwala "
            "na całkowite wyeliminowanie konieczności ręcznego montażu i korekcji nagrań lektorskich."
        )
        self.assertGreater(len(long_sentence), 350)

        chunks = self.chunker.parse(long_sentence)
        self.assertGreater(len(chunks), 1)

        for c in chunks:
            self.assertLessEqual(len(c.text), 350)

        # Tylko ostatni sub-chunk powinien mieć is_paragraph_end = True
        self.assertFalse(chunks[0].is_paragraph_end)
        self.assertTrue(chunks[-1].is_paragraph_end)

    def test_srt_generation(self):
        """Sprawdza poprawność kalkulacji timecodów w SRT przy zadanych sztucznych długościach audio i pauzach."""
        chunks = [
            ScriptChunk(index=1, text="Pierwsze zdanie narracji.", is_paragraph_end=False),
            ScriptChunk(index=2, text="Drugie zdanie w tym samym akapicie.", is_paragraph_end=True),
            ScriptChunk(index=3, text="Trzecie zdanie w nowym akapicie.", is_paragraph_end=True),
        ]

        durations = [2.5, 3.0, 1.8]
        # Pauza między zdaniami 0.3s, pauza między akapitami 0.75s
        pauses = [0.3, 0.75]

        srt_output = generate_srt_content(chunks, durations, pauses)

        self.assertIn("1\n00:00:00,000 --> 00:00:02,500\nPierwsze zdanie narracji.", srt_output)
        # 2.5 + 0.3 = 2.800 start, trwanie 3.0 -> koniec 5.800
        self.assertIn("2\n00:00:02,800 --> 00:00:05,800\nDrugie zdanie w tym samym akapicie.", srt_output)
        # 5.8 + 0.75 = 6.550 start, trwanie 1.8 -> koniec 8.350
        self.assertIn("3\n00:00:06,550 --> 00:00:08,350\nTrzecie zdanie w nowym akapicie.", srt_output)

    def test_sec_to_srt_time(self):
        """Weryfikacja formatowania czasu SRT."""
        self.assertEqual(sec_to_srt_time(0.0), "00:00:00,000")
        self.assertEqual(sec_to_srt_time(1.234), "00:00:01,234")
        self.assertEqual(sec_to_srt_time(65.5), "00:01:05,500")
        self.assertEqual(sec_to_srt_time(3661.05), "01:01:01,050")

    def test_detect_script_language(self):
        """Weryfikacja wykrywania języka tekstu."""
        pl_text = "To jest w pełni zautomatyzowany skrypt lektorski w języku polskim."
        en_text = "This is a fully automated script narrator using neural speech synthesis."

        self.assertEqual(detect_script_language(pl_text), "pl")
        self.assertEqual(detect_script_language(en_text), "en")

    def test_cli_argument_defaults(self):
        """Weryfikacja domyślnych wartości argumentów parsera CLI."""
        parser = create_argument_parser()
        args = parser.parse_args(["-i", "test.md"])

        self.assertEqual(args.input, Path("test.md"))
        self.assertEqual(args.engine, "kokoclone")
        self.assertEqual(args.ref_audio, Path("voice/sample_reference.wav"))
        self.assertEqual(args.lang, "auto")
        self.assertIsNone(args.voice)
        self.assertFalse(args.expressive)
        self.assertTrue(args.generate_subtitles)
        self.assertEqual(args.pause_sentence, 300)
        self.assertEqual(args.pause_paragraph, 750)

    @patch("narrate_script.get_tts_engine")
    @patch("narrate_script.concatenate_and_master_narration")
    @patch("narrate_script.get_audio_duration")
    def test_pipeline_integration_mocked(
        self,
        mock_duration: MagicMock,
        mock_concat: MagicMock,
        mock_get_tts: MagicMock,
    ):
        """Test integracyjny przepływu z zamockowanym silnikiem TTS i syntezą."""
        mock_duration.return_value = 2.0

        def fake_concat(audio_paths, output_wav, **kwargs):
            import numpy as np
            import soundfile as sf

            output_wav.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(output_wav), np.zeros(24000 * 2, dtype=np.float32), 24000)

        mock_concat.side_effect = fake_concat

        mock_engine = MagicMock()
        mock_engine.synthesize.return_value = True
        mock_get_tts.return_value = mock_engine

        test_md = self.temp_path / "sample_script.md"
        test_md.write_text("# Testowy Nagłówek\n\nPierwsze zdanie testowe.\n", encoding="utf-8")

        out_dir = self.temp_path / "custom_run"

        success = run_script_narration(
            input_file=test_md,
            engine_name="edge",
            ref_audio=None,
            lang="pl",
            output_dir=out_dir,
            pause_sentence_ms=200,
            pause_paragraph_ms=500,
        )

        self.assertTrue(success)
        self.assertTrue((out_dir / "06_output" / "narration_summary.md").exists())
        self.assertTrue((out_dir / "06_output" / "narration.srt").exists())
        self.assertTrue((out_dir / "run_summary.json").exists())
        self.assertTrue((out_dir / "01_source_extracted" / "chunks.json").exists())


if __name__ == "__main__":
    unittest.main()
