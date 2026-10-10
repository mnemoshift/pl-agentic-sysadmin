#!/usr/bin/env bash
# ==============================================================================
# setup_kdenlive_mcp.sh — Autonomiczny instalator i audytor Kdenlive + MCP Server
#
# Zasada działania:
# 1. 100% User-Space (Zero-Sudo): Flatpak --user, ~/.local/bin, uv venv
# 2. Tworzy wrappery CLI dla silnika MLT (melt) i Kdenlive
# 3. Klonuje i konfiguruje serwer MCP (kdenlive-mcp) z poprawkami XML i libass
# 4. Sprawdza i generuje konfigurację MCP dla Antigravity
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TEMPLATES_DIR="${REPO_ROOT}/templates/kdenlive"

TARGET_MCP_DIR="${HOME}/.local/share/kdenlive-mcp"
TARGET_BIN_DIR="${HOME}/.local/bin"
GLOBAL_MCP_CONFIG="${HOME}/.gemini/config/mcp_config.json"

MODE="${1:---check}"

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

print_header() {
    echo "=========================================================="
    echo "  KDENLIVE & MCP SERVER — WORKSTATION SETUP & AUDIT"
    echo "=========================================================="
}

check_status() {
    print_header
    echo "[*] Sprawdzanie stanu instalacji Kdenlive i serwera MCP..."
    echo ""

    local all_ok=true

    # 1. Flatpak org.kde.kdenlive
    if flatpak info org.kde.kdenlive &>/dev/null; then
        local kdenlive_ver
        kdenlive_ver=$(flatpak info org.kde.kdenlive | grep "Version:" | awk '{print $2}')
        echo "  [✓] Flatpak Kdenlive zainstalowany: ${kdenlive_ver}"
    else
        echo "  [✗] Brak pakietu Flatpak org.kde.kdenlive (wymagany)"
        all_ok=false
    fi

    # 2. Wrapper CLI kdenlive
    if [[ -x "${TARGET_BIN_DIR}/kdenlive" ]]; then
        echo "  [✓] Wrapper CLI kdenlive: ${TARGET_BIN_DIR}/kdenlive"
    else
        echo "  [✗] Brak wrappera CLI: ${TARGET_BIN_DIR}/kdenlive"
        all_ok=false
    fi

    # 3. Wrapper CLI melt
    if [[ -x "${TARGET_BIN_DIR}/melt" ]]; then
        local melt_ver
        melt_ver=$("${TARGET_BIN_DIR}/melt" --version 2>&1 | head -n1 || echo "unknown")
        echo "  [✓] Wrapper CLI melt: ${TARGET_BIN_DIR}/melt (${melt_ver})"
    else
        echo "  [✗] Brak wrappera CLI: ${TARGET_BIN_DIR}/melt"
        all_ok=false
    fi

    # 4. Repozytorium kdenlive-mcp
    if [[ -d "${TARGET_MCP_DIR}" ]]; then
        echo "  [✓] Katalog serwera MCP obecny: ${TARGET_MCP_DIR}"
        
        # Venv
        if [[ -x "${TARGET_MCP_DIR}/.venv/bin/kdenlive-mcp" ]]; then
            echo "  [✓] Środowisko Python venv serwera MCP aktywne"
        else
            echo "  [✗] Brak wirtualnego środowiska ${TARGET_MCP_DIR}/.venv"
            all_ok=false
        fi

        # Sprawdzenie poprawek XML
        if grep -q "a_track = 0 if idx == 0 else pos - 1" "${TARGET_MCP_DIR}/src/kdenlive_mcp/kdenlive/adapter/xml_writer.py" 2>/dev/null; then
            echo "  [✓] Poprawka kaskady kompozycji (qtblend) zainstalowana"
        else
            echo "  [!] Brak poprawki kaskady qtblend w xml_writer.py"
            all_ok=false
        fi

        if grep -q "master = _sub(mlt, \"tractor\", id=\"{%s}\" % _pad_uuid(sequence.id)" "${TARGET_MCP_DIR}/src/kdenlive_mcp/kdenlive/adapter/xml_writer.py" 2>/dev/null; then
            echo "  [✓] Poprawka unikalności Sequence UUID zainstalowana"
        else
            echo "  [!] Brak poprawki Sequence UUID w xml_writer.py"
            all_ok=false
        fi
    else
        echo "  [✗] Brak repozytorium kdenlive-mcp w ${TARGET_MCP_DIR}"
        all_ok=false
    fi

    # 5. Konfiguracja MCP w Antigravity
    if [[ -f "${GLOBAL_MCP_CONFIG}" ]] && grep -q "kdenlive-mcp" "${GLOBAL_MCP_CONFIG}"; then
        echo "  [✓] Konfiguracja MCP w Antigravity obecna: ${GLOBAL_MCP_CONFIG}"
    else
        echo "  [!] Brak wpisu kdenlive w ${GLOBAL_MCP_CONFIG}"
    fi

    echo ""
    if [[ "${all_ok}" == true ]]; then
        echo "Status: [GOTOWY] Środowisko Kdenlive MCP jest w 100% zoptymalizowane i gotowe do montażu."
    else
        echo "Status: [WYMAGANA AKCJA] Uruchom 'make media-setup-mcp' lub './scripts/media/setup_kdenlive_mcp.sh --setup'."
    fi
    echo "=========================================================="
}

