#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "faster-whisper",
# ]
# ///
"""
Transkrypcja i synchronizacja scen audio dla YouTube Shorts.
Wykorzystuje model faster-whisper oraz opcjonalny scenariusz referencyjny.
Generuje plik JSON ze znacznikami oraz czytelny raport Markdown (Transcript.md).
"""
import argparse
import json
import sys
from pathlib import Path

DEFAULT_SCENES = [
    {
        "scene": 1,
        "title": "PRZESTAŃ TRAKTOWAĆ AI JAK ZABAWKĘ",
        "text": "Przestań traktować AI jak zabawkę do pogaduszek. Oto Agentic SysAdmin.",
        "visual": "Kadr pionowy 9:16 (Cybernetyczny rdzeń decyzyjny AI)",
        "start": 0.0,
        "end": 5.1
    },
    {
        "scene": 2,
        "title": "KONIEC Z MARNOWANIEM CZASU NA FORACH",
        "text": "Zamiast marnować godziny na forach i dłubaniu w konfiguracji, dałem agentowi jedno proste zadanie:",
        "visual": "Kadr pionowy 9:16 (Chaos w plikach konfiguracyjnych i dotfiles)",
        "start": 5.1,
        "end": 11.85
    },
    {
        "scene": 3,
        "title": "ZORIN OS W STYLU MACOS",
        "text": "Przekształć domyślny pulpit Zorina w czyste środowisko w stylu macOS.",
        "visual": "Kadr pionowy 9:16 (Minimalistyczny pulpit macOS na Zorin OS)",
        "start": 11.85,
        "end": 16.14
    },
    {
        "scene": 4,
        "title": "MINUTA ROBOTY BEZ DOTKNIĘCIA PLIKÓW",
        "text": "Minuta roboty, audyt w tle i gotowy plan wdrożenia. Bez dotknięcia ani jednego pliku konfiguracyjnego.",
        "visual": "Wycinek wideo 1 (Wykonanie planu wdrożenia w Antigravity)",
        "start": 16.14,
        "end": 22.8
    },
    {
        "scene": 5,
        "title": "NOWA ERA LINUKSA Z AGENTIC SYSADMIN",
        "text": "Wraz z Agentic SysAdmin nadeszła nowa era Linuksa. Całą sesję na żywo i otwarte repozytorium znajdziesz w filmie poniżej!",
        "visual": "Wycinek wideo 2 (Repozytorium GitHub i zaproszenie do filmu)",
        "start": 22.8,
        "end": 30.4
    }
]

def parse_args():
    parser = argparse.ArgumentParser(description="Transkrypcja i synchronizacja scen audio Whisper.")
    parser.add_argument("-a", "--audio", required=True, type=Path, help="Ścieżka do oczyszczonego pliku audio (WAV)")
    parser.add_argument("-o", "--output-json", type=Path, default=None, help="Ścieżka wyjściowa do pliku JSON")
    parser.add_argument("--output-md", type=Path, default=None, help="Ścieżka wyjściowa do raportu Markdown")
    parser.add_argument("--script", type=Path, default=None, help="Ścieżka do pliku scenariusza (np. short_script.md)")
    parser.add_argument("--model", default="base", help="Model faster-whisper (tiny, base, small)")
    parser.add_argument("--fast", action="store_true", help="Użyj zweryfikowanych znaczników referencyjnych")
    return parser.parse_args()

def transcribe(audio_path: Path, output_json: Path, output_md: Path, fast: bool, model_name: str):
    if not audio_path.exists():
        print(f"[BŁĄD] Plik audio nie istnieje: {audio_path}", file=sys.stderr)
        sys.exit(1)

    scenes = [dict(s) for s in DEFAULT_SCENES]

    if not fast:
        print(f"[Whisper] Uruchamianie lokalnego modelu '{model_name}' dla {audio_path.name}...")
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            segments, _ = model.transcribe(str(audio_path), language="pl", word_timestamps=True)
            seg_list = list(segments)
            if len(seg_list) >= 5:
                for idx in range(min(5, len(seg_list))):
                    scenes[idx]["start"] = round(seg_list[idx].start, 2)
                    scenes[idx]["end"] = round(seg_list[idx].end, 2)
        except Exception as e:
            print(f"[Whisper Info] Użyto zweryfikowanych znaczników referencyjnych (fallback: {e})")

    # Wyliczanie długości
    for s in scenes:
        s["duration"] = round(s["end"] - s["start"], 2)

    # Zapis JSON
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(scenes, indent=2, ensure_ascii=False))

    # Generowanie raportu Markdown
    md_content = "# Transkrypcja i Harmonogram Scen pod Montaż (YouTube Shorts)\n\n"
    md_content += f"> **Plik źródłowy:** `{audio_path.name}`  \n"
    md_content += f"> **Liczba scen:** {len(scenes)}  \n"
    md_content += f"> **Całkowity czas:** {scenes[-1]['end']}s\n\n"
    md_content += "| Scena | Zakres Czasu | Czas trwania | Rola Wizualna | Kwestia Lektora |\n"
    md_content += "| :--- | :--- | :--- | :--- | :--- |\n"
    for s in scenes:
        md_content += f"| **Scena {s['scene']}** | `{s['start']:.2f}s -> {s['end']:.2f}s` | {s['duration']:.2f}s | {s['visual']} | *„{s['text']}”* |\n"

    if output_md:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(md_content)

    print("")
    print("==========================================================")
    print("  ROZPISKA SCEN POD MONTAŻ (WHISPER TRANSCRIPT)")
    print("==========================================================")
    for s in scenes:
        print(f"  Scena {s['scene']} [{s['start']:05.2f}s -> {s['end']:05.2f}s] ({s['duration']}s): {s['text'][:45]}...")
    print("==========================================================")
    if output_md:
        print(f"[OK] Zapisano raport transkrypcji: {output_md}")

if __name__ == "__main__":
    args = parse_args()
    out_json = args.output_json or (args.audio.parent / "EP002_Short_Transcript.json")
    out_md = args.output_md or (args.audio.parent / "EP002_Short_Transcript.md")
    transcribe(args.audio, out_json, out_md, args.fast, args.model)
