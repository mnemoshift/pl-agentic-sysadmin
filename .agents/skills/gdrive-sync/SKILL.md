---
name: gdrive-sync
description: Zarządzanie selektywną, dwukierunkową synchronizacją Dysku Google (rclone bisync/vfs) na dysk lokalny NVMe stacji roboczej. Eliminuje problemy z FUSE (GVFS), zawieszaniem procedury suspend (stan D), ułomnymi ścieżkami w KeePassXC oraz blokadami uploadu w przeglądarkach. Używaj, gdy użytkownik chce skonfigurować Dysk Google, dodać/usunąć synchronizowany katalog, zsynchronizować pliki lub rozwiązać problemy z usypianiem systemu i dostępem do plików chmurowych.
---

# Google Drive Selective Sync Skill (Workstation Hub Core Skill)

Ten skill dostarcza zautomatyzowane, weryfikowalne procedury selektywnej dwukierunkowej synchronizacji Dysku Google z lokalnym dyskiem NVMe stacji roboczej przy użyciu oficjalnego silnika **`rclone`** (w przestrzeni użytkownika, bez konieczności uprawnień roota).

---

## 1. Dlaczego GVFS w Linuksie zawodzi (Windows vs Linux)

| Aspekt | Google Drive for Desktop (Windows) | GNOME Online Accounts / GVFS (Linux default) | Workstation Hub: Rclone Selective Sync (Nasz standard) |
| :--- | :--- | :--- | :--- |
| **Mechanizm** | Sterownik wirtualnego dysku z natywnym lokalnym buforem blokowym na dysku `C:`. | Minimalna warstwa FUSE (`gvfsd-google`) wykonująca zapytania HTTP REST API przy każdym odczycie. | **Prawdziwe pliki na lokalnym dysku NVMe** (`~/GoogleDrive/`) synchronizowane w tle silnikiem `rclone bisync`. |
| **Ścieżki do plików** | Standardowe: `G:\Mój dysk\KeePass\baza.kdbx`. | Patologiczne URI z identyfikatorami węzłów Google: `/run/user/1000/gvfs/google-drive:host=.../0ALCzWgX8.../10Pf2...`. | **Czyste ścieżki POSIX:** `/home/jarek/GoogleDrive/KeePass/baza.kdbx`. |
| **KeePassXC / Flatpaki** | Działa natywnie. | Zawiesza się, gubi ścieżki po restarcie, odpytuje powolne API. | **100% natywny dostęp:** Zerowe opóźnienia (>3000 MB/s z NVMe), brak zależności od sieci. |
| **Załączanie w przeglądarkach** | Standardowe okno eksploratora Windows. | Okno wyboru plików GTK/Chromium zawiesza się lub nie pozwala załączyć pliku z GVFS. | **Błyskawiczne:** Plik wybierany jest jak każdy normalny plik z katalogu domowego. |
| **Uśpienie PC (Suspend)** | Klient integruje się z APM/ACPI Windowsa. | **Krytyczny błąd:** FUSE zawiesza proces w stanie `D` (`TASK_UNINTERRUPTIBLE`), kernel freezer po 20s przerywa uśpienie (`EBUSY`). | **Zero tarcia:** Brak wiszących zapytań FUSE. Uśpienie komputera następuje natychmiast (1-2s). |
| **Praca Offline** | Bufor lokalny dla zaznaczonych plików. | Brak dostępu do plików bez aktywnego internetu. | **Pełna praca offline:** Wszystkie wybrane foldery są fizycznie na dysku lokalnym. |

---

## 2. Dostępne Polecenia Operacyjne (Makefile & CLI)

Wszystkie operacje dostępne są przez ujednolicony interfejs `Makefile` stacji roboczej:

```bash
# 1. Sprawdzenie stanu rclone, konfiguracji, zsynchronizowanych folderów i timera
make gdrive-status

# 2. Instalacja rclone w przestrzeni użytkownika (~/.local/bin) bez sudo
make gdrive-install

# 3. Interaktywna autoryzacja konta Google w przeglądarce (rclone config)
make gdrive-auth

# 4. Przeglądanie katalogów dostępnych na Dysku Google
make gdrive-list
make gdrive-list PATH="Projekty"

# 5. Lista obecnie zdefiniowanych folderów synchronizacji
make gdrive-folders

# 6. Dodanie katalogu do selektywnej synchronizacji
make gdrive-add REMOTE="KeePass" [LOCAL="KeePass"] [MODE="bisync"] [DESC="Baza haseł"]

# 7. Usunięcie katalogu z konfiguracji synchronizacji (pliki lokalne pozostają)
make gdrive-remove REMOTE="KeePass"

# 8. Ręczne wywołanie synchronizacji
make gdrive-sync                                    # Wszystkie aktywne foldery
make gdrive-sync FOLDER="KeePass"                   # Tylko folder KeePass
make gdrive-sync DRY_RUN=1                          # Przebieg próbny (symulacja)
make gdrive-sync FOLDER="KeePass" RESYNC=1          # Wymuszenie re-indeksacji bazy dwukierunkowej

# 9. Automatyzacja w tle (systemd --user timer)
make gdrive-timer-enable [INTERVAL="15m"]           # Uruchamia synchronizację co 15 minut
make gdrive-timer-disable                           # Zatrzymuje automatyczną synchronizację

# 10. Opcjonalne montowanie VFS całego dysku na żądanie (z lokalnym buforem blokowym)
make gdrive-mount                                   # Montuje w ~/GoogleDrive/Cloud-All
make gdrive-unmount                                 # Odmontowuje zasób
```

