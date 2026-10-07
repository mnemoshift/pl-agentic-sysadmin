---
name: voice-dubber
description: Autonomiczny potok lokalnego dubbingu zestawu wideo (Shorts i screencasty) z wykorzystaniem modeli AI (Whisper, Breeze-TTS-2, Kokoro, Edge-TTS) na GPU bez zewnętrznych API. Używaj, gdy użytkownik zleca wycięcie próbki referencyjnej głosu ze wskazanego źródła, przetłumaczenie materiału z zachowaniem słownika inżynierskiego IT, zsynchronizowanie ścieżki lektorskiej z wideo lub wygenerowanie zdubbingowanego zestawu materiałów wideo zgodnych ze standardem emisyjnym YouTube (-14 LUFS).
---

# Voice Dubber Skill (Workstation Hub Sovereign Audio Pipeline)

Skill dostarcza w pełni zautomatyzowane, powtarzalne procedury lokalnego dubbingu i syntezy mowy dla zestawu materiałów wideo w katalogu roboczym `work/` na stacji roboczej Linux (Zorin OS) z kartą NVIDIA RTX. Wszystkie materiały użytkownika pozostają wyłącznie w `work/` z zachowaniem 100% prywatności biometrii głosu.

---

## 1. Dostępne Moduły i Interfejs Operacyjny

Wszystkie operacje są realizowane przez moduły w `scripts/media/` oraz dedykowane cele w `Makefile`:

```bash
# 1. Ekstrakcja próbki referencyjnej głosu (Voice Cloning Sample):
python3 scripts/media/extract_voice_sample.py \
  -i work/voice_source/EP003_VoiceOver_CLEAN.wav \
  -s 00:00:12.000 -e 00:00:20.300 \
  -o work/voice_sample/ref_voice_sample.wav \
  -t "Zmontowałem to w całości lokalnie na Linuksie, rozmawiając z agentem AI w naszym repozytorium, ani razu nie dotknąłem myszki."
# lub: make media-extract-sample INPUT=work/voice_source/EP003_VoiceOver_CLEAN.wav START=00:00:12.000 END=00:00:20.300 OUTPUT=work/voice_sample/ref_voice_sample.wav

# 2. Dubbing pierwszego shorta (Główne studium przypadku - EP002):
python3 scripts/media/dub_short.py -w work/EP002_Short
# lub: make media-dub-ep002

# 3. Dubbing drugiego shorta (Skalowanie na zestaw wideo - EP001):
python3 scripts/media/dub_short.py -w work/EP001_Short
# lub: make media-dub-ep001

# 4. Przetwarzanie wsadowe zestawu wideo:
python3 scripts/media/dub_short.py --batch work/EP002_Short work/EP001_Short
# lub: make media-dub-batch

# 5. Czysty reset środowiska przed nagraniem:
make media-dub-clean
```

---

## 2. Standard Wykonawczy dla Jednozdaniowych Promptów

Agent interpretuje zwięzłe polecenia użytkownika i automatycznie realizuje poszczególne etapy potoku:

### Krok 1: Wycięcie próbki referencyjnej głosu
* **Prompt użytkownika:** `Wytnij 8-sekundową próbkę głosu z nagrania w work/voice_source od 00:12 do 00:20.`
* **Działanie Agenta:**
  1. Lokalizuje plik źródłowy w `work/voice_source/` (np. `EP003_VoiceOver_CLEAN.wav`).
  2. Wywołuje `scripts/media/extract_voice_sample.py` z parametrami `-s 00:00:12.000 -e 00:00:20.300`.
  3. Zapisuje bezstratną próbkę studyjną (24kHz mono WAV) w `work/voice_sample/ref_voice_sample.wav` wraz z plikiem tekstowym transkrypcji `.txt`.
  4. Raportuje gotowość próbki lektora do klonowania.

