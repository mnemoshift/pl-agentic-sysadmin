#!/usr/bin/env bash
# scripts/session_ctl.sh — Kontroler pamięci sesyjnej Workstation Hub
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MEMORY_DIR="${REPO_ROOT}/memory"
STATE_FILE="${MEMORY_DIR}/SESSION_STATE.md"
JOURNAL_FILE="${MEMORY_DIR}/JOURNAL.md"

mkdir -p "${MEMORY_DIR}"

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

usage() {
    echo "Użycie: $0 {status|log <komunikat>|check}"
    echo ""
    echo "Polecenia:"
    echo "  status            Wyświetla aktywny stan sesji"
    echo "  log \"<komunikat>\" Doprowadza wpis ze znacznikiem czasu do dziennika"
    echo "  check             Weryfikuje poprawność plików pamięci"
    exit 1
}

cmd_status() {
    if [[ ! -f "${STATE_FILE}" ]]; then
        echo "[BŁĄD] Brak pliku stanu: ${STATE_FILE}"
        exit 1
    fi
    echo "========================================================"
    echo "  AKTUALNY STAN SESJI (${STATE_FILE})"
    echo "========================================================"
    cat "${STATE_FILE}"
}

cmd_log() {
    local msg="${1:-}"
    if [[ -z "${msg}" ]]; then
        echo "[BŁĄD] Wymagana treść wpisu: $0 log \"Treść wpisu...\""
        exit 1
    fi

    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S %Z')"

    if [[ ! -f "${JOURNAL_FILE}" ]]; then
        cat << 'EOF' > "${JOURNAL_FILE}"
# Dziennik Zdarzeń i Audytów (JOURNAL.md)

Chronologiczny rejestr wszystkich sesji, wykonanych audytów, zmian konfiguracji i decyzji architektonicznych stacji roboczej.

---
EOF
    fi

    cat << EOF >> "${JOURNAL_FILE}"

## [${timestamp}] - Aktualizacja Dziennika
- **Autor / Agent**: Antigravity SysAdmin
- **Wpis**:
${msg}
EOF

    echo "[OK] Zapisano wpis w ${JOURNAL_FILE} (${timestamp})"
}

cmd_check() {
    local errors=0
    echo "Sprawdzanie integralności pamięci..."
    if [[ -f "${STATE_FILE}" ]]; then
        echo "  [✓] SESSION_STATE.md istnieje ($(wc -l < "${STATE_FILE}") linii)"
    else
        echo "  [✗] Brak SESSION_STATE.md"
        errors=$((errors + 1))
    fi

    if [[ -f "${JOURNAL_FILE}" ]]; then
        echo "  [✓] JOURNAL.md istnieje ($(wc -l < "${JOURNAL_FILE}") linii)"
    else
        echo "  [✗] Brak JOURNAL.md"
        errors=$((errors + 1))
    fi

    if [[ ${errors} -eq 0 ]]; then
        echo "[OK] Wszystkie pliki pamięci są poprawne."
    else
        echo "[BŁĄD] Wykryto ${errors} problemów z plikami pamięci."
        exit 1
    fi
}

case "${1:-}" in
    status)
        cmd_status
        ;;
    log)
        shift
        cmd_log "$*"
        ;;
    check)
        cmd_check
        ;;
    *)
        usage
        ;;
esac
