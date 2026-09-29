# Szablon Scenariusza YouTube Shorts (Format Pionowy 9:16)

> **Instrukcja dla twórcy:**
> 1. Skopiuj ten szablon do katalogu roboczego swojego projektu:  
>    `cp templates/kdenlive/short_script.md work/<NAZWA_PROJEKTU>/input/short_script.md`
> 2. Dostosuj poniższe 5 scen pod swój materiał (orientacyjny łączny czas: ~30-45 sekund).
> 3. Skrypt jest automatycznie odczytywany przez pipeline `scripts/media/transcribe_audio.py` oraz Agenta AI w celu:
>    - wygenerowania precyzyjnych promptów do kadrów tła 9:16 (dla Agenta lub Midjourney),
>    - powiązania segmentów transkrypcji Whisper z tytułami plansz na ścieżce V3,
>    - przygotowania dynamicznych napisów karaoke (CapCut style) z eliminacją nakładania klatek.

---

### Zasady Dobrego Shorta Technicznego:
- **Scena 1 (Hak):** Pierwsze 3 sekundy decydują o zatrzymaniu scrollowania. Mocne, zaskakujące zdanie.
- **Scena 2 (Problem):** Konkretne tarcie, ból inżynierski lub strata czasu, którą widz doskonale zna.
- **Scena 3 (Zadanie):** Jednoznaczne polecenie lub demonstracja rozwiązania problemu.
- **Scena 4 (Rezultat):** Dowód działania (screencast w tle, wykonanie planu, metryki, czysty kod).
- **Scena 5 (CTA):** Zaproszenie do obejrzenia pełnego materiału na YouTube lub przejścia do otwartego repozytorium.
- **Żelazna zasada kadrowania 9:16:** Górna 1/3 kadru **zawsze ciemna i bez wtopionego tekstu** (zarezerwowana na dynamiczne tytuły V3 i napisy karaoke).

---

### Rozpiska Scen (1 do 5):

#### Scena 1 [0:00 - 0:05] — Hak Wizualny (Hook)
* **Kwestia lektora:**  
  *„[Wpisz mocne, prowokujące lub intrygujące pierwsze zdanie lektora — np. Przestań traktować AI jak zabawkę...]”*
* **Koncepcja graficzna 9:16:**  
  [Opis pionowego kadru tła — np. Cybernetyczny rdzeń AI, futurystyczny procesor w chłodnych odcieniach cyberpunka]
* **Tytuł na osi czasu (Ścieżka V3):**  
  `[KRÓTKI DYNAMICZNY TYTUŁ WIELKIMI LITERAMI — MAX 4-5 SŁÓW]`
* **Zasada kadrowania:**  
  Górna 1/3 kadru ciemna, bez wtopionego tekstu (przestrzeń pod tytuły i karaoke).

---

#### Scena 2 [0:05 - 0:12] — Zdefiniowanie Bólu (Problem)
* **Kwestia lektora:**  
  *„[Opis frustracji lub powszechnego problemu — np. Zamiast marnować godziny na forach i dłubaniu w konfiguracji...]”*
* **Koncepcja graficzna 9:16:**  
  [Opis wizualny chaosu / problemu — np. Labirynt plików konfiguracyjnych, ściana surowego kodu dotfiles w terminalu]
* **Tytuł na osi czasu (Ścieżka V3):**  
  `[TYTUŁ PODKREŚLAJĄCY PROBLEM LUB FRUSTRACJĘ]`
* **Zasada kadrowania:**  
  Górna 1/3 kadru ciemna, bez wtopionego tekstu.

---

#### Scena 3 [0:12 - 0:18] — Zadanie Inżynierskie (Zadanie / Rozwiązanie)
* **Kwestia lektora:**  
  *„[Konkretna intencja lub zlecenie dla systemu/agenta — np. Dałem agentowi jedno proste zadanie: przekształć pulpit...]”*
* **Koncepcja graficzna 9:16:**  
  [Opis estetycznego rezultatu / interfejsu — np. Eleganckie stanowisko pracy, minimalistyczny pulpit z nowoczesnym dokiem]
* **Tytuł na osi czasu (Ścieżka V3):**  
  `[TYTUŁ PREZENTUJĄCY CEL LUB ROZWIĄZANIE]`
* **Zasada kadrowania:**  
  Górna 1/3 kadru ciemna, bez wtopionego tekstu.

---

#### Scena 4 [0:18 - 0:24] — Rezultat i Autonomia (Wycinek Wideo / Dowód)
* **Kwestia lektora:**  
  *„[Opis bezwysiłkowego rezultatu — np. Minuta roboty, audyt w tle i gotowy plan wdrożenia. Bez dotknięcia ani jednego pliku...]”*
* **Koncepcja wideo:**  
  [Wycinek z nagrania źródłowego 16:9 z rozmyciem tła gblur — np. Agent realizujący plan w terminalu / IDE]
* **Tytuł na osi czasu (Ścieżka V3):**  
  `[TYTUŁ AKCENTUJĄCY SZYBKOŚĆ LUB SKUTECZNOŚĆ]`

---

#### Scena 5 [0:24 - 0:30] — Podsumowanie i Call to Action (Wycinek Wideo / Finał)
* **Kwestia lektora:**  
  *„[Podsumowanie i wezwanie do akcji — np. Całą sesję na żywo i gotowe skrypty znajdziesz w filmie pod linkiem poniżej!]”*
* **Koncepcja wideo:**  
  [Wycinek z materiału źródłowego — np. Repozytorium GitHub, podsumowanie architektury lub plansza końcowa]
* **Tytuł na osi czasu (Ścieżka V3):**  
  `[MOCNA PUENTA LUB WEZWANIE DO ZOBACZENIA PEŁNEGO FILMU]`