---

## 3. Plik Konfiguracji i Model Danych

Konfiguracja synchronizacji przechowywana jest w standardzie XDG:
`~/.config/mnemoshift/gdrive-sync.json`

```json
{
  "remote_name": "gdrive",
  "local_base_dir": "~/GoogleDrive",
  "sync_folders": [
    {
      "remote_path": "KeePass",
      "local_path": "KeePass",
      "mode": "bisync",
      "enabled": true,
      "description": "Bazy haseł KeePassXC (lokalna kopia NVMe, natywny dostęp offline)"
    },
    {
      "remote_path": "Dokumenty/Wazne",
      "local_path": "Dokumenty",
      "mode": "bisync",
      "enabled": true,
      "description": "Bieżące dokumenty i umowy"
    }
  ],
  "timer_interval": "15m"
}
```

### Tryby synchronizacji (`mode`):
- **`bisync` (Domyślny, Zalecany):** Prawdziwa synchronizacja dwukierunkowa. Zmiany lokalne wędrują do chmury; zmiany w chmurze (np. edycja na telefonie) są pobierane na dysk. Konflikty rozwiązywane są na korzyść nowszego pliku (`--conflict-resolve newer`).
- **`pull`:** Lustro jednostronne Remote -> Local (dla katalogów tylko do odczytu lokalnego).
- **`push`:** Lustro jednostronne Local -> Remote (dla automatycznych kopii zapasowych).

---

## 4. Protokół Postępowania dla Agenta SysAdmin (Krok po Kroku)

Gdy użytkownik prosi o konfigurację Dysku Google, dodanie folderu lub naprawę zawieszającego się uśpienia:

### KROK 1: Pre-flight Audit
Sprawdź stan środowiska:
```bash
make gdrive-status
```
- Sprawdź, czy `rclone` jest zainstalowany. Jeśli nie -> `make gdrive-install`.
- Sprawdź, czy remote `gdrive:` istnieje w `~/.config/rclone/rclone.conf`.

### KROK 2: Autoryzacja Konta (Jednorazowa)
Jeśli remote nie istnieje, poinstruuj użytkownika lub uruchom:
```bash
make gdrive-auth
```
Kreator otworzy przeglądarkę i poprosi o zgodę na dostęp rclone do Dysku Google.

### KROK 3: Wybór Folderów do Selektywnej Synchronizacji
Wylistuj dostępne zasoby na Dysku Google:
```bash
make gdrive-list
```
Dodaj wybrany folder do konfiguracji:
```bash
make gdrive-add REMOTE="NazwaFolderuWChmurze" LOCAL="LokalnaNazwa" MODE="bisync"
```

### KROK 4: Pierwsza Synchronizacja (Inicjalizacja Bazy Bisync)
Pierwsze uruchomienie `bisync` dla nowego katalogu wymaga flagi `--resync`, aby zbudować bazę porównawczą:
```bash
make gdrive-sync FOLDER="NazwaFolderuWChmurze" RESYNC=1
```
Skrypt automatycznie wykrywa brak bazy i w razie potrzeby sam zaaplikuje `--resync`.

### KROK 5: Aktywacja Usługi w Tle
Włącz timer `systemd --user`, aby synchronizacja wykonywała się automatycznie w tle:
```bash
make gdrive-timer-enable INTERVAL="15m"
```

### KROK 6: Migracja Aplikacji (np. KeePassXC)
1. Poinformuj użytkownika, by w KeePassXC otworzył bazę z nowej, czystej ścieżki:
   `/home/jarek/GoogleDrive/KeePass/<baza>.kdbx`
2. W ustawieniach KeePassXC upewnij się, że włączona jest opcja:
   *„Automatycznie przeładuj bazę, jeśli została zmodyfikowana na dysku”*.
3. Opcjonalnie: odłącz konto Google z *Ustawienia -> Konta online (GNOME Online Accounts)*, aby wyeliminować przestarzały, niestabilny montaż GVFS.

---

## 5. Protokół Weryfikacji (Post-flight Verification)

1. **Weryfikacja istnienia plików:**
   ```bash
   ls -la ~/GoogleDrive/<Folder>/
   ```
2. **Weryfikacja dwukierunkowości:**
   - Utwórz plik testowy `touch ~/GoogleDrive/<Folder>/test_sync.txt`.
   - Uruchom `make gdrive-sync FOLDER="<Folder>"`.
   - Sprawdź czy plik pojawił się w chmurze (`make gdrive-list PATH="<Folder>"`).
   - Usuń plik testowy i zsynchronizuj ponownie.
3. **Weryfikacja Usypiania Systemu (Suspend):**
   - Przy otwartym programie KeePassXC wywołaj testowe uśpienie (`systemctl suspend`).
   - Upewnij się, że stacja robocza gaśnie w ciągu 1-2 sekund bez błędu `Freezing user space processes failed after 20.007 seconds`.
