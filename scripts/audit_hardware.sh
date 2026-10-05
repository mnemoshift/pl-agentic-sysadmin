#!/usr/bin/env bash
# scripts/audit_hardware.sh — Kompleksowy audyt sprzętowy stacji roboczej
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INVENTORY_DIR="${REPO_ROOT}/inventory"
MD_FILE="${INVENTORY_DIR}/hardware.md"
JSON_FILE="${INVENTORY_DIR}/hardware.json"

mkdir -p "${INVENTORY_DIR}"

echo "=========================================================="
echo "  WORKSTATION HUB — AUDYT SPRZĘTOWY"
echo "  Data: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "=========================================================="

python3 - "$MD_FILE" "$JSON_FILE" << 'EOF'
import os
import sys
import json
import subprocess
from datetime import datetime

def run_cmd(cmd):
    try:
        env = dict(os.environ, LC_ALL="C")
        res = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        return res.stdout.strip()
    except Exception as e:
        return ""

def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

print("[1/7] Zbieranie danych o płycie głównej i systemie...")
board_vendor = read_file("/sys/devices/virtual/dmi/id/board_vendor") or "Unknown"
board_name = read_file("/sys/devices/virtual/dmi/id/board_name") or "Unknown"
bios_vendor = read_file("/sys/devices/virtual/dmi/id/bios_vendor") or "Unknown"
bios_version = read_file("/sys/devices/virtual/dmi/id/bios_version") or "Unknown"
bios_date = read_file("/sys/devices/virtual/dmi/id/bios_date") or "Unknown"
sys_vendor = read_file("/sys/devices/virtual/dmi/id/sys_vendor") or "Unknown"
product_name = read_file("/sys/devices/virtual/dmi/id/product_name") or "Unknown"

kernel = run_cmd("uname -r")
hostname = run_cmd("hostname")
os_name = run_cmd("grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '\"'")

print("[2/7] Badanie procesora (CPU)...")
cpu_model = run_cmd("lscpu | grep 'Model name:' | sed 's/Model name:[ \t]*//'")
cpu_cores = run_cmd("lscpu | grep '^Core(s) per socket:' | awk '{print $NF}'")
cpu_threads = run_cmd("lscpu | grep '^CPU(s):' | awk '{print $NF}'")
cpu_max_mhz = run_cmd("lscpu | grep 'CPU max MHz:' | awk '{print $NF}'")
cpu_min_mhz = run_cmd("lscpu | grep 'CPU min MHz:' | awk '{print $NF}'")
cpu_arch = run_cmd("uname -m")
cpu_l1d = run_cmd("lscpu | grep -i 'L1d cache:' | sed 's/.*:[ \t]*//'")
cpu_l1i = run_cmd("lscpu | grep -i 'L1i cache:' | sed 's/.*:[ \t]*//'")
cpu_l2 = run_cmd("lscpu | grep -i 'L2 cache:' | sed 's/.*:[ \t]*//'")
cpu_l3 = run_cmd("lscpu | grep -i 'L3 cache:' | sed 's/.*:[ \t]*//'")
cpu_virt = run_cmd("lscpu | grep 'Virtualization:' | sed 's/Virtualization:[ \t]*//'") or "Brak"

print("[3/7] Badanie pamięci RAM...")
ram_total_h = run_cmd("free -h | awk '/^Mem:/ {print $2}'")
ram_used_h = run_cmd("free -h | awk '/^Mem:/ {print $3}'")
ram_free_h = run_cmd("free -h | awk '/^Mem:/ {print $4}'")
ram_avail_h = run_cmd("free -h | awk '/^Mem:/ {print $7}'")
swap_total_h = run_cmd("free -h | awk '/^Swap:/ {print $2}'")
swap_used_h = run_cmd("free -h | awk '/^Swap:/ {print $3}'")

ram_total_bytes = run_cmd("free -b | awk '/^Mem:/ {print $2}'")
ram_avail_bytes = run_cmd("free -b | awk '/^Mem:/ {print $7}'")

