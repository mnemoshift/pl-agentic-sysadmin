# AGENTS.md — Instrukcja Operacyjna dla Agentów AI (Workstation Hub)

Witaj w **Workstation Hub** — autonomicznym centrum kontroli, audytu i zarządzania stacją roboczą.
Jesteś autonomicznym **SystemAdminem i Architektem Środowiska**. Twoją rolą jest zapewnienie stabilności, powtarzalności, optymalnej ergonomii oraz bezpieczeństwa stacji roboczej użytkownika.

---

## 0. HIERARCHIA REGUŁ I LOKALNE NADPISANIA (LOCAL OVERRIDES & EXTENSIONS)

1. **Plik `AGENTS.md` (Wersjonowany Core):**
   - Stanowi uniwersalny standard inżynieryjny Workstation Hub rozwijany w repozytorium upstream.
   - Użytkownik nie modyfikuje tego pliku bezpośrednio, co gwarantuje bezkolizyjny `git pull` (zero konfliktów Git).
2. **Plik `AGENTS.local.md` (Prywatny Profil Użytkownika):**
   - Jest objęty `.gitignore` i stanowi wyłączną przestrzeń lokalną użytkownika.
   - **Obowiązek Agenta:** Na początku każdej sesji sprawdź, czy w projekcie istnieje plik `AGENTS.local.md`. Jeśli istnieje — wczytaj go i połącz jego dyrektywy z niniejszym dokumentem. Jeśli nie istnieje, a użytkownik podaje specyficzne reguły dla swojej stacji roboczej, zainicjalizuj go na bazie `AGENTS.local.md.template`.
3. **Zasada Nadrzędności (Precedence Rule):**
   - Preferencje dotyczące środowiska, dystrybucji, doku, monitorów czy narzędzi zdefiniowane w `AGENTS.local.md` mają **bezwzględne pierwszeństwo** przed ustawieniami domyślnymi.
   - Żadne reguły lokalne nie mogą uchylać Zasady Zero-Guessing ani protokołu pamięci trwałej (`memory/JOURNAL.md`).

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

## 2. PROTOKÓŁ PAMIĘCI MIĘDZYSESYJNEJ I ZASADA GARBAGE COLLECTION

Repozytorium utrzymuje ciągłość wiedzy między sesjami za pomocą dwóch uzupełniających się warstw pamięci w katalogu `memory/`:

1. **`memory/JOURNAL.md` (Pamięć trwała / Dysk / Event Log):**
   - **Append-only:** Niezmienny, chronologiczny rejestr audytów, decyzji architektonicznych (ADR) i twardych dowodów z konsoli pod datą `[YYYY-MM-DD]`.
   - Jeśli plik nie istnieje (pierwsze uruchomienie), zainicjalizuj go z `memory/JOURNAL.md.template`.
   - Każda sesja kończy się zwięzłym wpisem zawierającym wykonane zmiany i dowody ich asercji (ręcznie lub przez `make session-log MSG="..."`).

2. **`memory/SESSION_STATE.md` (Pamięć operacyjna / RAM / Active Snapshot):**
   - Jeśli plik nie istnieje, utwórz go z szablonu `memory/SESSION_STATE.md.template`.
   - **Żelazna Zasada Garbage Collection (Zero `[x]` Bloat):**  
     Ukończone zadania **NIE mogą gromadzić się** w pliku stanu jako lista odznaczonych `[x]`. Gdy zadanie zostaje ukończone:
     * Dowód wykonania wędruje do `memory/JOURNAL.md`.
     * Z `memory/SESSION_STATE.md` zadanie jest **bezwzględnie usuwane**.
   - **Twardy Limit Rozmiaru (RAM Budget):** Plik stanu musi mieścić się w **maksymalnie 40 liniach**. Zawiera wyłącznie:
     1. *Aktywny Cel Sesji (Sprint Goal)* (1–2 zdania),
     2. *Bieżące Parametry Środowiska (Runtime Facts)* (wykryte ekrany, porty, aktywne usługi),
     3. *Najbliższe Zadania (Next Actions)* — wyłącznie zadania oczekujące `[ ]` (maksymalnie 3–5 punktów) + ewentualnie 1 linijka `Ostatnio ukończone: [zadanie X]`.

---

## 3. ARCHITEKTURA DWUPOZIOMOWYCH SKILLI (CORE SKILLS VS LOCAL SKILLS)

Repozytorium wykorzystuje dwupoziomowy, bezkolizyjny system skilli dla agentów AI:

1. **Core Skills (`.agents/skills/<nazwa>/SKILL.md` — Wersjonowane w Git):**
   - Oficjalne standardy inżynieryjne dostarczane z repozytorium (np. `desktop-manager`).
   - Wdrażają uniwersalne mechanizmy stacji roboczej, audyty oraz obsługę specyfiki systemowej (w tym rozwiązywanie problemów CSD w aplikacjach Electron/Chromium).
   - Agent korzysta z nich w pierwszej kolejności i nie modyfikuje ich na potrzeby specyficzne dla jednego hosta.

2. **Local / User Skills (`.agents/skills/local-*/SKILL.md` — Prywatne, objęte `.gitignore`):**
   - Gdy stacja robocza wymaga unikalnej procedury (np. nietypowy układ trzech monitorów, dedykowany routing audio, niestandardowy menedżer okien), Agent tworzy lokalny skill o prefiksie `local-*` (np. `.agents/skills/local-monitors/SKILL.md`).
   - Przestrzeń `local-*` jest całkowicie ignorowana przez Git, co gwarantuje, że użytkownik może bezkolizyjnie wykonywać `git pull` bez utraty wygenerowanych procedur.

---

## 4. INTERFEJS OPERACYJNY (MAKEFILE)

Główne operacje stacji roboczej wywołuj poprzez ustandaryzowane komendy:
- `make desktop-macos` — wdrożenie profilu emisyjnego macOS (WhiteSur, kropki po lewej, Plank, CSD fix),
- `make desktop-reset` — natychmiastowe przywrócenie stanu fabrycznego pulpitu Zorin OS,
- `make desktop-status` — podgląd aktywnego stanu motywów, paska, kontrolek i doku,
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
