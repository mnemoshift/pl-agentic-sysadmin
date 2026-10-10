#!/usr/bin/env bash
# ==============================================================================
# WORKSTATION HUB: Google Drive Selective Sync Controller
# Zarządzanie selektywną, dwukierunkową synchronizacją Dysku Google (rclone)
# na dysk lokalny NVMe. Eliminuje problemy z FUSE (GVFS), zawieszaniem suspendu
# i brakiem wsparcia ścieżek w KeePassXC oraz przeglądarkach.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/mnemoshift"
CONFIG_FILE="${CONFIG_DIR}/gdrive-sync.json"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE_NAME="mnemoshift-gdrive-sync"

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

# ------------------------------------------------------------------------------
# 1. Detekcja i instalacja rclone (User-Space by default)
# ------------------------------------------------------------------------------

find_rclone() {
    if command -v rclone &>/dev/null; then
        command -v rclone
    elif [[ -x "$HOME/.local/bin/rclone" ]]; then
        echo "$HOME/.local/bin/rclone"
    else
        return 1
    fi
}

cmd_install() {
    log_info "Sprawdzanie dostępności rclone..."
    local rclone_bin
    if rclone_bin=$(find_rclone); then
        log_ok "rclone jest już zainstalowany: $rclone_bin ($($rclone_bin version | head -n 1))"
        return 0
    fi

    log_warn "rclone nie jest zainstalowany. Rozpoczynam instalację w przestrzeni użytkownika (~/.local/bin)..."
    mkdir -p "$HOME/.local/bin"

    local temp_dir
    temp_dir="$(mktemp -d)"

    log_info "Pobieranie oficjalnej wersji binarnej rclone (Linux amd64)..."
    curl -fsSL "https://downloads.rclone.org/rclone-current-linux-amd64.zip" -o "${temp_dir}/rclone.zip"

    log_info "Rozpakowywanie do ~/.local/bin/rclone..."
    unzip -q -j "${temp_dir}/rclone.zip" "*/rclone" -d "${temp_dir}"
    install -m 755 "${temp_dir}/rclone" "$HOME/.local/bin/rclone"
    rm -rf "${temp_dir}"

    if [[ -x "$HOME/.local/bin/rclone" ]]; then
        log_ok "Pomyślnie zainstalowano rclone: $($HOME/.local/bin/rclone version | head -n 1)"
        log_info "Ścieżka: $HOME/.local/bin/rclone"
    else
        log_err "Instalacja nie powiodła się. Możesz zainstalować rclone systemowo: sudo apt install -y rclone"
        exit 1
    fi
}

# ------------------------------------------------------------------------------
# 2. Inicjalizacja konfiguracji
# ------------------------------------------------------------------------------

cmd_init_config() {
    mkdir -p "${CONFIG_DIR}"
    if [[ ! -f "${CONFIG_FILE}" ]]; then
        if [[ -f "${REPO_ROOT}/templates/gdrive_sync.json.template" ]]; then
            cp "${REPO_ROOT}/templates/gdrive_sync.json.template" "${CONFIG_FILE}"
        else
            printf '{\n  "remote_name": "gdrive",\n  "local_base_dir": "~/GoogleDrive",\n  "sync_folders": [],\n  "timer_interval": "15m"\n}\n' > "${CONFIG_FILE}"
        fi
        log_ok "Utworzono plik konfiguracji: ${CONFIG_FILE}"
    fi
}

get_config_val() {
    local key="$1"
    python3 - "${CONFIG_FILE}" "${key}" << 'PY_GET_EOF'
import sys, json, os
path = os.path.expanduser(sys.argv[1])
key = sys.argv[2]
if not os.path.exists(path):
    print("")
    sys.exit(0)
with open(path) as f:
    data = json.load(f)
val = data.get(key, "")
if isinstance(val, str):
    val = os.path.expanduser(val)
print(val)
PY_GET_EOF
}

# ------------------------------------------------------------------------------
# 3. Autoryzacja i konfiguracja pilota Google Drive
# ------------------------------------------------------------------------------

