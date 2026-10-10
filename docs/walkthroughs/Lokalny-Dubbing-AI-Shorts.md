# Walkthrough: Suwerenny Potok Dubbingu i Voiceoveru AI na GPU (Shorts)

Procedura automatycznego tłumaczenia, syntezy mowy i masteringu audio dla zestawu materiałów YouTube Shorts (format pionowy 9:16) bez zewnętrznych API i opłat chmurowych.

---

## 1. Architektura i Bilans Pamięci VRAM (RTX 4060 Ti 16GB)

Przepustowość wewnętrznej pamięci GDDR6 karty graficznej wynosi **288 GB/s**, podczas gdy magistrala PCIe 4.0 x8 oferuje zaledwie **~12 GB/s** (proporcja **24:1**). 

Przekroczenie budżetu 16.0 GB VRAM powoduje natychmiastowe zrzucanie tensorów do systemowego RAM-u przez wąskie gardło magistrali i katastrofalny spadek wydajności (spadek 24:1). Dlatego cały potok audio zamyka się w bezpiecznym oknie pamięci z dużym marginesem bezpieczeństwa:

| Komponent / Model | Rola w Potoku | Format Wag | Alokacja VRAM |
| :--- | :--- | :--- | :---: |
| **faster-whisper (large-v3-turbo / base)** | Ekstrakcja segmentów i znaczników czasu | CTranslate2 FP16 | **1.60 GB** |
| **Breeze-TTS-2 3.5B (PyTorch CUDA)** | Zero-shot klonowanie głosu referencyjnego | bfloat16 / FP16 | **7.70 GB** |
| **Kokoro-82M (Alternatywa)** | Szybki lektor radiowy EN | ONNX FP16 | **0.28 GB** |
| **Edge-TTS (Fallback)** | Natychmiastowa synteza lektorska | Headless | **0.00 GB** |
| **System OS / GUI Zorin OS** | Kompozytor i bufor ramki | Native | **0.50 GB** |
| **Margines Bezpieczeństwa (Headroom)** | Dynamiczne bufory aktywacji | Wolna pamięć | **~6.20 GB** |
| **ŁĄCZNY BILANS** | **Kompletny Stos Audio na GPU** | — | **~9.80 GB / 16.0 GB** |

---

## 2. Przygotowanie Przestrzeni Roboczej (`work/`)

Repozytorium jest w 100% generyczne — żadne prywatne surówki ani nagrania lektorskie nie trafiają do Gita. Wszystkie materiały źródłowe umieszczasz wyłącznie w katalogu `work/` (objętym `.gitignore`).

W potoku dubbingu przyjmujemy jednolity, suwerenny standard wejściowy dla każdego projektu (`work/<ID>/input/`):
* **Czysty Plik Wideo (`*.mp4`):** Każdy podkatalog `input/` zawiera **WYŁĄCZNIE plik wideo**.
* **Zero zależności od zewnętrznych napisów:** Stan początkowy nie bazuje na obecności plików `.srt` ani skryptów `.md`. Jeżeli napisy są potrzebne, agent i potok generują je od zera w locie (Whisper ekstrahuje mowę, tworzy segmenty i zapisuje napisy `_PL.srt` oraz `_EN.srt`).
* **Wersjonowanie przebiegów (Run Versioning):** Każde uruchomienie potoku, jeśli nie wskazano jawnego katalogu wyjściowego przez `-o / --output-dir`, tworzy niezależny, zwersjonowany folder w `work/runs/YYYY-MM-DD_HH-MM-SS_<engine>_<slug>/`, a najnowszy przebieg jest zawsze dostępny pod atomowym symlinkiem `work/latest`.

Struktura katalogu `work/`:

