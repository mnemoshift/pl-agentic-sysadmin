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

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ==============================================================================
# 0. SELF-BOOTSTRAPPING: Automatyczne przełączanie na środowisko .venv repozytorium
# ==============================================================================
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

if __name__ == "__main__" and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    if VENV_PYTHON.exists() and os.access(str(VENV_PYTHON), os.X_OK):
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)
    elif not VENV_PYTHON.exists() and shutil.which("uv"):
        print("[INFO] Wykryto brak środowiska .venv w repozytorium. Automatyczna inicjalizacja przez 'uv sync'...")
        subprocess.run(["uv", "sync"], cwd=str(REPO_ROOT), check=True)
        if VENV_PYTHON.exists():
            os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

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

import torch  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402
from transformers import MarianMTModel, MarianTokenizer  # noqa: E402

# Rejestracja ścieżki skryptów w sys.path dla pakietów wewnętrznych
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from text_director import (  # noqa: E402
    clean_voiceover_text,
    direct_voiceover,
    enrich_voiceover_tags,
    strip_voice_tags,
    supports_voice_tags,
)
from tts_engines import (  # noqa: E402
    BaseTTSEngine,
    detect_best_engine,
    get_tts_engine,
)
from work_manager import WorkRunManager  # noqa: E402


def log_info(msg: str):
    print(f"\033[1;34m[INFO]\033[0m {msg}")

def log_ok(msg: str):
    print(f"\033[1;32m[OK]\033[0m {msg}")

def log_warn(msg: str):
    print(f"\033[1;33m[WARN]\033[0m {msg}")

def log_err(msg: str):
    print(f"\033[1;31m[ERROR]\033[0m {msg}", file=sys.stderr)

def log_pacing(msg: str):
    print(f"\033[1;35m[PACING]\033[0m {msg}")

# Kalibracja tempa lektora dla domkniętej pętli feedbacku (Closed-Loop Pacing Guardrail)
SPEECH_WPS_BENCHMARK: float = 3.42  # Średnia prędkość mowy lektora Qwen3-TTS (słów / sekundę)
DEFAULT_MAX_PACING_RETRIES: int = 10  # Domyślny limit prób rekalibracji na scenę


@dataclass(frozen=True)
class PacingTarget:
    window_dur: float
    speech_target_sec: float
    desired_gap: float
    min_acceptable_gap: float
    max_acceptable_gap: float
    target_words: int
    min_words: int
    max_words: int


def compute_pacing_target(
    window_dur: float,
    orig_pause: float = 0.0,
    pl_words: int = 0,
    wps: float = SPEECH_WPS_BENCHMARK,
) -> PacingTarget:
    """
    Wylicza zbalansowany budżet czasowy i docelową liczbę słów dla danej sceny:
    - Uwzględnia gęstość semantyczną oryginału PL (pl_words), zapobiegając sztucznemu
      rozdymaniu lakonicznych wypowiedzi (np. pauzy demonstracyjne na ekranie).
    - Dla intencjonalnych przerw w wideo (demonstracje > 2.0s): zachowuje oryginalną pauzę.
    - Dla mowy ciągłej: celuje w naturalny oddech radiowy (1.0s - 1.3s).
    - Progi akceptacji [min_acceptable_gap, max_acceptable_gap] zapobiegają fałszywym alarmom.
    """
    if orig_pause > 2.0:
        speech_target_sec = max(2.0, window_dur - orig_pause)
        desired_gap = orig_pause
        min_acceptable_gap = max(0.8, orig_pause - 1.5)
        max_acceptable_gap = orig_pause + 2.0
    else:
        # Mowa ciągła: naturalny oddech radiowy
        speech_target_sec = max(2.0, window_dur - 1.2)
        desired_gap = 1.2
        min_acceptable_gap = 0.4
        max_acceptable_gap = 3.2

    max_fit_words = max(5, int(round(speech_target_sec * wps)))

    if pl_words > 0:
        # Naturalna ekspansja językowa z polskiego na angielski (zwykle 1.15 - 1.35x)
        natural_en_words = max(4, int(round(pl_words * 1.25)))
        if natural_en_words < max_fit_words:
            # Polski lektor mówił wolno / z pauzami demonstracyjnymi na ekranie.
            # Nie zmuszamy modelu do halucynacji podwójnej liczby słów.
            target_words = max(natural_en_words, int(round((natural_en_words + max_fit_words) / 2)))
            min_words = max(4, int(round(natural_en_words * 0.85)))
            max_words = max_fit_words
        else:
            target_words = max_fit_words
            min_words = max(4, int(round((window_dur - max_acceptable_gap) * wps)))
            max_words = max(5, int(round((window_dur - min_acceptable_gap) * wps)))
    else:
        target_words = max_fit_words
        min_words = max(4, int(round((window_dur - max_acceptable_gap) * wps)))
        max_words = max(5, int(round((window_dur - min_acceptable_gap) * wps)))

    return PacingTarget(
        window_dur=round(window_dur, 2),
        speech_target_sec=round(speech_target_sec, 2),
        desired_gap=round(desired_gap, 2),
        min_acceptable_gap=round(min_acceptable_gap, 2),
        max_acceptable_gap=round(max_acceptable_gap, 2),
        target_words=target_words,
        min_words=min_words,
        max_words=max_words,
    )




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