cmd_auth() {
    local rclone_bin
    if ! rclone_bin=$(find_rclone); then
        cmd_install
        rclone_bin=$(find_rclone)
    fi

    cmd_init_config
    local remote_name
    remote_name=$(get_config_val "remote_name")
    if [[ -z "${remote_name}" ]]; then
        remote_name="gdrive"
    fi

    log_info "Sprawdzanie czy remote '${remote_name}' istnieje w rclone..."
    if "$rclone_bin" listremotes 2>/dev/null | grep -q "^${remote_name}:"; then
        log_ok "Remote '${remote_name}:' jest już skonfigurowany w ~/.config/rclone/rclone.conf."
        log_info "Testowanie połączenia z Google Drive..."
        if "$rclone_bin" about "${remote_name}:" &>/dev/null; then
            log_ok "Połączenie z Google Drive działa prawidłowo!"
            "$rclone_bin" about "${remote_name}:"
            return 0
        else
            log_warn "Połączenie zwróciło błąd. Może być wymagana ponowna autoryzacja."
        fi
    fi

    echo "=================================================================="
    echo "  KREATOR KONFIGURACJI GOOGLE DRIVE W RCLONE"
    echo "=================================================================="
    echo "Zaraz uruchomimy procedurę autoryzacji rclone dla zdalnego dysku: '${remote_name}'."
    echo "Wskazówki podczas kreatora:"
    echo "  1. Wybierz 'n' (New remote) i podaj nazwę: ${remote_name}"
    echo "  2. Wybierz typ dysku: drive (Google Drive)"
    echo "  3. 'client_id' oraz 'client_secret': wciśnij ENTER (domyślne)"
    echo "  4. 'scope': wybierz '1' (Full access to all files)"
    echo "  5. 'root_folder_id' i 'service_account_file': wciśnij ENTER"
    echo "  6. 'Edit advanced config': 'n'"
    echo "  7. 'Use web browser to authenticate': 'y' (otworzy przeglądarkę z logowaniem Google)"
    echo "  8. 'Configure this as a Shared Drive (Team Drive)': 'n'"
    echo "  9. 'Keep this remote': 'y' i 'q' (Quit config)"
    echo "=================================================================="
    read -rp "Naciśnij ENTER, aby uruchomić 'rclone config'..."

    "$rclone_bin" config
}

# ------------------------------------------------------------------------------
# 4. Status i diagnostyka
# ------------------------------------------------------------------------------

cmd_status() {
    echo "=================================================================="
    echo "  STATUS SYNCHRONIZACJI GOOGLE DRIVE (WORKSTATION HUB)"
    echo "=================================================================="

    local rclone_bin
    if rclone_bin=$(find_rclone); then
        log_ok "Binarka rclone: ${rclone_bin} ($($rclone_bin version | head -n 1))"
    else
        log_err "Brak rclone! Zainstaluj wykonując: make gdrive-install"
        return 1
    fi

    cmd_init_config
    local remote_name local_base
    remote_name=$(get_config_val "remote_name")
    local_base=$(get_config_val "local_base_dir")

    echo -e "\n--- Konfiguracja: ${CONFIG_FILE} ---"
    echo "Remote Name:     ${remote_name}:"
    echo "Katalog bazowy:  ${local_base}"

    if "$rclone_bin" listremotes 2>/dev/null | grep -q "^${remote_name}:"; then
        log_ok "Remote '${remote_name}:' obecny w rclone.conf"
        if "$rclone_bin" about "${remote_name}:" &>/dev/null; then
            log_ok "Łączność z API Google Drive: AKTYWNA"
            "$rclone_bin" about "${remote_name}:" | sed 's/^/  /'
        else
            log_warn "Nie udało się połączyć z API '${remote_name}:' (sprawdź token: make gdrive-auth)"
        fi
    else
        log_err "Remote '${remote_name}:' NIE jest skonfigurowany. Wykonaj: make gdrive-auth"
    fi

    echo -e "\n--- Synchronizowane Foldery ---"
    cmd_list_folders

    echo -e "\n--- Usługa Tła (systemd --user) ---"
    if systemctl --user is-active --quiet "${SERVICE_NAME}.timer" 2>/dev/null; then
        log_ok "Timer ${SERVICE_NAME}.timer jest AKTYWNY (automatyczna synchronizacja działa w tle)"
        systemctl --user list-timers "${SERVICE_NAME}.timer" --no-pager | head -n 3 | sed 's/^/  /'
    else
        log_warn "Timer ${SERVICE_NAME}.timer jest WYŁĄCZONY. Włącz go poleceniem: make gdrive-timer-enable"
    fi
}

