# Walkthrough: Instalacja i Konfiguracja Kdenlive z Serwerem MCP w User-Space

> **Kontekst:** Kompletny przewodnik architektoniczny jak krok po kroku skonfigurować Kdenlive i serwer `kdenlive-mcp` na Linuksie (Zorin OS / Ubuntu) pod kontrolę autonomicznego agenta AI w Antigravity. Zero uprawnień roota (User-Space by Default), zero płatnych subskrypcji chmurowych.

---

## 1. Dlaczego Kdenlive MCP zamiast DaVinci Resolve Free na Linuksie?

Przed wdrożeniem automatyzacji wideo stanęliśmy przed dylematem wyboru platformy montażowej:
1. **Darmowy DaVinci Resolve na Linuksie:**
   - Brak obsługi formatów konsumenckich H.264/H.265 (MP4) i dźwięku AAC w wersji bezpłatnej (wymóg licencji Studio 300$ lub gigantycznego transkodowania każdego nagrania OBS do formatu DNxHR: 10 minut = ~60 GB).
   - Brak wbudowanego Speech-to-Text w darmowej wersji.
   - Zamknięta, binarna baza projektów, trudna do manipulacji przez LLM.
2. **Kdenlive (Silnik MLT):**
   - Natywne czytanie H.264/H.265/AAC prosto z OBS-a.
   - Sprzętowa akceleracja kodowania i renderowania NVENC na kartach NVIDIA RTX.
   - **Plik projektu to czysty XML:** Każde cięcie, filtr, ścieżka i kompozycja to czytelny znacznik tekstowy, który silnik `melt` potrafi wyrenderować z konsoli bez uruchamiania GUI.
   - Idealny cel pod integrację przez protokół **Model Context Protocol (MCP)**.

---

## 2. Architektura Środowiska (User-Space by Default)

Całość opiera się na zasadzie izolacji w przestrzeni użytkownika — żadna z operacji nie wymaga komendy `sudo`:

```text
┌───────────────────────────────────────────────────────────┐
│                    Antigravity IDE                        │
│             (~/.gemini/config/mcp_config.json)            │
└─────────────────────────────┬─────────────────────────────┘
                              │ JSON-RPC (MCP Protocol)
                              ▼
┌───────────────────────────────────────────────────────────┐
│              kdenlive-mcp (Python FastMCP)                │
│             (~/.local/share/kdenlive-mcp/.venv)           │
└──────────────┬─────────────────────────────┬──────────────┘
               │ XML Generation              │ CLI Exec
               ▼                             ▼
┌──────────────────────────────┐ ┌──────────────────────────┐
│  Szablony MLT XML (.kdenlive)│ │ ~/.local/bin/melt        │
│  Dynamiczne napisy ASS       │ │ ~/.local/bin/kdenlive    │
└──────────────────────────────┘ └───────────┬──────────────┘
                                             │ flatpak run
                                             ▼
                               ┌────────────────────────────┐
                               │ org.kde.kdenlive (Flatpak) │
                               │ Akceleracja NVENC (RTX)    │
                               └────────────────────────────┘
```

---

## 3. Instalacja Krok po Kroku (Manualna lub Automatyczna)

W naszym repozytorium cały proces jest zautomatyzowany jednym poleceniem:
```bash
make media-setup-mcp
```
Poniżej opis techniczny poszczególnych etapów, które skrypt wykonuje pod spodem.

### Etap 1: Instalacja Kdenlive via Flatpak User
Instalujemy oficjalny pakiet z Flathuba w przestrzeni użytkownika (`--user`):
```bash
flatpak install --user flathub org.kde.kdenlive -y
```

### Etap 2: Wrappery CLI dla Kdenlive i Melt
Silnik renderujący MLT (`melt`) oraz binarka Kdenlive znajdują się wewnątrz piaskownicy Flatpaka. Aby serwer MCP i terminal mogły je wywoływać natywnie, tworzymy dwa wrappery w `~/.local/bin/`:

1. `~/.local/bin/kdenlive`:
```bash
#!/bin/bash
exec flatpak run org.kde.kdenlive "$@"
```
2. `~/.local/bin/melt`:
```bash
#!/bin/bash
exec flatpak run --command=melt org.kde.kdenlive "$@"
```
Nadajemy uprawnienia wykonywalności:
```bash
chmod +x ~/.local/bin/kdenlive ~/.local/bin/melt
```

### Etap 3: Klonowanie i Środowisko Serwera MCP
Klonujemy otwartoźródłowy serwer MCP i tworzymy odizolowane środowisko za pomocą szybkiego menedżera `uv`:
```bash
git clone https://github.com/12bijaya/MCP_Server_Kdenlive.git ~/.local/share/kdenlive-mcp
cd ~/.local/share/kdenlive-mcp
uv venv
uv pip install -e ".[test]" "mcp<2"
```

---