```text
work/
├── voice_source/
│   └── EP003_VoiceOver_CLEAN.wav                         # Nagranie źródłowe do wycięcia próbki lektora (00:12–00:20)
├── voice_sample/
│   └── ref_voice_sample.wav                              # Wycięta próbka lektorska (24kHz mono)
├── EP002_Short/
│   └── input/
│       └── EP002_Short_Agentic_SysAdmin_Karaoke_FIXED.mp4 # Wyłącznie wideo shorta (30s)
├── EP001_Short/
│   └── input/
│       └── EP001_Short_WSL_vs_Zorin_FINAL.mp4             # Wyłącznie wideo shorta (34s)
├── latest -> runs/2026-10-10_16-30-00_edge_EP002_Short    # Atomowy symlink do ostatniego przebiegu
└── runs/
    └── 2026-10-10_16-30-00_edge_EP002_Short/              # Zwersjonowany workspace przebiegu
        ├── logs/
        │   └── execution.log                             # Pełny strumień konsoli (Tee logging)
        ├── 01_source_extracted/                          # Wyekstrahowany strumień mowy (24kHz WAV)
        ├── 02_transcription/                             # Surowa transkrypcja i segmenty czasowe Whisper
        ├── 03_llm_adaptation/                            # JSON adaptacji LLM z pacingiem
        ├── 04_tts_segments/                              # Pocięte pliki WAV scen i markery .txt / .engine
        ├── 05_subtitles/                                 # Napisy SRT / ASS
        ├── 06_output/                                    # Finalne deliverable (WAV -14 LUFS, MP4, Summary MD)
        └── run_summary.json                              # Zbiorczy raport z audytem jakości (WPM, dryf, clipping)
```

Przed rozpoczęciem sesji folder `work/voice_sample/` oraz foldery wyjściowe nie istnieją — Agent wygeneruje je od zera na Twoich oczach.

---

## 3. Ścieżka Krok po Kroku w Antigravity (Anatomia Potoku na EP002)

Otwierasz Antigravity w projekcie `pl-agentic-sysadmin-work`. Agent automatycznie ładuje kontekst z `AGENTS.md` oraz skill `voice-dubber`. 

W pierwszym podejściu przechodzimy przez proces krok po kroku, aby dokładnie widzieć anatomię poszczególnych etapów i bilans zasobów:

### Krok 1: Wycięcie próbki głosu lektora
Wklejasz w oknie czatu Antigravity:
> *Wytnij 8-sekundową próbkę głosu z nagrania w work/voice_source od 00:12 do 00:20.*

* **Działanie Agenta:** 
  - Lokalizuje `work/voice_source/EP003_VoiceOver_CLEAN.wav`.
  - Wywołuje procedurę ekstrakcji i zapisuje bezstratną próbkę studyjną (24kHz mono WAV) w `work/voice_sample/ref_voice_sample.wav` wraz z transkrypcją referencyjną (*„Zmontowałem to w całości lokalnie na Linuksie...”*).
  - Raportuje gotowość biometrii głosu do syntezy.

### Krok 2: Dubbing i mastering pierwszego shorta (EP002)
Wklejasz w czacie polecenie czystej intencji (bez podawania flag technicznych ani parametrów głośności — agent sam wie, że przygotowuje materiał emisyjny):
> *Przetłumacz i zdubbinguj shorta w work/EP002_Short.*

* **Działanie Agenta:**
  - Automatycznie wykrywa wideo w `work/EP002_Short/input/` (brak predefiniowanych napisów czy skryptów).
  - Ekstrahuje strumień mowy i lokalnie uruchamia Whisper, który w locie dzieli nagranie na segmenty ze znacznikami czasu.
  - Tłumaczy kwestie z zachowaniem ścisłego słownika IT (*mount point*, *VRAM footprint*, *PCIe bus*, *macOS-inspired workspace*).
  - Generuje komplet napisów SRT (`EP002_Short_PL.srt` oraz `EP002_Short_EN.srt`).
  - Przeprowadza syntezę na GPU (Breeze-TTS-2 / Edge-TTS) z wykorzystaniem wyciętej próbki głosu.
  - Dopasowuje tempo do cięć wideo, wstawia pauzy i masteruje ścieżkę do standardu emisyjnego **-14 LUFS** (EBU R128).
  - Zapisuje rezultaty w wersjonowanym folderze `work/runs/YYYY-MM-DD_HH-MM-SS_<engine>_EP002_Short/06_output/` (lub w jawnie wskazanym `-o / --output-dir`) i dostarcza komplet plików produkcyjnych:
    1. Czysty plik audio lektora EN: `EP002_Short_VoiceOver_EN_CLEAN.wav` (pod YouTube Multi-Language Audio).
    2. Gotowy plik wideo z dubbingiem: `EP002_Short_FINAL_EN_DUBBED.mp4` (obraz + audio EN).
    3. Napisy: `EP002_Short_EN.srt` oraz `EP002_Short_PL.srt`.
    4. Zbiorczy raport audytu jakości: `run_summary.json` oraz `EP002_Short_Dubbing_Summary.md`.
  - Zwraca w czacie zwięzłą tabelę porównawczą A/B (PL vs EN).

