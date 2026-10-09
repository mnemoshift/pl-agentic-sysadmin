---
name: voice-dubber
description: Autonomiczny potok lokalnego dubbingu i generowania lektora (Shorts, długie wideo/epizody oraz skrypty Markdown) z wykorzystaniem modeli AI (Qwen3-TTS, Kokoro/KokoClone, Chatterbox, Breeze-TTS-2, Edge-TTS, Whisper, MarianMT/Bielik) na GPU RTX. Używaj ZAWSZE, gdy użytkownik zleca: wycięcie próbki głosu, dubbing wideo (Shorts lub Long/odcinki w work/EP...), syntezę głosu konkretnym silnikiem (qwen, kokoro, chatterbox, breeze, edge), tłumaczenie ścieżki lektorskiej lub generowanie polskiego voiceoveru z pliku .md.
---

# Voice Dubber Skill (Workstation Hub Sovereign Audio Pipeline)

Skill dostarcza w pełni zautomatyzowane, powtarzalne procedury lokalnego dubbingu oraz generowania lektora dla materiałów wideo i skryptów czytanych w katalogu roboczym `work/` na stacji roboczej Linux (Zorin OS) z kartą NVIDIA RTX.

---

## ⚡ ŻELAZNA REGUŁA AGENTA: ZERO-TOKEN OVERHEAD (BEZPOŚREDNIE WYKONANIE)

> [!IMPORTANT]
> **KATEGORYCZNY ZAKAZ CRAWLINGU KODU I BADAŃ IMPORTÓW:**
> Gdy użytkownik wydaje polecenie dubbingu lub syntezy (np. *"Zdubbinguj materiał w work/EP002 używając qwen tts"*), **NATYCHMIAST uruchom dedykowane polecenie CLI w terminalu**.
> - **NIE** czytaj plików źródłowych w `scripts/media/` ani `tools/`.
> - **NIE** sprawdzaj wersji bibliotek w `site-packages` ani nie wykonuj `python -c "import ..."`.
> - **NIE** szukaj grepem implementacji silników.
> Skrypty CLI są samowystarczalnymi czarnymi skrzynkami z wbudowaną obsługą błędów, cache'owaniem i automatycznym fallbackiem. Oszczędzaj tokeny użytkownika i natychmiast przejdź do uruchomienia zadania.

---

## 1. Tabela Intencji i Gotowe Polecenia CLI

| Intencja / Prompt użytkownika | Polecenie CLI do natychmiastowego uruchomienia |
| :--- | :--- |
| **Dubbing materiału długiego (EP002) silnikiem Qwen:**<br>`Zdubbinguj materiał w work/EP002 używając Qwen TTS` | `python3 scripts/media/dub_video.py -w work/EP002 --engine qwen` |
| **Dubbing materiału długiego (EP002) silnikiem Kokoro:**<br>`Zdubbinguj materiał w work/EP002 używając Kokoro` | `python3 scripts/media/dub_video.py -w work/EP002 --engine kokoro` |
| **Dubbing materiału długiego (EP002) silnikiem Chatterbox:**<br>`Zdubbinguj materiał w work/EP002 używając Chatterbox` | `python3 scripts/media/dub_video.py -w work/EP002 --engine chatterbox` |
| **Dubbing shorta z domyślnym silnikiem:**<br>`Przetłumacz i zdubbinguj shorta w work/EP002_Short` | `python3 scripts/media/dub_video.py -w work/EP002_Short` |
| **Przetwarzanie wsadowe zestawu wideo:**<br>`Zdubbinguj wszystkie shorty w work/` | `python3 scripts/media/dub_video.py --batch work/EP002_Short work/EP001_Short` |
| **Wycięcie próbki referencyjnej głosu:**<br>`Wytnij 8s próbkę z nagrania w work/voice_source od 00:12 do 00:20` | `python3 scripts/media/extract_voice_sample.py -i work/voice_source/EP003_VoiceOver_CLEAN.wav -s 00:00:12.000 -e 00:00:20.300 -o work/voice_sample/ref_voice_sample.wav -t "Zmontowałem to w całości lokalnie na Linuksie, rozmawiając z agentem AI w naszym repozytorium, ani razu nie dotknąłem myszki."` |
| **Generowanie polskiego lektora z pliku Markdown:**<br>`Wygeneruj voiceover z voiceover_read_script.md dla EP004` | `python3 scripts/media/generate_voiceover.py -s episodes/EP004_local_ai_dubbing_voiceover/voiceover_read_script.md -w work/EP004` |
| **Szybki odsłuch / test wycinka lektora (Wieszak 1):**<br>`Wygeneruj próbkę lektora z Wieszaka 1 dla EP004` | `python3 scripts/media/generate_voiceover.py -s episodes/EP004_local_ai_dubbing_voiceover/voiceover_read_script.md -w work/EP004 --section "WIESZAK 1"` |
| **Czysty reset wygenerowanych plików przed nagraniem:**<br>`Wyczyść wygenerowane artefakty dubbingu` | `make media-dub-clean` |

