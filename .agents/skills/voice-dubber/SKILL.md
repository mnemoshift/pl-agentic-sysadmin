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
* **Prompt użytkownika:** `Przetłumacz i zdubbinguj shorta w work/EP002_Short z zachowaniem standardu -14 LUFS.`
* **Działanie Agenta:**
  1. Weryfikuje obecność wideo źródłowego w `work/EP002_Short/input/` (`EP002_Short_Agentic_SysAdmin_Karaoke_FIXED.mp4`) oraz próbki głosu w `work/voice_sample/`.
  2. Uruchamia `scripts/media/dub_short.py -w work/EP002_Short`.
  3. Skrypt realizuje:
     - Ekstrakcję audio z wideo.
     - Parsowanie scenariusza `short_script.md` ze słownikiem technicznym IT.
     - Inżynierskie tłumaczenie terminów IT (*mount point*, *VRAM footprint*, *PCIe bus*, *macOS-inspired desktop*).
     - Syntezę segmentów mowy na GPU (Breeze-TTS-2 klonem głosu lub fallback) z próbką referencyjną.
     - Wyrównanie czasowe (time-syncing pod cięcia) i mastering do -14 LUFS (EBU R128).
     - Złożenie gotowego zduplikowanego pliku wideo `assets/EP002_Short_FINAL_EN_DUBBED.mp4`.
  4. Wyświetla w czacie Antigravity tabelę porównawczą A/B (PL vs EN) i raportuje gotowe pliki.

### Krok 3: Dubbing drugiego shorta (EP001 Short - Zestaw wideo)
* **Prompt użytkownika:** `Zdubbinguj teraz drugi materiał w work/EP001_Short.`
* **Działanie Agenta:**
  1. Weryfikuje obecność wideo w `work/EP001_Short/input/` (`EP001_Short_WSL_vs_Zorin_FINAL.mp4`) oraz pliku `.srt`.
  2. Uruchamia `scripts/media/dub_short.py -w work/EP001_Short`.
  3. Prezentuje podsumowanie wygenerowanych plików i potwierdza pełną skalowalność potoku na zestawie wideo.