print("[4/7] Badanie karty graficznej i VRAM (NVIDIA)...")
gpu_name = "N/A"
gpu_driver = "N/A"
gpu_vbios = "N/A"
gpu_bus_id = "N/A"
gpu_vram_total = "N/A"
gpu_vram_used = "N/A"
gpu_vram_free = "N/A"
gpu_temp = "N/A"
gpu_power_draw = "N/A"
gpu_power_limit = "N/A"
gpu_fan_speed = "N/A"

nvidia_raw = run_cmd("nvidia-smi --query-gpu=name,driver_version,vbios_version,pci.bus_id,memory.total,memory.used,memory.free,temperature.gpu,power.draw,power.limit,fan.speed --format=csv,noheader,nounits 2>/dev/null")
if nvidia_raw:
    parts = [p.strip() for p in nvidia_raw.split(",")]
    if len(parts) >= 11:
        gpu_name = parts[0]
        gpu_driver = parts[1]
        gpu_vbios = parts[2]
        gpu_bus_id = parts[3]
        gpu_vram_total = f"{parts[4]} MiB"
        gpu_vram_used = f"{parts[5]} MiB"
        gpu_vram_free = f"{parts[6]} MiB"
        gpu_temp = f"{parts[7]} °C"
        gpu_power_draw = f"{parts[8]} W"
        gpu_power_limit = f"{parts[9]} W"
        gpu_fan_speed = f"{parts[10]} %"
else:
    lspci_gpus = run_cmd("lspci | grep -E 'VGA|3D|Display' | sed -E 's/^[0-9a-f:.]* (VGA compatible controller|3D controller|Display controller): //'")
    if lspci_gpus:
        gpu_name = " / ".join([g.strip() for g in lspci_gpus.splitlines() if g.strip()])
    lspci_drivers = run_cmd("lspci -k | grep -EA3 'VGA|3D|Display' | grep 'Kernel driver in use:' | sed -E 's/.*:[[:space:]]*//'")
    if lspci_drivers:
        gpu_driver = " / ".join(list(dict.fromkeys([d.strip() for d in lspci_drivers.splitlines() if d.strip()])))


print("[5/7] Badanie pamięci masowej i dysków...")
lsblk_json_raw = run_cmd("lsblk -J -e7 -o NAME,SIZE,TYPE,FSTYPE,MODEL,SERIAL,MOUNTPOINTS,ROTA")
storage_devices = []
try:
    lsblk_data = json.loads(lsblk_json_raw)
    storage_devices = lsblk_data.get("blockdevices", [])
except Exception:
    pass

df_raw = run_cmd("df -hT -x tmpfs -x devtmpfs -x squashfs")

print("[6/7] Badanie urządzeń audio i kamer...")
audio_server = run_cmd("wpctl status 2>&1 | head -n 1") or "PipeWire"
alsa_cards = run_cmd("aplay -l 2>/dev/null | grep '^card '")
alsa_capture = run_cmd("arecord -l 2>/dev/null | grep '^card '")
audio_sinks = run_cmd("wpctl status 2>/dev/null | sed -n '/Sinks:/,/Sink endpoints:/p' | grep -E '^ [ *|]'")
audio_sources = run_cmd("wpctl status 2>/dev/null | sed -n '/Sources:/,/Filters:/p' | grep -E '^ [ *|]'")

cameras = []
v4l_dir = "/sys/class/video4linux"
if os.path.exists(v4l_dir):
    for entry in sorted(os.listdir(v4l_dir)):
        dev_path = f"/dev/{entry}"
        name = read_file(f"{v4l_dir}/{entry}/name")
        udev_prod = run_cmd(f"udevadm info -q property -n {dev_path} 2>/dev/null | grep -E '^ID_V4L_PRODUCT=' | head -n1 | cut -d= -f2")
        udev_vendor = run_cmd(f"udevadm info -q property -n {dev_path} 2>/dev/null | grep -E '^ID_VENDOR=' | head -n1 | cut -d= -f2")
        udev_driver = run_cmd(f"udevadm info -q property -n {dev_path} 2>/dev/null | grep -E '^ID_USB_DRIVER=' | head -n1 | cut -d= -f2")
        cameras.append({
            "device": dev_path,
            "name": name,
            "product": udev_prod or name,
            "vendor": udev_vendor or "Unknown",
            "driver": udev_driver or "uvcvideo"
        })

