#!/usr/bin/env python3
"""
GhostShift Neural TTS - Select & Listen Reader
Autonomiczne narzędzie Text-To-Speech dla ekosystemu GhostShift (Zorin OS / Linux).
Wspiera bezpośredni odczyt zaznaczenia (X11 & Wayland), filtr Markdown i streaming do mpv.
"""

import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

# Automatyczna relokacja do dedykowanego venv jeśli skrypt uruchomiono interpreterem systemowym
VENV_PYTHON = Path.home() / ".local/share/ghostshift-tts/venv/bin/python3"
if VENV_PYTHON.exists() and sys.executable != str(VENV_PYTHON):
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

# Ścieżki konfiguracyjne
CONFIG_DIR = Path.home() / ".config" / "ghostshift-tts"
CONFIG_FILE = CONFIG_DIR / "config.json"
PID_FILE = Path("/tmp/ghostshift-tts.pid")
LOG_FILE = Path("/tmp/ghostshift-tts.log")

DEFAULT_CONFIG = {
    "voice": "pl-PL-MarekNeural",
    "rate": "+0%",
    "pitch": "+0Hz",
    "volume": "+0%",
    "clean_markdown": True
}

VOICE_CATALOG = {
    "pl-PL-MarekNeural": "Polski: Marek (Męski, naturalny, ciepły)",
    "pl-PL-ZofiaNeural": "Polski: Zofia (Żeński, spokojny, naturalny)",
    "en-US-JennyNeural": "Angielski (US): Jenny (Żeński, wszechstronny)",
    "en-US-GuyNeural": "Angielski (US): Guy (Męski, swobodny)",
    "en-US-AriaNeural": "Angielski (US): Aria (Żeński, profesjonalny)",
    "en-GB-SoniaNeural": "Angielski (UK): Sonia (Żeński, brytyjski)",
    "en-GB-RyanNeural": "Angielski (UK): Ryan (Męski, brytyjski)"
}

SPEED_OPTIONS = [
    ("Normalne (100%)", "+0%"),
    ("Lekko szybciej (115%)", "+15%"),
    ("Szybko (130%)", "+30%"),
    ("Bardzo szybko (150%)", "+50%"),
    ("Lekko wolniej (85%)", "-15%")
]


