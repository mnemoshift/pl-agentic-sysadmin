#!/usr/bin/env python3
"""
Adapter silnika KokoClone (Kokoro-ONNX + Kanade Voice Conversion).
Licencje: Kokoro-ONNX (Apache 2.0) + Kanade (MIT) — w pełni komercyjne.
Generuje krystalicznie czystą mowę z Kokoro i przenosi barwę głosu referencyjnego za pomocą Kanade.
"""

import sys
import tempfile
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

        clean_lang = (
            lang.split(".")[0].replace("-", "_").split("_")[0].lower().strip()
            if lang
            else "en"
        )

        if clean_lang.startswith("pl"):
            # Kokoro nie wspiera natywnego G2P dla języka polskiego.
            # Wykorzystujemy architekturę dwuetapową: synteza Edge-TTS (Marek) + transfer barwy Kanade.
            from .edge import EdgeTTSEngine

            edge_voice = kwargs.get("voice") or "pl-PL-MarekNeural"
            edge = EdgeTTSEngine(voice=edge_voice)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                temp_base = Path(tf.name)
            try:
                ok = edge.synthesize(text=text, out_wav=temp_base, voice=edge_voice)
                if not ok:
                    return False
                return self.convert_audio(source_audio=temp_base, ref_audio=ref_audio, output_wav=out_wav)
            finally:
                temp_base.unlink(missing_ok=True)

        try:
            self._ensure_cloner()
            out_wav.parent.mkdir(parents=True, exist_ok=True)
            self._cloner.generate(
                text=text,
                lang=clean_lang,
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
