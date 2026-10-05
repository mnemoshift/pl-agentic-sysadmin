---
name: desktop-manager
description: Zarządzanie profilami pulpitu stacji roboczej (dwutorowy silnik X11 / Wayland, profil Cyber Studio z HUD i telemetrią emisyjną, styl macOS WhiteSur z dokiem TopChrome i animacją zoom/hop, reset do vanilla Zorin, unifikacja kontrolek okien CSD w VS Code/Chrome). Używaj, gdy użytkownik prosi o zmianę wyglądu pulpitu, konfigurację studia nagrań, dostosowanie doku pod Waylandem lub X11, telemetrię GPU/CPU, reset ustawień lub synchronizację belek okien.
---

# Desktop Manager Skill (Workstation Hub Core Skill)

Ten skill dostarcza zautomatyzowane, weryfikowalne procedury zarządzania środowiskiem graficznym stacji roboczej w oparciu o **dwutorową architekturę serwera wyświetlania (X11 vs Wayland)**, profile produkcyjne (Cyber Studio & macOS WhiteSur), rozwiązywanie problemów z Client-Side Decorations (CSD) oraz deterministyczny reset do stanu fabrycznego Zorin OS.

---

## 1. Architektura Dwutorowa: Kategorie Sprzętowe i Środowiskowe

Workstation Hub automatycznie audytuje środowisko przed modyfikacją pulpitu (`detect_display_server`) i kieruje wykonanie do odpowiedniego silnika:

| Kategoria Środowiska | Serwer Wyświetlania | Architektura Doku | Telemetria / Widgety | Przeznaczenie |
| :--- | :--- | :--- | :--- | :--- |
| **Kategoria 1: Workstation X11** | **X11 / Xorg** (`XDG_SESSION_TYPE=x11`) | **Plank Dual-Dock** (`plank`) — motyw `MnemoShift-HUD` lub `Transparent`, autostart X11 | **Conky HUD** (przydymione szkło) + **MnemoShift Emission HUD** | Ciężkie stacje montażowe z dedykowanym GPU NVIDIA (RTX), wieloma monitorami (21:9 + 16:9) |
| **Kategoria 2: Laptop / PC Wayland** | **Wayland** (`XDG_SESSION_TYPE=wayland`) | **Ubuntu Dock (Dash-to-Dock)** w warstwie **TopChrome** z animacją **Zoom & Hop** | Pasek systemowy Zorin Taskbar TOP (28px) z wyśrodkowanym zegarem | Laptopy i komputery z grafiką Intel/AMD (iGPU) lub hybrydową, nowoczesne instalacje Zorin OS 18 / Ubuntu 24.04 |

---

## 2. Inżynieria Doku pod Waylandem (Kategoria 2)

Protokół Wayland w kompozytorze GNOME Shell (Mutter) uniemożliwia zewnętrznym aplikacjom X11 (jak Plank) bezpośrednie zarządzanie oknami, pozycją ekranową oraz barierami wskaźnika myszy. Dlatego dla sesji Wayland wdrożono wyspecjalizowany, natywny silnik doku:

1. **Warstwa `TopChrome` zamiast `addChrome`:**
   - Domyślny Ubuntu Dock rejestruje się przez `Main.layoutManager.addChrome(this)`, co umieszcza go w drzewie sceny Cluttera **poniżej grupy okien** (`global.top_window_group`). Gdy okno nachodzi na dół ekranu, zasłania dok i przechwytuje zdarzenia myszy.
   - Nasza procedura rejestruje dok przez `Main.layoutManager.addTopChrome(this, { trackFullscreen: true })`, co wynosi dok na **sam wierzch ponad wszystkie nachodzące okna**.
2. **Aktywny Wyzwalacz Dolnej Krawędzi (Edge Trigger):**
   - Rezerwacja 2-pikselowego paska czułości (`_slideoutSize = 2`) w warstwie TopChrome na dnie ekranu.
   - Usunięcie blokującego warunku `user_time` z `_dockDwellTimeout`, dzięki czemu zjechanie kursorem do dolnej krawędzi bezwzględnie i natychmiastowo wysuwa dok na wierzch nad aktywne okno.
3. **Efekt Zoom & Hop pod Kursorem (Styl Plank / macOS):**
   - Na zdarzeniu `notify::hover` w `appIcons.js` ikona pod kursorem powiększa się o 20% (`scale 1.2`) i unosi w górę o 6px (`translation_y: -6`) z płynnym wygładzaniem kwadratowym (`Clutter.AnimationMode.EASE_OUT_QUAD`, 120ms).
   - Po zjechaniu myszą ikona miękko powraca do bazowego rozmiaru (`scale 1.0, translation_y 0`).
   - Wskaźniki uruchomionych aplikacji (kropki DOTS) pozostają stabilnie na dole paska.