# ------------------------------------------------------------------------------
# 5. Przeglądanie zasobów na Google Drive
# ------------------------------------------------------------------------------

cmd_list_remote() {
    local subpath="${1:-}"
    local rclone_bin
    rclone_bin=$(find_rclone) || { log_err "Brak rclone"; exit 1; }
    cmd_init_config
    local remote_name
    remote_name=$(get_config_val "remote_name")

    local target="${remote_name}:${subpath}"
    log_info "Katalogi w chmurze [${target}]:"
    "$rclone_bin" lsd "${target}" || true
}

# ------------------------------------------------------------------------------
# 6. Zarządzanie zdefiniowanymi katalogami
# ------------------------------------------------------------------------------

cmd_list_folders() {
    cmd_init_config
    python3 - "${CONFIG_FILE}" << 'PY_LIST_EOF'
import sys, json, os, subprocess

path = os.path.expanduser(sys.argv[1])
if not os.path.exists(path):
    print("  [Brak pliku konfiguracyjnego]")
    sys.exit(0)

with open(path) as f:
    data = json.load(f)

base = os.path.expanduser(data.get("local_base_dir", "~/GoogleDrive"))
folders = data.get("sync_folders", [])

if not folders:
    print("  [Brak zdefiniowanych folderów. Dodaj folder poleceniem: make gdrive-add REMOTE=<nazwa>]")
    sys.exit(0)

header = f"{'STATUS':<10} {'TRYB':<8} {'REMOTE PATH':<25} {'LOCAL DIR':<32} {'ROZMIAR LOKALNY'}"
print(header)
print("-" * 90)

for item in folders:
    enabled = "AKTYWNY" if item.get("enabled", True) else "WYŁĄCZONY"
    mode = item.get("mode", "bisync")
    rem = item.get("remote_path", "")
    loc_rel = item.get("local_path", rem)
    loc_full = os.path.join(base, loc_rel)
    
    size_str = "brak na dysku"
    if os.path.exists(loc_full):
        try:
            du = subprocess.check_output(["du", "-sh", loc_full], stderr=subprocess.DEVNULL).decode().split()[0]
            count = len(os.listdir(loc_full))
            size_str = f"{du} ({count} el.)"
        except Exception:
            size_str = "istnieje"

    row = f"{enabled:<10} {mode:<8} {rem:<25} {loc_full:<32} {size_str}"
    print(row)
PY_LIST_EOF
}

cmd_add_folder() {
    local remote_path="${1:-}"
    local local_path="${2:-}"
    local mode="${3:-bisync}"
    local desc="${4:-}"

    if [[ -z "${remote_path}" ]]; then
        log_err "Użycie: $0 add-folder <remote_path> [local_path] [mode] [desc]"
        exit 1
    fi

    if [[ -z "${local_path}" ]]; then
        local_path="${remote_path}"
    fi

    cmd_init_config
    local local_base
    local_base=$(get_config_val "local_base_dir")
    local full_local="${local_base}/${local_path}"
    mkdir -p "${full_local}"

    python3 - "${CONFIG_FILE}" "${remote_path}" "${local_path}" "${mode}" "${desc}" << 'PY_ADD_EOF'
import sys, json, os

path = os.path.expanduser(sys.argv[1])
rem = sys.argv[2]
loc = sys.argv[3]
mode = sys.argv[4]
desc = sys.argv[5]

with open(path) as f:
    data = json.load(f)

folders = data.get("sync_folders", [])
exists = False
for f in folders:
    if f.get("remote_path") == rem:
        f["local_path"] = loc
        f["mode"] = mode
        f["enabled"] = True
        if desc:
            f["description"] = desc
        exists = True
        break

if not exists:
    folders.append({
        "remote_path": rem,
        "local_path": loc,
        "mode": mode,
        "enabled": True,
        "description": desc
    })

data["sync_folders"] = folders
with open(path, "w") as f:
    json.dump(data, f, indent=2)
PY_ADD_EOF

    log_ok "Folder '${remote_path}' dodany do konfiguracji synchronizacji (${mode})!"
    log_info "Lokalna ścieżka docelowa: ${full_local}"
    log_info "Aby wykonać pierwszą inicjalizację, uruchom: make gdrive-sync FOLDER='${remote_path}' RESYNC=1"
}

