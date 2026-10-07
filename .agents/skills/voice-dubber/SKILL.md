---
name: voice-dubber
description: Autonomiczny potok lokalnego dubbingu wideo (Shorts i screencasty) z wykorzystaniem modeli AI (Whisper, Breeze-TTS-2, Kokoro, Edge-TTS) na GPU bez zewnętrznych API. Używaj, gdy użytkownik zleca wycięcie próbki referencyjnej głosu, przetłumaczenie materiału z zachowaniem słownika inżynierskiego IT, zsynchronizowanie ścieżki lektorskiej z wideo lub wygenerowanie zdubbingowanego pliku wideo zgodnego ze standardem emisyjnym YouTube (-14 LUFS).
---

# Voice Dubber Skill (Workstation Hub Sovereign Audio Pipeline)

Skill dostarcza w pełni zautomatyzowane, powtarzalne procedury lokalnego dubbingu i syntezy mowy dla materiałów wideo w katalogu roboczym `work/` na stacji roboczej Linux (Zorin OS) z kartą NVIDIA RTX. Wszystkie materiały użytkownika pozostają wyłącznie w `work/` z zachowaniem 100% prywatności biometrii głosu.

---

## 1. Dostępne Moduły i Interfejs Operacyjny

Wszystkie operacje są realizowane przez moduły w `scripts/media/` oraz dedykowane cele w `Makefile`:

```bash
# 1. Ekstrakcja próbki referencyjnej głosu (Voice Cloning Sample):
python3 scripts/media/extract_voice_sample.py \
  -i work/voice_source/nagranie.wav \
  -s 00:00:12.000 -e 00:00:20.300 \
  -o work/voice_sample/ref_voice_sample.wav \
  -t "Transkrypcja referencyjna wypowiedzi..."

# 2. Autonomiczny dubbing i mastering shorta (np. EP002):
python3 scripts/media/dub_short.py \
  -i work/EP002_Short/input/EP002_Short_Agentic_SysAdmin.mp4 \
  -w work/EP002_Short \
  --ref-audio work/voice_sample/ref_voice_sample.wav

# 3. Dubbing przez cel Makefile:
make media-dub SHORT=EP002_Short
```

---

## 2. Standard Wykonawczy dla Jednozdaniowych Promptów

Agent interpretuje zwięzłe polecenia użytkownika i automatycznie realizuje poszczególne etapy potoku:

### Krok 1: Ekstrakcja próbki referencyjnej głosu
* **Prompt użytkownika:** `Wytnij 8-sekundową próbkę głosu z nagrania w work/voice_source od 00:12 do 00:20.`
* **Działanie Agenta:**
  1. Lokalizuje plik źródłowy w `work/voice_source/` (lub wskazanym katalogu `work/`).
  2. Wywołuje `scripts/media/extract_voice_sample.py` z parametrami `-s 00:00:12.000 -e 00:00:20.300`.
  3. Zapisuje bezstratną próbkę studyjną (24kHz mono WAV) w `work/voice_sample/ref_voice_sample.wav` wraz z plikiem tekstowym transkrypcji `.txt`.
  4. Raportuje gotowość próbki lektora do klonowania.

### Krok 2: Tłumaczenie inżynierskie i dubbing materiału
* **Prompt użytkownika:** `Przetłumacz i zdubbinguj shorta w work/EP002_Short z zachowaniem standardu -14 LUFS.`
* **Działanie Agenta:**
  1. Weryfikuje obecność wideo źródłowego w `work/EP002_Short/input/` oraz próbki głosu w `work/`.
  2. Uruchamia `scripts/media/dub_short.py -i work/EP002_Short/input/... -w work/EP002_Short`.
  3. Skrypt realizuje:
     - Ekstrakcję audio z wideo.
     - Parsowanie scenariusza `short_script.md` lub automatyczną transkrypcję `faster-whisper`.
     - Inżynierskie tłumaczenie terminów IT (*mount point*, *VRAM footprint*, *PCIe bus*, *macOS-inspired desktop*).
     - Syntezę segmentów mowy na GPU (Breeze-TTS-2 klonem głosu lub fallback).
     - Wyrównanie czasowe (time-syncing pod cięcia) i mastering do -14 LUFS (EBU R128).
     - Złożenie gotowego zduplikowanego pliku wideo `assets/EP002_Short_FINAL_EN_DUBBED.mp4`.
  4. Wyświetla w czacie Antigravity tabelę porównawczą A/B (PL vs EN) i raportuje gotowe pliki.

### Krok 3: Odsłuch i weryfikacja
* **Prompt użytkownika:** `Odtwórz rezultat i porównaj fragment z polskim oryginałem.`
* **Działanie Agenta:**
  1. Prezentuje parametry audio (głośność LUFS, True Peak).
  2. Odtwarza pierwsze 5 sekund wideo/audio za pomocą `mpv` lub udostępnia link do podglądu pliku.
