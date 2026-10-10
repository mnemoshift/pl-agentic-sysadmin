#!/usr/bin/env python3
"""
Adapter silnika KokoClone (Kokoro-ONNX + Kanade Voice Conversion).
Licencje: Kokoro-ONNX (Apache 2.0) + Kanade (MIT) — w pełni komercyjne.
Generuje krystalicznie czystą mowę z Kokoro i przenosi barwę głosu referencyjnego za pomocą Kanade.
"""

import sys
from pathlib import Path

from .base import BaseTTSEngine

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
KOKOCLONE_DIR = REPO_ROOT / "tools" / "kokoclone"


class KokoCloneEngine(BaseTTSEngine):
    def __init__(self):
        self._cloner = None

    @property
    def name(self) -> str:
        return "KokoClone (Kokoro-ONNX + Kanade, Apache 2.0 / MIT)"

    def is_available(self) -> bool:
        if not KOKOCLONE_DIR.exists():
            return False
        try:
            if str(KOKOCLONE_DIR) not in sys.path:
                sys.path.insert(0, str(KOKOCLONE_DIR))
            import core.cloner  # noqa: F401
            return True
        except Exception:
            return False

    def _ensure_cloner(self):
        if self._cloner is not None:
            return
        if str(KOKOCLONE_DIR) not in sys.path:
            sys.path.insert(0, str(KOKOCLONE_DIR))
        from core.cloner import KokoClone
        print("\033[1;34m[INFO]\033[0m Ładowanie silnika KokoClone (Kokoro-ONNX + Kanade Zero-Shot)...")
        self._cloner = KokoClone()
        print("\033[1;32m[OK]\033[0m Zainicjalizowano silnik KokoClone.")

    def synthesize(
        self,
        text: str,
        out_wav: Path,
        ref_audio: Path | None = None,
        ref_transcript: str = "",
        instruction: str = "",
        seed: int = 42,
        lang: str = "en",
        **kwargs,
    ) -> bool:
        if not ref_audio or not ref_audio.exists():
            print("\033[1;31m[ERROR]\033[0m KokoClone wymaga podania próbki referencyjnej (--ref-audio).", file=sys.stderr)
            return False

        try:
            self._ensure_cloner()
            out_wav.parent.mkdir(parents=True, exist_ok=True)
            self._cloner.generate(
                text=text,
                lang=lang,
                reference_audio=str(ref_audio.resolve()),
                output_path=str(out_wav),
            )
            return True
        except Exception as e:
            print(f"\033[1;31m[ERROR]\033[0m Błąd syntezy przez KokoClone: {e}", file=sys.stderr)
            return False

    def convert_audio(self, source_audio: Path, ref_audio: Path, output_wav: Path) -> bool:
        """Przenosi barwę mówcy referencyjnego na istniejący plik audio (np. w języku polskim)."""
        try:
            self._ensure_cloner()
            output_wav.parent.mkdir(parents=True, exist_ok=True)
            self._cloner.convert(
                source_audio=str(source_audio.resolve()),
                reference_audio=str(ref_audio.resolve()),
                output_path=str(output_wav),
            )
            return True
        except Exception as e:
            print(f"\033[1;31m[ERROR]\033[0m Błąd konwersji głosu przez Kanade: {e}", file=sys.stderr)
            return False
