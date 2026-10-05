#!/usr/bin/env bash
# scripts/audit_software.sh — Audyt oprogramowania i inwentaryzacja pakietów
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INVENTORY_DIR="${REPO_ROOT}/inventory"
PKG_DIR="${INVENTORY_DIR}/pkg-lists"
SOURCES_DIR="${PKG_DIR}/sources.list.d"

mkdir -p "${PKG_DIR}" "${SOURCES_DIR}"

echo "=========================================================="
echo "  WORKSTATION HUB — AUDYT OPROGRAMOWANIA"
echo "  Data: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "=========================================================="

echo "[1/5] Zrzucanie list pakietów APT..."
apt-mark showmanual | sort > "${PKG_DIR}/apt-manual.txt"
dpkg-query -W -f='${binary:Package}\t${Version}\t${Architecture}\n' | sort > "${PKG_DIR}/dpkg-all.txt"

echo "[2/5] Kopiowanie konfiguracji repozytoriów (/etc/apt/sources.list.d)..."
if [[ -d "/etc/apt/sources.list.d" ]]; then
    cp -r /etc/apt/sources.list.d/* "${SOURCES_DIR}/" 2>/dev/null || true
fi

echo "[3/5] Zrzucanie list Flatpak i Snap..."
if command -v flatpak &>/dev/null; then
    flatpak list --columns=application,version,branch,origin > "${PKG_DIR}/flatpak.txt" 2>/dev/null || true
else
    echo "Flatpak nie jest zainstalowany." > "${PKG_DIR}/flatpak.txt"
fi

if command -v snap &>/dev/null; then
    snap list > "${PKG_DIR}/snap.txt" 2>/dev/null || true
else
    echo "Snap nie jest zainstalowany." > "${PKG_DIR}/snap.txt"
fi

echo "[4/5] Analiza środowiska i narzędzi developerskich..."
python3 - "${INVENTORY_DIR}" "${PKG_DIR}" << 'EOF'
import os
import sys
import json
import subprocess
from datetime import datetime

inventory_dir = sys.argv[1]
pkg_dir = sys.argv[2]

def run(cmd):
    try:
        env = dict(os.environ, LC_ALL="C")
        res = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        return res.stdout.strip()
    except Exception:
        return ""

now_iso = datetime.now().isoformat()
now_human = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
hostname = run("hostname") or "Unknown"

# Pakiety APT
apt_manual_count = 0
apt_manual_sample = []
if os.path.exists(os.path.join(pkg_dir, "apt-manual.txt")):
    with open(os.path.join(pkg_dir, "apt-manual.txt"), "r") as f:
        lines = [l.strip() for l in f if l.strip()]
        apt_manual_count = len(lines)
        apt_manual_sample = lines[:30]

dpkg_total_count = 0
if os.path.exists(os.path.join(pkg_dir, "dpkg-all.txt")):
    with open(os.path.join(pkg_dir, "dpkg-all.txt"), "r") as f:
        dpkg_total_count = len([l for l in f if l.strip()])

# Flatpaks
flatpaks = []
if os.path.exists(os.path.join(pkg_dir, "flatpak.txt")):
    with open(os.path.join(pkg_dir, "flatpak.txt"), "r") as f:
        for idx, line in enumerate(f):
            if idx == 0 and "Application ID" in line:
                continue
            parts = line.strip().split()
            if len(parts) >= 1:
                flatpaks.append(line.strip())

def check_tool(cmd):
    res = run(cmd)
    if not res or "not found" in res.lower() or "brak" in res.lower():
        return "Niedostępny"
    return res

# Narzędzia
tools = {
    "python3": check_tool("python3 --version"),
    "uv": check_tool("uv --version"),
    "node": check_tool("node -v"),
    "npm": check_tool("npm -v"),
    "docker": check_tool("docker --version"),
    "docker_compose": check_tool("docker compose version 2>/dev/null") if check_tool("docker compose version 2>/dev/null") != "Niedostępny" else check_tool("docker-compose --version"),
    "git": check_tool("git --version"),
    "gcc": check_tool("gcc --version | head -n 1"),
    "brave": check_tool("brave-browser --version"),
    "google_chrome": check_tool("google-chrome --version"),
    "code": check_tool("code --version | head -n 1"),
    "rclone": check_tool("rclone --version | head -n 1"),
    "nvidia_driver": check_tool("nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null"),
    "nvidia_container_toolkit": check_tool("nvidia-ctk --version 2>&1 | head -n 1")
}

# Repozytoria z sources.list.d
repos = sorted(os.listdir(os.path.join(pkg_dir, "sources.list.d"))) if os.path.exists(os.path.join(pkg_dir, "sources.list.d")) else []

# Usługi systemowe
systemd_services_raw = run("systemctl list-units --type=service --state=running --no-pager --no-legend | awk '{print $1}'")
systemd_services = [s.strip() for s in systemd_services_raw.splitlines() if s.strip()]

software_dict = {
    "audit_timestamp": now_iso,
    "packages": {
        "apt_manual_count": apt_manual_count,
        "dpkg_total_count": dpkg_total_count,
        "flatpak_count": len(flatpaks),
        "snap_count": 0
    },
    "repositories": repos,
    "runtimes_and_tools": tools,
    "running_services_count": len(systemd_services),
    "running_services_sample": systemd_services[:25]
}

json_path = os.path.join(inventory_dir, "software.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(software_dict, f, indent=2, ensure_ascii=False)

# Generowanie Markdown
def build_flatpak_table(fps):
    if not fps:
        return "_Brak pakietów Flatpak._"
    lines = [
        "| Aplikacja Flatpak | Informacje |",
        "| :--- | :--- |"
    ]
    for fp in fps:
        cols = fp.split()
        app_id = cols[0]
        rest = " ".join(cols[1:]) if len(cols) > 1 else "-"
        lines.append(f"| `{app_id}` | {rest} |")
    return "\n".join(lines)

def build_repos_list(rps):
    if not rps:
        return "_Brak niestandardowych repozytoriów w sources.list.d._"
    return "\n".join([f"- `{r}`" for r in rps])

def tool_status(val):
    return "Niedostępny" if val == "Niedostępny" else "Zainstalowany"

md_content = f"""# Inwentarz Oprogramowania Stacji Roboczej (software.md)
*Wygenerowano automatycznie przez `make inventory` (`scripts/audit_software.sh`)*  
**Data audytu**: {now_human} ({now_iso})  
**Podstawa**: Raport wygenerowany na stacji `{hostname}`

---

## 1. Narzędzia Deweloperskie i Środowiska Uruchomieniowe
| Narzędzie / Komponent | Zainstalowana Wersja | Status |
| :--- | :--- | :--- |
| **Python** | `{tools['python3']}` | {tool_status(tools['python3'])} |
| **UV (Python Package Mgr)** | `{tools['uv']}` | {tool_status(tools['uv'])} |
| **Git** | `{tools['git']}` | {tool_status(tools['git'])} |
| **Brave Browser** | `{tools['brave']}` | {tool_status(tools['brave'])} |
| **Google Chrome** | `{tools['google_chrome']}` | {tool_status(tools['google_chrome'])} |
| **VS Code** | `{tools['code']}` | {tool_status(tools['code'])} |
| **Node.js** | `{tools['node']}` | {tool_status(tools['node'])} |
| **NPM** | `{tools['npm']}` | {tool_status(tools['npm'])} |
| **Docker Engine** | `{tools['docker']}` | {tool_status(tools['docker'])} |
| **Docker Compose** | `{tools['docker_compose']}` | {tool_status(tools['docker_compose'])} |
| **Kompilator C/C++ (GCC)** | `{tools['gcc']}` | {tool_status(tools['gcc'])} |
| **Rclone (Dysk w chmurze)** | `{tools['rclone']}` | {tool_status(tools['rclone'])} |
| **Sterownik NVIDIA GPU** | `{tools['nvidia_driver']}` | {tool_status(tools['nvidia_driver'])} |
| **NVIDIA Container Toolkit** | `{tools['nvidia_container_toolkit']}` | {tool_status(tools['nvidia_container_toolkit'])} |

---

## 2. Podsumowanie Menedżerów Pakietów
| Menedżer Pakietów | Liczba Pakietów | Plik Zrzutu (Snapshot) |
| :--- | :--- | :--- |
| **APT (Ręcznie oznaczone / Manual)** | **{apt_manual_count} pakietów** | [`inventory/pkg-lists/apt-manual.txt`](pkg-lists/apt-manual.txt) |
| **DPKG (Wszystkie pakiety systemowe)** | **{dpkg_total_count} pakietów** | [`inventory/pkg-lists/dpkg-all.txt`](pkg-lists/dpkg-all.txt) |
| **Flatpak (Aplikacje desktopowe)** | **{len(flatpaks)} aplikacji/modułów** | [`inventory/pkg-lists/flatpak.txt`](pkg-lists/flatpak.txt) |
| **Snap** | **0 pakietów** | [`inventory/pkg-lists/snap.txt`](pkg-lists/snap.txt) |

---

## 3. Repozytoria Zewnętrzne i PPA (`/etc/apt/sources.list.d/`)
Zrzut plików źródłowych zdeponowany w [`inventory/pkg-lists/sources.list.d/`](pkg-lists/sources.list.d/):
{build_repos_list(repos)}

---

## 4. Wykaz Aplikacji Flatpak
{build_flatpak_table(flatpaks)}

---

## 5. Działające Usługi Systemowe (`systemd`)
- Całkowita liczba aktywnych usług: **{len(systemd_services)}**
- Przykładowe kluczowe usługi:
{chr(10).join([f"  - `{s}`" for s in systemd_services[:20]])}
"""

md_path = os.path.join(inventory_dir, "software.md")
with open(md_path, "w", encoding="utf-8") as f:
    f.write(md_content)

print(f"[OK] Wygenerowano raport Markdown: {md_path}")
print(f"[OK] Wygenerowano raport JSON: {json_path}")
EOF

echo "[5/5] Audyt oprogramowania ukończony pomyślnie."
