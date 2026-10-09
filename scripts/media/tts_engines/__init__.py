#!/usr/bin/env python3
"""
Fabryka i rejestr silników TTS.
Gwarantuje leniwą inicjalizację (lazy loading), eliminując kolizje bibliotek i wycieki zależności.
"""

from pathlib import Path
from .base import BaseTTSEngine
from .qwen import QwenTTSEngine
from .kokoclone import KokoCloneEngine
from .chatterbox import ChatterboxEngine
from .breeze import BreezeTTSEngine
from .edge import EdgeTTSEngine

AVAILABLE_ENGINES = {
    "qwen": QwenTTSEngine,
    "kokoro": KokoCloneEngine,
    "chatterbox": ChatterboxEngine,
    "breeze": BreezeTTSEngine,
    "edge": EdgeTTSEngine,
}


def list_available_engines() -> dict[str, bool]:
    """Zwraca mapę silników i ich dostępność w bieżącym środowisku."""
    res = {}
    for name, cls in AVAILABLE_ENGINES.items():
        try:
            inst = cls()
            res[name] = inst.is_available()
        except Exception:
            res[name] = False
    return res


def detect_best_engine(ref_audio: Path | None = None) -> str:
    """Wybiera optymalny komercyjny silnik na podstawie dostępności i próbki referencyjnej."""
    has_ref = ref_audio and ref_audio.exists()
    status = list_available_engines()

    if has_ref:
        if status.get("qwen"):
            return "qwen"
        if status.get("kokoro"):
            return "kokoro"
        if status.get("chatterbox"):
            return "chatterbox"
        if status.get("breeze"):
            return "breeze"

    return "edge"


def get_tts_engine(name: str = "auto", ref_audio: Path | None = None, **kwargs) -> BaseTTSEngine:
    """Tworzy instancję wybranego silnika TTS."""
    if name == "auto":
        name = detect_best_engine(ref_audio)

    engine_cls = AVAILABLE_ENGINES.get(name.lower())
    if not engine_cls:
        raise ValueError(f"Nieznany silnik TTS: '{name}'. Dostępne: {list(AVAILABLE_ENGINES.keys())}")

    return engine_cls(**kwargs)


__all__ = [
    "BaseTTSEngine",
    "QwenTTSEngine",
    "KokoCloneEngine",
    "ChatterboxEngine",
    "BreezeTTSEngine",
    "EdgeTTSEngine",
    "get_tts_engine",
    "list_available_engines",
    "detect_best_engine",
    "AVAILABLE_ENGINES",
]