def log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def load_config():
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return {**DEFAULT_CONFIG, **cfg}
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def notify(title, message, icon="audio-volume-medium", timeout=2500):
    try:
        subprocess.run(
            ["notify-send", "-a", "GhostShift TTS", "-i", icon, "-t", str(timeout), title, message],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        log(f"Notify error: {e}")


def is_running():
    if not PID_FILE.exists():
        return False
    try:
        pid_str = PID_FILE.read_text().strip()
        if not pid_str:
            return False
        pid = int(pid_str)
        os.kill(pid, 0)
        return True
    except (ValueError, OSError):
        if PID_FILE.exists():
            PID_FILE.unlink(missing_ok=True)
        return False


def stop_speech():
    """Zatrzymuje aktywne czytanie. BEZWZGLĘDNIE nie używa os.killpg, aby nie ubić gsd-media-keys!"""
    stopped = False
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            if pid != os.getpid():
                log(f"Stopping worker PID {pid}")
                os.kill(pid, signal.SIGTERM)
                stopped = True
        except ProcessLookupError:
            pass
        except Exception as e:
            log(f"stop_speech error for PID: {e}")
        finally:
            PID_FILE.unlink(missing_ok=True)

    subprocess.run(["pkill", "-f", "mpv --no-video --really-quiet"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    if stopped:
        log("Speech playback stopped by toggle")
        notify("GhostShift TTS", "Odtwarzanie zatrzymane", "media-playback-stop", 1500)
    return stopped


def get_selected_text():
    """Pobiera tekst z bufora PRIMARY (zaznaczenie myszą), a jeśli pusty - ze schowka CLIPBOARD.
    Wspiera zarówno X11 (Gtk.Clipboard / xclip), jak i natywny Wayland (wl-paste)."""

    # 1. Próba Wayland (wl-paste) jeśli jesteśmy w sesji Wayland
    is_wayland = (os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY")))
    if is_wayland:
        try:
            res = subprocess.run(["wl-paste", "--primary", "--no-newline"], capture_output=True, text=True, timeout=1)
            if res.returncode == 0 and res.stdout.strip():
                log(f"Pobrano tekst z Wayland PRIMARY ({len(res.stdout)} znaków)")
                return res.stdout.strip()
        except Exception:
            pass
        try:
            res = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, text=True, timeout=1)
            if res.returncode == 0 and res.stdout.strip():
                log(f"Pobrano tekst z Wayland CLIPBOARD ({len(res.stdout)} znaków)")
                return res.stdout.strip()
        except Exception:
            pass

    # 2. Próba natywnego Gtk.Clipboard (X11 oraz aplikacje GTK)
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gdk, Gtk

        Gtk.init_check(None)

        primary = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
        text = primary.wait_for_text()
        if text and text.strip():
            log(f"Pobrano tekst z Gtk PRIMARY ({len(text)} znaków)")
            return text.strip()

        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        text = clipboard.wait_for_text()
        if text and text.strip():
            log(f"Pobrano tekst z Gtk CLIPBOARD ({len(text)} znaków)")
            return text.strip()
    except Exception as e:
        log(f"Gtk Clipboard error: {e}")

    # 3. Próba X11 xclip
    try:
        res = subprocess.run(["xclip", "-o", "-selection", "primary"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0 and res.stdout.strip():
            log(f"Pobrano tekst z xclip PRIMARY ({len(res.stdout)} znaków)")
            return res.stdout.strip()
        res = subprocess.run(["xclip", "-o", "-selection", "clipboard"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0 and res.stdout.strip():
            log(f"Pobrano tekst z xclip CLIPBOARD ({len(res.stdout)} znaków)")
            return res.stdout.strip()
    except Exception:
        pass

    log("Brak zaznaczonego tekstu w buforach")
    return ""


def clean_markdown_for_speech(text):
    """Czyści znaczniki Markdown, by lektor czytał tekst płynnie bez technicznych śmieci."""
    t = text

    # Zamień bloki kodu: ```język ... ``` -> [kod programu]
    t = re.sub(r'```[\w\-]*\n[\s\S]*?\n```', ' [kod programu] ', t)

    # Inline code `kod` -> kod
    t = re.sub(r'`([^`]+)`', r'\1', t)

    # Obrazy ![alt](url) -> usunięcie
    t = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', '', t)

    # Linki [Tekst](url) -> Tekst
    t = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', t)

    # Czyste adresy URL -> link
    t = re.sub(r'https?://\S+', ' link ', t)

    # Nagłówki Markdown #, ##, ### na początku linii -> tekst z kropką
    t = re.sub(r'^\s*#{1,6}\s*(.+)$', r'\1.', t, flags=re.MULTILINE)

    # Pogrubienia i kursywy: **tekst**, *tekst*, __tekst__, _tekst_
    t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)
    t = re.sub(r'\*([^*]+)\*', r'\1', t)
    t = re.sub(r'__([^_]+)__', r'\1', t)
    t = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'\1', t)

    # Przekreślenia ~~tekst~~
    t = re.sub(r'~~([^~]+)~~', r'\1', t)

    # Cytowania > tekst
    t = re.sub(r'^\s*>\s*', '', t, flags=re.MULTILINE)

    # Listy punktowane: usuń myślniki/gwiazdki na początku linii
    t = re.sub(r'^\s*[-*+]\s+', '', t, flags=re.MULTILINE)

    # Tabele Markdown: usuń separatory
    t = re.sub(r'\|[-:\s|]+\|', '', t)
    t = t.replace('|', ', ')

    # Znaczniki HTML np. <br>, <kbd>
    t = re.sub(r'<[^>]+>', '', t)

    # LaTeX $...$
    t = re.sub(r'\$([^$]+)\$', r'\1', t)

    # Wielokrotne spacje i puste linie
    t = re.sub(r'\n{3,}', '\n\n', t)
    t = re.sub(r'[ \t]+', ' ', t)

    return t.strip()


async def stream_tts(text, voice, rate="+0%", pitch="+0Hz", volume="+0%"):
    """Strumieniuje audio z edge-tts bezpośrednio do potoku mpv."""
    import edge_tts

    mpv_cmd = [
        "mpv",
        "--no-video",
        "--really-quiet",
        "--demuxer-lavf-format=mp3",
        "-"
    ]

    mpv_proc = subprocess.Popen(
        mpv_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    try:
        log(f"Rozpoczęcie syntezy edge_tts (głos: {voice}, znaki: {len(text)})")
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch, volume=volume)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio" and mpv_proc.poll() is None:
                try:
                    mpv_proc.stdin.write(chunk["data"])
                    mpv_proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    break

        if mpv_proc.stdin and not mpv_proc.stdin.closed:
            try:
                mpv_proc.stdin.close()
            except Exception:
                pass

        mpv_proc.wait()
        log("Odtwarzanie audio zakończone pomyślnie")
    except asyncio.CancelledError:
        log("Strumieniowanie anulowane")
    except Exception as e:
        log(f"Błąd podczas syntezy: {e}")
    finally:
        if mpv_proc.poll() is None:
            mpv_proc.terminate()
            try:
                mpv_proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                mpv_proc.kill()


def run_reader(custom_text=None):
    PID_FILE.write_text(str(os.getpid()))

    try:
        raw_text = custom_text if custom_text else get_selected_text()
        if not raw_text or not raw_text.strip():
            log("Nie odnaleziono tekstu do przeczytania")
            notify("GhostShift TTS", "Zaznacz najpierw tekst do przeczytania", "dialog-information", 2000)
            return

        cfg = load_config()
        text_to_speak = clean_markdown_for_speech(raw_text) if cfg.get("clean_markdown", True) else raw_text.strip()

        if not text_to_speak:
            log("Tekst pusty po oczyszczeniu Markdown")
            notify("GhostShift TTS", "Brak treści po przefiltrowaniu", "dialog-information", 2000)
            return

        voice = cfg.get("voice", "pl-PL-MarekNeural")
        rate = cfg.get("rate", "+0%")
        pitch = cfg.get("pitch", "+0Hz")
        volume = cfg.get("volume", "+0%")

        short_preview = (text_to_speak[:60] + "...") if len(text_to_speak) > 60 else text_to_speak
        notify("GhostShift TTS: Czytam...", f"{short_preview}", "audio-speakers", 2500)

        asyncio.run(stream_tts(text_to_speak, voice, rate=rate, pitch=pitch, volume=volume))
    except Exception as e:
        log(f"run_reader error: {e}")
    finally:
        if PID_FILE.exists():
            PID_FILE.unlink(missing_ok=True)


def action_toggle(custom_text=None):
    """Główna akcja pod skrót klawiszowy: jeśli mówi -> wyłącz; jeśli nie mówi -> czytaj."""
    log(f"action_toggle wywołana (czy działa: {is_running()})")
    if is_running():
        stop_speech()
    else:
        run_reader(custom_text)


def gui_config():
    """Graficzny konfigurator Zenity do wyboru głosu i prędkości."""
    cfg = load_config()
    current_voice = cfg.get("voice", "pl-PL-MarekNeural")
    current_rate = cfg.get("rate", "+0%")

    zenity_args = [
        "zenity",
        "--list",
        "--radiolist",
        "--title=GhostShift TTS - Konfiguracja Głosu",
        "--text=Wybierz neuronowy głos lektora:",
        "--column=Wybór",
        "--column=Identyfikator",
        "--column=Opis głosu",
        "--width=620",
        "--height=360"
    ]

    for v_id, desc in VOICE_CATALOG.items():
        is_selected = "TRUE" if v_id == current_voice else "FALSE"
        zenity_args.extend([is_selected, v_id, desc])

    res = subprocess.run(zenity_args, capture_output=True, text=True)
    if res.returncode != 0 or not res.stdout.strip():
        return

    chosen_voice = res.stdout.strip().split("|")[0]

    rate_args = [
        "zenity",
        "--list",
        "--radiolist",
        "--title=GhostShift TTS - Prędkość Mowy",
        "--text=Wybierz prędkość czytania:",
        "--column=Wybór",
        "--column=Wartość",
        "--column=Opis",
        "--width=450",
        "--height=300"
    ]

    for label, val in SPEED_OPTIONS:
        is_selected = "TRUE" if val == current_rate else "FALSE"
        rate_args.extend([is_selected, val, label])

    res_rate = subprocess.run(rate_args, capture_output=True, text=True)
    chosen_rate = current_rate
    if res_rate.returncode == 0 and res_rate.stdout.strip():
        chosen_rate = res_rate.stdout.strip().split("|")[0]

    cfg["voice"] = chosen_voice
    cfg["rate"] = chosen_rate
    save_config(cfg)

    notify("GhostShift TTS", f"Zapisano głos: {chosen_voice} ({chosen_rate})", "dialog-information")

    test_phrase = "Konfiguracja głosu została pomyślnie zapisana. Jakość dźwięku jest gotowa."
    if chosen_voice.startswith("en-"):
        test_phrase = "Voice configuration has been saved successfully. Audio quality is ready."

    asyncio.run(stream_tts(test_phrase, chosen_voice, rate=chosen_rate))


def print_usage():
    print("""Użycie: ghostshift-tts <komenda> [argumenty]

Komendy:
  toggle               Przełącz czytanie (start zaznaczonego tekstu / stop jeśli aktywne) [Domyślne pod skrót]
  read [tekst]         Czyta zaznaczony tekst lub opcjonalny podany tekst
  stop                 Natychmiast przerywa aktywne czytanie
  config               Otwiera graficzne okno wyboru głosu i prędkości (Zenity)
  set-voice <głos>     Ustawia aktywny głos (np. pl-PL-MarekNeural, pl-PL-ZofiaNeural)
  set-rate <tempo>     Ustawia tempo mowy (np. +0%, +15%, -15%)
  list-voices          Wyświetla dostępne rekomendowane głosy neuronowe
  status               Wyświetla aktualną konfigurację i stan
""")


def main():
    log(f"MAIN wywołany: {sys.argv} (PID: {os.getpid()}, PPID: {os.getppid()})")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "toggle"

    if cmd in ("toggle", "t"):
        text_arg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
        action_toggle(text_arg)
    elif cmd in ("read", "r"):
        text_arg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
        run_reader(text_arg)
    elif cmd in ("stop", "s", "kill"):
        stop_speech()
    elif cmd in ("config", "gui"):
        gui_config()
    elif cmd == "set-voice":
        if len(sys.argv) < 3:
            print("Podaj nazwę głosu, np.: ghostshift-tts set-voice pl-PL-ZofiaNeural")
            sys.exit(1)
        voice = sys.argv[2]
        cfg = load_config()
        cfg["voice"] = voice
        save_config(cfg)
        print(f"✔ Ustawiono głos: {voice}")
        notify("GhostShift TTS", f"Ustawiono głos: {voice}")
    elif cmd == "set-rate":
        if len(sys.argv) < 3:
            print("Podaj wartość tempa, np.: ghostshift-tts set-rate +15%")
            sys.exit(1)
        rate = sys.argv[2]
        cfg = load_config()
        cfg["rate"] = rate
        save_config(cfg)
        print(f"✔ Ustawiono tempo: {rate}")
    elif cmd == "list-voices":
        print("\nRekomendowane głosy neuronowe wysokiej jakości:")
        for v_id, desc in VOICE_CATALOG.items():
            print(f"  • {v_id:20} -> {desc}")
        print("\nPełna lista głosów Edge-TTS: uvx edge-tts --list-voices\n")
    elif cmd == "status":
        cfg = load_config()
        running = is_running()
        print("GhostShift TTS Status:")
        print(f"  Aktywny:   {'TAK (odtwarza)' if running else 'NIE (spoczynek)'}")
        print(f"  Głos:      {cfg.get('voice')}")
        print(f"  Tempo:     {cfg.get('rate')}")
        print(f"  Filtr MD:  {cfg.get('clean_markdown')}")
        print(f"  Config:    {CONFIG_FILE}")
    elif cmd in ("--help", "-h", "help"):
        print_usage()
    else:
        action_toggle(" ".join(sys.argv[1:]))


if __name__ == "__main__":
    main()
