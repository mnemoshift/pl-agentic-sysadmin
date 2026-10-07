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

W potoku dubbingu przyjmujemy jednolity, inżynierski standard wejściowy dla każdego projektu (`work/<ID>/input/`):
1. **Wideo (`*.mp4`):** Obraz ze zmontowanym materiałem.
2. **Czysty Lektor (`*_VoiceOver_CLEAN.wav`):** Odrębna, bezstratna ścieżka mowy (jeśli nie jest dostępna, skrypt automatycznie ekstrahuje strumień audio z pliku wideo).
3. **Opcjonalny Skrypt / Napisy (`short_script.md` lub `*.srt`):** Gotowy podział na kwestie (dla formatu Shorts). Jeśli skrypt nie zostanie dostarczony (np. dla długiego filmu), potok automatycznie uruchamia lokalny model Whisper do transkrypcji i detekcji znaczników czasowych.

Struktura katalogu `work/` przygotowana pod nagranie screencasta:

```text
work/
├── voice_source/
│   └── EP003_VoiceOver_CLEAN.wav                         # Nagranie źródłowe do wycięcia próbki lektora (00:12–00:20)
├── EP002_Short/
│   └── input/
│       ├── EP002_Short_Agentic_SysAdmin_Karaoke_FIXED.mp4 # Wideo shorta (30s)
│       ├── EP002_Short_VoiceOver_CLEAN.wav                # Czysta polska ścieżka lektorska
│       └── short_script.md                                # Scenariusz z podziałem na sceny i kwestie
├── EP001_Short/
│   └── input/
│       ├── EP001_Short_WSL_vs_Zorin_FINAL.mp4             # Wideo shorta (102s)
│       ├── EP001_Short_VoiceOver_CLEAN.wav                # Czysta polska ścieżka lektorska
│       └── EP001_Short_WSL_vs_Zorin.srt                   # Napisy z oryginalnymi znacznikami czasu
└── EP002/
    └── input/
        ├── EP002_Zorin_Desktop_FINAL.mp4                  # Pełny film długi (12:08, 1440p60)
        ├── EP002_VoiceOver_CLEAN.wav                      # Czysta polska ścieżka lektorska (brak skryptu -> Whisper auto)
        └── reference/
            ├── EP002_Audio_EN_ElevenLabs_14LUFS.mp3       # Ścieżka z ElevenLabs (do porównania A/B i rachunku)
            └── EP002_FINAL_EN_ElevenLabs.mp4              # Zmontowane wideo z ElevenLabs do podglądu A/B
```

Przed rozpoczęciem sesji folder `work/voice_sample/` oraz foldery wyjściowe `output/` nie istnieją — Agent wygeneruje je od zera na Twoich oczach.

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
  - Automatycznie wykrywa wideo w `work/EP002_Short/input/` oraz scenariusz `short_script.md`.
  - Tłumaczy kwestie z zachowaniem ścisłego słownika IT (*mount point*, *VRAM footprint*, *PCIe bus*, *macOS-inspired workspace*).
  - Przeprowadza syntezę na GPU z wykorzystaniem wyciętej próbki głosu.
  - Dopasowuje tempo do cięć wideo, wstawia pauzy i masteruje ścieżkę do standardu emisyjnego **-14 LUFS** (EBU R128).
  - Zapisuje rezultaty w folderze wyjściowym `work/EP002_Short/output/` i dostarcza **dwa pliki produkcyjne**:
    1. Czysty plik audio lektora EN: `EP002_Short_VoiceOver_EN_CLEAN.wav` (pod YouTube Multi-Language Audio).
    2. Gotowy plik wideo z dubbingiem: `EP002_Short_FINAL_EN_DUBBED.mp4` (obraz + audio EN).
  - Zwraca w czacie zwięzłą tabelę porównawczą A/B (PL vs EN).

### Krok 3: Odsłuch i inspekcja parametrów
Wpisujesz w czacie:
> *Odtwórz wygenerowane wideo dla EP002 i podsumuj parametry audio.*

* **Działanie Agenta:**
  - Uruchamia podgląd wideo lub odtwarza próbkę audio w systemowym odtwarzaczu.
  - Wyświetla zmierzone parametry: Zintegrowana głośność (`-14.0 LUFS` do `-15.3 LUFS`), True Peak (`< -1.0 dBFS`), LRA.

---

## 4. Ścieżka One-Shot w Antigravity (Cały Potok „Na Raz” dla EP001)

Gdy wiesz już jak działa system, nie musisz rozbijać pracy na pojedyncze etapy. Prawdziwa siła podejścia **Agentic SysAdmin** polega na zleceniu pełnego łańcucha operacyjnego za pomocą **dokładnie jednego promptu czystej intencji**.

