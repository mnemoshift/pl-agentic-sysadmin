# Walkthrough: Autonomiczny Montaż YouTube Shorta w Kdenlive z Agentem AI

> **Kontekst:** Alternatywa dla CapCut Pro na Linuksie (Zorin OS) bez płatnych subskrypcji i bez wysyłania danych do chmury. Wykorzystujemy serwer MCP Kdenlive, silnik MLT, lokalny model Whisper oraz reguły Agentic SysAdmina.

---

### Cel / Intencja
Oczekiwany efekt: 
1. **Wejście:** Surowe nagranie z mikrofonu OBS (`work/EP002_Short/input/raw_voiceover.mp4`) z falstartem i ciszą + długie wideo (`input/footage_ep002.mp4`).
2. **Oczyszczenie audio:** Odcięcie falstartu i ciszy, normalizacja do standardu emisyjnego EBU R128 (-14 LUFS, True Peak -1.5 dB).
3. **Generacja kadrów 9:16:** Trzy spójne grafiki wertykalne z ciemną górną 1/3 kadru pod tytuły.
4. **Złożenie osi czasu w Kdenlive:** Projekt 1080x1920 @ 60fps, kaskadowa kompozycja (rozmyte tło V1 + ostry klip V2 + tytuły V3 + audio A1).
5. **Dynamiczne napisy CapCut Karaoke:** Transkrypcja słowo po słowie z lokalnym modelem Whisper i formatem ASS (neonowe zielone podświetlenie `#00FF66`).
6. **Błyskawiczny render NVENC:** Eksport sprzętowy na karcie RTX w około 4 sekundy.

---

### Środowisko Robocze i Pliki Źródłowe
Praca odbywa się wewnątrz repozytorium `pl-agentic-sysadmin` w wykluczonym z Gita folderze roboczym `work/EP002_Short/`:

```bash
work/EP002_Short/
└── input/
    ├── raw_voiceover.mp4   # Surowy zrzut głosu z OBS-a
    └── footage_ep002.mp4   # Długie nagranie wideo (materiał źródłowy)
```

---

### Ścieżka Manualna / Oldschool (Dla zdeterminowanych)
Wyłącznie w celach porównawczych – pokazuje, ile żmudnego klikania i komend oszczędza Agent:

```bash
# 1. Obcięcie audio i normalizacja do -14 LUFS w ffmpeg
ffmpeg -y -ss 00:00:00.200 -to 00:00:30.600 -i work/EP002_Short/input/raw_voiceover.mp4 \
  -af "loudnorm=I=-14:LRA=7:tp=-1.5" -ar 48000 -ac 2 work/EP002_Short/assets/EP002_Short_VoiceOver_CLEAN.wav

# 2. Generowanie napisów Whisper z dokładnością do słowa
# Wymaga napisania skryptu w Pythonie grupowania w linijki i formatowania znaczników kolorów ASS:
# {\c&H0000FF66&}SŁOWO{\c&H00FFFFFF&}
uv run scripts/media/generate_karaoke.py \
  -a work/EP002_Short/assets/EP002_Short_VoiceOver_CLEAN.wav \
  -o work/EP002_Short/assets/EP002_Short_Karaoke.ass --fast

# 3. Ręczne składanie XML-a projektu Kdenlive / MLT
# Prawidłowe UUID traktorów, kaskada qtblend, filtry gblur i avfilter.subtitles
python3 scripts/media/build_kdenlive_short.py -w work/EP002_Short

# 4. Podgląd lub render z konsoli silnikiem melt
melt work/EP002_Short/EP002_Short.kdenlive -consumer avformat:work/EP002_Short/output.mp4 vcodec=h264_nvenc
```

---

### Ścieżka Agentic w Antigravity (Czysta intencja bez wkuwania parametrów)

Otwierasz Antigravity w głównym katalogu `pl-agentic-sysadmin`. Agent automatycznie ładuje reguły z `AGENTS.md` oraz serwer `kdenlive-mcp`.

#### Krok 1: Weryfikacja środowiska i narzędzi montażowych
Wklejasz do czatu:
> *Sprawdź konfigurację serwera MCP kdenlive oraz dostępność silnika melt i naszych narzędzi w scripts/media/.*

* **Działanie Agenta:** Wywołuje narzędzia MCP `mcp_kdenlive_*`, sprawdza wersję silnika `melt` oraz obecność modułów w `scripts/media/`.

#### Krok 2: Audyt i automatyczne czyszczenie audio
> *Przeanalizuj surowe nagranie z OBS-a w work/EP002_Short/input/raw_voiceover.mp4. Użyj naszego modułu scripts/media/clean_audio.py: wytnij początkową ciszę, falstart przed 30 sekundą oraz martwy ogon. Znormalizuj głośność do standardu -14 LUFS (EBU R128) i zapisz czysty plik WAV w work/EP002_Short/assets/EP002_Short_VoiceOver_CLEAN.wav.*

* **Działanie Agenta:** Odpala skrypt, obcina nagranie do przedziału `[00:00:00.200 - 00:00:30.600]`, aplikuje dwuprzebiegowy filtr EBU R128 i weryfikuje głośność. W lewym panelu pojawia się folder `assets/` z czystym dźwiękiem.

