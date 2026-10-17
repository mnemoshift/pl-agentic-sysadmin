# Walkthrough: Suwerenny Potok Dubbingu i Voiceoveru AI na GPU (Shorts & Long-Form)

Kompletny przewodnik uruchomienia autonomicznego potoku tłumaczenia, reżyserii aktorskiej, syntezy mowy z transferem barwy głosu oraz masteringu EBU R128 (-14.0 LUFS) na lokalnej karcie NVIDIA RTX 4060 Ti 16 GB - bez zewnętrznych API, abonamentów chmurowych i wycieków danych.

---

## 1. Architektura Potoku i Sekwencyjny Bilans Pamięci VRAM (16 GB)

Przepustowość pamięci GDDR6 na karcie RTX 4060 Ti 16 GB wynosi **288 GB/s**, podczas gdy magistrala PCIe 4.0 x8 oferuje ok. **12 GB/s** (stosunek **24:1**). Aby uniknąć jednoczesnego trzymania wszystkich modeli w pamięci i zrzucania tensorów do systemowego RAM-u, potok stosuje **sekwencyjne przekazywanie pałeczki (Sequential VRAM Handover)**: każdy etap zwalnia pamięć GPU (`torch.cuda.empty_cache()` oraz `keep_alive: 0` w Ollamie) przed startem kolejnego.

