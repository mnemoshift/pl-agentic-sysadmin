#!/usr/bin/env bash
# ==============================================================================
# Workstation Hub: Kontroler i Instalator GhostShift Neural TTS
# Automatyzuje instalację, konfigurację środowiska venv, skróty GNOME i status.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

VENV_DIR="$HOME/.local/share/ghostshift-tts/venv"
BIN_TARGET="$HOME/.local/bin/ghostshift-tts"
DESKTOP_TARGET="$HOME/.local/share/applications/ghostshift-tts-config.desktop"
CONFIG_FILE="$HOME/.config/ghostshift-tts/config.json"

log_info() { echo -e "\033[1;34m[INFO]\033[0m $*"; }
log_ok()   { echo -e "\033[1;32m[OK]\033[0m $*"; }
log_warn() { echo -e "\033[1;33m[WARN]\033[0m $*"; }
log_err()  { echo -e "\033[1;31m[ERROR]\033[0m $*"; }

check_tool() {
    local cmd="$1"
    local install_pkg="${2:-$1}"
    local install_cmd="${3:-sudo apt install -y $install_pkg}"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        log_err "Brak pakietu/narzędzia '$cmd'. Zainstaluj je poleceniem:\n  $install_cmd"
        return 1
    fi
    return 0
}

detect_session() {
    local session="${XDG_SESSION_TYPE:-}"
    if [ -z "$session" ]; then
        if [ -n "${WAYLAND_DISPLAY:-}" ]; then session="wayland"; else session="x11"; fi
    fi
    echo "$session" | tr '[:upper:]' '[:lower:]'
}

