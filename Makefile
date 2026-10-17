.PHONY: help setup setup-env test lint dub dub-init dub-transcribe dub-status media-setup-models audit inventory all-audits session-status session-log check restore-dry-run desktop-macos desktop-studio desktop-cyber-hud desktop-reset desktop-status media-check-mcp media-setup-mcp media-clean-audio media-karaoke media-build-short media-clean-work media-prepare-demo media-extract-sample media-dub-video media-dub-short media-dub-ep002 media-dub-ep001 media-dub-batch media-dub-clean gdrive-status gdrive-install gdrive-auth gdrive-list gdrive-folders gdrive-add gdrive-remove gdrive-sync gdrive-timer-enable gdrive-timer-disable gdrive-mount gdrive-unmount tts-status tts-install tts-config tts-test tts-uninstall

# Domyślny cel
help:
	@echo "=========================================================="
	@echo "  WORKSTATION HUB - SYSTEM CONTROL INTERFACE"
	@echo "=========================================================="
	@echo "Dostępne komendy:"
	@echo "  make setup           - Inicjalizuje środowisko Python (.venv) przez uv sync"
	@echo "  make test            - Uruchamia testy jednostkowe (pytest tests/)"
	@echo "  make lint            - Weryfikuje jakość kodu (Ruff check + ShellCheck)"
	@echo "  make setup-env       - Alias dla make setup"
	@echo "  make audit           - Wykonuje audyt fizycznego sprzętu (CPU, RAM, Storage, GPU, Audio, Kamery)"
	@echo "  make inventory       - Wykonuje inwentaryzację oprogramowania (APT, Flatpak, Repozytoria, Runtimes)"
	@echo "  make all-audits      - Uruchamia pełny zestaw audytów (sprzęt + oprogramowanie)"
	@echo "  make desktop-studio  - Wdraża profil Cyber Studio (MnemoShift Cyber-Blueprint, Top Bar Emission HUD, Conky, Plank HUD)"
	@echo "  make desktop-macos   - Wdraża profil emisyjny macOS (WhiteSur, kropki po lewej, autodetekcja Wayland/X11, CSD)"
	@echo "  make desktop-reset   - Przywraca stan fabryczny pulpitu Zorin OS (kropki po prawej, pasek na dole)"
	@echo "  make desktop-status  - Sprawdza aktywny stan konfiguracji pulpitu i doku"
	@echo "  make session-status  - Wyświetla aktualny stan z memory/SESSION_STATE.md"
	@echo "  make session-log MSG=\"...\" - Dopisuje wpis ze znacznikiem czasu do memory/JOURNAL.md"
	@echo "  make check           - Sprawdza integralność plików pamięci i inwentarza"
	@echo "  make restore-dry-run - Symuluje procedurę odtworzenia Disaster Recovery bez wprowadzania zmian"
	@echo "  --- Czytnik Tekstu TTS (Select & Listen: Edge Neural TTS) ---"
	@echo "  make tts-status      - Sprawdza stan czytnika GhostShift TTS, venv i skrótów klawiszowych"
	@echo "  make tts-install     - Instaluje zależności, środowisko venv, launcher i skróty <Super>+R"
	@echo "  make tts-config      - Otwiera okno wyboru głosu lektora i prędkości (Zenity GUI)"
	@echo "  make tts-test        - Odtwarza próbkę głosu neuronowego"
	@echo "  make tts-uninstall   - Usuwa integrację i skróty klawiszowych czytnika"
	@echo "  --- Suwerenny Dubbing AI (Whisper -> Bielik 11B -> Qwen3-TTS Custom + OpenVoice v2) ---"
	@echo "  make dub WORK=<folder> [FROM=translate|tts|master] [CHUNKS=auto|short|long] [ENGINE=...]"
	@echo "  make dub-init WORK=<folder> [INPUT=/sciezka/do/wideo.mp4]"
	@echo "  make dub-transcribe WORK=<folder> - Tylko transkrypcja Whisper + korekta Bielik + napisy PL/EN"
	@echo "  make dub-status      - Wyświetla stan projektów w work/, próbek głosu i ostatniego przebiegu"
	@echo "  --- Narzędzia Wideo & Audio (Kdenlive & Studio) ---"
	@echo "  make media-check-mcp - Sprawdza stan Kdenlive, wrapperów CLI i serwera MCP"
	@echo "  make media-setup-mcp - Instaluje Kdenlive (Flatpak user) i konfiguruje serwer MCP"
	@echo "  make media-setup-models - Przygotowuje lokalne wagi modeli AI (Qwen3-TTS, OpenVoice v2, Bielik)"
	@echo "  make media-clean-audio INPUT=... OUTPUT=... [START=...] [END=...] [LUFS=-14.0]"
	@echo "  make media-karaoke AUDIO=... OUTPUT=... [FAST=1] [FONT=...]"
	@echo "  make media-build-short WORKSPACE=... [NAME=EP002_Short]"
	@echo "  make media-extract-sample INPUT=... START=... END=... OUTPUT=..."
	@echo "  make media-clean-work - Czyści wygenerowane artefakty (assets, .kdenlive), zachowując input/"
	@echo "  make media-prepare-demo - Inicjalizuje/odnawia pliki wejściowe w work/EP002_Short/input/"
	@echo "  --- Google Drive Selektywna Synchronizacja (rclone) ---"
	@echo "  make gdrive-status   - Sprawdza stan rclone, połączenie z Google Drive i timer tła"
	@echo "  make gdrive-install  - Instaluje rclone w przestrzeni użytkownika (~/.local/bin/rclone)"
	@echo "  make gdrive-auth     - Konfiguruje autoryzację zdalnego dysku Google Drive (rclone config)"
	@echo "  make gdrive-list [PATH=...] - Wyświetla katalogi na Google Drive"
	@echo "  make gdrive-folders  - Wyświetla tabelę zdefiniowanych folderów synchronizacji"
	@echo "  make gdrive-add REMOTE=... [LOCAL=...] [MODE=bisync] [DESC=...] - Dodaje folder do synchronizacji"
	@echo "  make gdrive-remove REMOTE=... - Usuwa folder z listy synchronizacji"
	@echo "  make gdrive-sync [FOLDER=...] [DRY_RUN=1] [RESYNC=1] - Wykonuje synchronizację folderów"
	@echo "  make gdrive-timer-enable [INTERVAL=15m] - Włącza automatyczną synchronizację w systemd"
	@echo "  make gdrive-timer-disable - Wyłącza automatyczną synchronizację w systemd"
	@echo "  make gdrive-mount [REMOTE_PATH=...] [MOUNTPOINT=...] - Montuje dysk VFS z lokalnym cache"
	@echo "  make gdrive-unmount [MOUNTPOINT=...] - Odmontowuje dysk VFS"
	@echo "=========================================================="

