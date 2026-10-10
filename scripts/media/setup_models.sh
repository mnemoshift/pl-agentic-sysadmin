#!/usr/bin/env bash
set -euo pipefail

# Workstation Hub: Idempotentny instalator wag modeli AI (Breeze-TTS-2 & MarianMT)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET_DIR="${REPO_ROOT}/models/Breeze-TTS-2"

check_tool() {
    local cmd="$1"
    local install_pkg="${2:-$1}"
    local install_cmd="${3:-sudo apt install -y $install_pkg}"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo -e "\033[1;31m[ERROR]\033[0m Brak wymaganego narzędzia '${cmd}'. Zainstaluj je poleceniem:\n  ${install_cmd}" >&2
        return 1
    fi
    return 0
}

echo "[INFO] Weryfikacja wag modeli AI w ${TARGET_DIR}..."

# 1. Sprawdzenie czy wagi Breeze-TTS-2 już istnieją w repo
if [ -d "${TARGET_DIR}" ] && ls "${TARGET_DIR}"/*.safetensors 1>/dev/null 2>&1; then
    echo "[OK] Wagi modelu Breeze-TTS-2 są obecne i gotowe do użycia."
else
    mkdir -p "${REPO_ROOT}/models"
    
    # 2. Sprawdzenie lokalnego cache Hugging Face pod kątem symlinka (zero marnowania dysku)
    KNOWN_PATHS=(
        "${HOME}/.cache/huggingface/hub/models--MediaTek-Research--Breeze-TTS-2/snapshots"/*
    )
    
    FOUND_EXISTING=""
    for cand in "${KNOWN_PATHS[@]}"; do
        if [ -d "${cand}" ] && ls "${cand}"/*.safetensors 1>/dev/null 2>&1; then
            FOUND_EXISTING="${cand}"
            break
        fi
    done
    
    if [ -n "${FOUND_EXISTING}" ]; then
        echo "[INFO] Wykryto istniejące wagi w systemie (${FOUND_EXISTING})."
        echo "[INFO] Tworzenie symlinka do ${TARGET_DIR}..."
        rm -rf "${TARGET_DIR}"
        ln -s "${FOUND_EXISTING}" "${TARGET_DIR}"
        echo "[OK] Utworzono symlink do lokalnych wag (0 MB dodatkowego dysku)."
    else
        echo "[INFO] Pobieranie wag modelu MediaTek-Research/Breeze-TTS-2 z Hugging Face..."
        if command -v uv >/dev/null 2>&1; then
            uv run huggingface-cli download MediaTek-Research/Breeze-TTS-2 --local-dir "${TARGET_DIR}"
        elif command -v huggingface-cli >/dev/null 2>&1; then
            huggingface-cli download MediaTek-Research/Breeze-TTS-2 --local-dir "${TARGET_DIR}"
        else
            echo "[ERROR] Brak narzędzia huggingface-cli lub uv. Zainstaluj uv lub pobierz wagi ręcznie."
            exit 1
        fi
        echo "[OK] Pobrano wagi Breeze-TTS-2 do ${TARGET_DIR}."
    fi
fi

# 3. Weryfikacja modelu tłumaczeniowego MarianMT (Helsinki-NLP/opus-mt-pl-en)
echo "[INFO] Weryfikacja lokalnego modelu tłumaczeniowego MarianMT (PL -> EN)..."
VENV_PY="${REPO_ROOT}/.venv/bin/python"
if [ -x "${VENV_PY}" ]; then
    "${VENV_PY}" -c "from transformers import MarianMTModel, MarianTokenizer; m='Helsinki-NLP/opus-mt-pl-en'; MarianTokenizer.from_pretrained(m); MarianMTModel.from_pretrained(m); print('[OK] Model MarianMT gotowy do użycia na CPU.')"
else
    echo "[WARN] Środowisko .venv nie jest jeszcze zainicjalizowane. Uruchom: make setup-env"
fi

echo "[OK] Wszystkie modele AI są zainicjalizowane."
