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

### Środowisko Robocze: Szablony (`templates/`) vs Przestrzeń Robocza (`work/`)

Repozytorium rozróżnia dwa poziomy plików:
1. **Publiczne szablony (`templates/`):** Generyczne, czyste pliki bazowe współdzielone w repozytorium:
   - `templates/kdenlive/short_script.md` — uniwersalny szablon 5 scen z instrukcjami i placeholderami,
   - `templates/kdenlive/short_9_16_template.kdenlive` — profil MLT 1080x1920 @ 60fps z kaskadą rozmycia.
   *(W repozytorium nie przechowujemy statycznych grafik referencyjnych – każdy short ma własne, unikalne sceny, a grafiki są generowane od zera przez Agenta na bazie promptów z transkrypcji).*
2. **Prywatny katalog roboczy (`work/<PROJEKT>/`):** Folder wykluczony z Gita (`.gitignore`), w którym pracujesz ze swoim filmem:

```bash
work/<NAZWA_PROJEKTU>/ (np. work/EP002_Short/)
└── input/
    ├── short_script.md     # Skopiowany z templates/ i wypełniony scenariusz
    ├── raw_voiceover.mp4   # Surowy zrzut głosu z mikrofonu OBS
    └── footage_ep002.mp4   # Długie nagranie wideo (materiał źródłowy 16:9)
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
Wklejasz lub dyktujesz do czatu (obsługiwane przez skill `media-short-editor`):
> *Sprawdź gotowość Kdenlive i narzędzi multimedialnych.*

* **Działanie Agenta:** Wywołuje narzędzia MCP `mcp_kdenlive_*`, sprawdza wersję silnika `melt` oraz obecność modułów w `scripts/media/`.

#### Krok 2: Audyt i automatyczne czyszczenie audio
> *Oczyść surowe nagranie z OBS-a i przygotuj dźwięk do montażu.*

* **Działanie Agenta:** Lokalizuje nagranie w `work/EP002_Short/input/raw_voiceover.mp4`, wycina początkową ciszę, falstart przed 30 sekundą oraz martwy ogon, aplikuje dwuprzebiegowy filtr EBU R128 (-14 LUFS) i zapisuje plik w `assets/EP002_Short_VoiceOver_CLEAN.wav` wraz z raportem.

#### Krok 3: Generacja kadrów 9:16 pod ujęcia wertykalne
> *Wygeneruj 3 pionowe grafiki koncepcyjne z ciemną górą pod tytuły.*

* **Działanie Agenta:** Generuje 3 grafiki w `work/EP002_Short/assets/` od zera na bazie promptów ze scenariusza/transkrypcji (bez obrazów referencyjnych). Każdy kadr odzwierciedla intencję i treść danej sceny, ściśle przestrzegając zasady ciemnej góry kadru pod napisy tytułowe.

#### Krok 4: Zbudowanie osi czasu Kdenlive (Kaskada rozmycia + Tytuły)
> *Zmontuj pionowy projekt Kdenlive z kaskadowym tłem i tytułami.*

* **Działanie Agenta:** Wykorzystuje szablon MLT XML, mapuje zasoby na ścieżki i tworzy gotowy plik `.kdenlive` z kaskadą kompozycji `qtblend` (rozmyte tło V1, ostry klip V2, plansze tytułowe V3, audio A1).

#### Krok 5: Dynamiczne napisy CapCut Karaoke (Whisper + ASS)
> *Wygeneruj dynamiczne napisy karaoke CapCuta i podepnij pod projekt.*

* **Działanie Agenta:** Whisper analizuje audio ze znacznikami czasu dla każdego słowa, grupuje je po 2-3 wyrazy, generuje klatki ASS z podświetleniem neonową zielenią `#00FF66`, systemowo zabezpiecza przed nakładaniem się klatek (monotonic timeline) i podpina filtr `avfilter.subtitles` do projektu Kdenlive.

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
