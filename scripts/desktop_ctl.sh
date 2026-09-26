#!/usr/bin/env bash
# ==============================================================================
# WORKSTATION HUB: Desktop Profile Controller
# Zarządzanie profilem pulpitu: styl macOS (WhiteSur), reset do vanilla Zorin,
# konfiguracja menedżera okien (Mutter) oraz aplikacji CSD (VS Code, Chrome).
# ==============================================================================

set -euo pipefail

log_info() {
    echo -e "\033[1;34m[INFO]\033[0m $*"
}

log_ok() {
    echo -e "\033[1;32m[OK]\033[0m $*"
}

log_warn() {
    echo -e "\033[1;33m[WARN]\033[0m $*"
}

log_err() {
    echo -e "\033[1;31m[ERROR]\033[0m $*"
}

# ------------------------------------------------------------------------------
# 1. Konfiguracja aplikacji CSD (Client-Side Decoration: VS Code, Chrome)
# ------------------------------------------------------------------------------

configure_vscode_csd() {
    local mode="${1:-native}" # "native" lub "custom"
    local settings_file="$HOME/.config/Code/User/settings.json"

    mkdir -p "$(dirname "$settings_file")"
    if [ ! -f "$settings_file" ]; then
        echo "{}" > "$settings_file"
    fi

    python3 -c "
import json, sys

path = '$settings_file'
mode = '$mode'
try:
    with open(path, 'r') as f:
        content = f.read().strip()
        data = json.loads(content) if content else {}
    if mode == 'native':
        data['window.titleBarStyle'] = 'native'
    else:
        data.pop('window.titleBarStyle', None)
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)
    print(f'VS Code titleBarStyle -> {mode}')
except Exception as e:
    print(f'Błąd aktualizacji VS Code: {e}', file=sys.stderr)
"
}

configure_chrome_csd() {
    local use_system="${1:-true}" # true = systemowa belka, false = CSD Chrome
    local custom_frame
    if [ "$use_system" = "true" ]; then
        custom_frame="False"
    else
        custom_frame="True"
    fi

    python3 -c "
import json, glob, os

profiles = glob.glob(os.path.expanduser('~/.config/google-chrome/*/Preferences'))
for path in profiles:
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        if 'browser' not in data:
            data['browser'] = {}
        data['browser']['custom_chrome_frame'] = $custom_frame
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        prof_name = os.path.basename(os.path.dirname(path))
        print(f'Chrome [{prof_name}] custom_chrome_frame -> $custom_frame')
    except Exception as e:
        pass
"
}

# ------------------------------------------------------------------------------
# 2. Wdrażanie profilu macOS (apply-macos)
# ------------------------------------------------------------------------------

apply_macos() {
    log_info "Wdrażanie profilu pulpitu macOS (WhiteSur)..."

    # 1. Sprawdzenie i instalacja motywu WhiteSur jeśli dostępny w ~/repos
    local gtk_theme="WhiteSur-Light"
    local icon_theme="WhiteSur-light"
    local cursor_theme="McMojave-cursors"

    if [ -d "$HOME/repos/zorin-customization/WhiteSur-gtk-theme" ]; then
        log_info "Aktualizacja motywu WhiteSur GTK..."
        (cd "$HOME/repos/zorin-customization/WhiteSur-gtk-theme" && ./install.sh -m -t default >/dev/null 2>&1 || true)
    fi

    # 2. GNOME / Mutter ustawienia
    log_info "Konfiguracja motywów i kursora GNOME..."
    gsettings set org.gnome.desktop.interface gtk-theme "$gtk_theme" || true
    gsettings set org.gnome.desktop.interface icon-theme "$icon_theme" || true
    gsettings set org.gnome.desktop.interface cursor-theme "$cursor_theme" || true
    gsettings set org.gnome.shell.extensions.user-theme name "$gtk_theme" 2>/dev/null || true

    # 3. Kropki okien (traffic lights) po LEWEJ stronie
    log_info "Ustawianie kontrolek okien (traffic lights) po lewej stronie..."
    gsettings set org.gnome.desktop.wm.preferences button-layout 'close,minimize,maximize:'

    # 4. Przeniesienie paska Zorin na górę (jak w macOS / likwidacja kolizji z dokiem)
    log_info "Przenoszenie paska systemowego Zorina na górę..."
    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-position 'TOP' 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-positions '{"0":"TOP","1":"TOP"}' 2>/dev/null || true

    # 5. Uruchomienie i autostart doku Plank na dole
    log_info "Konfiguracja doku Plank..."
    mkdir -p "$HOME/.config/autostart"
    if [ -f /usr/share/applications/plank.desktop ]; then
        cp /usr/share/applications/plank.desktop "$HOME/.config/autostart/" 2>/dev/null || true
    fi
    if ! pgrep -x "plank" >/dev/null; then
        nohup plank >/dev/null 2>&1 &
        sleep 0.5
    fi

    # 6. Unifikacja aplikacji CSD (VS Code & Google Chrome)
    log_info "Wymuszanie natywnej belki okna w VS Code i Google Chrome..."
    configure_vscode_csd "native"
    configure_chrome_csd "true"

    log_ok "Profil macOS został pomyślnie zaaplikowany."
}