monitors_raw = run_cmd("xrandr --listmonitors 2>/dev/null")
monitors = []
for line in monitors_raw.splitlines():
    if ":" in line and not line.startswith("Monitors:"):
        monitors.append(line.strip())

print("[7/7] Badanie sieci i urządzeń USB...")
ip_addrs = run_cmd("ip -br a")
usb_devices = run_cmd("lsusb")

now_iso = datetime.now().isoformat()
now_human = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Tworzenie obiektu JSON
hardware_dict = {
    "audit_timestamp": now_iso,
    "system": {
        "hostname": hostname,
        "os": os_name,
        "kernel": kernel,
        "session_type": os.environ.get("XDG_SESSION_TYPE", "x11")
    },
    "motherboard": {
        "vendor": board_vendor,
        "model": board_name,
        "system_vendor": sys_vendor,
        "product_name": product_name,
        "bios": {
            "vendor": bios_vendor,
            "version": bios_version,
            "date": bios_date
        }
    },
    "cpu": {
        "model": cpu_model,
        "architecture": cpu_arch,
        "cores": cpu_cores,
        "threads": cpu_threads,
        "max_mhz": cpu_max_mhz,
        "min_mhz": cpu_min_mhz,
        "virtualization": cpu_virt,
        "cache": {
            "l1d": cpu_l1d,
            "l1i": cpu_l1i,
            "l2": cpu_l2,
            "l3": cpu_l3
        }
    },
    "ram": {
        "total_human": ram_total_h,
        "used_human": ram_used_h,
        "free_human": ram_free_h,
        "available_human": ram_avail_h,
        "total_bytes": int(ram_total_bytes) if ram_total_bytes.isdigit() else 0,
        "available_bytes": int(ram_avail_bytes) if ram_avail_bytes.isdigit() else 0,
        "swap_total": swap_total_h,
        "swap_used": swap_used_h
    },
    "gpu": {
        "name": gpu_name,
        "driver_version": gpu_driver,
        "vbios_version": gpu_vbios,
        "pci_bus_id": gpu_bus_id,
        "vram_total": gpu_vram_total,
        "vram_used": gpu_vram_used,
        "vram_free": gpu_vram_free,
        "temperature": gpu_temp,
        "power_draw": gpu_power_draw,
        "power_limit": gpu_power_limit,
        "fan_speed": gpu_fan_speed
    },
    "displays": monitors,
    "storage": {
        "devices": storage_devices,
        "df_summary": df_raw
    },
    "audio": {
        "server": audio_server,
        "alsa_playback": alsa_cards.splitlines(),
        "alsa_capture": alsa_capture.splitlines()
    },
    "cameras": cameras,
    "network": ip_addrs.splitlines(),
    "usb_devices": usb_devices.splitlines()
}

with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(hardware_dict, f, indent=2, ensure_ascii=False)

# Generowanie raportu Markdown
def build_storage_table(devices):
    lines = [
        "| Urządzenie | Rozmiar | Typ | System Plików | Model / Serial | Punkt Montowania |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |"
    ]
    def traverse(dev, indent=""):
        name = indent + dev.get("name", "")
        size = dev.get("size", "")
        dtype = dev.get("type", "")
        fstype = dev.get("fstype") or "-"
        model = (dev.get("model") or "").strip()
        serial = (dev.get("serial") or "").strip()
        desc = f"{model} ({serial})" if (model or serial) else "-"
        mounts = ", ".join([m for m in (dev.get("mountpoints") or []) if m]) or "-"
        lines.append(f"| `{name}` | {size} | {dtype} | `{fstype}` | {desc} | `{mounts}` |")
        for ch in dev.get("children", []):
            traverse(ch, indent + "└─ ")
    for d in devices:
        traverse(d)
    return "\n".join(lines)

def build_cameras_table(cams):
    if not cams:
        return "_Nie wykryto kamer V4L2._"
    lines = [
        "| Węzeł Urządzenia | Produkt | Producent | Sterownik |",
        "| :--- | :--- | :--- | :--- |"
    ]
    for c in cams:
        lines.append(f"| `{c['device']}` | **{c['product']}** | {c['vendor']} | `{c['driver']}` |")
    return "\n".join(lines)

