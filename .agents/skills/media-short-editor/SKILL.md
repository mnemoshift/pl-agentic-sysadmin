---
name: media-short-editor
description: Automatyzacja postprodukcji i montażu wideo YouTube Shorts (format pionowy 9:16 1080x1920) w Kdenlive z wykorzystaniem serwera Kdenlive MCP, modeli Whisper, normalizacji EBU R128 oraz reguł Agentic SysAdmina. Używaj, gdy użytkownik zleca sprawdzenie gotowości Kdenlive/narzędzi, czyszczenie/normalizację audio z OBS-a, generację grafik pionowych pod tytuły, kaskadowy montaż osi czasu MLT lub wygenerowanie dynamicznych napisów karaoke (CapCut style).
---

# Media Short Editor Skill (Workstation Hub Core Skill)

Skill dostarcza w pełni zautomatyzowane, powtarzalne procedury przygotowania i montażu wideo w formacie YouTube Shorts (9:16 1080x1920 @ 60fps) na stacji roboczej Linux (Zorin OS) bez użycia chmurowych edytorów i płatnych subskrypcji.

---

## 1. Dostępne Moduły i Interfejs Operacyjny (Makefile)

Wszystkie operacje są wspierane przez moduły w `scripts/media/` oraz dedykowane cele w `Makefile`:

```bash
# 0. Konfiguracja i audyt Kdenlive MCP (User-Space, Flatpak, venv uv, wrappery CLI)
make media-check-mcp
make media-setup-mcp

# 1. Czyszczenie audio: przycięcie ciszy, usunięcie falstartu i normalizacja do -14 LUFS (EBU R128)
make media-clean-audio
# lub: python3 scripts/media/clean_audio.py -i work/<ID>/input/raw_voiceover.mp4 -o work/<ID>/assets/<ID>_VoiceOver_CLEAN.wav

# 2. Generowanie dynamicznych napisów CapCut Karaoke (Whisper + ASS z anti-overlap)
make media-karaoke
# lub: uv run scripts/media/generate_karaoke.py -a work/<ID>/assets/<ID>_VoiceOver_CLEAN.wav -o work/<ID>/assets/<ID>_Karaoke.ass --fast

# 3. Kaskadowy montaż projektu Kdenlive 9:16 (rozmyte tło V1 + ostry klip V2 + tytuły V3 + audio A1)
make media-build-short
# lub: python3 scripts/media/build_kdenlive_short.py -w work/<ID>
```

---

## 2. Standard Wykonawczy dla Jednozdaniowych Promptów

Agent interpretuje krótkie, jednozdaniowe polecenia użytkownika i automatycznie realizuje kompletny cykl procedury:

### Krok 0: Konfiguracja i instalacja środowiska (Gdy Kdenlive nie jest zainstalowany)
* **Prompt użytkownika:** `Skonfiguruj Kdenlive i serwer MCP do montażu wideo.`
* **Działanie Agenta:**
  1. Sprawdza i instaluje Flatpak `org.kde.kdenlive` w user-space (`flatpak install --user flathub org.kde.kdenlive -y`).
  2. Tworzy wrappery w `~/.local/bin/` dla `kdenlive` oraz `melt`.
  3. Klonuje serwer `kdenlive-mcp`, tworzy środowisko `uv venv` z `mcp<2` i aplikuje poprawki XML.
  4. Generuje konfigurację w `~/.gemini/config/mcp_config.json`.
  5. Raportuje pełną gotowość.

### Krok 1: Weryfikacja środowiska
* **Prompt użytkownika:** `Sprawdź gotowość Kdenlive i narzędzi multimedialnych.`
* **Działanie Agenta:**
  1. Sprawdza dostępność serwera MCP `kdenlive` (narzędzia `mcp_kdenlive_*`).
  2. Weryfikuje obecność silnika `melt` (`which melt`).
  3. Potwierdza obecność modułów w `scripts/media/` i szablonów w `templates/kdenlive/`.
  4. Zwraca zwięzłe podsumowanie: status serwera, wersja silnika, gotowość do pracy.