cmd_remove_folder() {
    local remote_path="${1:-}"
    if [[ -z "${remote_path}" ]]; then
        log_err "Użycie: $0 remove-folder <remote_path>"
        exit 1
    fi

    cmd_init_config
    python3 - "${CONFIG_FILE}" "${remote_path}" << 'PY_REM_EOF'
import sys, json, os

path = os.path.expanduser(sys.argv[1])
rem = sys.argv[2]

with open(path) as f:
    data = json.load(f)

folders = [f for f in data.get("sync_folders", []) if f.get("remote_path") != rem]
data["sync_folders"] = folders

with open(path, "w") as f:
    json.dump(data, f, indent=2)
PY_REM_EOF

    log_ok "Usunięto '${remote_path}' z konfiguracji synchronizacji."
    log_info "Pliki lokalne na dysku NIE zostały usunięte."
}

# ------------------------------------------------------------------------------
# 7. Wykonanie synchronizacji (rclone bisync / sync)
# ------------------------------------------------------------------------------

sync_single_folder() {
    local rclone_bin="$1"
    local remote_name="$2"
    local local_base="$3"
    local remote_path="$4"
    local local_path="$5"
    local mode="$6"
    local dry_run="$7"
    local force_resync="$8"

    local remote_target="${remote_name}:${remote_path}"
    local local_target="${local_base}/${local_path}"

    mkdir -p "${local_target}"

    log_info "Synchronizacja: [${remote_target}] <--> [${local_target}] (Tryb: ${mode})"

    local dry_flag=""
    if [[ "${dry_run}" == "1" ]]; then
        dry_flag="--dry-run"
        log_warn "TRYB SYMULACJI (--dry-run) — brak trwałych zmian."
    fi

    case "${mode}" in
        bisync)
            local bisync_flags=(
                --check-access
                --conflict-resolve newer
                --drive-skip-gdocs
                --remove-empty-dirs
                --verbose
            )
            if [[ -n "${dry_flag}" ]]; then
                bisync_flags+=("${dry_flag}")
            fi

            if [[ "${force_resync}" == "1" ]]; then
                log_warn "Wymuszono flagę --resync (inicjalizacja bazy dwukierunkowej)..."
                "$rclone_bin" bisync "${remote_target}" "${local_target}" "${bisync_flags[@]}" --resync
            else
                set +e
                local sync_out
                sync_out=$("$rclone_bin" bisync "${remote_target}" "${local_target}" "${bisync_flags[@]}" 2>&1)
                local ret=$?
                set -e

                if [[ $ret -ne 0 ]]; then
                    if echo "${sync_out}" | grep -qE "Must use --resync to initialize|Prior path1 list not found|cannot find prior Path1 or Path2 listings"; then
                        log_warn "Brak bazy śledzenia dla '${remote_path}'. Uruchamiam automatyczną inicjalizację (--resync)..."
                        "$rclone_bin" bisync "${remote_target}" "${local_target}" "${bisync_flags[@]}" --resync
                    else
                        echo "${sync_out}"
                        log_err "Błąd synchronizacji bisync dla '${remote_path}'!"
                        return $ret
                    fi
                else
                    echo "${sync_out}"
                fi
            fi
            ;;
        pull)
            local pull_cmd=("$rclone_bin" sync "${remote_target}" "${local_target}" --drive-skip-gdocs --verbose)
            if [[ -n "${dry_flag}" ]]; then pull_cmd+=("${dry_flag}"); fi
            "${pull_cmd[@]}"
            ;;
        push)
            local push_cmd=("$rclone_bin" sync "${local_target}" "${remote_target}" --drive-skip-gdocs --verbose)
            if [[ -n "${dry_flag}" ]]; then push_cmd+=("${dry_flag}"); fi
            "${push_cmd[@]}"
            ;;
        *)
            log_err "Nieznany tryb synchronizacji: ${mode}"
            return 1
            ;;
    esac

    log_ok "Zakończono synchronizację dla '${remote_path}'."
}