#### Krok 3: Generacja kadrów 9:16 pod ujęcia wertykalne
> *Wygeneruj 3 grafiki koncepcyjne 9:16 do pierwszych 3 scen Shorta i zapisz w work/EP002_Short/assets/:*
> *1. Cybernetyczny rdzeń decyzyjny (Agentic SysAdmin).*
> *2. Złożony labirynt plików konfiguracyjnych i dotfiles.*
> *3. Czyste biurko: laptop w tle z domyślnym pulpitem Zorina, laptop na pierwszym planie z pulpitem w stylu macOS (dok Plank, okna traffic lights).*
> *Warunek krytyczny: górna 1/3 kadru musi być ciemna i pozbawiona jakichkolwiek napisów.*

* **Działanie Agenta:** Generuje grafiki z zachowaniem zasady ciemnej góry kadru, aby nie kolidowały z tytułami tekstowymi.

#### Krok 4: Zbudowanie osi czasu Kdenlive (Kaskada rozmycia + Tytuły)
> *Zbuduj projekt Kdenlive 1080x1920 @ 60fps w work/EP002_Short/EP002_Short.kdenlive przy użyciu naszego generatora scripts/media/build_kdenlive_short.py:*
> *- Na ścieżce audio A1 umieść assets/EP002_Short_VoiceOver_CLEAN.wav.*
> *- Na ścieżkach wideo ułóż 3 grafiki oraz 2 wycinki z input/footage_ep002.mp4.*
> *- Zastosuj kaskadę: na dolnej ścieżce V1 powiększone, rozmyte tło (gblur), na ścieżce V2 ostry obraz z cieniem.*
> *- Na ścieżce V3 dodaj plansze tytułowe dla każdej z 5 fraz z fontem Inter Black.*

* **Działanie Agenta:** Wykorzystuje szablon MLT XML, mapuje zasoby na ścieżki i tworzy gotowy plik `.kdenlive`.

#### Krok 5: Dynamiczne napisy CapCut Karaoke (Whisper + ASS)
> *Wygeneruj dynamiczne napisy w stylu CapCut Karaoke dla pliku work/EP002_Short/assets/EP002_Short_VoiceOver_CLEAN.wav przy użyciu modułu scripts/media/generate_karaoke.py (lub make media-karaoke z flagą FAST=1). Sformatuj je jako plik ASS z fontem Inter Black 76px, białym tekstem, 10px czarnym obrysem i neonowo-zielonym podświetleniem aktywnego słowa (#00FF66). Zapisz w work/EP002_Short/assets/EP002_Short_Karaoke.ass i podepnij pod projekt Kdenlive.*

* **Działanie Agenta:** Whisper analizuje audio ze znacznikami czasu dla każdego słowa, grupuje je po 2-3 wyrazy, generuje klatki ASS z podświetleniem neonową zielenią i podpina filtr `avfilter.subtitles` do projektu Kdenlive.

---

### Weryfikacja w GUI Kdenlive i Błyskawiczny Render

1. Uruchom Kdenlive i otwórz wygenerowany projekt:  
   `Menu -> Otwórz projekt -> work/EP002_Short/EP002_Short.kdenlive`
2. Wciśnij **Spację**:  
   Zobacz płynny podgląd – wideo w tle z estetycznym rozmyciem, idealna synchronizacja cięć z głosem oraz napisy karaoke precyzyjnie podświetlające każde wypowiadane słowo.
3. Wciśnij `Ctrl + Enter` (Renderuj) $\rightarrow$ wybierz profil **NVENC H.264** na karcie RTX $\rightarrow$ kliknij **Renderuj do pliku**.  
   Cały 30-sekundowy film 1080x1920 @ 60fps renderuje się w około **4 sekundy**.

---

### Interaktywna Korekta na Żywo (Aha-Moment)

Co jeśli chcesz zmienić stylistykę napisów pod inną markę lub kolorystykę kanału? Nie przeklikujesz filtrów w edytorze – mówisz do Agenta w czacie:

> *„Zmień kolor podświetlenia aktywnego słowa na jaskrawy żółty (#FFFF00), zmniejsz obrys do 6px i przesuń napisy nieco wyżej (MarginV=800).”*

* **Oczekiwane Działanie Agenta:** Agent uruchamia `generate_karaoke.py` z flagami `--highlight '&H0000FFFF&'` oraz `--margin-v 800`, natychmiast odświeżając plik sidecar `.ass`.
* **Efekt:** W Kdenlive podgląd natychmiast aktualizuje kolor i położenie tekstu bez konieczności ponownego składania projektu!

---

### Podsumowanie
- **Suwerenność danych:** 100% lokalnego przetwarzania, zero wysyłania nagrań i głosu na serwery komercyjnych platform.
- **Koszt:** 0 zł comiesięcznych subskrypcji.
- **Powtarzalność:** Zamiast spędzać 2 godziny na żmudnym ręcznym montażu każdego Shorta, cały proces jest sprowadzony do 5 powtarzalnych promptów lub pojedynczych celów `Makefile`.
