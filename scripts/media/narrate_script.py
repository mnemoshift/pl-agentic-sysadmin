#!/usr/bin/env python3
"""
Workstation Hub: Autonomiczny moduł narracji ze skryptu Markdown (Standalone Script Narrator).
Generuje pełne nagranie lektorskie (voice-over) bezpośrednio z pliku Markdown (.md)
w dowolnym języku (np. polskim, angielskim), z wykorzystaniem klonowania głosu (voice cloning)
oraz automatyczną synchronizacją napisów SRT i masteringiem emisyjnym EBU R128 (-14 LUFS).

Cechy:
1. ScriptChunker: Oczyszczanie składni Markdown i semantyczny podział na zdania/akapity (150-300 znaków)
   z pełnym zabezpieczeniem skrótów (np., tzn., m.in., 3.14).
2. Obsługa silników TTS: kokoclone, edge, qwen, chatterbox, breeze.
3. Wstrzykiwanie naturalnych przerw (pauzy międzyzdaniowe i międzyakapitowe).
4. Generowanie w 100% zsynchronizowanych napisów SRT na bazie rzeczywistych długości audio chunków.
5. Pełna integracja z WorkRunManager, QualityAnalyzer i rejestrem work/runs/.
"""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# ==============================================================================
# 0. SELF-BOOTSTRAPPING: Automatyczne przełączanie na środowisko .venv repozytorium
# ==============================================================================
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

if __name__ == "__main__" and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    if VENV_PYTHON.exists() and os.access(str(VENV_PYTHON), os.X_OK):
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from text_director import (  # noqa: E402
    clean_voiceover_text,
    enrich_voiceover_tags,
    strip_voice_tags,
    supports_voice_tags,
)
from tts_engines import (  # noqa: E402
    get_tts_engine,
)
from work_manager import WorkRunManager  # noqa: E402


def log_info(msg: str) -> None:
    print(f"\033[1;34m[INFO]\033[0m {msg}")


def log_ok(msg: str) -> None:
    print(f"\033[1;32m[OK]\033[0m {msg}")


def log_warn(msg: str) -> None:
    print(f"\033[1;33m[WARN]\033[0m {msg}")


def log_err(msg: str) -> None:
    print(f"\033[1;31m[ERROR]\033[0m {msg}", file=sys.stderr)


# ==============================================================================
# 1. MODEL DANYCH I PARSER SKRYPTU (ScriptChunker)
# ==============================================================================
@dataclass(frozen=True, slots=True)
class ScriptChunk:
    index: int
    text: str
    is_paragraph_end: bool
    heading: str = ""
    raw_text: str = ""


