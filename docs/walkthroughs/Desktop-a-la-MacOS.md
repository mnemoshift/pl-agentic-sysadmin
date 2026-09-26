### Cel / Intencja
> Oczekiwany efekt: Maksymalne podobieństwo do pulpitu MacOS - przezroczysty i animowany dok  na dole, górny smukły pasek statusu (28px) z wyśrodkowanym zegarem i menu Zorin z lewej strony, kropki okien (traffic lights) po lewej stronie, kursor macOS.
---
### Reset do stanu domyślnego po instalacji (Vanilla Reset #1)
> W celach prezentacyjnych - powrót do ustawień domyślnych Zorina:

```bash
make desktop-reset
```

---

### Ścieżka Manualna / Oldschool (Wklepanie w terminalu)
- Wyłącznie w celach edukacyjnych - odradzam uruchamianie 'z palca'.
- sporo pracy, efekt jest, ale za jaką cenę i na jak długo.

```bash
# 1. Pakiety systemowe
sudo apt update && sudo apt install -y plank gnome-tweaks git

# 2. Utworzenie katalogu na repozytoria i klonowanie motywów z GitHuba
mkdir -p ~/repos/zorin-customization && cd ~/repos/zorin-customization
git clone --depth 1 https://github.com/vinceliuice/WhiteSur-gtk-theme.git
git clone --depth 1 https://github.com/vinceliuice/WhiteSur-icon-theme.git
git clone --depth 1 https://github.com/vinceliuice/McMojave-cursors.git

# 3. Kompilacja i instalacja motywów WhiteSur, ikon i kursorów
cd ~/repos/zorin-customization/WhiteSur-gtk-theme && ./install.sh -m -t default -l -c light
cd ~/repos/zorin-customization/WhiteSur-icon-theme && ./install.sh
cd ~/repos/zorin-customization/McMojave-cursors && ./install.sh

# 4. Zastosowanie motywu, ikon i kursora macOS
gsettings set org.gnome.desktop.interface gtk-theme 'WhiteSur-Light'
gsettings set org.gnome.desktop.interface icon-theme 'WhiteSur-light'
gsettings set org.gnome.desktop.interface cursor-theme 'McMojave-cursors'
gsettings set org.gnome.shell.extensions.user-theme name 'WhiteSur-Light'

# 5. Styl macOS: Kropki okien (traffic lights) po LEWEJ stronie
gsettings set org.gnome.desktop.wm.preferences button-layout 'close,minimize,maximize:'

# 6. Konfiguracja smukłego paska górnego macOS (wysokość 28px, ukryte aplikacje, zegar na środku, menu Zorin)
gnome-extensions enable zorin-taskbar@zorinos.com 2>/dev/null || true
gnome-extensions enable zorin-menu@zorinos.com 2>/dev/null || true
gsettings set org.gnome.shell.extensions.zorin-taskbar panel-position 'TOP'
gsettings set org.gnome.shell.extensions.zorin-taskbar panel-positions '{"0":"TOP","1":"TOP"}'
gsettings set org.gnome.shell.extensions.zorin-taskbar multi-monitors true
gsettings set org.gnome.shell.extensions.zorin-taskbar stockgs-keep-top-panel false
gsettings set org.gnome.shell.extensions.zorin-taskbar panel-size 28
gsettings set org.gnome.shell.extensions.zorin-taskbar panel-sizes '{"0":28,"1":28}'
gsettings set org.gnome.shell.extensions.zorin-taskbar panel-margin 0
gsettings set org.gnome.shell.extensions.zorin-taskbar show-running-apps false
gsettings set org.gnome.shell.extensions.zorin-taskbar show-favorites false
python3 -c "
import subprocess, json
el = [
    {'element':'showAppsButton','visible':False,'position':'stackedTL'},
    {'element':'activitiesButton','visible':False,'position':'stackedTL'},
    {'element':'leftBox','visible':True,'position':'stackedTL'},
    {'element':'taskbar','visible':False,'position':'stackedTL'},
    {'element':'dateMenu','visible':True,'position':'centerMonitor'},
    {'element':'centerBox','visible':False,'position':'stackedBR'},
    {'element':'systemMenu','visible':True,'position':'stackedBR'},
    {'element':'rightBox','visible':True,'position':'stackedBR'},
    {'element':'desktopButton','visible':False,'position':'stackedBR'}
]
subprocess.run(['gsettings','set','org.gnome.shell.extensions.zorin-taskbar','panel-element-positions',json.dumps({'0':el,'1':el})])
subprocess.run(['gsettings','set','org.gnome.shell.extensions.zorin-taskbar','panel-element-positions-monitors-sync','true'])
"

# 7. Konfiguracja podwójnego doku Plank (DP-4: przypięte aplikacje, HDMI-0: tylko aktywne okna + menu)
dconf write /net/launchpad/plank/enabled-docks "['dock1', 'dock2']"
dconf write /net/launchpad/plank/docks/dock1/monitor "'DP-4'"
dconf write /net/launchpad/plank/docks/dock1/position "'bottom'"
dconf write /net/launchpad/plank/docks/dock1/theme "'Transparent'"
dconf write /net/launchpad/plank/docks/dock1/zoom-enabled "true"

dconf write /net/launchpad/plank/docks/dock2/monitor "'HDMI-0'"
dconf write /net/launchpad/plank/docks/dock2/position "'bottom'"
dconf write /net/launchpad/plank/docks/dock2/theme "'Transparent'"
dconf write /net/launchpad/plank/docks/dock2/zoom-enabled "true"
dconf write /net/launchpad/plank/docks/dock2/dock-items "['show-applications.dockitem', 'applications.dockitem']"
mkdir -p ~/.config/plank/dock2/launchers
rm -f ~/.config/plank/dock2/launchers/{antigravity,org.gnome.Terminal,org.gnome.Nautilus,google-chrome,code-url-handler,capcut}.dockitem 2>/dev/null || true
rm -f ~/.config/plank/dock1/launchers/capcut.dockitem 2>/dev/null || true

# 8. Uruchomienie Planka na dole i włączenie autostartu
mkdir -p ~/.config/autostart
cp /usr/share/applications/plank.desktop ~/.config/autostart/ 2>/dev/null || true
killall -9 plank 2>/dev/null || true
systemctl --user restart plank.service 2>/dev/null || nohup plank >/dev/null 2>&1 &

# 9. Aplikacje Electron/Chromium (VS Code, Chrome): wymuszenie natywnej belki z kropkami po lewej
mkdir -p ~/.config/Code/User && echo '{"window.titleBarStyle": "native"}' > ~/.config/Code/User/settings.json
```