setup: setup-env

setup-env:
	@echo "Inicjalizacja środowiska wirtualnego Python (.venv) przez uv..."
	@command -v uv >/dev/null 2>&1 || { echo "[BŁĄD] Wymagane narzędzie 'uv'. Zainstaluj: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
	@uv sync
	@echo "[OK] Środowisko .venv gotowe do użycia."

test:
	@echo "Uruchamianie testów jednostkowych (pytest)..."
	@uv run pytest tests/

lint:
	@echo "Uruchamianie lintera Pythona (Ruff)..."
	@uv run ruff check .
	@echo "Uruchamianie lintera skryptów Bash (ShellCheck)..."
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck scripts/*.sh scripts/media/*.sh; \
		echo "[OK] ShellCheck: wszystkie skrypty zweryfikowane pomyślnie."; \
	else \
		echo "[WARN] Brak polecenia 'shellcheck'. Zainstaluj: sudo apt install -y shellcheck"; \
	fi

audit:
	@chmod +x scripts/audit_hardware.sh
	@./scripts/audit_hardware.sh

inventory:
	@chmod +x scripts/audit_software.sh
	@./scripts/audit_software.sh

all-audits: audit inventory
	@echo "[OK] Wszystkie audyty stacji roboczej zostały zakończone sukcesem."

session-status:
	@chmod +x scripts/session_ctl.sh
	@./scripts/session_ctl.sh status

session-log:
	@chmod +x scripts/session_ctl.sh
	@if [ -z "$(MSG)" ]; then \
		echo "[BŁĄD] Wymagany parametr MSG. Użycie: make session-log MSG=\"Treść notatki...\""; \
		exit 1; \
	fi
	@./scripts/session_ctl.sh log "$(MSG)"

check:
	@chmod +x scripts/session_ctl.sh
	@./scripts/session_ctl.sh check
	@echo "Weryfikacja istnienia profili inwentarzowych:"
	@test -f inventory/hardware.md && echo "  [✓] inventory/hardware.md obecny" || echo "  [✗] Brak inventory/hardware.md"
	@test -f inventory/hardware.json && echo "  [✓] inventory/hardware.json obecny" || echo "  [✗] Brak inventory/hardware.json"
	@test -f inventory/software.md && echo "  [✓] inventory/software.md obecny" || echo "  [✗] Brak inventory/software.md"
	@test -f inventory/software.json && echo "  [✓] inventory/software.json obecny" || echo "  [✗] Brak inventory/software.json"
	@(test -f docs/recovery/DISASTER_RECOVERY.md || test -f recovery/DISASTER_RECOVERY.md) && echo "  [✓] docs/recovery/DISASTER_RECOVERY.md obecny" || echo "  [✗] Brak docs/recovery/DISASTER_RECOVERY.md"

restore-dry-run:
	@chmod +x scripts/restore_workstation.sh
	@./scripts/restore_workstation.sh --dry-run

desktop-macos:
	@chmod +x scripts/desktop_ctl.sh
	@./scripts/desktop_ctl.sh apply-macos

desktop-studio:
	@chmod +x scripts/desktop_ctl.sh
	@./scripts/desktop_ctl.sh apply-studio

desktop-cyber-hud: desktop-studio

desktop-reset:
	@chmod +x scripts/desktop_ctl.sh
	@./scripts/desktop_ctl.sh reset

desktop-status:
	@chmod +x scripts/desktop_ctl.sh
	@./scripts/desktop_ctl.sh status

media-clean-audio:
	@if [ -z "$(INPUT)" ] || [ -z "$(OUTPUT)" ]; then \
		echo "[BŁĄD] Wymagane parametry INPUT i OUTPUT. Przykład:"; \
		echo "  make media-clean-audio INPUT=input.mp4 OUTPUT=clean.wav [START=...] [END=...] [EXCLUDE=28.9-32.6] [LUFS=-14.0] [FAST=1]"; \
		exit 1; \
	fi
	@chmod +x scripts/media/clean_audio.py scripts/media/transcribe_audio.py
	@./scripts/media/clean_audio.py -i "$(INPUT)" -o "$(OUTPUT)" \
		$(if $(START),--start "$(START)") \
		$(if $(END),--end "$(END)") \
		$(if $(EXCLUDE),--exclude "$(EXCLUDE)") \
		$(if $(LUFS),--lufs "$(LUFS)")
	@uv run scripts/media/transcribe_audio.py -a "$(OUTPUT)" $(if $(FAST),--fast) $(if $(SCRIPT),--script "$(SCRIPT)")

media-karaoke:
	@if [ -z "$(AUDIO)" ] || [ -z "$(OUTPUT)" ]; then \
		echo "[BŁĄD] Wymagane parametry AUDIO i OUTPUT. Przykład:"; \
		echo "  make media-karaoke AUDIO=voice.wav OUTPUT=subtitles.ass [KDENLIVE=project.kdenlive] [FAST=1]"; \
		exit 1; \
	fi
	@chmod +x scripts/media/generate_karaoke.py
	@uv run scripts/media/generate_karaoke.py -a "$(AUDIO)" -o "$(OUTPUT)" \
		$(if $(FAST),--fast) \
		$(if $(FONT),--font "$(FONT)") \
		$(if $(HIGHLIGHT),--highlight "$(HIGHLIGHT)") \
		$(if $(KDENLIVE),--kdenlive "$(KDENLIVE)")

media-build-short:
	@if [ -z "$(WORKSPACE)" ]; then \
		echo "[BŁĄD] Wymagany parametr WORKSPACE. Przykład:"; \
		echo "  make media-build-short WORKSPACE=~/workspaces/EP002_Short [NAME=EP002_Short] [WITH_KARAOKE=1]"; \
		exit 1; \
	fi
	@chmod +x scripts/media/build_kdenlive_short.py
	@./scripts/media/build_kdenlive_short.py -w "$(WORKSPACE)" $(if $(NAME),-n "$(NAME)") $(if $(WITH_KARAOKE),--with-karaoke)

media-check-mcp:
	@chmod +x scripts/media/setup_kdenlive_mcp.sh
	@./scripts/media/setup_kdenlive_mcp.sh --check

media-setup-mcp:
	@chmod +x scripts/media/setup_kdenlive_mcp.sh
	@./scripts/media/setup_kdenlive_mcp.sh --setup

media-clean-work:
	@echo "Czyszczenie wygenerowanych artefaktów montażu w work/..."
	@rm -rf work/*/assets work/*/*.kdenlive* work/*/*.ass work/*/*.mp4 2>/dev/null || true
	@echo "[OK] Wyczyszczono artefakty montażu. Pliki wejściowe w work/*/input/ zachowane."

media-prepare-demo:
	@chmod +x scripts/media/prepare_demo.sh
	@./scripts/media/prepare_demo.sh

# --- Suwerenny Potok Dubbingu i Voiceoveru AI (Whisper / Bielik 11B / Qwen3-TTS Custom + OpenVoice v2 / EBU R128) ---

DUB_WORK := $(or $(WORK),$(WORKSPACE),$(PROJECT))
DUB_ENGINE := $(or $(ENGINE),qwen)
DUB_EXPRESSIVE_FLAG := $(if $(filter 0 false no FALSE NO,$(EXPRESSIVE)),--no-expressive,--expressive)
DUB_FROM := $(or $(FROM),$(FROM_STAGE))
DUB_CHUNKS := $(or $(CHUNKS),$(CHUNK_MODE))
DUB_RESUME_FROM := $(or $(RESUME),$(RESUME_FROM))

dub:
	@if [ -z "$(DUB_WORK)" ] && [ -z "$(INPUT)" ]; then \
		echo "[BŁĄD] Wymagany parametr WORK=<podfolder> (lub WORKSPACE=<podfolder>). Przykłady:"; \
		echo "  make dub WORK=EP002_Short"; \
		echo "  make dub WORK=EP002_Short FROM=translate  (wznowienie po edycji PL w 03_scenes_pl_grouped.json)"; \
		echo "  make dub WORK=EP002_Short FROM=tts        (wznowienie po edycji kwestii/acting directions)"; \
		echo "  make dub WORK=EP002_Short FROM=master     (wznowienie time-syncu, masteringu i muxingu)"; \
		echo "  make dub WORK=EP002_Short CHUNKS=short    (wymuszenie podziału krótkiego: 2.5-7.5s)"; \
		echo "  make dub WORK=moj_material INPUT=/sciezka/do/wideo.mp4"; \
		echo "  make dub WORK=EP002_Short ENGINE=qwen-base"; \
		echo "  make dub WORK=EP002_Short ENGINE=kokoro"; \
		echo "  make dub WORK=EP002_Short TRANSCRIBE_ONLY=1"; \
		exit 1; \
	fi
	@chmod +x scripts/media/dub_video.py
	@./scripts/media/dub_video.py \
		$(if $(DUB_WORK),-w "$(DUB_WORK)") \
		$(if $(INPUT),-i "$(INPUT)") \
		$(if $(SCRIPT),-s "$(SCRIPT)") \
		$(if $(REF_AUDIO),--ref-audio "$(REF_AUDIO)") \
		--engine "$(DUB_ENGINE)" \
		$(if $(OUTPUT_DIR),-o "$(OUTPUT_DIR)") \
		$(if $(ACCENT),--accent "$(ACCENT)") \
		$(if $(LLM_MODEL),--llm-model "$(LLM_MODEL)") \
		$(if $(INSTRUCTION),--instruction "$(INSTRUCTION)") \
		$(if $(DUB_FROM),--from-stage "$(DUB_FROM)") \
		$(if $(DUB_CHUNKS),--chunk-mode "$(DUB_CHUNKS)") \
		$(if $(DUB_RESUME_FROM),--resume-from "$(DUB_RESUME_FROM)") \
		$(if $(filter 1 true yes TRUE YES,$(TRANSCRIBE_ONLY)),--transcribe-only) \
		$(DUB_EXPRESSIVE_FLAG)

dub-init:
	@if [ -z "$(DUB_WORK)" ]; then \
		echo "[BŁĄD] Wymagany parametr WORK=<podfolder>. Przykład:"; \
		echo "  make dub-init WORK=moj_material [INPUT=/sciezka/do/wideo.mp4]"; \
		exit 1; \
	fi
	@target_dir="work/$$(basename "$(DUB_WORK)")"; \
	mkdir -p "$$target_dir/input" "$$target_dir/runs"; \
	if [ -n "$(INPUT)" ]; then \
		if [ -f "$(INPUT)" ]; then \
			cp -f "$(INPUT)" "$$target_dir/input/"; \
			echo "[OK] Skopiowano plik wejściowy do $$target_dir/input/$$(basename "$(INPUT)")"; \
		else \
			echo "[BŁĄD] Plik INPUT=$(INPUT) nie istnieje!"; \
			exit 1; \
		fi; \
	fi; \
	echo "[OK] Przestrzeń robocza gotowa: $$target_dir/input/"; \
	echo "     Uruchom dubbing komendą: make dub WORK=$$(basename "$(DUB_WORK)")"

dub-transcribe:
	@if [ -z "$(DUB_WORK)" ]; then \
		echo "[BŁĄD] Wymagany parametr WORK=<podfolder>. Przykład:"; \
		echo "  make dub-transcribe WORK=EP002_Short"; \
		exit 1; \
	fi
	@$(MAKE) --no-print-directory dub WORK="$(DUB_WORK)" INPUT="$(INPUT)" LLM_MODEL="$(LLM_MODEL)" TRANSCRIBE_ONLY=1

dub-status:
	@echo "=========================================================="
	@echo "  STATUS PRZESTRZENI DUBBINGU (work/)"
	@echo "=========================================================="
	@echo "1. Globalne próbki referencyjne głosu (work/voice_sample/):"
	@ls -lh work/voice_sample/*.wav 2>/dev/null | awk '{print "   - " $$9 " (" $$5 ")"}' || echo "   [BRAK PRÓBEK W work/voice_sample/]"
	@echo ""
	@echo "2. Aktywne projekty w work/:"
	@found=0; \
	for d in work/*/; do \
		[ -d "$$d" ] || continue; \
		b=$$(basename "$$d"); \
		if [ "$$b" = "voice_sample" ] || [ "$$b" = "archive" ] || [ "$$b" = "latest" ]; then continue; fi; \
		found=1; \
		in_cnt=$$(find "$$d/input" -maxdepth 1 -type f 2>/dev/null | wc -l); \
		run_cnt=$$(find "$$d/runs" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l); \
		latest_target=$$(readlink "$$d/latest" 2>/dev/null || echo "brak"); \
		echo "   * $$b (input: $$in_cnt plików, przebiegi: $$run_cnt, latest -> $$latest_target)"; \
	done; \
	if [ "$$found" -eq 0 ]; then echo "   (Brak aktywnych projektów. Użyj: make dub-init WORK=<nazwa> INPUT=<plik.mp4>)"; fi
	@echo ""
	@if [ -L "work/latest" ] && [ -f "work/latest/run_summary.json" ]; then \
		echo "3. Ostatni przebieg (work/latest -> $$(readlink work/latest)):"; \
		uv run python -c 'import json; d=json.load(open("work/latest/run_summary.json")); m=d.get("meta",{}); q=d.get("quality_analysis") or {}; print(f"   - Projekt: {m.get(\"task_slug\")} | Silnik: {d.get(\"stats\",{}).get(\"active_engine\", m.get(\"engine\"))} | Czas: {m.get(\"total_duration_seconds\")}s | Status: {q.get(\"overall_quality_status\", \"N/A\")}")'; \
	fi
	@echo "=========================================================="

media-setup-models:
	@chmod +x scripts/media/setup_models.sh
	@./scripts/media/setup_models.sh

media-extract-sample:
	@if [ -z "$(INPUT)" ] || [ -z "$(START)" ] || [ -z "$(END)" ] || [ -z "$(OUTPUT)" ]; then \
		echo "[BŁĄD] Wymagane parametry INPUT, START, END i OUTPUT. Przykład:"; \
		echo "  make media-extract-sample INPUT=work/source.wav START=00:00:12.000 END=00:00:20.300 OUTPUT=work/voice_sample/ref.wav [TRANSCRIPT=\"...\"]"; \
		exit 1; \
	fi
	@chmod +x scripts/media/extract_voice_sample.py
	@./scripts/media/extract_voice_sample.py -i "$(INPUT)" -s "$(START)" -e "$(END)" -o "$(OUTPUT)" $(if $(TRANSCRIPT),-t "$(TRANSCRIPT)")

# Aliasy zachowujące wsteczną kompatybilność:
media-dub-video: dub

media-dub-short: dub

media-dub-ep002-short:
	@$(MAKE) --no-print-directory dub WORK=EP002_Short REF_AUDIO="$(REF_AUDIO)" ENGINE="$(ENGINE)" ACCENT="$(ACCENT)" LLM_MODEL="$(LLM_MODEL)" EXPRESSIVE="$(EXPRESSIVE)"

media-dub-ep002-long:
	@$(MAKE) --no-print-directory dub WORK=EP002 REF_AUDIO="$(REF_AUDIO)" ENGINE="$(ENGINE)" ACCENT="$(ACCENT)" LLM_MODEL="$(LLM_MODEL)" EXPRESSIVE="$(EXPRESSIVE)"

media-dub-ep004-long:
	@$(MAKE) --no-print-directory dub WORK=EP004a REF_AUDIO="$(REF_AUDIO)" ENGINE="$(ENGINE)" ACCENT="$(ACCENT)" LLM_MODEL="$(LLM_MODEL)" EXPRESSIVE="$(EXPRESSIVE)"

media-test-acting:
	@chmod +x scripts/media/compare_qwen_acting.py
	@./scripts/media/compare_qwen_acting.py $(if $(TEXT),--text "$(TEXT)") $(if $(INSTRUCTION),--instruction "$(INSTRUCTION)") $(if $(MODEL),--model-id "$(MODEL)") $(if $(SPEAKER),--speaker "$(SPEAKER)") $(if $(ENGINE),--engine "$(ENGINE)") $(if $(REF_AUDIO),--ref-audio "$(REF_AUDIO)") $(if $(OUT_DIR),--output-dir "$(OUT_DIR)") $(if $(TAU),--tau "$(TAU)") $(if $(filter 1 true yes TRUE YES,$(NO_TIMBRE)),--no-timbre) $(if $(filter 1 true yes TRUE YES,$(PLAY)),--play)

media-transform-voice:
	@chmod +x scripts/media/convert_voice_timbre.py
	@./scripts/media/convert_voice_timbre.py $(if $(SOURCE),--source "$(SOURCE)") $(if $(REF),--ref "$(REF)") $(if $(OUTPUT),--output "$(OUTPUT)") $(if $(TAU),--tau "$(TAU)") $(if $(filter 1 true yes TRUE YES,$(PLAY)),--play)

media-dub-ep002: media-dub-ep002-short

media-dub-ep001:
	@$(MAKE) --no-print-directory dub WORK=EP001_Short REF_AUDIO="$(REF_AUDIO)" ENGINE="$(ENGINE)" ACCENT="$(ACCENT)" LLM_MODEL="$(LLM_MODEL)" EXPRESSIVE="$(EXPRESSIVE)"

media-dub-batch:
	@chmod +x scripts/media/dub_video.py
	@./scripts/media/dub_video.py --batch EP002_Short EP001_Short $(if $(REF_AUDIO),--ref-audio "$(REF_AUDIO)") --engine "$(DUB_ENGINE)" $(if $(ACCENT),--accent "$(ACCENT)") $(if $(LLM_MODEL),--llm-model "$(LLM_MODEL)") $(DUB_EXPRESSIVE_FLAG)

media-voiceover:
	@if [ -z "$(SCRIPT)" ]; then \
		echo "[BŁĄD] Wymagany parametr SCRIPT. Przykład:"; \
		echo "  make media-voiceover SCRIPT=/path/to/voiceover_read_script.md [WORK_DIR=work/EP004] [SECTION='WIESZAK 1']"; \
		exit 1; \
	fi
	@chmod +x scripts/media/generate_voiceover.py
	@./scripts/media/generate_voiceover.py -s "$(SCRIPT)" $(if $(WORK_DIR),-w "$(WORK_DIR)") $(if $(REF_AUDIO),--ref-audio "$(REF_AUDIO)") $(if $(SECTION),--section "$(SECTION)") $(if $(LIMIT),--limit "$(LIMIT)")

media-dub-clean:
	@echo "Czyszczenie wygenerowanych przebiegów dubbingu (runs/latest/output) w work/<projekt>/..."
	@for d in work/*/; do \
		b=$$(basename "$$d"); \
		if [ "$$b" = "voice_sample" ] || [ "$$b" = "archive" ]; then continue; fi; \
		rm -rf "$$d/runs" "$$d/latest" "$$d/output" 2>/dev/null || true; \
	done
	@rm -f work/latest 2>/dev/null || true
	@echo "[OK] Wyczyszczono artefakty przebiegów. Pliki w work/voice_sample/, work/archive/ oraz work/*/input/ zachowane."

# --- Google Drive Selektywna Synchronizacja (rclone) ---

gdrive-status:
	@chmod +x scripts/gdrive_ctl.sh
	@./scripts/gdrive_ctl.sh status

gdrive-install:
	@chmod +x scripts/gdrive_ctl.sh
	@./scripts/gdrive_ctl.sh install

gdrive-auth:
	@chmod +x scripts/gdrive_ctl.sh
	@./scripts/gdrive_ctl.sh auth

gdrive-list:
	@chmod +x scripts/gdrive_ctl.sh
	@./scripts/gdrive_ctl.sh list-remote "$(PATH)"

gdrive-folders:
	@chmod +x scripts/gdrive_ctl.sh
	@./scripts/gdrive_ctl.sh list-folders

gdrive-add:
	@if [ -z "$(REMOTE)" ]; then \
		echo "[BŁĄD] Wymagany parametr REMOTE. Przykład:"; \
		echo "  make gdrive-add REMOTE=KeePass [LOCAL=KeePass] [MODE=bisync] [DESC=\"Baza haseł\"]"; \
		exit 1; \
	fi
	@chmod +x scripts/gdrive_ctl.sh
	@./scripts/gdrive_ctl.sh add-folder "$(REMOTE)" "$(LOCAL)" "$(or $(MODE),bisync)" "$(DESC)"

gdrive-remove:
	@if [ -z "$(REMOTE)" ]; then \
		echo "[BŁĄD] Wymagany parametr REMOTE. Przykład:"; \
		echo "  make gdrive-remove REMOTE=KeePass"; \
		exit 1; \
	fi
	@chmod +x scripts/gdrive_ctl.sh
	@./scripts/gdrive_ctl.sh remove-folder "$(REMOTE)"

gdrive-sync:
	@chmod +x scripts/gdrive_ctl.sh
	@DRY_RUN="$(DRY_RUN)" RESYNC="$(RESYNC)" ./scripts/gdrive_ctl.sh sync "$(FOLDER)"

gdrive-timer-enable:
	@chmod +x scripts/gdrive_ctl.sh
	@./scripts/gdrive_ctl.sh timer-enable "$(INTERVAL)"

gdrive-timer-disable:
	@chmod +x scripts/gdrive_ctl.sh
	@./scripts/gdrive_ctl.sh timer-disable

gdrive-mount:
	@chmod +x scripts/gdrive_ctl.sh
	@./scripts/gdrive_ctl.sh mount "$(REMOTE_PATH)" "$(MOUNTPOINT)"

gdrive-unmount:
	@chmod +x scripts/gdrive_ctl.sh
	@./scripts/gdrive_ctl.sh unmount "$(MOUNTPOINT)"

# --- Czytnik Tekstu TTS (Select & Listen: Edge Neural TTS) ---

tts-status:
	@chmod +x scripts/tts_ctl.sh
	@./scripts/tts_ctl.sh status

tts-install:
	@chmod +x scripts/tts_ctl.sh
	@./scripts/tts_ctl.sh install

tts-config:
	@chmod +x scripts/tts_ctl.sh
	@./scripts/tts_ctl.sh config

tts-test:
	@chmod +x scripts/tts_ctl.sh
	@./scripts/tts_ctl.sh test

tts-uninstall:
	@chmod +x scripts/tts_ctl.sh
	@./scripts/tts_ctl.sh uninstall

