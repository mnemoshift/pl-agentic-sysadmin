#!/usr/bin/env python3
"""
Abstrakcyjna klasa bazowa dla silników syntezy mowy TTS w potoku multimedialnym.
Definiuje wspólny interfejs, uniemożliwiając wycieki zależności i kolizje wersji.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseTTSEngine(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Czytelna nazwa silnika i modelu."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Zwraca True, jeśli silnik i jego zależności są dostępne w środowisku."""
        pass

    @abstractmethod
    def synthesize(
        self,
        text: str,
        out_wav: Path,
        ref_audio: Path | None = None,
        ref_transcript: str = "",
        instruction: str = "",
        seed: int = 42,
        **kwargs,
    ) -> bool:
        """
        Syntezuje zadany tekst i zapisuje wynik jako plik WAV.
        Zwraca True przy sukcesie, False przy błędzie.
        """
        pass
