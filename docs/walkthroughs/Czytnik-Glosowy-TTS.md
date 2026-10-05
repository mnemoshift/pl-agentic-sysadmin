# GhostShift Neural TTS — Czytnik Tekstu 'Select & Listen' (Edge Neural)
*Autonomiczne narzędzie Text-To-Speech dla stacji roboczej Linux (Zorin OS / GNOME)*

---

## 🎯 1. Cel i Filozofia: Dlaczego nie SaaS i dlaczego nie eSpeak?

Praca inżyniera oprogramowania z agentami AI (Antigravity IDE, Claude Code) polega na ciągłej analizie kodu, planów architektonicznych i dokumentacji. 

Tradycyjne rozwiązania na Linuksie dzielą się na dwie skrajności:
1. **Robotyczne syntezatory z lat 90. (`espeak`, stary `festival`):** Brzmią metalicznie, nie potrafią poprawnie intonować zdań w języku polskim, a po 2 minutach słuchania powodują zmęczenie poznawcze.
2. **Komercyjne narzędzia SaaS / abonamenty:** Wymagają płatnych subskrypcji, wysyłają prywatny kod do zewnętrznych chmur i nie integrują się płynnie ze skrótami systemowymi powłoki GNOME.

**GhostShift Neural TTS** rozwiązuje ten problem bezkompromisowo:
* Wykorzystuje wysokiej jakości neuronowe modele mowy **Microsoft Edge Neural TTS** (`pl-PL-MarekNeural`, `pl-PL-ZofiaNeural`, głosy angielskie Jenny, Guy, Aria, Ryan).
* Działa w 100% lokalnie w przestrzeni użytkownika (user-space, brak uprawnień roota).
* **Zasada Select & Listen:** Wystarczy zaznaczyć tekst kursorem myszy w dowolnej aplikacji (Antigravity, terminal, przeglądarka) i wcisnąć `<Super> + R` — czytnik natychmiast zaczyna czytać zaznaczenie. Zero wciskania `Ctrl + C` i zero otwierania dodatkowych okien.

---

## 🏛️ 2. Architektura Systemowa

```mermaid
graph TD
    User([Użytkownik]) -->|1. Zaznaczenie tekstu myszą| App[Dowolna aplikacja: Antigravity / Browser / Terminal]
    User -->|2. Wciśnięcie Super + R| MediaKeys[GNOME gsd-media-keys]
    
    MediaKeys -->|Uruchomienie| Script[~/.local/bin/ghostshift-tts toggle]
    
    subgraph Bufor i Ekstrakcja
        Script -->|Detekcja sesji| Detect{Wayland czy X11?}
        Detect -->|Wayland| WlPaste[wl-paste --primary / Gtk.Clipboard]
        Detect -->|X11| GtkClipboard[Gtk.Clipboard SELECTION_PRIMARY / xclip]
    end
    
    subgraph Przetwarzanie i Filtr
        WlPaste --> Filter[Filtr Markdown: oczyszczenie kodu, URL i tabel]
        GtkClipboard --> Filter
    end
    
    subgraph Streaming Audio (<250ms)
        Filter --> EdgeTTS[Dedykowany venv: edge-tts Communicate.stream]
        EdgeTTS -->|Potok STDIN MP3| MPV[Odtwarzacz mpv --no-video -]
        MPV --> AudioOut([Głośniki / Słuchawki PipeWire])
    end
```

### Kluczowe Filary Architektury:
1. **Ultra-niska latencja (< 250 ms):**  
   Dźwięk nie jest zapisywany na dysk w plikach tymczasowych. Pakiet `edge-tts` strumieniuje pakiety audio bezpośrednio na wejście standardowe procesu `mpv` (`demuxer-lavf-format=mp3 -`). Pierwsze słowa słyszysz ułamki sekund po wciśnięciu skrótu.
2. **Inteligentny Filtr Markdown:**  
   Przed syntezą tekst przechodzi przez filtr `clean_markdown_for_speech()`:
   * Wieloliniowe bloki kodu (` ```python ... ``` `) są zastępowane naturalną zapowiedzią `[kod programu]`,
   * Adresy URL (`https://...`) są zamieniane na słowo `link`,
   * Usuwane są techniczne separatory tabel (`|---|`), gwiazdki pogrubień, nagłówki `#` i znaczniki HTML. Lektor czyta czystą prozę merytoryczną.
3. **Mechanizm Toggle (Start / Stop):**  
   Skrót `<Super> + R` działa dwukierunkowo. Jeśli lektor milczy $\to$ rozpoczyna czytanie zaznaczenia. Jeśli lektor aktualnie czyta $\to$ natychmiast przerywa odtwarzanie i zwalnia proces `mpv`.
4. **Odporność na Ubicie Demona GNOME (Hartowanie PID):**  
   W odróżnieniu od naiwnych implementacji używających `os.killpg` (które w środowisku GNOME ubijały nadrzędny demon `gsd-media-keys`), czytnik selektywnie zatrzymuje wyłącznie własny proces roboczy (`os.kill(worker_pid, SIGTERM)`) i podproces `mpv`.

---

## ⚡ 3. Interfejs Operacyjny (Makefile)

Wszystkie procedury instalacji, testowania i konfiguracji są zintegrowane w głównym `Makefile`:

```bash
# 1. Sprawdzenie stanu czytnika, venv i skrótów klawiszowych
make tts-status

# 2. Jednorazowa instalacja (pakiety systemowe, venv, launcher, skróty GNOME)
make tts-install

# 3. Odtworzenie próbki testowej głosu
make tts-test

# 4. Otwarcie graficznego konfiguratora wyboru głosu i tempa mowy (Zenity GUI)
make tts-config

# 5. Całkowite odinstalowanie czytnika i usunięcie skrótów
make tts-uninstall
```

---

## 🎮 4. Skróty Klawiszowe i Konfiguracja

Domyślnie instalator rejestruje dwa globalne skróty w powłoce GNOME:
* **`<Super> + R`** (R jak *Read*) — domyślny, ergonomiczny skrót pod lewą rękę.
* **`<Ctrl> + <Alt> + S`** (S jak *Speech*) — alternatywny skrót kompatybilny z aplikacjami przechwytującymi klawisz Super.

### Dostępne Głosy Neuronowe:
Wybór głosu odbywa się przez polecenie `make tts-config` lub w menu aplikacji: **Konfigurator Głosu TTS (GhostShift)**:
* `pl-PL-MarekNeural` — Męski, ciepły, naturalny (domyślny).
* `pl-PL-ZofiaNeural` — Żeński, spokojny, studyjny.
* `en-US-JennyNeural` / `en-US-GuyNeural` / `en-US-AriaNeural` — Głosy amerykańskie.
* `en-GB-RyanNeural` / `en-GB-SoniaNeural` — Głosy brytyjskie.

Tempo mowy można płynnie regulować od `-15%` (wolniej) do `+50%` (szybki odsłuch dokumentacji).
