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

detect_display_server() {
    local session="${XDG_SESSION_TYPE:-}"
    if [ -z "$session" ]; then
        if [ -n "${WAYLAND_DISPLAY:-}" ]; then
            session="wayland"
        elif [ -n "${DISPLAY:-}" ]; then
            session="x11"
        else
            session="$(loginctl show-session "$(loginctl show-user "$(whoami)" -p Display --value 2>/dev/null)" -p Type --value 2>/dev/null || echo "wayland")"
        fi
    fi
    echo "$session" | tr '[:upper:]' '[:lower:]'
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

check_tool() {
    local cmd="$1"
    local install_pkg="${2:-$1}"
    local install_cmd="${3:-sudo apt install -y $install_pkg}"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        log_err "Brak pakietu/narzędzia '$cmd'. Zainstaluj go poleceniem:\n  $install_cmd"
        return 1
    fi
    return 0
}

ensure_hardware_inventory() {
    local inv_json="$REPO_ROOT/inventory/hardware.json"
    if [ ! -f "$inv_json" ] || ! python3 -c "import json; d=json.load(open('$inv_json')); assert 'displays' in d and d['displays']" 2>/dev/null; then
        log_info "Brak spopulowanego inventory/hardware.json. Uruchamianie procedury audytu sprzętowego..."
        "$REPO_ROOT/scripts/audit_hardware.sh" >/dev/null 2>&1 || true
    fi
}

detect_displays() {
    ensure_hardware_inventory
    local inv_json="$REPO_ROOT/inventory/hardware.json"

    local prim_detected=""
    local sec_detected=""

    # 1. Detekcja monitorów w sesjach Wayland lub przy obecności tylko XWAYLAND0
    local is_wayland=false
    if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
        is_wayland=true
    elif command -v xrandr >/dev/null 2>&1; then
        local xrandr_check=()
        mapfile -t xrandr_check < <(xrandr --query 2>/dev/null | grep -E " connected" | awk '{print $1}')
        if [ ${#xrandr_check[@]} -eq 1 ] && [ "${xrandr_check[0]}" = "XWAYLAND0" ]; then
            is_wayland=true
        fi
    fi

    if [ "$is_wayland" = true ]; then
        local drm_mons=()
        mapfile -t drm_mons < <(find /sys/class/drm/ -maxdepth 1 -name "card*-*" -exec sh -c 'grep -q "^connected$" "$1/status" && basename "$1"' _ {} \; 2>/dev/null | sed 's/^card[0-9]-//')
        if [ ${#drm_mons[@]} -gt 0 ]; then
            prim_detected="${drm_mons[0]:-}"
            sec_detected="${drm_mons[1]:-}"
        fi
    fi

    # 2. Odczyt z Living Inventory (dla X11 lub fallback)
    if [ -z "$prim_detected" ] && [ -f "$inv_json" ]; then
        local parsed
        parsed=$(python3 -c "
import json
try:
    with open('$inv_json') as f:
        d = json.load(f)
    mons = d.get('displays', [])
    for m in mons:
        parts = m.strip().split()
        if parts:
            name = parts[-1]
            is_prim = '*' in parts[1] if len(parts) > 1 else False
            print(f'{name}:{'1' if is_prim else '0'}')
except Exception:
    pass
" 2>/dev/null)
        while IFS=: read -r name is_prim; do
            [ -z "$name" ] && continue
            [ "$name" = "XWAYLAND0" ] && continue
            if [ "$is_prim" = "1" ] && [ -z "$prim_detected" ]; then
                prim_detected="$name"
            elif [ -z "$prim_detected" ]; then
                prim_detected="$name"
            elif [ -z "$sec_detected" ] && [ "$name" != "$prim_detected" ]; then
                sec_detected="$name"
            fi
        done <<< "$parsed"
    fi

    # 3. Standardowy fallback do xrandr dla sesji X11
    if [ -z "$prim_detected" ] && command -v xrandr >/dev/null 2>&1; then
        local xrandr_mons=()
        mapfile -t xrandr_mons < <(xrandr --query 2>/dev/null | grep -E " connected" | awk '{print $1}')
        if [ ${#xrandr_mons[@]} -gt 0 ] && [ "${xrandr_mons[0]}" != "XWAYLAND0" ]; then
            prim_detected="${xrandr_mons[0]:-}"
            sec_detected="${xrandr_mons[1]:-}"
        fi
    fi

    PRIMARY_DISPLAY="${CLI_PRIMARY_DISPLAY:-${PRIMARY_DISPLAY:-$prim_detected}}"
    SECONDARY_DISPLAY="${CLI_SECONDARY_DISPLAY:-${SECONDARY_DISPLAY:-$sec_detected}}"

    if [ -n "$PRIMARY_DISPLAY" ] && [ -n "$SECONDARY_DISPLAY" ] && [ "$PRIMARY_DISPLAY" != "$SECONDARY_DISPLAY" ]; then
        MONITOR_COUNT=2
    elif [ -n "$PRIMARY_DISPLAY" ]; then
        MONITOR_COUNT=1
    else
        MONITOR_COUNT=1
        PRIMARY_DISPLAY="default"
    fi
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

    # Zapewnij obecność xmllint stub jeśli brak pakietu systemowego (zapobiega pytaniu install.sh o sudo)
    if ! command -v xmllint &>/dev/null; then
        mkdir -p "$HOME/.local/bin"
        printf '#!/bin/sh\nexit 0\n' > "$HOME/.local/bin/xmllint"
        chmod +x "$HOME/.local/bin/xmllint"
    fi

    # 1. WhiteSur GTK Theme
    if [ -d "$HOME/.themes/WhiteSur-Light" ] || [ -d "$HOME/.local/share/themes/WhiteSur-Light" ]; then
        log_info "Motyw WhiteSur GTK jest już zainstalowany."
    else
        if ! command -v sassc &>/dev/null; then
            log_err "Brak narzędzia 'sassc' w systemie! Do skompilowania motywu WhiteSur GTK wymagana jest instalacja: sudo apt install -y sassc libglib2.0-dev-bin"
            return 1
        fi

        if [ ! -d "$base_dir/WhiteSur-gtk-theme" ]; then
            log_info "Klonowanie WhiteSur-gtk-theme z GitHuba..."
            git clone --depth 1 https://github.com/vinceliuice/WhiteSur-gtk-theme.git "$base_dir/WhiteSur-gtk-theme"
        fi
        log_info "Instalacja motywu WhiteSur GTK..."
        (cd "$base_dir/WhiteSur-gtk-theme" && ./install.sh -m -t default -l -c light >/dev/null 2>&1) || true
    fi

    # 2. WhiteSur Icon Theme
    if [ -d "$HOME/.local/share/icons/WhiteSur-light" ] || [ -d "$HOME/.icons/WhiteSur-light" ]; then
        log_info "Motyw ikon WhiteSur jest już zainstalowany."
    else
        if [ ! -d "$base_dir/WhiteSur-icon-theme" ]; then
            log_info "Klonowanie WhiteSur-icon-theme z GitHuba..."
            git clone --depth 1 https://github.com/vinceliuice/WhiteSur-icon-theme.git "$base_dir/WhiteSur-icon-theme"
        fi
        log_info "Instalacja motywu ikon WhiteSur..."
        (cd "$base_dir/WhiteSur-icon-theme" && ./install.sh >/dev/null 2>&1) || true
    fi

    # 3. McMojave Cursors
    if [ -d "$HOME/.local/share/icons/McMojave-cursors" ] || [ -d "$HOME/.icons/McMojave-cursors" ]; then
        log_info "Kursor McMojave jest już zainstalowany."
    else
        if [ ! -d "$base_dir/McMojave-cursors" ]; then
            log_info "Klonowanie McMojave-cursors z GitHuba..."
            git clone --depth 1 https://github.com/vinceliuice/McMojave-cursors.git "$base_dir/McMojave-cursors"
        fi
        log_info "Instalacja kursorów McMojave..."
        (cd "$base_dir/McMojave-cursors" && ./install.sh >/dev/null 2>&1) || true
    fi
}

# ------------------------------------------------------------------------------
# 3. Konfiguracja doku Plank (Dual-Dock dla konfiguracji wielomonitorowej)
# ------------------------------------------------------------------------------

configure_plank_dual_dock() {
    local theme_name="${1:-Transparent}"
    detect_displays
    local mon_count="$MONITOR_COUNT"

    if [ "$mon_count" -le 1 ]; then
        log_info "Konfiguracja doku Plank (Pojedynczy ekran / laptop, motyw: $theme_name)..."
        dconf write /net/launchpad/plank/enabled-docks "['dock1']"
        dconf write /net/launchpad/plank/docks/dock1/monitor "''"
        dconf write /net/launchpad/plank/docks/dock1/position "'bottom'"
        dconf write /net/launchpad/plank/docks/dock1/alignment "'center'"
        dconf write /net/launchpad/plank/docks/dock1/theme "'$theme_name'"
        dconf write /net/launchpad/plank/docks/dock1/zoom-enabled "true"
        dconf write /net/launchpad/plank/docks/dock1/zoom-percent "140"
        dconf write /net/launchpad/plank/docks/dock1/icon-size "48"
        dconf write /net/launchpad/plank/docks/dock1/hide-mode "'intelligent'"
        dconf write /net/launchpad/plank/docks/dock1/show-dock-item "false"
        mkdir -p "$HOME/.config/plank/dock1/launchers"
    else
        log_info "Konfiguracja podwójnego doku Plank (Dual-Dock: $PRIMARY_DISPLAY + $SECONDARY_DISPLAY, motyw: $theme_name)..."
        dconf write /net/launchpad/plank/enabled-docks "['dock1', 'dock2']"

        dconf write /net/launchpad/plank/docks/dock1/monitor "'$PRIMARY_DISPLAY'"
        dconf write /net/launchpad/plank/docks/dock1/position "'bottom'"
        dconf write /net/launchpad/plank/docks/dock1/alignment "'center'"
        dconf write /net/launchpad/plank/docks/dock1/theme "'$theme_name'"
        dconf write /net/launchpad/plank/docks/dock1/zoom-enabled "true"
        dconf write /net/launchpad/plank/docks/dock1/show-dock-item "false"

        dconf write /net/launchpad/plank/docks/dock2/monitor "'$SECONDARY_DISPLAY'"
        dconf write /net/launchpad/plank/docks/dock2/position "'bottom'"
        dconf write /net/launchpad/plank/docks/dock2/alignment "'center'"
        dconf write /net/launchpad/plank/docks/dock2/theme "'$theme_name'"
        dconf write /net/launchpad/plank/docks/dock2/zoom-enabled "true"
        dconf write /net/launchpad/plank/docks/dock2/zoom-percent "150"
        dconf write /net/launchpad/plank/docks/dock2/icon-size "48"
        dconf write /net/launchpad/plank/docks/dock2/hide-mode "'intelligent'"
        dconf write /net/launchpad/plank/docks/dock2/show-dock-item "false"
        dconf write /net/launchpad/plank/docks/dock2/dock-items "['show-applications.dockitem', 'applications.dockitem']"
        mkdir -p "$HOME/.config/plank/dock2/launchers"
    fi

    mkdir -p "$HOME/.config/plank/dock1/launchers"

    # Zapewnij aktywatory menu w dock2 tylko dla konfiguracji wielomonitorowej
    if [ "$mon_count" -gt 1 ]; then
        mkdir -p "$HOME/.config/plank/dock2/launchers"
        if [ ! -f "$HOME/.config/plank/dock2/launchers/applications.dockitem" ]; then
            cat << 'EOF' > "$HOME/.config/plank/dock2/launchers/applications.dockitem"
[PlankDockItemPreferences]
Launcher=docklet://applications
EOF
        fi

        if [ -f "$HOME/.local/share/applications/show-applications.desktop" ]; then
            cat << EOF > "$HOME/.config/plank/dock2/launchers/show-applications.dockitem"
[PlankDockItemPreferences]
Launcher=file://$HOME/.local/share/applications/show-applications.desktop
EOF
        fi

        # Usuń z doku nagraniowego dock2 zbędne przypięte aplikacje (mają być tylko te aktualnie otwarte na $SECONDARY_DISPLAY)
        rm -f "$HOME/.config/plank/dock2/launchers/"{antigravity,org.gnome.Terminal,org.gnome.Nautilus,google-chrome,code-url-handler,capcut}.dockitem 2>/dev/null || true
    fi

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
        # shellcheck disable=SC2016
        sed -i 's|^Exec=.*|Exec=sh -c '\''if [ "$XDG_SESSION_TYPE" = "x11" ]; then plank; fi'\''|' "$HOME/.config/autostart/plank.desktop"
    fi

    if systemctl --user list-unit-files plank.service 2>/dev/null | grep -q "plank.service"; then
        log_info "Restartowanie usługi Plank przez systemd user service..."
        systemctl --user enable plank.service 2>/dev/null || true
        systemctl --user restart plank.service 2>/dev/null || systemctl --user start plank.service 2>/dev/null || true
    else
        killall plank 2>/dev/null || true
        nohup env XDG_SESSION_TYPE=x11 GDK_BACKEND=x11 plank >/dev/null 2>&1 &
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

    # Likwidacja drugiego pustego paska GNOME (stockgs-keep-top-panel=false) i zachowanie dasha dla doku
    gsettings set org.gnome.shell.extensions.zorin-taskbar stockgs-keep-top-panel false 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar stockgs-keep-dash true 2>/dev/null || true

    # Smukła wysokość a la macOS (28px zamiast 48px) oraz brak marginesu
    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-size 28 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-margin 0 2>/dev/null || true

    # W profilu macOS aplikacje są zawsze delegowane do dolnego doku (Wayland Dock na Waylandzie, Plank na X11)
    gsettings set org.gnome.shell.extensions.zorin-taskbar show-running-apps false 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar show-favorites false 2>/dev/null || true

    # Rozmieszczenie elementów w pasku:
    # Lewa strona: leftBox (menu Zorin)
    # Środek: dateMenu (zegar i data w centrum ekranu - styl macOS)
    # Prawa strona: systemMenu (zasilanie, sieć, głośność) + rightBox (tacka)
    python3 -c "
import os, json, subprocess
show_apps = False

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
    {'element': 'taskbar', 'visible': show_apps, 'position': 'stackedTL'},
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
# 4b. Konfiguracja natywnego doku Wayland (Ubuntu Dock / Dash to Dock)
# ------------------------------------------------------------------------------

configure_wayland_dock() {
    log_info "Konfiguracja animowanego doku Wayland (Ubuntu Dock / Dash to Dock)..."

    local user_ext_dir="$HOME/.local/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com"
    local sys_ext_dir="/usr/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com"

    if [ ! -d "$user_ext_dir" ]; then
        if [ -d "$sys_ext_dir" ]; then
            log_info "Kopiowanie ubuntu-dock do przestrzeni użytkownika (~/.local/share/gnome-shell/extensions)..."
            mkdir -p "$HOME/.local/share/gnome-shell/extensions"
            cp -r "$sys_ext_dir" "$user_ext_dir"
        else
            log_warn "Brak rozszerzenia ubuntu-dock w systemie. Aby dok Wayland działał, zainstaluj pakiet: sudo apt install -y gnome-shell-extension-ubuntu-dock"
        fi
    fi

    gnome-extensions enable ubuntu-dock@ubuntu.com 2>/dev/null || true

    # Zapewnij obecność ikony podglądu aplikacji pod WhiteSur (zapobiega wyświetlaniu dużego znaku +)
    mkdir -p "$HOME/.local/share/icons/WhiteSur/actions/symbolic" "$HOME/.local/share/icons/WhiteSur-light/actions/symbolic" "$HOME/.local/share/icons/hicolor/scalable/actions"
    if [ -f "$HOME/.local/share/icons/WhiteSur/actions/symbolic/view-app-grid-symbolic.svg" ]; then
        cp -f "$HOME/.local/share/icons/WhiteSur/actions/symbolic/view-app-grid-symbolic.svg" "$HOME/.local/share/icons/WhiteSur/actions/symbolic/view-app-grid-zorin-symbolic.svg" 2>/dev/null || true
        cp -f "$HOME/.local/share/icons/WhiteSur/actions/symbolic/view-app-grid-symbolic.svg" "$HOME/.local/share/icons/WhiteSur-light/actions/symbolic/view-app-grid-zorin-symbolic.svg" 2>/dev/null || true
        cp -f "$HOME/.local/share/icons/WhiteSur/actions/symbolic/view-app-grid-symbolic.svg" "$HOME/.local/share/icons/hicolor/scalable/actions/view-app-grid-zorin-symbolic.svg" 2>/dev/null || true
    fi

    # Zapewnij obecność kluczowych aplikacji w ulubionych bez niszczenia istniejących
    python3 -c "
import ast, os, subprocess
curr_str = subprocess.run(['gsettings', 'get', 'org.gnome.shell', 'favorite-apps'], capture_output=True, text=True).stdout.strip()
try:
    favs = ast.literal_eval(curr_str)
    if not isinstance(favs, list):
        favs = []
except Exception:
    favs = []

defaults = ['antigravity.desktop', 'google-chrome.desktop', 'brave-browser.desktop', 'code.desktop', 'org.gnome.Nautilus.desktop', 'org.gnome.Terminal.desktop']
if not favs:
    favs = [d for d in defaults if os.path.exists(f'/usr/share/applications/{d}') or os.path.exists(f'{os.path.expanduser(\"~\")}/.local/share/applications/{d}')]
else:
    if 'antigravity.desktop' not in favs and (os.path.exists('/usr/share/applications/antigravity.desktop') or os.path.exists(f'{os.path.expanduser(\"~\")}/.local/share/applications/antigravity.desktop')):
        favs.append('antigravity.desktop')

subprocess.run(['gsettings', 'set', 'org.gnome.shell', 'favorite-apps', str(favs)], check=False)
" 2>/dev/null || true

    # Zapewnij łatanie docking.js pod kątem aktywnego wykrywania kursora nad oknami (TopChrome + slideoutSize = 2px)
    local user_docking="$HOME/.local/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com/docking.js"
    if [ -f "$user_docking" ]; then
        python3 -c "
docking_file = '$user_docking'
with open(docking_file, 'r') as f:
    content = f.read()
content = content.replace('this._slideoutSize = 0;', 'this._slideoutSize = 2;')
content = content.replace('Main.layoutManager.addChrome(this);', 'Main.layoutManager.addTopChrome(this, { trackFullscreen: true });')
if 'currentUserTime !== this._dockDwellUserTime' in content:
    content = content.replace(
        'if (currentUserTime !== this._dockDwellUserTime)\n            return GLib.SOURCE_REMOVE;',
        '// User interaction check bypassed for responsive dock'
    )
with open(docking_file, 'w') as f:
    f.write(content)
" 2>/dev/null || true
    fi

    # Zapewnij animację zoom/hop ikony pod kursorem (styl Plank / macOS)
    local user_appicons="$HOME/.local/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com/appIcons.js"
    if [ -f "$user_appicons" ]; then
        python3 -c "
appicons_file = '$user_appicons'
with open(appicons_file, 'r') as f:
    content = f.read()
if '_applyHoverHopAnimation' not in content:
    func_code = '''function _applyHoverHopAnimation(button, getIconActor) {
    if (!button)
        return;
    button.connect('notify::hover', () => {
        const rawActor = typeof getIconActor === 'function' ? getIconActor() : getIconActor;
        const actor = rawActor?._iconBin || rawActor;
        if (!actor)
            return;
        actor.remove_all_transitions();
        actor.set_pivot_point(0.5, 0.5);
        if (button.hover) {
            const pos = Utils.getPosition();
            let transX = 0;
            let transY = 0;
            if (pos === St.Side.BOTTOM)
                transY = -6;
            else if (pos === St.Side.TOP)
                transY = 6;
            else if (pos === St.Side.LEFT)
                transX = 6;
            else if (pos === St.Side.RIGHT)
                transX = -6;

            actor.ease({
                scale_x: 1.2,
                scale_y: 1.2,
                translation_x: transX,
                translation_y: transY,
                duration: 120,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
        } else {
            actor.ease({
                scale_x: 1.0,
                scale_y: 1.0,
                translation_x: 0,
                translation_y: 0,
                duration: 120,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
        }
    });
}
'''
    content = content.replace('const DockAbstractAppIcon = GObject.registerClass({', func_code + '\nconst DockAbstractAppIcon = GObject.registerClass({')
    content = content.replace('this._indicator = new AppIconIndicators.AppIconIndicator(this);', 'this._indicator = new AppIconIndicators.AppIconIndicator(this);\n        _applyHoverHopAnimation(this, () => this.icon);')
    content = content.replace('this._menuTimeoutId = 0;\n    }', 'this._menuTimeoutId = 0;\n        _applyHoverHopAnimation(this.toggleButton, () => this.icon);\n    }')
    with open(appicons_file, 'w') as f:
        f.write(content)
" 2>/dev/null || true
    fi

    gsettings set org.gnome.shell.extensions.dash-to-dock dock-position 'BOTTOM' 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock extend-height false 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock dock-fixed false 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock autohide true 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock intellihide true 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock intellihide-mode 'ALL_WINDOWS' 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock require-pressure-to-show false 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock show-delay 0.05 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock hide-delay 0.15 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock dash-max-icon-size 48 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock custom-theme-shrink true 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock transparency-mode 'FIXED' 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock background-opacity 0.25 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock running-indicator-style 'DOTS' 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock show-favorites true 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock show-running true 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock show-show-apps-button true 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock show-apps-at-top true 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock show-trash false 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.dash-to-dock show-mounts false 2>/dev/null || true

    # Ukrycie aplikacji w górnym pasku, gdy aktywny jest dolny dok
    gsettings set org.gnome.shell.extensions.zorin-taskbar show-running-apps false 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar show-favorites false 2>/dev/null || true
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

elem_dict = {k: elements for k in keys}
subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.zorin-taskbar', 'panel-element-positions', json.dumps(elem_dict)], check=False)
" 2>/dev/null || true

    # Przeładuj rozszerzenie, aby Mutter załadował zaktualizowane parametry
    gnome-extensions disable ubuntu-dock@ubuntu.com 2>/dev/null || true
    sleep 0.2
    gnome-extensions enable ubuntu-dock@ubuntu.com 2>/dev/null || true
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

    # 5. Konfiguracja dolnego doku (Wayland: Ubuntu Dock / Dash to Dock, X11: Plank)
    local session_type
    session_type="$(detect_display_server)"
    if [ "$session_type" = "wayland" ]; then
        log_info "Wykryto serwer wyświetlania Wayland — konfiguracja doku Wayland (TopChrome + Hover Zoom/Hop)..."
        configure_wayland_dock
    else
        log_info "Wykryto serwer wyświetlania X11 — konfiguracja natywnego doku Plank..."
        configure_plank_dual_dock
    fi

    # 6. Unifikacja aplikacji CSD (VS Code & Google Chrome)
    log_info "Wymuszanie natywnej belki okna w VS Code i Google Chrome..."
    configure_vscode_csd "native"
    configure_chrome_csd "true"


    log_ok "Profil macOS został pomyślnie zaaplikowany."
}

# ------------------------------------------------------------------------------
# 6. Konfiguracja górnego paska Zorin OS dla profilu Cyber Studio (Emission HUD)
# ------------------------------------------------------------------------------

configure_zorin_studio_panel() {
    log_info "Konfiguracja asymetrycznego paska Zorin OS (brak zegara na monitorze emisyjnym, wyśrodkowany HUD)..."
    gnome-extensions enable zorin-taskbar@zorinos.com 2>/dev/null || true
    gnome-extensions enable zorin-menu@zorinos.com 2>/dev/null || true

    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-position 'TOP' 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar multi-monitors true 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar stockgs-keep-top-panel false 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar stockgs-keep-dash true 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-size 28 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar panel-margin 0 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar show-running-apps false 2>/dev/null || true
    gsettings set org.gnome.shell.extensions.zorin-taskbar show-favorites false 2>/dev/null || true

    python3 -c "
import json, subprocess

primary_elements = [
    {'element': 'showAppsButton', 'visible': False, 'position': 'stackedTL'},
    {'element': 'activitiesButton', 'visible': False, 'position': 'stackedTL'},
    {'element': 'leftBox', 'visible': True, 'position': 'stackedTL'},
    {'element': 'taskbar', 'visible': False, 'position': 'stackedTL'},
    {'element': 'dateMenu', 'visible': True, 'position': 'centerMonitor'},
    {'element': 'centerBox', 'visible': True, 'position': 'stackedBR'},
    {'element': 'systemMenu', 'visible': True, 'position': 'stackedBR'},
    {'element': 'rightBox', 'visible': True, 'position': 'stackedBR'},
    {'element': 'desktopButton', 'visible': False, 'position': 'stackedBR'}
]

emission_elements = [
    {'element': 'showAppsButton', 'visible': False, 'position': 'stackedTL'},
    {'element': 'activitiesButton', 'visible': False, 'position': 'stackedTL'},
    {'element': 'leftBox', 'visible': True, 'position': 'stackedTL'},
    {'element': 'taskbar', 'visible': False, 'position': 'stackedTL'},
    {'element': 'dateMenu', 'visible': False, 'position': 'centerMonitor'},
    {'element': 'centerBox', 'visible': True, 'position': 'centerMonitor'},
    {'element': 'systemMenu', 'visible': True, 'position': 'stackedBR'},
    {'element': 'rightBox', 'visible': True, 'position': 'stackedBR'},
    {'element': 'desktopButton', 'visible': False, 'position': 'stackedBR'}
]

elem_dict = {
    '0': primary_elements,
    '1': emission_elements,
}
prim = '$PRIMARY_DISPLAY'
sec = '$SECONDARY_DISPLAY'
if prim and prim != 'default':
    elem_dict[prim] = primary_elements
if sec:
    elem_dict[sec] = emission_elements

try:
    import dbus
    bus = dbus.SessionBus()
    proxy = bus.get_object('org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig')
    iface = dbus.Interface(proxy, 'org.gnome.Mutter.DisplayConfig')
    serial, monitors, logical_monitors, properties = iface.GetCurrentState()
    for i, lm in enumerate(logical_monitors):
        mon = lm[5][0]
        connector, vendor, product, mon_serial = mon[0], mon[1], mon[2], mon[3]
        key = f'{vendor}-{mon_serial}' if vendor and mon_serial else str(connector)
        if 'HDMI' in str(connector) or 'SAM' in key:
            elem_dict[key] = emission_elements
            elem_dict[str(i)] = emission_elements
            elem_dict[str(connector)] = emission_elements
        else:
            elem_dict[key] = primary_elements
            elem_dict[str(i)] = primary_elements
            elem_dict[str(connector)] = primary_elements
except Exception:
    pass

subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.zorin-taskbar', 'panel-element-positions-monitors-sync', 'false'], check=False)
subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.zorin-taskbar', 'panel-element-positions', json.dumps(elem_dict)], check=False)
" 2>/dev/null || true
}

# ------------------------------------------------------------------------------
# 7. Aplikacja tapet MnemoShift Cyber-Blueprint
# ------------------------------------------------------------------------------

apply_studio_wallpapers() {
    local repo_dir="$1"
    local wp_dir="$repo_dir/assets/wallpapers"
    local spanned_master="$wp_dir/dual_monitor_spanned_cockpit_blueprint.jpg"
    local wp1_ultrawide="$wp_dir/ultrawide_crop/01-sovereign-cockpit-deck.jpg"
    local wp3_1080p="$wp_dir/1080p/03-tactical-hud-blueprint.jpg"

    detect_displays

    if [ "$MONITOR_COUNT" -gt 1 ] && [ -f "$spanned_master" ]; then
        log_info "Aktywacja tapety w trybie spanned (Dual-Monitor: $PRIMARY_DISPLAY + $SECONDARY_DISPLAY)..."
        gsettings set org.gnome.desktop.background picture-options 'spanned'
        gsettings set org.gnome.desktop.background picture-uri "file://$spanned_master"
        gsettings set org.gnome.desktop.background picture-uri-dark "file://$spanned_master"
    elif [ -f "$wp1_ultrawide" ]; then
        log_info "Aktywacja tapety Ultrawide (Primary: $PRIMARY_DISPLAY)..."
        gsettings set org.gnome.desktop.background picture-options 'zoom'
        gsettings set org.gnome.desktop.background picture-uri "file://$wp1_ultrawide"
        gsettings set org.gnome.desktop.background picture-uri-dark "file://$wp1_ultrawide"
    elif [ -f "$wp3_1080p" ]; then
        log_info "Aktywacja tapety standardowej..."
        gsettings set org.gnome.desktop.background picture-options 'zoom'
        gsettings set org.gnome.desktop.background picture-uri "file://$wp3_1080p"
        gsettings set org.gnome.desktop.background picture-uri-dark "file://$wp3_1080p"
    fi
}

# ------------------------------------------------------------------------------
# 8. Uruchamianie Conky HUD (Multi-Monitor Smoked Glass)
# ------------------------------------------------------------------------------

start_conky_multi() {
    killall conky 2>/dev/null || true
    sleep 0.5
    local config_prim="$HOME/.config/conky/mnemoshift_hud_primary.conf"
    local config_sec="$HOME/.config/conky/mnemoshift_hud_secondary.conf"

    detect_displays

    if [ "$MONITOR_COUNT" -gt 1 ]; then
        log_info "Uruchamianie Conky HUD: $PRIMARY_DISPLAY (head 0) oraz $SECONDARY_DISPLAY (head 1)..."
        conky -c "$config_prim" -m 0 -d 2>/dev/null || true
        conky -c "$config_sec" -m 1 -d 2>/dev/null || true
    else
        log_info "Uruchamianie Conky HUD: $PRIMARY_DISPLAY (head 0)..."
        conky -c "$config_prim" -m 0 -d 2>/dev/null || true
    fi
}

# ------------------------------------------------------------------------------
# 9. Wdrażanie profilu Cyber Studio (apply-studio)
# ------------------------------------------------------------------------------

apply_studio() {
    log_info "Wdrażanie profilu Cyber Studio (MnemoShift Cyber-Blueprint & Emission HUD)..."
    local repo_dir
    repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

    local session_type
    session_type="$(detect_display_server)"

    # 1. Pakiety systemowe (conky-all, plank dla X11)
    if [ "$session_type" = "x11" ]; then
        log_info "Weryfikacja pakietów systemowych dla sesji X11..."
        check_tool conky conky-all "sudo apt install -y conky-all" || true
        check_tool plank plank "sudo apt install -y plank" || true
    else
        log_info "Wykryto sesję Wayland — profil Cyber Studio wykorzysta natywny dok Wayland zamiast Planka/Conky."
    fi

    # 2. Motyw Zorin Dark
    log_info "Konfiguracja motywu ciemnego Zorin..."
    gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark' || true
    gsettings set org.gnome.desktop.interface gtk-theme 'ZorinBlue-Dark' || true
    gsettings set org.gnome.desktop.interface icon-theme 'ZorinBlue-Dark' || true
    gsettings set org.gnome.desktop.interface cursor-theme 'Zorin' || true
    gsettings set org.gnome.shell.extensions.user-theme name 'ZorinBlue-Dark' 2>/dev/null || true
    gsettings set org.gnome.desktop.wm.preferences button-layout 'close,minimize,maximize:' || true

    # 3. Kopiowanie motywu Planka MnemoShift-HUD i konfiguracja doku
    mkdir -p "$HOME/.local/share/plank/themes/MnemoShift-HUD"
    cp -r "$repo_dir/templates/plank/MnemoShift-HUD/"* "$HOME/.local/share/plank/themes/MnemoShift-HUD/" 2>/dev/null || true
    if [ "$session_type" = "wayland" ]; then
        log_info "Konfiguracja animowanego doku Wayland dla profilu Cyber Studio..."
        configure_wayland_dock
    else
        log_info "Instalacja motywu Planka MnemoShift-HUD..."
        configure_plank_dual_dock "MnemoShift-HUD"
    fi

    # 4. Instalacja i konfiguracja Conky HUD na przydymionym szkle (tylko X11)
    if [ "$session_type" = "x11" ]; then
        log_info "Konfiguracja Conky HUD (przydymione szkło multi-monitor)..."
        mkdir -p "$HOME/.config/conky"
        cp "$repo_dir/templates/conky/mnemoshift_hud_primary.conf" "$HOME/.config/conky/" 2>/dev/null || true
        cp "$repo_dir/templates/conky/mnemoshift_hud_secondary.conf" "$HOME/.config/conky/" 2>/dev/null || true
    fi

    # 5. Instalacja i włączenie rozszerzenia GNOME Shell MnemoShift Emission HUD
    log_info "Instalacja rozszerzenia GNOME Shell MnemoShift Emission HUD..."
    local ext_dir="$HOME/.local/share/gnome-shell/extensions/mnemoshift-emission-hud@ghostshift.eu"
    mkdir -p "$ext_dir"
    cp -r "$repo_dir/templates/gnome-shell/mnemoshift-emission-hud@ghostshift.eu/"* "$ext_dir/"
    gnome-extensions enable mnemoshift-emission-hud@ghostshift.eu 2>/dev/null || true
    python3 -c "
import ast, subprocess
try:
    raw = subprocess.check_output(['gsettings', 'get', 'org.gnome.shell', 'enabled-extensions'], text=True).strip()
    exts = ast.literal_eval(raw)
    if 'mnemoshift-emission-hud@ghostshift.eu' not in exts:
        exts.append('mnemoshift-emission-hud@ghostshift.eu')
        subprocess.run(['gsettings', 'set', 'org.gnome.shell', 'enabled-extensions', str(exts)], check=False)
except Exception:
    pass
" 2>/dev/null || true

    # 6. Konfiguracja górnego paska zadań (Zorin Taskbar) - rozparowanie i telemetria
    configure_zorin_studio_panel

    # 7. Aplikacja tapet multi-monitor (spanned lub single)
    apply_studio_wallpapers "$repo_dir"

    # 8. Start Conky multi-monitor (tylko X11)
    if [ "$session_type" = "x11" ]; then
        log_info "Uruchamianie Conky HUD..."
        start_conky_multi
    fi

    # 9. Autostart Planka (tylko X11)
    if [ "$session_type" = "x11" ]; then
        mkdir -p "$HOME/.config/autostart"
        cp /usr/share/applications/plank.desktop "$HOME/.config/autostart/" 2>/dev/null || true
    fi

    log_ok "Profil Cyber Studio został pomyślnie wdrożony!"
}

# ------------------------------------------------------------------------------
# 10. Przywracanie stanu domyślnego (reset / vanilla Zorin)
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

    # 8. Wyłączenie doku Wayland oraz rozszerzenia GNOME Shell MnemoShift Emission HUD
    log_info "Wyłączanie rozszerzeń doku Wayland i MnemoShift Emission HUD..."
    gnome-extensions disable ubuntu-dock@ubuntu.com 2>/dev/null || true
    gsettings reset-recursively org.gnome.shell.extensions.dash-to-dock 2>/dev/null || true
    gnome-extensions disable mnemoshift-emission-hud@ghostshift.eu 2>/dev/null || true

    # 9. Zatrzymanie Conky i demona tapet
    log_info "Zatrzymywanie Conky i demona tapet..."
    killall conky 2>/dev/null || true
    systemctl --user stop conky.service 2>/dev/null || true
    systemctl --user disable conky.service 2>/dev/null || true
    systemctl --user stop mnemoshift-wallpaper.service 2>/dev/null || true
    systemctl --user disable mnemoshift-wallpaper.service 2>/dev/null || true
    pkill -f wallpaper_daemon.sh 2>/dev/null || true

    # 10. Przywrócenie domyślnej tapety Zorin OS
    log_info "Przywracanie domyślnej tapety Zorin OS..."
    gsettings reset org.gnome.desktop.background picture-uri 2>/dev/null || true
    gsettings reset org.gnome.desktop.background picture-uri-dark 2>/dev/null || true
    gsettings reset org.gnome.desktop.background picture-options 2>/dev/null || true
    gsettings set org.gnome.desktop.interface color-scheme 'default' 2>/dev/null || true

    log_ok "Pulpit został zresetowany do stanu fabrycznego Zorin OS."
}

# ------------------------------------------------------------------------------
# 11. Podgląd bieżącego stanu (status)
# ------------------------------------------------------------------------------

show_status() {
    echo "=========================================================="
    echo "  WORKSTATION HUB: STAN KONFIGURACJI PULPITU"
    echo "=========================================================="
    local s_type
    s_type="$(detect_display_server)"
    echo -n "Serwer wyświetlania:    "
    if [ "$s_type" = "wayland" ]; then
        echo -e "\033[1;36mWayland (natywny dok: Ubuntu Dock / Dash to Dock)\033[0m"
    else
        echo -e "\033[1;34mX11 / Xorg (natywny dok: Plank)\033[0m"
    fi
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
        echo -e "\033[1;32mUkryte (przeniesione do dolnego doku)\033[0m"
    else
        echo -e "\033[1;33mWidoczne (domyślny taskbar)\033[0m"
    fi
    echo -n "Układ zegara i daty:    "
    local elem_pos
    elem_pos=$(gsettings get org.gnome.shell.extensions.zorin-taskbar panel-element-positions 2>/dev/null || echo "")
    if [[ "$elem_pos" == *"centerMonitor"* ]]; then
        echo -e "\033[1;32mWyśrodkowany (macOS / Studio)\033[0m"
    else
        echo -e "\033[1;33mDomyślny (po prawej)\033[0m"
    fi
    echo -n "Motyw GTK:              "
    gsettings get org.gnome.desktop.interface gtk-theme
    echo -n "Motyw ikon:             "
    gsettings get org.gnome.desktop.interface icon-theme
    echo -n "Kursor myszy:           "
    gsettings get org.gnome.desktop.interface cursor-theme
    echo -n "Rozszerzenie user-theme: "
    gsettings get org.gnome.shell.extensions.user-theme name 2>/dev/null || echo "N/A"
    echo -n "Emission HUD (GNOME):   "
    if gnome-extensions list --enabled 2>/dev/null | grep -q "mnemoshift-emission-hud" || gsettings get org.gnome.shell enabled-extensions 2>/dev/null | grep -q "mnemoshift-emission-hud"; then
        echo -e "\033[1;32mAKTYWNY (rozszerzenie GNOME Shell)\033[0m"
    else
        echo -e "\033[1;33mNIEAKTYWNY\033[0m"
    fi
    echo -n "Conky HUD:              "
    if pgrep -x "conky" >/dev/null; then
        echo -e "\033[1;32mAKTYWNY ($(pgrep -c -x conky) instancji)\033[0m"
    else
        echo -e "\033[1;33mNIEAKTYWNY\033[0m"
    fi
    echo -n "Dok Wayland (Dock):     "
    if gnome-extensions list --enabled 2>/dev/null | grep -q "ubuntu-dock"; then
        echo -e "\033[1;32mAKTYWNY (animowany dok dolny)\033[0m"
    else
        echo -e "\033[1;33mNIEAKTYWNY\033[0m"
    fi
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
        local th1
        th1=$(dconf read /net/launchpad/plank/docks/dock1/theme 2>/dev/null || echo "Transparent")
        local count1
        count1=$(find "$HOME/.config/plank/dock1/launchers" -maxdepth 1 -mindepth 1 2>/dev/null | wc -l)
        echo "  -> dock1 (Monitor: $m1, motyw: $th1, przypiętych: $count1)"
    fi
    if [[ "$enabled_docks" == *"dock2"* ]]; then
        local m2
        m2=$(dconf read /net/launchpad/plank/docks/dock2/monitor 2>/dev/null || echo "domyślny")
        local th2
        th2=$(dconf read /net/launchpad/plank/docks/dock2/theme 2>/dev/null || echo "Transparent")
        local count2
        count2=$(find "$HOME/.config/plank/dock2/launchers" -maxdepth 1 -mindepth 1 2>/dev/null | wc -l)
        echo "  -> dock2 (Monitor: $m2, motyw: $th2, aktywatorów: $count2)"
    fi
    echo -n "Tapeta systemowa:       "
    gsettings get org.gnome.desktop.background picture-uri 2>/dev/null || echo "N/A"
    detect_displays
    echo -n "Ekrany (Living Inventory): "
    echo -e "Primary: \033[1;32m${PRIMARY_DISPLAY:-N/A}\033[0m, Secondary: \033[1;36m${SECONDARY_DISPLAY:-brak}\033[0m (Wykryto: $MONITOR_COUNT)"
    echo "=========================================================="
}

# ------------------------------------------------------------------------------
# Główny dyspozytor
# ------------------------------------------------------------------------------

CLI_PRIMARY_DISPLAY=""
CLI_SECONDARY_DISPLAY=""
ACTION=""

while [ $# -gt 0 ]; do
    case "$1" in
        --primary-display|-p)
            CLI_PRIMARY_DISPLAY="$2"
            shift 2
            ;;
        --secondary-display|-s)
            CLI_SECONDARY_DISPLAY="$2"
            shift 2
            ;;
        apply-macos|apply-studio|apply-cyber-hud|reset|status)
            ACTION="$1"
            shift
            ;;
        *)
            echo "Nieznana opcja: $1"
            echo "Użycie: $0 {apply-macos|apply-studio|reset|status} [--primary-display <NAME>] [--secondary-display <NAME>]"
            exit 1
            ;;
    esac
done

ACTION="${ACTION:-status}"

case "$ACTION" in
    apply-macos)
        apply_macos
        ;;
    apply-studio|apply-cyber-hud)
        apply_studio
        ;;
    reset)
        reset_defaults
        ;;
    status)
        show_status
        ;;
esac
