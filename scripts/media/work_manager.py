#!/usr/bin/env python3
"""
Workstation Hub: Moduł zarządzania sesją roboczą (WorkRunManager)
oraz automatycznej analizy jakości (QualityAnalyzer).

Zapewnia:
1. Wersjonowanie przebiegów w katalogu work/runs/YYYY-MM-DD_HH-MM-SS_<engine>_<slug>/
2. Bezpieczny atomowy symlink work/latest wskazujący na ostatni przebieg
3. Przechwytywanie pełnego strumienia konsoli (Tee logging do logs/execution.log)
4. Porządkowanie plików w podkatalogach etapowych (01_source_extracted do 06_output)
5. Pomiary czasu poszczególnych faz oraz metadane środowiskowe
6. Automatyczną analizę jakości efektu końcowego (WPM, dryf czasu, przesterowania, cisza)
7. Generowanie zbiorczego raportu run_summary.json
"""

import json
import logging
import os
import platform
import re
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_RUNS_DIR = REPO_ROOT / "work" / "runs"

STAGE_SOURCE_EXTRACTED = "01_source_extracted"
STAGE_TRANSCRIPTION = "02_transcription"
STAGE_LLM_ADAPTATION = "03_llm_adaptation"
STAGE_TTS_SEGMENTS = "04_tts_segments"
STAGE_SUBTITLES = "05_subtitles"
STAGE_OUTPUT = "06_output"

ALL_STAGE_FOLDERS = (
    "logs",
    STAGE_SOURCE_EXTRACTED,
    STAGE_TRANSCRIPTION,
    STAGE_LLM_ADAPTATION,
    STAGE_TTS_SEGMENTS,
    STAGE_SUBTITLES,
    STAGE_OUTPUT,
)


class TeeStream:
    """Strumień I/O duplikujący zapis na terminal i do pliku logu execution.log."""

    def __init__(self, original_stream: TextIO, log_file: TextIO):
        self.original_stream = original_stream
        self.log_file = log_file

    def write(self, data: str) -> int:
        self.original_stream.write(data)
        self.original_stream.flush()
        self.log_file.write(data)
        self.log_file.flush()
        return len(data)

    def flush(self) -> None:
        self.original_stream.flush()
        self.log_file.flush()

    def isatty(self) -> bool:
        return getattr(self.original_stream, "isatty", lambda: False)()

    def fileno(self) -> int:
        return self.original_stream.fileno()


