#!/usr/bin/env python3
"""
Workstation Hub: Reżyser tekstu lektorskiego (Text Director).
Realizuje dwufazowe wzbogacanie tekstu o znaczniki emocji i dynamiki (Two-Pass TTS Voice Tags):
- Krok 1 (Scenarzysta): czysty tekst po adaptacji pacingu (clean_voiceover_text).
- Krok 2 (Reżyser): wzbogacenie wypowiedzi o dozwolone znaczniki TTS (enrich_voiceover_tags).
- Krok 3 (Sanitizer / Fallback): oczyszczanie napisów oraz silników bez wsparcia tagów (strip_voice_tags).
"""

import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class TagFormat(StrEnum):
    NONE = "none"
    SSML = "ssml"
    PARALINGUISTIC_XML = "paralinguistic_xml"
    BRACKETS = "brackets"


class TTSEngineType(StrEnum):
    EDGE = "edge"
    QWEN = "qwen"
    CHATTERBOX = "chatterbox"
    KOKORO = "kokoro"
    KOKOCLONE = "kokoclone"
    BREEZE = "breeze"


@dataclass(frozen=True, slots=True)
class TTSEngineCapability:
    engine_name: str
    supports_tags: bool
    tag_format: TagFormat
    allowed_tags: tuple[str, ...]
    description: str


# ==============================================================================
# Słownik znaczników emocji i dynamiki Qwen3 TTS (Qwen3 TTS Prompt Guide)
# ==============================================================================
QWEN_EMOTION_TAGS: dict[str, str] = {
    # Tag: opis działania (Span scope)
    "sad": "Sad delivery",
    "bored": "Bored tone",
    "amazed": "Amazed / astonished tone",
    "tired": "Tired, exhausted tone",
    "angry": "Angry delivery",
    "excited": "Excited, enthusiastic delivery",
    "serious": "Serious, focused tone",
    "curious": "Curious, inquisitive tone",
    "shouting": "Shouting delivery",
    "whispers": "Whispering delivery",
    "asmr": "Soft ASMR style delivery",
    "panicked": "Panicked, rushed tone",
    "sarcastic": "Sarcastic tone",
    "empathetic": "Empathetic, compassionate tone",
    "mischievously": "Mischievous, playful tone",
    "reluctantly": "Reluctant delivery",
    "crying": "Crying, weeping delivery",
    "trembling": "Trembling, shaky delivery",
    "very slowly": "Very slow speech rate",
    "very fast": "Very fast speech rate",
    "scornful": "Scornful, dismissive tone",
    "like dracula": "Deep, eerie gothic style",
    "deep and loud shouting": "Deep, loud shouting",
}

QWEN_VOCAL_EVENT_TAGS: dict[str, str] = {
    # Tag: zdarzenie wokalne (Point scope)
    "gasp": "Sharp intake of breath",
    "sighing": "Sigh",
    "clears throat": "Throat clearing",
    "giggles": "Giggle / chuckle",
    "laughing": "Laughter",
    "cough": "Cough",
    "snorts": "Snort or scoff",
}

ALL_QWEN_TAGS: set[str] = set(QWEN_EMOTION_TAGS.keys()) | set(QWEN_VOCAL_EVENT_TAGS.keys())


