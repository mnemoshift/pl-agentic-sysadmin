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
# 2. Zarządzanie repozytoriami motywów (WhiteSur, McMojave)
# ------------------------------------------------------------------------------

ensure_theme_repositories() {
    local base_dir="$HOME/repos/zorin-customization"
    mkdir -p "$base_dir"

    # 1. WhiteSur GTK Theme
    if [ ! -d "$base_dir/WhiteSur-gtk-theme" ]; then
        log_info "Klonowanie WhiteSur-gtk-theme z GitHuba..."
        git clone --depth 1 https://github.com/vinceliuice/WhiteSur-gtk-theme.git "$base_dir/WhiteSur-gtk-theme"
    fi
    log_info "Instalacja/aktualizacja motywu WhiteSur GTK..."
    (cd "$base_dir/WhiteSur-gtk-theme" && ./install.sh -m -t default -l -c light >/dev/null 2>&1 || true)

    # 2. WhiteSur Icon Theme
    if [ ! -d "$base_dir/WhiteSur-icon-theme" ]; then
        log_info "Klonowanie WhiteSur-icon-theme z GitHuba..."
        git clone --depth 1 https://github.com/vinceliuice/WhiteSur-icon-theme.git "$base_dir/WhiteSur-icon-theme"
    fi
    log_info "Instalacja motywu ikon WhiteSur..."
    (cd "$base_dir/WhiteSur-icon-theme" && ./install.sh >/dev/null 2>&1 || true)

    # 3. McMojave Cursors
    if [ ! -d "$base_dir/McMojave-cursors" ]; then
        log_info "Klonowanie McMojave-cursors z GitHuba..."
        git clone --depth 1 https://github.com/vinceliuice/McMojave-cursors.git "$base_dir/McMojave-cursors"
    fi
    log_info "Instalacja kursorów McMojave..."
    (cd "$base_dir/McMojave-cursors" && ./install.sh >/dev/null 2>&1 || true)
}

# ------------------------------------------------------------------------------
# 3. Konfiguracja doku Plank (Dual-Dock dla konfiguracji wielomonitorowej)
# ------------------------------------------------------------------------------