### Krok 2: Dubbing pierwszego shorta (EP002 Short)
* **Prompt użytkownika:** `Przetłumacz i zdubbinguj shorta w work/EP002_Short.`
* **Działanie Agenta:**
  1. Weryfikuje obecność wideo źródłowego w `work/EP002_Short/input/` (`EP002_Short_Agentic_SysAdmin_Karaoke_FIXED.mp4`) oraz próbki głosu w `work/voice_sample/`.
  2. Uruchamia `scripts/media/dub_short.py -w work/EP002_Short`.
  3. Skrypt realizuje automatycznie:
     - Ekstrakcję audio z wideo.
     - Parsowanie scenariusza `short_script.md` ze słownikiem technicznym IT.
     - Inżynierskie tłumaczenie terminów IT (*mount point*, *VRAM footprint*, *PCIe bus*, *macOS-inspired desktop*).
     - Syntezę segmentów mowy na GPU (Breeze-TTS-2 klonem głosu lub fallback) z próbką referencyjną.
     - Wyrównanie czasowe (time-syncing pod cięcia) i mastering do broadcastowego standardu YouTube (**-14.0 LUFS**, True Peak $\le$ -1.0 dBFS).
     - Dostarczenie **dwóch plików produkcyjnych**:
       - `assets/EP002_Short_VoiceOver_EN_CLEAN.wav` (alternatywna ścieżka językowa pod YouTube Multi-Language Audio).
       - `assets/EP002_Short_FINAL_EN_DUBBED.mp4` (pełne wideo EN: obraz + zdubbingowana ścieżka dźwiękowa).
  4. Wyświetla w czacie tabelę porównawczą A/B (PL vs EN) oraz podsumowanie plików.

### Krok 3: Odsłuch i weryfikacja
* **Prompt użytkownika:** `Odtwórz wygenerowane wideo dla EP002 i podsumuj parametry audio.`
* **Działanie Agenta:** Uruchamia odtwarzacz wideo z wygenerowanym plikiem i raportuje zmierzoną głośność (-14 LUFS, True Peak).

---

## 3. Tryb One-Shot („Na Raz” dla EP001 Short)

Użytkownik zleca wykonanie całego potoku w jednym poleceniu czystej intencji (bez podawania flag CLI ani parametrów technicznych):

* **Prompt użytkownika:** `Zdubbinguj materiał w work/EP001_Short przy użyciu przygotowanej próbki głosu i odtwórz gotowe wideo.`
* *(lub od zera bez wcześniejszej próbki):* `Wytnij 8-sekundową próbkę głosu z work/voice_source od 00:12 do 00:20 i zdubbinguj materiał w work/EP001_Short.`
* **Działanie Agenta:**
  1. Spina cały workflow bez pytań pomocniczych.
  2. Ekstrahuje i tłumaczy 19 segmentów wypowiedzi z pliku `.srt`.
  3. Syntezuje mowę na GPU i masteruje do -14 LUFS.
  4. Zapisuje oba pliki produkcyjne w `work/EP001_Short/assets/`:
     - `EP001_Short_VoiceOver_EN_CLEAN.wav` (dla YouTube Multi-Language Audio),
     - `EP001_Short_FINAL_EN_DUBBED.mp4` (pełny film EN z dubbingiem).
  5. Uruchamia podgląd wideo.

---

## 4. Wygenerowane Pliki Produkcyjne (Standard Emisyjny)

Dla każdego projektu w katalogu `work/<ID>/assets/` powstają:
1. **Alternatywna ścieżka audio (YouTube MLA):** `<ID>_VoiceOver_EN_CLEAN.wav` (WAV 48kHz stereo, -14.0 LUFS, True Peak $\le$ -1.0 dBFS) — do bezpośredniego wgrania w YouTube Studio jako dodatkowa ścieżka językowa do istniejącego filmu.
2. **Pełne wideo z dubbingiem EN:** `<ID>_FINAL_EN_DUBBED.mp4` (wideo + dubbing EN) — gotowy film do publikacji na zagranicznym kanale lub Shorts.
3. **Transkrypcja i raport:** `<ID>_Dubbing_Transcript_EN.json` oraz `<ID>_Dubbing_Summary.md` (tabela A/B scen PL vs EN).

---

## 5. Materiały Długie i Walidacja Referencyjna (`work/EP002`)

Dla pełnometrażowych materiałów (np. `work/EP002`, 12:08):
* Gdy w `input/` brak pliku scenariusza (`.md` / `.srt`), potok automatycznie uruchamia silnik Whisper na ścieżce `EP002_VoiceOver_CLEAN.wav` lub wyekstrahowanym audio z filmu.
* W folderze `work/EP002/input/reference/` przechowywana jest wersja zmontowana w chmurze (`EP002_Audio_EN_ElevenLabs_14LUFS.mp3` oraz `EP002_FINAL_EN_ElevenLabs.mp4`), służąca do natychmiastowego odsłuchu i porównania A/B jakości oraz bilansu ekonomicznego (0 zł vs spalony limit tokenów).
