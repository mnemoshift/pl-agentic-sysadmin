---
name: voice-dubber
description: Autonomiczny potok lokalnego dubbingu i generowania lektora (Shorts, długie wideo/epizody oraz skrypty Markdown) z wykorzystaniem modeli AI (Whisper large-v3-turbo, Bielik 11B v3.0 Instruct, Qwen3-TTS 1.7B CustomVoice + OpenVoice v2 Timbre Converter, Qwen3-TTS Base, KokoClone, Chatterbox, Breeze-TTS-2, Edge-TTS) na GPU RTX. Używaj ZAWSZE, gdy użytkownik zleca: wycięcie próbki głosu, dubbing wideo (np. w work/<podfolder>), syntezę głosu konkretnym silnikiem, test Acting Direction lub generowanie polskiego voiceoveru z pliku .md.
---

# Voice Dubber Skill (Workstation Hub Sovereign Audio Pipeline)

Skill dostarcza w pełni zautomatyzowane, powtarzalne procedury lokalnego dubbingu oraz generowania lektora w izolowanej strukturze `work/<projekt>/` na stacji roboczej Linux (Zorin OS) z kartą NVIDIA RTX.

---

## ŻELAZNA REGUŁA AGENTA: ZERO-TOKEN OVERHEAD (BEZPOŚREDNIE WYKONANIE)

> [!IMPORTANT]
> **KATEGORYCZNY ZAKAZ CRAWLINGU KODU I BADAŃ IMPORTÓW:**
> Gdy użytkownik wydaje polecenie dubbingu lub syntezy (np. *"Zdubbinguj materiał w work/EP002_Short"* lub *"Zdubbinguj wideo w podfolderze moj_film"*), **NATYCHMIAST uruchom dedykowaną komendę `make dub` w terminalu**.
> - **NIE** czytaj plików źródłowych w `scripts/media/` ani `tools/`.
> - **NIE** sprawdzaj wersji bibliotek w `site-packages` ani nie wykonuj `python -c "import ..."`.
> - **NIE** szukaj grepem implementacji silników.
> Komendy `make dub` są samowystarczalnymi czarnymi skrzynkami z wbudowaną obsługą błędów, wersjonowaniem przebiegów i automatycznym zwalnianiem VRAM.

---

## 1. Konwencja Katalogu `work/<projekt>/`

Każdy dubbingowany materiał posiada własny podfolder w `work/<projekt>/`, co chroni przed nadpisaniem plików:
- `work/<projekt>/input/` - wejściowy plik `.mp4` (oraz opcjonalnie czysta ścieżka `.wav` lub dedykowana próbka `ref_voice*.wav`).
- `work/<projekt>/output/` - automatyczny symlink do gotowych plików produkcyjnych najnowszego przebiegu (`06_output/`).
- `work/<projekt>/latest/` - automatyczny symlink do pełnego katalogu ostatniego przebiegu ze wszystkimi plikami pośrednimi (`01_source_extracted` .. `06_output`).
- `work/<projekt>/runs/` - niemutowalna historia wszystkich przebiegów (`YYYY-MM-DD_HH-MM-SS_<engine>_<projekt>`).
- `work/voice_sample/` - domyślna globalna pula próbek referencyjnych głosu autora (`ref_voice_sample_en.wav`, `ref_voice_sample.wav`).

---

## 2. Tabela Intencji i Gotowe Polecenia CLI (`make`)

| Intencja / Prompt użytkownika | Polecenie CLI do natychmiastowego uruchomienia |
| :--- | :--- |
| **Domyślny dubbing materiału w podfolderze `work/<projekt>`:**<br>`Przetłumacz i zdubbinguj materiał w EP002_Short` | `make dub WORK=EP002_Short` |
| **Wznowienie potoku od etapu tłumaczenia (po edycji PL w 03_scenes_pl_grouped.json):**<br>`Wznów dubbing od tłumaczenia po poprawieniu transkrypcji` | `make dub WORK=EP002_Short FROM=translate` |
| **Wznowienie potoku od syntezy TTS (po edycji kwestii EN lub instrukcji aktorskich):**<br>`Wznów syntezę TTS dla EP002_Short po zmianie acting directions` | `make dub WORK=EP002_Short FROM=tts` *(re-syntezuje TYLKO zmienione sceny!)* |
| **Wznowienie potoku od masteringu EBU R128 i muxingu MP4:**<br>`Wznów mastering dla EP002_Short` | `make dub WORK=EP002_Short FROM=master` |
| **Wymuszenie podziału na krótkie kwestie (Shorts / 2.5-7.5s):**<br>`Zdubbinguj film wymuszając krótkie sceny pod napisy` | `make dub WORK=EP002_Short CHUNKS=short` |
| **Inicjalizacja nowego projektu z zewnętrznym plikiem MP4 i dubbing:**<br>`Zdubbinguj plik /sciezka/wideo.mp4 w folderze nowy_klip` | `make dub WORK=nowy_klip INPUT=/sciezka/wideo.mp4` |
| **Dubbing z wyborem alternatywnego silnika TTS:**<br>`Zdubbinguj EP002_Short używając czystego modelu Qwen Base / Kokoro / Chatterbox` | `make dub WORK=EP002_Short ENGINE=qwen-base`<br>`make dub WORK=EP002_Short ENGINE=kokoro`<br>`make dub WORK=EP002_Short ENGINE=chatterbox` |
| **Wyłącznie transkrypcja Whisper + korekta Bielik + tłumaczenie i napisy SRT:**<br>`Przygotuj tylko transkrypcję i napisy PL/EN dla EP002_Short` | `make dub-transcribe WORK=EP002_Short` |
| **Sprawdzenie statusu projektów i próbek głosu w `work/`:**<br>`Pokaż status projektów dubbingowych w work` | `make dub-status` |
| **Test porównawczy Acting Direction + Timbre Transfer (3 kroki):**<br>`Przetestuj Qwen CustomVoice z acting direction i moją barwą głosu` | `make media-test-acting` |
| **Wycięcie próbki referencyjnej głosu:**<br>`Wytnij 8s próbkę z nagrania od 00:12 do 00:20` | `make media-extract-sample INPUT=work/source.wav START=00:00:12.000 END=00:00:20.300 OUTPUT=work/voice_sample/ref_voice_sample.wav` |
| **Czysty reset wygenerowanych przebiegów (zachowuje `input/` i `voice_sample/`):**<br>`Wyczyść wygenerowane artefakty dubbingu` | `make media-dub-clean` |

