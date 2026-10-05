---
name: desktop-manager
description: Zarządzanie profilami pulpitu stacji roboczej (profil Cyber Studio z HUD i telemetrią emisyjną, styl macOS WhiteSur, reset do vanilla Zorin, unifikacja kontrolek okien CSD w VS Code/Chrome oraz dok Plank). Używaj, gdy użytkownik prosi o zmianę wyglądu pulpitu, konfigurację studia nagrań, usunięcie zegara z paska emisyjnego, telemetrię GPU/CPU, reset ustawień lub synchronizację belek okien.
---

# Desktop Manager Skill (Workstation Hub Core Skill)

Ten skill dostarcza zautomatyzowane, weryfikowalne procedury zarządzania środowiskiem graficznym stacji roboczej (ze szczególnym uwzględnieniem Zorin OS / GNOME / X11), profilu emisyjnego wideo (Cyber Studio & Emission HUD), rozwiązywania problemów z Client-Side Decorations (CSD) oraz deterministycznego resetu do stanu domyślnego.

---

## 1. Dostępne Profile i Polecenia Operacyjne

Skill wykorzystuje zintegrowany kontroler pulpitu `scripts/desktop_ctl.sh` dostępny przez `Makefile`:

```bash
# Wdrożenie profilu Cyber Studio (MnemoShift Cyber-Blueprint, Top Bar Emission HUD, Conky HUD, Plank HUD)
make desktop-studio
# lub bezpośrednio:
./scripts/desktop_ctl.sh apply-studio

# Wdrożenie profilu emisyjnego macOS (WhiteSur, kropki po lewej, taskbar góra, Plank dół, CSD fix)
make desktop-macos
# lub bezpośrednio:
./scripts/desktop_ctl.sh apply-macos

# Błyskawiczny powrót do domyślnego stanu Zorin OS (kropki po prawej, pasek dół, wyłączenie Planka, Conky i rozszerzeń)
make desktop-reset
# lub bezpośrednio:
./scripts/desktop_ctl.sh reset

# Audyt bieżącego stanu dekoracji, motywów, procesów doku i telemetrii
make desktop-status
# lub bezpośrednio:
./scripts/desktop_ctl.sh status
```

---

## 2. Architektura Profilu Cyber Studio (MnemoShift Studio HUD)

Profil Cyber Studio (`make desktop-studio`) rozwiązuje kluczowe wyzwania produkcyjne stacji nagraniowej:

1. **Eliminacja Błędów Ciągłości Montażowej (Anti-Continuity Error):**
   - Na monitorze emisyjnym (`HDMI-0`, 16:9) zegar i data są całkowicie ukryte w `zorin-taskbar` (`panel-element-positions-monitors-sync = false`).
   - Zapobiega to dekoncentracji widza, gdy kolejne ujęcia (takes) screencastu były nagrywane o różnych godzinach.
   - Monitor główny roboczy (`DP-4`, 21:9 Ultra-Wide) zachowuje standardowy zegar i kalendarz.

2. **Natywne Rozszerzenie GNOME Shell — MnemoShift Emission HUD:**
   - W wolnym slocie środkowym paska emisyjnego instalowane jest rozszerzenie `mnemoshift-emission-hud@ghostshift.eu`.
   - Zapewnia asynchroniczny (non-blocking) odczyt w czasie rzeczywistym: `CPU %`, `RAM GiB`, `GPU CUDA %` oraz `VRAM GiB` akceleratora RTX 4060 Ti 16GB.

3. **Widget Telemetryczny Conky HUD na Przydymionym Szkle:**
   - Poprzednio tekst zlewał się ze skomplikowaną siatką CAD tapety.
   - Zastosowano panel ARGB (`#0B0E14`, ~86% krycia) z laserową obwódką cyan (`#29F0F7`).
   - Obsługa wielu monitorów (`mnemoshift_hud_dp4.conf` i `mnemoshift_hud_hdmi0.conf`).

4. **Kapsułkowy Dok Plank (Pill Dock):**
   - Motyw `MnemoShift-HUD` z obwódką cyan (`#29F0F7`), miękkim zaokrągleniem (`TopRoundness=16`, `BottomRoundness=16`) i neonową kropką aktywności.

5. **Spanned / Multi-Monitor Wallpaper Dispatcher:**
   - Automatyczny wybór: obraz kompozytowy 5360×1440 w trybie spanned przy dwóch aktywnych monitorach lub wykadrowana tapeta przy jednym ekranie.

---

## 3. Architektura Ramek Okien: SSD vs CSD

Środowisko graficzne Linuksa dzieli okna na dwie kategorie:

1. **Server-Side Decorations (SSD) — Natywne okna systemowe (Mutter):**
   * Dotyczy: Nautilus, Terminal, Ustawienia, aplikacje GTK4/libadwaita.
   * Kontrolowane przez: `gsettings set org.gnome.desktop.wm.preferences button-layout 'close,minimize,maximize:'`.
   * Reagują natychmiast po zmianie klucza GSettings.

2. **Client-Side Decorations (CSD) — Aplikacje Electron i Chromium:**
   * Dotyczy: **Visual Studio Code**, **Google Chrome**, **Brave**.
   * Aplikacje te domyślnie ignorują ustawienia menedżera okien Mutter i same rysują nagłówek z przyciskami po prawej stronie.
   * **Rozwiązanie w ramach skilla:**
     * **VS Code:** Wymuszenie `"window.titleBarStyle": "native"` w `~/.config/Code/User/settings.json`.
     * **Google Chrome:** Ustawienie `"custom_chrome_frame": false` w plikach `~/.config/google-chrome/*/Preferences`.
     * Wymuszenie to oddaje dekorację okna menedżerowi Mutter, co zapewnia 100% spójności wizualnej (traffic lights po lewej stronie w całym systemie).

> [!NOTE]
> **Antigravity IDE:** Posiada sztywno zadeklarowany tryb bezramkowy (`titleBarStyle: 'hidden'`) z wykorzystaniem Chromium Window Controls Overlay. Zgodnie z wytycznymi architektonicznymi pozostawiamy Antigravity w nowoczesnym układzie frameless bez modyfikowania plików `.asar`.

---

## 4. Protokół Wykonawczy dla Agenta

Gdy użytkownik zleca Ci konfigurację pulpitu lub jego reset:
1. **Audyt wstępny (Pre-flight):**
   Wywołaj `make desktop-status` i sprawdź aktualne motywy, status doku, Conky oraz rozszerzenia GNOME.
2. **Wykonanie atomowe:**
   Wywołaj odpowiedni cel `make desktop-studio`, `make desktop-macos` lub `make desktop-reset`.
3. **Weryfikacja końcowa (Post-flight):**
   Upewnij się, że procesy doku (`pgrep -x plank`), Conky (`pgrep -x conky`) oraz klucze `button-layout` są w stanie oczekiwanym.
4. **Zapis do pamięci:**
   Zanotuj wykonanie operacji w `memory/JOURNAL.md` z podaniem daty i dowodu.
