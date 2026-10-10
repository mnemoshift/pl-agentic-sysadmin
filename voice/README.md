# Sovereign Voice Reference Samples (`voice/`)

Katalog zawierający studyjne wzorce głosu lektora (Jarek) do lokalnego klonowania głosu (zero-shot voice cloning) w modelach TTS (`Qwen3-TTS`, `Kokoro / Kanade`, `Chatterbox-Turbo`, `Breeze-TTS`).

---

## 1. Dostępne Próbki Referencyjne

| Plik audio | Plik transkrypcji | Język | Czas trwania | Zintegrowana głośność | Przeznaczenie |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `jarek_clean_reference.wav` | `jarek_clean_reference.txt` | **PL** | 8.30s | **-17.4 LUFS** | Lektor w języku polskim (voiceover z Markdowna, klonowanie PL). |
| `jarek_en_reference.wav` | `jarek_en_reference.txt` | **EN** | 13.80s | **-17.4 LUFS** | Autonomiczny dubbing i voiceover w języku angielskim. |

---

## 2. Dlaczego Dedykowany Wzorzec EN?

Podczas wielojęzycznego klonowania głosu (np. `Qwen3-TTS-Base`, `CosyVoice`) z polskiego wzorca lektorskiego, model przenosi nie tylko barwę głosu, ale również polską fonetykę i rytmikę (wschodnioeuropejski akcent).

Nagranie wzorca `jarek_en_reference.wav` w języku angielskim przez Jarka pozwala modelowi:
1. Zachować autentyczną barwę i tembr głosu inżyniera.
2. Zastosować natywną dla języka angielskiego artykulację i kadencję.
3. Całkowicie wyeliminować twardy, wschodni akcent w anglojęzycznych renderach YouTube i Shorts.

---

## 3. Parametry Techniczne Audio

- **Format:** PCM 16-bit (`pcm_s16le`), WAV
- **Częstotliwość próbkowania:** 24 000 Hz (standard natywny dla tokenizera audio w Qwen3-TTS i modelach zero-shot)
- **Kanały:** 1 (Mono)
- **Normalizacja:** Studyjna EBU R128 (`-17.4 LUFS`, True Peak `-1.0 dBFS`)
- **Stosunek sygnału do szumu (SNR):** > 54 dB (tor mikrofonowy Shure MV7 / OBS Studio)

---

## 4. Aliasy i Kompatybilność Wsteczna

Dla zachowania pełnej zgodności z istniejącymi skryptami montażowymi utworzono symlinki:
- `ref_voice_sample.wav` ➔ `jarek_clean_reference.wav`
- `ref_voice_sample.txt` ➔ `jarek_clean_reference.txt`
- `ref_voice_sample_en.wav` ➔ `jarek_en_reference.wav`
- `ref_voice_sample_en.txt` ➔ `jarek_en_reference.txt`