```text
[WEJŚCIE: work/<projekt>/input/wideo.mp4 + work/voice_sample/ref_voice_sample_en.wav]
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ETAP 1: Ekstrakcja Audio (01_source_extracted/)                             │
│ - FFmpeg PCM 16-bit 24 kHz mono (<ID>_VoiceOver_RAW_24k.wav)                │
└─────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ETAP 2: Transkrypcja ASR + Korekta Bielik + Grupowanie (02_transcription/)  │
│ 2a. faster-whisper large-v3-turbo (CUDA FP16, ~1.6 GB VRAM)                 │
│     -> 01_whisper_raw_segments.json / .srt                                  │
│ 2b. Bielik 11B v3.0 Instruct (Ollama Q4_K_M, ~7.5 GB VRAM)                  │
│     -> Naprawa fonetyki terminów IT i interpunkcji PL                       │
│     -> 02_bielik_cleaned_segments.json + 02_bielik_cleanup_diff.md          │
│ 2c. Semantyczne grupowanie w pełne kwestie lektorskie (12-28s)              │
│     -> 03_scenes_pl_grouped.json / .srt                                     │
└─────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ETAP 3: Adaptacja EN, Pacing Guardrail i Reżyseria (03_llm_adaptation/)     │
│ 3a. Bielik 11B + Pacing Controller (zamknięta pętla kontroli czasu i sylab) │
│     -> 04_translated_scenes_en.json + 04_pacing_calibration_log.json        │
│ 3b. Bielik 11B Text Director (generowanie instrukcji aktorskich dla TTS)    │
│     -> 05_acting_directions.json  [Po tym kroku: Ollama unload -> 0 GB VRAM]│
└─────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ETAP 4: Hybrydowa Synteza Mowy i Transfer Barwy Głosu (04_tts_segments/)    │
│ 4a. Qwen3-TTS 1.7B CustomVoice (Apache 2.0, ~3.8 GB VRAM)                   │
│     -> Synteza z pełnym Acting Direction (scene_XXX_raw_speaker.wav)        │
│ 4b. OpenVoice v2 Tone Color Converter (MIT, ~0.4 GB VRAM)                   │
│     -> Nałożenie barwy Twojego głosu z próbki referencyjnej (scene_XXX.wav) │
└─────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ETAP 5 i 6: Synchronizacja WSOLA, Mastering EBU R128 i Muxing (06_output/)  │
│ - Dopasowanie czasu mowy do cięć wideo (FFmpeg atempo [0.92x - 1.08x])      │
│ - Room Tone (-58 dB pink noise) + Broadcast EQ (70 Hz HPF + 8 kHz +1.5 dB)  │
│ - Mastering EBU R128 (-14.0 LUFS, True Peak <= -1.0 dBFS)                   │
│ - Gotowe pliki w work/<projekt>/output/: MP4, WAV 48kHz, SRT PL/EN, Raport  │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Komponent / Model | Rola w Potoku | Licencja | Szczytowy VRAM |
| :--- | :--- | :---: | :---: |
| **faster-whisper (`large-v3-turbo`)** | Surowa transkrypcja mowy ze znacznikami czasu | MIT | **~1.6 GB** |
| **Bielik 11B v3.0 Instruct (`Q4_K_M`)** | Korekta ASR PL, tłumaczenie z Pacing Guardrail, Acting Direction | Apache 2.0 | **~7.5 GB** |
| **Qwen3-TTS 1.7B CustomVoice** | Ekspresyjna synteza mowy EN ze sterowaniem aktorskim (`instruct`) | Apache 2.0 | **~3.8 GB** |
| **OpenVoice v2 Tone Color Converter** | Zero-shot konwersja barwy głosu na barwę autora | MIT | **~0.4 GB** |
| **Alternatywy TTS (`qwen-base`, `kokoro`, `chatterbox`)** | Opcjonalne silniki syntezy wybierane flagą `ENGINE=` | Apache 2.0 / MIT | **0.3 - 4.2 GB** |

---

## 2. Konwencja Katalogu `work/` (Izolacja Projektów i Zero Nadpisywania)

Wszystkie materiały robocze znajdują się w katalogu `work/` (objętym `.gitignore`). Aby można było dubbingować dowolną liczbę różnych filmów bez obawy o nadpisanie wcześniejszych wyników, obowiązuje konwencja **jeden podfolder w `work/` = jeden materiał wideo**:

```text
work/
├── voice_sample/                     # Globalna pula próbek referencyjnych głosu (barwa lektora)
│   ├── ref_voice_sample_en.wav       # Domyślna próbka referencyjna EN (24 kHz mono, 6-15s)
│   └── ref_voice_sample.wav          # Próbka referencyjna PL
│
├── EP002_Short/                      # Podfolder konkretnego projektu (np. EP002_Short, moj_film)
│   ├── input/                        # [WEJŚCIE] Surowe pliki źródłowe (nigdy nie są modyfikowane)
│   │   ├── wideo.mp4                 # Wideo źródłowe do zdubbingowania (wymagane)
│   │   ├── voiceover_clean.wav       # Opcjonalna czysta ścieżka polskiego lektora WAV
│   │   └── ref_voice*.wav            # Opcjonalna próbka głosu dedykowana tylko dla tego projektu
│   │
│   ├── output -> runs/<latest>/06_output  # [WYJŚCIE] Symlink do gotowych plików ostatniego przebiegu
│   ├── latest -> runs/<latest>            # Symlink do pełnego katalogu ostatniego przebiegu
│   │
│   └── runs/                         # Niemutowalna historia wszystkich uruchomień danego projektu
│       └── 2026-10-17_12-00-00_qwen_EP002_Short/
│           ├── 01_source_extracted/  # Wyekstrahowana ścieżka lektorska 24 kHz mono
│           ├── 02_transcription/     # Surowy Whisper -> Korekta Bielik (+ Diff) -> Grupowanie
│           ├── 03_llm_adaptation/    # Tłumaczenie EN + Pacing Log + Acting Directions JSON
│           ├── 04_tts_segments/      # Segmenty WAV (surowy aktor + konwersja barwy OpenVoice v2)
│           ├── 05_subtitles/         # Napisy robocze SRT PL/EN
│           ├── 06_output/            # Pliki produkcyjne (MP4, WAV -14 LUFS, SRT, Raport MD)
│           ├── logs/execution.log    # Pełny log wykonania potoku
│           └── run_summary.json      # Metryki czasu, WPM, dryfu i poziomów audio
│
├── latest -> <PROJEKT>/runs/<latest> # Globalny symlink do ostatniego uruchomienia w całym repo
└── archive/                          # Archiwum historycznych eksperymentów i starszych przebiegów
```

---

## 3. Szybki Start z Poziomu Terminala (`make`)

Cały proces został opakowany w proste komendy `make`, w których podajesz wyłącznie nazwę podfolderu projektu (`WORK=<podfolder>`):

### Krok 0: Jednorazowe przygotowanie środowiska i modeli
```bash
# Inicjalizacja środowiska Python (.venv)
make setup

# Pobranie wag modeli AI oraz upewnienie się, że w Ollamie dostępny jest model Bielik 11B:
make media-setup-models
ollama pull SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M
```

### Krok 1: Przygotowanie próbki głosu (jednorazowo)
Domyślna próbka referencyjna znajduje się w `work/voice_sample/ref_voice_sample_en.wav`. Jeśli chcesz wyciąć nową 8-10 sekundową próbkę ze swojego czystego nagrania:
```bash
make media-extract-sample \
  INPUT=/sciezka/do/twojego_nagrania.wav \
  START=00:00:12.000 \
  END=00:00:22.000 \
  OUTPUT=work/voice_sample/ref_voice_sample_en.wav
