#!/usr/bin/env bash
# ==============================================================================
# prepare_demo.sh — Inicjalizacja i weryfikacja środowiska nagraniowego EP002 Short
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORK_INPUT="$REPO_ROOT/work/EP002_Short/input"
WORK_ROOT="$REPO_ROOT/work/EP002_Short"

echo "[DEMO-PREP] Inicjalizacja środowiska demonstracyjnego w: $WORK_ROOT"

# 1. Przygotuj katalogi
mkdir -p "$WORK_INPUT"

# 2. Wyczyść stare artefakty generowane w trakcie sesji (jeśli istnieją)
rm -rf "$WORK_ROOT/assets" "$WORK_ROOT"/*.kdenlive* "$WORK_ROOT"/*.mp4 "$WORK_ROOT"/*.ass 2>/dev/null || true

# 3. Sprawdź / odtwórz surowy voiceover
VOICEOVER_SRC="${VOICEOVER_SRC:-${HOME}/projects/obs/output/2026-09-28 17-52-10.mp4}"
if [ ! -f "$WORK_INPUT/raw_voiceover.mp4" ]; then
    if [ -n "$VOICEOVER_SRC" ] && [ -f "$VOICEOVER_SRC" ]; then
        echo "[DEMO-PREP] Kopiowanie surowego nagrania OBS ($VOICEOVER_SRC)..."
        cp "$VOICEOVER_SRC" "$WORK_INPUT/raw_voiceover.mp4"
    else
        echo "[INFO] Brak zewnętrznego voiceoveru — jeśli potrzebny, umieść plik w $WORK_INPUT/raw_voiceover.mp4"
    fi
else
    echo "[DEMO-PREP] raw_voiceover.mp4 jest na swoim miejscu."
fi

# 4. Sprawdź / odtwórz footage źródłowe
FOOTAGE_SRC="${FOOTAGE_SRC:-}"
if [ ! -f "$WORK_INPUT/footage_ep002.mp4" ] && [ ! -L "$WORK_INPUT/footage_ep002.mp4" ]; then
    if [ -n "$FOOTAGE_SRC" ] && [ -f "$FOOTAGE_SRC" ]; then
        echo "[DEMO-PREP] Tworzenie symlinka do footage_ep002.mp4..."
        ln -sf "$FOOTAGE_SRC" "$WORK_INPUT/footage_ep002.mp4"
    else
        echo "[INFO] Brak FOOTAGE_SRC — umieść wideo źródłowe w $WORK_INPUT/"
    fi
else
    echo "[DEMO-PREP] footage_ep002.mp4 jest na swoim miejscu."
fi

# 5. Sprawdź / odtwórz short_script.md
SCRIPT_TPL="$REPO_ROOT/templates/kdenlive/EP002_Short_script.md"
if [ ! -f "$WORK_INPUT/short_script.md" ]; then
    if [ -f "$SCRIPT_TPL" ]; then
        echo "[DEMO-PREP] Kopiowanie opisu scen z szablonu $SCRIPT_TPL..."
        cp "$SCRIPT_TPL" "$WORK_INPUT/short_script.md"
    else
        echo "[OSTRZEŻENIE] Brak szablonu $SCRIPT_TPL."
    fi
else
    echo "[DEMO-PREP] short_script.md jest na swoim miejscu."
fi

echo "=========================================================="
echo "[DEMO-PREP] Sukces! Zawartość $WORK_INPUT:"
ls -lh "$WORK_INPUT"
echo "=========================================================="
