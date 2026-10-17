#!/usr/bin/env -S uv run python
"""
Workstation Hub: Moduł i skrypt CLI do transferu barwy głosu (Tone Color Conversion).
Wykorzystuje OpenVoice V2 Tone Color Converter (licencja MIT) do przeniesienia
barwy głosu z próbki referencyjnej na dowolne wygenerowane audio mowy (np. z Qwen3-TTS),
przy 100% zachowaniu intonacji, emocji, przerw i pacingu (Acting Direction).
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Wyłączamy cuDNN ze względu na znany konflikt wersji runtime w PyTorch 2.14
os.environ["TORCH_CUDNN_V8_API_DISABLED"] = "1"
import torch  # noqa: E402

torch.backends.cudnn.enabled = False

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("convert_voice_timbre")

CLR_RESET = "\033[0m"
CLR_BOLD = "\033[1m"
CLR_CYAN = "\033[1;36m"
CLR_GREEN = "\033[1;32m"
CLR_YELLOW = "\033[1;33m"
CLR_RED = "\033[1;31m"
CLR_DIM = "\033[2m"


class ToneColorConverterEngine:
    """Klasa opakowująca silnik OpenVoice V2 Tone Color Converter."""

    def __init__(
        self,
        model_dir: Path | None = None,
        device: str = "cuda:0" if torch.cuda.is_available() else "cpu",
    ) -> None:
        self.device = device
        self.model_dir = model_dir or (REPO_ROOT / "models" / "OpenVoiceV2" / "converter")
        self.config_path = self.model_dir / "config.json"
        self.checkpoint_path = self.model_dir / "checkpoint.pth"

        self._converter = None
        self._cached_target_se: dict[str, torch.Tensor] = {}

    def _ensure_model(self) -> None:
        if self._converter is not None:
            return

        if not self.config_path.exists() or not self.checkpoint_path.exists():
            raise FileNotFoundError(
                f"Brak wag OpenVoice V2 w {self.model_dir}. "
                f"Uruchom pobieranie wag do katalogu models/OpenVoiceV2/converter."
            )

        logger.info("Inicjalizacja OpenVoice V2 Tone Color Converter na urządzeniu %s...", self.device)
        from openvoice.api import ToneColorConverter

        self._converter = ToneColorConverter(str(self.config_path), device=self.device)
        # Wyłączamy cyfrowy znak wodny, aby nie wprowadzać artefaktów do audio studyjnego
        self._converter.watermark_model = None
        self._converter.load_ckpt(str(self.checkpoint_path))
        logger.info("Pomyślnie załadowano wagi OpenVoice V2 checkpoint.pth.")

    def extract_speaker_embedding(self, wav_paths: list[Path] | Path) -> torch.Tensor:
        """Ekstrahuje wektor cech mówcy (Speaker Embedding) z plików WAV."""
        self._ensure_model()
        if isinstance(wav_paths, (str, Path)):
            wav_paths = [Path(wav_paths)]

        valid_paths = [str(p) for p in wav_paths if p.exists() and p.stat().st_size > 1000]
        if not valid_paths:
            raise FileNotFoundError(f"Nie znaleziono poprawnych plików audio w: {wav_paths}")

        cache_key = ":".join(sorted(valid_paths))
        if cache_key in self._cached_target_se:
            return self._cached_target_se[cache_key]

        se = self._converter.extract_se(valid_paths)
        self._cached_target_se[cache_key] = se
        return se

    def convert_timbre(
        self,
        source_audio: Path,
        target_ref_audio: Path | list[Path],
        output_audio: Path,
        tau: float = 0.3,
    ) -> Path:
        """
        Przekształca barwę głosu z pliku source_audio na barwę docelową target_ref_audio.

        Args:
            source_audio: Ścieżka do pliku audio źródłowego (np. z syntezy Qwen-TTS).
            target_ref_audio: Próbka głosu docelowego (np. Twój ref_voice_sample_en.wav).
            output_audio: Ścieżka do zapisu wynikowego pliku WAV.
            tau: Współczynnik siły transferu barwy (0.1 - 0.6, domyślnie 0.3).
        """
        self._ensure_model()

        if not source_audio.exists():
            raise FileNotFoundError(f"Plik źródłowy nie istnieje: {source_audio}")

        # 1. Ekstrakcja embeddingu ze źródła
        src_se = self._converter.extract_se(str(source_audio))

        # 2. Ekstrakcja embeddingu z docelowego głosu
        tgt_se = self.extract_speaker_embedding(target_ref_audio)

        # 3. Konwersja barwy
        output_audio.parent.mkdir(parents=True, exist_ok=True)
        self._converter.convert(
            audio_src_path=str(source_audio),
            src_se=src_se,
            tgt_se=tgt_se,
            output_path=str(output_audio),
            tau=tau,
        )
        return output_audio


def play_audio(wav_path: Path) -> None:
    player = shutil.which("mpv") or shutil.which("ffplay") or shutil.which("aplay")
    if not player:
        print(f"{CLR_YELLOW}[WARN] Brak mpv/ffplay do odsłuchu.{CLR_RESET}")
        return

    cmd = [player, str(wav_path)]
    if "ffplay" in player:
        cmd = [player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(wav_path)]
    elif "mpv" in player:
        cmd = [player, "--no-video", "--really-quiet", str(wav_path)]

    try:
        subprocess.run(cmd, check=False)
    except Exception as e:
        logger.warning("Nie udało się odtworzyć audio: %s", e)


def find_default_reference_audio() -> Path | None:
    candidates = [
        REPO_ROOT / "work" / "voice_sample" / "ref_voice_sample_en.wav",
        REPO_ROOT / "work" / "voice_sample" / "ref_voice_sample.wav",
        REPO_ROOT / "voice" / "sample_reference.wav",
    ]
    for c in candidates:
        if c.exists() and c.stat().st_size > 1000:
            return c
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Transfer barwy głosu za pomocą OpenVoice V2 (MIT) przy 100% zachowaniu acting direction",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-s", "--source",
        type=Path,
        required=True,
        help="Ścieżka do pliku audio z kwestią źródłową (np. wygenerowaną przez Qwen-TTS)",
    )
    parser.add_argument(
        "-r", "--ref",
        type=Path,
        default=None,
        help="Ścieżka do próbki referencyjnej głosu docelowego (domyślnie szuka w work/voice_sample/)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Ścieżka do wygenerowanego pliku WAV (domyślnie dodaje sufiks _timbre.wav)",
    )
    parser.add_argument(
        "-t", "--tau",
        type=float,
        default=0.3,
        help="Współczynnik transferu barwy (rekomendowany zakres: 0.15 - 0.40)",
    )
    parser.add_argument(
        "--play",
        action="store_true",
        help="Automatycznie odtwórz plik audio po zakończeniu konwersji",
    )

    args = parser.parse_args()

    ref_audio = args.ref or find_default_reference_audio()
    if not ref_audio or not ref_audio.exists():
        print(f"{CLR_RED}[BŁĄD] Nie znaleziono próbki referencyjnej głosu docelowego.{CLR_RESET}")
        print("Wskaż plik za pomocą parametru -r / --ref lub umieść plik w work/voice_sample/ref_voice_sample_en.wav.")
        return 1

    source_audio = args.source
    if not source_audio.exists():
        print(f"{CLR_RED}[BŁĄD] Plik źródłowy nie istnieje: {source_audio}{CLR_RESET}")
        return 1

    output_audio = args.output
    if not output_audio:
        output_audio = source_audio.parent / f"{source_audio.stem}_timbre{source_audio.suffix}"

    print(f"\n{CLR_CYAN}{CLR_BOLD}═══════════════════════════════════════════════════════════════════════════{CLR_RESET}")
    print(f"{CLR_CYAN}{CLR_BOLD}         MNEMOSHIFT // VOICE TIMBRE CONVERTER (OPENVOICE V2 MIT)          {CLR_RESET}")
    print(f"{CLR_CYAN}{CLR_BOLD}═══════════════════════════════════════════════════════════════════════════{CLR_RESET}")
    print(f"{CLR_BOLD}Plik źródłowy (Audio + Acting):{CLR_RESET} {source_audio}")
    print(f"{CLR_BOLD}Próbka docelowa (Twój głos):{CLR_RESET}   {ref_audio}")
    print(f"{CLR_BOLD}Współczynnik tau (Siła barwy):{CLR_RESET} {args.tau}")
    print(f"{CLR_BOLD}Plik wynikowy:{CLR_RESET}                 {output_audio}")
    print(f"{CLR_CYAN}───────────────────────────────────────────────────────────────────────────{CLR_RESET}\n")

    t0 = time.time()
    engine = ToneColorConverterEngine()
    engine.convert_timbre(
        source_audio=source_audio,
        target_ref_audio=ref_audio,
        output_audio=output_audio,
        tau=args.tau,
    )
    dur = time.time() - t0

    print(f"{CLR_GREEN}{CLR_BOLD}✓ Pomyślnie przetransferowano barwę głosu w {dur:.2f}s!{CLR_RESET}")
    print(f"Zapisano plik: {CLR_BOLD}{output_audio}{CLR_RESET}")

    if args.play:
        print(f"\n▶ Odtwarzanie pliku wynikowego: {output_audio.name}...")
        play_audio(output_audio)

    return 0


if __name__ == "__main__":
    sys.exit(main())