ENGINE_CAPABILITIES: dict[str, TTSEngineCapability] = {
    "edge": TTSEngineCapability(
        engine_name="edge",
        supports_tags=True,
        tag_format=TagFormat.SSML,
        allowed_tags=("break", "prosody", "express-as", "speak"),
        description="Wspiera format SSML: <break time='...ms'/>, <prosody rate='...'>, <express-as style='...'>",
    ),
    "qwen": TTSEngineCapability(
        engine_name="qwen",
        supports_tags=True,
        tag_format=TagFormat.BRACKETS,
        allowed_tags=tuple(sorted(ALL_QWEN_TAGS)),
        description="Wspiera oficjalne tagi Qwen3 TTS w nawiasach kwadratowych [tag]: emotion (span) i vocal events (point).",
    ),
    "chatterbox": TTSEngineCapability(
        engine_name="chatterbox",
        supports_tags=True,
        tag_format=TagFormat.BRACKETS,
        allowed_tags=("chuckle", "sigh", "gasp", "pause"),
        description="Wspiera znaczniki w nawiasach: [chuckle], [sigh], [gasp], [pause]",
    ),
    "kokoro": TTSEngineCapability(
        engine_name="kokoro",
        supports_tags=False,
        tag_format=TagFormat.NONE,
        allowed_tags=(),
        description="Brak wsparcia dla znaczników XML/bracket. Wyłącznie naturalna interpunkcja.",
    ),
    "kokoclone": TTSEngineCapability(
        engine_name="kokoclone",
        supports_tags=False,
        tag_format=TagFormat.NONE,
        allowed_tags=(),
        description="Brak wsparcia dla znaczników XML/bracket. Wyłącznie naturalna interpunkcja.",
    ),
    "breeze": TTSEngineCapability(
        engine_name="breeze",
        supports_tags=False,
        tag_format=TagFormat.NONE,
        allowed_tags=(),
        description="Brak wsparcia dla znaczników XML/bracket. Wyłącznie naturalna interpunkcja.",
    ),
}


def normalize_engine_name(engine_name: str) -> str:
    """Normalizuje nazwę silnika TTS do formy kanonicznej."""
    name = (engine_name or "").lower().strip()
    name = re.sub(r"[-_]", "", name)
    if "edge" in name:
        return "edge"
    if "qwen" in name:
        return "qwen"
    if "chatterbox" in name:
        return "chatterbox"
    if "kokoclone" in name:
        return "kokoclone"
    if "kokoro" in name:
        return "kokoro"
    if "breeze" in name:
        return "breeze"
    return name


def get_engine_capability(engine_name: str) -> TTSEngineCapability:
    """Zwraca możliwości wskazanego silnika TTS."""
    canonical = normalize_engine_name(engine_name)
    if canonical in ENGINE_CAPABILITIES:
        return ENGINE_CAPABILITIES[canonical]
    return TTSEngineCapability(
        engine_name=canonical,
        supports_tags=False,
        tag_format=TagFormat.NONE,
        allowed_tags=(),
        description=f"Nieznany silnik '{engine_name}'. Domyślny brak wsparcia znaczników.",
    )


def supports_voice_tags(engine_name: str) -> bool:
    """Sprawdza, czy silnik wspiera znaczniki ekspresji/pauz."""
    return get_engine_capability(engine_name).supports_tags


def strip_voice_tags(text: str) -> str:
    """
    Usuwa z tekstu wszelkie tagi XML/HTML (<...>) oraz tagi w nawiasach kwadratowych ([...]),
    w tym znaczniki wielowyrazowe ze spacjami (np. [clears throat], [very slowly]),
    aby nie trafiły do napisów ani do silników, które przeczytałyby je na głos.
    """
    if not text:
        return ""

    raw = text

    # Usunięcie wszelkich tagów XML / HTML (np. <break time="300ms"/>, <express-as style="excited">, <breath>, <strong>)
    raw = re.sub(r"<[^>]+>", "", raw)

    # Usunięcie znaczników w nawiasach kwadratowych (w tym wielowyrazowych ze spacjami i myślnikami)
    raw = re.sub(r"\[[a-zA-Z0-9_\- ]+\]", "", raw)

    # Dekodowanie encji XML z powrotem do znaków tekstowych (dla napisów i czystego tekstu)
    raw = (
        raw.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
    )

    # Normalizacja wielokrotnych spacji przed znakami interpunkcyjnymi
    raw = re.sub(r"\s+([,\.!?;:])", r"\1", raw)

    # Normalizacja białych znaków i usunięcie zbędnych spacji
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def filter_qwen_tags(text: str) -> str:
    """
    Skanuje tekst pod kątem znaczników [tag] i usuwa wszelkie tagi spoza oficjalnego
    słownika Qwen3 TTS (QWEN_EMOTION_TAGS + QWEN_VOCAL_EVENT_TAGS).
    Usuwa również wszelkie przypadkowe tagi XML (<...>).
    Zachowuje poprawne tagi ze słownika, oryginalne słowa i poprawną interpunkcję.
    """
    if not text:
        return ""

    raw = text

    # Usunięcie wszelkich tagów XML (<...>), aby nie były odczytane przez Qwen na głos
    raw = re.sub(r"<[^>]+>", "", raw)

    def replace_bracket_tag(match: re.Match[str]) -> str:
        content = match.group(1).strip()
        if content.lower() in ALL_QWEN_TAGS:
            return f"[{content.lower()}]"
        return ""

    raw = re.sub(r"\[([a-zA-Z0-9_\- ]+)\]", replace_bracket_tag, raw)

    # Normalizacja spacji przed znakami interpunkcyjnymi
    raw = re.sub(r"\s+([,\.!?;:])", r"\1", raw)

    # Normalizacja wielokrotnych spacji
    raw = re.sub(r"[ \t]+", " ", raw).strip()
    return raw



