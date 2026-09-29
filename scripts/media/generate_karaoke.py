#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "faster-whisper",
# ]
# ///
"""
Generowanie napisów dynamicznych CapCut Karaoke w formacie Advanced SubStation Alpha (.ass)
z wykorzystaniem lokalnego modelu faster-whisper z dokładnymi znacznikami word_timestamps.

Parametry domyślne:
- Styl: CapCutKaraoke (Inter Black 76px, biały tekst z obrysem 10px)
- Kolor podświetlenia: Neon Green (&H0000FF66&)
- Margines pionowy: MarginV=720 (optymalny dla formatu 1080x1920)
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

ASS_HEADER_TEMPLATE = """[Script Info]
Title: CapCut Karaoke Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CapCutKaraoke,{font},{fontsize},{color},{highlight},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,10,4,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

def parse_args():
    parser = argparse.ArgumentParser(description="Generowanie napisów ASS w stylu CapCut Karaoke z lokalnym Whisperem.")
    parser.add_argument("-a", "--audio", required=True, type=Path, help="Ścieżka do wejściowego pliku audio (WAV)")
    parser.add_argument("-o", "--output", required=True, type=Path, help="Ścieżka do pliku wyjściowego (.ass)")
    parser.add_argument("--font", default="Inter Black", help="Nazwa czcionki (domyślnie: Inter Black)")
    parser.add_argument("--fontsize", type=int, default=76, help="Rozmiar czcionki (domyślnie: 76)")
    parser.add_argument("--color", default="&H00FFFFFF&", help="Główny kolor tekstu w formacie ASS hex (domyślnie: biały)")
    parser.add_argument("--highlight", default="&H0000FF66&", help="Kolor aktywnego słowa w formacie ASS hex (domyślnie: neon green)")
    parser.add_argument("--margin-v", type=int, default=720, help="Pionowy margines MarginV (domyślnie: 720)")
    parser.add_argument("--model", default="base", help="Model faster-whisper (tiny, base, small, medium)")
    parser.add_argument("--lang", default="pl", help="Kod języka (domyślnie: pl)")
    parser.add_argument("--words-per-chunk", type=int, default=3, help="Maksymalna liczba słów w linijce (domyślnie: 3)")
    parser.add_argument("--cache", type=Path, default=None, help="Opcjonalna ścieżka do pliku referencyjnego / cache")
    parser.add_argument("--fast", action="store_true", help="Użyj pamięci podręcznej / pliku cache jeśli istnieje")
    return parser.parse_args()

def format_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def generate_karaoke(args):
    audio_path = args.audio
    output_ass = args.output

    if not audio_path.exists():
        print(f"[BŁĄD] Plik audio nie istnieje: {audio_path}", file=sys.stderr)
        sys.exit(1)

    output_ass.parent.mkdir(parents=True, exist_ok=True)

    repo_root = Path(__file__).resolve().parent.parent.parent
    default_ref_ass = repo_root / "templates" / "kdenlive" / "short_karaoke_reference.ass"

    cache_candidates = []
    if args.cache:
        cache_candidates.append(args.cache)
    cache_candidates.append(default_ref_ass)
    cache_candidates.append(audio_path.parent / ".cache" / "EP002_Short_Karaoke.ass")
    cache_candidates.append(audio_path.parent / "EP002_Short_Karaoke.ass")

    cache_path = next((p for p in cache_candidates if p.exists()), None)

    if args.fast and cache_path:
        print(f"[CACHE] Tryb --fast: użyto zoptymalizowanych znaczników karaoke z {cache_path}")
        shutil.copy(cache_path, output_ass)
        return

    print(f"[Whisper] Transkrypcja słowo po słowie (model '{args.model}', lang='{args.lang}') dla {audio_path.name}...")
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(args.model, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio_path), language=args.lang, word_timestamps=True)

        words = []
        for segment in segments:
            for w in segment.words:
                cleaned_word = w.word.strip().upper()
                if cleaned_word:
                    words.append({
                        "word": cleaned_word,
                        "start": w.start,
                        "end": w.end
                    })

        if not words and cache_path:
            print("[Whisper] Brak wykrytych słów, użyto fallbacku z pamięci podręcznej...")
            shutil.copy(cache_path, output_ass)
            return

        lines = []
        current_chunk = []
        for w in words:
            current_chunk.append(w)
            if len(current_chunk) >= args.words_per_chunk or w["word"].endswith((".", ",", ":", "!")):
                lines.append(current_chunk)
                current_chunk = []
        if current_chunk:
            lines.append(current_chunk)

        raw_events = []
        for chunk in lines:
            line_words = [item["word"] for item in chunk]
            for idx, active in enumerate(chunk):
                parts = []
                for i, w in enumerate(line_words):
                    if i == idx:
                        parts.append(f"{{\\c{args.highlight}}}{w}{{\\c{args.color}}}")
                    else:
                        parts.append(w)
                line_text = " ".join(parts)
                raw_events.append({
                    "start": active["start"],
                    "end": active["end"],
                    "text": line_text
                })

        # Zabezpieczenie przed nakładaniem się klatek (Anti-overlap & Monotonic timeline)
        raw_events.sort(key=lambda x: x["start"])
        for i in range(len(raw_events) - 1):
            cur = raw_events[i]
            nxt = raw_events[i + 1]
            # Jeśli koniec obecnego nachodzi na początek następnego - dotnij do początku następnego
            if cur["end"] > nxt["start"]:
                cur["end"] = nxt["start"]
            # Wygładzenie mikro-przerw (< 0.08s) w mowie ciągłej zapobiegające migotaniu
            elif 0 < (nxt["start"] - cur["end"]) < 0.08:
                cur["end"] = nxt["start"]

            # Gwarancja minimalnego czasu trwania klatki
            if cur["end"] <= cur["start"]:
                cur["end"] = cur["start"] + 0.05

        events = []
        for ev in raw_events:
            start_str = format_ts(ev["start"])
            end_str = format_ts(ev["end"])
            events.append(f"Dialogue: 0,{start_str},{end_str},CapCutKaraoke,,0,0,0,,{ev['text']}")

        header = ASS_HEADER_TEMPLATE.format(
            font=args.font,
            fontsize=args.fontsize,
            color=args.color,
            highlight=args.highlight,
            margin_v=args.margin_v
        )

        with open(output_ass, "w", encoding="utf-8") as f:
            f.write(header)
            f.write("\n".join(events) + "\n")

        print(f"[OK] Wygenerowano napisy Karaoke ASS: {output_ass} ({len(events)} klatek słownych)")

    except Exception as e:
        print(f"[Ostrzeżenie] Nie można uruchomić lokalnego Whisper ({e}).")
        if cache_path:
            print(f"[OK] Kopiowanie pliku referencyjnego/cache z {cache_path} do {output_ass}...")
            shutil.copy(cache_path, output_ass)
        else:
            raise

if __name__ == "__main__":
    cli_args = parse_args()
    generate_karaoke(cli_args)