# ------------------------------------------------------------------------------
# 3. Przywracanie stanu domyślnego (reset / vanilla Zorin)
# ------------------------------------------------------------------------------

reset_defaults() {
    log_info "Przywracanie domyślnych ustawień pulpitu Zorin OS (Vanilla Reset)..."

    # 1. Kropki okien na prawą stronę
    log_info "Przywracanie kontrolek okien na prawą stronę..."
    gsettings set org.gnome.desktop.wm.preferences button-layout 'appmenu:minimize,maximize,close'

    # 2. Pasek systemowy na dół ekranu
    log_info "Przenoszenie paska systemowego na dół..."
    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-position 'BOTTOM' 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-positions '{"0":"BOTTOM","1":"BOTTOM"}' 2>/dev/null || true

    # 3. Motyw Zorin domyślny
    log_info "Przywracanie motywów fabrycznych Zorina..."
    gsettings set org.gnome.desktop.interface gtk-theme 'ZorinBlue-Light' || true
    gsettings set org.gnome.desktop.interface icon-theme 'ZorinBlue-Light' || true
    gsettings set org.gnome.desktop.interface cursor-theme 'Zorin' || true
    gsettings reset org.gnome.shell.extensions.user-theme name 2>/dev/null || true

    # 4. Zatrzymanie Planka i usunięcie z autostartu
    log_info "Wyłączanie doku Plank..."
    killall plank 2>/dev/null || true
    rm -f "$HOME/.config/autostart/plank.desktop"

    # 5. Przywrócenie CSD dla VS Code i Chrome
    log_info "Przywracanie domyślnych nagłówków w VS Code i Chrome..."
    configure_vscode_csd "custom"
    configure_chrome_csd "false"

    log_ok "Pulpit został zresetowany do stanu fabrycznego Zorin OS."
}

# ------------------------------------------------------------------------------
# 4. Podgląd bieżącego stanu (status)
# ------------------------------------------------------------------------------

show_status() {
    echo "=========================================================="
    echo "  WORKSTATION HUB: STAN KONFIGURACJI PULPITU"
    echo "=========================================================="
    echo -n "Układ przycisków okien: "
    gsettings get org.gnome.desktop.wm.preferences button-layout
    echo -n "Pozycja paska Zorina:   "
    gsettings get org.gnome.shell.extensions.zorin-taskbar panel-position 2>/dev/null || echo "N/A"
    echo -n "Motyw GTK:              "
    gsettings get org.gnome.desktop.interface gtk-theme
    echo -n "Motyw ikon:             "
    gsettings get org.gnome.desktop.interface icon-theme
    echo -n "Kursor myszy:           "
    gsettings get org.gnome.desktop.interface cursor-theme
    echo -n "Dok Plank aktywny:      "
    if pgrep -x "plank" >/dev/null; then
        echo -e "\033[1;32mTAK (PID $(pgrep -x plank))\033[0m"
    else
        echo -e "\033[1;33mNIE\033[0m"
    fi
    echo -n "Plank w autostarcie:    "
    if [ -f "$HOME/.config/autostart/plank.desktop" ]; then
        echo -e "\033[1;32mTAK\033[0m"
    else
        echo -e "\033[1;33mNIE\033[0m"
    fi
    echo "=========================================================="
}

# ------------------------------------------------------------------------------
# Główny dyspozytor
# ------------------------------------------------------------------------------

case "${1:-status}" in
    apply-macos)
        apply_macos
        ;;
    reset)
        reset_defaults
        ;;
    status)
        show_status
        ;;
    *)
        echo "Użycie: $0 {apply-macos|reset|status}"
        exit 1
        ;;
esac
