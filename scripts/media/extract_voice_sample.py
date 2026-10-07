#!/usr/bin/env python3
"""
Ekstrakcja czystej próbki referencyjnej głosu (Voice Cloning Sample):
- Wycięcie fragmentu (3-10 sekund) ze wskazanego pliku wideo lub audio.
- Konwersja do formatu studyjnego dla modeli TTS (24kHz / 48kHz mono PCM WAV).
- Opcjonalne zapisanie towarzyszącego pliku tekstowego z transkrypcją referencyjną.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Ekstrakcja próbki głosu do klonowania zero-shot.")
    parser.add_argument("-i", "--input", required=True, type=Path, help="Ścieżka do źródłowego pliku wideo lub audio (np. w work/)")
    parser.add_argument("-o", "--output", required=True, type=Path, help="Ścieżka do wyjściowego pliku referencyjnego WAV")
    parser.add_argument("-s", "--start", required=True, type=str, help="Czas rozpoczęcia fragmentu (np. 00:00:12.000 lub 12.0)")
    parser.add_argument("-e", "--end", required=True, type=str, help="Czas zakończenia fragmentu (np. 00:00:20.300 lub 20.3)")
    parser.add_argument("-t", "--transcript", type=str, default=None, help="Dokładna transkrypcja wypowiedzi w wycinku")
    parser.add_argument("--sample-rate", type=int, default=24000, help="Częstotliwość próbkowania w Hz (domyślnie: 24000 pod modele TTS)")
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = args.input.resolve()
    output_path = args.output.resolve()

    if not input_path.exists():
        print(f"[BŁĄD] Plik wejściowy nie istnieje: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Wycinanie próbki głosu z {input_path.name} [{args.start} -> {args.end}]...")

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(args.start),
        "-to", str(args.end),
        "-i", str(input_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(args.sample_rate),
        "-ac", "1",
        str(output_path)
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print(f"[OK] Zapisano próbkę audio: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"[BŁĄD] Błąd ffmpeg podczas wycinania próbki: {e.stderr.decode()}", file=sys.stderr)
        sys.exit(1)

    if args.transcript:
        txt_path = output_path.with_suffix(".txt")
        txt_path.write_text(args.transcript.strip() + "\n", encoding="utf-8")
        print(f"[OK] Zapisano transkrypcję referencyjną: {txt_path.name}")


if __name__ == "__main__":
    main()