## 4. Trzy Kluczowe Poprawki Architektoniczne w Generatorze XML

Podczas pierwszych testów integracji natrafiliśmy na subtelne błędy w upstreamowym repozytorium MCP, które powodowały ostrzeżenia w Kdenlive GUI lub błędy walidacji silnika `melt`. Naprawiliśmy je na poziomie kodu serwera:

### 1. Błąd w `.gitignore` ukrywający moduł `snapshots`
Upstream w pliku `.gitignore` posiadał wpis `snapshots/`. W składni Gita dopasowywało to nie tylko folder zrzutów w katalogu głównym, ale również kod źródłowy `src/kdenlive_mcp/storage/snapshots/manager.py`. W efekcie po sklonowaniu brakowało kluczowego modułu Pythona.
* **Naprawa:** Zmiana wpisu na `/snapshots/` oraz odtworzenie pliku `manager.py`.

### 2. Kolizja Sequence UUID z Project UUID (Błąd *„Unreferenced clip (Fixed)”*)
W Kdenlive traktor sekcji (`<tractor id="{uuid}">`) musi posiadać UUID bazujący na `sequence.id`, unikalny względem identyfikatora dokumentu `project.id` (`docproperties.uuid`). Ich kolizja powodowała komunikat naprawczy w GUI.
* **Naprawa w `xml_writer.py`:**
```python
# Zamiast: master = _sub(mlt, "tractor", id="{%s}" % _pad_uuid(project.id))
master = _sub(mlt, "tractor", id="{%s}" % _pad_uuid(sequence.id), ...)
```

### 3. Kaskada Kompozycji Wideo `qtblend` (Błąd *„forced track”*)
Domyślnie generator łączył wszystkie wyższe ścieżki wideo z torem zerowym (`a_track="0"`). W silniku MLT Kdenlive dolna ścieżka (`V1`) kompozytuje się z tłem `0`, ale każda kolejna (`V2`, `V3`) musi kompozytować się z torem bezpośrednio pod nią (`pos - 1`).
* **Naprawa w `xml_writer.py`:**
```python
# Kaskada: ścieżka dolna do tła 0, wyższe do ścieżki poniżej:
a_track = 0 if idx == 0 else pos - 1
_prop(t, "a_track", str(a_track))
```

### 4. Ignorowanie ostrzeżeń GTK w stderr silnika `melt`
W dystrybucjach opartych o Ubuntu/Zorin środowisko potrafi wyrzucić na stderr nieszkodliwe ostrzeżenie `Failed to load module "xapp-gtk3-module"`. Validator traktował każde wystąpienie słowa "Failed" jako błąd krytyczny.
* **Naprawa w `project_validator.py`:** Oczyszczenie stderr z ostrzeżeń o modułach GTK przed ewaluacją błędu.

Wszystkie powyższe poprawki znajdują się w pliku `templates/kdenlive/kdenlive_mcp_patches.diff` i są aplikowane automatycznie przez nasz instalator.

---

## 5. Konfiguracja w Antigravity

Aby Antigravity widział serwer MCP, dodajemy konfigurację w pliku `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "kdenlive": {
      "command": "/home/jarek/.local/share/kdenlive-mcp/.venv/bin/kdenlive-mcp",
      "args": [],
      "env": {
        "KDENLIVE_MCP_KDENLIVE": "/home/jarek/.local/bin/kdenlive",
        "KDENLIVE_MCP_MELT": "/home/jarek/.local/bin/melt"
      }
    }
  }
}
```

---

## 6. Weryfikacja Działania

Stan środowiska można sprawdzić w dowolnym momencie z poziomu terminala:
```bash
make media-check-mcp
```
Wynik audytu:
```text
==========================================================
  KDENLIVE & MCP SERVER — WORKSTATION SETUP & AUDIT
==========================================================
[*] Sprawdzanie stanu instalacji Kdenlive i serwera MCP...

  [✓] Flatpak Kdenlive zainstalowany: 26.08.1
  [✓] Wrapper CLI kdenlive: /home/jarek/.local/bin/kdenlive
  [✓] Wrapper CLI melt: /home/jarek/.local/bin/melt (melt 7.41.0)
  [✓] Katalog serwera MCP obecny: /home/jarek/.local/share/kdenlive-mcp
  [✓] Środowisko Python venv serwera MCP aktywne
  [✓] Poprawka kaskady kompozycji (qtblend) zainstalowana
  [✓] Poprawka unikalności Sequence UUID zainstalowana
  [✓] Konfiguracja MCP w Antigravity obecna: /home/jarek/.gemini/config/mcp_config.json

Status: [GOTOWY] Środowisko Kdenlive MCP jest w 100% zoptymalizowane i gotowe do montażu.
==========================================================
```

Albo bezpośrednio z poziomu czatu z Agentem:
> `Sprawdź gotowość Kdenlive i narzędzi multimedialnych.`