### Krok 3: Odsłuch i inspekcja parametrów
Wpisujesz w czacie:
> *Odtwórz wygenerowane wideo dla EP002 i podsumuj parametry audio.*

* **Działanie Agenta:**
  - Uruchamia podgląd wideo lub odtwarza próbkę audio w systemowym odtwarzaczu.
  - Wyświetla zmierzone parametry: Zintegrowana głośność (`-14.0 LUFS` do `-15.3 LUFS`), True Peak (`< -1.0 dBFS`), WPM, dryf czasu.

---

## 4. Ścieżka One-Shot w Antigravity (Cały Potok „Na Raz” dla EP001)

Gdy wiesz już jak działa system, nie musisz rozbijać pracy na pojedyncze etapy. Prawdziwa siła podejścia **Agentic SysAdmin** polega na zleceniu pełnego łańcucha operacyjnego za pomocą **dokładnie jednego promptu czystej intencji**.

Dla drugiego shorta z zestawu (`work/EP001_Short`, 34-sekundowa wersja punchy) zlecamy wykonanie całego potoku za jednym zamachem:

> *Zdubbinguj materiał w work/EP001_Short przy użyciu przygotowanej próbki głosu i odtwórz gotowe wideo.*

* **Działanie Agenta:**
  1. Spina cały workflow bez konieczności interwencji użytkownika.
  2. Bada wejście: wykrywa wyłącznie plik wideo `EP001_Short_WSL_vs_Zorin_FINAL.mp4` (bez zewnętrznych plików .srt czy .wav).
  3. Ekstrahuje audio i transkrypuje w Whisper dynamiczne segmenty.
  4. Dokonuje inżynierskiego przekładu PL $\rightarrow$ EN i generuje napisy `EP001_Short_PL.srt` oraz `EP001_Short_EN.srt`.
  5. Przeprowadza syntezę, dopasowuje czasy segmentów pod oryginalne cięcia.
  6. Przeprowadza broadcastowy mastering EBU R128 (-14.0 LUFS, True Peak $\le$ -1.0 dBFS).
  7. Zapisuje komplet plików produkcyjnych i aktualizuje symlink `work/latest`.
  8. Wyświetla podsumowanie z tabelą scen i uruchamia odtworzenie rezultatu.

---

## 5. Skalowanie na Długi Format (EP002 i Porównanie 1:1 z ElevenLabs)

Ten sam suwerenny potok nie jest ograniczony wyłącznie do formatu Shorts. W projekcie `work/EP002` znajduje się pełnometrażowy odcinek (12:08, 1440p60) w `work/EP002/input/EP002_Zorin_Desktop_FINAL.mp4` oraz nagranie referencyjne przygotowane w ElevenLabs (`work/EP002/reference/EP002_FINAL_EN_ElevenLabs.mp4`).

Wpisujesz w czacie Antigravity:
> *Zdubbinguj materiał w work/EP002 przy użyciu przygotowanej próbki głosu.*

* **Działanie Agenta:**
  1. Wykrywa czyste wideo w `input/`.
  2. Ekstrahuje strumień mowy i automatycznie transkrypuje oraz synchronizuje segmenty z Whisperem.
  3. Dokonuje inżynierskiego przekładu dialogów oraz generuje napisy SRT.
  4. Generuje zsynchronizowane audio i gotowy plik wideo w zwersjonowanym folderze `work/runs/`.
  5. Umożliwia natychmiastowe zderzenie jakościowe A/B: odsłuch lokalnego modelu na karcie RTX 4060 Ti (koszt 0 zł, zero wycieków do chmury) obok chmurowego dubbingu ElevenLabs.

---

## 6. Ścieżka Manualna / Oldschool CLI (Dla zdeterminowanych)

Wyłącznie w celach poglądowych dla inżynierów, którzy chcą uruchomić poszczególne polecenia ręcznie z poziomu terminala bash:

```bash
# 1. Ręczne wycięcie próbki referencyjnej głosu:
python3 scripts/media/extract_voice_sample.py \
  -i work/voice_source/EP003_VoiceOver_CLEAN.wav \
  -s 00:00:12.000 -e 00:00:20.300 \
  -o work/voice_sample/ref_voice_sample.wav \
  -t "Zmontowałem to w całości lokalnie na Linuksie, rozmawiając z agentem AI w naszym repozytorium, ani razu nie dotknąłem myszki."

# 2. Domyślny przebieg dubbingu (tworzy zwersjonowany katalog work/runs/... oraz link work/latest):
python3 scripts/media/dub_video.py -w work/EP002_Short

# 3. Dubbing z jawnym wskazaniem katalogu wyjściowego (-o / --output-dir):
python3 scripts/media/dub_video.py -w work/EP002_Short -o work/EP002_Short/output

# 4. Dubbing z włączonym trybem ekspresyjnym Two-Pass TTS Voice Tags:
python3 scripts/media/dub_video.py -w work/EP002_Short --engine edge --expressive

# 5. Przetwarzanie wsadowe zestawu wideo:
python3 scripts/media/dub_video.py --batch work/EP002_Short work/EP001_Short work/EP002

# 6. Generowanie polskiego lektora ze skryptu Markdown:
python3 scripts/media/generate_voiceover.py -s scripts/media/scenariusz.md -o work/runs/voiceover_pl
```

---

## 7. Wersjonowanie Przebiegów, Struktura Plików i Standard Emisyjny

### Zasada wersjonowania (Run Workspace):
1. **Domyślne uruchomienie bez `-o`:** Skrypt tworzy unikalny katalog `work/runs/YYYY-MM-DD_HH-MM-SS_<engine>_<slug>/` i atomowo ustawia symlink `work/latest` wskazujący na ten katalog. Poprzednie przebiegi pozostają nienaruszone, co umożliwia porównywanie eksperymentów A/B.
2. **Jawne wskazanie katalogu wyjściowego (`-o / --output-dir <katalog>`):** Skrypt zapisuje wyniki bezpośrednio do wskazanego folderu (np. `work/EP002_Short/output/`), zachowując uporządkowaną hierarchię podkatalogów etapowych. Nie jest tworzone żadne wymuszone linkowanie wsteczne do innych folderów.

### Podkatalogi etapowe wewnątrz każdego przebiegu:
* `logs/execution.log` – kompletny zrzut konsoli (stdout/stderr) przechwytywany w locie.
* `01_source_extracted/` – wyekstrahowany strumień mowy 24kHz PCM mono.
* `02_transcription/` – surowa transkrypcja i segmenty czasowe Whisper.
* `03_llm_adaptation/` – plik JSON z przetłumaczonymi kwestiami i pacingiem lektorskim.
* `04_tts_segments/` – wygenerowane pliki `.wav`, `.txt` i `.engine` dla każdej sceny.
* `05_subtitles/` – napisy `_EN.srt` i `_PL.srt`.
* `06_output/` – gotowe pliki produkcyjne (Deliverables).
* `run_summary.json` – metadane systemowe, czasy faz oraz audyt jakościowy.

### Pliki produkcyjne w `06_output/`:
1. **Plik dźwiękowy lektora (YouTube Multi-Language Audio):**
   * `<ID>_VoiceOver_EN_CLEAN.wav` – zmasterowany plik audio lektora EN (48kHz stereo, broadcast mastering -14.0 LUFS, True Peak $\le$ -1.0 dBFS).
2. **Zdubbingowany film EN (Full Video + Dubbing):**
   * `<ID>_FINAL_EN_DUBBED.mp4` – kompletny plik wideo ze zsynchronizowaną ścieżką EN i oryginalnym obrazem.
3. **Napisy:**
   * `<ID>_EN.srt` oraz `<ID>_PL.srt`.
4. **Raport podsumowujący:**
   * `<ID>_Dubbing_Summary.md` – tabela zsynchronizowanych scen wraz z audytem jakościowym (Quality Metrics).

### Automatyczny Audyt Jakościowy (`QualityAnalyzer`):
Każdy przebieg automatycznie analizuje gotowy plik audio i zapisuje metryki w `run_summary.json`:
- **WPM (Words Per Minute):** Tempo mowy z ostrzeżeniem jeśli wykracza poza normę (110–170 WPM).
- **Dryf czasu (Drift):** Różnica czasu trwania mowy względem docelowego okna wideo (ostrzeżenie > 2.0s).
- **Integralność sygnału (Peak dB, RMS dB, Clipping):** Weryfikacja przesterowań (True Peak > -0.05 dBFS).
- **Nienaturalne pauzy:** Wykrywanie niepożądanych pustych przerw wewnątrz kwestii (> 1.5s).
