#!/usr/bin/env python3
"""
Adapter silnika Chatterbox-Turbo (ResembleAI/Chatterbox-Turbo).
Licencja MIT (w pełni komercyjna pod monetyzację).
Działa w odizolowanym środowisku Pythona (.venv-chatterbox) w celu ochrony przed konfliktami wersji transformers.
"""

import subprocess
import sys
from pathlib import Path

from .base import BaseTTSEngine

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class ChatterboxEngine(BaseTTSEngine):
    def __init__(self):
        self.in_process = False
        self._model = None
        self.python_bin = self._resolve_python()

        # Opcjonalna próba inicjalizacji in-process, jeśli transformers>=5 jest w bieżącym venv
        try:
            import torch
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = ChatterboxTurboTTS.from_pretrained(device=device)
            self.in_process = True
        except Exception:
            self.in_process = False

    @property
    def name(self) -> str:
        return "Chatterbox-Turbo (MIT)"

    def _resolve_python(self) -> Path:
        candidates = [
            REPO_ROOT / ".venv-chatterbox" / "bin" / "python",
            Path.home() / "workspaces" / "pl-agentic-sysadmin-work" / ".venv" / "bin" / "python",
            Path(sys.executable),
        ]
        for cand in candidates:
            if cand.exists():
                return cand
        return Path(sys.executable)

    def is_available(self) -> bool:
        if self.in_process:
            return True
        if not self.python_bin or not self.python_bin.exists():
            return False
        # Sprawdzenie dostępności modułu w dedykowanym interpreterze
        cmd = [str(self.python_bin), "-c", "import chatterbox; import setuptools"]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0

    def synthesize(
        self,
        text: str,
        out_wav: Path,
        ref_audio: Path | None = None,
        ref_transcript: str = "",
        instruction: str = "",
        seed: int = 42,
        **kwargs,
    ) -> bool:
        if not ref_audio or not ref_audio.exists():
            print("\033[1;31m[ERROR]\033[0m Chatterbox wymaga podania próbki referencyjnej (--ref-audio).", file=sys.stderr)
            return False

        try:
            out_wav.parent.mkdir(parents=True, exist_ok=True)
            if self.in_process and self._model:
                import torchaudio as ta
                wav = self._model.generate(text, audio_prompt_path=str(ref_audio.resolve()))
                ta.save(str(out_wav), wav, self._model.sr)
                return True
            else:
                code = (
                    "import torchaudio as ta\n"
                    "from chatterbox.tts_turbo import ChatterboxTurboTTS\n"
                    "model = ChatterboxTurboTTS.from_pretrained(device='cuda')\n"
                    f"wav = model.generate({repr(text)}, audio_prompt_path={repr(str(ref_audio.resolve()))})\n"
                    f"ta.save({repr(str(out_wav))}, wav, model.sr)\n"
                )
                res = subprocess.run(
                    [str(self.python_bin), "-c", code],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if res.returncode != 0:
                    print(f"\033[1;31m[ERROR]\033[0m Błąd Chatterbox subprocess: {res.stderr.strip()}", file=sys.stderr)
                    return False
                return True
        except Exception as e:
            print(f"\033[1;31m[ERROR]\033[0m Błąd syntezy przez Chatterbox: {e}", file=sys.stderr)
            return False