configure_plank_dual_dock() {
    log_info "Konfiguracja podwójnego doku Plank (Dual-Dock: DP-4 + HDMI-0)..."

    # Włącz obsługę wielu doków w Plank
    dconf write /net/launchpad/plank/enabled-docks "['dock1', 'dock2']"

    # Dok 1 (Ekran główny Ultrawide / DP-4): wszystkie przypięte aplikacje
    dconf write /net/launchpad/plank/docks/dock1/monitor "'DP-4'"
    dconf write /net/launchpad/plank/docks/dock1/position "'bottom'"
    dconf write /net/launchpad/plank/docks/dock1/alignment "'center'"
    dconf write /net/launchpad/plank/docks/dock1/theme "'Transparent'"
    dconf write /net/launchpad/plank/docks/dock1/zoom-enabled "true"
    dconf write /net/launchpad/plank/docks/dock1/show-dock-item "false"

    # Dok 2 (Ekran nagraniowy 16:9 / HDMI-0): tylko aktywne aplikacje + menu
    dconf write /net/launchpad/plank/docks/dock2/monitor "'HDMI-0'"
    dconf write /net/launchpad/plank/docks/dock2/position "'bottom'"
    dconf write /net/launchpad/plank/docks/dock2/alignment "'center'"
    dconf write /net/launchpad/plank/docks/dock2/theme "'Transparent'"
    dconf write /net/launchpad/plank/docks/dock2/zoom-enabled "true"
    dconf write /net/launchpad/plank/docks/dock2/zoom-percent "150"
    dconf write /net/launchpad/plank/docks/dock2/icon-size "48"
    dconf write /net/launchpad/plank/docks/dock2/hide-mode "'intelligent'"
    dconf write /net/launchpad/plank/docks/dock2/show-dock-item "false"
    dconf write /net/launchpad/plank/docks/dock2/dock-items "['show-applications.dockitem', 'applications.dockitem']"

    # Katalogi konfiguracji doków
    mkdir -p "$HOME/.config/plank/dock1/launchers"
    mkdir -p "$HOME/.config/plank/dock2/launchers"

    # Zapewnij aktywatory menu w dock2
    if [ ! -f "$HOME/.config/plank/dock2/launchers/applications.dockitem" ]; then
        cat << 'EOF' > "$HOME/.config/plank/dock2/launchers/applications.dockitem"
[PlankDockItemPreferences]
Launcher=docklet://applications
EOF
    fi

    if [ -f "$HOME/.local/share/applications/show-applications.desktop" ]; then
        cat << 'EOF' > "$HOME/.config/plank/dock2/launchers/show-applications.dockitem"
[PlankDockItemPreferences]
Launcher=file:///home/jarek/.local/share/applications/show-applications.desktop
EOF
    fi

    # Usuń z doku nagraniowego dock2 zbędne przypięte aplikacje (mają być tylko te aktualnie otwarte na HDMI-0)
    rm -f "$HOME/.config/plank/dock2/launchers/"{antigravity,org.gnome.Terminal,org.gnome.Nautilus,google-chrome,code-url-handler,capcut}.dockitem 2>/dev/null || true

    # Usuń uszkodzony/pusty element capcut z doku głównego dock1
    rm -f "$HOME/.config/plank/dock1/launchers/capcut.dockitem" 2>/dev/null || true
    python3 -c "
import subprocess
try:
    res = subprocess.run(['dconf', 'read', '/net/launchpad/plank/docks/dock1/dock-items'], stdout=subprocess.PIPE, text=True)
    if res.stdout and 'capcut.dockitem' in res.stdout:
        val = res.stdout.strip()
        items = eval(val)
        items = [x for x in items if x != 'capcut.dockitem']
        subprocess.run(['dconf', 'write', '/net/launchpad/plank/docks/dock1/dock-items', str(items)], check=False)
except Exception:
    pass
" 2>/dev/null || true

    # Autostart i usługa systemd
    mkdir -p "$HOME/.config/autostart"
    if [ -f /usr/share/applications/plank.desktop ]; then
        cp /usr/share/applications/plank.desktop "$HOME/.config/autostart/" 2>/dev/null || true
    fi

    if systemctl --user list-unit-files plank.service 2>/dev/null | grep -q "plank.service"; then
        log_info "Restartowanie usługi Plank przez systemd user service..."
        systemctl --user enable plank.service 2>/dev/null || true
        systemctl --user restart plank.service 2>/dev/null || systemctl --user start plank.service 2>/dev/null || true
    else
        killall plank 2>/dev/null || true
        nohup plank >/dev/null 2>&1 &
        sleep 0.5
    fi
}

# ------------------------------------------------------------------------------
# 4. Konfiguracja górnego paska Zorin OS w stylu macOS
# ------------------------------------------------------------------------------

