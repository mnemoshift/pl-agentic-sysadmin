#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "faster-whisper",
#     "av<14",
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
import re
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
    parser.add_argument("-k", "--kdenlive", type=Path, default=None, help="Ścieżka do projektu .kdenlive pod który podpiąć napisy (opcjonalnie; autodetekcja jeśli nie podano)")
    parser.add_argument("--font", default="Inter Black", help="Nazwa czcionki (domyślnie: Inter Black)")
    parser.add_argument("--fontsize", type=int, default=76, help="Rozmiar czcionki (domyślnie: 76)")
    parser.add_argument("--color", default="&H00FFFFFF&", help="Główny kolor tekstu w formacie ASS hex (domyślnie: biały)")
    parser.add_argument("--highlight", default="&H0000FF66&", help="Kolor aktywnego słowa w formacie ASS hex (domyślnie: neon green)")
    parser.add_argument("--margin-v", type=int, default=720, help="Pionowy margines MarginV (domyślnie: 720)")
    parser.add_argument("--model", default="base", help="Model faster-whisper (tiny, base, small, medium)")
    parser.add_argument("--lang", default="pl", help="Kod języka (domyślnie: pl)")
    parser.add_argument("--words-per-chunk", type=int, default=3, help="Maksymalna liczba słów w linijce (domyślnie: 3)")
    parser.add_argument("--cache", type=Path, default=None, help="Opcjonalna ścieżka do pliku cache napisów ASS")
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

    if args.fast and args.cache and args.cache.exists():
        print(f"[CACHE] Tryb --fast: użyto zoptymalizowanych znaczników karaoke z {args.cache}")
        shutil.copy(args.cache, output_ass)
        attach_to_kdenlive(output_ass, args.kdenlive)
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

        if not words:
            print("[Whisper] Ostrzeżenie: Nie wykryto słów w pliku audio.", file=sys.stderr)
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
        attach_to_kdenlive(output_ass, args.kdenlive)

    except Exception as e:
        print(f"[BŁĄD Whisper]: {e}", file=sys.stderr)
        sys.exit(1)

def attach_to_kdenlive(output_ass: Path, kdenlive_arg: Path | None = None):
    kdenlive_path = kdenlive_arg
    if not kdenlive_path:
        # Autodetekcja projektu .kdenlive w katalogu projektu
        candidates = []
        if output_ass.parent.name == "assets":
            candidates.extend(output_ass.parent.parent.glob("*.kdenlive"))
        candidates.extend(output_ass.parent.glob("*.kdenlive"))
        valid_candidates = [c for c in candidates if not c.name.startswith(".")]
        if valid_candidates:
            kdenlive_path = valid_candidates[0]

    if not kdenlive_path:
        return

    if not kdenlive_path.exists():
        print(f"[Ostrzeżenie] Wskazany plik projektu Kdenlive nie istnieje: {kdenlive_path}", file=sys.stderr)
        return

    try:
        content = kdenlive_path.read_text(encoding="utf-8")

        # Wykrycie UUID traktora sekwencji
        m_uuid = re.search(r'<property name="kdenlive:docproperties\.activetimeline">({[0-9a-fA-F-]+})</property>', content)
        if not m_uuid:
            m_uuid = re.search(r'<tractor id="({[0-9a-fA-F-]+})"', content)
        seq_uuid = m_uuid.group(1) if m_uuid else "{d2e1ab66-a2fb-4e67-a630-734b7bdff6a6}"

        # Utworzenie i skopiowanie pliku sidecar Kdenlive
        target_sidecar = kdenlive_path.parent / f"{kdenlive_path.name}{seq_uuid}-1.ass"
        shutil.copy(output_ass, target_sidecar)
        print(f"[OK] Skopiowano plik sidecar: {target_sidecar.name}")

        # Aktualizacja sequenceproperties.subtitlesList
        sub_list_xml = f'''<property name="kdenlive:sequenceproperties.subtitlesList">[
    {{
        "file": "{target_sidecar.resolve()}",
        "id": 1,
        "name": "CapCut Karaoke"
    }}
]
</property>'''
        if '<property name="kdenlive:sequenceproperties.subtitlesList">' in content:
            content = re.sub(
                r'<property name="kdenlive:sequenceproperties\.subtitlesList">.*?</property>',
                sub_list_xml,
                content,
                flags=re.DOTALL
            )
        else:
            needle = '<property name="kdenlive:sequenceproperties.globalSubtitleStyles">[\n]\n</property>'
            if needle in content:
                content = content.replace(needle, f"{needle}\n  {sub_list_xml}")

        # Aktualizacja activeSubtitleIndex
        if '<property name="kdenlive:sequenceproperties.kdenlive:activeSubtitleIndex">' in content:
            content = re.sub(
                r'<property name="kdenlive:sequenceproperties\.kdenlive:activeSubtitleIndex">.*?</property>',
                '<property name="kdenlive:sequenceproperties.kdenlive:activeSubtitleIndex">1</property>',
                content
            )

        # Sprawdzenie obecności filtru avfilter.subtitles
        if '<property name="mlt_service">avfilter.subtitles</property>' in content:
            content = re.sub(
                r'(<property name="mlt_service">avfilter\.subtitles</property>.*?<property name="av\.filename">)[^<]+(</property>)',
                rf'\g<1>{target_sidecar.resolve()}\g<2>',
                content,
                flags=re.DOTALL
            )
        else:
            filter_nums = [int(n) for n in re.findall(r'<filter id="filter(\d+)"', content)]
            new_id_num = max(filter_nums, default=16) + 1
            filter_xml = f'''   <filter id="filter{new_id_num}">
    <property name="mlt_service">avfilter.subtitles</property>
    <property name="av.alpha">1</property>
    <property name="internal_added">237</property>
    <property name="av.filename">{target_sidecar.resolve()}</property>
   </filter>
  </tractor>'''
            escaped_seq = re.escape(seq_uuid)
            tractor_pat = rf'(<tractor id="{escaped_seq}"[^>]*>.*?)(\s*</tractor>)'
            if re.search(tractor_pat, content, flags=re.DOTALL):
                content = re.sub(tractor_pat, rf'\g<1>\n{filter_xml}', content, count=1, flags=re.DOTALL)
            else:
                content = re.sub(r'(\s*</tractor>)', f'\n{filter_xml}', content, count=1)

        kdenlive_path.write_text(content, encoding="utf-8")
        print(f"[OK] Podpięto napisy Karaoke pod projekt Kdenlive: {kdenlive_path.name}")

    except Exception as e:
        print(f"[Ostrzeżenie] Nie udało się podpiąć napisów pod projekt Kdenlive: {e}", file=sys.stderr)

if __name__ == "__main__":
    cli_args = parse_args()
    generate_karaoke(cli_args)
