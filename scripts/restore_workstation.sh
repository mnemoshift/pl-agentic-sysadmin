#!/usr/bin/env bash
# scripts/restore_workstation.sh — Skrypt automatycznego odtwarzania stacji roboczej (Disaster Recovery)
# Przeznaczenie: Odtworzenie stanu systemu po czystej instalacji Zorin OS 18.1 / Ubuntu 24.04 LTS Noble
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INVENTORY_DIR="${REPO_ROOT}/inventory"
PKG_DIR="${INVENTORY_DIR}/pkg-lists"
APT_MANUAL_FILE="${PKG_DIR}/apt-manual.txt"
FLATPAK_FILE="${PKG_DIR}/flatpak.txt"

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

DRY_RUN=false
MODE="all"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --repos-only)
            MODE="repos"
            shift
            ;;
        --pkgs-only)
            MODE="pkgs"
            shift
            ;;
        --flatpaks-only)
            MODE="flatpaks"
            shift
            ;;
        --help|-h)
            echo "Użycie: $0 [--dry-run] [--repos-only|--pkgs-only|--flatpaks-only]"
            exit 0
            ;;
        *)
            echo "Nieznana flaga: $1"
            exit 1
            ;;
    esac
done

exec_cmd() {
    local cmd="$*"
    if [[ "${DRY_RUN}" == "true" ]]; then
        echo "  [DRY-RUN] ${cmd}"
    else
        echo "  [EXEC] ${cmd}"
        eval "${cmd}"
    fi
}

echo "=========================================================="
echo "  WORKSTATION HUB — PROCEDURA DISASTER RECOVERY"
echo "  Tryb: ${MODE} | Dry-run: ${DRY_RUN}"
echo "=========================================================="

if [[ "${DRY_RUN}" != "true" && $EUID -ne 0 ]]; then
    echo "[UWAGA] Uruchamianie w trybie modyfikacji wymaga uprawnień roota (sudo)."
    echo "Jeśli wymagane będzie sudo, zostaniesz poproszony o hasło."
fi

# Krok 1: Weryfikacja repozytoriów i kluczy
if [[ "${MODE}" == "all" || "${MODE}" == "repos" ]]; then
    echo ""
    echo "[Krok 1/5] Konfiguracja zewnętrznych repozytoriów..."
    
    # Podstawowe narzędzia do pobierania kluczy
    exec_cmd "sudo apt update && sudo apt install -y curl wget gpg ca-certificates lsb-release gnupg"

    # Docker
    echo "  -> Konfiguracja Docker Official Repo..."
    exec_cmd "sudo install -m 0755 -d /etc/apt/keyrings"
    exec_cmd "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg"
    exec_cmd 'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null'

    # VS Code
    echo "  -> Konfiguracja Microsoft VS Code Repo..."
    exec_cmd "wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | sudo tee /etc/apt/keyrings/packages.microsoft.gpg > /dev/null"
    exec_cmd 'echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" | sudo tee /etc/apt/sources.list.d/vscode.list > /dev/null'

    # NVIDIA Container Toolkit
    echo "  -> Konfiguracja NVIDIA Container Toolkit..."
    exec_cmd "curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg"
    exec_cmd 'curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed "s#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g" | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null'

    # Brave Browser
    echo "  -> Konfiguracja Brave Browser..."
    exec_cmd "sudo curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg"
    exec_cmd 'echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg] https://brave-browser-apt-release.s3.brave.com/ stable main" | sudo tee /etc/apt/sources.list.d/brave-browser-release.list > /dev/null'

    # Google Chrome
    echo "  -> Konfiguracja Google Chrome..."
    exec_cmd "wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor --yes -o /usr/share/keyrings/google-chrome-keyring.gpg"
    exec_cmd 'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list > /dev/null'

    exec_cmd "sudo apt update"
fi

# Krok 2: Instalacja pakietów APT
if [[ "${MODE}" == "all" || "${MODE}" == "pkgs" ]]; then
    echo ""
    echo "[Krok 2/5] Odtwarzanie pakietów APT (Manual list)..."
    if [[ -f "${APT_MANUAL_FILE}" ]]; then
        echo "  Wykryto listę z $(wc -l < "${APT_MANUAL_FILE}") pakietami w ${APT_MANUAL_FILE}."
        exec_cmd "sudo xargs -a ${APT_MANUAL_FILE} apt install -y --ignore-missing"
    else
        echo "  [OSTRZEŻENIE] Brak pliku ${APT_MANUAL_FILE}. Instaluję zestaw bazowy..."
        exec_cmd "sudo apt install -y build-essential git curl wget jq make htop iotop inxi python3-pip python3-venv docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin nvidia-container-toolkit"
    fi
fi

# Krok 3: Konfiguracja Flatpak i instalacja aplikacji Flathub
if [[ "${MODE}" == "all" || "${MODE}" == "flatpaks" ]]; then
    echo ""
    echo "[Krok 3/5] Odtwarzanie aplikacji Flatpak..."
    exec_cmd "sudo apt install -y flatpak"
    exec_cmd "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"

    # Kluczowe aplikacje ze stacji roboczej
    CORE_FLATPAKS=(
        "com.obsproject.Studio"
        "com.obsproject.Studio.Plugin.SourceRecord"
        "com.spotify.Client"
        "md.obsidian.Obsidian"
        "org.kde.kdenlive"
        "org.keepassxc.KeePassXC"
        "org.onlyoffice.desktopeditors"
        "org.freedesktop.LinuxAudio.Plugins.TAP"
        "org.freedesktop.LinuxAudio.Plugins.swh"
    )

    for app in "${CORE_FLATPAKS[@]}"; do
        echo "  -> Instalacja Flatpak: ${app}"
        exec_cmd "flatpak install -y --noninteractive flathub ${app}"
    done
fi

# Krok 4: Weryfikacja punktów montowania dysków
if [[ "${MODE}" == "all" ]]; then
    echo ""
    echo "[Krok 4/5] Sprawdzenie struktury dysków i katalogów montowania..."
    MOUNT_DIRS=("/mnt/c" "/mnt/d" "/mnt/e" "/mnt/f")
    for m in "${MOUNT_DIRS[@]}"; do
        if [[ ! -d "$m" ]]; then
            echo "  Tworzenie punktu montowania: $m"
            exec_cmd "sudo mkdir -p $m"
        else
            echo "  Punkt montowania istnieje: $m"
        fi
    done
fi

# Krok 5: Weryfikacja powdrożeniowa
if [[ "${MODE}" == "all" ]]; then
    echo ""
    echo "[Krok 5/5] Weryfikacja powdrożeniowa (Post-flight check)..."
    echo "  Sprawdzanie stanu stacji..."
    exec_cmd "make check"
    exec_cmd "make audit"
fi

echo ""
echo "=========================================================="
echo "  Procedura odtwarzania stacji roboczej zakończona."
echo "=========================================================="