cmd_sync() {
    local target_folder="${1:-}"
    local dry_run="${DRY_RUN:-0}"
    local force_resync="${RESYNC:-0}"

    local rclone_bin
    rclone_bin=$(find_rclone) || { log_err "Brak rclone!"; exit 1; }

    cmd_init_config
    local remote_name local_base
    remote_name=$(get_config_val "remote_name")
    local_base=$(get_config_val "local_base_dir")

    local self_script
    self_script="$(realpath "${BASH_SOURCE[0]}")"

    python3 - "${CONFIG_FILE}" "${target_folder}" "${rclone_bin}" "${self_script}" "${dry_run}" "${force_resync}" << 'PY_SYNC_EOF'
import sys, json, os, subprocess

path = os.path.expanduser(sys.argv[1])
target = sys.argv[2]
rclone_bin = sys.argv[3]
self_script = sys.argv[4]
dry_run = sys.argv[5]
force_resync = sys.argv[6]

if not os.path.exists(path):
    print("[BŁĄD] Brak pliku konfiguracji: " + path, file=sys.stderr)
    sys.exit(1)

with open(path) as f:
    data = json.load(f)

remote = data.get("remote_name", "gdrive")
base = os.path.expanduser(data.get("local_base_dir", "~/GoogleDrive"))
folders = data.get("sync_folders", [])

matched = 0

for item in folders:
    rem = item.get("remote_path", "")
    if target and target != rem and target != item.get("local_path", ""):
        continue
    if not item.get("enabled", True):
        continue
    matched += 1
    loc = item.get("local_path", rem)
    mode = item.get("mode", "bisync")
    
    cmd = [
        self_script, "_sync_single",
        rclone_bin, remote, base, rem, loc, mode, dry_run, force_resync
    ]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        sys.exit(res.returncode)

if matched == 0:
    if target:
        print(f"[WARN] Nie znaleziono aktywnego folderu pasującego do: {target}", file=sys.stderr)
    else:
        print("[INFO] Brak zdefiniowanych folderów do synchronizacji.", file=sys.stderr)
PY_SYNC_EOF
}

# ------------------------------------------------------------------------------
# 8. Integracja z systemd --user (Automatyczna synchronizacja w tle)
# ------------------------------------------------------------------------------

cmd_timer_enable() {
    local interval="${1:-}"
    cmd_init_config
    if [[ -z "${interval}" ]]; then
        interval=$(get_config_val "timer_interval")
        if [[ -z "${interval}" ]]; then
            interval="15m"
        fi
    fi

    mkdir -p "${SYSTEMD_USER_DIR}"

    local self_path
    self_path="$(realpath "${BASH_SOURCE[0]}")"

    cat << EOF_SRV > "${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"
[Unit]
Description=MnemoShift Google Drive Background Sync Service
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=${self_path} sync
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF_SRV

    cat << EOF_TMR > "${SYSTEMD_USER_DIR}/${SERVICE_NAME}.timer"
[Unit]
Description=Run MnemoShift Google Drive Sync every ${interval}

[Timer]
OnBootSec=2m
OnUnitActiveSec=${interval}
Persistent=true

[Install]
WantedBy=timers.target
EOF_TMR

    log_info "Przeładowywanie demona systemd --user..."
    systemctl --user daemon-reload
    systemctl --user enable --now "${SERVICE_NAME}.timer"

    log_ok "Włączono i uruchomiono timer: ${SERVICE_NAME}.timer (interwał: ${interval})"
    systemctl --user list-timers "${SERVICE_NAME}.timer" --no-pager
}

cmd_timer_disable() {
    log_info "Zatrzymywanie i wyłączanie ${SERVICE_NAME}.timer..."
    systemctl --user stop "${SERVICE_NAME}.timer" 2>/dev/null || true
    systemctl --user disable "${SERVICE_NAME}.timer" 2>/dev/null || true
    systemctl --user daemon-reload
    log_ok "Timer ${SERVICE_NAME}.timer został wyłączony."
}

# ------------------------------------------------------------------------------
# 9. Opcjonalny VFS Mount (przeglądanie całego dysku w Nautilusie na żądanie)
# ------------------------------------------------------------------------------