---

## 2. Obsługiwane Silniki Syntezy (`--engine`)

Wszystkie silniki działają w 100% lokalnie i są zintegrowane w potoku `dub_video.py`:

- `--engine auto` *(domyślny)*: Automatycznie wybiera najlepszy komercyjny silnik (Qwen ➔ Kokoro ➔ Chatterbox ➔ Breeze ➔ Edge).
- `--engine qwen`: **Qwen3-TTS** (`0.6B-Base`, Apache 2.0). Rekomendowany silnik komercyjny. Bardzo naturalna kadencja i autentyczna barwa głosu.
- `--engine kokoro`: **KokoClone** (Kokoro-ONNX + Kanade Voice Conversion, Apache 2.0 / MIT). Krystaliczna wymowa i zero-shot transfer barwy.
- `--engine chatterbox`: **Chatterbox-Turbo** (MIT). Odizolowany, stanowczy, radiowy ton inżynierski.
- `--engine breeze`: **Breeze-TTS-2** (Zero-shot).
- `--engine edge`: **Edge-TTS** (Microsoft Neural Voices). Szybki podgląd i awaryjny fallback bez obciążania GPU.

---

## 3. Standard Wykonawczy i Cykl Życia Zasobów GPU

Potok `dub_video.py` realizuje sekwencyjne zarządzanie pamięcią VRAM (Sequential Handover):
1. **Faster-Whisper large-v3-turbo:** Ekstrakcja segmentów ASR i zwalnianie pamięci GPU.
2. **Semantyczny chunking:** Grupowanie w logiczne zdania (15–25s) bez ucinania wypowiedzi.
3. **Lokalne tłumaczenie:** Bielik 11B (Ollama) ze słownikiem `config/tech_terms.json`, natychmiastowe zwalnianie VRAM (`keep-alive: 0`).
4. **Synteza mowy:** Wybrany silnik TTS generuje audio dla poszczególnych scen z cache'owaniem w `output/dub_parts/`.
5. **Mastering i Delivery:** Wyrównanie tempa, padding ciszy, mastering **EBU R128 (-14.0 LUFS)**, eksport napisów SRT i montaż końcowego wideo MP4.

---

## 4. Wygenerowane Pliki Produkcyjne (Standard Emisyjny)

Dla każdego projektu w katalogu `work/<ID>/output/` powstają gotowe pliki:
1. `<ID>_VoiceOver_EN_CLEAN.wav` — WAV 48kHz stereo, -14.0 LUFS, do YouTube Studio jako alternatywna ścieżka językowa (Multi-Language Audio).
2. `<ID>_FINAL_EN_DUBBED.mp4` — pełne wideo z obrazem i zsynchronizowanym dubbingiem EN.
3. `<ID>_EN.srt` / `<ID>_PL.srt` — napisy w języku angielskim i polskim.
4. `<ID>_Dubbing_Summary.md` — raport ze zsynchronizowanymi scenami i czasami.
