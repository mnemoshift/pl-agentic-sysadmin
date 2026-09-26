---
name: desktop-manager
description: Zarządzanie profilem pulpitu stacji roboczej (styl macOS WhiteSur, reset do vanilla Zorin, unifikacja kontrolek okien CSD w VS Code/Chrome oraz dok Plank). Używaj, gdy użytkownik prosi o zmianę wyglądu pulpitu, reset ustawień, konfigurację traffic lights po lewej stronie lub synchronizację belek okien.
---

# Desktop Manager Skill (Workstation Hub Core Skill)

Ten skill dostarcza zautomatyzowane, weryfikowalne procedury zarządzania środowiskiem graficznym stacji roboczej (ze szczególnym uwzględnieniem Zorin OS / GNOME / X11), rozwiązywania problemów z Client-Side Decorations (CSD) oraz deterministycznego resetu do stanu domyślnego.

---

## 1. Dostępne Polecenia Operacyjne

Skill wykorzystuje zintegrowany kontroler pulpitu `scripts/desktop_ctl.sh` dostępny przez `Makefile`:

```bash
# Wdrożenie profilu emisyjnego macOS (WhiteSur, kropki po lewej, taskbar góra, Plank dół, CSD fix)
make desktop-macos
# lub bezpośrednio:
./scripts/desktop_ctl.sh apply-macos

# Błyskawiczny powrót do domyślnego stanu Zorin OS (kropki po prawej, pasek dół, wyłączenie Planka)
make desktop-reset
# lub bezpośrednio:
./scripts/desktop_ctl.sh reset

# Audyt bieżącego stanu dekoracji, motywów i procesów doku
make desktop-status
# lub bezpośrednio:
./scripts/desktop_ctl.sh status
```

---

## 2. Architektura Ramek Okien: SSD vs CSD

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

## 3. Protokół Wykonawczy dla Agenta

Gdy użytkownik zleca Ci konfigurację pulpitu lub jego reset:
1. **Audyt wstępny (Pre-flight):**
   Wywołaj `make desktop-status` i sprawdź aktualne motywy oraz układ przycisków.
2. **Wykonanie atomowe:**
   Wywołaj odpowiedni cel `make desktop-macos` lub `make desktop-reset`.
3. **Weryfikacja końcowa (Post-flight):**
   Upewnij się, że procesy doku (`pgrep -x plank`) oraz klucze `button-layout` są w stanie oczekiwanym.
4. **Zapis do pamięci:**
   Zanotuj wykonanie operacji w `memory/JOURNAL.md` z podaniem daty i dowodu.
