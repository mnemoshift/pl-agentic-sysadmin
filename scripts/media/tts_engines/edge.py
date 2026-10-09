#!/usr/bin/env python3
"""
Adapter silnika Edge-TTS (Microsoft Neural Cloud Voices).
Służy jako wysoce niezawodny fallback lub szybki podgląd bez obciążania GPU VRAM.
Obsługuje wielojęzyczne głosy angielskie i polskie (np. pl-PL-MarekNeural).
"""

import shutil
import subprocess
import sys
from pathlib import Path
from .base import BaseTTSEngine

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"


class EdgeTTSEngine(BaseTTSEngine):
    def __init__(self, voice: str = "en-US-ChristopherNeural", rate: str = "+2%"):
        self.voice = voice
        self.rate = rate

    @property
    def name(self) -> str:
        return f"Edge-TTS ({self.voice})"

    def is_available(self) -> bool:
        if shutil.which("edge-tts"):
            return True
        if (VENV_PYTHON.parent / "edge-tts").exists():
            return True
        return False

    def synthesize(
        self,
        text: str,
        out_wav: Path,
        ref_audio: Path | None = None,
        ref_transcript: str = "",
        instruction: str = "",
        seed: int = 42,
        voice: str | None = None,
        rate: str | None = None,
        **kwargs,
    ) -> bool:
        active_voice = voice or self.voice
        active_rate = rate or self.rate

        edge_bin = shutil.which("edge-tts")
        if not edge_bin and (VENV_PYTHON.parent / "edge-tts").exists():
            edge_bin = str(VENV_PYTHON.parent / "edge-tts")

        if not edge_bin:
            print("\033[1;31m[ERROR]\033[0m Brak zainstalowanego pakietu edge-tts.", file=sys.stderr)
            return False

        temp_mp3 = out_wav.with_suffix(".mp3")
        cmd = [
            edge_bin,
            "--text", text,
            "--voice", active_voice,
            f"--rate={active_rate}",
            "--write-media", str(temp_mp3),
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                print(f"\033[1;31m[ERROR]\033[0m Błąd generowania mowy przez Edge-TTS: {res.stderr.strip()}", file=sys.stderr)
                return False

            # Konwersja do WAV 24kHz / mono
            out_wav.parent.mkdir(parents=True, exist_ok=True)
            conv_cmd = [
                "ffmpeg", "-y",
                "-i", str(temp_mp3),
                "-ac", "1",
                "-ar", "24000",
                str(out_wav),
            ]
            conv_res = subprocess.run(conv_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if temp_mp3.exists():
                temp_mp3.unlink()

            if conv_res.returncode != 0:
                print(f"\033[1;31m[ERROR]\033[0m Błąd konwersji FFmpeg dla Edge-TTS: {conv_res.stderr.strip()}", file=sys.stderr)
                return False
            return True

        except Exception as e:
            print(f"\033[1;31m[ERROR]\033[0m Wyjątek podczas syntezy Edge-TTS: {e}", file=sys.stderr)
            if temp_mp3.exists():
                temp_mp3.unlink()
            return False
