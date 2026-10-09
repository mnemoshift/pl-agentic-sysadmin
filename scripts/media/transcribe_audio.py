#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "faster-whisper",
#     "av<14",
# ]
# ///
"""
Transkrypcja i synchronizacja scen audio dla YouTube Shorts.
Wykorzystuje model faster-whisper oraz opcjonalny scenariusz referencyjny (short_script.md).
Obsługuje dynamiczne parsowanie dowolnego scenariusza lub automatyczną generację scen z mowy.
Generuje plik JSON ze znacznikami oraz czytelny raport Markdown (Transcript.md).
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Domyślny pusty szablon scen (brak sztucznego hardcodingu tekstów)
DEFAULT_SCENES = []


def parse_args():
    parser = argparse.ArgumentParser(description="Transkrypcja i synchronizacja scen audio Whisper.")
    parser.add_argument("-a", "--audio", required=True, type=Path, help="Ścieżka do oczyszczonego pliku audio (WAV)")
    parser.add_argument("-o", "--output-json", type=Path, default=None, help="Ścieżka wyjściowa do pliku JSON")
    parser.add_argument("--output-md", type=Path, default=None, help="Ścieżka wyjściowa do raportu Markdown")
    parser.add_argument("--script", type=Path, default=None, help="Ścieżka do pliku scenariusza (np. short_script.md)")
    parser.add_argument("--model", default="base", help="Model faster-whisper (tiny, base, small)")
    parser.add_argument("--fast", action="store_true", help="Użyj znaczników referencyjnych / czasu ze scenariusza")
    return parser.parse_args()

def parse_short_script(script_path: Path) -> list[dict]:
    """
    Parsuje plik markdown scenariusza short_script.md.
    Wyciąga numery scen, kwestie lektora, koncepcje wizualne, tytuły na osi czasu oraz znaczniki czasu.
    """
    if not script_path or not script_path.exists():
        return []

    try:
        content = script_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[Ostrzeżenie] Nie udało się odczytać scenariusza {script_path}: {e}", file=sys.stderr)
        return []

    scenes = []
    # Rozbijamy na bloki: "#### Scena X" lub "### Scena X"
    scene_blocks = re.split(r'(?m)^#{3,4}\s+Scena\s+(\d+)', content)
    for i in range(1, len(scene_blocks), 2):
        scene_num = int(scene_blocks[i])
        block_text = scene_blocks[i+1]

        # Zakres czasu z nagłówka, np. [0:00 - 0:05]
        time_match = re.search(r'\[(\d+):(\d+(?:\.\d+)?)\s*-\s*(\d+):(\d+(?:\.\d+)?)\]', block_text[:120])
        start_sec = 0.0
        end_sec = 0.0
        if time_match:
            sm, ss, em, es = time_match.groups()
            start_sec = round(int(sm) * 60 + float(ss), 2)
            end_sec = round(int(em) * 60 + float(es), 2)

        # Kwestia lektora
        text = ""
        text_match = re.search(r'\*\s*\*\*Kwestia lektora:\*\*\s*\n\s*(?:[„"«\*]+)?(.*?)(?:[”"»\*]+)?(?:\n\s*\*|\n\n|$)', block_text, re.DOTALL)
        if text_match:
            raw_text = text_match.group(1).strip().strip('„”"\'*')
            text = re.sub(r'\s+', ' ', raw_text)

        # Koncepcja graficzna lub wideo
        visual = ""
        vis_match = re.search(r'\*\s*\*\*(?:Koncepcja graficzna|Koncepcja wideo)[^*]*\*\*\s*\n\s*(.*?)(?:\n\s*\*|\n\n|$)', block_text, re.DOTALL)
        if vis_match:
            raw_vis = vis_match.group(1).strip()
            visual = re.sub(r'\s+', ' ', raw_vis)

        # Tytuł na osi czasu (Ścieżka V3)
        title = ""
        title_match = re.search(r'\*\s*\*\*Tytuł na osi czasu[^*]*\*\*\s*\n\s*`?(.*?)`?(?:\n\s*\*|\n\n|$)', block_text, re.DOTALL)
        if title_match:
            raw_title = title_match.group(1).strip().strip('`*')
            title = re.sub(r'\s+', ' ', raw_title)

        if not title:
            title = f"SCENA {scene_num}"

        is_placeholder = text.startswith("[") and text.endswith("]")

        scenes.append({
            "scene": scene_num,
            "title": title,
            "text": "" if is_placeholder else text,
            "visual": visual if not (visual.startswith("[") and visual.endswith("]")) else f"Kadr pionowy 9:16 (Scena {scene_num})",
            "start": start_sec,
            "end": end_sec,
            "is_placeholder": is_placeholder
        })

    return scenes

def find_script_file(audio_path: Path, script_arg: Path | None) -> Path | None:
    if script_arg and script_arg.exists():
        return script_arg

    candidates = [
        audio_path.parent / "short_script.md",
        audio_path.parent.parent / "input" / "short_script.md",
        audio_path.parent / "input" / "short_script.md",
        Path.cwd() / "templates" / "kdenlive" / "short_script.md"
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

def transcribe(audio_path: Path, output_json: Path, output_md: Path, fast: bool, model_name: str, script_arg: Path | None):
    if not audio_path.exists():
        print(f"[BŁĄD] Plik audio nie istnieje: {audio_path}", file=sys.stderr)
        sys.exit(1)

    # 1. Sprawdzanie i parsowanie scenariusza
    script_file = find_script_file(audio_path, script_arg)
    parsed_scenes = []
    if script_file:
        print(f"[Scenariusz] Wczytywanie scenariusza: {script_file}")
        parsed_scenes = parse_short_script(script_file)

    # Ustalanie bazowej listy scen
    if parsed_scenes and not all(s.get("is_placeholder", False) for s in parsed_scenes):
        scenes = [dict(s) for s in parsed_scenes]
    else:
        scenes = []

    whisper_success = False
    if not fast:
        print(f"[Whisper] Uruchamianie lokalnego modelu '{model_name}' dla {audio_path.name}...")
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            segments, _ = model.transcribe(str(audio_path), language="pl", word_timestamps=True)
            seg_list = list(segments)

            if seg_list:
                whisper_success = True
                if not scenes:
                    for idx, seg in enumerate(seg_list, 1):
                        scenes.append({
                            "scene": idx,
                            "title": f"SCENA {idx}",
                            "text": seg.text.strip(),
                            "visual": "Kadr wideo",
                            "start": round(seg.start, 2),
                            "end": round(seg.end, 2)
                        })
                elif len(seg_list) >= len(scenes):
                    for idx in range(len(scenes)):
                        scenes[idx]["start"] = round(seg_list[idx].start, 2)
                        scenes[idx]["end"] = round(seg_list[idx].end, 2)
                        if not scenes[idx]["text"]:
                            scenes[idx]["text"] = seg_list[idx].text.strip()
                else:
                    for idx, seg in enumerate(seg_list):
                        if idx < len(scenes):
                            scenes[idx]["start"] = round(seg.start, 2)
                            scenes[idx]["end"] = round(seg.end, 2)
                            if not scenes[idx]["text"]:
                                scenes[idx]["text"] = seg.text.strip()
        except Exception as e:
            print(f"[Whisper Info] Błąd transkrypcji Whisper: {e}")

    if not scenes:
        print(f"[BŁĄD] Nie udało się wygenerować scen (brak scenariusza oraz brak transkrypcji).", file=sys.stderr)
        sys.exit(1)

    if not whisper_success and not fast:
        print(f"[Whisper Info] Użyto znaczników ze scenariusza lub bazy referencyjnej.")

    # Wyliczanie długości
    for s in scenes:
        s["duration"] = round(s["end"] - s["start"], 2)

    # Zapis JSON
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(scenes, indent=2, ensure_ascii=False))

    # Generowanie raportu Markdown
    md_content = "# Transkrypcja i Harmonogram Scen pod Montaż (YouTube Shorts)\n\n"
    md_content += f"> **Plik źródłowy audio:** `{audio_path.name}`  \n"
    if script_file:
        md_content += f"> **Scenariusz referencyjny:** `{script_file}`  \n"
    md_content += f"> **Liczba scen:** {len(scenes)}  \n"
    total_time = scenes[-1]['end'] if scenes else 0.0
    md_content += f"> **Całkowity czas:** {total_time}s\n\n"
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
        txt_snippet = s['text'][:45] + "..." if len(s['text']) > 45 else s['text']
        print(f"  Scena {s['scene']} [{s['start']:05.2f}s -> {s['end']:05.2f}s] ({s['duration']}s): {txt_snippet}")
    print("==========================================================")
    if output_md:
        print(f"[OK] Zapisano raport transkrypcji: {output_md}")

if __name__ == "__main__":
    args = parse_args()
    out_json = args.output_json or (args.audio.parent / f"{args.audio.stem}_Transcript.json")
    out_md = args.output_md or (args.audio.parent / f"{args.audio.stem}_Transcript.md")
    transcribe(args.audio, out_json, out_md, args.fast, args.model, args.script)