def apply_tech_terms(text: str, tech_terms: dict[str, str]) -> str:
    """Aplikuje słownik pojęć inżynierskich IT na wyjściowy tekst lektora z granicami słów."""
    if not tech_terms or not text:
        return text
    for pl_term, en_term in tech_terms.items():
        text = re.sub(rf"\b{re.escape(pl_term)}\b", en_term, text, flags=re.IGNORECASE)
    return text



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


## ==============================================================================
# 3. LOKALNE TŁUMACZENIE I KOREKTA LLM (BIELIK / OLLAMA LUB MARIANMT)
# ==============================================================================
# clean_voiceover_text oraz strip_voice_tags są zaimportowane z text_director



def clean_llm_translation(raw_text: str) -> str:
    """Oczyszcza odpowiedź LLM z ewentualnych metadanych, nagłówków, cudzysłowów i notatek."""
    return clean_voiceover_text(raw_text)



class OllamaTranslator:
    """
    Wyspecjalizowany translator LLM oparty o model Bielik w lokalnej instalacji Ollama.
    Realizuje inżynierski przekład semantyczny z uwzględnieniem budżetu tempa mowy (pacing)
    oraz adaptacyjnym harmonogramem temperatury dla przełamywania lokalnych minimów.
    """

    SYSTEM_PROMPT = (
        "You are a Principal Solutions Architect (22+ years experience) recording an authentic "
        "YouTube screencast voiceover in English based on Polish audio.\n\n"
        "Key Requirements:\n"
        "1. Tone: Senior architect talking to peer engineer. Pragmatic, direct, articulate, zero corporate buzzwords.\n"
        "2. Natural Spoken Fluency:\n"
        "   - Produce grammatically flawless, natural spoken English with smooth cadence.\n"
        "   - Never use broken, clipped, or telegraphic phrasing (e.g. say 'welcome to newcomers', NEVER 'newcomers to others').\n"
        "3. Strict Fidelity (NO HALLUCINATIONS):\n"
        "   - Translate strictly what is stated in the Polish source. Do NOT extrapolate, invent side stories, "
        "or append unprompted concluding summaries or essays.\n"
        "4. IT Terminology:\n"
        "   - 'man pages', 'dotfiles', 'Obsidian vault', 'Antigravity', 'Claude Code', 'mount point', "
        "'VRAM footprint', 'bare metal', 'zero-guessing principle'.\n"
        "   - 'na żywym organizmie' -> 'on a live system'\n"
        "   - 'Linux pod spodem' -> 'Linux under the hood'\n"
        "   - 'z miłą chęcią wam pokażę' -> 'I would be happy to show you'\n"
        "   - 'byłem tam i wracałem do Windowsa' -> 'been there, done that, and kept going back to Windows'\n"
        "   - 'zderzamy dwie epoki' -> 'we are colliding two eras'\n"
        "   - 'bebechy Linuxa' -> 'the internal plumbing of Linux'\n"
        "   - 'agentowy sysadmin' -> 'Agentic SysAdmin'\n"
        "   - 'Kdenlive' -> 'Kdenlive'\n"
        "5. Output Format:\n"
        "   - Output ONLY the plain spoken English voiceover text wrapped strictly in <voiceover>...</voiceover> tags.\n"
        "   - Example: <voiceover>Welcome to the workstation hub.</voiceover>\n"
        "   - No notes, no explanations, no quotes, no commentary outside or inside the tags."
    )

    def __init__(
        self,
        model_name: str = "SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M",
        base_url: str = "http://localhost:11434",
    ):
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

    def _call_ollama(self, messages: list[dict], temperature: float = 0.25) -> str:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": 0.9,
            },
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=90.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_content = data.get("message", {}).get("content", "").strip()
            return clean_voiceover_text(raw_content)

    def translate_chunk(
        self,
        text_pl: str,
        pacing: PacingTarget,
        prev_words: int | None = None,
        attempt: int = 1,
    ) -> str:
        """
        Tłumaczy segment mowy na język angielski z kontrolą tempa:
        - Dla próby 1: bazowe tłumaczenie semantyczne ze wskazówką budżetu słów.
        - Dla kolejnych prób: rekalibracja bezpośrednio ze źródła PL z adaptacyjną temperaturą.
        """
        temp = min(0.60, 0.25 + 0.05 * (attempt - 1))

        if attempt == 1 or prev_words is None:
            user_prompt = (
                f"PACING RULES & BUDGET:\n"
                f"- Speech window: {pacing.speech_target_sec:.1f}s\n"
                f"- Target voiceover length: ~{pacing.target_words} words "
                f"(acceptable range: {pacing.min_words} to {pacing.max_words} words).\n"
                f"- Express the source thoughts thoroughly and articulately without adding unprompted concluding summaries.\n"
                f"- Do NOT output word counts or notes in parentheses.\n"
                f"- Wrap your final translation strictly within <voiceover>...</voiceover> tags.\n\n"
                f"SOURCE TEXT TO TRANSLATE:\n"
                f"<source_text>\n{text_pl}\n</source_text>\n\n"
                f"Output ONLY the spoken English voiceover wrapped in <voiceover> tags:"
            )
        else:
            direction = "too short" if prev_words < pacing.target_words else "too long"
            if direction == "too short":
                guidance = (
                    f"- The previous translation had {prev_words} words, which speaks slightly too fast.\n"
                    f"- Produce a slightly fuller translation (~{pacing.target_words} words, up to {pacing.max_words} words max).\n"
                    f"- Strictly retain fidelity to the Polish text. Do NOT invent background tutorials or side topics.\n"
                    f"- Expand ONLY by using complete grammatical sentences and articulate spoken cadence.\n"
                    f"- Do NOT append concluding essays."
                )
            else:
                guidance = (
                    f"- The previous translation had {prev_words} words, which exceeds the {pacing.speech_target_sec:.1f}s budget.\n"
                    f"- Condense the translation to ~{pacing.target_words} words (range: {pacing.min_words} to {pacing.max_words} words).\n"
                    f"- Cut redundant phrasing and wordy transitions while retaining all technical facts and commands."
                )

            user_prompt = (
                f"PACING REVISION RULES & BUDGET:\n"
                f"- Speech window: {pacing.speech_target_sec:.1f}s\n"
                f"- Target voiceover length: ~{pacing.target_words} words "
                f"(acceptable range: {pacing.min_words} to {pacing.max_words} words).\n"
                f"{guidance}\n"
                f"- Do NOT output word counts or notes in parentheses.\n"
                f"- Wrap your revised voiceover output strictly within <voiceover>...</voiceover> tags.\n\n"
                f"SOURCE TEXT TO TRANSLATE:\n"
                f"<source_text>\n{text_pl}\n</source_text>\n\n"
                f"Output ONLY the spoken English voiceover wrapped in <voiceover> tags:"
            )

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        return self._call_ollama(messages, temperature=temp)

    def unload(self) -> None:
        """Natychmiast zwalnia model z VRAM, aby nie kolidował z syntezatorem TTS."""
        try:
            payload = {"model": self.model_name, "keep_alive": 0}
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
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