### Krok 2: Audyt i czyszczenie audio
* **Prompt użytkownika:** `Oczyść surowe nagranie z OBS-a i przygotuj dźwięk do montażu.`
* **Działanie Agenta:**
  1. Lokalizuje surowy plik w katalogu roboczym (domyślnie `work/EP002_Short/input/raw_voiceover.mp4`).
  2. Wykonuje moduł `scripts/media/clean_audio.py` (lub `make media-clean-audio`).
  3. Automatycznie wycina początkową ciszę, usuwa falstart przed 30 sekundą oraz martwy ogon nagrania.
  4. Przeprowadza dwuprzebiegową normalizację do standardu YouTube (`-14.0 LUFS`, True Peak `< -1.0 dBFS`).
  5. Zapisuje wyjściowy plik `assets/EP002_Short_VoiceOver_CLEAN.wav` i raportuje dokładną długość oraz parametry EBU R128 w czacie.

### Krok 3: Generacja grafik pionowych 9:16
* **Prompt użytkownika:** `Wygeneruj 3 pionowe grafiki koncepcyjne z ciemną górą pod tytuły.`
* **Działanie Agenta:**
  1. Generuje 3 wertykalne kadry 1080x1920 do katalogu roboczego `work/EP002_Short/assets/`:
     - `kadr1_agentic_sysadmin.jpg`: Cybernetyczny rdzeń decyzyjny AI / serwerownia.
     - `kadr2_config_chaos.jpg`: Złożony labirynt plików konfiguracyjnych i dotfiles.
     - `kadr3_macos_desktop.jpg`: Minimalistyczne biurko, kontrast domyślny Zorin vs styl macOS.
  2. **Żelazna reguła kadrowania:** Górna 1/3 kadru musi pozostać ciemna i pozbawiona jakichkolwiek wtopionych napisów (przestrzeń zarezerwowana na napisy tytułowe w Kdenlive).

### Krok 4: Kaskadowy montaż osi czasu Kdenlive
* **Prompt użytkownika:** `Zmontuj pionowy projekt Kdenlive z kaskadowym tłem i tytułami.`
* **Działanie Agenta:**
  1. Wywołuje `scripts/media/build_kdenlive_short.py` (lub `make media-build-short`).
  2. Buduje projekt XML `work/EP002_Short/EP002_Short.kdenlive` o profilu 1080x1920 @ 60fps.
  3. Układa ścieżki zgodnie ze standardem MLT:
     - **A1:** Oczyszczony plik lektorski `assets/EP002_Short_VoiceOver_CLEAN.wav`.
     - **V1 (Tło):** Poziome wycinki wideo powiększone do pionu z filtrem rozmycia `gblur` (sigma 14).
     - **V2 (Główna oś):** 3 grafiki koncepcyjne oraz 2 wycinki z materiału źródłowego z eleganckim cieniem.
     - **V3 (Tytuły):** Plansze tytułowe dla 5 fraz z fontem Inter Black 76px, wyśrodkowane.
  4. Kompozycja `qtblend`: prawidłowa kaskada ścieżek (`V1` do tła 0, wyższe ścieżki do `pos - 1`).

### Krok 5: Dynamiczne napisy CapCut Karaoke
* **Prompt użytkownika:** `Wygeneruj dynamiczne napisy karaoke CapCuta i podepnij pod projekt.`
* **Działanie Agenta:**
  1. Wywołuje `scripts/media/generate_karaoke.py` (lub `make media-karaoke`).
  2. Model `faster-whisper` przetwarza audio ze znacznikami na poziomie pojedynczych słów.
  3. Grupuje słowa w dynamiczne frazy po 2-3 wyrazy w linijce z neonowo-zielonym podświetleniem aktywnego słowa (`#00FF66`).
  4. **Systemowa reguła Anti-Overlap:** Skrypt automatycznie wyrównuje czasy końców i początków kolejnych klatek (`cur.end = nxt.start`), gwarantując brak nachodzenia na siebie na osi czasu i brak pionowego skakania tekstu.
  5. Zapisuje plik `assets/EP002_Short_Karaoke.ass` oraz sidecar sekwencji Kdenlive, integrując napisy z projektem.

### Krok 6: Weryfikacja projektu (Opcjonalnie)
* **Prompt użytkownika:** `Zweryfikuj poprawność projektu przed renderem.`
* **Działanie Agenta:** Sprawdza poprawność XML, ładuje projekt weryfikacyjnie silnikiem `melt` i potwierdza gotowość do otwarcia w Kdenlive GUI lub bezpośredniego renderu NVENC.