configure_zorin_top_panel() {
    log_info "Konfiguracja smukłego paska górnego w stylu macOS (bez apek, zegar na środku, menu Zorin)..."
    gnome-extensions enable zorin-taskbar@zorinos.com 2>/dev/null || true
    gnome-extensions enable zorin-menu@zorinos.com 2>/dev/null || true

    # Pozycja TOP na wszystkich monitorach
    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-position 'TOP' 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar multi-monitors true 2>/dev/null || true

    # Likwidacja drugiego pustego paska GNOME (stockgs-keep-top-panel=false)
    gsettings set org.gnome.shell.extensions.zorin-taskbar stockgs-keep-top-panel false 2>/dev/null || true

    # Smukła wysokość a la macOS (28px zamiast 48px) oraz brak marginesu
    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-size 28 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-margin 0 2>/dev/null || true

    # Ukrycie aplikacji w pasku (aplikacje są w doku Plank na dole)
    gsettings set org.gnome.shell.extensions.zorin-taskbar show-running-apps false 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar show-favorites false 2>/dev/null || true

    # Rozmieszczenie elementów w pasku:
    # Lewa strona: leftBox (menu Zorin)
    # Środek: dateMenu (zegar i data w centrum ekranu - styl macOS)
    # Prawa strona: systemMenu (zasilanie, sieć, głośność) + rightBox (tacka)
    # Wyłączone: taskbar (okna/apki), showAppsButton, activitiesButton, desktopButton
    python3 -c "
import json, subprocess
keys = ['0', '1']
try:
    import dbus
    bus = dbus.SessionBus()
    proxy = bus.get_object('org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig')
    iface = dbus.Interface(proxy, 'org.gnome.Mutter.DisplayConfig')
    serial, monitors, logical_monitors, properties = iface.GetCurrentState()
    for i, lm in enumerate(logical_monitors):
        keys.append(str(i))
        mon = lm[5][0]
        connector, vendor, product, mon_serial = mon[0], mon[1], mon[2], mon[3]
        if vendor and mon_serial:
            keys.append(f'{vendor}-{mon_serial}')
        if connector:
            keys.append(str(connector))
except Exception:
    pass
keys = list(set(keys))

elements = [
    {'element': 'showAppsButton', 'visible': False, 'position': 'stackedTL'},
    {'element': 'activitiesButton', 'visible': False, 'position': 'stackedTL'},
    {'element': 'leftBox', 'visible': True, 'position': 'stackedTL'},
    {'element': 'taskbar', 'visible': False, 'position': 'stackedTL'},
    {'element': 'dateMenu', 'visible': True, 'position': 'centerMonitor'},
    {'element': 'centerBox', 'visible': False, 'position': 'stackedBR'},
    {'element': 'systemMenu', 'visible': True, 'position': 'stackedBR'},
    {'element': 'rightBox', 'visible': True, 'position': 'stackedBR'},
    {'element': 'desktopButton', 'visible': False, 'position': 'stackedBR'}
]

pos_dict = {k: 'TOP' for k in keys}
size_dict = {k: 28 for k in keys}
elem_dict = {k: elements for k in keys}

subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.zorin-taskbar', 'panel-positions', json.dumps(pos_dict)], check=False)
subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.zorin-taskbar', 'panel-sizes', json.dumps(size_dict)], check=False)
subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.zorin-taskbar', 'panel-element-positions', json.dumps(elem_dict)], check=False)
subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.zorin-taskbar', 'panel-element-positions-monitors-sync', 'true'], check=False)
" 2>/dev/null || true
}

# ------------------------------------------------------------------------------
# 5. Wdrażanie profilu macOS (apply-macos)
# ------------------------------------------------------------------------------

apply_macos() {
    log_info "Wdrażanie profilu pulpitu macOS (WhiteSur)..."

    # 1. Sprawdzenie, klonowanie i instalacja motywów z GitHuba
    ensure_theme_repositories

    local gtk_theme="WhiteSur-Light"
    local icon_theme="WhiteSur-light"
    local cursor_theme="McMojave-cursors"

    # 2. GNOME / Mutter ustawienia
    log_info "Konfiguracja motywów i kursora GNOME..."
    gsettings set org.gnome.desktop.interface gtk-theme "$gtk_theme" || true
    gsettings set org.gnome.desktop.interface icon-theme "$icon_theme" || true
    gsettings set org.gnome.desktop.interface cursor-theme "$cursor_theme" || true
    gsettings set org.gnome.shell.extensions.user-theme name "$gtk_theme" 2>/dev/null || true

    # 3. Kropki okien (traffic lights) po LEWEJ stronie
    log_info "Ustawianie kontrolek okien (traffic lights) po lewej stronie..."
    gsettings set org.gnome.desktop.wm.preferences button-layout 'close,minimize,maximize:'

    # 4. Konfiguracja smukłego paska Zorin na górze ekranu (macOS menu bar)
    configure_zorin_top_panel

    # 5. Uruchomienie i konfiguracja podwójnego doku Plank na dole
    configure_plank_dual_dock

    # 6. Unifikacja aplikacji CSD (VS Code & Google Chrome)
    log_info "Wymuszanie natywnej belki okna w VS Code i Google Chrome..."
    configure_vscode_csd "native"
    configure_chrome_csd "true"

    log_ok "Profil macOS został pomyślnie zaaplikowany."
}

# ------------------------------------------------------------------------------
# 6. Przywracanie stanu domyślnego (reset / vanilla Zorin)
# ------------------------------------------------------------------------------