def translate_scenes_batch(
    scenes: list[dict],
    translator=None,
    llm_model: str = "auto",
    max_pacing_retries: int = DEFAULT_MAX_PACING_RETRIES,
) -> None:
    """
    Tłumaczy listę scen z języka polskiego na angielski.
    1. Przeprowadza inżynierski przekład semantyczny przez model Bielik LLM (Ollama), jeśli dostępny.
    2. Waliduje długość i dopasowanie do budżetu czasowego (Closed-Loop Pacing Guardrail) w pętli do max_pacing_retries prób.
    3. Stosuje adaptacyjne skalowanie temperatury oraz Best-of-N fallback minimalizujący odchylenie pauzy.
    4. Fallback: wsadowy przekład neuronowy MarianMT na CPU w przypadku braku Ollama.
    5. Standaryzuje słownictwo inżynierskie IT (config/tech_terms.json).
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
        log_info(f"Inżynierskie tłumaczenie semantyczne przez model Bielik LLM ({target_llm}) z pętlą kalibracji tempa (max {max_pacing_retries} prób)...")
        t0 = time.time()
        for idx, sc in enumerate(scenes):
            if idx + 1 < len(scenes):
                window_dur = scenes[idx + 1]["start"] - sc["start"]
                orig_pause = max(0.0, scenes[idx + 1]["start"] - sc["end"])
            else:
                window_dur = sc["end"] - sc["start"]
                orig_pause = 0.0

            pl_words = len(sc.get("text_pl", "").split())
            pacing = compute_pacing_target(window_dur, orig_pause, pl_words=pl_words)
            history = []  # [(cand, words, est_gap, gap_dev)]
            accepted = False

            cand = ""
            words = 0
            for attempt in range(1, max_pacing_retries + 1):
                prev_words = words if attempt > 1 else None
                try:
                    cand = ollama_trans.translate_chunk(
                        text_pl=sc["text_pl"],
                        pacing=pacing,
                        prev_words=prev_words,
                        attempt=attempt,
                    )
                    cand = apply_tech_terms(clean_voiceover_text(cand), tech_terms)
                except Exception as e_ollama:
                    log_warn(f"Błąd Ollama w próbie {attempt} dla sceny {sc['id']} ({e_ollama}), użycie MarianMT...")
                    if translator is None:
                        translator = LocalMarianTranslator()
                    cand = translator.translate_batch([sc["text_pl"]])[0]
                    cand = apply_tech_terms(clean_voiceover_text(cand), tech_terms)
                    history.append((cand, len(cand.split()), window_dur - (len(cand.split()) / SPEECH_WPS_BENCHMARK), 0.0))
                    accepted = True
                    break

                words = len(cand.split())
                est_dur = words / SPEECH_WPS_BENCHMARK
                est_gap = window_dur - est_dur
                gap_dev = abs(est_gap - pacing.desired_gap)
                word_diff = abs(words - pacing.target_words)
                history.append((cand, words, est_gap, gap_dev))

                # Warunki akceptacji:
                # 1. Szacowana luka mieści się w akceptowalnym oknie [min_acceptable_gap, max_acceptable_gap]
                # 2. Liczba słów mieści się w dopuszczalnym przedziale [min_words, max_words]
                # 3. Odchylenie liczby słów <= 5 (różnica <= 1.4s, bez problemu kompensowana przez atempo [0.94, 1.06])
                # 4. Wypowiedź w pełni przekłada źródło PL (words >= pl_words * 0.9) a luka nie przekracza okna z marginesem
                is_gap_ok = pacing.min_acceptable_gap <= est_gap <= pacing.max_acceptable_gap
                is_words_ok = pacing.min_words <= words <= pacing.max_words or word_diff <= 5
                is_fidelity_ok = (words >= int(pl_words * 0.9)) and (est_gap <= pacing.max_acceptable_gap + 1.5)

                if is_gap_ok or is_words_ok or is_fidelity_ok or max_pacing_retries <= 1:
                    sc["text_en"] = clean_voiceover_text(cand)
                    sc["calibration_retries"] = attempt
                    sc["calibration_status"] = f"{attempt} {'próba' if attempt == 1 else 'próby'} (Idealnie)"
                    status_label = "IDEALNIE" if attempt == 1 else f"ZAAKCEPTOWANO w próbie {attempt}!"
                    log_ok(f"Scena {sc['id']:02d}/{len(scenes)} [Próba {attempt}/{max_pacing_retries}]: {words} słów (szac. {est_dur:.1f}s, luka: {est_gap:.1f}s, okno: {window_dur:.1f}s) -> {status_label}")
                    accepted = True
                    break

                else:
                    gap_type = f"ZA DUŻA LUKA ({est_gap:.1f}s > {pacing.max_acceptable_gap:.1f}s)" if est_gap > pacing.max_acceptable_gap else f"ZA DŁUGI TEKST ({est_dur:.1f}s > {pacing.speech_target_sec:.1f}s)"
                    log_pacing(f"Scena {sc['id']:02d}/{len(scenes)} [Próba {attempt}/{max_pacing_retries}]: {words} słów (szac. {est_dur:.1f}s, luka: {est_gap:.1f}s, cel: ~{pacing.target_words} słów [{pacing.min_words}-{pacing.max_words}]) -> {gap_type}. Rekalibracja Bielik...")

            if not accepted and history:
                # Best-of-N: wybór kandydata o najmniejszym odchyleniu od naturalnego oddechu radiowego
                best_attempt = min(history, key=lambda x: x[3])
                sc["text_en"] = clean_voiceover_text(best_attempt[0])
                sc["calibration_retries"] = len(history)
                sc["calibration_status"] = f"Najlepsza z {len(history)} ({best_attempt[1]} słów, luka: {best_attempt[2]:.1f}s)"
                log_warn(f"Scena {sc['id']:02d}/{len(scenes)}: Wykorzystano {len(history)} prób. Wybrano wariant o najmniejszym odchyleniu pauzy: {best_attempt[1]} słów (szac. luka: {best_attempt[2]:.1f}s).")

        dt = time.time() - t0
        log_ok(f"Zakończono tłumaczenie Bielik z walidacją budżetu czasowego w {dt:.2f}s.")
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
            sc["text_en"] = apply_tech_terms(clean_voiceover_text(text_en), tech_terms)
            sc["calibration_retries"] = 1
            sc["calibration_status"] = "MarianMT (Brak kalibracji)"





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


def resolve_reference_audio(
    ref_audio: Path | str | None = None,
    work_dir: Path | None = None,
    ref_transcript: str = "",
    target_lang: str = "en",
) -> tuple[Path, str]:
    """
    Jednolita detekcja pliku referencyjnego głosu lektora (WAV) oraz opcjonalnej transkrypcji (TXT).
    Zgodnie z konwencją pl-agentic-sysadmin jedyną lokalizacją próbek jest: work/voice_sample/

    Reguły:
    1. Jeśli ref_audio nie podano, sprawdzana jest zmienna środowiskowa VOICE_REF_FILE.
    2. Jeśli wskazano konkretną próbkę (jawny parametr lub env):
       - Sprawdza istnienie bezpośrednio oraz w katalogu work/voice_sample/.
       - Jeśli plik nie istnieje: zgłasza błąd z listą dostępnych próbek w work/voice_sample/.
    3. Jeśli nie wskazano żadnej próbki:
       - Skanuje katalog work/voice_sample/ w poszukiwaniu plików audio (*.wav, *.mp3, *.flac).
       - Jeśli jest dokładnie 1 plik: staje się on automatycznie domyślnym bez względu na nazwę.
       - Jeśli jest więcej niż 1 plik: zgłasza błąd informujący, że wymagany jest parametr
         --voice-ref / --ref-audio lub zmienna VOICE_REF_FILE, i wyświetla listę dostępnych opcji.
       - Jeśli brak próbek: zgłasza błąd z instrukcją jak dodać próbkę do work/voice_sample/.
    """
    sample_dir = REPO_ROOT / "work" / "voice_sample"

    if not ref_audio:
        env_ref = os.environ.get("VOICE_REF_FILE")
        if env_ref:
            ref_audio = Path(env_ref)

    if ref_audio:
        cand = Path(ref_audio)
        resolved: Path | None = None
        if not cand.is_absolute():
            if cand.exists():
                resolved = cand.resolve()
            elif (sample_dir / cand).exists():
                resolved = (sample_dir / cand).resolve()
            elif (REPO_ROOT / cand).exists():
                resolved = (REPO_ROOT / cand).resolve()
            elif (REPO_ROOT / "voice" / cand).exists():
                resolved = (REPO_ROOT / "voice" / cand).resolve()
            elif work_dir and (work_dir / cand).exists():
                resolved = (work_dir / cand).resolve()
        else:
            if cand.exists():
                resolved = cand.resolve()

        if resolved is None:
            available = [p.name for p in sorted(sample_dir.glob("*.wav"))] if sample_dir.exists() else []
            opts_msg = f"Dostępne próbki w work/voice_sample/: {available}" if available else "Katalog work/voice_sample/ jest pusty."
            raise FileNotFoundError(
                f"Błąd: Nie znaleziono próbki referencyjnej głosu '{ref_audio}'. Nagraj 10s audio i umieść w voice/ lub ustaw VOICE_REF_FILE w .env.\n{opts_msg}"
            )
        resolved_path = resolved
    else:
        if not sample_dir.exists():
            sample_dir.mkdir(parents=True, exist_ok=True)
        available = sorted([
            p for p in sample_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".wav", ".mp3", ".flac"}
        ])

        if len(available) == 1:
            resolved_path = available[0].resolve()
            log_info(f"Wykryto pojedynczą próbkę lektorską w work/voice_sample/: {resolved_path.name} (użycie jako domyślnej)")
        elif len(available) > 1:
            opts = [p.name for p in available]
            raise ValueError(
                f"W katalogu work/voice_sample/ wykryto wiele próbek: {opts}.\n"
                f"Wymagane jest wskazanie konkretnego pliku za pomocą parametru --voice-ref <plik> "
                f"lub zmiennej środowiskowej VOICE_REF_FILE."
            )
        elif (REPO_ROOT / "voice" / "sample_reference.wav").exists():
            resolved_path = (REPO_ROOT / "voice" / "sample_reference.wav").resolve()
            log_info(f"Użycie domyślnej próbki referencyjnej: {resolved_path.name}")
        else:
            raise FileNotFoundError(
                "Błąd: Nie znaleziono próbki referencyjnej głosu. Nagraj 10s audio i umieść w voice/ lub ustaw VOICE_REF_FILE w .env."
            )

    if resolved_path and not ref_transcript:
        txt_cand = resolved_path.with_suffix(".txt")
        if txt_cand.exists():
            ref_transcript = txt_cand.read_text(encoding="utf-8").strip()

    return resolved_path, ref_transcript


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
        text = strip_voice_tags(clean_voiceover_text(sc.get(lang_key, "")))
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
                scene["pacing_status"] = f"x{speed_factor:.2f} (Kompresja)"
                log_info(f"Dopasowanie tempa (kompresja) dla sceny {scene['id']}: x{speed_factor:.2f} ({seg_dur:.2f}s -> {seg_dur/speed_factor:.2f}s, okno: {avail_window:.2f}s)")
            elif (avail_window - seg_dur) > desired_pause + 0.4:
                # Nadmiarowa martwa cisza — subtelna relaksacja tempa mowy (bezpieczny zakres [0.92, 0.98])
                # Używamy transparentnego filtru atempo (WSOLA w dziedzinie czasu) eliminującego metaliczny pogłos i drżenie
                raw_speed = seg_dur / target_dur
                speed_factor = max(0.92, min(0.98, raw_speed))
                adj_dur = seg_dur / speed_factor
                actual_gap = avail_window - adj_dur
                scene["pacing_status"] = f"x{speed_factor:.2f} (Spokojne)"
                log_info(f"Dopasowanie tempa (relaksacja ciszy) dla sceny {scene['id']}: x{speed_factor:.2f} ({seg_dur:.2f}s -> {adj_dur:.2f}s, luka: {actual_gap:.2f}s, orig_gap: {orig_pause:.2f}s)")
            else:
                speed_factor = 1.0
                scene["pacing_status"] = "1.00x (Płynne)"

            adj_dur = seg_dur / speed_factor
            cmd = ["ffmpeg", "-y", "-i", str(seg_wav)]
            if abs(speed_factor - 1.0) > 0.005:
                cmd.extend(["-filter:a", f"atempo={speed_factor:.3f}"])
            cmd.extend(["-ar", "48000", "-ac", "1", str(out_seg)])
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

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
            filter_complex.append("[vo_raw][roomtone]amix=inputs=2:dropout_transition=0:normalize=0[mixed]")
        else:
            filter_complex.append("[vo_raw]acopy[mixed]")

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
    max_pacing_retries: int = DEFAULT_MAX_PACING_RETRIES,
    expressive: bool = False,
    output_dir: Path | None = None,
) -> bool:
    work_dir = work_dir.resolve()
    short_id = work_dir.name

    # Inicjalizacja menedżera przebiegu (WorkRunManager)
    run_mgr = WorkRunManager(
        task_slug=short_id,
        engine=engine,
        explicit_output_dir=output_dir,
    )

    with run_mgr.capture_logs():
        if not input_video:
            input_video = auto_detect_input_video(work_dir)

        if not input_video or not input_video.exists():
            log_err(f"Nie znaleziono wideo źródłowego w {work_dir}/input/")
            run_mgr.finish_run()
            return False

        total_duration = get_audio_duration(input_video)

        log_info("=" * 65)
        log_info(f" Workstation Hub: Autonomiczny Potok Dubbingu dla {short_id}")
        log_info("=" * 65)
        log_info(f"Wideo wejściowe:  {input_video.name} ({total_duration:.2f}s)")
        log_info(f"Katalog projektu: {work_dir}")
        log_info(f"Katalog runu:     {run_mgr.run_dir}")
        log_info(f"Silnik TTS:       {engine.upper()}")

        # Walidacja i automatyczna detekcja próbki referencyjnej głosu
        if not transcribe_only and engine != "edge":
            ref_audio, ref_transcript = resolve_reference_audio(ref_audio, work_dir=work_dir, ref_transcript=ref_transcript)
            if ref_audio:
                log_info(f"Próbka głosu:     {ref_audio.name} ({'z transkrypcją' if ref_transcript else 'bez transkrypcji'})")

        # 1. Ekstrakcja czystego audio ze źródła lub dedykowany plik lektorski
        raw_audio = run_mgr.source_extracted_dir / f"{short_id}_VoiceOver_RAW_24k.wav"
        input_voiceover = None
        input_dir = work_dir / "input"
        if input_dir.exists():
            for vo_cand in sorted(input_dir.glob("*.wav")):
                if "voiceover" in vo_cand.name.lower() or "clean" in vo_cand.name.lower():
                    input_voiceover = vo_cand
                    break

        with run_mgr.measure_stage("source_extraction"):
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

        with run_mgr.measure_stage("transcription"):
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
            run_mgr.finish_run()
            return False

        # 3. Dynamiczne tłumaczenie maszynowe (Bielik LLM / MarianMT + Tech Terms) z walidacją budżetu czasu
        with run_mgr.measure_stage("llm_adaptation"):
            translate_scenes_batch(scenes, translator=translator, llm_model=llm_model, max_pacing_retries=max_pacing_retries)

        transcript_json = run_mgr.llm_adaptation_dir / f"{short_id}_Dubbing_Transcript_EN.json"
        with open(transcript_json, "w", encoding="utf-8") as f:
            json.dump(scenes, f, ensure_ascii=False, indent=2)
        log_ok(f"Zapisano transkrypcję segmentów: {transcript_json.name}")

        srt_pl_file = run_mgr.subtitles_dir / f"{short_id}_PL.srt"
        srt_en_file = run_mgr.subtitles_dir / f"{short_id}_EN.srt"
        export_srt(scenes, srt_pl_file, lang_key="text_pl")
        export_srt(scenes, srt_en_file, lang_key="text_en")
        log_ok(f"Wygenerowano napisy SRT: {srt_pl_file.name} oraz {srt_en_file.name}")

        if transcribe_only:
            run_mgr.record_stats(
                scenes_count=len(scenes),
                total_duration_sec=round(total_duration, 2),
                transcribe_only=True,
            )
            summary_json = run_mgr.finish_run()
            log_ok(f"Zapisano raport przebiegu: {summary_json.name}")
            log_ok(f"Tryb --transcribe-only zakończony dla {short_id}.")
            return True

        # 4. Inicjalizacja wybranego silnika syntezy (Qwen3-TTS / Chatterbox / KokoClone / Breeze / Edge)
        dub_parts_dir = run_mgr.tts_segments_dir
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

        llm_director_client = None
        if expressive and (supports_voice_tags(selected_engine) or selected_engine == "qwen"):
            target_llm = "SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M" if llm_model in ("auto", "bielik") else llm_model
            candidate_llm = OllamaTranslator(model_name=target_llm)
            if candidate_llm.is_available():
                llm_director_client = candidate_llm
                if selected_engine == "qwen":
                    log_info(f"Reżyser tekstu: Włączono Acting Direction (Instruct TTS) ({selected_engine.upper()}, model: {target_llm}).")
                else:
                    log_info(f"Reżyser tekstu: Włączono wzbogacanie Two-Pass TTS Voice Tags ({selected_engine.upper()}, model: {target_llm}).")
            else:
                log_warn("Ollama nie jest dostępna dla Reżysera tekstu. Użycie standardowej ekspresji / czystego tekstu.")

        log_info(f"Generowanie mowy dla poszczególnych scen (silnik: {selected_engine.upper()})...")
        with run_mgr.measure_stage("tts_generation"):
            acting_directions_log: dict[str, Any] = {}
            for sc in scenes:
                clean_vo = clean_voiceover_text(sc.get("text_en", ""))
                active_instruction = instruction

                if selected_engine == "qwen":
                    if expressive and llm_director_client:
                        clean_vo, acting_instruction = direct_voiceover(clean_vo, client_llm=llm_director_client)
                        if acting_instruction:
                            active_instruction = acting_instruction
                    else:
                        clean_vo = strip_voice_tags(clean_vo)
                    directed_vo = clean_vo
                    sc["acting_instruction"] = active_instruction
                    acting_directions_log[f"scene_{sc['id']:03d}"] = {
                        "text": clean_vo,
                        "instruction": active_instruction,
                    }
                elif expressive and supports_voice_tags(selected_engine) and llm_director_client:
                    directed_vo = enrich_voiceover_tags(clean_vo, selected_engine, client_llm=llm_director_client)
                else:
                    directed_vo = strip_voice_tags(clean_vo)

                # Do napisów (.srt / .ass), transcript JSON i raportów ZAWSZE trafia tekst oczyszczony ze znaczników!
                sc["text_en"] = strip_voice_tags(directed_vo)
                sc["text_en_directed"] = directed_vo

                part_wav = dub_parts_dir / f"scene_{sc['id']:03d}.wav"
                txt_marker = part_wav.with_suffix(".txt")
                engine_marker = part_wav.with_suffix(".engine")
                expected_engine = selected_engine

                # Inteligentne wznawianie: użyj istniejącego pliku tylko jeśli tekst do syntezy jest identyczny ORAZ silnik jest zgodny
                if (
                    part_wav.exists()
                    and part_wav.stat().st_size > 1000
                    and txt_marker.exists()
                    and txt_marker.read_text(encoding="utf-8").strip() == directed_vo.strip()
                    and (not engine_marker.exists() or engine_marker.read_text(encoding="utf-8").strip() == expected_engine)
                ):
                    segment_wavs.append(part_wav)
                    continue

                log_info(f"{selected_engine.upper()}: Synteza sceny {sc['id']}: '{directed_vo[:42]}...'")
                synth_ok = active_engine_instance.synthesize(
                    text=directed_vo,
                    out_wav=part_wav,
                    ref_audio=ref_audio,
                    ref_transcript=ref_transcript,
                    instruction=active_instruction,
                )

                if not synth_ok:
                    if selected_engine != "edge" and engine != "auto":
                        log_err(f"Błąd syntezy sceny {sc['id']} przez wymuszony silnik {selected_engine}.")
                        run_mgr.finish_run()
                        return False
                    voice_to_use = edge_voice or "en-US-ChristopherNeural"
                    log_info(f"Edge-TTS Fallback: Synteza sceny {sc['id']}: '{directed_vo[:42]}...' (voice: {voice_to_use})")
                    fallback_engine = get_tts_engine("edge", voice=voice_to_use)
                    synth_ok = fallback_engine.synthesize(text=directed_vo, out_wav=part_wav)
                    active_engine_name = f"Edge-TTS ({voice_to_use})"
                    if synth_ok:
                        engine_marker.write_text("edge\n", encoding="utf-8")
                else:
                    engine_marker.write_text(f"{selected_engine}\n", encoding="utf-8")

                if part_wav.exists() and part_wav.stat().st_size > 1000:
                    txt_marker.write_text(directed_vo.strip() + "\n", encoding="utf-8")
                segment_wavs.append(part_wav)

            if acting_directions_log:
                directions_file = run_mgr.llm_adaptation_dir / f"{short_id}_Acting_Directions.json"
                directions_file.write_text(
                    json.dumps(acting_directions_log, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                log_ok(f"Zapisano instrukcje reżyserskie TTS: {directions_file.name}")
                run_mgr.record_stats(acting_directions_count=len(acting_directions_log))

        if llm_director_client is not None:
            llm_director_client.unload()

        # 5. Time-sync i mastering EBU R128
        mastered_wav = run_mgr.output_dir / f"{short_id}_VoiceOver_EN_CLEAN.wav"
        with run_mgr.measure_stage("audio_mastering"):
            time_sync_and_master(scenes, segment_wavs, total_duration, mastered_wav, target_lufs=-14.0, target_tp=-1.0)

        # Deliverables w 06_output: zaktualizowane napisy SRT i transkrypcja
        out_srt_en = run_mgr.output_dir / f"{short_id}_EN.srt"
        out_srt_pl = run_mgr.output_dir / f"{short_id}_PL.srt"
        out_transcript_json = run_mgr.output_dir / f"{short_id}_Dubbing_Transcript_EN.json"

        export_srt(scenes, out_srt_en, lang_key="text_en", use_synced=True)
        export_srt(scenes, out_srt_pl, lang_key="text_pl")
        export_srt(scenes, srt_en_file, lang_key="text_en", use_synced=True)
        with open(out_transcript_json, "w", encoding="utf-8") as f:
            json.dump(scenes, f, ensure_ascii=False, indent=2)

        # 6. Finalny montaż wideo EN
        output_video_file = None
        if output_video:
            output_video_file = run_mgr.output_dir / f"{short_id}_FINAL_EN_DUBBED.mp4"
            log_info(f"Generowanie filmu z angielską ścieżką dźwiękową: {output_video_file.name}...")
            with run_mgr.measure_stage("video_muxing"):
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

        # 7. Automatyczna analiza jakości efektu końcowego (QualityAnalyzer)
        full_vo_text = " ".join(sc.get("text_en", "") for sc in scenes)
        quality = run_mgr.quality_analyzer.analyze_output(
            audio_path=mastered_wav,
            target_speech_window=total_duration,
            voiceover_text=full_vo_text,
            video_path=output_video_file if output_video else None,
        )

        # Raport Markdown
        summary_md = run_mgr.output_dir / f"{short_id}_Dubbing_Summary.md"
        with open(summary_md, "w", encoding="utf-8") as f:
            f.write(f"# Raport Dubbingu AI: {short_id}\n\n")
            f.write(f"- **Wideo źródłowe:** `{input_video.name}` ({total_duration:.2f}s)\n")
            f.write(f"- **Silnik syntezy:** `{active_engine_name}`\n")
            f.write("- **Standard emisyjny audio:** `EBU R128 (-14.0 LUFS, True Peak <= -1.0 dBFS)`\n\n")
            f.write("## Audyt Jakościowy (Quality Metrics)\n\n")
            f.write(f"- **Status ogólny:** `{quality.overall_quality_status}`\n")
            f.write(f"- **Tempo mowy (WPM):** `{quality.wpm}` (ostrzeżenie: `{quality.pacing_warning}`)\n")
            f.write(f"- **Dryf czasu:** `{quality.drift_seconds:.2f}s` (okno mowy: `{quality.target_window_sec:.2f}s`)\n")
            f.write(f"- **Poziom szczytowy (Peak):** `{quality.peak_db} dB` (przesterowanie: `{quality.is_clipping}`)\n")
            f.write(f"- **Głośność RMS:** `{quality.rms_db} dB`\n")
            f.write(f"- **Maksymalna pauza w mowie:** `{quality.max_internal_silence_sec:.2f}s` (nienaturalna cisza: `{quality.unnatural_silence_detected}`)\n\n")
            f.write("## Wygenerowane Pliki Produkcyjne (Deliverables)\n\n")
            f.write("1. **Plik dźwiękowy lektora (YouTube Multi-Language Audio):**\n")
            f.write(f"   `{mastered_wav.name}` (WAV 48kHz stereo, -14.0 LUFS — do wrzucenia w YouTube Studio jako alternatywna ścieżka językowa).\n\n")
            if output_video and output_video_file:
                f.write("2. **Zdubbingowany film EN (Full Video + Dubbing):**\n")
                f.write(f"   `{output_video_file.name}` (wideo + zsynchronizowany dubbing EN).\n\n")
            f.write(f"3. **Napisy w języku angielskim:** `{out_srt_en.name}`\n")
            f.write(f"4. **Napisy w języku polskim:** `{out_srt_pl.name}`\n\n")
            f.write("## Tabela Zsynchronizowanych Scen\n\n")
            f.write("| Scena | Zakres czasu | Pacing / Status | Kalibracja Bielik | Pauza po scenie | Oryginał PL | Kwestia EN |\n")
            f.write("| :---: | :---: | :---: | :---: | :---: | :--- | :--- |\n")
            for sc in scenes:
                start_t = sc.get("start_synced", sc["start"])
                end_t = sc.get("end_synced", sc["end"])
                pacing = sc.get("pacing_status", "1.00x (Płynne)")
                calib = sc.get("calibration_status", "1 próba (Idealnie)")
                pause_str = sc.get("post_pause_str", "-")
                f.write(f"| {sc['id']} | `{start_t:.2f}s - {end_t:.2f}s` | `{pacing}` | `{calib}` | `{pause_str}` | {sc['text_pl']} | **{sc['text_en']}** |\n")

        run_mgr.record_stats(
            scenes_count=len(scenes),
            total_duration_sec=round(total_duration, 2),
            words_count=quality.word_count,
            active_engine=active_engine_name,
            expressive=expressive,
        )
        summary_json = run_mgr.finish_run(quality_analysis=quality)

        log_ok(f"Zapisano raport podsumowujący: {summary_md.name}")
        log_ok(f"Zapisano metadane i audyt przebiegu: {summary_json.name}")
        log_info(f"Katalog przebiegu (Run Workspace): {run_mgr.run_dir}")
        log_info("=" * 65)
        log_ok(f"PROCES ZAKOŃCZONY SUKCESEM DLA {short_id}!")
        log_info("Dostarczone pliki produkcyjne (Deliverables):")
        log_info(f"  1. [YouTube Audio Track]: {mastered_wav.name}")
        if output_video and output_video_file:
            log_info(f"  2. [Full Dubbed Video]:   {output_video_file.name}")
        log_info(f"  3. [English Subtitles]:   {out_srt_en.name}")
        log_info(f"  4. [Polish Subtitles]:    {out_srt_pl.name}")
        log_info(f"  5. [Run Summary JSON]:    {summary_json.name}")
        log_info("  6. [Execution Log]:       logs/execution.log")
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
    parser.add_argument("-o", "--output-dir", type=Path, default=None, help="Jawnie wskazany katalog wyjściowy (jeśli nie podano, tworzy wersjonowany katalog w work/runs/)")
    parser.add_argument("-s", "--script", type=Path, default=None, help="Opcjonalny plik scenariusza (MD lub SRT)")
    parser.add_argument("--batch", nargs="+", help="Lista katalogów projektów do przetworzenia wsadowego")

    # Próbka głosu
    parser.add_argument("--voice-ref", "--ref-audio", dest="voice_ref", type=Path, default=None, help="Ścieżka do próbki referencyjnej WAV (domyślnie z work/voice_sample/)")
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
    parser.add_argument("--max-pacing-retries", type=int, default=DEFAULT_MAX_PACING_RETRIES, help="Maksymalna liczba iteracji rekalibracji długości tekstu przez Bielika (domyślnie: 10)")
    parser.add_argument("--expressive", action="store_true", default=False, help="Włącz dwufazowe wzbogacanie tekstu o znaczniki emocji/dynamiki (Two-Pass TTS Voice Tags)")
    args = parser.parse_args()

    # Wybór presetów akcentu i głosu
    accent_cfg = ACCENT_PRESETS.get(args.accent, ACCENT_PRESETS["default"])
    active_instruction = args.instruction
    if active_instruction == parser.get_default("instruction") and args.accent != "default":
        active_instruction = accent_cfg["instruction"]
    active_edge_voice = args.edge_voice or accent_cfg["edge_voice"]

    # Wycięcie próbki referencyjnej w locie jeśli wskazano --ref-source
    ref_audio = args.voice_ref
    ref_transcript = args.ref_transcript
    if args.ref_source and args.ref_source.exists():
        sample_out = REPO_ROOT / "work" / "voice_sample" / "ref_voice_sample.wav"
        extract_voice_sample_clip(args.ref_source, args.ref_start, args.ref_end, sample_out, ref_transcript)
        ref_audio = sample_out

    try:
        ref_audio, ref_transcript = resolve_reference_audio(ref_audio, work_dir=args.work_dir, ref_transcript=ref_transcript)
    except (FileNotFoundError, ValueError):
        print(
            "Błąd: Nie znaleziono próbki referencyjnej głosu. Nagraj 10s audio i umieść w voice/ lub ustaw VOICE_REF_FILE w .env.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Leniwa inicjalizacja modeli (GPU VRAM jest zwalniane sekwencyjnie)
    shared_translator = None
    shared_tts_engine = None

    # Tryb wsadowy
    if args.batch:
        log_info(f"Uruchamianie przetwarzania zestawu wideo ({len(args.batch)} projektów)...")
        for b_dir in args.batch:
            target_dir = Path(b_dir)
            target_out = (args.output_dir / target_dir.name) if (args.output_dir and len(args.batch) > 1) else args.output_dir
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
                max_pacing_retries=args.max_pacing_retries,
                expressive=args.expressive,
                output_dir=target_out,
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
        max_pacing_retries=args.max_pacing_retries,
        expressive=args.expressive,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
