# Voice Reference Samples Guide (`voice/` & `work/voice_sample/`)

Centrum konfiguracji i wytycznych dla próbek głosu lektora do lokalnego klonowania mowy zero-shot (`Breeze-TTS-2`, `KokoClone / Kanade`, `Qwen-TTS`, `Chatterbox`).

---

## 1. Prywatność i Bezpieczeństwo Biometryczne (Open-Source Policy)

> [!IMPORTANT]
> **Repozytorium publiczne nie zawiera żadnych prywatnych próbek audio lektora.**
> Wszelkie próbki głosu stanowią dane biometryczne i podlegają bezwzględnej ochronie prywatności.

- Wszystkie nagrania audio lektora przechowywane są lokalnie w katalogu `work/voice_sample/`.
- Cały katalog `work/` jest objęty regułą w `.gitignore` i **nigdy nie trafia do zdalnego repozytorium Git**.

---

## 2. Konwencja Lokalizacji i Wybór Próbki w Skryptach

Wszystkie skrypty potoku mediów (`dub_video.py`, `generate_voiceover.py`, `Makefile`) korzystają z ustandaryzowanej konwencji:

1. **Jeden plik w `work/voice_sample/`**:
   - Jeżeli w katalogu znajduje się dokładnie **jeden** plik audio (`.wav`), jest on automatycznie wybierany jako domyślny wzorzec lektorski — bez względu na jego nazwę.
2. **Wiele plików w `work/voice_sample/`**:
   - Jeżeli w katalogu znajduje się więcej niż jedna próbka, skrypt **wymaga** wskazania pożądanej próbki parametrem CLI:
     ```bash
     python scripts/media/dub_video.py --voice-ref ref_voice_sample.wav ...
     ```
     lub poprzez zmienną środowiskową:
     ```bash
     export VOICE_REF_FILE=work/voice_sample/ref_voice_sample.wav
     ```
   - Jeśli parametr nie zostanie podany lub wskazuje nieistniejący plik, wykonanie skryptu zostaje przerwane z czytelnym komunikatem i listą wszystkich dostępnych próbek.
3. **Brak plików w `work/voice_sample/`**:
   - Skrypt zgłasza błąd z instrukcją nagrania i umieszczenia próbki.

---

## 3. Jak Przygotować Własną Próbkę Głosu?

Aby uzyskać studyjną jakość klonowania mowy bez artefaktów i zniekształceń:

### A. Wymagania techniczne pliku audio
- **Format:** PCM 16-bit WAV (`pcm_s16le`, `.wav`).
- **Częstotliwość próbkowania:** 24 000 Hz lub 48 000 Hz (modele wewnętrznie resamplują do natywnych 24kHz).
- **Kanały:** 1 (Mono).
- **Długość fragmentu:** 10–15 sekund czystej, nieprzerwanej mowy (bez długich przerw, muzyki w tle, szumów tła czy kliknięć ust).
- **Normalizacja:** `-17.4 LUFS` do `-14.0 LUFS` (zgodnie ze standardem EBU R128).

### B. Opcjonalny plik transkrypcji (`.txt`)
Wraz z plikiem `.wav` warto umieścić plik tekstowy o identycznej nazwie bazowej (np. `my_voice.txt`), zawierający dokładny zapis wypowiedzianego tekstu. Pozwala to modelom zero-shot na idealną synchronizację fonetyczną.

### C. Ekstrakcja próbki z istniejącego nagrania (Makefile)
Możesz wyciąć wzorcowy fragment bezpośrednio z nagranego wideo lub audio za pomocą wbudowanego narzędzia:
```bash
make media-extract-sample \
  INPUT=work/raw_recording.mp4 \
  START=00:00:15.000 \
  END=00:00:27.500 \
  OUTPUT=work/voice_sample/my_voice.wav \
  TRANSCRIPT="Cześć! Dzisiaj konfigurujemy stację roboczą dla agentów AI."
```
