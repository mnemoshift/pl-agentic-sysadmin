# Walkthrough: Suwerenny Potok Dubbingu i Voiceoveru AI na GPU (Shorts)

Procedura automatycznego tłumaczenia, syntezy mowy i masteringu audio dla formatów YouTube Shorts (format pionowy 9:16) bez zewnętrznych API i opłat chmurowych.

---

## 1. Architektura i Bilans Pamięci VRAM (RTX 4060 Ti 16GB)

Przepustowość wewnętrznej pamięci GDDR6 karty graficznej wynosi **288 GB/s**, podczas gdy magistrala PCIe 4.0 x8 oferuje zaledwie **~12 GB/s** (proporcja **24:1**). 

Przekroczenie budżetu 16.0 GB VRAM powoduje natychmiastowe zrzucanie danych do systemowego RAM-u przez wąskie gardło magistrali i katastrofalny spadek wydajności. Dlatego potok audio został zaprojektowany z twardym marginesem bezpieczeństwa:

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

## 2. Dostępne Moduły w `scripts/media/`

* `scripts/media/extract_voice_sample.py` – precyzyjne wycięcie 3–10 sekundowej próbki referencyjnej mowy z nagrania źródłowego w `work/`.
* `scripts/media/dub_short.py` – kompletny orkiestrator potoku:
  1. Ekstrakcja audio z wideo źródłowego (WAV 24kHz mono).
  2. Parsowanie scenariusza (`short_script.md` / `.srt`) lub automatyczna transkrypcja Whisper.
  3. Inżynierskie tłumaczenie terminów IT z dopasowaniem do okna czasowego.
  4. Synteza mowy na GPU (Breeze-TTS-2 lub lekki fallback).
  5. Time-syncing, wstawianie pauz i mastering do standardu **-14 LUFS** (EBU R128).
  6. Wygenerowanie gotowego pliku wideo z angielską ścieżką dźwiękową.

---

## 3. Przykładowy Przebieg Operacyjny

### Krok 1: Wycięcie próbki głosu
```bash
python3 scripts/media/extract_voice_sample.py \
  -i work/voice_source/EP003_VoiceOver_CLEAN.wav \
  -s 00:00:12.000 -e 00:00:20.300 \
  -o work/voice_sample/ref_voice_sample.wav \
  -t "Zmontowałem to w całości lokalnie na Linuksie, rozmawiając z agentem AI w naszym repozytorium, ani razu nie dotknąłem myszki."
```

### Krok 2: Dubbing i mastering shorta EP002
```bash
python3 scripts/media/dub_short.py \
  -i work/EP002_Short/input/EP002_Short_Agentic_SysAdmin.mp4 \
  -w work/EP002_Short \
  --ref-audio work/voice_sample/ref_voice_sample.wav
```

### Krok 3: Pliki wynikowe w `work/EP002_Short/assets/`
* `EP002_Short_VoiceOver_EN_CLEAN.wav` – zmasterowany plik audio lektora EN (-14.0 LUFS, True Peak <= -1.0 dBFS).
* `EP002_Short_Dubbing_Transcript_EN.json` – znaczniki czasowe i kwestie dwujęzyczne.
* `EP002_Short_Dubbing_Summary.md` – tabela podsumowująca sceny.
* `EP002_Short_FINAL_EN_DUBBED.mp4` – zduplikowany short z podmienionym audio.
