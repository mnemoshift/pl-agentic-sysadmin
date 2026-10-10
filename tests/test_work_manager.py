#!/usr/bin/env python3
"""
Testy jednostkowe dla modułu WorkRunManager oraz QualityAnalyzer (scripts/media/work_manager.py).
Weryfikują:
- test_workspace_creation_and_hierarchy (tworzenie katalogu runu i etapów 01_* do 06_*)
- test_symlink_latest_update (atomowa aktualizacja symlinku work/latest)
- test_quality_analyzer_metrics (kalkulacja WPM, delty czasu, peak dB, clipping, cisza)
- test_run_summary_serialization (format i zawartość pliku run_summary.json)
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parent.parent
sys_path = str(REPO_ROOT / "scripts" / "media")
if sys_path not in os.sys.path:
    os.sys.path.insert(0, sys_path)

from work_manager import (  # noqa: E402
    ALL_STAGE_FOLDERS,
    QualityAnalyzer,
    WorkRunManager,
)


class TestWorkRunManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name) / "work"
        self.runs_dir = self.work_dir / "runs"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_workspace_creation_and_hierarchy(self):
        """Weryfikacja poprawnego utworzenia folderów etapów 01_* do 06_* oraz logs."""
        mgr = WorkRunManager(
            task_slug="test_short",
            engine="edge",
            base_dir=self.runs_dir,
        )

        self.assertTrue(mgr.run_dir.exists())
        self.assertTrue(mgr.run_dir.is_dir())
        self.assertIn("edge_test_short", mgr.run_dir.name)

        # Sprawdzenie obecności wszystkich podfolderów etapowych
        for stage_folder in ALL_STAGE_FOLDERS:
            folder_path = mgr.run_dir / stage_folder
            self.assertTrue(folder_path.exists(), f"Brak folderu etapu: {stage_folder}")
            self.assertTrue(folder_path.is_dir())

        # Test zapisu artefaktów przez save_artifact
        txt_path = mgr.save_artifact("02_transcription", "test.txt", "Przykładowa transkrypcja")
        self.assertTrue(txt_path.exists())
        self.assertEqual(txt_path.read_text(encoding="utf-8"), "Przykładowa transkrypcja")

        json_path = mgr.save_artifact("03_llm_adaptation", "data.json", {"key": "value"})
        self.assertTrue(json_path.exists())
        self.assertEqual(json.loads(json_path.read_text(encoding="utf-8")), {"key": "value"})

    def test_symlink_latest_update(self):
        """Sprawdzenie, czy work/latest poprawnie wskazuje na bieżący run i aktualizuje się."""
        mgr1 = WorkRunManager(
            task_slug="first_run",
            engine="edge",
            base_dir=self.runs_dir,
        )
        latest_link = self.work_dir / "latest"

        self.assertTrue(latest_link.exists())
        self.assertTrue(latest_link.is_symlink())
        self.assertEqual(latest_link.resolve(), mgr1.run_dir.resolve())

        # Drugi przebieg - symlink powinien wskazywać na nowy run
        mgr2 = WorkRunManager(
            task_slug="second_run",
            engine="qwen",
            base_dir=self.runs_dir,
        )
        self.assertTrue(latest_link.exists())
        self.assertEqual(latest_link.resolve(), mgr2.run_dir.resolve())
        self.assertNotEqual(mgr1.run_dir, mgr2.run_dir)

    def test_quality_analyzer_metrics(self):
        """Sprawdzenie kalkulacji WPM, delty czasowej oraz flagi przesterowania na syntetycznym pliku WAV."""
        sr = 24000
        duration_sec = 2.0
        t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)

        # 1. Czysty ton bez przesterowania (amplituda 0.5 -> ok. -6 dBFS)
        clean_audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        clean_wav_path = Path(self.temp_dir.name) / "clean.wav"
        sf.write(str(clean_wav_path), clean_audio, sr)

        analyzer = QualityAnalyzer()
        # 5 słów w 2.0s -> 5 / (2/60) = 150 WPM (w normie 110-170)
        text = "This is a clean voiceover"
        metrics_clean = analyzer.analyze_output(
            audio_path=clean_wav_path,
            target_speech_window=2.05,
            voiceover_text=text,
        )

        self.assertAlmostEqual(metrics_clean.audio_duration_sec, 2.0, delta=0.05)
        self.assertAlmostEqual(metrics_clean.drift_seconds, 0.05, delta=0.05)
        self.assertFalse(metrics_clean.drift_warning)
        self.assertEqual(metrics_clean.word_count, 5)
        self.assertAlmostEqual(metrics_clean.wpm, 150.0, delta=5.0)
        self.assertFalse(metrics_clean.pacing_warning)
        self.assertFalse(metrics_clean.is_clipping)
        self.assertAlmostEqual(metrics_clean.peak_db, -6.02, delta=0.2)
        self.assertEqual(metrics_clean.overall_quality_status, "PASSED")

        # 2. Sygnał przesterowany (amplituda 1.0)
        clipped_audio = np.ones(int(sr * 1.0), dtype=np.float32)
        clipped_wav_path = Path(self.temp_dir.name) / "clipped.wav"
        sf.write(str(clipped_wav_path), clipped_audio, sr)

        metrics_clipped = analyzer.analyze_output(
            audio_path=clipped_wav_path,
            target_speech_window=1.0,
            voiceover_text="Quick test",
        )
        self.assertTrue(metrics_clipped.is_clipping)
        self.assertEqual(metrics_clipped.overall_quality_status, "WARNING")

        # 3. Sygnał z nienaturalną pustą przerwą > 1.5s w środku mowy
        # 0.5s mowy + 1.8s ciszy + 0.5s mowy
        part_speech = (0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, int(sr * 0.5)))).astype(np.float32)
        part_silence = np.zeros(int(sr * 1.8), dtype=np.float32)
        silent_audio = np.concatenate([part_speech, part_silence, part_speech])
        silent_wav_path = Path(self.temp_dir.name) / "silent.wav"
        sf.write(str(silent_wav_path), silent_audio, sr)

        metrics_silence = analyzer.analyze_output(
            audio_path=silent_wav_path,
            target_speech_window=2.8,
            voiceover_text="Start pause end",
        )
        self.assertTrue(metrics_silence.unnatural_silence_detected)
        self.assertGreaterEqual(metrics_silence.max_internal_silence_sec, 1.7)
        self.assertEqual(metrics_silence.overall_quality_status, "WARNING")

    def test_run_summary_serialization(self):
        """Weryfikacja poprawności formatu i zawartości generowanego pliku run_summary.json."""
        mgr = WorkRunManager(
            task_slug="summary_test",
            engine="edge",
            base_dir=self.runs_dir,
        )

        with mgr.measure_stage("transcription"):
            pass

        with mgr.measure_stage("llm_adaptation"):
            pass

        mgr.record_stats(source_words=45, target_words=52, target_window_sec=18.0, actual_audio_sec=17.9)

        # Syntetyczna analiza jakości
        dummy_quality = {
            "audio_duration_sec": 17.9,
            "target_window_sec": 18.0,
            "drift_seconds": 0.1,
            "drift_warning": False,
            "word_count": 52,
            "wpm": 152.0,
            "pacing_warning": False,
            "peak_db": -1.2,
            "rms_db": -16.5,
            "is_clipping": False,
            "max_internal_silence_sec": 0.4,
            "unnatural_silence_detected": False,
            "overall_quality_status": "PASSED",
        }

        summary_file = mgr.finish_run(quality_analysis=dummy_quality)
        self.assertTrue(summary_file.exists())
        self.assertEqual(summary_file.name, "run_summary.json")

        content = json.loads(summary_file.read_text(encoding="utf-8"))
        self.assertIn("meta", content)
        self.assertIn("stages_timing", content)
        self.assertIn("stats", content)
        self.assertIn("quality_analysis", content)

        self.assertEqual(content["meta"]["task_slug"], "summary_test")
        self.assertEqual(content["meta"]["engine"], "edge")
        self.assertIn("transcription", content["stages_timing"])
        self.assertIn("llm_adaptation", content["stages_timing"])
        self.assertEqual(content["stats"]["source_words"], 45)
        self.assertEqual(content["quality_analysis"]["overall_quality_status"], "PASSED")

    def test_capture_logs_tee_stream(self):
        """Weryfikacja przechwytywania logów konsolowych do execution.log."""
        mgr = WorkRunManager(
            task_slug="log_test",
            engine="edge",
            base_dir=self.runs_dir,
        )

        with mgr.capture_logs():
            print("To jest testowy komunikat na stdout")
            print("To jest testowy komunikat na stderr", file=os.sys.stderr)

        log_file = mgr.logs_dir / "execution.log"
        self.assertTrue(log_file.exists())
        log_content = log_file.read_text(encoding="utf-8")
        self.assertIn("To jest testowy komunikat na stdout", log_content)

    def test_explicit_output_dir(self):
        """Weryfikacja trybu z jawnie wskazanym katalogiem wyjściowym (explicit_output_dir)."""
        explicit_dir = Path(self.temp_dir.name) / "custom_output"
        mgr = WorkRunManager(
            task_slug="custom_task",
            engine="edge",
            explicit_output_dir=explicit_dir,
        )

        self.assertTrue(mgr.is_explicit)
        self.assertEqual(mgr.run_dir.resolve(), explicit_dir.resolve())
        self.assertTrue(explicit_dir.exists())

        # Sprawdzenie obecności podfolderów etapowych w jawnie wskazanym katalogu
        for stage_folder in ALL_STAGE_FOLDERS:
            folder_path = explicit_dir / stage_folder
            self.assertTrue(folder_path.exists(), f"Brak folderu etapu: {stage_folder}")

        with mgr.capture_logs():
            print("Wiadomość z jawnego katalogu")

        summary_file = mgr.finish_run()
        self.assertTrue(summary_file.exists())
        self.assertEqual(summary_file.parent.resolve(), explicit_dir.resolve())
        self.assertTrue((explicit_dir / "logs" / "execution.log").exists())

    def test_quality_analyzer_zero_duration_protects_wpm(self):
        """Weryfikacja zabezpieczenia przed dzieleniem przez zero w QualityAnalyzer."""
        sr = 24000
        empty_wav_path = Path(self.temp_dir.name) / "empty.wav"
        # Plik o zerowej liczbie próbek
        sf.write(str(empty_wav_path), np.array([], dtype=np.float32), sr)

        analyzer = QualityAnalyzer()
        metrics = analyzer.analyze_output(
            audio_path=empty_wav_path,
            target_speech_window=0.0,
            voiceover_text="Some text here",
        )
        self.assertEqual(metrics.audio_duration_sec, 0.0)
        self.assertEqual(metrics.wpm, 0.0)
        self.assertFalse(metrics.pacing_warning)

    def test_remove_latest_symlink(self):
        """Weryfikacja bezpiecznego usuwania symlinka latest (w tym broken symlink)."""
        mgr = WorkRunManager(
            task_slug="symlink_cleanup_test",
            engine="edge",
            base_dir=self.runs_dir,
        )
        latest_link = self.work_dir / "latest"
        self.assertTrue(latest_link.exists() or latest_link.is_symlink())

        # Bezpieczne usunięcie
        mgr.remove_latest_symlink()
        self.assertFalse(latest_link.is_symlink())
        self.assertFalse(latest_link.exists())

        # Powtórne usunięcie (missing_ok) nie powinno rzucać wyjątku
        mgr.remove_latest_symlink()


if __name__ == "__main__":
    unittest.main()

