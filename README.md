# `pl-agentic-sysadmin` — Autonomiczny Workstation Hub & Protokół AI SysAdmin (PL)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Channel: MnemoShift](https://img.shields.io/badge/YouTube-MnemoShift-red.svg)](https://youtube.com)

> *Autonomiczne centrum kontroli, audytu i odtwarzania stacji roboczej Linux, współpracujące w modelu ciągłej pamięci z agentami AI (Antigravity IDE, Claude Code) — edycja polskojęzyczna.*

Tradycyjne podejście do konfiguracji systemu (ręczne wklepywanie komend, niespójne dotfiles, amnezja chatbotów w przeglądarce) zawodzi w erze inżynierii agentowej. **`pl-agentic-sysadmin`** zamienia Twoje repozytorium w żyjący hub stacji roboczej, który daje agentowi AI oczy (audyt sprzętu), ręce (deterministyczne skrypty i Makefile) oraz trwałą pamięć.

---

## 🚀 Szybki Start: Uruchomienie w Antigravity 2.0

### Krok 1: Pobranie repozytorium (Terminal)
Wklej w terminalu polecenie klonowania:
```bash
git clone https://github.com/mnemoshift/pl-agentic-sysadmin.git ~/workspaces/pl-agentic-sysadmin
```

### Krok 2: Otwarcie i konfiguracja projektu w Antigravity 2.0
1. Uruchom **Antigravity 2.0** (z menu aplikacji Zorina lub poleceniem `antigravity`).
2. W lewym panelu bocznym przejdź do sekcji **Projects** $\rightarrow$ kliknij **Add Project** (lub **Open Folder**) i wskaż sklonowany katalog:  
   `~/workspaces/pl-agentic-sysadmin`
3. **Konfiguracja bezpieczeństwa (Potwierdzanie komend):**
   * W prawym górnym rogu okna czatu / ustawieniach projektu:
   * Ustaw **Tool Execution Policy** na `Request Review` (lub wyłącz *Auto-approve commands*).
   * Dzięki temu Agent przed każdą modyfikacją systemu zaprezentuje plan operacyjny (*Implementation Plan*) i poprosi Cię o autoryzację komend shellowych.
4. Gotowe — Agent natychmiast załaduje reguły `AGENTS.md` oraz Core Skill `desktop-manager`.

---

## ⚡ Dostępne Polecenia Operacyjne (Makefile)

Jeśli wolisz wywoływać procedury bezpośrednio z konsoli:
```bash
# Wyświetlenie wszystkich dostępnych komend
make help

# 🖥️ Zarządzanie profilem pulpitu (Nowość z EP002)
make desktop-macos   # Wdrożenie profilu emisyjnego macOS (WhiteSur, kropki po lewej, Plank, CSD fix)
make desktop-reset   # Natychmiastowy powrót do stanu fabrycznego Zorin OS (1 sekunda)
make desktop-status  # Audyt dekoracji okien, pozycji paska Zorina i doku

# 🔍 Audyt sprzętu i oprogramowania
make audit           # Audyt CPU, RAM, GPU, Audio, Kamery, Ekrany
make inventory       # Living Inventory pakietów APT, Flatpak i repozytoriów
make restore-dry-run # Bezpieczna symulacja Disaster Recovery
```

---

## 🏛️ Architektura: 4 Filary Systemu

```mermaid
graph TD
    User([Inżynier / Twórca]) <--> Agent[Agent AI w Antigravity IDE]
    
    subgraph Protokół i Pamięć
        AGENTS[AGENTS.md - Zasada Zero-Guessing]
        STATE[memory/SESSION_STATE.md - Aktywny RAM]
        JRNL[memory/JOURNAL.md - Pamięć trwała ISO]
    end

    subgraph Diagnostyka i Fakty
        Audit[scripts/audit_hardware.sh - make audit]
        Inv[inventory/ - Living Inventory]
        Make[Makefile - Interfejs operacyjny]
    end

    subgraph Adaptacja i Skille
        Skills[.agents/skills/ - Lokalne skille agenta]
        LocalScripts[scripts/local_* - Idempotentne skrypty stacji]
    end

    Agent --> AGENTS
    Agent <--> STATE
    Agent --> JRNL
    Agent --> Audit
    Agent --> Inv
    Agent --> Make
    Agent --> Skills
    Agent --> LocalScripts
```

### 1. Zasada Zero-Guessing & Bezkolizyjne Aktualizacje (`AGENTS.md` + `AGENTS.local.md`)
Agent AI **nie ma prawa zgadywać** stanu Twojej maszyny. Każda zmiana jest poprzedzona audytem stanu faktycznego (*Pre-flight check*), wykonana atomowo z kopią zapasową i zweryfikowana po zakończeniu (*Post-flight verification*).

Co kluczowe dla użytkowników GitHuba: repozytorium rozdziela standard frameworka (`AGENTS.md`) od Twoich prywatnych reguł (`AGENTS.local.md` w `.gitignore`). Możesz w dowolnym momencie wykonać `git pull` po nowe funkcje od twórcy, a Twoje lokalne preferencje (KDE, inny dok, własne monitory) pozostaną w 100% nienaruszone (zero konfliktów Git).

### 2. Dwuwarstwowa Pamięć Międzysesyjna (Dual-Layer Memory)
- **`memory/SESSION_STATE.md` (Pamięć operacyjna / RAM):** Stan bieżący, aktywny cel sprintu, lista ukończonych zadań i parametry wykrytych monitorów.
- **`memory/JOURNAL.md` (Pamięć trwała / Dysk):** Niezmienny, chronologiczny rejestr zdarzeń pod datą `[YYYY-MM-DD]` zawierający twarde dowody z konsoli.

### 3. Dwupoziomowe Skille (Core Skills vs Local Skills)
- **Core Skills (`.agents/skills/`):** Gotowe, uniwersalne procedury dostarczane w Git przez twórcę (np. `desktop-manager` z obsługą specyfiki CSD w aplikacjach Electron/Chromium).
- **Local Skills (`.agents/skills/local-*/`):** Gdy Agent na Twojej maszynie generuje specyficzną procedurę (np. niestandardowy układ trzech monitorów czy routing audio), zapisuje ją w przestrzeni `local-*` objętej `.gitignore`. Daje to 100% powtarzalności bez konfliktów przy kolejnych `git pull`.

### 4. Living Inventory & Disaster Recovery
Każda zainstalowana aplikacja, biblioteka czy usługa jest katalogowana w `inventory/`. W razie awarii dysku procedura `make restore-dry-run` oraz `scripts/restore_workstation.sh` przywracają całe środowisko programistyczne w 3 minuty.

---

## 📺 Materiał Wideo (YouTube)

Odcinek instruktażowy prezentujący działanie tego repozytorium krok po kroku oraz kontrast między pracą w terminalu a trybem Agentic:
- 🎬 **MnemoShift EP002:** *Pulpit Zorin OS: Terminal Oldschool vs Agentic SysAdmin (Od zera w Antigravity)* — [Obejrzyj na YouTube](https://youtube.com)

---

## 📄 Licencja

Projekt udostępniany na licencji MIT. Zobacz plik [LICENSE](LICENSE) po szczegóły.