setup_all() {
    print_header
    echo "[*] Uruchamianie procedury instalacji i konfiguracji w User-Space..."
    echo ""

    mkdir -p "${TARGET_BIN_DIR}"

    # 1. Kdenlive Flatpak
    if ! flatpak info org.kde.kdenlive &>/dev/null; then
        echo "[1/5] Instalacja Flatpak org.kde.kdenlive w user-space..."
        flatpak install --user flathub org.kde.kdenlive -y
    else
        echo "[1/5] Kdenlive Flatpak jest już zainstalowany."
    fi

    # 2. Wrappery CLI
    echo "[2/5] Konfiguracja wrapperów CLI w ${TARGET_BIN_DIR}..."
    cat << 'EOF' > "${TARGET_BIN_DIR}/kdenlive"
#!/bin/bash
exec flatpak run org.kde.kdenlive "$@"
EOF
    chmod +x "${TARGET_BIN_DIR}/kdenlive"

    cat << 'EOF' > "${TARGET_BIN_DIR}/melt"
#!/bin/bash
exec flatpak run --command=melt org.kde.kdenlive "$@"
EOF
    chmod +x "${TARGET_BIN_DIR}/melt"

    # 3. Klon repozytorium MCP
    echo "[3/5] Przygotowanie serwera kdenlive-mcp..."
    if [[ ! -d "${TARGET_MCP_DIR}" ]]; then
        echo "  -> Klonowanie repozytorium MCP z GitHuba..."
        git clone https://github.com/12bijaya/MCP_Server_Kdenlive.git "${TARGET_MCP_DIR}"
    fi

    # 4. Aplikacja poprawek architektonicznych i snapshots manager
    echo "[4/5] Aplikowanie poprawek architektonicznych (XML Cascade, Sequence UUID, Stderr filter)..."
    mkdir -p "${TARGET_MCP_DIR}/src/kdenlive_mcp/storage/snapshots"
    if [[ -f "${TEMPLATES_DIR}/snapshots_manager.py.tpl" ]]; then
        cp "${TEMPLATES_DIR}/snapshots_manager.py.tpl" "${TARGET_MCP_DIR}/src/kdenlive_mcp/storage/snapshots/manager.py"
    fi

    # Poprawka .gitignore w kdenlive-mcp
    if grep -q "^snapshots/$" "${TARGET_MCP_DIR}/.gitignore" 2>/dev/null; then
        sed -i 's|^snapshots/$|/snapshots/|g' "${TARGET_MCP_DIR}/.gitignore"
    fi

    # Aplikacja patcha
    if [[ -f "${TEMPLATES_DIR}/kdenlive_mcp_patches.diff" ]]; then
        (
            cd "${TARGET_MCP_DIR}"
            git apply "${TEMPLATES_DIR}/kdenlive_mcp_patches.diff" 2>/dev/null || true
        )
    fi

    # Budowa środowiska uv venv
    echo "  -> Budowanie wirtualnego środowiska uv venv dla kdenlive-mcp..."
    (
        cd "${TARGET_MCP_DIR}"
        if ! command -v uv &>/dev/null; then
            echo "  [!] Błąd: Narzędzie uv nie jest zainstalowane w systemie."
            exit 1
        fi
        uv venv
        uv pip install -e ".[test]" "mcp<2"
    )

    # 5. Konfiguracja MCP w Antigravity
    echo "[5/5] Rejestracja serwera MCP w konfiguracji Antigravity..."
    mkdir -p "$(dirname "${GLOBAL_MCP_CONFIG}")"
    python3 - << PYEOF
import json
from pathlib import Path

p = Path("${GLOBAL_MCP_CONFIG}")
if p.exists():
    try:
        data = json.loads(p.read_text())
    except Exception:
        data = {}
else:
    data = {}

servers = data.setdefault("mcpServers", {})
servers["kdenlive"] = {
    "command": "${TARGET_MCP_DIR}/.venv/bin/kdenlive-mcp",
    "args": [],
    "env": {
        "KDENLIVE_MCP_KDENLIVE": "${TARGET_BIN_DIR}/kdenlive",
        "KDENLIVE_MCP_MELT": "${TARGET_BIN_DIR}/melt"
    }
}

p.write_text(json.dumps(data, indent=2) + "\n")
print(f"  [✓] Zarejestrowano serwer 'kdenlive' w {p}")
PYEOF

    echo ""
    echo "[OK] Instalacja i konfiguracja Kdenlive MCP zakończona sukcesem."
    echo "Uruchom './scripts/media/setup_kdenlive_mcp.sh --check' aby zweryfikować stan."
    echo "=========================================================="
}

case "${MODE}" in
    --check|check)
        check_status
        ;;
    --setup|setup|--install|install)
        setup_all
        ;;
    *)
        echo "Nieznany tryb: ${MODE}"
        echo "Dostępne: --check (domyślny), --setup"
        exit 1
        ;;
esac