check_dependencies() {
    log_info "Sprawdzanie pakietów systemowych dla czytnika TTS..."
    local missing=()

    command -v mpv >/dev/null 2>&1 || missing+=("mpv")
    command -v zenity >/dev/null 2>&1 || missing+=("zenity")

    local session
    session="$(detect_session)"
    if [ "$session" = "wayland" ]; then
        command -v wl-paste >/dev/null 2>&1 || missing+=("wl-clipboard")
    else
        command -v xclip >/dev/null 2>&1 || missing+=("xclip")
    fi

    python3 -c "import gi" 2>/dev/null || missing+=("python3-gi")

    if [ ${#missing[@]} -gt 0 ]; then
        log_warn "Brakujące pakiety systemowe: ${missing[*]}"
        if [ "$EUID" -eq 0 ]; then
            apt-get update && apt-get install -y "${missing[@]}"
        elif command -v sudo >/dev/null 2>&1; then
            log_info "Instalacja brakujących pakietów przez sudo apt install..."
            sudo apt-get update && sudo apt-get install -y "${missing[@]}"
        else
            log_err "Zainstaluj ręcznie brakujące pakiety: sudo apt install -y ${missing[*]}"
            return 1
        fi
    fi
    log_ok "Wszystkie pakiety systemowe są obecne."
}

setup_venv() {
    log_info "Konfiguracja dedykowanego środowiska venv (~/.local/share/ghostshift-tts/venv)..."
    mkdir -p "$(dirname "$VENV_DIR")"

    if [ ! -d "$VENV_DIR" ]; then
        if command -v uv >/dev/null 2>&1; then
            log_info "Tworzenie środowiska venv przy użyciu uv..."
            uv venv --system-site-packages "$VENV_DIR"
        else
            log_info "Tworzenie środowiska venv przy użyciu python3 -m venv..."
            python3 -m venv --system-site-packages "$VENV_DIR"
        fi
    fi

    log_info "Instalacja pakietu edge-tts w środowisku venv..."
    if command -v uv >/dev/null 2>&1; then
        uv pip install --python "$VENV_DIR/bin/python" "edge-tts>=7.0.0"
    else
        "$VENV_DIR/bin/pip" install --quiet "edge-tts>=7.0.0"
    fi
    log_ok "Środowisko venv i pakiet edge-tts są gotowe."
}

install_bin_and_desktop() {
    log_info "Instalacja skryptu wykonywalnego w ~/.local/bin/..."
    mkdir -p "$HOME/.local/bin"
    cp -f "$REPO_DIR/scripts/ghostshift_tts.py" "$BIN_TARGET"
    chmod +x "$BIN_TARGET"

    log_info "Instalacja launchera menu aplikacji (~/.local/share/applications)..."
    mkdir -p "$HOME/.local/share/applications"
    if [ -f "$REPO_DIR/templates/applications/ghostshift-tts-config.desktop" ]; then
        cp -f "$REPO_DIR/templates/applications/ghostshift-tts-config.desktop" "$DESKTOP_TARGET"
        sed -i "s|Exec=.*|Exec=$BIN_TARGET config|" "$DESKTOP_TARGET"
    fi
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    log_ok "Pliki wykonywalne i launcher zostały zainstalowane."
}

configure_gnome_shortcuts() {
    log_info "Konfiguracja globalnych skrótów klawiszowych GNOME (<Super>+R oraz <Ctrl>+<Alt>+S)..."
    python3 -c "
import ast, subprocess

def get_list():
    try:
        raw = subprocess.check_output(['gsettings', 'get', 'org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings'], text=True).strip()
        l = ast.literal_eval(raw)
        return l if isinstance(l, list) else []
    except Exception:
        return []

def set_list(l):
    subprocess.run(['gsettings', 'set', 'org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings', str(l)], check=False)

def apply_binding(path, name, command, binding):
    schema = f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{path}'
    subprocess.run(['gsettings', 'set', schema, 'name', name], check=False)
    subprocess.run(['gsettings', 'set', schema, 'command', command], check=False)
    subprocess.run(['gsettings', 'set', schema, 'binding', binding], check=False)

bindings = get_list()

path0 = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom_ghostshift_tts0/'
path1 = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom_ghostshift_tts1/'

if path0 not in bindings:
    bindings.append(path0)
if path1 not in bindings:
    bindings.append(path1)

set_list(bindings)
apply_binding(path0, 'GhostShift TTS (Czytaj na głos)', '$BIN_TARGET toggle', '<Super>r')
apply_binding(path1, 'GhostShift TTS (Alternatywny)', '$BIN_TARGET toggle', '<Ctrl><Alt>s')
" 2>/dev/null || true
    log_ok "Globalne skróty klawiszowe zostały zarejestrowane."
}

install_all() {
    echo "=========================================================="
    echo "  INSTALACJA GHOSTSHIFT NEURAL TTS (SELECT & LISTEN)"
    echo "=========================================================="
    check_dependencies
    setup_venv
    install_bin_and_desktop
    configure_gnome_shortcuts

    log_ok "Instalacja zakończona pomyślnie!"
    echo "----------------------------------------------------------"
    echo "Instrukcja użycia:"
    echo "  1. Zaznacz dowolny tekst myszą (w edytorze, terminalu, przeglądarce)."
    echo "  2. Naciśnij <Super> + R (lub <Ctrl> + <Alt> + S) — lektor natychmiast zacznie czytać."
    echo "  3. Ponowne naciśnięcie skrótu natychmiast zatrzymuje czytanie (Toggle)."
    echo "  4. Wybór głosu i prędkości: polecenie 'make tts-config' lub w menu aplikacji."
    echo "=========================================================="
}

show_status() {
    echo "=========================================================="
    echo "  STAN CZYTNIKA GHOSTSHIFT NEURAL TTS"
    echo "=========================================================="
    local session
    session="$(detect_session)"
    echo -n "Serwer wyświetlania:    "
    if [ "$session" = "wayland" ]; then
        echo -e "\033[1;36mWayland (schowek: wl-clipboard / Gtk)\033[0m"
    else
        echo -e "\033[1;34mX11 / Xorg (schowek: Gtk / xclip)\033[0m"
    fi

    echo -n "Skrypt wykonywalny:     "
    if [ -x "$BIN_TARGET" ]; then
        echo -e "\033[1;32m$BIN_TARGET\033[0m"
    else
        echo -e "\033[1;31mBrak ($BIN_TARGET)\033[0m"
    fi

    echo -n "Środowisko venv:        "
    if [ -f "$VENV_DIR/bin/python" ]; then
        echo -e "\033[1;32mAKTYWNE ($VENV_DIR)\033[0m"
    else
        echo -e "\033[1;31mBrak środowiska venv\033[0m"
    fi

    echo -n "Silnik Edge-TTS:        "
    if [ -f "$VENV_DIR/bin/edge-tts" ]; then
        local ver
        ver="$("$VENV_DIR/bin/edge-tts" --version 2>&1 || echo 'ok')"
        echo -e "\033[1;32mZainstalowany ($ver)\033[0m"
    else
        echo -e "\033[1;31mBrak edge-tts w venv\033[0m"
    fi

    echo -n "Odtwarzacz mpv:         "
    if command -v mpv >/dev/null 2>&1; then
        echo -e "\033[1;32m$(mpv --version | head -n 1)\033[0m"
    else
        echo -e "\033[1;31mBrak pakietu mpv\033[0m"
    fi

    echo -n "Konfigurator GUI:       "
    if command -v zenity >/dev/null 2>&1; then
        echo -e "\033[1;32mZenity obecny\033[0m"
    else
        echo -e "\033[1;33mBrak pakietu zenity (brak okna GUI)\033[0m"
    fi

    echo -n "Skrót klawiszowy:       "
    python3 -c "
import ast, subprocess
raw = subprocess.check_output(['gsettings', 'get', 'org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings'], text=True).strip()
try:
    bindings = ast.literal_eval(raw)
except Exception:
    bindings = []
found = False
for b in bindings:
    try:
        cmd = subprocess.check_output(['gsettings', 'get', f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{b}', 'command'], text=True).strip()
        if 'ghostshift-tts' in cmd:
            bind = subprocess.check_output(['gsettings', 'get', f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{b}', 'binding'], text=True).strip()
            print(f'\033[1;32mZAREJESTROWANY ({bind} -> ghostshift-tts)\033[0m')
            found = True
            break
    except Exception:
        pass
if not found:
    print('\033[1;33mNIEZAREJESTROWANY\033[0m')
" 2>/dev/null || echo "Błąd sprawdzania skrótów"

    echo -n "Aktywny głos i tempo:   "
    if [ -f "$CONFIG_FILE" ]; then
        python3 -c "
import json
with open('$CONFIG_FILE') as f:
    c = json.load(f)
print(f\"{c.get('voice', 'N/A')} (tempo: {c.get('rate', '0%')})\")
" 2>/dev/null || echo "Błąd odczytu config.json"
    else
        echo "Domyślny (pl-PL-MarekNeural)"
    fi
    echo "=========================================================="
}

uninstall_all() {
    log_info "Usuwanie integracji GhostShift TTS..."
    rm -f "$BIN_TARGET" "$DESKTOP_TARGET"
    python3 -c "
import ast, subprocess
raw = subprocess.check_output(['gsettings', 'get', 'org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings'], text=True).strip()
try:
    l = ast.literal_eval(raw)
    l = [p for p in l if 'custom_ghostshift_tts' not in p]
    subprocess.run(['gsettings', 'set', 'org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings', str(l)], check=False)
except Exception:
    pass
" 2>/dev/null || true
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    log_ok "Usunięto skróty, pliki wykonywalne i launcher."
}

case "${1:-status}" in
    install)
        install_all
        ;;
    status)
        show_status
        ;;
    config|gui)
        if [ -x "$BIN_TARGET" ]; then
            "$BIN_TARGET" config
        else
            python3 "$REPO_DIR/scripts/ghostshift_tts.py" config
        fi
        ;;
    test)
        if [ -x "$BIN_TARGET" ]; then
            "$BIN_TARGET" read "GhostShift TTS działa poprawnie. Czytnik jest gotowy."
        else
            python3 "$REPO_DIR/scripts/ghostshift_tts.py" read "GhostShift TTS działa poprawnie. Czytnik jest gotowy."
        fi
        ;;
    uninstall)
        uninstall_all
        ;;
    *)
        echo "Użycie: $0 {install|status|config|test|uninstall}"
        exit 1
        ;;
esac