---
### Inicjalizacja Agentic Way w Antigravity 2.0
> README - sekcja: **Szybki Start: Uruchomienie w Antigravity 2.0**

---
### Prompt (Czysta intencja bez komend konfiguracji)
- Stan bieżący - pulpit w  motywie domyślnym
- Wklej lub podyktuj głosem do Agenta w ramach nowej sesji w założonym projekcie:

> *Przygotuj ten system tak aby pulpit i uruchamiane aplikacje wyglądały w sposób maksymalnie podobny do pulpitu w MacOS.  

Następująca część promptu powinna być konsekwencją instrukcji w AGENTS.md (nie wklejamy)
> *1. Przeprowadź audyt sprzętu i podłączonych monitorów.  
> 1. Przedstaw mi plan konfiguracji i poproś o zatwierdzenie.  
> 2. Wykonaj to deterministycznie i udokumentuj fakty w dzienniku sesji.*

Następująca część prompta powinna być wynikiem analizy i 'inteligencji' agenta (nie wklejamy).
> *Skonfiguruj pulpit: pobierz i skompiluj motyw WhiteSur z GitHuba, włącz kolorowe kontrolki okien (traffic lights) po lewej stronie (w tym natywne belki CSD dla VS Code i Chrome), kursor macOS, podwójny dok Plank na dole (na monitorze głównym Ultrawide pełen zestaw skrótów, a na ekranie nagraniowym 16:9 minimalistyczny dok z aktywnymi oknami i menu), smukły górny pasek Zorina o wysokości 28px na obydwu monitorach (bez listy otwartych okien – te mają być wyłącznie w doku Plank na dole, z wyśrodkowanym zegarem i datą, oraz z menu Zorin po lewej stronie pod znaczkiem Zorina; bez podwójnego paska) oraz skonfiguruj autostart. Wykorzystaj wbudowane w repozytorium skille i kontrolery.*

---

###  Weryfikacja i akceptacja (Walkthrough Agentic)
* Zaakceptuj wygenerowany przez Agenta plan i komendy.

---

### Interaktywna Korekta na Żywo (Aha-Moment: Elastyczność Agenta)
- Weryfikacja VS Code - jeżeli brak MacOSowej belki

> *VS Code nie ma belki stylizowanej pod MacOS - wprowadź niezbędne zmiany.*

- Restart VS Code i powinniśmy widzieć zmiany...
- Natywna belka systemowa w VS Code z kropkami po lewej wygląda topornie i zabiera pionową przestrzeń. Zamiast szukać w Google i edytować JSON-y ręcznie, dyktujesz Agentowi korektę w czacie:

> *„Wiesz co, w VS Code ten natywny pasek wygląda zbyt ciężko i zabiera za dużo miejsca. Przywróć w VS Code zintegrowany pasek tytułu, zachowując styl macOS i kropki w pozostałych oknach.”*

* **Oczekiwane Działanie Agenta:** Agent odczytuje `~/.config/Code/User/settings.json`, usuwa wpis `window.titleBarStyle: native` i raportuje zmianę.
* **Efekt na ekranie:** VS Code wymaga restartu - okno wraca do eleganckiego, bezramkowego paska, podczas gdy reszta systemu ma traffic lights.

### Podsumowanie
  - **sedno pracy z Agentic SysAdminem:** to nie jest sztywny, jednorazowy instalator, z którym musisz walczyć. To interaktywny partner — mówisz po ludzku, co Ci się nie podoba, a on atomowo dostosowuje środowisko pod Twoje preferencje.
  - korzysta ze skryptów (skills), ale reaguje na błędy, specyfike intencji, poprawia je i wykorzystuje w innych kontekstach
  - Wyświetl wpis w `memory/JOURNAL.md` oraz wykonaj `make restore-dry-run` jako dowód powtarzalności Disaster Recovery!