```

### Krok 2: Inicjalizacja nowego projektu w `work/<podfolder>`
Możesz utworzyć folder `work/<podfolder>/input/` ręcznie i wrzucić tam plik `.mp4`, albo użyć komendy `make dub-init`:
```bash
make dub-init WORK=moj_material INPUT=/sciezka/do/filmu.mp4
```

### Krok 3: Uruchomienie domyślnego potoku dubbingu
Jedna komenda uruchamia cały 6-etapowy workflow (Whisper -> Bielik Cleanup -> Grouping -> Bielik Translation & Pacing -> Bielik Acting Direction -> Qwen3-TTS CustomVoice + OpenVoice v2 Timbre Converter -> Mastering -14 LUFS):
```bash
make dub WORK=moj_material
```
*(Możesz też pominąć `make dub-init` i od razu podać `make dub WORK=moj_material INPUT=/sciezka/do/filmu.mp4` - skrypt automatycznie utworzy `work/moj_material/input/` i skopiuje plik źródłowy).*

Po zakończeniu gotowe pliki znajdziesz w:
- **`work/moj_material/output/`** (zawiera `moj_material_FINAL_EN_DUBBED.mp4`, `moj_material_VoiceOver_EN_CLEAN.wav`, napisy `.srt` oraz raport `moj_material_Dubbing_Summary.md`).
- **`work/moj_material/latest/`** (zawiera wszystkie pliki pośrednie z etapów `01_*` do `06_*`).

### Krok 4: Wybór innego silnika TTS, trybu chunkowania i wznawianie etapów (Opcjonalnie)
Domyślnie potok używa `ENGINE=qwen` (hybrydy `Qwen3-TTS 1.7B CustomVoice + OpenVoice v2`), ale możesz elastycznie sterować każdym aspektem potoku za pomocą parametrów `make`:

```bash
# --- Wznawianie i Restart od Wybranego Etapu ---
# 1. Wznowienie od tłumaczenia po ręcznej korekcie transkrypcji PL (03_scenes_pl_grouped.json):
make dub WORK=moj_material FROM=translate

# 2. Wznowienie od syntezy TTS po edycji kwestii EN lub instrukcji aktorskich (05_acting_directions.json):
# (Dzięki markerom .txt i .instr syntezowane są tylko zmodyfikowane sceny - cache hit dla pozostałych!)
make dub WORK=moj_material FROM=tts

# 3. Wznowienie od masteringu audio EBU R128 i muxingu wideo MP4:
make dub WORK=moj_material FROM=master

# --- Kontrola Wielkości Kwestii (Adaptive Chunking) ---
# Domyślnie 'auto': filmy <= 2 min (Shorts) dzielone na 2.5-7.5s, filmy > 2 min na 12-28s.
# Możesz jawnie wymusić tryb podziału:
make dub WORK=moj_material CHUNKS=short   # Kwestie 2.5-7.5s (dla dynamicznych cięć i napisów karaoke)
make dub WORK=moj_material CHUNKS=long    # Akapity 12-28s (dla długich wykładów i screencastów)

# --- Alternatywne Silniki Syntezy TTS ---
# Czysty klon zero-shot Qwen3-TTS 0.6B Base (bez CustomVoice i bez OpenVoice v2)
make dub WORK=moj_material ENGINE=qwen-base

# KokoClone (Kokoro-ONNX + Kanade Voice Conversion)
make dub WORK=moj_material ENGINE=kokoro

# Chatterbox-Turbo (MIT)
make dub WORK=moj_material ENGINE=chatterbox

# Breeze-TTS-2 (CC-BY-NC - wyłącznie do testów niekomercyjnych)
make dub WORK=moj_material ENGINE=breeze

# Szybki podgląd na Microsoft Edge Neural TTS (0 GB VRAM)
make dub WORK=moj_material ENGINE=edge

# Wyłącznie transkrypcja Whisper + korekta Bielik + tłumaczenie i napisy SRT (bez syntezy TTS)
make dub-transcribe WORK=moj_material

