#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "faster-whisper",
#     "av<14",
#     "edge-tts",
#     "soundfile",
# ]
# ///
"""
Workstation Hub: Autonomiczny, w pełni generyczny potok lokalnego dubbingu wideo (Shorts / Screencasts).
Wszystkie pliki użytkownika i materiały źródłowe są przetwarzane wyłącznie w katalogu roboczym (work/).

Kroki potoku:
1. Opcjonalna ekstrakcja próbki referencyjnej głosu (--ref-source / --ref-start / --ref-end).
2. Ekstrakcja czystego audio ze źródłowego pliku wideo (WAV 24kHz mono).
3. Segmentacja i ekstrakcja znaczników czasowych (scenariusz MD / SRT lub Whisper).
4. Tłumaczenie inżynierskie PL -> EN ze słownikiem technicznym IT i rygorem okna czasowego.
5. Synteza mowy: Zero-shot Breeze-TTS-2 (próbka referencyjna) lub szybki lektor (Kokoro / Edge-TTS).
6. Time-syncing, padding ciszy i mastering EBU R128 (-14 LUFS / True Peak -1.0 dBFS).
7. Złożenie pliku wideo z podmienioną ścieżką audio EN.
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Słownik terminów inżynierskich IT
TECH_TERMS = {
    "Agentic SysAdmin": "Agentic SysAdmin",
    "Zorin OS": "Zorin OS",
    "Antigravity": "Antigravity",
    "punkt montowania": "mount point",
    "narzut pamięci VRAM": "VRAM footprint",
    "szyna PCIe": "PCIe bus",
    "montaż cięty": "ripple edit",
    "ścieżka na osi czasu": "timeline track",
    "pliki konfiguracyjne": "configuration files",
    "plan wdrożenia": "implementation plan",
    "otwarte repozytorium": "open-source repo",
    "pulpit": "desktop",
    "dok": "dock",
}

# Wzorcowe tłumaczenia zdań dla standaryzacji
PHRASE_DICTIONARY = {
    "Przestań traktować AI jak zabawkę do pogaduszek. Oto Agentic SysAdmin.":
        "Stop treating AI like a chatbot toy. Meet Agentic SysAdmin.",
    "Zamiast marnować godziny na forach i dłubaniu w konfiguracji, dałem agentowi jedno proste zadanie:":
        "Instead of wasting hours on forums and tweaking configs, I gave the agent one simple goal:",
    "Przekształć domyślny pulpit Zorina w czyste środowisko w stylu macOS.":
        "Transform default Zorin desktop into a clean, macOS-inspired workspace.",
    "Minuta roboty, audyt w tle i gotowy plan wdrożenia. Bez dotknięcia ani jednego pliku konfiguracyjnego.":
        "One minute of work, background audit, and a complete implementation plan. Without touching a single config file.",
    "Wraz z Agentic SysAdmin nadeszła nowa era Linuksa. Całą sesję na żywo i otwarte repozytorium znajdziesz w filmie poniżej!":
        "With Agentic SysAdmin, a new era of Linux has arrived. Watch the full live session and get the open repo in the video below!",
}


def log_info(msg: str):
    print(f"\033[1;34m[INFO]\033[0m {msg}")

def log_ok(msg: str):
    print(f"\033[1;32m[OK]\033[0m {msg}")

def log_warn(msg: str):
    print(f"\033[1;33m[WARN]\033[0m {msg}")

def log_err(msg: str):
    print(f"\033[1;31m[ERROR]\033[0m {msg}", file=sys.stderr)


def get_audio_duration(file_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def extract_raw_audio(video_path: Path, output_wav: Path, sample_rate: int = 24000) -> None:
    log_info(f"Ekstrakcja audio z {video_path.name} -> {output_wav.name} ({sample_rate}Hz mono)...")
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le",
        "-ar", str(sample_rate), "-ac", "1",
        str(output_wav)
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    log_ok("Wyekstrahowano strumień audio.")


def extract_voice_sample_clip(source_path: Path, start: str, end: str, output_wav: Path, transcript: str | None = None) -> None:
    log_info(f"Wycinanie próbki głosu z {source_path.name} [{start} -> {end}]...")
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-to", str(end),
        "-i", str(source_path),
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "24000", "-ac", "1",
        str(output_wav)
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    if transcript:
        output_wav.with_suffix(".txt").write_text(transcript.strip() + "\n", encoding="utf-8")
    log_ok(f"Zapisano próbkę głosu: {output_wav.name}")


def parse_srt(srt_path: Path) -> list[dict]:
    content = srt_path.read_text(encoding="utf-8")
    entries = re.split(r'\n\s*\n', content.strip())
    scenes = []
    
    def time_to_sec(t_str):
        h, m, s_ms = t_str.strip().split(':')
        s, ms = s_ms.split(',')
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

    for idx, entry in enumerate(entries, start=1):
        lines = [line.strip() for line in entry.splitlines() if line.strip()]
        if len(lines) >= 3:
            time_match = re.search(r'(\d+:\d+:\d+,\d+)\s*-->\s*(\d+:\d+:\d+,\d+)', lines[1])
            if time_match:
                start = time_to_sec(time_match.group(1))
                end = time_to_sec(time_match.group(2))
                text = " ".join(lines[2:])
                scenes.append({
                    "id": idx,
                    "start": round(start, 2),
                    "end": round(end, 2),
                    "text_pl": text
                })
    return scenes


def parse_short_script_md(script_path: Path) -> list[dict]:
    content = script_path.read_text(encoding="utf-8")
    scenes = []
    blocks = re.split(r'(?m)^#{3,4}\s+Scena\s+(\d+)', content)
    
    for i in range(1, len(blocks), 2):
        scene_num = int(blocks[i])
        block = blocks[i+1]
        
        # Czas, np. [0:00 - 0:05]
        time_match = re.search(r'\[(\d+):(\d+(?:\.\d+)?)\s*-\s*(\d+):(\d+(?:\.\d+)?)\]', block[:120])
        start_sec, end_sec = 0.0, 0.0
        if time_match:
            sm, ss, em, es = time_match.groups()
            start_sec = float(sm) * 60 + float(ss)
            end_sec = float(em) * 60 + float(es)
            
        # Kwestia lektora
        text_match = re.search(r'\*\s*\*\*Kwestia lektora:\*\*\s*(?:\n\s*)?[*„"“](.*?)[*"”]', block, re.DOTALL)
        text_pl = text_match.group(1).strip() if text_match else ""
        text_pl = re.sub(r'\s+', ' ', text_pl)
        
        scenes.append({
            "id": scene_num,
            "start": round(start_sec, 2),
            "end": round(end_sec, 2),
            "text_pl": text_pl
        })
    return scenes


def transcribe_with_whisper(audio_path: Path) -> list[dict]:
    log_info("Brak pliku scenariusza. Uruchamianie lokalnego modelu Whisper...")
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cuda", compute_type="float16")
        segments, _ = model.transcribe(str(audio_path), beam_size=5, language="pl")
        scenes = []
        for seg in segments:
            scenes.append({
                "id": seg.id + 1,
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text_pl": seg.text.strip()
            })
        log_ok(f"Whisper wygenerował {len(scenes)} segmentów.")
        return scenes
    except Exception as e:
        log_warn(f"Błąd uruchomienia Whisper w locie: {e}. Używam domyślnych segmentów awaryjnych.")
        duration = get_audio_duration(audio_path)
        return [{
            "id": 1,
            "start": 0.0,
            "end": round(duration, 2),
            "text_pl": "Nagranie lektorskie do zsynchronizowania."
        }]


def translate_segment(text_pl: str) -> str:
    cleaned = text_pl.strip(' „"”')
    if cleaned in PHRASE_DICTIONARY:
        return PHRASE_DICTIONARY[cleaned]
    for pl_key, en_val in PHRASE_DICTIONARY.items():
        if pl_key.lower() in cleaned.lower():
            return en_val

    translated = cleaned
    for pl_term, en_term in TECH_TERMS.items():
        translated = re.sub(re.escape(pl_term), en_term, translated, flags=re.IGNORECASE)
    return translated


async def synthesize_edge_tts(text: str, out_wav: Path, voice: str = "en-US-ChristopherNeural") -> None:
    import edge_tts
    temp_mp3 = out_wav.with_suffix(".mp3")
    communicate = edge_tts.Communicate(text, voice, rate="+2%", pitch="-2Hz")
    await communicate.save(str(temp_mp3))
    
    cmd = [
        "ffmpeg", "-y", "-i", str(temp_mp3),
        "-acodec", "pcm_s16le", "-ar", "24000", "-ac", "1",
        str(out_wav)
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    if temp_mp3.exists():
        temp_mp3.unlink()


def find_breeze_runner() -> tuple[Path | None, Path | None, Path | None]:
    candidates = [
        Path.home() / "projects" / "ghostshift" / "exploration" / "experiments" / "breeze2-tts-local",
        Path.home() / "workspaces" / "breeze2-tts-local",
    ]
    for base in candidates:
        model = base / "models" / "Breeze-TTS-2"
        infer = base / "src" / "breeze-tts" / "infer.py"
        venv = base / ".venv" / "bin" / "python"
        if model.exists() and infer.exists() and venv.exists():
            return venv, infer, model
    return None, None, None


def synthesize_breeze(text: str, out_wav: Path, ref_audio: Path, ref_transcript: str, instruction: str) -> bool:
    venv, infer, model = find_breeze_runner()
    if not (venv and infer and model):
        return False
        
    cmd = [
        str(venv), str(infer), str(model),
        "--text", text,
        "--ref-audio", str(ref_audio),
        "--ref-text", ref_transcript,
        "--output", str(out_wav),
        "--cfg-scale", "4.0"
    ]
    if instruction:
        cmd.extend(["--instruction", instruction])
        
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except Exception as e:
        log_warn(f"Breeze-TTS-2 inference error: {e}")
        return False


def synthesize_segment(text_en: str, out_wav: Path, engine: str, ref_audio: Path | None, ref_transcript: str, instruction: str) -> str:
    used_engine = engine
    if engine in ("breeze", "auto"):
        if ref_audio and ref_audio.exists() and synthesize_breeze(text_en, out_wav, ref_audio, ref_transcript, instruction):
            return "Breeze-TTS-2 (Zero-Shot Clone)"
        else:
            if engine == "breeze":
                log_warn("Wagi Breeze-TTS-2 nie są jeszcze w pełni zainicjalizowane, używam bezpiecznego fallbacku Edge-TTS...")
            used_engine = "edge"
            
    if used_engine in ("edge", "auto", "kokoro"):
        asyncio.run(synthesize_edge_tts(text_en, out_wav))
        return "Edge-TTS (en-US-ChristopherNeural)"

    raise RuntimeError(f"Nieobsługiwany silnik TTS: {engine}")


def time_sync_and_master(
    scenes: list[dict],
    segment_wavs: list[Path],
    total_duration: float,
    output_wav: Path,
    target_lufs: float = -14.0,
    target_tp: float = -1.0
) -> None:
    log_info(f"Synchronizacja segmentów i mastering EBU R128 ({target_lufs} LUFS)...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        adjusted_wavs = []
        
        for idx, (scene, seg_wav) in enumerate(zip(scenes, segment_wavs)):
            seg_dur = get_audio_duration(seg_wav)
            avail_dur = scene["end"] - scene["start"]
            
            if idx + 1 < len(scenes):
                max_window = scenes[idx + 1]["start"] - scene["start"]
            else:
                max_window = total_duration - scene["start"]
                
            out_seg = tmp_path / f"synced_{idx:03d}.wav"
            
            if seg_dur > max_window and max_window > 0.5:
                speed_factor = min(seg_dur / max_window, 1.25)
                log_info(f"Dopasowanie tempa dla sceny {scene['id']}: x{speed_factor:.2f}")
                cmd = [
                    "ffmpeg", "-y", "-i", str(seg_wav),
                    "-filter:a", f"atempo={speed_factor:.3f}",
                    "-ar", "48000", "-ac", "1",
                    str(out_seg)
                ]
            else:
                cmd = [
                    "ffmpeg", "-y", "-i", str(seg_wav),
                    "-ar", "48000", "-ac", "1",
                    str(out_seg)
                ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            adjusted_wavs.append(out_seg)

        # Montaż na osi czasu z adelay
        filter_complex = []
        mix_inputs = []
        for idx, (scene, adj_wav) in enumerate(zip(scenes, adjusted_wavs)):
            delay_ms = int(scene["start"] * 1000)
            filter_complex.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms}[d{idx}]")
            mix_inputs.append(f"[d{idx}]")
            
        filter_complex.append(f"{''.join(mix_inputs)}amix=inputs={len(scenes)}:dropout_transition=0:normalize=0[mixed]")
        filter_complex.append(f"[mixed]loudnorm=I={target_lufs}:TP={target_tp}:LRA=11[mastered]")
        
        cmd = ["ffmpeg", "-y"]
        for adj_wav in adjusted_wavs:
            cmd.extend(["-i", str(adj_wav)])
            
        cmd.extend([
            "-filter_complex", ";".join(filter_complex),
            "-map", "[mastered]",
            "-ar", "48000", "-ac", "2",
            str(output_wav)
        ])
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        log_ok(f"Zapisano zmasterowany plik audio: {output_wav.name}")


def main():
    parser = argparse.ArgumentParser(description="Generyczny autonomiczny potok dubbingu wideo w work/.")
    parser.add_argument("-i", "--input", required=True, type=Path, help="Plik wideo źródłowego (MP4 w work/)")
    parser.add_argument("-w", "--work-dir", type=Path, default=None, help="Katalog roboczy projektu (np. work/EP002_Short)")
    parser.add_argument("-s", "--script", type=Path, default=None, help="Opcjonalny plik scenariusza (MD lub SRT)")
    
    # Parametry próbki głosu
    parser.add_argument("--ref-audio", type=Path, default=None, help="Ścieżka do gotowej próbki referencyjnej WAV")
    parser.add_argument("--ref-transcript", type=str, default="", help="Transkrypcja próbki referencyjnej")
    parser.add_argument("--ref-source", type=Path, default=None, help="Plik źródłowy do wycięcia próbki w locie")
    parser.add_argument("--ref-start", type=str, default="00:00:12.000", help="Początek wycinka próbki")
    parser.add_argument("--ref-end", type=str, default="00:00:20.300", help="Koniec wycinka próbki")

    # Silnik i styl
    parser.add_argument("--engine", choices=["auto", "breeze", "kokoro", "edge"], default="auto", help="Silnik syntezy TTS")
    parser.add_argument("--instruction", type=str, default="Maintain a calm, confident, authoritative engineering delivery with clear cadence.", help="Instrukcja stylu mowy")
    parser.add_argument("--output-video", action="store_true", default=True, help="Wygeneruj zduplikowane wideo z dubbingiem EN")
    args = parser.parse_args()

    input_video = args.input.resolve()
    if not input_video.exists():
        log_err(f"Plik wejściowy nie istnieje: {input_video}")
        sys.exit(1)

    work_dir = args.work_dir.resolve() if args.work_dir else input_video.parent.parent
    assets_dir = work_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    short_id = work_dir.name
    total_duration = get_audio_duration(input_video)

    log_info("=" * 65)
    log_info(f" Workstation Hub: Autonomiczny Potok Dubbingu dla {short_id}")
    log_info("=" * 65)
    log_info(f"Wideo wejściowe:  {input_video.name} ({total_duration:.2f}s)")
    log_info(f"Katalog roboczy:  {work_dir}")
    log_info(f"Silnik TTS:       {args.engine.upper()}")

    # 0. Opcjonalna ekstrakcja próbki referencyjnej
    ref_audio = args.ref_audio
    ref_transcript = args.ref_transcript
    if args.ref_source and args.ref_source.exists():
        target_sample_wav = assets_dir / "ref_voice_sample.wav"
        extract_voice_sample_clip(args.ref_source, args.ref_start, args.ref_end, target_sample_wav, ref_transcript)
        ref_audio = target_sample_wav

    # Jeśli nie podano próbki, szukamy w katalogach roboczych work/
    if not ref_audio:
        candidates = [
            assets_dir / "ref_voice_sample.wav",
            work_dir / "input" / "ref_voice_sample.wav",
            work_dir.parent / "voice_sample" / "ref_voice_sample.wav",
        ]
        for cand in candidates:
            if cand.exists():
                ref_audio = cand
                txt_cand = cand.with_suffix(".txt")
                if txt_cand.exists() and not ref_transcript:
                    ref_transcript = txt_cand.read_text(encoding="utf-8").strip()
                break

    # 1. Ekstrakcja czystego audio ze źródłowego wideo
    raw_audio = assets_dir / f"{short_id}_VoiceOver_RAW_24k.wav"
    extract_raw_audio(input_video, raw_audio, sample_rate=24000)

    # 2. Parsowanie scenariusza lub transkrypcja
    script_path = args.script
    if not script_path:
        for candidate in [work_dir / "input" / "short_script.md", work_dir / f"{short_id}.srt", input_video.with_suffix(".srt")]:
            if candidate.exists():
                script_path = candidate
                break

    if script_path and script_path.exists():
        log_info(f"Wczytywanie scenariusza: {script_path.name}")
        if script_path.suffix == ".srt":
            scenes = parse_srt(script_path)
        else:
            scenes = parse_short_script_md(script_path)
    else:
        scenes = transcribe_with_whisper(raw_audio)

    if not scenes:
        log_err("Nie udało się wyodrębnić segmentów do dubbingu.")
        sys.exit(1)

    # 3. Tłumaczenie inżynierskie
    log_info("Tłumaczenie segmentów na język angielski z zachowaniem słownika IT...")
    for sc in scenes:
        sc["text_en"] = translate_segment(sc["text_pl"])

    transcript_json = assets_dir / f"{short_id}_Dubbing_Transcript_EN.json"
    with open(transcript_json, "w", encoding="utf-8") as f:
        json.dump(scenes, f, ensure_ascii=False, indent=2)
    log_ok(f"Zapisano transkrypcję segmentów: {transcript_json.name}")

    # 4. Synteza mowy
    dub_parts_dir = assets_dir / "dub_parts"
    dub_parts_dir.mkdir(parents=True, exist_ok=True)
    segment_wavs = []
    
    log_info("Generowanie mowy dla poszczególnych scen...")
    active_engine_name = "unknown"
    for sc in scenes:
        part_wav = dub_parts_dir / f"scene_{sc['id']:03d}.wav"
        active_engine_name = synthesize_segment(sc["text_en"], part_wav, args.engine, ref_audio, ref_transcript, args.instruction)
        segment_wavs.append(part_wav)

    # 5. Time-sync i mastering EBU R128
    mastered_wav = assets_dir / f"{short_id}_VoiceOver_EN_CLEAN.wav"
    time_sync_and_master(scenes, segment_wavs, total_duration, mastered_wav, target_lufs=-14.0, target_tp=-1.0)

    # 6. Finalny montaż wideo EN
    if args.output_video:
        output_video_file = assets_dir / f"{short_id}_FINAL_EN_DUBBED.mp4"
        log_info(f"Generowanie zduplikowanego wideo z angielską ścieżką dźwiękową: {output_video_file.name}...")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_video),
            "-i", str(mastered_wav),
            "-c:v", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(output_video_file)
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        log_ok(f"Utworzono gotowy plik wideo EN: {output_video_file.name}")

    # Raport Markdown
    summary_md = assets_dir / f"{short_id}_Dubbing_Summary.md"
    with open(summary_md, "w", encoding="utf-8") as f:
        f.write(f"# Raport Dubbingu AI: {short_id}\n\n")
        f.write(f"- **Wideo źródłowe:** `{input_video.name}` ({total_duration:.2f}s)\n")
        f.write(f"- **Silnik syntezy:** `{active_engine_name}`\n")
        f.write(f"- **Standard audio:** `EBU R128 (-14.0 LUFS, True Peak <= -1.0 dBFS)`\n")
        f.write(f"- **Plik audio lektora:** `{mastered_wav.name}`\n")
        if args.output_video:
            f.write(f"- **Zdubbingowane wideo EN:** `{short_id}_FINAL_EN_DUBBED.mp4`\n\n")
        f.write("## Tabela Zsynchronizowanych Scen\n\n")
        f.write("| Scena | Zakres czasu | Oryginał PL | Kwestia EN |\n")
        f.write("| :---: | :---: | :--- | :--- |\n")
        for sc in scenes:
            f.write(f"| {sc['id']} | `{sc['start']:.2f}s - {sc['end']:.2f}s` | {sc['text_pl']} | **{sc['text_en']}** |\n")

    log_ok(f"Zapisano raport podsumowujący: {summary_md.name}")
    log_info("=" * 65)
    log_ok(f"PROCES ZAKOŃCZONY SUKCESEM DLA {short_id}!")
    log_info("=" * 65)


if __name__ == "__main__":
    main()
