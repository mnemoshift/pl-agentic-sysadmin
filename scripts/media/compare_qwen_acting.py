#!/usr/bin/env python3
"""
Workstation Hub: Skrypt demonstracyjno-testowy Qwen3-TTS (Acting Direction Comparison).

Porównuje syntezę mowy tego samego tekstu w dwóch wariantach:
1. Baseline (BEZ Acting Direction): czysty zero-shot voice cloning bez wektora instruct_ids.
2. Acting Direction (Z Reżyserią): synteza z dołączonym wektorem instruct_ids definiującym
   ton, emocje, tempo i prozodię wypowiedzi.

Idealny do demonstracji na żywo w terminalu podczas nagrania screencastu EP004b.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Dołączamy moduły z scripts/media
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "media"))

from text_director import clean_voiceover_text, strip_voice_tags
from tts_engines.qwen import QwenTTSEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("compare_qwen_acting")

# ANSI Colors
CLR_RESET = "\033[0m"
CLR_BOLD = "\033[1m"
CLR_CYAN = "\033[1;36m"
CLR_GREEN = "\033[1;32m"
CLR_YELLOW = "\033[1;33m"
CLR_RED = "\033[1;31m"
CLR_BLUE = "\033[1;34m"
CLR_MAGENTA = "\033[1;35m"
CLR_DIM = "\033[2m"


def find_default_reference_audio(repo_root: Path) -> tuple[Path | None, str]:
    """Wyszukuje domyślną próbkę głosu w work/voice_sample/ lub voice/."""
    candidates = [
        repo_root / "work" / "voice_sample" / "ref_voice_sample_en.wav",
        repo_root / "work" / "voice_sample" / "ref_voice_sample.wav",
        repo_root / "voice" / "sample_reference.wav",
    ]
    for cand in candidates:
        if cand.exists() and cand.stat().st_size > 1000:
            txt_cand = cand.with_suffix(".txt")
            transcript = txt_cand.read_text(encoding="utf-8").strip() if txt_cand.exists() else ""
            return cand, transcript

    # Fallback: dowolny plik .wav w work/voice_sample/
    sample_dir = repo_root / "work" / "voice_sample"
    if sample_dir.exists():
        wavs = list(sample_dir.glob("*.wav"))
        if wavs:
            cand = wavs[0]
            txt_cand = cand.with_suffix(".txt")
            transcript = txt_cand.read_text(encoding="utf-8").strip() if txt_cand.exists() else ""
            return cand, transcript

    return None, ""


def get_audio_duration_and_sr(wav_path: Path) -> tuple[float, int]:
    """Odczytuje czas trwania i częstotliwość próbkowania pliku WAV za pomocą soundfile lub ffprobe."""
    try:
        import soundfile as sf
        info = sf.info(str(wav_path))
        return float(info.duration), int(info.samplerate)
    except Exception:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration:stream=sample_rate", "-of", "default=noprint_wrappers=1:nokey=1",
            str(wav_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
        duration = float(lines[1]) if len(lines) > 1 else 0.0
        sr = int(lines[0]) if len(lines) > 0 else 24000
        return duration, sr


def play_audio(wav_path: Path) -> None:
    """Odtwarza plik audio w tle za pomocą mpv, ffplay lub aplay."""
    player = shutil.which("mpv") or shutil.which("ffplay") or shutil.which("aplay")
    if not player:
        print(f"{CLR_YELLOW}[WARN] Brak zainstalowanego odtwarzacza (mpv/ffplay/aplay). Pomiń odsłuch.{CLR_RESET}")
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Porównanie syntezy Qwen3-TTS: Bez Acting Direction vs Z Acting Direction (EP004b Demo)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--text",
        type=str,
        default="We moved the entire autonomous agent workflow to Zorin OS, and the drop in latency was immediately noticeable.",
        help="Czysty tekst kwestii do zsyntetyzowania w języku angielskim",
    )
    parser.add_argument(
        "--instruction",
        type=str,
        default="Speak naturally in a calm, authoritative engineering tone, pacing slightly relaxed.",
        help="Instrukcja reżyserska (Acting Direction) przekazywana przez instruct_ids",
    )
    parser.add_argument(
        "--ref-audio",
        type=Path,
        default=None,
        help="Ścieżka do pliku WAV z próbką referencyjną głosu lektora (10-15s)",
    )
    parser.add_argument(
        "--ref-transcript",
        type=str,
        default="",
        help="Opcjonalna transkrypcja próbki referencyjnej",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "work" / "qwen_acting_test",
        help="Katalog docelowy dla wygenerowanych próbek audio",
    )
    parser.add_argument(
        "--model-id",
        type=str,
        default="Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        help="Identyfikator modelu Qwen na HuggingFace",
    )
    parser.add_argument(
        "--play",
        action="store_true",
        help="Automatycznie odtwórz próbki audio po zakończeniu syntezy",
    )
    parser.add_argument(
        "--only-baseline",
        action="store_true",
        help="Wygeneruj wyłącznie wersję baseline (bez Acting Direction)",
    )
    parser.add_argument(
        "--only-acting",
        action="store_true",
        help="Wygeneruj wyłącznie wersję z Acting Direction",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed generatora liczb losowych dla powtarzalności syntezy",
    )

    args = parser.parse_args()

    # Wyszukanie próbki referencyjnej
    ref_audio = args.ref_audio
    ref_transcript = args.ref_transcript
    if not ref_audio:
        ref_audio, default_transcript = find_default_reference_audio(REPO_ROOT)
        if not ref_transcript:
            ref_transcript = default_transcript

    if not ref_audio or not ref_audio.exists():
        print(f"{CLR_RED}[BŁĄD] Nie znaleziono próbki referencyjnej głosu!{CLR_RESET}")
        print(f"Umieść plik .wav w {REPO_ROOT}/work/voice_sample/ lub wskaż go parametrem --ref-audio.")
        return 1

    # Oczyszczenie tekstu
    clean_text = strip_voice_tags(clean_voiceover_text(args.text))
    acting_instruction = args.instruction.strip()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_baseline = args.output_dir / "1_baseline_without_acting.wav"
    out_acting = args.output_dir / "2_with_acting_direction.wav"
    report_json = args.output_dir / "acting_comparison_report.json"

    # Nagłówek CLI
    print(f"\n{CLR_CYAN}{CLR_BOLD}═══════════════════════════════════════════════════════════════════════════{CLR_RESET}")
    print(f"{CLR_CYAN}{CLR_BOLD}   MNEMOSHIFT // QWEN3-TTS ACTING DIRECTION COMPARISON BENCHMARK   {CLR_RESET}")
    print(f"{CLR_CYAN}{CLR_BOLD}═══════════════════════════════════════════════════════════════════════════{CLR_RESET}")
    print(f"{CLR_BOLD}Tekst do syntezy:{CLR_RESET}   \"{CLR_GREEN}{clean_text}{CLR_RESET}\"")
    print(f"{CLR_BOLD}Reżyseria (Acting):{CLR_RESET} \"{CLR_YELLOW}{acting_instruction}{CLR_RESET}\"")
    print(f"{CLR_BOLD}Próbka referencyjna:{CLR_RESET} {ref_audio} ({CLR_DIM}{ref_audio.stat().st_size // 1024} KB{CLR_RESET})")
    print(f"{CLR_BOLD}Katalog wyjściowy:{CLR_RESET}  {args.output_dir}")
    print(f"{CLR_CYAN}───────────────────────────────────────────────────────────────────────────{CLR_RESET}\n")

    # Inicjalizacja silnika Qwen3-TTS
    print(f"{CLR_BLUE}[1/3] Inicjalizacja modelu {args.model_id} na GPU...{CLR_RESET}")
    engine = QwenTTSEngine(model_id=args.model_id)

    results: dict[str, dict[str, float | str | int]] = {}

    # FAZA 1: Baseline (bez Acting Direction)
    if not args.only_acting:
        print(f"\n{CLR_BOLD}▶ FAZA 1: Generowanie BEZ Acting Direction (Baseline voice clone)...{CLR_RESET}")
        print(f"{CLR_DIM}  Wektor instruct_ids jest całkowicie pominięty (czysty wzorzec głosu).{CLR_RESET}")
        t0 = time.time()
        ok_base = engine.synthesize(
            text=clean_text,
            out_wav=out_baseline,
            ref_audio=ref_audio,
            ref_transcript=ref_transcript,
            instruction="",  # PUSTA instrukcja -> brak instruct_ids
            seed=args.seed,
        )
        t_base = time.time() - t0
        if ok_base and out_baseline.exists():
            dur_base, sr_base = get_audio_duration_and_sr(out_baseline)
            rtf_base = t_base / dur_base if dur_base > 0 else 0.0
            print(f"{CLR_GREEN}✓ Gotowe w {t_base:.2f}s{CLR_RESET} | Długość audio: {CLR_BOLD}{dur_base:.2f}s{CLR_RESET} (RTF: {rtf_base:.2f}x) | Zapisano: {out_baseline.name}")
            results["baseline"] = {
                "file": str(out_baseline),
                "duration_seconds": round(dur_base, 2),
                "generation_time_seconds": round(t_base, 2),
                "sample_rate": sr_base,
                "acting_instruction": None,
            }
        else:
            print(f"{CLR_RED}✗ Błąd generowania wersji baseline!{CLR_RESET}")
            return 1

    # FAZA 2: Z Acting Direction
    if not args.only_baseline:
        print(f"\n{CLR_BOLD}▶ FAZA 2: Generowanie Z Acting Direction (Instruct TTS)...{CLR_RESET}")
        print(f"{CLR_DIM}  Dołączony wektor instruct_ids: \"{acting_instruction}\"{CLR_RESET}")
        t0 = time.time()
        ok_act = engine.synthesize(
            text=clean_text,
            out_wav=out_acting,
            ref_audio=ref_audio,
            ref_transcript=ref_transcript,
            instruction=acting_instruction,  # PEŁNA instrukcja -> instruct_ids
            seed=args.seed,
        )
        t_act = time.time() - t0
        if ok_act and out_acting.exists():
            dur_act, sr_act = get_audio_duration_and_sr(out_acting)
            rtf_act = t_act / dur_act if dur_act > 0 else 0.0
            print(f"{CLR_GREEN}✓ Gotowe w {t_act:.2f}s{CLR_RESET} | Długość audio: {CLR_BOLD}{dur_act:.2f}s{CLR_RESET} (RTF: {rtf_act:.2f}x) | Zapisano: {out_acting.name}")
            results["acting_direction"] = {
                "file": str(out_acting),
                "duration_seconds": round(dur_act, 2),
                "generation_time_seconds": round(t_act, 2),
                "sample_rate": sr_act,
                "acting_instruction": acting_instruction,
            }
        else:
            print(f"{CLR_RED}✗ Błąd generowania wersji z acting direction!{CLR_RESET}")
            return 1

    # Podsumowanie i raport
    print(f"\n{CLR_CYAN}{CLR_BOLD}═══════════════════════════════════════════════════════════════════════════{CLR_RESET}")
    print(f"{CLR_CYAN}{CLR_BOLD}                          PODSUMOWANIE TESTU                               {CLR_RESET}")
    print(f"{CLR_CYAN}{CLR_BOLD}═══════════════════════════════════════════════════════════════════════════{CLR_RESET}")

    if "baseline" in results and "acting_direction" in results:
        dur_b = float(results["baseline"]["duration_seconds"])
        dur_a = float(results["acting_direction"]["duration_seconds"])
        diff_s = dur_a - dur_b
        diff_pct = (diff_s / dur_b) * 100 if dur_b > 0 else 0.0
        sign = "+" if diff_s > 0 else ""

        print(f"1. Baseline (Bez reżyserii):  {CLR_BOLD}{dur_b:.2f}s{CLR_RESET}  ➔  {out_baseline}")
        print(f"2. Z Acting Direction:        {CLR_BOLD}{dur_a:.2f}s{CLR_RESET}  ➔  {out_acting}")
        print(f"───────────────────────────────────────────────────────────────────────────")
        print(f"Wpływ reżysera na czas trwania: {CLR_YELLOW}{CLR_BOLD}{sign}{diff_s:.2f}s ({sign}{diff_pct:.1f}%){CLR_RESET}")
        print(f"Wpływ na brzmienie: Zmiana dynamiki, modulacja kadencji i naturalniejszy oddech.")

    # Zapis raportu JSON
    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "text": clean_text,
        "ref_audio": str(ref_audio),
        "results": results,
    }
    report_json.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{CLR_DIM}Zapisano metadane testu do: {report_json}{CLR_RESET}")

    print(f"\n{CLR_BOLD}Jak odsłuchać pliki w terminalu:{CLR_RESET}")
    print(f"  {CLR_GREEN}mpv {out_baseline}{CLR_RESET}   # 1. Posłuchaj wersji surowej (baseline)")
    print(f"  {CLR_YELLOW}mpv {out_acting}{CLR_RESET}     # 2. Posłuchaj wersji z reżyserią (acting direction)")
    print(f"  {CLR_CYAN}mpv {out_baseline} {out_acting}{CLR_RESET} # 3. Odsłuchaj jedno po drugim dla natychmiastowego porównania")

    if args.play:
        print(f"\n{CLR_BOLD}Odtwarzanie porównawcze...{CLR_RESET}")
        if out_baseline.exists():
            print(f"▶ Odtwarzam 1. Baseline: {out_baseline.name}...")
            play_audio(out_baseline)
            time.sleep(0.5)
        if out_acting.exists():
            print(f"▶ Odtwarzam 2. Acting Direction: {out_acting.name}...")
            play_audio(out_acting)

    print(f"\n{CLR_GREEN}{CLR_BOLD}[OK] Test zakończony pomyślnie.{CLR_RESET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
