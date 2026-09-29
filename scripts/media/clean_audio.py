#!/usr/bin/env python3
"""
Audyt i czyszczenie surowego nagrania audio (OBS / mikrofon):
- Przycięcie martwej ciszy na początku i końcu oraz usunięcie falstartów
- Normalizacja głośności EBU R128 (domyślnie -14 LUFS, True Peak -1.5 dB)
- Konwersja do formatu WAV 48kHz stereo (standard wideo)
- Wsparcie dla wycinania niepożądanych fragmentów (--exclude) bez obcinania całości nagrania
"""
import argparse
import subprocess
import sys
from pathlib import Path

def parse_time_to_seconds(ts_str: str) -> float:
    ts_str = ts_str.strip()
    if ":" in ts_str:
        parts = ts_str.split(":")
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
    return float(ts_str)

def parse_args():
    parser = argparse.ArgumentParser(
        description="Audyt, przycinanie i normalizacja audio do standardu EBU R128 (-14 LUFS)."
    )
    parser.add_argument("-i", "--input", required=True, type=Path, help="Ścieżka do wejściowego pliku audio/wideo")
    parser.add_argument("-o", "--output", required=True, type=Path, help="Ścieżka do wyjściowego pliku WAV")
    parser.add_argument("--start", "-s", default=None, help="Punkt startowy cięcia (opcjonalnie, np. 00:00:00.200)")
    parser.add_argument("--end", "-e", default=None, help="Punkt końcowy cięcia (opcjonalnie, domyślnie: do końca nagrania)")
    parser.add_argument("--exclude", "-x", default=None, help="Zakres czasu do wycięcia falstartu/pauzy (np. '28.9-32.6' lub '00:00:28.900-00:00:32.600')")
    parser.add_argument("--lufs", type=float, default=-14.0, help="Docelowa zintegrowana głośność LUFS (domyślnie: -14.0)")
    parser.add_argument("--true-peak", type=float, default=-1.5, help="Maksymalny poziom True Peak w dB (domyślnie: -1.5)")
    parser.add_argument("--sample-rate", type=int, default=48000, help="Częstotliwość próbkowania w Hz (domyślnie: 48000)")
    return parser.parse_args()

def clean_audio(input_file: Path, output_file: Path, start: str | None, end: str | None, exclude: str | None, lufs: float, true_peak: float, sample_rate: int):
    if not input_file.exists():
        print(f"[BŁĄD] Plik wejściowy nie istnieje: {input_file}", file=sys.stderr)
        sys.exit(1)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    cut_desc = f"[{start or '0'} -> {end or 'koniec'}]"
    if exclude:
        cut_desc += f" (wycięto: {exclude})"
    print(f"[1/2] Audytowanie, czyszczenie {cut_desc} i normalizacja {input_file.name}...")

    cmd = ["ffmpeg", "-y"]
    if start:
        cmd.extend(["-ss", str(start)])
    if end:
        cmd.extend(["-to", str(end)])
    
    cmd.extend(["-i", str(input_file)])

    # Budowanie filtrów audio
    af_filters = []
    if exclude:
        conditions = []
        for rng in exclude.split(","):
            rng = rng.strip()
            if "-" in rng:
                s_str, e_str = rng.split("-", 1)
                s_sec = parse_time_to_seconds(s_str)
                e_sec = parse_time_to_seconds(e_str)
                conditions.append(f"between(t,{s_sec:.3f},{e_sec:.3f})")
        if conditions:
            af_filters.append(f"aselect='not({'+'.join(conditions)})'")
            af_filters.append("asetpts=N/SR/TB")

    af_filters.append(f"loudnorm=I={lufs}:LRA=7:tp={true_peak}")

    cmd.extend([
        "-af", ",".join(af_filters),
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
        exclude=args.exclude,
        lufs=args.lufs,
        true_peak=args.true_peak,
        sample_rate=args.sample_rate
    )