cmd_mount() {
    local subpath="${1:-}"
    local mountpoint="${2:-$HOME/GoogleDrive/Cloud-All}"

    local rclone_bin
    rclone_bin=$(find_rclone) || { log_err "Brak rclone"; exit 1; }
    cmd_init_config
    local remote_name
    remote_name=$(get_config_val "remote_name")

    mkdir -p "${mountpoint}"

    if mount | grep -q "${mountpoint}"; then
        log_warn "Katalog ${mountpoint} jest już zamontowany."
        return 0
    fi

    log_info "Montowanie [${remote_name}:${subpath}] w [${mountpoint}] z bezpiecznym lokalnym VFS cache..."
    nohup "$rclone_bin" mount "${remote_name}:${subpath}" "${mountpoint}" \
        --vfs-cache-mode full \
        --vfs-cache-max-age 24h \
        --vfs-cache-max-size 10G \
        --vfs-read-chunk-size 32M \
        --vfs-read-chunk-size-limit 512M \
        --dir-cache-time 15m \
        --daemon &>/dev/null &

    sleep 2
    if mount | grep -q "${mountpoint}"; then
        log_ok "Pomyślnie zamontowano w: ${mountpoint}"
    else
        log_err "Błąd montowania VFS. Sprawdź logi."
    fi
}

cmd_unmount() {
    local mountpoint="${1:-$HOME/GoogleDrive/Cloud-All}"
    if mount | grep -q "${mountpoint}"; then
        log_info "Odmontowywanie ${mountpoint}..."
        fusermount3 -u "${mountpoint}" || fusermount -u "${mountpoint}"
        log_ok "Odmontowano."
    else
        log_warn "Katalog ${mountpoint} nie jest zamontowany."
    fi
}

# ------------------------------------------------------------------------------
# Dispatcher
# ------------------------------------------------------------------------------

usage() {
    echo "=================================================================="
    echo "  WORKSTATION HUB: Google Drive Sync Controller (rclone)"
    echo "=================================================================="
    echo "Użycie: $0 <polecenie> [argumenty...]"
    echo ""
    echo "Główne polecenia:"
    echo "  status                       Audyt rclone, remote'a, katalogów i usługi tła"
    echo "  install                      Instaluje rclone do ~/.local/bin (bez sudo)"
    echo "  auth                         Interaktywna konfiguracja/autoryzacja Google Drive"
    echo "  list-remote [ścieżka]        Wyświetla katalogi na Google Drive"
    echo "  list-folders                 Wyświetla zdefiniowane foldery synchronizacji"
    echo "  add-folder <remote> [local] [mode] [desc]  Dodaje folder do synchronizacji"
    echo "  remove-folder <remote>       Usuwa folder z konfiguracji synchronizacji"
    echo "  sync [folder]                Uruchamia synchronizację (obsługuje DRY_RUN=1, RESYNC=1)"
    echo "  timer-enable [interwał]      Włącza automatyczną synchronizację w systemd (np. 15m)"
    echo "  timer-disable                Wyłącza automatyczną synchronizację systemd"
    echo "  mount [remote] [mountpoint]  Opcjonalne montowanie VFS z lokalnym cache"
    echo "  unmount [mountpoint]         Odmontowuje zasób VFS"
    echo "=================================================================="
    exit 1
}

main() {
    local cmd="${1:-}"
    shift || true

    case "${cmd}" in
        install)          cmd_install ;;
        init-config)      cmd_init_config ;;
        auth)             cmd_auth ;;
        status)           cmd_status ;;
        list-remote)      cmd_list_remote "$@" ;;
        list-folders)     cmd_list_folders ;;
        add-folder)       cmd_add_folder "$@" ;;
        remove-folder)    cmd_remove_folder "$@" ;;
        sync)             cmd_sync "$@" ;;
        timer-enable)     cmd_timer_enable "$@" ;;
        timer-disable)    cmd_timer_disable ;;
        mount)            cmd_mount "$@" ;;
        unmount)          cmd_unmount "$@" ;;
        _sync_single)     sync_single_folder "$@" ;;
        *)                usage ;;
    esac
}

main "$@"