# Podgląd stanu wszystkich projektów w work/ i ostatniego przebiegu
make dub-status
```

---

## 4. Testowanie Acting Direction i Konwersji Barwy Głosu (`make media-test-acting`)

Chcesz przed pełnym dubbingiem usłyszeć różnicę między suchą syntezą a pełną reżyserią głosu (`Acting Direction`) i konwersją barwy (`OpenVoice v2`) na pojedynczym zdaniu? Użyj wbudowanego benchmarku:

```bash
# Domyślny test 3-etapowy (1. Bez reżyserii -> 2. Z reżyserią aktorską -> 3. Z Twoją barwą głosu):
make media-test-acting PLAY=1

# Test z własnym tekstem i własną instrukcją reżyserską:
make media-test-acting \
  TEXT="Why did the container crash? Wait... we forgot to mount the volume!" \
  INSTRUCTION="Start with confused curiosity, pause briefly, then speak with sudden realization and urgency." \
  PLAY=1
```

Skrypt zapisuje trzy próbki porównawcze w `work/acting_test/`:
1. `1_without_acting_direction.wav` - płaski odczyt bez instrukcji,
2. `2_with_acting_direction.wav` - ekspresyjny odczyt wygenerowany przez `Qwen3-TTS 1.7B CustomVoice`,
3. `3_with_acting_and_timbre.wav` - ten sam ekspresyjny odczyt po nałożeniu Twojej barwy głosu przez `OpenVoice v2`.

---

## 5. Praca w Trybie Agentowym w Antigravity IDE (`voice-dubber`)

Gdy otworzysz repozytorium w **Antigravity IDE** (lub Claude Code), agent automatycznie ładuje reguły `AGENTS.md` oraz skill `.agents/skills/voice-dubber/SKILL.md`. Nie musisz pamiętać nazw skryptów ani flag - wydajesz polecenia w języku naturalnym:

### Przykładowe prompty w czacie Antigravity:
1. **Dubbing istniejącego projektu w `work/`:**
   > *"Zdubbinguj materiał w EP002_Short i pokaż podsumowanie parametrów audio."*
   - Agent uruchamia `make dub WORK=EP002_Short`, czeka na zakończenie 6 etapów i prezentuje tabelę zsynchronizowanych scen oraz metryki LUFS/WPM z `work/EP002_Short/output/`.
2. **Dubbing nowego pliku wideo z dysku:**
   > *"Zainicjuj projekt dubbingowy 'ep005_teaser' z pliku ~/Wideo/teaser.mp4 i uruchom pełny dubbing."*
   - Agent wykonuje `make dub WORK=ep005_teaser INPUT=~/Wideo/teaser.mp4`.
3. **Porównanie różnych silników TTS na tym samym materiale:**
   > *"Wygeneruj dubbing dla EP002_Short używając domyślnego silnika qwen, a potem drugi przebieg używając kokoro, żebym mógł porównać oba w folderze runs."*
   - Ponieważ każdy przebieg zapisuje się w osobnym podkatalogu `work/EP002_Short/runs/<timestamp>_<engine>_EP002_Short/`, żaden plik nie zostaje nadpisany.
4. **Inspekcja korekty transkrypcji i tłumaczenia:**
   > *"Pokaż jakie błędy po Whisperze poprawił Bielik w ostatnim przebiegu EP002_Short."*
   - Agent odczytuje plik `work/EP002_Short/latest/02_transcription/02_bielik_cleanup_diff.md` i wyświetla tabelę zmian `Przed (Whisper) -> Po (Bielik)`.

---

## 6. Anatomia Plików Pośrednich i Produkcyjnych (Pełna Audytowalność)

Każdy przebieg w `work/<projekt>/latest/` zostawia kompletny ślad audytowy:

- **`01_source_extracted/`**:
  - `<ID>_VoiceOver_RAW_24k.wav` - wyekstrahowany strumień mowy z wideo.
- **`02_transcription/`**:
  - `01_whisper_raw_segments.json` / `.srt` - surowy wynik modelu Whisper przed jakąkolwiek ingerencją.
  - `02_bielik_cleaned_segments.json` / `.srt` - segmenty po korekcie fonetyki IT i interpunkcji przez Bielika.
  - `02_bielik_cleanup_diff.md` - czytelna tabela Markdown pokazująca dokładnie, które segmenty zmodyfikował Bielik.
  - `03_scenes_pl_grouped.json` / `.srt` - połączone pełne kwestie lektorskie (12-28s) gotowe do tłumaczenia.
- **`03_llm_adaptation/`**:
  - `04_translated_scenes_en.json` - przetłumaczone kwestie EN wraz z budżetem czasu i słów.
  - `04_pacing_calibration_log.json` - szczegółowy dziennik iteracji pętli Pacing Guardrail (liczba słów i sylab w każdej próbie).
  - `05_acting_directions.json` - wygenerowane przez Bielika instrukcje aktorskie (`instruct`) dla każdej sceny.
- **`04_tts_segments/`**:
  - `scene_XXX_raw_speaker.wav` - surowe nagranie aktora z `Qwen3-TTS 1.7B CustomVoice` (przed konwersją barwy).
  - `scene_XXX.wav` - docelowe nagranie sceny po konwersji barwy głosu przez `OpenVoice v2`.
- **`06_output/` (dostępne również bezpośrednio przez symlink `work/<projekt>/output/`)**:
  - `<ID>_VoiceOver_EN_CLEAN.wav` - zmasterowana ścieżka audio 48 kHz stereo (**-14.0 LUFS**, True Peak <= -1.0 dBFS) gotowa do wgrania w YouTube Studio (*Multi-Language Audio*).
  - `<ID>_FINAL_EN_DUBBED.mp4` - gotowy film z angielską ścieżką dźwiękową.
  - `<ID>_EN.srt` oraz `<ID>_PL.srt` - zsynchronizowane napisy końcowe.
  - `<ID>_Dubbing_Summary.md` oraz `../run_summary.json` - raport jakościowy (`QualityAnalyzer`).

---

## 7. Samodzielna Konfiguracja Słownika Fonetycznego ASR i Pojęć IT (`config/`)

Gdy Whisper błędnie usłyszy specjalistyczne pojęcie branżowe (np. fonetyczne *„AgentXsAdmin”* zamiast *„Agentic SysAdmin”* lub *„Quen”* zamiast *„Qwen”*), możesz samodzielnie rozszerzyć reguły korekty w dwóch plikach konfiguracyjnych w katalogu `config/`:

### A. Fonetyczne reguły Whisper ASR (`config/asr_corrections.json`)
Plik zawiera słownik wyrażeń regularnych (regex) mapowanych na docelowe, poprawne brzmienie. Reguły są stosowane deterministycznie przed i po czyszczeniu przez Bielika:

```json
{
  "\\bAgent[Xx]sAdmin\\b": "Agentic SysAdmin",
  "\\bAgent\\s+[Xx]sAdmin\\b": "Agentic SysAdmin",
  "\\bAgent\\s+[Xx]s\\s+Admin\\b": "Agentic SysAdmin",
  "\\bQuen\\b": "Qwen",
  "\\bQN3\\b": "Qwen3",
  "\\bkłen\\b": "Qwen",
  "\\bCustom Voice\\b": "CustomVoice",
  "\\bCadenLive\\b": "Kdenlive"
}
```
> [!TIP]
> Zawsze stosuj granice słów `\b`, aby uniknąć przypadkowego podmienienia fragmentów innych słów. W pliku JSON każdy ukośnik wsteczny musi być podwójny (`\\b`).

### B. Inżynierski słownik pojęć i tłumaczeń (`config/tech_terms.json`)
Słownik ten jest wstrzykiwany bezpośrednio do promptu systemowego modelu Bielik 11B podczas tłumaczenia i pacingu. Wymusza poprawne odpowiedniki terminów IT i zapobiega dosłownym, nieporadnym translacjom:

```json
{
  "Agentic SysAdmin": "Agentic SysAdmin",
  "AgentXsAdmin": "Agentic SysAdmin",
  "punkt montowania": "mount point",
  "narzut pamięci VRAM": "VRAM footprint",
  "szyna PCIe": "PCIe bus",
  "montaż cięty": "ripple edit",
  "ścieżka na osi czasu": "timeline track"
}
```

---

## 8. Protokół Ręcznej Korekty i Wznawiania (`FROM=translate|tts|master`)

Potok dubbingowy wspiera pełny przepływ **Human-in-the-Loop**. Jeśli chcesz skorygować wygenerowany tekst lub zmienić styl aktorski lektora, nie musisz uruchamiać całego procesu od zera:

```text
[Baza: work/<projekt>/latest/]
       │
       ├─► Edycja transkrypcji PL (03_scenes_pl_grouped.json)
       │         └─► make dub WORK=<projekt> FROM=translate
       │
       ├─► Edycja kwestii EN / acting instruction (05_acting_directions.json)
       │         └─► make dub WORK=<projekt> FROM=tts  (re-synteza TYLKO zmienionych scen!)
       │
       └─► Korekta masteringu / parametrów wideo
                 └─► make dub WORK=<projekt> FROM=master