def clean_voiceover_text(text: str) -> str:
    """
    Oczyszcza surowy tekst voiceoveru/dubbingu z wszelkich wycieków metadanych promptu:
    - wyciąga zawartość <voiceover>...</voiceover>,
    - odcina sekcję PACING BUDGET i pokrewne reguły,
    - usuwa wtrącenia metadanych w nawiasach kwadratowych i okrągłych,
    - usuwa bloki kodu Markdown oraz zbędne cudzysłowy.
    """
    if not text:
        return ""

    raw = text.strip()

    # 1. Priorytetowe parsowanie zawartości tagu <voiceover>...</voiceover>
    vo_match = re.search(r"<voiceover>(.*?)</voiceover>", raw, flags=re.DOTALL | re.IGNORECASE)
    if vo_match:
        raw = vo_match.group(1).strip()
    else:
        # Usunięcie pojedynczych niedomkniętych tagów
        raw = re.sub(r"^.*?<voiceover>\s*", "", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"\s*</voiceover>.*$", "", raw, flags=re.DOTALL | re.IGNORECASE)

    # 2. Usunięcie tagów <source_text>...</source_text> oraz tagów pomocniczych
    raw = re.sub(r"<source_text>.*?</source_text>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"</?(?:source_text|voiceover)>", "", raw, flags=re.IGNORECASE)

    # 3. Odcięcie frazy PACING BUDGET / PACING RULES oraz wszystkiego, co następuje po niej
    raw = re.sub(r"\bPACING BUDGET\b.*", "", raw, flags=re.IGNORECASE | re.DOTALL)
    raw = re.sub(r"\bPACING (?:RULES|REVISION RULES)\b.*", "", raw, flags=re.IGNORECASE | re.DOTALL)

    # 4. Usunięcie bloków kodu Markdown
    raw = re.sub(r"^```(?:[a-zA-Z]+)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    # 5. Usunięcie typowych prefiksów generowanych przez LLM
    prefixes = [
        r"^(?:Here(?:'s| is) (?:a |the )?(?:(?:natural|fluent|idiomatic|spoken|English|revised|plain)\s+)*(?:translation|voiceover)[^:]*:\s*)",
        r"^(?:English translation:\s*)",
        r"^(?:Translation:\s*)",
        r"^(?:Sure, here is[^:]*:\s*)",
        r"^(?:Voiceover:\s*)",
    ]
    for p in prefixes:
        raw = re.sub(p, "", raw, flags=re.IGNORECASE)

    # 6. Wytnij wtrącenia metadanych w nawiasach np. [Speech window: ...], (Target voiceover length: ...)
    raw = re.sub(
        r"\[(?:\s*pacing|\s*speech window|\s*target voiceover|\s*word count|\s*words?|\s*count|\s*note|\s*voiceover|\s*audio|\s*pause|\s*sound|\s*laughter|\s*sigh|\s*target)[^\]]*\]",
        "",
        raw,
        flags=re.IGNORECASE,
    )
    raw = re.sub(
        r"\((?:\s*pacing|\s*speech window|\s*target voiceover|\s*target voice|\s*word count|\s*words?|\s*count|\s*note|\s*voiceover|\s*audio|\s*pause|\s*sound|\s*laughter|\s*sigh|\s*target|\s*natural|\s*articulate|\s*approximately)[^\)]*\)",
        "",
        raw,
        flags=re.IGNORECASE,
    )

    # 7. Zdjęcie zbędnych cudzysłowów opakowujących całą wypowiedź
    raw = raw.strip(' "”„\'`')

    # 8. Normalizacja białych znaków
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _build_qwen_director_prompt(text: str) -> tuple[str, str]:
    """Generuje dedykowany prompt Reżysera dla Qwen3 TTS zgodnie z oficjalnym Prompt Guide."""
    emotions_str = "\n".join(f"  - [{tag}]: {desc}" for tag, desc in QWEN_EMOTION_TAGS.items())
    events_str = "\n".join(f"  - [{tag}]: {desc}" for tag, desc in QWEN_VOCAL_EVENT_TAGS.items())

    system_prompt = (
        "You are an elite Audio & Voiceover Director specialized in Qwen3 TTS expressive speech.\n"
        "Your task is to enrich the given voiceover line with official Qwen3 TTS prompt tags in square brackets [...].\n\n"
        "OFFICIAL QWEN3 TTS TAG SPECIFICATION:\n"
        "1. Emotion & Delivery Tags (Span scope - defines overall style/tone from insertion point until next tag or segment):\n"
        f"{emotions_str}\n\n"
        "2. Rich-language Vocal Event Tags (Point scope - momentary vocal event at that exact point without altering the overarching emotion):\n"
        f"{events_str}\n\n"
        "USAGE RULES & GUIDELINES:\n"
        "- Tags can be combined directly, e.g.: '[tired][sighing]Another day of work...' or '[excited]Great news! [laughing]We did it!'\n"
        "- Use natural punctuation (hyphens '-', ellipses '...', exclamation marks '!') alongside tags to guide pacing and pauses.\n"
        "- Insert at most 1 to 3 tags per utterance. Keep delivery tasteful, natural, and understated.\n"
        "- DO NOT invent any tags. ONLY use tags from the approved lists above.\n\n"
        "STRICT CARDINAL RULES:\n"
        "1. DO NOT CHANGE, ADD, OR DELETE ANY WORDS from the original text. Every single word of the original text must remain verbatim in place.\n"
        "2. ONLY insert tags from the approved lists in square brackets [...].\n"
        "3. Wrap your entire output strictly inside <directed_text>...</directed_text> tags.\n"
        "4. Output NO preamble, NO commentary, NO markdown codeblocks, NO quotes outside or inside the tags."
    )

    user_prompt = (
        f"Original spoken text:\n\"{text}\"\n\n"
        "Enrich with allowed Qwen3 TTS voice tags while strictly preserving every single word verbatim. "
        "Output ONLY inside <directed_text>...</directed_text>."
    )
    return system_prompt, user_prompt


def _build_director_prompt(text: str, engine_name: str) -> tuple[str, str]:
    """Generuje system prompt oraz user prompt dla Reżysera tekstu."""
    cap = get_engine_capability(engine_name)

    if cap.engine_name == "qwen":
        return _build_qwen_director_prompt(text)

    engine_tag_instructions = ""
    if cap.tag_format == TagFormat.SSML:
        engine_tag_instructions = (
            "Allowed SSML tags:\n"
            "- <break time=\"300ms\"/> or <break time=\"500ms\"/> (for strategic dramatic pauses)\n"
            "- <prosody rate=\"+10%\">...</prosody> (for key emphasis or dynamic tempo change)\n"
            "- <express-as style=\"excited\">...</express-as> or <express-as style=\"cheerful\">...</express-as> "
            "or <express-as style=\"whispering\">...</express-as>\n"
            "Ensure all tags are well-formed and closed. Self-close <break .../> properly."
        )
    elif cap.tag_format == TagFormat.PARALINGUISTIC_XML:
        engine_tag_instructions = (
            "Allowed Paralinguistic XML tags:\n"
            "- <breath/> (for subtle natural breaths before key thoughts)\n"
            "- <laughter>...</laughter> (for amused or ironic delivery)\n"
            "- <strong>...</strong> (for punchy emphasis)\n"
            "- Ellipses '...' for thoughtful pacing pauses.\n"
            "Ensure all tags are closed properly."
        )
    elif cap.tag_format == TagFormat.BRACKETS:
        engine_tag_instructions = (
            "Allowed Bracket tags:\n"
            "- [pause] (brief dramatic pause)\n"
            "- [chuckle] (light humorous chuckle)\n"
            "- [sigh] (thoughtful or relieved sigh)\n"
            "- [gasp] (startled intake of air)\n"
        )

    system_prompt = (
        "You are an elite Audio & Voiceover Director.\n"
        "Your task is to enrich the given voiceover line with subtle, realistic voice tags to enhance delivery.\n\n"
        f"{engine_tag_instructions}\n\n"
        "STRICT CARDINAL RULES:\n"
        "1. DO NOT CHANGE, ADD, OR DELETE ANY WORDS from the original text. "
        "Every single word of the original text must remain verbatim in place.\n"
        "2. Only insert allowed voice tags around key phrases or pauses.\n"
        "3. Maximum 2 to 3 tags per utterance. Keep it natural and understated.\n"
        "4. Wrap your entire output strictly inside <directed_text>...</directed_text> tags.\n"
        "5. No preamble, no commentary, no quotes outside or inside the tags."
    )

    user_prompt = (
        f"Original spoken text:\n\"{text}\"\n\n"
        "Enrich with allowed voice tags while strictly preserving every single word. "
        "Output ONLY inside <directed_text>...</directed_text>."
    )

    return system_prompt, user_prompt


def _extract_words(text: str) -> list[str]:
    """Ekstrahuje listę słów z tekstu z pominięciem znaczników i interpunkcji."""
    clean = strip_voice_tags(text)
    return [w.lower() for w in re.findall(r"\b\w+\b", clean)]


def _validate_directed_text(original_text: str, directed_text: str, cap: TTSEngineCapability) -> bool:
    """Weryfikuje, czy reżyser nie zmienił słów i czy tagi są poprawne."""
    orig_words = _extract_words(original_text)
    dir_words = _extract_words(directed_text)

    # Słowa muszą być w 100% zachowane
    if orig_words != dir_words:
        logger.warning(
            "Reżyser LLM zmodyfikował słowa oryginału! Fallback do oryginalnego tekstu.\n"
            "Oryginał: %s\nReżyser: %s",
            orig_words,
            dir_words,
        )
        return False

    # Sprawdzenie niedozwolonych tagów
    if cap.tag_format == TagFormat.NONE:
        # Silnik bez wsparcia nie powinien mieć żadnych tagów
        if "<" in directed_text or ">" in directed_text or "[" in directed_text:
            return False

    if cap.engine_name == "qwen":
        # Qwen wspiera wyłącznie nawiasy kwadratowe z listy whitelist. Brak tagów XML.
        if "<" in directed_text or ">" in directed_text:
            return False
        found_tags = re.findall(r"\[([a-zA-Z0-9_\- ]+)\]", directed_text)
        for t in found_tags:
            if t.strip().lower() not in ALL_QWEN_TAGS:
                return False

    return True


def _call_llm_director(
    system_prompt: str,
    user_prompt: str,
    client_llm: Any,
) -> str | None:
    """Wywołuje LLM za pomocą przekazanego klienta lub callable."""
    try:
        # Obsługa translatora OllamaTranslator / obiektu z metodą _call_ollama
        if hasattr(client_llm, "_call_ollama"):
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            return client_llm._call_ollama(messages, temperature=0.1)

        # Obsługa klienta z metodą chat()
        if hasattr(client_llm, "chat") and callable(client_llm.chat):
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            res = client_llm.chat(messages=messages)
            if isinstance(res, str):
                return res
            if hasattr(res, "content"):
                return res.content
            return str(res)

        # Obsługa klienta z metodą generate()
        if hasattr(client_llm, "generate") and callable(client_llm.generate):
            prompt = f"{system_prompt}\n\n{user_prompt}"
            res = client_llm.generate(prompt)
            return res if isinstance(res, str) else str(res)

        # Obsługa funkcji callable client_llm(prompt)
        if callable(client_llm):
            prompt = f"{system_prompt}\n\n{user_prompt}"
            res = client_llm(prompt)
            return res if isinstance(res, str) else str(res)

    except Exception as e:
        logger.warning("Błąd wywołania LLM w Reżyserze tekstu: %s", e)
        return None

    return None


def escape_raw_ampersands(text: str) -> str:
    """
    Upewnia się, że tekst poza tagami XML nie zawiera surowych znaków '&'.
    Zamienia '&' na '&amp;' w miejscach, które nie są poprawnymi encjami XML.
    """
    if not text or "&" not in text:
        return text

    # Podział na tagi XML (<...>) oraz zwykły tekst
    parts = re.split(r"(<[^>]+>)", text)
    escaped_parts: list[str] = []
    # Wzorzec dopasowujący poprawne encje XML: nazwane (&amp;, &lt;) lub numeryczne (&#123;, &#x1F;)
    valid_entity_pattern = re.compile(r"&(?!([a-zA-Z][a-zA-Z0-9]*|#[0-9]+|#x[0-9a-fA-F]+);)")

    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            escaped_parts.append(part)
        else:
            escaped_parts.append(valid_entity_pattern.sub("&amp;", part))

    return "".join(escaped_parts)


def prepare_edge_ssml(text: str) -> str:
    """
    Przygotowuje tekst w formacie SSML dla silnika Edge TTS:
    - Zabezpiecza surowe znaki '&' poza tagami XML zamieniając je na '&amp;'.
    - Zachowuje poprawne encje XML oraz znaczniki SSML (<break .../>, <prosody>, etc.).
    """
    if not text:
        return ""
    return escape_raw_ampersands(text)


prepare_ssml = prepare_edge_ssml


def enrich_voiceover_tags(
    text: str,
    engine_type: str,
    client_llm: Any = None,
) -> str:
    """
    Krok 2 (Reżyser / Decorator):
    Jeśli silnik TTS wspiera znaczniki, wzbogaca wypowiedź o dedykowane tagi,
    zachowując bezwzględnie oryginalne słowa. W razie braku wsparcia lub błędu
    zwraca bezpieczny tekst oczyszczony.
    Dla formatu SSML (Edge TTS) upewnia się, że surowe znaki '&' są zamienione na '&amp;'.
    """
    clean_text = clean_voiceover_text(text)
    if not clean_text:
        return ""

    cap = get_engine_capability(engine_type)
    if not cap.supports_tags:
        return strip_voice_tags(clean_text)

    if client_llm is None:
        if cap.engine_name == "qwen":
            return filter_qwen_tags(clean_text)
        if cap.tag_format == TagFormat.SSML:
            return prepare_edge_ssml(clean_text)
        return clean_text

    system_prompt, user_prompt = _build_director_prompt(clean_text, cap.engine_name)
    raw_response = _call_llm_director(system_prompt, user_prompt, client_llm)

    if not raw_response:
        if cap.engine_name == "qwen":
            return filter_qwen_tags(clean_text)
        if cap.tag_format == TagFormat.SSML:
            return prepare_edge_ssml(clean_text)
        return clean_text

    # Wyciągnięcie zawartości <directed_text>...</directed_text>
    match = re.search(r"<directed_text>(.*?)</directed_text>", raw_response, flags=re.DOTALL | re.IGNORECASE)
    if match:
        directed_cand = match.group(1).strip()
    else:
        # Fallback jeśli model nie domknął tagu lub zwrócił tekst bezpośrednio
        directed_cand = re.sub(r"^.*?<directed_text>\s*", "", raw_response, flags=re.DOTALL | re.IGNORECASE)
        directed_cand = re.sub(r"\s*</directed_text>.*$", "", directed_cand, flags=re.DOTALL | re.IGNORECASE).strip()
        directed_cand = directed_cand.strip(' "”„\'`')

    # Filtracja dla Qwen: usunięcie ewentualnych halucynacji tagowych i tagów XML przed asercją
    if cap.engine_name == "qwen":
        directed_cand = filter_qwen_tags(directed_cand)

    # Asercja wierności słów i integralności
    if _validate_directed_text(clean_text, directed_cand, cap):
        if cap.tag_format == TagFormat.SSML:
            directed_cand = prepare_edge_ssml(directed_cand)
        return directed_cand

    if cap.engine_name == "qwen":
        return filter_qwen_tags(clean_text)
    if cap.tag_format == TagFormat.SSML:
        return prepare_edge_ssml(clean_text)
    return clean_text