4. **Spójność Wektorowa i Pasek WhiteSur:**
   - Podmiana symbolicznej ikony siatki programów (`view-app-grid-zorin-symbolic.svg`) w motywie WhiteSur, zapobiegająca wyświetlaniu dużego znaku `+`.
   - Przycisk programów umieszczony po lewej stronie doku (`show-apps-at-top true`).
   - Przypięte ulubione w doku: Antigravity IDE, Brave, Nautilus, Terminal.

> [!IMPORTANT]
> **Wymóg przeładowania ES Modules w Waylandzie:**  
> Silnik GJS w GNOME Shell 46 keszuje załadowane moduły JavaScript w pamięci procesu kompozytora. Każda aktualizacja kodu rozszerzeń doku wymaga jednorazowego przelogowania użytkownika (wyloguj/zaloguj), aby kompozytor wczytał nowy kod z dysku.

---

## 3. Dostępne Profile i Polecenia Operacyjne

Zintegrowany interfejs `Makefile` oraz skrypt `scripts/desktop_ctl.sh` automatycznie adaptują się do wykrytego serwera wyświetlania:

```bash
# Wdrożenie profilu emisyjnego macOS (WhiteSur, kropki po lewej, taskbar góra 28px, dolny dok Wayland/Plank, CSD fix)
make desktop-macos
# lub bezpośrednio:
./scripts/desktop_ctl.sh apply-macos

# Wdrożenie profilu Cyber Studio (MnemoShift Cyber-Blueprint, Top Bar Emission HUD, Conky HUD, Plank HUD)
make desktop-studio
# lub bezpośrednio:
./scripts/desktop_ctl.sh apply-studio

# Błyskawiczny powrót do domyślnego stanu Zorin OS (wyłączenie doków, Conky i rozszerzeń)
make desktop-reset
# lub bezpośrednio:
./scripts/desktop_ctl.sh reset

# Audyt bieżącego stanu dekoracji, motywów, serwera wyświetlania i procesów doku
make desktop-status
# lub bezpośrednio:
./scripts/desktop_ctl.sh status
```

---

## 4. Architektura Ramek Okien: SSD vs CSD

Środowisko graficzne dzieli aplikacje na dwie kategorie:

1. **Server-Side Decorations (SSD) — Natywne okna systemowe (Mutter):**
   * Dotyczy: Nautilus, Terminal, Ustawienia, aplikacje GTK4/libadwaita.
   * Kontrolowane przez: `gsettings set org.gnome.desktop.wm.preferences button-layout 'close,minimize,maximize:'`.
   * Reagują natychmiast po zmianie klucza GSettings.

2. **Client-Side Decorations (CSD) — Aplikacje Electron i Chromium:**
   * Dotyczy: **Visual Studio Code**, **Google Chrome**, **Brave**.
   * Domyślnie ignorują ustawienia menedżera okien Mutter i same rysują nagłówek z przyciskami po prawej stronie.
   * **Rozwiązanie w ramach skilla:**
     * **VS Code:** Wymuszenie `"window.titleBarStyle": "native"` w `~/.config/Code/User/settings.json`.
     * **Google Chrome:** Ustawienie `"custom_chrome_frame": false` w `~/.config/google-chrome/*/Preferences`.
     * Zapewnia to pełną spójność traffic lights po lewej stronie w całym systemie.

> [!NOTE]
> **Antigravity IDE:** Posiada deklarację trybu bezramkowego (`titleBarStyle: 'hidden'`) z wykorzystaniem Chromium Window Controls Overlay. Zgodnie z wytycznymi architektonicznymi pozostawiamy Antigravity w nowoczesnym układzie frameless bez modyfikowania plików `.asar`.

---

## 5. Protokół Wykonawczy dla Agenta

Gdy użytkownik zleca Ci konfigurację pulpitu lub jego reset:
1. **Audyt wstępny (Pre-flight):**
   Wywołaj `make desktop-status` i zbadaj:
   * Wykryty serwer wyświetlania (`Wayland` vs `X11`),
   * Aktywne rozszerzenia, motywy i procesy doku.
2. **Wykonanie atomowe:**
   Wywołaj odpowiedni cel (`make desktop-macos`, `make desktop-studio` lub `make desktop-reset`).
3. **Weryfikacja końcowa (Post-flight):**
   Sprawdź kod powrotu i upewnij się poleceniem `make desktop-status`, że stan jest spójny z wykrytą sesją.
4. **Zapis do pamięci:**
   Zanotuj wykonanie operacji w `memory/JOURNAL.md` z podaniem dowodu i zaktualizuj `memory/SESSION_STATE.md`.