class ScriptChunker:
    """
    Parser i semantyczny segmentator tekstu Markdown pod kątem syntezy mowy TTS:
    - Oczyszcza składnię wizualną Markdown (linki, kody blokowe, grafiki, pogrubienia).
    - Zamienia nagłówki na normalne zdania i oznacza je jako granice bloków (pauza akapitowa).
    - Dzieli tekst na zdania z zabezpieczeniem skrótów i liczb dziesiętnych.
    - Dzieli zbyt długie zdania (>350 znaków) na naturalnych przecinkach lub spójnikach.
    """

    PROTECTED_ABBREVIATIONS: tuple[str, ...] = (
        # Język polski
        r"np\.",
        r"tzn\.",
        r"m\.in\.",
        r"itd\.",
        r"itp\.",
        r"tzw\.",
        r"ok\.",
        r"prof\.",
        r"dr\.",
        r"doc\.",
        r"art\.",
        r"ust\.",
        r"pkt\.",
        r"ul\.",
        r"al\.",
        r"\b\d+\s*r\.",
        # Język angielski
        r"e\.g\.",
        r"i\.e\.",
        r"etc\.",
        r"mr\.",
        r"mrs\.",
        r"ms\.",
        r"vs\.",
        r"inc\.",
        r"ltd\.",
        r"co\.",
        r"corp\.",
        r"approx\.",
        r"no\.",
        r"vol\.",
    )

    def __init__(self, max_sentence_len: int = 350, target_chunk_min: int = 150):
        self.max_sentence_len = max_sentence_len
        self.target_chunk_min = target_chunk_min

    @staticmethod
    def clean_markdown_text(raw_text: str) -> str:
        """
        Usuwa formatowanie Markdown, zachowując czysty tekst do odczytania:
        - Obrazy: ![alt](url) -> usunięcie
        - Linki: [tekst](url) -> tekst
        - Kody blokowe: ```...``` -> usunięcie
        - Kody inline: `kod` -> kod
        - Pogrubienia i kursywy: **tekst**, *tekst*, __tekst__, _tekst_ -> tekst
        - Cytaty: > tekst -> tekst
        - Poziome linie: ---, ===, *** -> usunięcie
        - Tagi HTML: <...> -> usunięcie
        """
        if not raw_text:
            return ""

        text = raw_text

        # 1. Usunięcie bloków kodu ```...```
        text = re.sub(r"```[a-zA-Z0-9_\-]*\n.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)

        # 2. Usunięcie obrazków ![alt](url)
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)

        # 3. Zastąpienie linków [tekst](url) samym tekstem
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

        # 4. Usunięcie kodów w backtickach `kod`
        text = re.sub(r"`([^`]+)`", r"\1", text)

        # 5. Usunięcie pogrubień i kursyw
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)

        # 6. Usunięcie znaczników cytatów blokowych na początku linii (> ...)
        text = re.sub(r"^\s*>\s*", "", text, flags=re.MULTILINE)

        # 7. Usunięcie poziomych linii oddzielających
        text = re.sub(r"^\s*[-=_*]{3,}\s*$", "", text, flags=re.MULTILINE)

        # 8. Usunięcie znaczników HTML
        text = re.sub(r"<[^>]+>", "", text)

        # 9. Zamiana myślników i pauz na naturalne przecinki
        text = re.sub(r"\s*[–—]\s*", ", ", text)

        # 10. Usunięcie zbędnych cudzysłowów
        text = text.strip(' "”„\'`')

        return text.strip()

    def split_into_sentences(self, text: str) -> list[str]:
        """
        Dzieli ciągły tekst na zdania z zabezpieczeniem skrótów,
        liczb dziesiętnych oraz wielokropków.
        """
        if not text:
            return []

        working_text = text

        # 1. Zabezpieczenie liczb dziesiętnych (np. 3.14 -> 3__DEC_DOT__14)
        working_text = re.sub(r"(?<=\d)\.(?=\d)", "__DEC_DOT__", working_text)

        # 2. Zabezpieczenie wielokropków (...)
        working_text = re.sub(r"\.{3,}", "__ELLIPSIS__", working_text)

        # 3. Zabezpieczenie skrótów
        for abbr_pattern in self.PROTECTED_ABBREVIATIONS:
            def _replace_dots(match: re.Match) -> str:
                return match.group(0).replace(".", "__ABBR_DOT__")

            working_text = re.sub(abbr_pattern, _replace_dots, working_text, flags=re.IGNORECASE)

        # 4. Podział na zdania na podstawie interpunkcji końcowej [.?!;]
        raw_parts = re.split(r"(?<=[.?!;])\s+(?=[A-Z0-9ĄĆĘŁŃÓŚŹŻ\"\'\u201e\u201c])", working_text)
        if len(raw_parts) <= 1:
            raw_parts = re.split(r"(?<=[.?!;])\s+", working_text)

        sentences = []
        for part in raw_parts:
            # Przywrócenie zabezpieczonych tokenów
            restored = (
                part.replace("__DEC_DOT__", ".")
                .replace("__ELLIPSIS__", "...")
                .replace("__ABBR_DOT__", ".")
                .strip()
            )
            # Usunięcie wielokrotnych spacji
            restored = re.sub(r"\s+", " ", restored).strip()
            if restored:
                sentences.append(restored)

        return sentences

    def split_long_sentence(self, sentence: str) -> list[str]:
        """
        Jeśli pojedyncze zdanie przekracza max_sentence_len (350 znaków),
        dzieli je bezpiecznie na przecinkach lub spójnikach, celując w fragmenty 150-300 znaków.
        """
        sentence = sentence.strip()
        if len(sentence) <= self.max_sentence_len:
            return [sentence]

        chunks = []
        current = sentence
        while len(current) > self.max_sentence_len:
            candidate_window = current[: self.max_sentence_len]
            split_pos = -1

            # 1. Poszukiwanie przecinka w oknie
            for m in re.finditer(r",\s+", candidate_window):
                if m.end() >= self.target_chunk_min:
                    split_pos = m.end()

            # 2. Jeśli brak odpowiedniego przecinka, poszukiwanie spójnika
            if split_pos == -1:
                conjunction_pattern = (
                    r"\s+(?:i|oraz|ale|lecz|a|ponieważ|dlatego|bo|czyli|gdy|kiedy|"
                    r"and|but|or|so|because|which|that|while)\s+"
                )
                for m in re.finditer(conjunction_pattern, candidate_window, re.IGNORECASE):
                    if m.start() >= self.target_chunk_min:
                        split_pos = m.start()

            # 3. Fallback: najbliższa spacja
            if split_pos == -1:
                space_pos = candidate_window.rfind(" ")
                if space_pos >= self.target_chunk_min:
                    split_pos = space_pos + 1
                else:
                    split_pos = self.max_sentence_len

            chunk = current[:split_pos].strip()
            if chunk:
                chunks.append(chunk)
            current = current[split_pos:].strip()

        if current:
            chunks.append(current)

        return chunks

    def parse(self, markdown_content: str) -> list[ScriptChunk]:
        """
        Główna metoda segmentacji:
        1. Rozbija Markdown na linie, identyfikując nagłówki i bloki akapitów.
        2. Czyści treść i zamienia nagłówki na zdania kończące się kropką.
        3. Dzieli na zdania, obsługuje długie zdania i oznacza is_paragraph_end.
        """
        lines = markdown_content.splitlines()
        chunks: list[ScriptChunk] = []
        chunk_idx = 1

        blocks: list[tuple[str, bool]] = []
        current_paragraph_lines: list[str] = []

        for line in lines:
            stripped = line.strip()

            # Pusta linia oznacza koniec akapitu
            if not stripped:
                if current_paragraph_lines:
                    blocks.append(("\n".join(current_paragraph_lines), False))
                    current_paragraph_lines = []
                continue

            # Rozpoznanie nagłówka (#, ##, ### itp.)
            header_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if header_match:
                if current_paragraph_lines:
                    blocks.append(("\n".join(current_paragraph_lines), False))
                    current_paragraph_lines = []

                header_text = header_match.group(2).strip()
                blocks.append((header_text, True))
                continue

            current_paragraph_lines.append(stripped)

        if current_paragraph_lines:
            blocks.append(("\n".join(current_paragraph_lines), False))

        # Przetwarzanie bloków na gotowe chunki
        for block_text, is_heading in blocks:
            cleaned_block = self.clean_markdown_text(block_text)
            if not cleaned_block:
                continue

            if is_heading:
                # Nagłówek traktujemy jako pojedynczy, zamknięty blok zdaniowy
                heading_sentence = cleaned_block
                if not re.search(r"[.?!;:]$", heading_sentence):
                    heading_sentence += "."

                sub_chunks = self.split_long_sentence(heading_sentence)
                for idx_sub, sub_text in enumerate(sub_chunks):
                    is_last = idx_sub == len(sub_chunks) - 1
                    chunks.append(
                        ScriptChunk(
                            index=chunk_idx,
                            text=sub_text,
                            is_paragraph_end=is_last,
                            heading=cleaned_block,
                            raw_text=block_text,
                        )
                    )
                    chunk_idx += 1
            else:
                # Normalny akapit: podział na zdania
                sentences = self.split_into_sentences(cleaned_block)
                if not sentences:
                    continue

                for s_idx, sentence in enumerate(sentences):
                    is_last_sentence = s_idx == len(sentences) - 1
                    sub_chunks = self.split_long_sentence(sentence)
                    for idx_sub, sub_text in enumerate(sub_chunks):
                        is_last_sub = idx_sub == len(sub_chunks) - 1
                        is_para_end = is_last_sentence and is_last_sub
                        chunks.append(
                            ScriptChunk(
                                index=chunk_idx,
                                text=sub_text,
                                is_paragraph_end=is_para_end,
                                raw_text=sentence,
                            )
                        )
                        chunk_idx += 1

        return chunks


