#!/usr/bin/env python3
"""
Workstation Hub: Autonomiczny generator lektora / voiceoveru AI w języku polskim.
Generuje profesjonalną ścieżkę lektorską na podstawie pliku Markdown (.md),
odwzorowując barwę głosu i dykcję lektora za pomocą lokalnej konwersji głosu (Kanade Zero-Shot).

Funkcjonalności:
- Inteligentny parser skryptów czytanych Markdown (usuwanie metadanych, wtrąceń reżyserskich `*(...)*`,
  nagłówków i znaczników intonacyjnych `[akcent]`, precyzyjna obsługa pauz `[pauza 1s]`).
- Dwuetapowa synteza z klonowaniem barwy:
    1. Czysta polska artykulacja i dykcja (Edge-TTS pl-PL-MarekNeural).
    2. Zero-shot transfer barwy i tembru głosu lektora (Kanade Voice Conversion).
- Inteligentne wznawianie (cache per akapit/zdanie).
- Emisyjny mastering audio EBU R128 (-14.0 LUFS, True Peak <= -1.0 dBFS, 48kHz, Broadcast EQ).
- Automatyczne generowanie zsynchronizowanych napisów SRT oraz raportu Markdown.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# ==============================================================================
# 0. SELF-BOOTSTRAPPING: Automatyczne przełączanie na środowisko .venv repozytorium
# ==============================================================================
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

if __name__ == "__main__" and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    if VENV_PYTHON.exists() and os.access(str(VENV_PYTHON), os.X_OK):
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

# Upewnienie się, że moduły z scripts/media są dostępne
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from dub_video import OllamaTranslator, resolve_reference_audio  # noqa: E402
from text_director import (  # noqa: E402
    clean_voiceover_text,
    enrich_voiceover_tags,
    strip_voice_tags,
    supports_voice_tags,
)
from tts_engines import EdgeTTSEngine, KokoCloneEngine  # noqa: E402


def log_info(msg: str):
    print(f"\033[1;34m[INFO]\033[0m {msg}")


def log_ok(msg: str):
    print(f"\033[1;32m[OK]\033[0m {msg}")


def log_warn(msg: str):
    print(f"\033[1;33m[WARN]\033[0m {msg}")


def log_err(msg: str):
    print(f"\033[1;31m[ERROR]\033[0m {msg}", file=sys.stderr)


# ==============================================================================
# 1. PARSER SKRYPTÓW CZYTANYCH MARKDOWN (READ SCRIPT PARSER)
# ==============================================================================
def clean_speech_text(raw_text: str) -> str:
    """Oczyszcza tekst do czystej formy czytanej przez lektora."""
    text = clean_voiceover_text(raw_text)
    # Usunięcie pogrubień, kursywy i kodów w backtickach
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Zastąpienie myślników i wielokropków naturalnymi przerwami
    text = re.sub(r"\s*[–—]\s*", ", ", text)
    text = re.sub(r"\s*-\s*", " ", text)
    text = re.sub(r"\.{3,}", "...", text)
    # Usunięcie zbędnych cudzysłowów
    text = text.strip(' "”„\'`')
    # Normalizacja spacji
    text = re.sub(r"\s+", " ", text).strip()
    return clean_voiceover_text(text)


def parse_markdown_voiceover_script(md_path: Path) -> list[dict]:
    """
    Parsuje skrypt czytany w formacie Markdown:
    - Pomija nagłówki sekcji (#, ##, ###)
    - Pomija bloki cytatów metadanych (> ...)
    - Pomija wtrącenia reżyserskie typu *(Widok ekranu...)* lub *(Odtworzenie audio...)*
    - Wykrywa pauzy typu [pauza 1s], [pauza 2s], [pauza 0.5s]
    - Usuwa znaczniki intonacyjne typu [akcent], [spokojny ton]
    Zwraca uporządkowaną listę segmentów mowy i przerw.
    """
    content = md_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    items = []
    item_id = 1
    current_section = "Wstęp"

    for line in lines:
        stripped = line.strip()

        # Pomijanie pustych linii i separatorów
        if not stripped or stripped.startswith("---") or stripped.startswith("==="):
            continue

        # Sekcje (np. ### [0:00 - 1:15] WIESZAK 1: ...)
        if stripped.startswith("#"):
            # Zachowaj nazwę wieszaka dla metadanych
            section_match = re.search(r"WIESZAK\s+\d+[^:]*:\s*(.*)", stripped, re.IGNORECASE)
            if section_match:
                current_section = section_match.group(0).strip()
            continue

        # Blok metadanych profilu (np. > **Profil twórcy:** ...)
        if stripped.startswith(">"):
            continue

        # Wtrącenia reżyserskie w całej linii (np. *(Widok Antigravity IDE...)*)
        if re.match(r"^\*\([^*]+\)\*$", stripped) or re.match(r"^\([^*]+\)$", stripped):
            continue

        # Usunięcie wtrąceń reżyserskich występujących wewnątrz tekstu
        cleaned_line = re.sub(r"\*\([^*]+\)\*", "", stripped)
        cleaned_line = re.sub(r"\([^*)]*(?:widok|ekran|odtworzenie|kursor|wtrącenie)[^*)]*\)", "", cleaned_line, flags=re.IGNORECASE).strip()

        if not cleaned_line:
            continue

        # Rozbicie linii na fragmenty wokół pauz [pauza Xs]
        # Przykład: "Widzicie to? [pauza 1s] Posłuchajcie." -> Speech, Pause(1.0), Speech
        pause_pattern = re.compile(r"\[pauza\s+([\d\.,]+)\s*s?\]", re.IGNORECASE)
        parts = []
        last_idx = 0

        for match in pause_pattern.finditer(cleaned_line):
            pre_text = cleaned_line[last_idx:match.start()].strip()
            if pre_text:
                parts.append({"type": "speech", "raw": pre_text})

            dur_str = match.group(1).replace(",", ".")
            try:
                pause_dur = float(dur_str)
            except ValueError:
                pause_dur = 1.0
            parts.append({"type": "pause", "duration": pause_dur})
            last_idx = match.end()

        post_text = cleaned_line[last_idx:].strip()
        if post_text:
            parts.append({"type": "speech", "raw": post_text})

        for p in parts:
            if p["type"] == "pause":
                items.append({
                    "id": item_id,
                    "type": "pause",
                    "duration": p["duration"],
                    "section": current_section,
                })
                item_id += 1
            else:
                # Usunięcie znaczników intonacyjnych typu [akcent], [spokojny uśmiech]
                speech_text = re.sub(r"\[(?:akcent|spokojny[^\]]*|uśmiech|pauza|wdech|cisza)[^\]]*\]", "", p["raw"], flags=re.IGNORECASE)
                speech_text = clean_speech_text(speech_text)
                if speech_text:
                    items.append({
                        "id": item_id,
                        "type": "speech",
                        "text": speech_text,
                        "section": current_section,
                    })
                    item_id += 1

    return items


# ==============================================================================
# 2. AUDIO DSP, MASTERING I NAPISY SRT
# ==============================================================================
def sec_to_srt_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    if ms >= 1000:
        s += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def get_audio_duration(file_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def create_silence_wav(out_wav: Path, duration_sec: float, sample_rate: int = 24000):
    """Generuje czysty plik ciszy WAV o zadanej długości w sekundach."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r={sample_rate}:cl=mono",
        "-t", f"{duration_sec:.3f}",
        "-acodec", "pcm_s16le",
        str(out_wav),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def concatenate_and_master(
    segment_files: list[tuple[Path, dict]],
    output_wav: Path,
    output_srt: Path,
    target_lufs: float = -14.0,
    target_tp: float = -1.0,
):
    """
    Łączy wygenerowane fragmenty audio w jeden ciągły plik lektorski,
    tworzy precyzyjnie zsynchronizowane napisy SRT i aplikuje broadcast mastering EBU R128.
    """
    output_wav.parent.mkdir(parents=True, exist_ok=True)

    concat_list_file = output_wav.with_suffix(".concat.txt")
    srt_entries = []
    current_time = 0.0
    srt_idx = 1

    with open(concat_list_file, "w", encoding="utf-8") as f:
        for wav_path, item_info in segment_files:
            f.write(f"file '{wav_path.resolve()}'\n")
            dur = get_audio_duration(wav_path)
            start_t = current_time
            end_t = current_time + dur
            current_time = end_t

            if item_info.get("type") == "speech":
                txt = strip_voice_tags(clean_voiceover_text(item_info.get("text", "")))
                srt_entries.append(
                    f"{srt_idx}\n{sec_to_srt_time(start_t)} --> {sec_to_srt_time(end_t)}\n{txt}\n"
                )
                srt_idx += 1

    # Zapis napisów SRT
    output_srt.write_text("\n".join(srt_entries) + "\n", encoding="utf-8")

    # Tymczasowe złączenie bez kompresji
    temp_concat = output_wav.with_suffix(".temp_concat.wav")
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list_file),
        "-c", "copy",
        str(temp_concat),
    ]
    subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Mastering broadcastowy EBU R128 (-14 LUFS) + Broadcast EQ
    audio_filter = (
        "highpass=f=80,"
        "equalizer=f=200:width_type=q:width=1.0:g=1.5,"
        "equalizer=f=3000:width_type=q:width=1.2:g=1.5,"
        "equalizer=f=4500:width_type=q:width=1.5:g=-2.0,"
        "compand=attacks=0.02:decays=0.2:points=-80/-80|-40/-30|-20/-10|-10/-4|0/0:soft-knee=0.01,"
        f"loudnorm=I={target_lufs}:TP={target_tp}:LRA=9.0"
    )

    log_info(f"Aplikowanie masteringu emisyjnego EBU R128 ({target_lufs} LUFS, 48kHz stereo)...")
    cmd_master = [
        "ffmpeg", "-y",
        "-i", str(temp_concat),
        "-af", audio_filter,
        "-ar", "48000",
        "-ac", "2",
        str(output_wav),
    ]
    subprocess.run(cmd_master, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Porządki po plikach tymczasowych
    if concat_list_file.exists():
        concat_list_file.unlink()
    if temp_concat.exists():
        temp_concat.unlink()


# ==============================================================================
# 3. GŁÓWNY POTOK GENEROWANIA VOICEOVERU (PIPELINE)
# ==============================================================================
def generate_voiceover(
    script_path: Path,
    work_dir: Path,
    ref_audio: Path | None = None,
    polish_voice: str = "pl-PL-MarekNeural",
    use_voice_conversion: bool = True,
    max_items: int | None = None,
    section_filter: str | None = None,
    expressive: bool = False,
) -> bool:
    script_path = script_path.resolve()
    work_dir = work_dir.resolve()
    output_dir = work_dir / "output"
    parts_dir = work_dir / "vo_parts"
    output_dir.mkdir(parents=True, exist_ok=True)
    parts_dir.mkdir(parents=True, exist_ok=True)

    log_info("=" * 65)
    log_info(" Workstation Hub: Generator Voiceoveru PL (Profil Lektora: work/voice_sample)")
    log_info("=" * 65)
    log_info(f"Skrypt Markdown:    {script_path.name}")
    log_info(f"Katalog roboczy:    {work_dir}")
    log_info(f"Konwersja barwy:    {'TAK (Kanade Zero-Shot)' if use_voice_conversion else 'NIE (Czysty Edge-TTS)'}")
    if ref_audio:
        log_info(f"Próbka wzorca głosu: {ref_audio.name}")

    # 1. Parsowanie skryptu czytanego Markdown
    items = parse_markdown_voiceover_script(script_path)
    if not items:
        log_err("Nie znaleziono żadnych segmentów tekstu do odczytania w skrypcie.")
        return False

    if section_filter:
        items = [it for it in items if section_filter.lower() in it.get("section", "").lower()]
        log_info(f"Filtrowanie do sekcji '{section_filter}': {len(items)} segmentów.")

    if max_items:
        items = items[:max_items]
        log_info(f"Ograniczono przetwarzanie do pierwszych {max_items} segmentów.")

    log_ok(f"Wyekstrahowano {len(items)} elementów ze skryptu (mowa i pauzy).")

    # 2. Inicjalizacja silnika TTS oraz konwersji głosu
    edge_engine = EdgeTTSEngine(voice=polish_voice, rate="+0%")
    cloner_engine = None

    if use_voice_conversion:
        if not ref_audio or not ref_audio.exists():
            log_warn("Brak pliku próbki referencyjnej (--ref-audio). Wyłączanie konwersji głosu Kanade.")
            use_voice_conversion = False
        else:
            try:
                cloner_engine = KokoCloneEngine()
                if not cloner_engine.is_available():
                    log_warn("Silnik KokoClone/Kanade nie jest dostępny. Fallback do czystego głosu lektora.")
                    use_voice_conversion = False
            except Exception as e_cl:
                log_warn(f"Błąd inicjalizacji Kanade ({e_cl}). Fallback do czystego głosu lektora.")
                use_voice_conversion = False

    # 2.5 Reżyser tekstu dla trybu ekspresyjnego
    llm_director_client = None
    if expressive and supports_voice_tags("edge"):
        candidate_llm = OllamaTranslator(model_name="SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M")
        if candidate_llm.is_available():
            llm_director_client = candidate_llm
            log_info("Reżyser tekstu: Włączono wzbogacanie Two-Pass TTS Voice Tags (Bielik LLM).")
        else:
            log_warn("Ollama nie jest dostępna dla Reżysera tekstu. Użycie czystego tekstu.")

    # 3. Generowanie poszczególnych części
    segment_files = []
    log_info("Rozpoczynanie syntezy i transferu barwy dla segmentów...")

    for it in items:
        item_id = it["id"]
        item_type = it["type"]

        if item_type == "pause":
            pause_wav = parts_dir / f"part_{item_id:04d}_pause_{it['duration']}s.wav"
            if not pause_wav.exists() or pause_wav.stat().st_size < 100:
                create_silence_wav(pause_wav, it["duration"])
            segment_files.append((pause_wav, it))
            continue

        # Typ speech
        clean_text = clean_voiceover_text(it["text"])
        if expressive and supports_voice_tags("edge") and llm_director_client:
            directed_text = enrich_voiceover_tags(clean_text, "edge", client_llm=llm_director_client)
        else:
            directed_text = strip_voice_tags(clean_text)

        it["text"] = strip_voice_tags(directed_text)  # Do napisów SRT i raportu MD
        it["text_directed"] = directed_text          # Do syntezy TTS
        base_wav = parts_dir / f"part_{item_id:04d}_base.wav"
        cloned_wav = parts_dir / f"part_{item_id:04d}_cloned.wav"
        txt_marker = parts_dir / f"part_{item_id:04d}.txt"

        final_part_wav = cloned_wav if use_voice_conversion else base_wav

        # Inteligentne wznawianie (cache)
        if (
            final_part_wav.exists()
            and final_part_wav.stat().st_size > 1000
            and txt_marker.exists()
            and txt_marker.read_text(encoding="utf-8").strip() == directed_text.strip()
        ):
            segment_files.append((final_part_wav, it))
            continue

        log_info(f"Segment #{item_id:03d} [{it['section'][:25]}]: '{directed_text[:45]}...'")

        # Krok A: Czysta polska synteza
        synth_ok = edge_engine.synthesize(text=directed_text, out_wav=base_wav)
        if not synth_ok:
            log_err(f"Błąd syntezy segmentu #{item_id}. Przerywanie.")
            return False

        # Krok B: Przeniesienie barwy Jarka przez Kanade (jeśli włączone)
        if use_voice_conversion and cloner_engine and ref_audio:
            conv_ok = cloner_engine.convert_audio(
                source_audio=base_wav,
                ref_audio=ref_audio,
                output_wav=cloned_wav,
            )
            if not conv_ok:
                log_warn(f"Nie powiodła się konwersja segmentu #{item_id}, użycie czystego audio bazowego.")
                final_part_wav = base_wav
            else:
                final_part_wav = cloned_wav
        else:
            final_part_wav = base_wav

        txt_marker.write_text(directed_text + "\n", encoding="utf-8")
        segment_files.append((final_part_wav, it))

    if llm_director_client is not None:
        llm_director_client.unload()

    project_slug = work_dir.name if work_dir.name and work_dir.name != "work" else script_path.stem.replace("_read_script", "").replace("voiceover_", "")
    if not project_slug or project_slug == "voiceover":
        project_slug = "VoiceOver"
    mastered_wav = output_dir / f"{project_slug}_VoiceOver_PL_CLEAN.wav"
    subtitles_srt = output_dir / f"{project_slug}_VoiceOver_PL.srt"

    log_info(f"Łączenie {len(segment_files)} segmentów i generowanie finalnego mastera...")
    concatenate_and_master(
        segment_files=segment_files,
        output_wav=mastered_wav,
        output_srt=subtitles_srt,
        target_lufs=-14.0,
        target_tp=-1.0,
    )

    total_dur = get_audio_duration(mastered_wav)

    # 5. Raport podsumowujący
    report_md = output_dir / f"{project_slug}_VoiceOver_Summary.md"
    with open(report_md, "w", encoding="utf-8") as f:
        f.write(f"# Raport Generowania Voiceoveru PL: {project_slug}\n\n")
        f.write(f"- **Skrypt źródłowy:** `{script_path.name}`\n")
        f.write(f"- **Długość całkowita:** `{total_dur:.2f}s` ({total_dur / 60.0:.2f} min)\n")
        f.write(f"- **Styl / Głos bazowy:** `{polish_voice}`\n")
        f.write(f"- **Konwersja barwy (Kanade):** `{'TAK (' + ref_audio.name + ')' if use_voice_conversion else 'NIE'}`\n")
        f.write("- **Standard emisyjny:** `EBU R128 (-14.0 LUFS, True Peak <= -1.0 dBFS, 48kHz stereo)`\n\n")
        f.write("## Wygenerowane Pliki Produkcyjne (Deliverables)\n\n")
        f.write(f"1. **Czysty lektor (Gotowy master do Kdenlive):** `{mastered_wav.name}`\n")
        f.write(f"2. **Zsynchronizowane napisy lektorskie:** `{subtitles_srt.name}`\n\n")
        f.write("## Tabela Wygenerowanych Segmentów\n\n")
        f.write("| # | Typ | Sekcja / Wieszak | Treść / Czas |\n")
        f.write("| :---: | :---: | :--- | :--- |\n")
        for f_path, it in segment_files:
            if it["type"] == "pause":
                f.write(f"| {it['id']} | `PAUZA` | {it.get('section', '-')} | *Pauza {it['duration']}s* |\n")
            else:
                f.write(f"| {it['id']} | `MOWA` | {it.get('section', '-')} | {it['text']} |\n")

    log_ok("=" * 65)
    log_ok(f"SUKCES! Wygenerowano pełną ścieżkę lektorską dla {project_slug} ({total_dur:.2f}s).")
    log_info("Dostarczone pliki:")
    log_info(f"  1. [Master WAV]:      {mastered_wav}")
    log_info(f"  2. [Napisy SRT]:      {subtitles_srt}")
    log_info(f"  3. [Raport MD]:       {report_md}")
    log_info("=" * 65)
    return True


# ==============================================================================
# 4. PUNKT WEJŚCIA CLI
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Autonomiczny potok generowania polskiego voiceoveru z Markdown.")
    parser.add_argument("-s", "--script", type=Path, required=True, help="Ścieżka do pliku Markdown ze skryptem czytanym (.md)")
    parser.add_argument("-w", "--work-dir", type=Path, default=None, help="Katalog roboczy projektu (domyślnie work/<nazwa_skryptu>)")
    parser.add_argument("--voice-ref", "--ref-audio", dest="voice_ref", type=Path, default=None, help="Ścieżka do próbki referencyjnej WAV (domyślnie z work/voice_sample/)")
    parser.add_argument("--voice", type=str, default="pl-PL-MarekNeural", help="Głos bazowy lektora (domyślnie pl-PL-MarekNeural)")
    parser.add_argument("--no-cloning", action="store_true", default=False, help="Wyłącz konwersję barwy Kanade (generuj czystego Marka)")
    parser.add_argument("--section", type=str, default=None, help="Ogranicz generowanie do wybranej sekcji/wieszaka (np. 'WIESZAK 1')")
    parser.add_argument("--limit", type=int, default=None, help="Ogranicz do pierwszych N segmentów (do szybkiego testu)")
    parser.add_argument("--expressive", action="store_true", default=False, help="Włącz dwufazowe wzbogacanie tekstu o znaczniki emocji/dynamiki (Two-Pass TTS Voice Tags)")
    args = parser.parse_args()

    script_path = args.script.resolve()
    if not script_path.exists():
        log_err(f"Nie znaleziono pliku skryptu: {script_path}")
        sys.exit(1)

    work_dir = args.work_dir
    if not work_dir:
        work_dir = REPO_ROOT / "work" / script_path.stem.replace("_read_script", "")

    ref_audio = None
    if not args.no_cloning:
        try:
            ref_audio, _ = resolve_reference_audio(args.voice_ref, work_dir=work_dir)
            if not ref_audio.exists():
                raise FileNotFoundError(f"Plik {ref_audio} nie istnieje.")
        except (FileNotFoundError, ValueError):
            print(
                "Błąd: Nie znaleziono próbki referencyjnej głosu. Nagraj 10s audio i umieść w voice/ lub ustaw VOICE_REF_FILE w .env.",
                file=sys.stderr,
            )
            sys.exit(1)

    success = generate_voiceover(
        script_path=script_path,
        work_dir=work_dir,
        ref_audio=ref_audio,
        polish_voice=args.voice,
        use_voice_conversion=not args.no_cloning,
        max_items=args.limit,
        section_filter=args.section,
        expressive=args.expressive,
    )
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