```

### Scenariusz 1: Poprawka transkrypcji PL (`FROM=translate`)
1. Otwórz plik `work/<projekt>/latest/02_transcription/03_scenes_pl_grouped.json`.
2. Popraw błędy w polskim tekście (`text_pl`).
3. *(Opcjonalnie)* Zapisz zmodyfikowany plik w `work/<projekt>/input/03_scenes_pl_grouped.json`.
4. Uruchom:
   ```bash
   make dub WORK=<projekt> FROM=translate
   ```
   *Skrypt pobierze audio z etapu 1, wczyta Twoją poprawioną transkrypcję PL, przeprowadzi nowe tłumaczenie Bielikiem z Pacing Guardrail, wygeneruje instrukcje aktorskie, zsyntetyzuje mowę i zmasteruje wideo w nowym katalogu `runs/`.*

### Scenariusz 2: Korekta kwestii EN lub instrukcji aktorskiej (`FROM=tts`)
1. Otwórz plik `work/<projekt>/latest/03_llm_adaptation/05_acting_directions.json`.
   Przykładowa zawartość:
   ```json
   {
     "scene_001": {
       "text": "What if autonomous agents could manage entire Linux servers?",
       "instruction": "Speak with confident engineering authority and calm pacing."
     },
     "scene_002": {
       "text": "Wait, let's look under the hood right now.",
       "instruction": "Start with sudden energetic curiosity, pause briefly, then speak with clear focus."
     }
   }
   ```
2. Zmodyfikuj angielski tekst (`text`) lub instrukcję reżyserską (`instruction`) dla wybranej sceny.
3. *(Opcjonalnie)* Zapisz zmodyfikowany plik w `work/<projekt>/input/05_acting_directions.json`.
4. Uruchom:
   ```bash
   make dub WORK=<projekt> FROM=tts
   ```
   *Dzięki wbudowanym markerom cache (`.txt` oraz `.instr`):*
   - Sceny, których tekst i instrukcja **nie uległy zmianie**, zostaną natychmiast załadowane z pamięci podręcznej (`cache hit`),
   - **Tylko zmodyfikowane sceny** zostaną ponownie zsyntetyzowane przez model `Qwen3-TTS 1.7B CustomVoice` i przetworzone przez `OpenVoice v2`,
   - Całość zostanie na nowo zsynchronizowana i zmasterowana w kilka sekund zamiast kilku minut!

---

## 9. Zabezpieczenia Pacingu i Eliminacja Dryfu Czasu (Shorts)

W krótkich formach wideo (YouTube Shorts / TikTok / Reels) tolerancja na rozjazd czasowy wynosi **0 sekund** – lektor nie może nachodzić na cięcia montażowe ani wykraczać poza koniec filmu. Aby to zagwarantować, w potoku zaimplementowano 4 twarde mechanizmy obronne:

1. **Kalibracja Benchmarku Tempa Mowy (WPS = 2.35):**
   Głos `Ryan` w Qwen3-TTS mówi z naturalną prędkością ~138–142 WPM (2.30–2.35 słowa na sekundę). Pętla Pacing Guardrail w Bieliku przyjmuje ten benchmark jako twardy budżet, uniemożliwiając generowanie zbyt długich zdań.
2. **Adaptacyjne Chunkowanie (Shorts vs Long):**
   Dla materiałów $\le 120$ s kwestie dzielone są na odcinki 2.5–7.5 s na kropkach i pauzach $\ge 0.7$ s. Zapobiega to kumulacji opóźnień między cięciami wideo.
3. **Elastyczna Kompresja WSOLA (`atempo` do 1.25x):**
   Jeśli wygenerowana kwestia jest nieco dłuższa niż nominalne okno wideo, silnik FFmpeg automatycznie kompresuje czas mowy bez zmiany wysokości głosu (`pitch-neutral`).
4. **Twardy Strażnik Outro i Ostateczne Przycięcie (`afade`):**
   Finałowa kwestia ma twardą rezerwę co najmniej 0.25 s czystego outro przed końcem filmu. Jeśli mowa lektora przekracza dostępny czas, zostaje automatycznie skompresowana (do 1.30x) oraz miękko wyciszona (`afade 150ms`). Końcowy plik audio WAV jest twardo przycięty flagą `-t {total_duration}`, co gwarantuje 100% zgodności co do milisekundy.