# ==============================================================================
# 2. POMOCNICZE AUDIO DSP I NAPISY SRT
# ==============================================================================
def sec_to_srt_time(sec: float) -> str:
    """Konwertuje sekundy na standardowy format timecodu SRT: HH:MM:SS,mmm."""
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
    """Pobiera dokładny czas trwania pliku audio w sekundach."""
    try:
        info = sf.info(str(file_path))
        return float(info.duration)
    except Exception:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return float(res.stdout.strip())
        except Exception:
            return 0.0


def create_silence_wav(out_wav: Path, duration_sec: float, sample_rate: int = 24000) -> None:
    """Generuje czysty plik ciszy WAV o zadanej długości."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    num_samples = max(1, int(sample_rate * duration_sec))
    silence = np.zeros(num_samples, dtype=np.float32)
    sf.write(str(out_wav), silence, sample_rate)


def generate_srt_content(
    chunks: list[ScriptChunk],
    durations: list[float],
    pauses: list[float],
) -> str:
    """
    Generuje zsynchronizowaną treść napisów SRT na bazie rzeczywistych
    czasów trwania chunków audio i przerw między nimi.
    """
    srt_lines: list[str] = []
    current_time = 0.0
    srt_idx = 1

    for i, (chunk, dur) in enumerate(zip(chunks, durations, strict=False)):
        start_t = current_time
        end_t = current_time + dur
        current_time = end_t

        clean_text = strip_voice_tags(clean_voiceover_text(chunk.text))
        srt_lines.append(
            f"{srt_idx}\n{sec_to_srt_time(start_t)} --> {sec_to_srt_time(end_t)}\n{clean_text}\n"
        )
        srt_idx += 1

        if i < len(pauses):
            current_time += pauses[i]

    return "\n".join(srt_lines) + "\n"


def concatenate_and_master_narration(
    audio_paths: list[Path],
    output_wav: Path,
    target_lufs: float = -14.0,
    target_tp: float = -1.0,
) -> None:
    """
    Łączy segmenty audio w jeden spójny plik i aplikuje mastering emisyjny
    EBU R128 (-14.0 LUFS, True Peak <= -1.0 dBFS, 48kHz stereo).
    """
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    concat_list_file = output_wav.with_suffix(".concat.txt")

    with open(concat_list_file, "w", encoding="utf-8") as f:
        for p in audio_paths:
            f.write(f"file '{p.resolve()}'\n")

    temp_concat = output_wav.with_suffix(".temp_concat.wav")

    try:
        # Krok 1: Bezstratne złączenie
        cmd_concat = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_file),
            "-c",
            "copy",
            str(temp_concat),
        ]
        res = subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            # Jeśli copy nie pasuje (np. różne nagłówki WAV), wykonaj resamplowane łączenie
            cmd_reencode = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list_file),
                "-ar",
                "24000",
                "-ac",
                "1",
                str(temp_concat),
            ]
            subprocess.run(cmd_reencode, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)

        # Krok 2: Mastering broadcastowy EBU R128 (-14 LUFS, Broadcast EQ)
        audio_filter = (
            "highpass=f=80,"
            "equalizer=f=200:width_type=q:width=1.0:g=1.5,"
            "equalizer=f=3000:width_type=q:width=1.2:g=1.5,"
            "equalizer=f=4500:width_type=q:width=1.5:g=-2.0,"
            "compand=attacks=0.02:decays=0.2:points=-80/-80|-40/-30|-20/-10|-10/-4|0/0:soft-knee=0.01,"
            f"loudnorm=I={target_lufs}:TP={target_tp}:LRA=9.0"
        )
        cmd_master = [
            "ffmpeg",
            "-y",
            "-i",
            str(temp_concat),
            "-af",
            audio_filter,
            "-ar",
            "48000",
            "-ac",
            "2",
            str(output_wav),
        ]
        res_master = subprocess.run(cmd_master, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if res_master.returncode != 0:
            # Fallback w przypadku błędu filtra loudnorm na bardzo krótkim materiale
            cmd_fallback = [
                "ffmpeg",
                "-y",
                "-i",
                str(temp_concat),
                "-ar",
                "48000",
                "-ac",
                "2",
                str(output_wav),
            ]
            subprocess.run(cmd_fallback, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    finally:
        concat_list_file.unlink(missing_ok=True)
        temp_concat.unlink(missing_ok=True)


def normalize_language_code(lang: str | None) -> str:
    """Normalizuje kody języka (np. en_US.UTF-8 -> en, pl-PL -> pl, auto -> auto)."""
    if not lang:
        return "auto"
    s = lang.strip().lower()
    if s in ("auto", "default", "c", "posix"):
        return "auto"
    # Odrzucenie specyfikatorów kodowania .utf-8 oraz dialektów _pl / _us
    base = s.split(".")[0].replace("-", "_").split("_")[0]
    return base or "auto"


def detect_script_language(text: str) -> str:
    """Wykrywa dominujący język skryptu (domyślnie 'pl' lub 'en')."""
    pl_chars = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
    if any(c in pl_chars for c in text):
        return "pl"
    pl_words = {"i", "w", "z", "do", "na", "nie", "się", "to", "jest", "jak", "oraz", "dla", "że"}
    words = {w.lower() for w in re.findall(r"\b\w+\b", text)}
    if len(words.intersection(pl_words)) >= 2:
        return "pl"
    return "en"


def resolve_voice_sample(ref_audio: Path | str | None) -> Path | None:
    """Rozwiązuje ścieżkę do pliku referencyjnego głosu."""
    if ref_audio:
        cand = Path(ref_audio)
        if cand.is_absolute() and cand.exists():
            return cand
        if cand.exists():
            return cand.resolve()
        for parent_dir in (REPO_ROOT, REPO_ROOT / "voice", REPO_ROOT / "work" / "voice_sample"):
            resolved = parent_dir / cand
            if resolved.exists():
                return resolved.resolve()

    # Domyślny fallback do standardowego pliku
    default_candidates = [
        REPO_ROOT / "voice" / "sample_reference.wav",
        REPO_ROOT / "work" / "voice_sample" / "sample_reference.wav",
    ]
    for c in default_candidates:
        if c.exists():
            return c.resolve()

    return None


# ==============================================================================
# 3. GŁÓWNY POTOK NARRACJI (NARRATE SCRIPT PIPELINE)
# ==============================================================================
def run_script_narration(
    input_file: Path,
    engine_name: str = "kokoclone",
    ref_audio: Path | None = None,
    lang: str = "auto",
    voice: str | None = None,
    expressive: bool = False,
    generate_subtitles: bool = True,
    pause_sentence_ms: int = 300,
    pause_paragraph_ms: int = 750,
    output_dir: Path | None = None,
) -> bool:
    """Realizuje kompletny potok narracji skryptu Markdown."""
    input_file = input_file.resolve()
    if not input_file.exists():
        log_err(f"Plik wejściowy nie istnieje: {input_file}")
        return False

    raw_content = input_file.read_text(encoding="utf-8")
    if not raw_content.strip():
        log_err(f"Plik wejściowy jest pusty: {input_file}")
        return False

    # 1. Detekcja języka
    norm_lang = normalize_language_code(lang)
    detected_lang = detect_script_language(raw_content) if norm_lang == "auto" else norm_lang

    # 2. Rozwiązanie głosu referencyjnego
    resolved_ref = resolve_voice_sample(ref_audio)
    if engine_name.lower() in ("kokoclone", "kokoro", "qwen", "chatterbox", "breeze") and (
        not resolved_ref or not resolved_ref.exists()
    ):
        log_warn(
            f"Silnik '{engine_name}' zaleca głos referencyjny, ale plik '{ref_audio}' nie został odnaleziony."
        )

    # 3. Domyślny głos bazowy dla Edge-TTS jeśli brak
    active_voice = voice
    if not active_voice:
        active_voice = "pl-PL-MarekNeural" if detected_lang.startswith("pl") else "en-US-ChristopherNeural"

    # 4. Inicjalizacja WorkRunManager
    task_slug = f"narrate_{input_file.stem}"
    run_mgr = WorkRunManager(
        task_slug=task_slug,
        engine=engine_name,
        base_dir=REPO_ROOT / "work" / "runs",
        explicit_output_dir=output_dir,
    )

    with run_mgr.capture_logs():
        log_info("=" * 68)
        log_info(" Workstation Hub: Standalone Script Narrator (Klonowanie głosu & Markdown)")
        log_info("=" * 68)
        log_info(f"Plik wejściowy:     {input_file.name}")
        log_info(f"Silnik TTS:         {engine_name}")
        log_info(f"Język mowy:         {detected_lang}")
        log_info(f"Głos bazowy:        {active_voice}")
        log_info(f"Głos referencyjny:  {resolved_ref.name if resolved_ref else 'Brak'}")
        log_info(f"Pauzy:              zdanie: {pause_sentence_ms}ms, akapit: {pause_paragraph_ms}ms")
        log_info(f"Tryb ekspresyjny:   {'WŁĄCZONY' if expressive else 'WYŁĄCZONY'}")
        log_info(f"Katalog roboczy:    {run_mgr.run_dir}")

        # KROK 1: Segmentacja Markdown
        chunker = ScriptChunker()
        chunks = chunker.parse(raw_content)
        if not chunks:
            log_err("Nie znaleziono żadnej czytelnej treści do narracji.")
            run_mgr.finish_run()
            return False

        log_ok(f"Wyodrębniono {len(chunks)} semantycznych chunków mowy.")

        # Zapis wyekstrahowanych chunków jako artefakt etapu 01
        chunks_payload = [
            {
                "index": c.index,
                "text": c.text,
                "is_paragraph_end": c.is_paragraph_end,
                "heading": c.heading,
            }
            for c in chunks
        ]
        run_mgr.save_artifact("01_source_extracted", "chunks.json", chunks_payload)

        # KROK 2: Inicjalizacja silnika TTS
        try:
            tts = get_tts_engine(name=engine_name, ref_audio=resolved_ref, voice=active_voice)
        except Exception as e_init:
            log_err(f"Błąd inicjalizacji silnika TTS '{engine_name}': {e_init}")
            run_mgr.finish_run()
            return False

        # Opcjonalny klient LLM dla trybu ekspresyjnego
        llm_client = None
        if expressive and supports_voice_tags(engine_name):
            try:
                from dub_video import OllamaTranslator

                candidate_llm = OllamaTranslator(model_name="SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M")
                if candidate_llm.is_available():
                    llm_client = candidate_llm
                    log_info("Reżyser tekstu: Włączono dwufazowe tagowanie emocji (Bielik LLM).")
            except Exception as e_llm:
                log_warn(f"Nie udało się zainicjalizować klienta LLM dla Reżysera: {e_llm}")

        # KROK 3: Synteza poszczególnych chunków
        tts_dir = run_mgr.tts_segments_dir
        generated_chunk_wavs: list[Path] = []
        chunk_durations: list[float] = []
        pause_durations: list[float] = []

        log_info(f"Rozpoczynanie syntezy {len(chunks)} segmentów...")
        with run_mgr.measure_stage("tts_synthesis"):
            for chunk in chunks:
                chunk_wav = tts_dir / f"chunk_{chunk.index:04d}.wav"
                marker_txt = tts_dir / f"chunk_{chunk.index:04d}.txt"

                text_to_speak = chunk.text
                if expressive and supports_voice_tags(engine_name) and llm_client:
                    text_to_speak = enrich_voiceover_tags(chunk.text, engine_name, client_llm=llm_client)

                # Sprawdzenie pamięci podręcznej (cache)
                if (
                    chunk_wav.exists()
                    and chunk_wav.stat().st_size > 1000
                    and marker_txt.exists()
                    and marker_txt.read_text(encoding="utf-8").strip() == text_to_speak.strip()
                ):
                    dur = get_audio_duration(chunk_wav)
                    generated_chunk_wavs.append(chunk_wav)
                    chunk_durations.append(dur)
                else:
                    log_info(f"Chunk #{chunk.index:03d} (akapit: {chunk.is_paragraph_end}): '{text_to_speak[:45]}...'")
                    success = tts.synthesize(
                        text=text_to_speak,
                        out_wav=chunk_wav,
                        ref_audio=resolved_ref,
                        lang=detected_lang,
                        voice=active_voice,
                    )
                    if not success:
                        log_err(f"Błąd syntezy chunka #{chunk.index}. Przerywanie.")
                        run_mgr.finish_run()
                        return False

                    marker_txt.write_text(text_to_speak + "\n", encoding="utf-8")
                    dur = get_audio_duration(chunk_wav)
                    generated_chunk_wavs.append(chunk_wav)
                    chunk_durations.append(dur)

                # Obliczenie długości pauzy po chunku
                pause_s = (pause_paragraph_ms / 1000.0) if chunk.is_paragraph_end else (pause_sentence_ms / 1000.0)
                pause_durations.append(pause_s)

        if llm_client is not None:
            llm_client.unload()

        # KROK 4: Generowanie plików ciszy dla pauz i łączenie
        audio_sequence: list[Path] = []
        silence_sentence_wav = tts_dir / "pause_sentence.wav"
        silence_paragraph_wav = tts_dir / "pause_paragraph.wav"

        if pause_sentence_ms > 0 and (
            not silence_sentence_wav.exists() or silence_sentence_wav.stat().st_size < 100
        ):
            create_silence_wav(silence_sentence_wav, pause_sentence_ms / 1000.0)

        if pause_paragraph_ms > 0 and (
            not silence_paragraph_wav.exists() or silence_paragraph_wav.stat().st_size < 100
        ):
            create_silence_wav(silence_paragraph_wav, pause_paragraph_ms / 1000.0)

        for i, wav_path in enumerate(generated_chunk_wavs):
            audio_sequence.append(wav_path)
            # Wstawienie ciszy po każdym chunku oprócz ostatniego
            if i < len(generated_chunk_wavs) - 1:
                is_para_end = chunks[i].is_paragraph_end
                if is_para_end and pause_paragraph_ms > 0:
                    audio_sequence.append(silence_paragraph_wav)
                elif not is_para_end and pause_sentence_ms > 0:
                    audio_sequence.append(silence_sentence_wav)

        # KROK 5: Łączenie i mastering EBU R128
        output_full_wav = run_mgr.output_dir / "full_narration.wav"
        log_info(f"Łączenie {len(audio_sequence)} elementów audio i mastering emisyjny...")
        with run_mgr.measure_stage("audio_mastering"):
            concatenate_and_master_narration(
                audio_paths=audio_sequence,
                output_wav=output_full_wav,
                target_lufs=-14.0,
                target_tp=-1.0,
            )

        total_audio_duration = get_audio_duration(output_full_wav)

        # KROK 6: Generowanie napisów SRT
        if generate_subtitles:
            # Pauzy pomiędzy chunkami (bez pauzy po ostatnim)
            effective_pauses = pause_durations[:-1] if len(pause_durations) > 1 else []
            srt_content = generate_srt_content(chunks, chunk_durations, effective_pauses)

            subtitles_file_stage = run_mgr.subtitles_dir / "narration.srt"
            subtitles_file_output = run_mgr.output_dir / "narration.srt"

            subtitles_file_stage.write_text(srt_content, encoding="utf-8")
            subtitles_file_output.write_text(srt_content, encoding="utf-8")
            log_ok(f"Zapisano zsynchronizowane napisy: {subtitles_file_output.name}")

        # KROK 7: Automatyczna analiza jakości (QualityAnalyzer)
        full_text_clean = " ".join(c.text for c in chunks)
        quality = run_mgr.quality_analyzer.analyze_output(
            audio_path=output_full_wav,
            target_speech_window=total_audio_duration,
            voiceover_text=full_text_clean,
        )

        # KROK 8: Raport podsumowujący
        summary_md = run_mgr.output_dir / "narration_summary.md"
        with open(summary_md, "w", encoding="utf-8") as f:
            f.write(f"# Raport Narracji Skryptu: {input_file.name}\n\n")
            f.write(f"- **Plik źródłowy:** `{input_file.name}`\n")
            f.write(f"- **Silnik TTS:** `{engine_name}`\n")
            f.write(f"- **Głos bazowy:** `{active_voice}`\n")
            f.write(f"- **Głos referencyjny:** `{resolved_ref.name if resolved_ref else 'Brak'}`\n")
            f.write(f"- **Liczba chunków:** `{len(chunks)}`\n")
            f.write(f"- **Długość całkowita:** `{total_audio_duration:.2f}s` ({total_audio_duration / 60.0:.2f} min)\n")
            f.write("- **Standard masteringu:** `EBU R128 (-14.0 LUFS, TP <= -1.0 dBFS, 48kHz stereo)`\n\n")
            f.write("## Audyt Jakościowy (Quality Metrics)\n\n")
            f.write(f"- **Status ogólny:** `{quality.overall_quality_status}`\n")
            f.write(f"- **Tempo mowy (WPM):** `{quality.wpm}` (ostrzeżenie: `{quality.pacing_warning}`)\n")
            f.write(f"- **Poziom szczytowy (Peak):** `{quality.peak_db} dB` (przester: `{quality.is_clipping}`)\n")
            f.write(f"- **Głośność RMS:** `{quality.rms_db} dB`\n")
            f.write(f"- **Maksymalna pauza wewnętrzna:** `{quality.max_internal_silence_sec:.2f}s`\n\n")
            f.write("## Wygenerowane Pliki Produkcyjne\n\n")
            f.write(f"1. **Pełne audio:** `{output_full_wav.name}`\n")
            if generate_subtitles:
                f.write("2. **Zsynchronizowane napisy:** `narration.srt`\n")
            f.write("3. **Log konsoli:** `logs/execution.log`\n")

        run_mgr.record_stats(
            chunks_count=len(chunks),
            total_duration_sec=round(total_audio_duration, 2),
            words_count=quality.word_count,
            wpm=quality.wpm,
            engine=engine_name,
            lang=detected_lang,
            expressive=expressive,
        )
        summary_json = run_mgr.finish_run(quality_analysis=quality)

        log_ok("=" * 68)
        log_ok(f"SUKCES! Wygenerowano pełną narrację dla {input_file.stem} ({total_audio_duration:.2f}s).")
        log_info(f"Katalog przebiegu (Run Workspace): {run_mgr.run_dir}")
        log_info(f"  1. [Audio Master]:     {output_full_wav.name}")
        if generate_subtitles:
            log_info("  2. [Napisy SRT]:       narration.srt")
        log_info(f"  3. [Raport MD]:        {summary_md.name}")
        log_info(f"  4. [Run Summary JSON]: {summary_json.name}")
        log_info("=" * 68)

    return True


# ==============================================================================
# 4. PUNKT WEJŚCIA CLI
# ==============================================================================
def create_argument_parser() -> argparse.ArgumentParser:
    """Tworzy parser argumentów CLI."""
    parser = argparse.ArgumentParser(
        description="Autonomiczny moduł narracji ze skryptu Markdown z klonowaniem głosu.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        required=True,
        help="Ścieżka do pliku Markdown ze skryptem narracji (.md)",
    )
    parser.add_argument(
        "-e",
        "--engine",
        type=str,
        default="kokoclone",
        choices=["kokoclone", "edge", "qwen", "chatterbox", "breeze", "kokoro"],
        help="Wybór silnika syntezy mowy TTS",
    )
    parser.add_argument(
        "-r",
        "--ref-audio",
        type=Path,
        default=Path("voice/sample_reference.wav"),
        help="Ścieżka do pliku WAV z próbką głosu referencyjnego",
    )
    parser.add_argument(
        "-l",
        "--lang",
        type=str,
        default="auto",
        help="Kod języka ('pl', 'en', 'auto' dla automatycznej detekcji)",
    )
    parser.add_argument(
        "--voice",
        type=str,
        default=None,
        help="Nazwa głosu wbudowanego (np. pl-PL-MarekNeural dla Edge TTS)",
    )
    parser.add_argument(
        "--expressive",
        action="store_true",
        default=False,
        help="Włącza dwufazowe tagowanie ekspresji i pauz dramatycznych przez Reżysera tekstu",
    )
    parser.add_argument(
        "--generate-subtitles",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generuje zsynchronizowany plik napisów .srt na bazie rzeczywistych długości audio",
    )
    parser.add_argument(
        "--pause-sentence",
        type=int,
        default=300,
        help="Długość pauzy między zdaniami w milisekundach",
    )
    parser.add_argument(
        "--pause-paragraph",
        type=int,
        default=750,
        help="Długość pauzy między akapitami i nagłówkami w milisekundach",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Jawnie wskazany katalog wyjściowy (jeśli nie podano, tworzy wersjonowany katalog w work/runs/)",
    )
    return parser


def main() -> None:
    parser = create_argument_parser()
    args = parser.parse_args()

    success = run_script_narration(
        input_file=args.input,
        engine_name=args.engine,
        ref_audio=args.ref_audio,
        lang=args.lang,
        voice=args.voice,
        expressive=args.expressive,
        generate_subtitles=args.generate_subtitles,
        pause_sentence_ms=args.pause_sentence,
        pause_paragraph_ms=args.pause_paragraph,
        output_dir=args.output_dir,
    )

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
