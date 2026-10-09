#!/usr/bin/env python3
"""
Testy jednostkowe dla potoku dubbingu wideo (scripts/media/dub_video.py).
Weryfikują:
- compute_pacing_target (budżetowanie słów i dopasowanie do gęstości PL)
- clean_llm_translation (usuwanie znaczników metadanych i prefiksów LLM)
- apply_tech_terms (podmiana terminów IT z granicami słów)
- resolve_reference_audio (wyszukiwanie próbek głosu referencyjnego)
"""

import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "media"))

from dub_video import (
    compute_pacing_target,
    clean_llm_translation,
    apply_tech_terms,
    resolve_reference_audio,
    PacingTarget,
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
            "Zorin OS. Just a week ago, this concept didn't exist for me. Today, it's my daily workstation."
        )
        self.assertNotIn("Word count", cleaned)
        self.assertNotIn("Here is", cleaned)
        self.assertNotIn("[pause]", cleaned)

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

    def test_resolve_reference_audio(self):
        ref_audio, ref_transcript = resolve_reference_audio()
        self.assertIsNotNone(ref_audio)
        self.assertTrue(ref_audio.exists())
        self.assertIsInstance(ref_transcript, str)


if __name__ == "__main__":
    unittest.main()
