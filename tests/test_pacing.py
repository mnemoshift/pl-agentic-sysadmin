#!/usr/bin/env python3
"""
Testy jednostkowe dla potoku dubbingu wideo (scripts/media/dub_video.py).
Weryfikują:
- compute_pacing_target (budżetowanie słów i dopasowanie do gęstości PL)
- clean_llm_translation (usuwanie znaczników metadanych i prefiksów LLM)
- apply_tech_terms (podmiana terminów IT z granicami słów)
- resolve_reference_audio (wyszukiwanie próbek głosu referencyjnego)
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "media"))

from dub_video import (  # noqa: E402
    PacingTarget,
    apply_asr_corrections,
    apply_tech_terms,
    clean_llm_translation,
    clean_voiceover_text,
    compute_pacing_target,
    group_whisper_segments,
    resolve_reference_audio,
    resolve_work_dir,
)


class TestPacingController(unittest.TestCase):
    def test_compute_pacing_target_continuous(self):
        # Mowa ciągła (window=24.0s, orig_pause=0.0s, pl_words=46)
        pt = compute_pacing_target(window_dur=24.0, orig_pause=0.0, pl_words=46)
        self.assertIsInstance(pt, PacingTarget)
        self.assertEqual(pt.window_dur, 24.0)
        self.assertEqual(pt.desired_gap, 1.2)
        self.assertEqual(pt.min_acceptable_gap, 0.4)
        self.assertEqual(pt.max_acceptable_gap, 3.2)
        # Cel powinien mieścić się w logicznym zakresie ekspansji
        self.assertTrue(50 <= pt.target_words <= 75)
        self.assertTrue(pt.min_words <= pt.target_words <= pt.max_words)

    def test_compute_pacing_target_demonstration_pause(self):
        # Pauza demonstracyjna (window=20.0s, orig_pause=3.5s, pl_words=25)
        pt = compute_pacing_target(window_dur=20.0, orig_pause=3.5, pl_words=25)
        self.assertEqual(pt.desired_gap, 3.5)
        self.assertGreaterEqual(pt.min_acceptable_gap, 2.0)
        self.assertLessEqual(pt.speech_target_sec, 16.5)

    def test_clean_llm_translation_filters_metadata(self):
        raw = "Here is the natural spoken English translation:\n\n\"Zorin OS. Just a week ago, this concept didn't exist for me. Today, it's my daily workstation.\" (Word count: 17) [pause]"
        cleaned = clean_llm_translation(raw)
        self.assertEqual(
            cleaned,
            "Zorin OS. Just a week ago, this concept didn't exist for me. Today, it's my daily workstation.",
        )
        self.assertNotIn("Word count", cleaned)
        self.assertNotIn("Here is", cleaned)
        self.assertNotIn("[pause]", cleaned)

    def test_clean_voiceover_text_extracts_voiceover_tag(self):
        raw = (
            "Here is the result you requested:\n"
            "<voiceover>Automating your workstation gives you peace of mind.</voiceover>\n"
            "PACING BUDGET (Speech window: 24.0s):\n"
            "- Target voiceover length: ~15 words"
        )
        cleaned = clean_voiceover_text(raw)
        self.assertEqual(cleaned, "Automating your workstation gives you peace of mind.")

    def test_clean_voiceover_text_cuts_pacing_budget_leak(self):
        raw = (
            "\"This is the clean spoken line.\" PACING BUDGET (Speech window: 12.0s): "
            "- Target voiceover length: ~8 words (acceptable range: 6 to 10 words)."
        )
        cleaned = clean_voiceover_text(raw)
        self.assertEqual(cleaned, "This is the clean spoken line.")

    def test_clean_voiceover_text_removes_bracketed_metadata_and_quotes(self):
        raw = "   \"Every developer needs a reliable setup.\" [Speech window: 15.0s] (Target voiceover length: ~10 words)   "
        cleaned = clean_voiceover_text(raw)
        self.assertEqual(cleaned, "Every developer needs a reliable setup.")

    def test_clean_voiceover_text_strips_source_text_tags(self):
        raw = (
            "<source_text>Oto tekst źródłowy</source_text>\n"
            "<voiceover>Here is the spoken output.</voiceover>"
        )
        cleaned = clean_voiceover_text(raw)
        self.assertEqual(cleaned, "Here is the spoken output.")

    def test_apply_tech_terms_word_boundaries(self):
        tech_terms = {
            "kodek": "Codex",
            "Kodeksie": "Codex",
            "dok": "dock",
            "Zorin OS": "Zorin OS",
        }
        # Słowo w odmianie ze słownika powinno być podmienione
        text1 = "Możesz to zestawić w Kodeksie."
        self.assertEqual(apply_tech_terms(text1, tech_terms), "Możesz to zestawić w Codex.")

        # Słowo 'dokładnie' NIE powinno zostać zepsute na 'dockładnie'
        text2 = "Dokładnie tak to działa w doku."
        self.assertEqual(apply_tech_terms(text2, tech_terms), "Dokładnie tak to działa w doku.")

    def test_resolve_reference_audio_explicit(self):
        sample_path = REPO_ROOT / "work" / "voice_sample" / "ref_voice_sample.wav"
        if sample_path.exists():
            ref_audio, ref_transcript = resolve_reference_audio(ref_audio=sample_path)
            self.assertIsNotNone(ref_audio)
            self.assertTrue(ref_audio.exists())
            self.assertEqual(ref_audio.name, "ref_voice_sample.wav")

    def test_resolve_reference_audio_nonexistent_raises(self):
        with self.assertRaises(FileNotFoundError):
            resolve_reference_audio(ref_audio="nonexistent_sample_xyz.wav")

    def test_resolve_work_dir_conventions(self):
        expected = (REPO_ROOT / "work" / "EP002_Short").resolve()
        self.assertEqual(resolve_work_dir("EP002_Short"), expected)
        self.assertEqual(resolve_work_dir("work/EP002_Short"), expected)
        self.assertEqual(resolve_work_dir(expected), expected)

    def test_apply_asr_corrections_agentic_sysadmin(self):
        # Weryfikacja korekty fonetycznej ASR dla pojęć inżynierskich
        sample_text = "To jest AgentXsAdmin oraz Agent XsAdmin w środowisku Zorin OS."
        corrected = apply_asr_corrections(sample_text)
        self.assertIn("Agentic SysAdmin", corrected)
        self.assertNotIn("AgentXsAdmin", corrected)
        self.assertNotIn("Agent XsAdmin", corrected)

    def test_group_whisper_segments_adaptive_shorts(self):
        # 6 krótkich zdań o łącznym czasie 30s
        raw_cleaned = [
            {"id": 1, "start": 0.0, "end": 4.5, "text": "Pierwsze krótkie zdanie."},
            {"id": 2, "start": 4.8, "end": 9.2, "text": "Drugie zdanie z kropką."},
            {"id": 3, "start": 9.5, "end": 14.8, "text": "Trzecia kwestia o agentach."},
            {"id": 4, "start": 15.2, "end": 20.0, "text": "Czwarty segment prezentacji."},
            {"id": 5, "start": 20.4, "end": 25.1, "text": "Piąte zdanie podsumowania."},
            {"id": 6, "start": 25.5, "end": 30.0, "text": "Finałowe pożegnanie z widzami."},
        ]
        # Dla krótkich materiałów (total_duration <= 120s) podział powinien zachować krótkie kwestie (nie scalać do 28s)
        scenes = group_whisper_segments(raw_cleaned, chunk_mode="short", total_duration=30.0)
        self.assertGreaterEqual(len(scenes), 4)
        for sc in scenes:
            dur = sc["end"] - sc["start"]
            self.assertLessEqual(dur, 8.5)

    def test_compute_pacing_target_short_scene(self):
        # Krótka scena (window=5.0s, orig_pause=0.3s, pl_words=10)
        pt = compute_pacing_target(window_dur=5.0, orig_pause=0.3, pl_words=10)
        self.assertEqual(pt.desired_gap, 0.3)
        self.assertEqual(pt.min_acceptable_gap, 0.15)
        self.assertLessEqual(pt.max_acceptable_gap, 1.2)
        self.assertLessEqual(pt.target_words, 12)


if __name__ == "__main__":
    unittest.main()