reset_defaults() {
    log_info "Przywracanie domyślnych ustawień pulpitu Zorin OS (Vanilla Reset)..."

    # 1. Włączenie natywnych rozszerzeń paska zadań i menu Zorina (Layout 1 / Windows Style)
    log_info "Włączanie rozszerzeń paska i menu Zorina..."
    gnome-extensions enable zorin-taskbar@zorinos.com 2>/dev/null || true
    gnome-extensions enable zorin-menu@zorinos.com 2>/dev/null || true

    # 2. Kropki okien na prawą stronę
    log_info "Przywracanie kontrolek okien na prawą stronę..."
    gsettings set org.gnome.desktop.wm.preferences button-layout 'appmenu:minimize,maximize,close'

    # 3. Pasek systemowy na dół ekranu (na wszystkich monitorach, standardowa wysokość 48px)
    log_info "Konfiguracja dolnego paska zadań Zorina..."
    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-position 'BOTTOM' 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar multi-monitors true 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar stockgs-keep-top-panel false 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-size 48 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-margin 4 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar show-running-apps true 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar show-favorites true 2>/dev/null || true

    python3 -c "
import json, subprocess
keys = ['0', '1']
try:
    import dbus
    bus = dbus.SessionBus()
    proxy = bus.get_object('org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig')
    iface = dbus.Interface(proxy, 'org.gnome.Mutter.DisplayConfig')
    serial, monitors, logical_monitors, properties = iface.GetCurrentState()
    for i, lm in enumerate(logical_monitors):
        keys.append(str(i))
        mon = lm[5][0]
        connector, vendor, product, mon_serial = mon[0], mon[1], mon[2], mon[3]
        if vendor and mon_serial:
            keys.append(f'{vendor}-{mon_serial}')
        if connector:
            keys.append(str(connector))
except Exception:
    pass
keys = list(set(keys))
pos_dict = {k: 'BOTTOM' for k in keys}
size_dict = {k: 48 for k in keys}
subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.zorin-taskbar', 'panel-positions', json.dumps(pos_dict)], check=False)
subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.zorin-taskbar', 'panel-sizes', json.dumps(size_dict)], check=False)
subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.zorin-taskbar', 'panel-element-positions', '{}'], check=False)
subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.zorin-taskbar', 'panel-element-positions-monitors-sync', 'true'], check=False)
" 2>/dev/null || true

    # 4. Motyw Zorin domyślny
    log_info "Przywracanie motywów fabrycznych Zorina..."
    gsettings set org.gnome.desktop.interface gtk-theme 'ZorinBlue-Light' || true
    gsettings set org.gnome.desktop.interface icon-theme 'ZorinBlue-Light' || true
    gsettings set org.gnome.desktop.interface cursor-theme 'Zorin' || true
    gsettings reset org.gnome.desktop.wm.preferences theme 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.user-theme name '' 2>/dev/null || true

    # 5. Odinstalowanie nadpisań motywów WhiteSur (GTK, ikony, kursory, GTK4 / libadwaita)
    log_info "Usuwanie nadpisań motywów WhiteSur (GTK, ikony, kursory, GTK4)..."
    if [ -f "$HOME/repos/zorin-customization/WhiteSur-gtk-theme/install.sh" ]; then
        "$HOME/repos/zorin-customization/WhiteSur-gtk-theme/install.sh" -u >/dev/null 2>&1 || true
    fi
    if [ -f "$HOME/repos/zorin-customization/WhiteSur-icon-theme/install.sh" ]; then
        "$HOME/repos/zorin-customization/WhiteSur-icon-theme/install.sh" -u >/dev/null 2>&1 || true
    fi
    rm -rf "$HOME/.themes/WhiteSur"* 2>/dev/null || true
    rm -rf "$HOME/.local/share/icons/WhiteSur"* 2>/dev/null || true
    rm -rf "$HOME/.local/share/icons/McMojave"* 2>/dev/null || true
    rm -rf "$HOME/.config/gtk-4.0/"* 2>/dev/null || true
    rm -f "$HOME/.config/gtk-3.0/settings.ini" 2>/dev/null || true
    rm -f "$HOME/.config/kdeglobals" 2>/dev/null || true

    # 6. Zatrzymanie Planka (proces + systemd) i usunięcie z autostartu
    log_info "Wyłączanie doku Plank..."
    killall -9 plank 2>/dev/null || true
    systemctl --user stop plank.service 2>/dev/null || true
    systemctl --user disable plank.service 2>/dev/null || true
    rm -f "$HOME/.config/autostart/plank.desktop"

    # 7. Przywrócenie CSD dla VS Code i Chrome
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
    echo -n "Wysokość paska Zorina:  "
    local psize
    psize=$(gsettings get org.gnome.shell.extensions.zorin-taskbar panel-size 2>/dev/null || echo "48")
    echo "${psize}px"
    echo -n "Aplikacje w pasku:      "
    local show_apps
    show_apps=$(gsettings get org.gnome.shell.extensions.zorin-taskbar show-running-apps 2>/dev/null || echo "true")
    if [ "$show_apps" = "false" ]; then
        echo -e "\033[1;32mUkryte (przeniesione do doku Plank)\033[0m"
    else
        echo -e "\033[1;33mWidoczne (domyślny taskbar)\033[0m"
    fi
    echo -n "Układ zegara i daty:    "
    local elem_pos
    elem_pos=$(gsettings get org.gnome.shell.extensions.zorin-taskbar panel-element-positions 2>/dev/null || echo "")
    if [[ "$elem_pos" == *"centerMonitor"* ]]; then
        echo -e "\033[1;32mWyśrodkowany (macOS / GNOME)\033[0m"
    else
        echo -e "\033[1;33mDomyślny (po prawej)\033[0m"
    fi
    echo -n "Motyw GTK:              "
    gsettings get org.gnome.desktop.interface gtk-theme
    echo -n "Motyw ikon:             "
    gsettings get org.gnome.desktop.interface icon-theme
    echo -n "Kursor myszy:           "
    gsettings get org.gnome.desktop.interface cursor-theme
    echo -n "Rozszerzenie user-theme:"
    gsettings get org.gnome.shell.extensions.user-theme name 2>/dev/null || echo "N/A"
    echo -n "Dok Plank aktywny:      "
    if pgrep -x "plank" >/dev/null; then
        echo -e "\033[1;32mTAK (PID $(pgrep -x plank))\033[0m"
    else
        echo -e "\033[1;33mNIE (nieaktywny)\033[0m"
    fi
    echo -n "Plank w systemd:        "
    if systemctl --user is-active plank.service 2>/dev/null | grep -q "^active"; then
        echo -e "\033[1;32mACTIVE (enabled: $(systemctl --user is-enabled plank.service 2>/dev/null || echo 'no'))\033[0m"
    else
        echo -e "\033[1;33mINACTIVE / DISABLED\033[0m"
    fi
    echo -n "Plank w autostarcie:    "
    if [ -f "$HOME/.config/autostart/plank.desktop" ]; then
        echo -e "\033[1;32mTAK\033[0m"
    else
        echo -e "\033[1;33mNIE\033[0m"
    fi
    echo -n "Plank multi-dock:      "
    local enabled_docks
    enabled_docks=$(dconf read /net/launchpad/plank/enabled-docks 2>/dev/null || echo "N/A")
    echo "$enabled_docks"
    if [[ "$enabled_docks" == *"dock1"* ]]; then
        local m1
        m1=$(dconf read /net/launchpad/plank/docks/dock1/monitor 2>/dev/null || echo "domyślny")
        local count1
        count1=$(ls -1 "$HOME/.config/plank/dock1/launchers" 2>/dev/null | wc -l)
        echo "  -> dock1 (Monitor: $m1, przypiętych: $count1)"
    fi
    if [[ "$enabled_docks" == *"dock2"* ]]; then
        local m2
        m2=$(dconf read /net/launchpad/plank/docks/dock2/monitor 2>/dev/null || echo "domyślny")
        local count2
        count2=$(ls -1 "$HOME/.config/plank/dock2/launchers" 2>/dev/null | wc -l)
        echo "  -> dock2 (Monitor: $m2, aktywatorów: $count2 — tylko otwarte okna + menu)"
    fi
    echo -n "Style GTK4 / libadwaita:"
    if [ -f "$HOME/.config/gtk-4.0/gtk.css" ]; then
        echo -e "\033[1;35mWhiteSur Overrides Obecne\033[0m"
    else
        echo -e "\033[1;32mCzysty stan domyślny\033[0m"
    fi
    echo -n "Motywy w ~/.themes:     "
    if [ -d "$HOME/.themes/WhiteSur-Light" ]; then
        echo -e "\033[1;35mWhiteSur zainstalowany\033[0m"
    else
        echo -e "\033[1;32mCzysty stan domyślny\033[0m"
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
