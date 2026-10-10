#!/usr/bin/env python3
"""
Kompatybilny wrapper dla starszych wywołań dub_short.py.
Automatycznie przekazuje wywołanie do nadrzędnego narzędzia dub_video.py,
wspierającego zarówno format długi (Long-form/Episodes), jak i krótki (Shorts).
"""

import sys
from pathlib import Path

# Dołączenie ścieżki bieżącego katalogu i import dub_video
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import dub_video  # noqa: E402

if __name__ == "__main__":
    dub_video.main()
