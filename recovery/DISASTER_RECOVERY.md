# Procedura Odtworzenia Stacji Roboczej (Disaster Recovery Playbook)

Niniejszy dokument opisuje procedurę odtworzenia stacji roboczej od zera po czystej instalacji systemu lub awarii dysku.
Wszystkie kroki bazują na twardych danych zebranych w audytach w katalogu `inventory/`.

---

## ⚡ Tryb Szybki: Automatyczne Odtworzenie (Dry-Run & Real)

W repozytorium znajduje się dedykowany skrypt `scripts/restore_workstation.sh`, który krok po kroku weryfikuje i instaluje brakujące oprogramowanie.

```bash
# 1. Sprawdzenie co zostanie zainstalowane (bezpieczna symulacja)
make restore-dry-run

# 2. Wykonanie faktycznego odtworzenia oprogramowania
./scripts/restore_workstation.sh
```

---

## 📋 Procedura Krok po Kroku (Manual / Audited)

### KROK 1: Klonowanie Repozytorium na Czystym Systemie
```bash
mkdir -p ~/workspaces/mnemoshift
cd ~/workspaces/mnemoshift
git clone https://github.com/mnemoshift/agentic-sysadmin.git
cd agentic-sysadmin
```

### KROK 2: Weryfikacja Sprzętu
Uruchom audyt sprzętowy, aby upewnić się, że sterowniki GPU i urządzenia peryferyjne są widoczne:
```bash
make audit
```

### KROK 3: Odtworzenie Środowiska i Pakietów
Uruchom procedurę instalacji brakujących narzędzi:
```bash
./scripts/restore_workstation.sh
```

### KROK 4: Personalizacja Pulpitu (Tryb Agentic)
Otwórz projekt w Antigravity IDE:
```bash
antigravity .
```
Wklej prompt personalizacyjny (np. dla profilu emisyjnego):
> *"Jesteś moim Agentic SysAdminem. Skonfiguruj pulpit Zorin OS pod mój profil emisyjny: dok Plank na dole ekranu 16:9, ciemny motyw WhiteSur, bez zbędnych rozpraszaczy i zoptymalizuj stację pod nagrania."*

Agent sam zbada ekrany, wygeneruje lokalne skrypty i wdroży konfigurację w 60 sekund!
