#!/usr/bin/env python3
"""
Workstation Hub: Autonomiczny, w pełni lokalny potok dubbingu AI (Shorts / Screencasts).
Wszystkie komponenty działają w 100% lokalnie i offline w dedykowanym środowisku repozytorium (.venv):
- Ekstrakcja czystego strumienia mowy (ffmpeg)
- Lokalna transkrypcja znaczników czasu (faster-whisper GPU/CPU)
- Neuronowe tłumaczenie maszynowe (MarianMT Helsinki-NLP/opus-mt-pl-en na CPU)
- Inżynierski słownik pojęć IT (config/tech_terms.json)
- Zero-shot synteza i klonowanie głosu referencyjnego (Breeze-TTS-2 w GPU VRAM)
- Time-syncing, padding ciszy i mastering EBU R128 (-14.0 LUFS, True Peak <= -1.0 dBFS)
- Generowanie podwójnego pakietu produkcyjnego: WAV (YouTube Studio) oraz MP4 (Full Video EN)
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# ==============================================================================
# 0. SELF-BOOTSTRAPPING: Automatyczne przełączanie na środowisko .venv repozytorium
# ==============================================================================
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists() and os.access(str(VENV_PYTHON), os.X_OK):
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)
elif sys.executable != str(VENV_PYTHON) and not VENV_PYTHON.exists():
    if shutil.which("uv"):
        print("[INFO] Wykryto brak środowiska .venv w repozytorium. Automatyczna inicjalizacja przez 'uv sync'...")
        subprocess.run(["uv", "sync"], cwd=str(REPO_ROOT), check=True)
        if VENV_PYTHON.exists():
            os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

# ==============================================================================
# 1. BEZPOŚREDNIE IMPORTY BIBLIOTEK W PROCESIE (DIRECT IN-PROCESS IMPORTS)
# ==============================================================================
import argparse
import json
import re
import tempfile
import time
import urllib.request

# Preload bibliotek CUDA (libcublasLt first, then libcublas) dla akceleracji CTranslate2 / faster-whisper jeśli dostępne
try:
    import ctypes
    for cublaslt_candidate in [
        "/usr/local/lib/ollama/cuda_v12/libcublasLt.so.12",
        "/usr/local/cuda/lib64/libcublasLt.so.12",
    ]:
        if Path(cublaslt_candidate).exists():
            ctypes.CDLL(cublaslt_candidate)
            break
    for cublas_candidate in [
        "/usr/local/lib/ollama/cuda_v12/libcublas.so.12",
        "/usr/local/cuda/lib64/libcublas.so.12",
    ]:
        if Path(cublas_candidate).exists():
            ctypes.CDLL(cublas_candidate)
            break
except Exception:
    pass

import soundfile as sf
import torch
from faster_whisper import WhisperModel
from transformers import MarianMTModel, MarianTokenizer

# Rejestracja ścieżki skryptów w sys.path dla pakietów wewnętrznych
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from tts_engines import (
    BaseTTSEngine,
    get_tts_engine,
    detect_best_engine,
    list_available_engines,
    AVAILABLE_ENGINES,
)


def log_info(msg: str):
    print(f"\033[1;34m[INFO]\033[0m {msg}")

def log_ok(msg: str):
    print(f"\033[1;32m[OK]\033[0m {msg}")

def log_warn(msg: str):
    print(f"\033[1;33m[WARN]\033[0m {msg}")

def log_err(msg: str):
    print(f"\033[1;31m[ERROR]\033[0m {msg}", file=sys.stderr)


# ==============================================================================
# 2. SŁOWNIK INŻYNIERSKI IT (DYNAMICZNY Z CONFIG/TECH_TERMS.JSON)
# ==============================================================================
def load_tech_terms() -> dict[str, str]:
    config_path = REPO_ROOT / "config" / "tech_terms.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as e:
            log_warn(f"Nie udało się odczytać {config_path}: {e}")
    # Domyślny zestaw uniwersalnych terminów inżynierskich IT
    return {
        "Agentic SysAdmin": "Agentic SysAdmin",
        "agentowego syzadmina": "Agentic SysAdmin",
        "agentowym syzadminie": "Agentic SysAdmin",
        "agent sizadmin": "Agentic SysAdmin",
        "agentowego sizadmina": "Agentic SysAdmin",
        "antygrawitii": "Antigravity",
        "antygrawiti": "Antigravity",
        "klot-code": "Claude Code",
        "kodek": "Codex",
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


def load_asr_corrections() -> dict[str, str]:
    config_path = REPO_ROOT / "config" / "asr_corrections.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as e:
            log_warn(f"Nie udało się odczytać {config_path}: {e}")
    return {}


def apply_asr_corrections(text: str) -> str:
    rules = load_asr_corrections()
    for pat, repl in rules.items():
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    return text


# Profile akcentu lektora (instrukcje stylu dla Breeze-TTS oraz dedykowane głosy Edge-TTS)
ACCENT_PRESETS = {
    "default": {
        "instruction": "Maintain a calm, confident, authoritative engineering delivery with clear cadence.",
        "edge_voice": "en-US-ChristopherNeural",
    },
    "us": {
        "instruction": "Speak in a fluent, natural American English accent with clear articulation and confident engineering delivery.",
        "edge_voice": "en-US-AndrewMultilingualNeural",
    },
    "uk": {
        "instruction": "Speak in a calm, articulate British English accent with measured pace and authoritative tone.",
        "edge_voice": "en-GB-RyanNeural",
    },
    "neutral": {
        "instruction": "Speak in a polished, neutral international English accent with smooth cadence, clear vowels and articulate pronunciation.",
        "edge_voice": "en-US-AndrewMultilingualNeural",
    },
}


def group_whisper_segments(raw_segments, min_duration=12.0, max_duration=28.0) -> list[dict]:
    """
    Łączy drobne segmenty ASR w spójne grupy zdań/paragrafów (15-25s),
    eliminując ucinanie zdań w połowie i redukując liczbę zapytań do TTS.
    """
    merged = []
    curr = {"start": None, "end": None, "text": ""}

    for s in raw_segments:
        s_start = getattr(s, "start", None) if hasattr(s, "start") else s.get("start")
        s_end = getattr(s, "end", None) if hasattr(s, "end") else s.get("end")
        s_text = getattr(s, "text", "") if hasattr(s, "text") else s.get("text", "")
        s_text = s_text.strip()
        if not s_text:
            continue

        if curr["start"] is None:
            curr["start"] = round(s_start, 2)
            curr["end"] = round(s_end, 2)
            curr["text"] = s_text
            continue

        dur = s_end - curr["start"]
        curr_dur = curr["end"] - curr["start"]
        gap = s_start - curr["end"]
        ends_sentence = curr["text"].rstrip().endswith((".", "?", "!", ":"))

        if (curr_dur >= min_duration and ends_sentence) or (gap >= 1.2 and curr_dur >= 10.0) or (dur > max_duration):
            merged.append(curr)
            curr = {"start": round(s_start, 2), "end": round(s_end, 2), "text": s_text}
        else:
            curr["end"] = round(s_end, 2)
            curr["text"] += " " + s_text

    if curr["start"] is not None:
        merged.append(curr)

    scenes = []
    for idx, m in enumerate(merged, 1):
        cleaned_pl = apply_asr_corrections(m["text"].strip())
        scenes.append({
            "id": idx,
            "start": m["start"],
            "end": m["end"],
            "text_pl": cleaned_pl
        })
    return scenes


# ==============================================================================
# 3. LOKALNE TŁUMACZENIE I KOREKTA LLM (BIELIK / OLLAMA LUB MARIANMT)
# ==============================================================================
def clean_llm_translation(raw_text: str) -> str:
    """Oczyszcza odpowiedź LLM z ewentualnych metadanych, nagłówków, cudzysłowów i notatek."""
    text = raw_text.strip()
    # Usunięcie bloków kodu markdown
    text = re.sub(r"^```(?:[a-zA-Z]+)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Usunięcie typowych prefiksów generowanych przez LLM
    prefixes = [
        r"^(?:Here(?:'s| is) the (?:natural |fluent |idiomatic |spoken |English )?(?:translation|voiceover)[^:]*:\s*)",
        r"^(?:English translation:\s*)",
        r"^(?:Translation:\s*)",
        r"^(?:Sure, here is[^:]*:\s*)",
        r"^(?:Voiceover:\s*)",
    ]
    for p in prefixes:
        text = re.sub(p, "", text, flags=re.IGNORECASE)
    # Usunięcie wtrąceń w nawiasach kwadratowych/okrągłych typu [pause], (laughs), [Note: ...]
    text = re.sub(r"\[(?:note|voiceover|audio|pause|sound|laughter|sigh)[^\]]*\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\((?:note|voiceover|audio|pause|laughter|sigh)[^\)]*\)", "", text, flags=re.IGNORECASE)
    # Usunięcie zewnętrznych cudzysłowów
    text = text.strip(' "”„\'`')
    # Normalizacja białych znaków
    text = re.sub(r"\s+", " ", text).strip()
    return text


class OllamaTranslator:
    def __init__(self, model_name: str = "SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", [])]
                return any(self.model_name.lower() in m.lower() or m.lower() in self.model_name.lower() for m in models)
        except Exception:
            return False

    def translate_scene(self, text_pl: str, duration_sec: float | None = None, orig_pause: float = 0.0) -> str:
        pl_words = len(text_pl.split())
        timing_guidance = ""
        user_hint = ""

        if duration_sec and duration_sec > 1.0:
            # Jeśli w oryginale była intencjonalna pauza > 2.0s (np. prezentacja ekranowa), szanujemy ją
            if orig_pause > 2.0:
                speech_target_sec = max(2.0, duration_sec - orig_pause)
            else:
                speech_target_sec = max(2.0, duration_sec - 1.2)

            target_words = max(6, int(speech_target_sec * 3.3))
            is_dense = (pl_words / speech_target_sec) > 2.6

            if is_dense:
                timing_guidance = (
                    f"\nTIMING & PACING BUDGET (Fast-paced scene, voice window: {speech_target_sec:.1f}s):\n"
                    f"- The Polish speech was dense. Keep the English translation crisp, direct, and concise (~{target_words} words).\n"
                    f"- Avoid wordy filler or redundant clauses, but maintain natural spoken fluency."
                )
                user_hint = f"\n\n(Note: Keep crisp and concise, ~{target_words} words for this {speech_target_sec:.1f}s window)"
            else:
                timing_guidance = (
                    f"\nTIMING & PACING BUDGET (Continuous voiceover, voice window: {speech_target_sec:.1f}s):\n"
                    f"- Target voiceover length: ~{target_words} words to comfortably fill {speech_target_sec:.1f}s with fluent narration.\n"
                    f"- DO NOT use clipped or telegraphic shorthand. Express thoughts with natural conversational fullness and complete sentences.\n"
                    f"- Connect clauses smoothly so the voiceover flows continuously throughout the scene without dying down early."
                )
                user_hint = f"\n\n(Note: Natural articulate flow, target ~{target_words} words for this {speech_target_sec:.1f}s window)"

        system_prompt = (
            "You are a Principal Solutions Architect (22+ years experience) recording an authentic YouTube screencast voiceover in English based on Polish audio.\n\n"
            "Key Requirements:\n"
            "1. Tone: Senior architect talking to peer engineer. Pragmatic, direct, articulate, zero corporate buzzwords.\n"
            "2. Spoken Voiceover Delivery:\n"
            "   - Produce grammatically flawless, natural spoken English.\n"
            "   - Connect clauses naturally so the voiceover has broadcast momentum and flow, avoiding abrupt stops.\n"
            "   - Never use broken, clipped, or telegraphic phrasing (e.g. say 'welcome to newcomers', NEVER 'newcomers to others').\n"
            "3. Pacing & Flow Alignment:\n"
            "   - Follow the TIMING & PACING BUDGET provided below.\n"
            "   - When given comfortable time, do not over-condense into minimal fragments; provide full, clear explanations.\n"
            "4. IT Terminology:\n"
            "   - 'man pages', 'dotfiles', 'Obsidian vault', 'Antigravity', 'Claude Code', 'mount point', 'VRAM footprint', 'bare metal', 'zero-guessing principle'.\n"
            "   - 'na żywym organizmie' -> 'on a live system'\n"
            "   - 'Linux pod spodem' -> 'Linux under the hood'\n"
            "   - 'z miłą chęcią wam pokażę' -> 'I would be happy to show you'\n"
            "   - 'byłem tam i wracałem do Windowsa' -> 'been there, done that, and kept going back to Windows'\n"
            "   - 'zderzamy dwie epoki' -> 'we are colliding two eras'\n"
            "   - 'bebechy Linuxa' -> 'the internal plumbing of Linux'\n"
            "   - 'agentowy sysadmin' -> 'Agentic SysAdmin'\n"
            "   - 'Kdenlive' -> 'Kdenlive'\n"
            "5. Output ONLY the spoken English translation. No explanations, no quotes, no markdown notes."
            f"{timing_guidance}"
        )

        user_prompt = f"Translate this Polish spoken chunk into natural English spoken voiceover:\n\n{text_pl}{user_hint}"

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
            }
        }

        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=90.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            translated = data.get("message", {}).get("content", "").strip()
            translated = clean_llm_translation(translated)
            return translated

    def unload(self) -> None:
        """Natychmiast zwalnia model z VRAM, aby nie kolidował z Breeze-TTS."""
        try:
            payload = {"model": self.model_name, "keep_alive": 0}
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                resp.read()
            log_info(f"Zwolniono model {self.model_name} z VRAM Ollama.")
        except Exception as e:
            log_warn(f"Błąd zwalniania modelu z Ollama: {e}")


class LocalMarianTranslator:
    def __init__(self, model_name: str = "Helsinki-NLP/opus-mt-pl-en"):
        self.model_name = model_name
        self.tokenizer = None
        self.model = None

    def _ensure_loaded(self):
        if self.model is None:
            log_info(f"Inicjalizacja lokalnego modelu tłumaczeniowego {self.model_name} (CPU)...")
            self.tokenizer = MarianTokenizer.from_pretrained(self.model_name)
            self.model = MarianMTModel.from_pretrained(self.model_name)
            log_ok("Zainicjalizowano model tłumaczeniowy MarianMT w pamięci.")

    def translate_batch(self, texts_pl: list[str], batch_size: int = 16) -> list[str]:
        self._ensure_loaded()
        translated_results = []
        for i in range(0, len(texts_pl), batch_size):
            chunk = texts_pl[i:i + batch_size]
            encoded = self.tokenizer(chunk, return_tensors="pt", padding=True, truncation=True)
            with torch.no_grad():
                generated = self.model.generate(**encoded)
            decoded = self.tokenizer.batch_decode(generated, skip_special_tokens=True)
            translated_results.extend(decoded)
        return translated_results


def translate_scenes_batch(scenes: list[dict], translator=None, llm_model: str = "auto") -> None:
    """
    Tłumaczy listę scen z języka polskiego na angielski.
    1. Przeprowadza inżynierski przekład semantyczny przez model Bielik LLM (Ollama), jeśli dostępny.
    2. Fallback: wsadowy przekład neuronowy MarianMT na CPU.
    3. Stosuje słownik pojęć inżynierskich IT (config/tech_terms.json).
    """
    if not scenes:
        return

    # Krok 1: Deterministyczna korekta fonetycznych artefaktów ASR w tekście PL
    for sc in scenes:
        sc["text_pl"] = apply_asr_corrections(sc.get("text_pl", ""))

    tech_terms = load_tech_terms()
    target_llm = "SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M" if llm_model in ("auto", "bielik") else llm_model
    ollama_trans = OllamaTranslator(model_name=target_llm)

    if ollama_trans.is_available():
        log_info(f"Inżynierskie tłumaczenie semantyczne przez model Bielik LLM ({target_llm})...")
        t0 = time.time()
        for idx, sc in enumerate(scenes):
            if idx + 1 < len(scenes):
                window_dur = scenes[idx + 1]["start"] - sc["start"]
                orig_pause = max(0.0, scenes[idx + 1]["start"] - sc["end"])
            else:
                window_dur = sc["end"] - sc["start"]
                orig_pause = 0.0
            log_info(f"Bielik: Tłumaczenie sceny {sc['id']}/{len(scenes)} (okno: {window_dur:.1f}s, luka: {orig_pause:.1f}s): '{sc['text_pl'][:42]}...'")
            try:
                sc["text_en"] = ollama_trans.translate_scene(sc["text_pl"], duration_sec=window_dur, orig_pause=orig_pause)
            except Exception as e_ollama:
                log_warn(f"Błąd Ollama dla sceny {sc['id']} ({e_ollama}), użycie MarianMT...")
                if translator is None:
                    translator = LocalMarianTranslator()
                sc["text_en"] = translator.translate_batch([sc["text_pl"]])[0]
        dt = time.time() - t0
        log_ok(f"Zakończono tłumaczenie Bielik w {dt:.2f}s.")
        ollama_trans.unload()
    else:
        log_info("Bielik/Ollama niedostępny. Uruchamianie lokalnego modelu tłumaczeniowego MarianMT (CPU)...")
        if translator is None:
            translator = LocalMarianTranslator()
        pl_texts = [sc.get("text_pl", "").strip(' „"”') for sc in scenes]
        t0 = time.time()
        translated_en = translator.translate_batch(pl_texts, batch_size=16)
        dt = time.time() - t0
        log_ok(f"Przetłumaczono {len(scenes)} segmentów w {dt:.2f}s przez MarianMT.")
        for sc, text_en in zip(scenes, translated_en):
            sc["text_en"] = text_en

    # Krok 3: Dodatkowa standaryzacja pojęć inżynierskich IT
    for sc in scenes:
        cleaned_en = clean_llm_translation(sc.get("text_en", ""))
        for pl_term, en_term in tech_terms.items():
            cleaned_en = re.sub(re.escape(pl_term), en_term, cleaned_en, flags=re.IGNORECASE)
        sc["text_en"] = cleaned_en




# ==============================================================================
# 5. AUDIO & VIDEO UTILITIES (FFMPEG / FFPROBE / WHISPER)
# ==============================================================================
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


def export_srt(scenes: list[dict], srt_path: Path, lang_key: str = "text_pl", use_synced: bool = False) -> None:
    lines = []
    for idx, sc in enumerate(scenes, start=1):
        s_start = sc.get("start_synced", sc["start"]) if use_synced else sc["start"]
        s_end = sc.get("end_synced", sc["end"]) if use_synced else sc["end"]
        start_str = sec_to_srt_time(s_start)
        end_str = sec_to_srt_time(s_end)
        text = sc.get(lang_key, "").strip()
        lines.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n")
    srt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
        time_match = re.search(r'\[(\d+):(\d+(?:\.\d+)?)\s*-\s*(\d+):(\d+(?:\.\d+)?)\]', block[:120])
        start_sec, end_sec = 0.0, 0.0
        if time_match:
            sm, ss, em, es = time_match.groups()
            start_sec = float(sm) * 60 + float(ss)
            end_sec = float(em) * 60 + float(es)

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


def transcribe_with_whisper(audio_path: Path, model_name: str = "large-v3-turbo") -> list[dict]:
    log_info(f"Brak pliku scenariusza. Uruchamianie lokalnego modelu Whisper ({model_name})...")
    initial_prompt = (
        "W tym filmie omawiamy Zorin OS, Linux, stację roboczą, architekturę IT, "
        "Antigravity, Claude Code, Obsidian vault, pliki README, Markdown, Makefile, "
        "VRAM, NVENC, zasadę zero guessing, na żywym organizmie."
    )

    # 1. Próba na CUDA (FP16)
    for cand in [model_name, "large-v3-turbo", "base"]:
        try:
            model = WhisperModel(cand, device="cuda", compute_type="float16")
            segments, _ = model.transcribe(str(audio_path), beam_size=5, language="pl", initial_prompt=initial_prompt)
            raw_list = list(segments)
            del model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            scenes = group_whisper_segments(raw_list)
            if scenes:
                log_ok(f"Whisper (CUDA/{cand}) wygenerował {len(scenes)} spójnych scen logicznych (ze {len(raw_list)} surowych segmentów).")
                return scenes
        except Exception as e_cuda:
            log_warn(f"Whisper (CUDA/{cand}) niedostępny: {e_cuda}")
            if cand == "base":
                break

    # 2. Próba na CPU (INT8)
    for cand in ["large-v3-turbo", "base"]:
        try:
            model = WhisperModel(cand, device="cpu", compute_type="int8")
            segments, _ = model.transcribe(str(audio_path), beam_size=5, language="pl", initial_prompt=initial_prompt)
            raw_list = list(segments)
            del model
            scenes = group_whisper_segments(raw_list)
            if scenes:
                log_ok(f"Whisper (CPU/{cand}) wygenerował {len(scenes)} spójnych scen.")
                return scenes
        except Exception as e_cpu:
            log_warn(f"Whisper (CPU/{cand}) błąd: {e_cpu}")

    duration = get_audio_duration(audio_path)
    return [{
        "id": 1,
        "start": 0.0,
        "end": round(duration, 2),
        "text_pl": "Nagranie lektorskie do zsynchronizowania."
    }]


def time_sync_and_master(
    scenes: list[dict],
    segment_wavs: list[Path],
    total_duration: float,
    output_wav: Path,
    target_lufs: float = -14.0,
    target_tp: float = -1.0,
    max_speed_factor: float = 1.08,
    min_inter_gap: float = 0.35,
    enable_room_tone: bool = True
) -> None:
    log_info(f"Synchronizacja segmentów i mastering EBU R128 ({target_lufs} LUFS, oddech: {int(min_inter_gap*1000)}ms)...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        adjusted_wavs = []
        actual_starts = []

        prev_end = 0.0

        for idx, (scene, seg_wav) in enumerate(zip(scenes, segment_wavs)):
            seg_dur = get_audio_duration(seg_wav)
            nominal_start = scene["start"]

            # Anchor: start exactly at nominal_start (or immediately after prev_end + min_inter_gap if previous ran over)
            actual_start = max(nominal_start, prev_end + min_inter_gap if idx > 0 else nominal_start)

            if idx + 1 < len(scenes):
                next_nominal = scenes[idx + 1]["start"]
                orig_pause = max(0.0, scenes[idx + 1]["start"] - scene["end"])
                avail_window = max(0.5, next_nominal - actual_start)
            else:
                next_nominal = total_duration
                orig_pause = max(0.0, total_duration - scene["end"])
                avail_window = max(0.5, total_duration - actual_start)

            # Intencjonalna pauza w oryginale (>2.0s np. demonstracja na ekranie) vs mowa ciągła (oddech 0.8s-1.3s)
            if orig_pause > 2.0:
                desired_pause = orig_pause
            else:
                desired_pause = min(1.3, max(0.8, orig_pause + 0.4))

            target_dur = max(seg_dur, avail_window - desired_pause)
            out_seg = tmp_path / f"synced_{idx:03d}.wav"

            if seg_dur > avail_window:
                # Wypowiedź dłuższa niż okno — przyspieszamy z zachowaniem min_inter_gap na oddech
                effective_window = max(0.5, avail_window - min_inter_gap)
                raw_factor = seg_dur / effective_window
                speed_factor = min(raw_factor, max_speed_factor)
                adj_dur = seg_dur / speed_factor
                scene["pacing_status"] = f"x{speed_factor:.2f} (Kompresja)"
                log_info(f"Dopasowanie tempa (kompresja) dla sceny {scene['id']}: x{speed_factor:.2f} ({seg_dur:.2f}s -> {adj_dur:.2f}s, okno: {avail_window:.2f}s)")
                cmd = [
                    "ffmpeg", "-y", "-i", str(seg_wav),
                    "-filter:a", f"atempo={speed_factor:.3f}",
                    "-ar", "48000", "-ac", "1",
                    str(out_seg)
                ]
            elif (avail_window - seg_dur) > desired_pause + 0.4:
                # Nadmiarowa martwa cisza — dynamiczna relaksacja tempa (do 0.78), aby wypełnić okno mową
                raw_speed = seg_dur / target_dur
                speed_factor = max(0.78, min(0.98, raw_speed))
                adj_dur = seg_dur / speed_factor
                actual_gap = avail_window - adj_dur
                scene["pacing_status"] = f"x{speed_factor:.2f} (Spokojne)"
                log_info(f"Dopasowanie tempa (relaksacja ciszy) dla sceny {scene['id']}: x{speed_factor:.2f} ({seg_dur:.2f}s -> {adj_dur:.2f}s, luka: {actual_gap:.2f}s, orig_gap: {orig_pause:.2f}s)")
                # Najwyższej jakości time-stretch przez librubberband (z fallbackiem do atempo)
                cmd = [
                    "ffmpeg", "-y", "-i", str(seg_wav),
                    "-filter:a", f"rubberband=tempo={speed_factor:.3f}",
                    "-ar", "48000", "-ac", "1",
                    str(out_seg)
                ]
            else:
                speed_factor = 1.0
                adj_dur = seg_dur
                scene["pacing_status"] = "1.00x (Płynne)"
                cmd = [
                    "ffmpeg", "-y", "-i", str(seg_wav),
                    "-ar", "48000", "-ac", "1",
                    str(out_seg)
                ]

            try:
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            except subprocess.CalledProcessError:
                # Fallback dla filtrów audio
                fallback_cmd = [
                    "ffmpeg", "-y", "-i", str(seg_wav),
                    "-filter:a", f"atempo={speed_factor:.3f}",
                    "-ar", "48000", "-ac", "1",
                    str(out_seg)
                ]
                subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            adjusted_wavs.append(out_seg)
            actual_starts.append(actual_start)
            prev_end = actual_start + adj_dur

            scene["start_synced"] = round(actual_start, 2)
            scene["end_synced"] = round(actual_start + adj_dur, 2)

        # Wyliczenie pauzy po każdej scenie dla raportu
        for idx, sc in enumerate(scenes):
            if idx + 1 < len(scenes):
                gap = scenes[idx + 1]["start_synced"] - sc["end_synced"]
                sc["post_pause_str"] = f"{gap:.2f}s"
            else:
                gap = total_duration - sc["end_synced"]
                sc["post_pause_str"] = f"{gap:.2f}s (Outro)"

        # Montaż na osi czasu z adelay
        filter_complex = []
        mix_inputs = []
        for idx, (scene, adj_wav, act_start) in enumerate(zip(scenes, adjusted_wavs, actual_starts)):
            delay_ms = int(act_start * 1000)
            filter_complex.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms}[d{idx}]")
            mix_inputs.append(f"[d{idx}]")

        filter_complex.append(f"{''.join(mix_inputs)}amix=inputs={len(scenes)}:dropout_transition=0:normalize=0[vo_raw]")

        if enable_room_tone:
            # Subtelny, ciepły szum tła (room tone) na poziomie -58 dB eliminujący cyfrową próżnię w pauzach
            filter_complex.append(f"anoisesrc=d={total_duration:.2f}:c=pink:r=48000:a=0.0005,lowpass=f=3500,highpass=f=120,volume=-58dB[roomtone]")
            filter_complex.append(f"[vo_raw][roomtone]amix=inputs=2:dropout_transition=0:normalize=0[mixed]")
        else:
            filter_complex.append(f"[vo_raw]acopy[mixed]")

        # Broadcast Presence EQ (odcięcie subsoniczne 70Hz + blask 8kHz) + emisyjny standard EBU R128
        filter_complex.append(f"[mixed]highpass=f=70,treble=g=1.5:f=8000,loudnorm=I={target_lufs}:TP={target_tp}:LRA=11[mastered]")

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
        log_ok(f"Zapisano zmasterowany plik audio z Broadcast EQ i Room Tone: {output_wav.name}")


def auto_detect_input_video(work_dir: Path) -> Path | None:
    input_dir = work_dir / "input"
    if not input_dir.exists():
        return None

    mp4_files = [f for f in input_dir.glob("*.mp4") if not f.name.startswith("raw_voiceover")]
    if not mp4_files:
        return None

    for pref in ["FIXED", "FINAL", "Karaoke"]:
        for f in mp4_files:
            if pref in f.name:
                return f
    return max(mp4_files, key=lambda f: f.stat().st_size)


# ==============================================================================
# 6. GŁÓWNY POTOK PRZETWARZANIA (SINGLE SHORT / EPISODE)
# ==============================================================================
def process_single_short(
    work_dir: Path,
    input_video: Path | None,
    script_path: Path | None,
    ref_audio: Path | None,
    ref_transcript: str,
    engine: str,
    instruction: str,
    output_video: bool,
    transcribe_only: bool = False,
    llm_model: str = "auto",
    edge_voice: str | None = None,
    translator: LocalMarianTranslator | None = None,
    tts_engine: BaseTTSEngine | None = None,
) -> bool:
    work_dir = work_dir.resolve()
    short_id = work_dir.name
    output_dir = work_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_video:
        input_video = auto_detect_input_video(work_dir)

    if not input_video or not input_video.exists():
        log_err(f"Nie znaleziono wideo źródłowego w {work_dir}/input/")
        return False

    total_duration = get_audio_duration(input_video)

    log_info("=" * 65)
    log_info(f" Workstation Hub: Autonomiczny Potok Dubbingu dla {short_id}")
    log_info("=" * 65)
    log_info(f"Wideo wejściowe:  {input_video.name} ({total_duration:.2f}s)")
    log_info(f"Katalog roboczy:  {work_dir}")
    log_info(f"Silnik TTS:       {engine.upper()}")

    # 1. Ekstrakcja czystego audio ze źródła lub dedykowany plik lektorski
    raw_audio = output_dir / f"{short_id}_VoiceOver_RAW_24k.wav"
    input_voiceover = None
    input_dir = work_dir / "input"
    if input_dir.exists():
        for vo_cand in sorted(input_dir.glob("*.wav")):
            if "voiceover" in vo_cand.name.lower() or "clean" in vo_cand.name.lower():
                input_voiceover = vo_cand
                break

    if input_voiceover and input_voiceover.exists():
        log_info(f"Wykryto dedykowany plik lektorski: {input_voiceover.name}")
        cmd = [
            "ffmpeg", "-y", "-i", str(input_voiceover),
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "24000", "-ac", "1",
            str(raw_audio)
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        log_ok("Przygotowano strumień lektorski 24kHz z dedykowanego pliku WAV.")
    else:
        extract_raw_audio(input_video, raw_audio, sample_rate=24000)

    # 2. Parsowanie scenariusza lub automatyczna transkrypcja Whisper
    if not script_path:
        candidates = [
            work_dir / "input" / "short_script.md",
            work_dir / f"{short_id}.srt",
            input_video.with_suffix(".srt"),
        ]
        candidates.extend(list((work_dir / "input").glob("*.srt")))
        for cand in candidates:
            if cand.exists():
                script_path = cand
                break

    if script_path and script_path.exists():
        log_info(f"Wczytywanie scenariusza: {script_path.name}")
        if script_path.suffix == ".srt":
            scenes = parse_srt(script_path)
        else:
            scenes = parse_short_script_md(script_path)

        srt_duration = scenes[-1]["end"] if scenes else 0.0
        if abs(srt_duration - total_duration) > 20.0:
            log_warn("Scenariusz nie odpowiada czasowo wideo! Uruchamianie bezpośredniej transkrypcji Whisper...")
            whisper_scenes = transcribe_with_whisper(raw_audio)
            if whisper_scenes:
                scenes = whisper_scenes
    else:
        log_info("Brak pliku scenariusza (.md/.srt) — uruchamianie automatycznej transkrypcji Whisper...")
        scenes = transcribe_with_whisper(raw_audio)

    if not scenes:
        log_err(f"Nie udało się wyodrębnić segmentów do dubbingu dla {short_id}.")
        return False

    # 3. Dynamiczne tłumaczenie maszynowe (Bielik LLM / MarianMT + Tech Terms)
    translate_scenes_batch(scenes, translator=translator, llm_model=llm_model)

    transcript_json = output_dir / f"{short_id}_Dubbing_Transcript_EN.json"
    with open(transcript_json, "w", encoding="utf-8") as f:
        json.dump(scenes, f, ensure_ascii=False, indent=2)
    log_ok(f"Zapisano transkrypcję segmentów: {transcript_json.name}")

    srt_pl_file = output_dir / f"{short_id}_PL.srt"
    srt_en_file = output_dir / f"{short_id}_EN.srt"
    export_srt(scenes, srt_pl_file, lang_key="text_pl")
    export_srt(scenes, srt_en_file, lang_key="text_en")
    log_ok(f"Wygenerowano napisy SRT: {srt_pl_file.name} oraz {srt_en_file.name}")

    if transcribe_only:
        log_ok(f"Tryb --transcribe-only zakończony dla {short_id}.")
        return True

    # 4. Inicjalizacja wybranego silnika syntezy (Qwen3-TTS / Chatterbox / KokoClone / Breeze / Edge)
    dub_parts_dir = output_dir / "dub_parts"
    dub_parts_dir.mkdir(parents=True, exist_ok=True)
    segment_wavs = []

    # Rozstrzygnięcie i pobranie silnika
    selected_engine = engine
    if selected_engine == "auto":
        selected_engine = detect_best_engine(ref_audio)

    try:
        active_engine_instance = get_tts_engine(selected_engine, ref_audio=ref_audio, voice=edge_voice)
        active_engine_name = active_engine_instance.name
    except Exception as e_eng:
        log_warn(f"Nie udało się załadować silnika {selected_engine} ({e_eng}), fallback do Edge-TTS...")
        selected_engine = "edge"
        active_engine_instance = get_tts_engine("edge", voice=edge_voice or "en-US-ChristopherNeural")
        active_engine_name = active_engine_instance.name

    log_info(f"Generowanie mowy dla poszczególnych scen (silnik: {selected_engine.upper()})...")
    for sc in scenes:
        part_wav = dub_parts_dir / f"scene_{sc['id']:03d}.wav"
        txt_marker = part_wav.with_suffix(".txt")
        engine_marker = part_wav.with_suffix(".engine")
        expected_engine = selected_engine

        # Inteligentne wznawianie: użyj istniejącego pliku tylko jeśli tekst angielski jest identyczny ORAZ silnik jest zgodny
        if (
            part_wav.exists()
            and part_wav.stat().st_size > 1000
            and txt_marker.exists()
            and txt_marker.read_text(encoding="utf-8").strip() == sc["text_en"].strip()
            and (not engine_marker.exists() or engine_marker.read_text(encoding="utf-8").strip() == expected_engine)
        ):
            segment_wavs.append(part_wav)
            continue

        log_info(f"{selected_engine.upper()}: Synteza sceny {sc['id']}: '{sc['text_en'][:42]}...'")
        synth_ok = active_engine_instance.synthesize(
            text=sc["text_en"],
            out_wav=part_wav,
            ref_audio=ref_audio,
            ref_transcript=ref_transcript,
            instruction=instruction,
        )

        if not synth_ok:
            if selected_engine != "edge" and engine != "auto":
                log_err(f"Błąd syntezy sceny {sc['id']} przez wymuszony silnik {selected_engine}.")
                return False
            voice_to_use = edge_voice or "en-US-ChristopherNeural"
            log_info(f"Edge-TTS Fallback: Synteza sceny {sc['id']}: '{sc['text_en'][:42]}...' (voice: {voice_to_use})")
            fallback_engine = get_tts_engine("edge", voice=voice_to_use)
            synth_ok = fallback_engine.synthesize(text=sc["text_en"], out_wav=part_wav)
            active_engine_name = f"Edge-TTS ({voice_to_use})"
            if synth_ok:
                engine_marker.write_text("edge\n", encoding="utf-8")
        else:
            engine_marker.write_text(f"{selected_engine}\n", encoding="utf-8")

        if part_wav.exists() and part_wav.stat().st_size > 1000:
            txt_marker.write_text(sc["text_en"].strip() + "\n", encoding="utf-8")
        segment_wavs.append(part_wav)

    # 5. Time-sync i mastering EBU R128
    mastered_wav = output_dir / f"{short_id}_VoiceOver_EN_CLEAN.wav"
    time_sync_and_master(scenes, segment_wavs, total_duration, mastered_wav, target_lufs=-14.0, target_tp=-1.0)

    # Aktualizacja napisów SRT i transkrypcji o precyzyjnie zsynchronizowane znaczniki czasowe
    export_srt(scenes, srt_en_file, lang_key="text_en", use_synced=True)
    with open(transcript_json, "w", encoding="utf-8") as f:
        json.dump(scenes, f, ensure_ascii=False, indent=2)

    # 6. Finalny montaż wideo EN
    if output_video:
        output_video_file = output_dir / f"{short_id}_FINAL_EN_DUBBED.mp4"
        log_info(f"Generowanie filmu z angielską ścieżką dźwiękową: {output_video_file.name}...")
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
    summary_md = output_dir / f"{short_id}_Dubbing_Summary.md"
    with open(summary_md, "w", encoding="utf-8") as f:
        f.write(f"# Raport Dubbingu AI: {short_id}\n\n")
        f.write(f"- **Wideo źródłowe:** `{input_video.name}` ({total_duration:.2f}s)\n")
        f.write(f"- **Silnik syntezy:** `{active_engine_name}`\n")
        f.write(f"- **Standard emisyjny audio:** `EBU R128 (-14.0 LUFS, True Peak <= -1.0 dBFS)`\n\n")
        f.write("## Wygenerowane Pliki Produkcyjne (Deliverables)\n\n")
        f.write(f"1. **Plik dźwiękowy lektora (YouTube Multi-Language Audio):**\n")
        f.write(f"   `{mastered_wav.name}` (WAV 48kHz stereo, -14.0 LUFS — do wrzucenia w YouTube Studio jako alternatywna ścieżka językowa).\n\n")
        if output_video:
            f.write(f"2. **Zdubbingowany film EN (Full Video + Dubbing):**\n")
            f.write(f"   `{output_video_file.name}` (wideo + zsynchronizowany dubbing EN).\n\n")
        f.write(f"3. **Napisy w języku angielskim:** `{srt_en_file.name}`\n")
        f.write(f"4. **Napisy w języku polskim:** `{srt_pl_file.name}`\n\n")
        f.write("## Tabela Zsynchronizowanych Scen\n\n")
        f.write("| Scena | Zakres czasu | Pacing / Status | Pauza po scenie | Oryginał PL | Kwestia EN |\n")
        f.write("| :---: | :---: | :---: | :---: | :--- | :--- |\n")
        for sc in scenes:
            start_t = sc.get("start_synced", sc["start"])
            end_t = sc.get("end_synced", sc["end"])
            pacing = sc.get("pacing_status", "1.00x (Płynne)")
            pause_str = sc.get("post_pause_str", "-")
            f.write(f"| {sc['id']} | `{start_t:.2f}s - {end_t:.2f}s` | `{pacing}` | `{pause_str}` | {sc['text_pl']} | **{sc['text_en']}** |\n")

    log_ok(f"Zapisano raport podsumowujący: {summary_md.name}")
    log_info("=" * 65)
    log_ok(f"PROCES ZAKOŃCZONY SUKCESEM DLA {short_id}!")
    log_info("Dostarczone pliki produkcyjne (Deliverables):")
    log_info(f"  1. [YouTube Audio Track]: {mastered_wav.name}")
    if output_video:
        log_info(f"  2. [Full Dubbed Video]:   {output_video_file.name}")
    log_info(f"  3. [English Subtitles]:   {srt_en_file.name}")
    log_info(f"  4. [Polish Subtitles]:    {srt_pl_file.name}")
    log_info("=" * 65)
    return True


process_video = process_single_short


# ==============================================================================
# 7. PUNKT WEJŚCIA CLI
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Generyczny autonomiczny potok dubbingu wideo (pojedynczy lub zestaw).")
    parser.add_argument("-i", "--input", type=Path, default=None, help="Opcjonalny plik wideo źródłowego (MP4)")
    parser.add_argument("-w", "--work-dir", type=Path, default=None, help="Katalog roboczy projektu (np. work/EP002_Short)")
    parser.add_argument("-s", "--script", type=Path, default=None, help="Opcjonalny plik scenariusza (MD lub SRT)")
    parser.add_argument("--batch", nargs="+", help="Lista katalogów projektów do przetworzenia wsadowego")

    # Próbka głosu
    parser.add_argument("--ref-audio", type=Path, default=None, help="Ścieżka do gotowej próbki referencyjnej WAV")
    parser.add_argument("--ref-transcript", type=str, default="", help="Transkrypcja próbki referencyjnej")
    parser.add_argument("--ref-source", type=Path, default=None, help="Plik źródłowy do wycięcia próbki w locie")
    parser.add_argument("--ref-start", type=str, default="00:00:12.000", help="Początek wycinka próbki")
    parser.add_argument("--ref-end", type=str, default="00:00:20.300", help="Koniec wycinka próbki")

    # Silnik i styl
    parser.add_argument("--engine", choices=["auto", "qwen", "kokoro", "chatterbox", "breeze", "edge"], default="auto", help="Silnik syntezy TTS")
    parser.add_argument("--llm-model", type=str, default="auto", help="Model LLM w Ollama do inżynierskiego tłumaczenia (np. auto, bielik, none)")
    parser.add_argument("--accent", choices=["default", "us", "uk", "neutral"], default="default", help="Wybór stylu akcentu lektora (us, uk, neutral, default)")
    parser.add_argument("--edge-voice", type=str, default=None, help="Opcjonalny głos dla silnika Edge-TTS (np. en-US-AndrewMultilingualNeural, en-GB-RyanNeural)")
    parser.add_argument("--instruction", type=str, default="Maintain a calm, confident, authoritative engineering delivery with clear cadence.", help="Instrukcja stylu mowy")
    parser.add_argument("--output-video", action="store_true", default=True, help="Wygeneruj zduplikowane wideo z dubbingiem EN")
    parser.add_argument("--transcribe-only", action="store_true", default=False, help="Wygeneruj wyłącznie transkrypcję Whisper i napisy SRT (bez syntezy TTS)")
    args = parser.parse_args()

    # Wybór presetów akcentu i głosu
    accent_cfg = ACCENT_PRESETS.get(args.accent, ACCENT_PRESETS["default"])
    active_instruction = args.instruction
    if active_instruction == parser.get_default("instruction") and args.accent != "default":
        active_instruction = accent_cfg["instruction"]
    active_edge_voice = args.edge_voice or accent_cfg["edge_voice"]

    # Wycięcie próbki referencyjnej w locie jeśli wskazano --ref-source
    ref_audio = args.ref_audio
    ref_transcript = args.ref_transcript
    if args.ref_source and args.ref_source.exists():
        sample_out = REPO_ROOT / "work" / "voice_sample" / "ref_voice_sample.wav"
        extract_voice_sample_clip(args.ref_source, args.ref_start, args.ref_end, sample_out, ref_transcript)
        ref_audio = sample_out

    if not ref_audio:
        candidates = [
            REPO_ROOT / "work" / "voice_sample" / "ref_voice_sample.wav",
            Path("work/voice_sample/ref_voice_sample.wav"),
            Path("work/ref_voice_sample.wav"),
        ]
        for cand in candidates:
            if cand.exists():
                ref_audio = cand
                txt_cand = cand.with_suffix(".txt")
                if txt_cand.exists() and not ref_transcript:
                    ref_transcript = txt_cand.read_text(encoding="utf-8").strip()
                break

    # Leniwa inicjalizacja modeli (GPU VRAM jest zwalniane sekwencyjnie)
    shared_translator = None
    shared_tts_engine = None

    # Tryb wsadowy
    if args.batch:
        log_info(f"Uruchamianie przetwarzania zestawu wideo ({len(args.batch)} projektów)...")
        for b_dir in args.batch:
            target_dir = Path(b_dir)
            process_video(
                work_dir=target_dir,
                input_video=None,
                script_path=None,
                ref_audio=ref_audio,
                ref_transcript=ref_transcript,
                engine=args.engine,
                instruction=active_instruction,
                output_video=args.output_video,
                transcribe_only=args.transcribe_only,
                llm_model=args.llm_model,
                edge_voice=active_edge_voice,
                translator=shared_translator,
                tts_engine=shared_tts_engine,
            )
        return

    # Tryb pojedynczy
    work_dir = args.work_dir
    input_video = args.input.resolve() if args.input else None
    if not work_dir and input_video:
        work_dir = input_video.parent.parent

    if not work_dir:
        log_err("Wymagany parametr --work-dir (-w) lub --input (-i) lub --batch.")
        sys.exit(1)

    process_video(
        work_dir=work_dir,
        input_video=input_video,
        script_path=args.script,
        ref_audio=ref_audio,
        ref_transcript=ref_transcript,
        engine=args.engine,
        instruction=active_instruction,
        output_video=args.output_video,
        transcribe_only=args.transcribe_only,
        llm_model=args.llm_model,
        edge_voice=active_edge_voice,
        translator=shared_translator,
        tts_engine=shared_tts_engine,
    )


if __name__ == "__main__":
    main()