@dataclass(frozen=True, slots=True)
class QualityMetrics:
    audio_duration_sec: float
    target_window_sec: float
    drift_seconds: float
    drift_warning: bool
    word_count: int
    wpm: float
    pacing_warning: bool
    peak_db: float
    rms_db: float
    is_clipping: bool
    max_internal_silence_sec: float
    unnatural_silence_detected: bool
    overall_quality_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QualityAnalyzer:
    """Automatyczny audytor jakości wygenerowanego materiału audio i wideo."""

    def __init__(
        self,
        min_wpm: float = 110.0,
        max_wpm: float = 170.0,
        max_acceptable_drift_sec: float = 2.0,
        silence_threshold_amp: float = 0.005,  # ok. -46 dB
        max_internal_silence_sec: float = 1.5,
    ):
        self.min_wpm = min_wpm
        self.max_wpm = max_wpm
        self.max_acceptable_drift_sec = max_acceptable_drift_sec
        self.silence_threshold_amp = silence_threshold_amp
        self.max_internal_silence_sec = max_internal_silence_sec

    def analyze_output(
        self,
        audio_path: Path,
        target_speech_window: float = 0.0,
        voiceover_text: str = "",
        video_path: Path | None = None,
    ) -> QualityMetrics:
        """
        Ocenia jakość wygenerowanego lektora:
        - Oblicza dryf czasu względem zadanego okna mowy / długości wideo.
        - Kalkuluje tempo mowy w słowach na minutę (WPM) i weryfikuje zakres pacingu.
        - Sprawdza poziomy głośności (Peak dB, RMS dB) oraz wykrywa przesterowania.
        - Identyfikuje nienaturalne puste pauzy (> 1.5s w środku kwestii).
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Plik audio do analizy nie istnieje: {audio_path}")

        # Odczyt danych i metadanych audio
        data, sample_rate = sf.read(str(audio_path), dtype="float32")
        duration = float(len(data) / sample_rate) if sample_rate > 0 else 0.0

        # Przekształcenie stereo do mono na potrzeby analizy głośności
        if data.ndim > 1:
            mono_data = np.mean(data, axis=1)
        else:
            mono_data = data

        # 1. Audio Duration & Drift
        target_window = float(target_speech_window)
        if target_window > 0.0:
            drift = round(abs(duration - target_window), 3)
            drift_warning = drift > self.max_acceptable_drift_sec
        else:
            drift = 0.0
            drift_warning = False

        # 2. Pacing Metrics
        actual_duration = float(duration)
        words = len(re.findall(r"\b\w+\b", voiceover_text)) if voiceover_text else 0
        if actual_duration <= 0.0 or words == 0:
            wpm = 0.0
            pacing_warning = False
        else:
            wpm = round((words / (actual_duration / 60.0)), 1)
            pacing_warning = wpm < self.min_wpm or wpm > self.max_wpm

        # 3. Audio Integrity (Peak, RMS, Clipping)
        if len(mono_data) > 0:
            peak = float(np.max(np.abs(mono_data)))
            peak_db = round(float(20 * np.log10(peak)), 2) if peak > 1e-6 else -100.0
            rms = float(np.sqrt(np.mean(mono_data**2)))
            rms_db = round(float(20 * np.log10(rms)), 2) if rms > 1e-6 else -100.0
        else:
            peak = 0.0
            peak_db = -100.0
            rms_db = -100.0

        is_clipping = bool(peak >= 0.999 or peak_db >= -0.05)

        # 4. Silence Detection wewnątrz mowy
        max_silence_found = self._detect_max_internal_silence(mono_data, sample_rate)
        unnatural_silence = max_silence_found > self.max_internal_silence_sec

        # Status ogólny
        has_warnings = drift_warning or pacing_warning or is_clipping or unnatural_silence
        status = "WARNING" if has_warnings else "PASSED"

        return QualityMetrics(
            audio_duration_sec=round(duration, 3),
            target_window_sec=round(target_window, 3),
            drift_seconds=drift,
            drift_warning=drift_warning,
            word_count=words,
            wpm=wpm,
            pacing_warning=pacing_warning,
            peak_db=peak_db,
            rms_db=rms_db,
            is_clipping=is_clipping,
            max_internal_silence_sec=round(max_silence_found, 2),
            unnatural_silence_detected=unnatural_silence,
            overall_quality_status=status,
        )

    def _detect_max_internal_silence(self, data: np.ndarray, sample_rate: int) -> float:
        """Wykrywa najdłuższą ciągłą przerwę ciszy wewnątrz partii mowy."""
        if len(data) == 0 or sample_rate <= 0:
            return 0.0

        frame_len = int(sample_rate * 0.05)  # 50 ms
        if frame_len == 0:
            return 0.0

        num_frames = len(data) // frame_len
        if num_frames == 0:
            return 0.0

        trimmed = data[: num_frames * frame_len].reshape(num_frames, frame_len)
        frame_max = np.max(np.abs(trimmed), axis=1)

        # Wykrycie pierwszej i ostatniej ramki z głosem
        speech_indices = np.where(frame_max >= self.silence_threshold_amp)[0]
        if len(speech_indices) < 2:
            return 0.0

        start_speech = speech_indices[0]
        end_speech = speech_indices[-1]

        # Analiza przerw wyłącznie między początkiem a końcem mowy
        internal_frames = frame_max[start_speech : end_speech + 1]
        is_silent = internal_frames < self.silence_threshold_amp

        max_silent_frames = 0
        current_silent_frames = 0
        for silent in is_silent:
            if silent:
                current_silent_frames += 1
                if current_silent_frames > max_silent_frames:
                    max_silent_frames = current_silent_frames
            else:
                current_silent_frames = 0

        return float(max_silent_frames * 0.05)


class WorkRunManager:
    """
    Autonomiczny menedżer wersjonowania przebiegów roboczych w work/runs/.
    Zarządza cyklem życia sesji, przechwytywaniem logów i generowaniem run_summary.json.
    """

    def __init__(
        self,
        task_slug: str,
        engine: str = "default",
        base_dir: str | Path | None = None,
        explicit_output_dir: Path | None = None,
    ):
        self.task_slug = re.sub(r"[^\w\-]", "_", (task_slug or "task").strip())
        self.engine = re.sub(r"[^\w\-]", "_", (engine or "default").strip().lower())
        self.start_timestamp = datetime.now()
        self.start_perf = time.perf_counter()

        self.stages_timing: dict[str, float] = {}
        self.stats: dict[str, Any] = {}
        self.quality_analyzer = QualityAnalyzer()

        self._log_file_handle: TextIO | None = None
        self._orig_stdout: TextIO | None = None
        self._orig_stderr: TextIO | None = None
        self._logging_file_handler: logging.Handler | None = None

        if explicit_output_dir is not None:
            self.run_dir = Path(explicit_output_dir).resolve()
            self.base_dir = self.run_dir.parent
            self.is_explicit = True
        else:
            self.base_dir = Path(base_dir).resolve() if base_dir else DEFAULT_RUNS_DIR.resolve()
            timestamp_str = self.start_timestamp.strftime("%Y-%m-%d_%H-%M-%S")
            run_name = f"{timestamp_str}_{self.engine}_{self.task_slug}"
            self.run_dir = self.base_dir / run_name
            self.is_explicit = False

        self._init_workspace()

    def _init_workspace(self) -> None:
        """Tworzy katalog przebiegu, hierarchię podfolderów i aktualizuje symlink work/latest."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        for stage in ALL_STAGE_FOLDERS:
            (self.run_dir / stage).mkdir(parents=True, exist_ok=True)

        self._update_latest_symlink()

    def remove_latest_symlink(self) -> None:
        """Bezpiecznie usuwa symlink latest."""
        latest_link = self.base_dir.parent / "latest"
        if latest_link.is_symlink() or latest_link.exists():
            latest_link.unlink(missing_ok=True)

    def _update_latest_symlink(self) -> None:
        """Atomowo aktualizuje symlink work/latest wskazujący na bieżący run."""
        try:
            # work/latest tworzony jest o jeden poziom wyżej niż katalog runs/
            latest_link = self.base_dir.parent / "latest"
            latest_link.parent.mkdir(parents=True, exist_ok=True)

            # Ścieżka względna dla pełnej przenośności
            rel_target = os.path.relpath(self.run_dir, latest_link.parent)

            temp_link = latest_link.with_name(f".latest_tmp_{os.getpid()}")
            if temp_link.is_symlink() or temp_link.exists():
                temp_link.unlink(missing_ok=True)

            os.symlink(rel_target, temp_link)
            try:
                os.replace(temp_link, latest_link)
            except OSError:
                if latest_link.is_symlink() or latest_link.exists():
                    latest_link.unlink(missing_ok=True)
                os.replace(temp_link, latest_link)
        except Exception as e:
            logger.warning("Nie udało się zaktualizować symlinku latest: %s", e)

    # Właściwości ścieżek
    @property
    def logs_dir(self) -> Path:
        return self.run_dir / "logs"

    @property
    def source_extracted_dir(self) -> Path:
        return self.run_dir / STAGE_SOURCE_EXTRACTED

    @property
    def transcription_dir(self) -> Path:
        return self.run_dir / STAGE_TRANSCRIPTION

    @property
    def llm_adaptation_dir(self) -> Path:
        return self.run_dir / STAGE_LLM_ADAPTATION

    @property
    def tts_segments_dir(self) -> Path:
        return self.run_dir / STAGE_TTS_SEGMENTS

    @property
    def subtitles_dir(self) -> Path:
        return self.run_dir / STAGE_SUBTITLES

    @property
    def output_dir(self) -> Path:
        return self.run_dir / STAGE_OUTPUT

    def get_stage_dir(self, stage_identifier: str) -> Path:
        """Zwraca katalog etapu na podstawie nazwy lub aliasu."""
        s = stage_identifier.lower().strip()
        mapping = {
            "01": self.source_extracted_dir,
            "1": self.source_extracted_dir,
            "source": self.source_extracted_dir,
            "source_extracted": self.source_extracted_dir,
            STAGE_SOURCE_EXTRACTED: self.source_extracted_dir,
            "02": self.transcription_dir,
            "2": self.transcription_dir,
            "transcription": self.transcription_dir,
            STAGE_TRANSCRIPTION: self.transcription_dir,
            "03": self.llm_adaptation_dir,
            "3": self.llm_adaptation_dir,
            "llm": self.llm_adaptation_dir,
            "adaptation": self.llm_adaptation_dir,
            STAGE_LLM_ADAPTATION: self.llm_adaptation_dir,
            "04": self.tts_segments_dir,
            "4": self.tts_segments_dir,
            "tts": self.tts_segments_dir,
            "segments": self.tts_segments_dir,
            STAGE_TTS_SEGMENTS: self.tts_segments_dir,
            "05": self.subtitles_dir,
            "5": self.subtitles_dir,
            "subtitles": self.subtitles_dir,
            "srt": self.subtitles_dir,
            STAGE_SUBTITLES: self.subtitles_dir,
            "06": self.output_dir,
            "6": self.output_dir,
            "output": self.output_dir,
            STAGE_OUTPUT: self.output_dir,
            "logs": self.logs_dir,
        }
        if s in mapping:
            return mapping[s]

        # Domyślny fallback do podkatalogu wewnątrz run_dir
        target = self.run_dir / stage_identifier
        target.mkdir(parents=True, exist_ok=True)
        return target

    def save_artifact(
        self,
        stage_folder: str,
        filename: str,
        data: str | bytes | dict[str, Any] | list[Any] | Path,
    ) -> Path:
        """
        Zapisuje artefakt w wybranym folderze etapowym.
        Obsługuje tekst UTF-8, binaria, obiekty JSON oraz kopiowanie plików z Path.
        """
        target_dir = self.get_stage_dir(stage_folder)
        target_path = target_dir / filename

        if isinstance(data, (dict, list)):
            target_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        elif isinstance(data, str):
            target_path.write_text(data, encoding="utf-8")
        elif isinstance(data, bytes):
            target_path.write_bytes(data)
        elif isinstance(data, Path):
            if data.resolve() != target_path.resolve():
                shutil.copy2(str(data), str(target_path))
        else:
            target_path.write_text(str(data), encoding="utf-8")

        return target_path

    @contextmanager
    def capture_logs(self):
        """
        Context Manager aktywujący Tee Logging:
        Przekierowuje cały strumień stdout/stderr oraz logi systemowe
        jednocześnie na ekran terminala i do logs/execution.log.
        """
        log_file_path = self.logs_dir / "execution.log"
        self._log_file_handle = open(log_file_path, "a", encoding="utf-8")

        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr

        sys.stdout = TeeStream(self._orig_stdout, self._log_file_handle)
        sys.stderr = TeeStream(self._orig_stderr, self._log_file_handle)

        root_logger = logging.getLogger()
        self._logging_file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
        self._logging_file_handler.setFormatter(
            logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
        )
        root_logger.addHandler(self._logging_file_handler)

        try:
            yield
        finally:
            if self._orig_stdout:
                sys.stdout = self._orig_stdout
            if self._orig_stderr:
                sys.stderr = self._orig_stderr

            if self._logging_file_handler:
                root_logger.removeHandler(self._logging_file_handler)
                self._logging_file_handler.close()

            if self._log_file_handle and not self._log_file_handle.closed:
                self._log_file_handle.flush()
                self._log_file_handle.close()

    @contextmanager
    def measure_stage(self, stage_name: str):
        """Mierzy czas wykonania danego etapu i zapisuje wynik w stages_timing."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dt = time.perf_counter() - t0
            self.stages_timing[stage_name] = round(dt, 3)

    def record_stats(self, **kwargs) -> None:
        """Rejestruje statystyki wykonania (np. słowa, okno czasowe)."""
        self.stats.update(kwargs)

    def finish_run(self, quality_analysis: dict[str, Any] | QualityMetrics | None = None) -> Path:
        """
        Zamyka sesję i zapisuje zbiorczy plik run_summary.json.
        """
        total_dur = round(time.perf_counter() - self.start_perf, 3)

        cuda_avail = False
        try:
            import torch

            cuda_avail = bool(torch.cuda.is_available())
        except Exception:
            pass

        meta = {
            "timestamp": self.start_timestamp.isoformat(),
            "duration_total_sec": total_dur,
            "task_slug": self.task_slug,
            "engine": self.engine,
            "cli_arguments": sys.argv,
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "cuda_available": cuda_avail,
        }

        qa_dict = (
            quality_analysis.to_dict()
            if isinstance(quality_analysis, QualityMetrics)
            else (quality_analysis or {})
        )

        summary_payload = {
            "meta": meta,
            "stages_timing": self.stages_timing,
            "stats": self.stats,
            "quality_analysis": qa_dict,
        }

        summary_file = self.run_dir / "run_summary.json"
        summary_file.write_text(
            json.dumps(summary_payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return summary_file
