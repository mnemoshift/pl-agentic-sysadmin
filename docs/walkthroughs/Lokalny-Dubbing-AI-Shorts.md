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

W potoku dubbingu przyjmujemy jednolity, suwerenny standard wejściowy dla każdego projektu (`work/<ID>/input/`):
* **Czysty Plik Wideo (`*.mp4`):** Każdy podkatalog `input/` zawiera **WYŁĄCZNIE plik wideo**.
* **Zero zależności od zewnętrznych napisów:** Stan początkowy nie bazuje na obecności plików `.srt` ani skryptów `.md`. Jeżeli napisy są potrzebne, agent i potok generują je od zera w locie (Whisper ekstrahuje mowę, tworzy segmenty i zapisuje napisy `_PL.srt` oraz `_EN.srt` w `output/`).

Struktura katalogu `work/` przygotowana pod nagranie screencasta:

```text
work/
├── voice_source/
│   └── EP003_VoiceOver_CLEAN.wav                         # Nagranie źródłowe do wycięcia próbki lektora (00:12–00:20)
├── EP002_Short/
│   └── input/
│       └── EP002_Short_Agentic_SysAdmin_Karaoke_FIXED.mp4 # Wyłącznie wideo shorta (30s)
├── EP001_Short/
│   └── input/
│       └── EP001_Short_WSL_vs_Zorin_FINAL.mp4             # Wyłącznie wideo shorta (34s, "Po 10 latach...")
└── EP002/
    ├── input/
    │   └── EP002_Zorin_Desktop_FINAL.mp4                  # Wyłącznie wideo pełnego filmu (12:08, 1440p60)
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
  - Automatycznie wykrywa wideo w `work/EP002_Short/input/` (brak predefiniowanych napisów czy skryptów).
  - Ekstrahuje strumień mowy i lokalnie uruchamia Whisper, który w locie dzieli nagranie na segmenty ze znacznikami czasu.
  - Tłumaczy kwestie z zachowaniem ścisłego słownika IT (*mount point*, *VRAM footprint*, *PCIe bus*, *macOS-inspired workspace*).
  - Generuje komplet napisów SRT (`EP002_Short_PL.srt` oraz `EP002_Short_EN.srt`).
  - Przeprowadza syntezę na GPU (Breeze-TTS-2) z wykorzystaniem wyciętej próbki głosu.
  - Dopasowuje tempo do cięć wideo, wstawia pauzy i masteruje ścieżkę do standardu emisyjnego **-14 LUFS** (EBU R128).
  - Zapisuje rezultaty w folderze wyjściowym `work/EP002_Short/output/` i dostarcza komplet plików produkcyjnych:
    1. Czysty plik audio lektora EN: `EP002_Short_VoiceOver_EN_CLEAN.wav` (pod YouTube Multi-Language Audio).
    2. Gotowy plik wideo z dubbingiem: `EP002_Short_FINAL_EN_DUBBED.mp4` (obraz + audio EN).
    3. Napisy: `EP002_Short_EN.srt` oraz `EP002_Short_PL.srt`.
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

Dla drugiego shorta z zestawu (`work/EP001_Short`, 34-sekundowa wersja punchy) zlecamy wykonanie całego potoku za jednym zamachem:

> *Zdubbinguj materiał w work/EP001_Short przy użyciu przygotowanej próbki głosu i odtwórz gotowe wideo.*

Albo w scenariuszu, gdybyśmy startowali od zera bez wcześniejszego wycinania próbki:
> *Wytnij 8-sekundową próbkę głosu z work/voice_source od 00:12 do 00:20 i zdubbinguj materiał w work/EP001_Short.*

* **Działanie Agenta:**
  1. Spina cały workflow bez konieczności interwencji użytkownika.
  2. Bada wejście: wykrywa wyłącznie plik wideo `EP001_Short_WSL_vs_Zorin_FINAL.mp4` (bez zewnętrznych plików .srt czy .wav).
  3. Ekstrahuje audio i transkrypuje w Whisper 6 dynamicznych segmentów o porzuceniu WSL2, drenażu tokenów w PowerShellu i natywnym Linuksie.
  4. Dokonuje inżynierskiego przekładu PL $\rightarrow$ EN i generuje napisy `EP001_Short_PL.srt` oraz `EP001_Short_EN.srt`.
  5. Przeprowadza syntezę na GPU (model Breeze-TTS-2 w VRAM), dopasowuje czasy segmentów pod oryginalne cięcia.
  6. Przeprowadza broadcastowy mastering EBU R128 (-14.0 LUFS, True Peak $\le$ -1.0 dBFS).
  7. Zapisuje komplet plików produkcyjnych w `work/EP001_Short/output/`:
     - `EP001_Short_VoiceOver_EN_CLEAN.wav`
     - `EP001_Short_FINAL_EN_DUBBED.mp4`
     - `EP001_Short_EN.srt` oraz `EP001_Short_PL.srt`
  8. Wyświetla podsumowanie z tabelą scen i natychmiast uruchamia odtworzenie rezultatu.

---

## 5. Skalowanie na Długi Format (EP002 i Porównanie 1:1 z ElevenLabs)

Ten sam suwerenny potok nie jest ograniczony wyłącznie do formatu Shorts. W projekcie `work/EP002` znajduje się pełnometrażowy odcinek (12:08, 1440p60) w `work/EP002/input/EP002_Zorin_Desktop_FINAL.mp4` oraz nagranie referencyjne przygotowane w ElevenLabs (`work/EP002/reference/EP002_FINAL_EN_ElevenLabs.mp4`), które pochłonęło **115 000 płatnych kredytów**.

Wpisujesz w czacie Antigravity:
> *Zdubbinguj materiał w work/EP002 przy użyciu przygotowanej próbki głosu.*

* **Działanie Agenta:**
  1. Wykrywa czyste wideo `EP002_Zorin_Desktop_FINAL.mp4` w `input/`.
  2. Ekstrahuje strumień mowy i automatycznie transkrypuje oraz synchronizuje segmenty z wykorzystaniem lokalnego modelu Whisper.
  3. Dokonuje inżynierskiego przekładu dialogów oraz generuje napisy SRT.
  4. Generuje zsynchronizowane audio i gotowy plik wideo w `work/EP002/output/`.
  5. Umożliwia natychmiastowe zderzenie jakościowe A/B: odsłuch lokalnego modelu na karcie RTX 4060 Ti (koszt 0 zł, zero wycieków do chmury) obok chmurowego dubbingu ElevenLabs.

---

## 6. Ścieżka Manualna / Oldschool CLI (Dla zdeterminowanych)

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

# 4. Ręczny dubbing długiego odcinka (EP002):
python3 scripts/media/dub_short.py -w work/EP002

# 5. Lub przetwarzanie całego zestawu wsadowo jednym poleceniem:
python3 scripts/media/dub_short.py --batch work/EP002_Short work/EP001_Short work/EP002

# 6. Czysty reset katalogu roboczego przed kolejnym nagraniem:
make media-dub-clean
```

---

## 7. Wygenerowane Pliki i Standard Emisyjny

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