Dla drugiego shorta z zestawu (`work/EP001_Short`, 102 sekundy) zlecamy wykonanie całego potoku za jednym zamachem:

> *Zdubbinguj materiał w work/EP001_Short przy użyciu przygotowanej próbki głosu i odtwórz gotowe wideo.*

Albo w scenariuszu, gdybyśmy startowali od zera bez wcześniejszego wycinania próbki:
> *Wytnij 8-sekundową próbkę głosu z work/voice_source od 00:12 do 00:20 i zdubbinguj materiał w work/EP001_Short.*

* **Działanie Agenta:**
  1. Spina cały workflow bez konieczności interwencji użytkownika:
  2. Bada wejście: wykrywa `EP001_Short_WSL_vs_Zorin_FINAL.mp4` oraz plik `.srt`.
  3. Parsuje 19 segmentów wypowiedzi o wirtualizacji, PowerShellu i tokenach.
  4. Dokonuje inżynierskiego przekładu PL $\rightarrow$ EN.
  5. Przeprowadza syntezę na GPU, dopasowuje czasy segmentów pod oryginalne cięcia.
  6. Przeprowadza broadcastowy mastering EBU R128 (-14.0 LUFS, True Peak $\le$ -1.0 dBFS).
  7. Zapisuje oba kluczowe pliki produkcyjne w `work/EP001_Short/output/`:
     - `EP001_Short_VoiceOver_EN_CLEAN.wav`
     - `EP001_Short_FINAL_EN_DUBBED.mp4`
  8. Wyświetla podsumowanie z tabelą scen i natychmiast uruchamia odtworzenie rezultatu.

---

## 5. Ścieżka Manualna / Oldschool CLI (Dla zdeterminowanych)

Wyłącznie w celach poglądowych dla inżynierów, którzy chcą uruchomić poszczególne polecenia ręcznie z poziomu terminala bash:

```bash
# 1. Ręczne wycięcie próbki referencyjnej głosu:
python3 scripts/media/extract_voice_sample.py \
  -i work/voice_source/EP003_VoiceOver_CLEAN.wav \
  -s 00:00:12.000 -e 00:00:20.300 \
  -o work/voice_sample/ref_voice_sample.wav \
  -t "Zmontowałem to w całości lokalnie na Linuksie, rozmawiając z agentem AI w naszym repozytorium, ani razu nie dotknąłem myszki."

# 2. Ręczny dubbing pierwszego shorta (EP002):
python3 scripts/media/dub_short.py -w work/EP002_Short

# 3. Ręczny dubbing drugiego shorta (EP001):
python3 scripts/media/dub_short.py -w work/EP001_Short

# 4. Lub przetwarzanie całego zestawu wsadowo jednym poleceniem:
python3 scripts/media/dub_short.py --batch work/EP002_Short work/EP001_Short

# 5. Czysty reset katalogu roboczego przed kolejnym nagraniem:
make media-dub-clean
```

---

## 6. Wygenerowane Pliki i Standard Emisyjny

W katalogu `work/<ID>/output/` (zaraz obok katalogu `input/`) powstaje kompletny pakiet produkcyjny. Z każdego projektu otrzymujesz **dwa kluczowe pliki do dystrybucji**:

1. **Plik dźwiękowy lektora (YouTube Multi-Language Audio):**
   * `<ID>_VoiceOver_EN_CLEAN.wav` – zmasterowany plik audio lektora EN (48kHz stereo, broadcast mastering -14.0 LUFS, True Peak $\le$ -1.0 dBFS).
   * **Zastosowanie:** Gotowy do bezpośredniego wgrania w YouTube Studio w zakładce *Napisy i dźwięk -> Ścieżka dźwiękowa* jako alternatywny język (English) do oryginalnego filmu. Widzowie z zagranicy słyszą angielski dubbing, widzowie z Polski polski oryginał — bez utraty watch-time i bez ponownego wrzucania filmu.

2. **Zdubbingowany film EN (Full Video + Dubbing):**
   * `<ID>_FINAL_EN_DUBBED.mp4` – kompletny plik wideo ze zsynchronizowaną angielską ścieżką dźwiękową i oryginalnym obrazem.
   * **Zastosowanie:** Gotowy do bezpośredniej publikacji jako niezależny film na anglojęzycznym kanale YouTube lub osobnym formacie Shorts.

3. **Artefakty pomocnicze:**
   * `<ID>_Dubbing_Transcript_EN.json` – precyzyjne znaczniki czasowe, teksty PL i inżynierski przekład EN.
   * `<ID>_Dubbing_Summary.md` – czytelny raport z tabelą scen A/B oraz zmierzonymi parametrami emisyjnymi.
