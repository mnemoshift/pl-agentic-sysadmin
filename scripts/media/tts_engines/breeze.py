#!/usr/bin/env python3
"""
Adapter silnika Breeze-TTS-2 (MediaTek Breeze-TTS-2).
Wykorzystuje in-process FastBreezeStreamingRuntime w pamięci GPU VRAM.
Uwaga: licencja Breeze może nakładać ograniczenia na użycie komercyjne.
"""

import sys
from pathlib import Path

from .base import BaseTTSEngine

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BREEZE_TOOL_DIR = REPO_ROOT / "tools" / "breeze_tts"


def find_breeze_model_dir() -> Path | None:
    candidates = [
        REPO_ROOT / "models" / "Breeze-TTS-2",
        Path.home() / "workspaces" / "mnemoshift" / "pl-agentic-sysadmin" / "models" / "Breeze-TTS-2",
        Path.home() / "workspaces" / "pl-agentic-sysadmin-work" / "models" / "Breeze-TTS-2",
    ]
    for c in candidates:
        if c.exists() and (c / "config.json").exists():
            return c
    return None


class BreezeTTSEngine(BaseTTSEngine):
    def __init__(self, model_dir: Path | None = None):
        self.model_dir = model_dir or find_breeze_model_dir()
        self._runtime = None
        self._tokenizer = None
        self._audio_tokenizer = None
        self._model = None

    @property
    def name(self) -> str:
        return "Breeze-TTS-2 (MediaTek Zero-Shot)"

    def is_available(self) -> bool:
        if not BREEZE_TOOL_DIR.exists() or not self.model_dir:
            return False
        try:
            if str(BREEZE_TOOL_DIR) not in sys.path:
                sys.path.insert(0, str(BREEZE_TOOL_DIR))
            from breeze_infer.runtime import load_runtime  # noqa: F401
            return True
        except Exception:
            return False

    def _ensure_runtime(self):
        if self._runtime is not None:
            return
        if not self.model_dir:
            raise FileNotFoundError("Nie znaleziono katalogu wag Breeze-TTS-2.")

        if str(BREEZE_TOOL_DIR) not in sys.path:
            sys.path.insert(0, str(BREEZE_TOOL_DIR))

        from breeze_infer.runtime import load_runtime, resolve_device, update_generation_config_for_breeze
        from models.fast_streaming import FastBreezeStreamingRuntime, FastStreamingConfig

        device = resolve_device()
        print(f"\033[1;34m[INFO]\033[0m Ładowanie wag Breeze-TTS-2 do {device} (jednorazowa alokacja VRAM)...")
        self._tokenizer, self._model, self._audio_tokenizer = load_runtime(
            self.model_dir,
            device=device,
            attn_implementation="eager",
        )
        update_generation_config_for_breeze(self._model)
        config = FastStreamingConfig(
            max_new_tokens=850,
            max_seq_len=2048,
            repetition_penalty=1.1,
        )
        self._runtime = FastBreezeStreamingRuntime(
            self._model, self._audio_tokenizer, config, tokenizer=self._tokenizer
        )
        print("\033[1;32m[OK]\033[0m Zainicjalizowano model Breeze-TTS-2 w pamięci GPU.")

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
            print("\033[1;31m[ERROR]\033[0m Breeze-TTS-2 wymaga podania próbki referencyjnej (--ref-audio).", file=sys.stderr)
            return False

        try:
            import soundfile as sf
            from breeze_infer.runtime import set_all_seeds
            from breeze_infer.templates import get_template, prepare_inputs, select_template_name

            self._ensure_runtime()
            set_all_seeds(seed)
            request = {
                "id": "single-request",
                "text": text,
                "speaker": "S0",
                "ref_audio_path": str(ref_audio.resolve()),
                "ref_text": ref_transcript.strip(),
            }
            if instruction:
                request["instruction"] = instruction.strip()
            template_name = select_template_name(request)
            inputs = prepare_inputs(
                self._tokenizer,
                self._audio_tokenizer,
                self._model,
                [request],
                get_template(template_name),
                guidance_scale=1.0,
                guidance_scale_ref=None,
                guidance_scale_ins=None,
            )

            out_wav.parent.mkdir(parents=True, exist_ok=True)
            with sf.SoundFile(
                str(out_wav),
                mode="w",
                samplerate=self._runtime.sample_rate,
                channels=1,
                subtype="PCM_16",
            ) as output_file:
                for chunk in self._runtime.iter_audio_chunks(
                    inputs, request_id="single-request", seed=seed
                ):
                    output_file.write(chunk.audio)
            return True
        except Exception as e:
            print(f"\033[1;31m[ERROR]\033[0m Błąd syntezy segmentu przez Breeze-TTS-2: {e}", file=sys.stderr)
            return False
