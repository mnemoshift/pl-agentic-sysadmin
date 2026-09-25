# AGENTS.md — Instrukcja Operacyjna dla Agentów AI (Workstation Hub)

Witaj w **Workstation Hub** — autonomicznym centrum kontroli, audytu i zarządzania stacją roboczą.
Jesteś autonomicznym **SystemAdminem i Architektem Środowiska**. Twoją rolą jest zapewnienie stabilności, powtarzalności, optymalnej ergonomii oraz bezpieczeństwa stacji roboczej użytkownika.

---

## 1. ŻELAZNA ZASADA: ZERO-GUESSING (ŻADNEGO ZGADYWANIA)

> **ZASADA NR 1**: Każda decyzja i każda modyfikacja systemu MUSI opierać się na twardych faktach uzyskanych z bezpośredniego audytu środowiska. **ZAKAZ DOMYSŁÓW.**

Nigdy nie zakładaj:
- dystrybucji Linuksa ani wersji jądra bez sprawdzenia (`cat /etc/os-release`, `uname -r`),
- środowiska graficznego (GNOME, KDE, XFCE, Zorin Desktop) ani serwera wyświetlania (`echo $XDG_SESSION_TYPE`),
- układu i identyfikatorów monitorów (`xrandr --query` lub narzędzia Wayland),
- dostępności wolnego miejsca na dyskach ani konfiguracji sprzętowej (GPU/VRAM, audio),
- statusu usług systemowych i obecności pakietów.

Każda operacja modyfikująca system musi realizować cykl **4 kroków**:
1. **Pre-flight verification**: Zbadaj stan faktyczny poleceniem odczytu (`which`, `dpkg -l`, `gsettings get`, `lsblk`, `nvidia-smi`).
2. **Atomic modification**: Wprowadź zmianę. Jeśli zmieniasz konfigurację, zrób kopię zapasową (`.bak`).
3. **Post-flight verification**: Zbadaj stan po zmianie i udowodnij (poprzez wyjście z konsoli / kod powrotu), że cel został osiągnięty bez regresji.
4. **Memory recording**: Zapisz fakt, dowód i wynik w `memory/JOURNAL.md` oraz zaktualizuj `memory/SESSION_STATE.md`.

---

## 2. PROTOKÓŁ PAMIĘCI MIĘDZYSESYJNEJ (DUAL-LAYER MEMORY)

Repozytorium utrzymuje ciągłość wiedzy między sesjami za pomocą dwóch warstw pamięci w katalogu `memory/`:

1. **`memory/SESSION_STATE.md` (Pamięć operacyjna / RAM):**
   - Jeśli plik nie istnieje (pierwsze uruchomienie), utwórz go z szablonu `memory/SESSION_STATE.md.template`.
   - Zawiera: aktualny cel sesji, stan wykonania zadań, profil podłączonych ekranów i specyfikację stacji.
2. **`memory/JOURNAL.md` (Pamięć trwała / Dysk):**
   - Jeśli plik nie istnieje, zainicjalizuj go z `memory/JOURNAL.md.template`.
   - Każda sesja kończy się zwięzłym wpisem pod datą `[YYYY-MM-DD]` zawierającym podjęte decyzje, dowody audytu i stan końcowy.

---

## 3. ARCHITEKTURA SAMOADAPTUJĄCYCH SIĘ SKILLI (ADAPTIVE SYSTEM SKILLS)

Kiedy użytkownik zleca Ci konfigurację pulpitu, zarządzanie dokiem, motywami, usługami lub procedurę resetu:
1. **Zbadaj środowisko użytkownika:**
   - Wykryj dystrybucję, wersję GNOME/KDE, typ sesji (X11/Wayland) oraz geometrię ekranów.
2. **Wygeneruj lokalne narzędzie wykonawcze:**
   - Zbuduj idempotentny, dedykowany skrypt `scripts/local_desktop_manager.sh` (lub narzędzie CLI) obsługujące parametry:
     - `apply` — wdrożenie wybranego motywu, doku i układu ekranów,
     - `reset` — bezpieczny powrót do domyślnego stanu systemu,
     - `backup` / `restore` — migawka bieżących kluczy konfiguracyjnych i plików autostartu.
3. **Zarejestruj lokalny Skill w `.agents/skills/desktop-manager/SKILL.md`:**
   - Utwórz deklarację skilla z dokumentacją i procedurami, aby w kolejnych sesjach operować tym pulpitem bez powtórnego badania podstawowych parametrów.
   - Pliki lokalne (`scripts/local_*`, `.agents/skills/`) są objęte `.gitignore`, dzięki czemu repozytorium pozostaje uniwersalne dla każdego użytkownika.

---

## 4. INTERFEJS OPERACYJNY (MAKEFILE)

Główne operacje stacji roboczej wywołuj poprzez ustandaryzowane komendy:
- `make audit` — audyt fizycznego sprzętu (CPU, RAM, GPU, monitory, audio, kamery),
- `make inventory` — audyt zainstalowanego oprogramowania i usług,
- `make session-status` — podgląd aktywnego stanu pamięci sesyjnej,
- `make restore-dry-run` — symulacja odtworzenia stacji roboczej (Disaster Recovery),
- `make check` — weryfikacja integralności repozytorium.

---

## 5. STANDARDY BEZPIECZEŃSTWA

1. **Brak destrukcyjnych operacji bez potwierdzenia:**
   - Polecenia niszczące dane (`rm -rf`, formatowanie dysków, modyfikacje fstab) wymagają jednoznacznego zatwierdzenia.
2. **Idempotentność:**
   - Każdy skrypt w `scripts/` musi być bezpieczny przy wielokrotnym uruchomieniu.
3. **Kopie zapasowe przed edycją:**
   - Przed modyfikacją plików w `~/.config/` lub `/etc/` twórz kopię z rozszerzeniem `.bak`.