---

## 3. Domyślny Potok Docelowy i Obsługiwane Silniki (`ENGINE=...`)

Domyślnym silnikiem (`ENGINE=qwen`) jest wypracowana architektura hybrydowa łącząca reżyserię aktorską z klonowaniem barwy głosu na licencjach komercyjnych (Apache 2.0 + MIT):

1. `ENGINE=qwen` *(domyślny)*: **Qwen3-TTS 1.7B CustomVoice (Apache 2.0) + OpenVoice v2 Tone Color Converter (MIT)**.
   - Model `CustomVoice` realizuje pełne instrukcje reżyserskie (`Acting Direction` wygenerowane przez Bielika 11B), po czym `OpenVoice v2` przekształca barwę głosu aktora na barwę próbki referencyjnej użytkownika z `work/voice_sample/`.
   - W `04_tts_segments/` zachowywane są zarówno surowe pliki aktora (`scene_XXX_raw_speaker.wav`), jak i pliki po konwersji barwy (`scene_XXX.wav`).
2. `ENGINE=qwen-base`: **Qwen3-TTS 0.6B Base (Apache 2.0)** - bezpośredni zero-shot voice clone z próbki audio (bez CustomVoice i bez OpenVoice v2).
3. `ENGINE=kokoro`: **KokoClone** (Kokoro-ONNX + Kanade Voice Conversion, Apache 2.0 / MIT).
4. `ENGINE=chatterbox`: **Chatterbox-Turbo** (MIT).
5. `ENGINE=breeze`: **Breeze-TTS-2** (Zero-shot + instruct, CC-BY-NC - wyłącznie do badań niekomercyjnych).
6. `ENGINE=edge`: **Edge-TTS** (Microsoft Neural Voices) - szybki podgląd bez obciążania GPU.

---

## 4. Sekwencyjny Potok Wykonawczy (6 Etapów z Artefaktami Pośrednimi)

Każdy przebieg w `work/<projekt>/latest/` zapisuje pełen zestaw artefaktów pośrednich:
1. **`01_source_extracted/`**: Ekstrakcja czystego audio lektorskiego 24 kHz mono WAV.
2. **`02_transcription/`**:
   - `01_whisper_raw_*`: Surowy zrzut segmentów ASR z `faster-whisper large-v3-turbo`.
   - `02_bielik_cleaned_*` + `02_bielik_cleanup_diff.md`: Inżynierska korekta błędów fonetycznych IT i interpunkcji przez model **Bielik 11B v3.0 Instruct** wraz z tabelą porównawczą Diff (`Przed -> Po`).
   - `03_scenes_pl_grouped_*`: Podział oczyszczonego tekstu na spójne kwestie logiczne (12-28s).
3. **`03_llm_adaptation/`**:
   - `04_translated_scenes_en_*` + `04_pacing_calibration_log.json`: Adaptacja PL -> EN przez **Bielik 11B** z pętlą sprzężenia zwrotnego **Pacing Guardrail** (kontrola budżetu sylab i słów w oknie czasowym) oraz słownikiem `config/tech_terms.json`.
   - `05_acting_directions.json`: Instrukcje reżyserskie (`Acting Direction`) wygenerowane przez Bielika dla każdej sceny przed zwolnieniem pamięci VRAM (`keep_alive: 0`).
4. **`04_tts_segments/`**: Synteza mowy `Qwen3-TTS 1.7B CustomVoice` (`scene_XXX_raw_speaker.wav`) + transfer barwy głosu `OpenVoice v2` (`scene_XXX.wav`).
5. **`05_subtitles/`**: Zsynchronizowane napisy `.srt` w języku polskim i angielskim.
6. **`06_output/`** (podlinkowane jako `work/<projekt>/output/`):
   - `<ID>_VoiceOver_EN_CLEAN.wav` - zmasterowany lektor EN (48 kHz stereo, **EBU R128 -14.0 LUFS**, True Peak <= -1.0 dBFS, Room Tone -58 dB).
   - `<ID>_FINAL_EN_DUBBED.mp4` - gotowe wideo z podmienioną angielską ścieżką audio.
   - `<ID>_EN.srt` oraz `<ID>_PL.srt` - finalne napisy zsynchronizowane co do milisekundy.
   - `<ID>_Dubbing_Summary.md` oraz `run_summary.json` - raport audytu jakościowego (`QualityAnalyzer`: WPM, dryf czasu, Peak/RMS dB).
