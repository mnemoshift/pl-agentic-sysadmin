#!/usr/bin/env -S uv run python
"""
Workstation Hub: Skrypt demonstracyjno-testowy Qwen3-TTS & Breeze-TTS (Acting Direction Comparison).

Porównuje syntezę mowy tego samego tekstu w dwóch wariantach:
1. Baseline (BEZ Acting Direction): neutralna wypowiedź bez instrukcji.
2. Acting Direction (Z Reżyserią): synteza z instrukcją reżyserską (instruct)
   definiującą emocje, dynamikę, tempo i prozodię.

Wspiera:
- Qwen3-TTS 1.7B CustomVoice (natywne wsparcie instruct, wbudowani lektorzy np. Ryan, Aiden)
- Qwen3-TTS 0.6B Base (zero-shot voice clone z próbki ref_audio)
- Breeze-TTS-2 (zero-shot voice clone + natywna instrukcja instruct)
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "media"))

from convert_voice_timbre import ToneColorConverterEngine  # noqa: E402
from text_director import clean_voiceover_text, strip_voice_tags  # noqa: E402
from tts_engines.qwen import QwenTTSEngine  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("compare_acting")

# Kolory ANSI
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
    """Odczytuje czas trwania i częstotliwość próbkowania pliku WAV."""
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
    """Odtwarza plik audio za pomocą mpv, ffplay lub aplay."""
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
        description="Porównanie syntezy mowy: Bez Acting Direction vs Z Acting Direction (EP004b Benchmark)",
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
        help="Instrukcja reżyserska (Acting Direction) przekazywana modelowi",
    )
    parser.add_argument(
        "--engine",
        type=str,
        choices=["qwen", "breeze"],
        default="qwen",
        help="Silnik TTS: qwen (Qwen3-TTS) lub breeze (Breeze-TTS-2)",
    )
    parser.add_argument(
        "--model-id",
        type=str,
        default="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        help="Model Qwen: np. Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice (lub skrót 'custom'), Qwen/Qwen3-TTS-12Hz-0.6B-Base (lub 'base')",
    )
    parser.add_argument(
        "--speaker",
        type=str,
        default="Ryan",
        help="Głos dla trybu CustomVoice (np. Ryan - dynamic English, Aiden - sunny American English)",
    )
    parser.add_argument(
        "--ref-audio",
        type=Path,
        default=None,
        help="Ścieżka do próbki referencyjnej głosu lektora (wymagana dla modeli Base i Breeze)",
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
        default=REPO_ROOT / "work" / "acting_test",
        help="Katalog docelowy dla wygenerowanych próbek audio",
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
        "--no-timbre",
        action="store_true",
        help="Wyłącz etap 3: transfer barwy głosu (pozostawia czyste wyjście lektora)",
    )
    parser.add_argument(
        "--tau",
        type=float,
        default=0.3,
        help="Współczynnik transferu barwy (tau) dla OpenVoice V2 (0.15 - 0.45)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed generatora liczb losowych dla powtarzalności syntezy",
    )

    args = parser.parse_args()

    # Normalizacja skrótów model-id
    mid = args.model_id.lower().strip()
    if mid in ("custom", "customvoice", "1.7b", "1.7b-customvoice"):
        args.model_id = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    elif mid in ("base", "0.6b", "0.6b-base"):
        args.model_id = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"

    is_custom_voice = "customvoice" in args.model_id.lower() and args.engine == "qwen"

    # Wyszukanie próbki referencyjnej głosu
    ref_audio = args.ref_audio
    ref_transcript = args.ref_transcript
    if not ref_audio:
        ref_audio, default_transcript = find_default_reference_audio(REPO_ROOT)
        if not ref_transcript:
            ref_transcript = default_transcript

    if not is_custom_voice:
        if not ref_audio or not ref_audio.exists():
            print(f"{CLR_RED}[BŁĄD] Model typu Base / Breeze wymaga próbki referencyjnej głosu!{CLR_RESET}")
            print(f"Umieść plik .wav w {REPO_ROOT}/work/voice_sample/ lub wskaż go parametrem --ref-audio.")
            return 1

    clean_text = strip_voice_tags(clean_voiceover_text(args.text))
    acting_instruction = args.instruction.strip()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_baseline = args.output_dir / "1_baseline_without_acting.wav"
    out_acting = args.output_dir / "2_with_acting_direction.wav"
    out_timbre = args.output_dir / "3_with_acting_and_timbre.wav"
    report_json = args.output_dir / "acting_comparison_report.json"

    # Nagłówek CLI
    engine_label = (
        f"Qwen3-TTS 1.7B CustomVoice (Głos: {args.speaker}, Apache 2.0)"
        if is_custom_voice
        else "Qwen3-TTS 0.6B Base (Klon z pliku audio, Apache 2.0)"
        if args.engine == "qwen"
        else "Breeze-TTS-2 (MediaTek Zero-Shot Clone, CC-BY-NC)"
    )

    print(f"\n{CLR_CYAN}{CLR_BOLD}═══════════════════════════════════════════════════════════════════════════{CLR_RESET}")
    print(f"{CLR_CYAN}{CLR_BOLD}             MNEMOSHIFT // ACTING DIRECTION BENCHMARK              {CLR_RESET}")
    print(f"{CLR_CYAN}{CLR_BOLD}═══════════════════════════════════════════════════════════════════════════{CLR_RESET}")
    print(f"{CLR_BOLD}Silnik i model:{CLR_RESET}     {CLR_CYAN}{engine_label}{CLR_RESET}")
    print(f"{CLR_BOLD}Tekst do syntezy:{CLR_RESET}   \"{CLR_GREEN}{clean_text}{CLR_RESET}\"")
    print(f"{CLR_BOLD}Reżyseria (Acting):{CLR_RESET} \"{CLR_YELLOW}{acting_instruction}{CLR_RESET}\"")
    if is_custom_voice:
        print(f"{CLR_BOLD}Lektor bazowy:{CLR_RESET}      {args.speaker}")
        if ref_audio and ref_audio.exists() and not args.no_timbre:
            print(f"{CLR_BOLD}Transfer barwy:{CLR_RESET}     ➔ {ref_audio.name} (OpenVoice V2 MIT, tau={args.tau})")
    else:
        print(f"{CLR_BOLD}Próbka audio (Ref):{CLR_RESET} {ref_audio} ({CLR_DIM}{ref_audio.stat().st_size // 1024} KB{CLR_RESET})")
    print(f"{CLR_BOLD}Katalog wyjściowy:{CLR_RESET}  {args.output_dir}")
    print(f"{CLR_CYAN}───────────────────────────────────────────────────────────────────────────{CLR_RESET}\n")

    # Inicjalizacja instancji silnika
    if args.engine == "breeze":
        from tts_engines.breeze import BreezeTTSEngine
        engine = BreezeTTSEngine()
    else:
        engine = QwenTTSEngine(model_id=args.model_id)

    results: dict[str, dict[str, float | str | int | None]] = {}

    # FAZA 1: Baseline (bez Acting Direction)
    if not args.only_acting:
        print(f"\n{CLR_BOLD}▶ FAZA 1: Generowanie BEZ Acting Direction (Baseline)...{CLR_RESET}")
        print(f"{CLR_DIM}  Instrukcja jest całkowicie wyłączona (wzorzec neutralny).{CLR_RESET}")
        t0 = time.time()
        ok_base = engine.synthesize(
            text=clean_text,
            out_wav=out_baseline,
            ref_audio=ref_audio,
            ref_transcript=ref_transcript,
            instruction="",  # PUSTA instrukcja
            speaker=args.speaker,
            apply_timbre=False,
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
        print(f"\n{CLR_BOLD}▶ FAZA 2: Generowanie Z Acting Direction (Instruct Control)...{CLR_RESET}")
        print(f"{CLR_DIM}  Przekazana instrukcja reżyserska: \"{acting_instruction}\"{CLR_RESET}")
        t0 = time.time()
        ok_act = engine.synthesize(
            text=clean_text,
            out_wav=out_acting,
            ref_audio=ref_audio,
            ref_transcript=ref_transcript,
            instruction=acting_instruction,  # PEŁNA instrukcja
            speaker=args.speaker,
            apply_timbre=False,
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

    # FAZA 3: Transfer Barwy Głosu (OpenVoice V2 Tone Color Converter MIT)
    should_run_timbre = (
        is_custom_voice
        and not args.no_timbre
        and not args.only_baseline
        and ref_audio
        and ref_audio.exists()
        and out_acting.exists()
    )
    if should_run_timbre:
        print(f"\n{CLR_BOLD}▶ FAZA 3: Transfer Barwy Głosu na Twój głos (OpenVoice V2 MIT)...{CLR_RESET}")
        print(f"{CLR_DIM}  Docelowa próbka krtani/rezonansu: {ref_audio.name} | tau: {args.tau}{CLR_RESET}")
        t0 = time.time()
        try:
            converter = ToneColorConverterEngine()
            converter.convert_timbre(
                source_audio=out_acting,
                target_ref_audio=ref_audio,
                output_audio=out_timbre,
                tau=args.tau,
            )
            t_timbre = time.time() - t0
            dur_timbre, sr_timbre = get_audio_duration_and_sr(out_timbre)
            print(f"{CLR_GREEN}✓ Gotowe w {t_timbre:.2f}s{CLR_RESET} | Długość audio: {CLR_BOLD}{dur_timbre:.2f}s{CLR_RESET} | Zapisano: {out_timbre.name}")
            results["acting_and_timbre"] = {
                "file": str(out_timbre),
                "duration_seconds": round(dur_timbre, 2),
                "generation_time_seconds": round(t_timbre, 2),
                "sample_rate": sr_timbre,
                "target_ref_audio": str(ref_audio),
                "tau": args.tau,
            }
        except Exception as e:
            logger.warning("Błąd transferu barwy głosu w fazie 3: %s", e)

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

        print(f"1. Baseline (Bez reżyserii):     {CLR_BOLD}{dur_b:.2f}s{CLR_RESET}  ➔  {out_baseline}")
        print(f"2. Z Acting Direction:           {CLR_BOLD}{dur_a:.2f}s{CLR_RESET}  ➔  {out_acting}")
        if "acting_and_timbre" in results:
            dur_t = float(results["acting_and_timbre"]["duration_seconds"])
            print(f"3. Z Twoją barwą głosu (Jarek):  {CLR_BOLD}{dur_t:.2f}s{CLR_RESET}  ➔  {out_timbre}")
        print("───────────────────────────────────────────────────────────────────────────")
        print(f"Wpływ reżysera na czas trwania: {CLR_YELLOW}{CLR_BOLD}{sign}{diff_s:.2f}s ({sign}{diff_pct:.1f}%){CLR_RESET}")

    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "engine": args.engine,
        "model_id": args.model_id,
        "speaker": args.speaker if is_custom_voice else None,
        "text": clean_text,
        "results": results,
    }
    report_json.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{CLR_DIM}Zapisano raport JSON do: {report_json}{CLR_RESET}")

    print(f"\n{CLR_BOLD}Jak odsłuchać pliki w terminalu:{CLR_RESET}")
    print(f"  {CLR_GREEN}mpv {out_baseline}{CLR_RESET}   # 1. Posłuchaj wersji surowej (baseline)")
    print(f"  {CLR_YELLOW}mpv {out_acting}{CLR_RESET}     # 2. Posłuchaj wersji z reżyserią (acting direction)")
    if "acting_and_timbre" in results:
        print(f"  {CLR_CYAN}mpv {out_timbre}{CLR_RESET}     # 3. Posłuchaj wersji z Twoją barwą głosu (reżyseria + Twój głos)")
        print(f"  {CLR_BOLD}mpv {out_baseline} {out_acting} {out_timbre}{CLR_RESET} # 4. Odsłuchaj wszystkie 3 po kolei dla pełnego porównania")
    else:
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
            time.sleep(0.5)
        if out_timbre.exists():
            print(f"▶ Odtwarzam 3. Twoja barwa głosu: {out_timbre.name}...")
            play_audio(out_timbre)

    print(f"\n{CLR_GREEN}{CLR_BOLD}[OK] Test zakończony pomyślnie.{CLR_RESET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
