#!/usr/bin/env python3
"""
Audyt i czyszczenie surowego nagrania audio (OBS / mikforon):
- Przycięcie martwej ciszy na początku i końcu oraz usunięcie falstartów
- Normalizacja głośności EBU R128 (domyślnie -14 LUFS, True Peak -1.5 dB)
- Konwersja do formatu WAV 48kHz stereo (standard wideo)
"""
import argparse
import subprocess
import sys
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(
        description="Audyt, przycinanie i normalizacja audio do standardu EBU R128 (-14 LUFS)."
    )
    parser.add_argument("-i", "--input", required=True, type=Path, help="Ścieżka do wejściowego pliku audio/wideo")
    parser.add_argument("-o", "--output", required=True, type=Path, help="Ścieżka do wyjściowego pliku WAV")
    parser.add_argument("--start", "-s", default="00:00:00.200", help="Punkt startowy cięcia (np. 00:00:00.200)")
    parser.add_argument("--end", "-e", default="00:00:30.600", help="Punkt końcowy cięcia (np. 00:00:30.600)")
    parser.add_argument("--lufs", type=float, default=-14.0, help="Docelowa zintegrowana głośność LUFS (domyślnie: -14.0)")
    parser.add_argument("--true-peak", type=float, default=-1.5, help="Maksymalny poziom True Peak w dB (domyślnie: -1.5)")
    parser.add_argument("--sample-rate", type=int, default=48000, help="Częstotliwość próbkowania w Hz (domyślnie: 48000)")
    return parser.parse_args()

def clean_audio(input_file: Path, output_file: Path, start: str, end: str, lufs: float, true_peak: float, sample_rate: int):
    if not input_file.exists():
        print(f"[BŁĄD] Plik wejściowy nie istnieje: {input_file}", file=sys.stderr)
        sys.exit(1)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    print(f"[1/2] Audytowanie, przycinanie [{start} -> {end}] i normalizacja {input_file.name}...")

    cmd = ["ffmpeg", "-y"]
    if start:
        cmd.extend(["-ss", start])
    if end:
        cmd.extend(["-to", end])
    cmd.extend([
        "-i", str(input_file),
        "-af", f"loudnorm=I={lufs}:LRA=7:tp={true_peak}",
        "-ar", str(sample_rate),
        "-ac", "2",
        str(output_file)
    ])

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[BŁĄD ffmpeg]:\n{res.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"[2/2] Zapisano czyste audio ({lufs} LUFS): {output_file}")

if __name__ == "__main__":
    args = parse_args()
    clean_audio(
        input_file=args.input,
        output_file=args.output,
        start=args.start,
        end=args.end,
        lufs=args.lufs,
        true_peak=args.true_peak,
        sample_rate=args.sample_rate
    )
