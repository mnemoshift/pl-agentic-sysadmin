#!/usr/bin/env python3
"""
Adapter silnika Qwen3-TTS (Qwen/Qwen3-TTS-12Hz-0.6B-Base).
Licencja Apache 2.0 (w pełni komercyjna pod monetyzację).
Wykorzystuje in-context voice cloning w pamięci GPU VRAM.
"""

import sys
from pathlib import Path

from .base import BaseTTSEngine


class QwenTTSEngine(BaseTTSEngine):
    def __init__(self, model_id: str = "Qwen/Qwen3-TTS-12Hz-0.6B-Base", **kwargs):
        self.model_id = model_id
        self._model = None
        self.cached_prompt = None
        self.cached_ref_audio = None

    @property
    def name(self) -> str:
        return f"Qwen3-TTS ({self.model_id.split('/')[-1]}, Apache 2.0)"

    def is_available(self) -> bool:
        try:
            import qwen_tts  # noqa: F401
            return True
        except Exception:
            return False

    def _ensure_model(self):
        if self._model is not None:
            return
        import torch
        from qwen_tts import Qwen3TTSModel

        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        print(f"\033[1;34m[INFO]\033[0m Ładowanie wag Qwen3-TTS ({self.model_id}) do {device}...")
        self._model = Qwen3TTSModel.from_pretrained(self.model_id, device_map=device, dtype=dtype)
        print("\033[1;32m[OK]\033[0m Zainicjalizowano model Qwen3-TTS w pamięci GPU.")

    def get_prompt(self, ref_audio: Path, ref_text: str):
        ref_path_str = str(ref_audio.resolve())
        if self.cached_prompt is None or self.cached_ref_audio != ref_path_str:
            self._ensure_model()
            if not ref_text.strip():
                txt_file = ref_audio.with_suffix(".txt")
                if txt_file.exists():
                    ref_text = txt_file.read_text(encoding="utf-8").strip()

            use_xvector = not bool(ref_text.strip())
            self.cached_prompt = self._model.create_voice_clone_prompt(
                ref_audio=ref_path_str,
                ref_text=ref_text.strip() if not use_xvector else None,
                x_vector_only_mode=use_xvector,
            )
            self.cached_ref_audio = ref_path_str
        return self.cached_prompt

    def synthesize(
        self,
        text: str,
        out_wav: Path,
        ref_audio: Path | None = None,
        ref_transcript: str = "",
        instruction: str = "",
        seed: int = 42,
        language: str = "English",
        **kwargs,
    ) -> bool:
        if not ref_audio or not ref_audio.exists():
            print("\033[1;31m[ERROR]\033[0m Qwen3-TTS wymaga podania próbki referencyjnej (--ref-audio).", file=sys.stderr)
            return False

        try:
            import logging

            import soundfile as sf
            from text_director import clean_voiceover_text, strip_voice_tags

            # Upewniamy się, że do generacji mowy trafia w 100% czysty tekst bez jakichkolwiek znaczników
            safe_text = strip_voice_tags(clean_voiceover_text(text))
            self._ensure_model()
            prompt = self.get_prompt(ref_audio, ref_transcript)

            acting_instruction = instruction.strip() if instruction else "Speak naturally in a clear, engaging tone."
            gen_kwargs = dict(kwargs)
            try:
                ins_text = self._model._build_instruct_text(acting_instruction)
                gen_kwargs["instruct_ids"] = self._model._tokenize_texts([ins_text])
            except Exception as e:
                logging.getLogger(__name__).warning("Nie udało się stokenizować instruct_ids dla Qwen3-TTS: %s", e)

            wavs, sr = self._model.generate_voice_clone(
                text=safe_text,
                language=language,
                voice_clone_prompt=prompt,
                **gen_kwargs,
            )
            out_wav.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(out_wav), wavs[0], sr)
            return True
        except Exception as e:
            print(f"\033[1;31m[ERROR]\033[0m Błąd syntezy przez Qwen3-TTS: {e}", file=sys.stderr)
            return False