def build_monitors_list(mons):
    if not mons:
        return "_Brak informacji o monitorach._"
    return "\n".join([f"- `{m}`" for m in mons])

md_content = f"""# Profil Sprzętowy Stacji Roboczej (hardware.md)
*Wygenerowano automatycznie przez `make audit` (`scripts/audit_hardware.sh`)*  
**Data audytu**: {now_human} ({now_iso})  
**Stacja**: `{hostname}` | **OS**: {os_name} | **Kernel**: `{kernel}`

---

## 1. Płyta Główna i BIOS
| Parametr | Wartość |
| :--- | :--- |
| **Producent Płyty** | {board_vendor} |
| **Model Płyty** | **{board_name}** |
| **BIOS Vendor** | {bios_vendor} |
| **Wersja BIOS** | `{bios_version}` (Wydany: {bios_date}) |
| **System Vendor / Produkt** | {sys_vendor} {product_name} |

---

## 2. Procesor (CPU)
| Parametr | Wartość |
| :--- | :--- |
| **Model** | **{cpu_model}** |
| **Architektura** | `{cpu_arch}` |
| **Rdzenie fizyczne / Wątki** | **{cpu_cores} rdzeni** / **{cpu_threads} wątków** |
| **Taktowanie Min / Max** | {cpu_min_mhz} MHz / **{cpu_max_mhz} MHz (Boost)** |
| **Wirtualizacja sprzętowa** | `{cpu_virt}` |
| **Pamięć Cache L1 / L2 / L3** | L1d: {cpu_l1d} • L2: {cpu_l2} • **L3: {cpu_l3}** |

---

## 3. Pamięć Operacyjna (RAM & Swap)
| Typ Pamięci | Całkowita | Użyta | Wolna | Dostępna |
| :--- | :--- | :--- | :--- | :--- |
| **RAM (Fizyczna)** | **{ram_total_h}** | {ram_used_h} | {ram_free_h} | **{ram_avail_h}** |
| **SWAP (Przestrzeń wymiany)** | **{swap_total_h}** | {swap_used_h} | {swap_total_h} | - |

---

## 4. Karta Graficzna (GPU) i Wyświetlacze
### Akcelerator Graficzny
| Parametr | Wartość |
| :--- | :--- |
| **Model GPU** | **{gpu_name}** |
| **Pamięć VRAM** | **{gpu_vram_total}** (Zajęte: {gpu_vram_used} • Wolne: {gpu_vram_free}) |
| **Wersja Sterownika NVIDIA** | **`{gpu_driver}`** |
| **Wersja VBIOS** | `{gpu_vbios}` |
| **Szyna PCI ID** | `{gpu_bus_id}` |
| **Temperatura / Wentylatory** | {gpu_temp} • Wentylatory: {gpu_fan_speed} |
| **Pobór Mocy / Limit** | {gpu_power_draw} / {gpu_power_limit} |

### Podłączone Ekrany (Monitory)
{build_monitors_list(monitors)}

---

## 5. Pamięć Masowa i Partycje (Storage)
### Dyski Fizyczne i Partycje
{build_storage_table(storage_devices)}

### Użycie Systemów Plików (`df -hT`)
```
{df_raw}
```

---

## 6. Urządzenia Multimedialne (Kamery & Audio)
### Kamery i Przechwytywanie Wideo (V4L2)
{build_cameras_table(cameras)}

### System Audio (PipeWire / WirePlumber)
- **Serwer Dźwięku**: `{audio_server}`
- **ALSA Playback Cards**:
```
{alsa_cards}
```
- **ALSA Capture Devices**:
```
{alsa_capture}
```

---

## 7. Interfejsy Sieciowe
```
{ip_addrs}
```

---

## 8. Wykaz Urządzeń USB (`lsusb`)
```
{usb_devices}
```
"""

with open(sys.argv[1], "w", encoding="utf-8") as f:
    f.write(md_content)

print(f"[OK] Wygenerowano raport Markdown: {sys.argv[1]}")
print(f"[OK] Wygenerowano raport JSON: {sys.argv[2]}")
EOF

echo "=========================================================="
echo "  Audyt sprzętowy ukończony pomyślnie."
echo "=========================================================="
