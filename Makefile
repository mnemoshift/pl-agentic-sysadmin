.PHONY: help audit inventory all-audits session-status session-log check restore-dry-run desktop-macos desktop-reset desktop-status media-check-mcp media-setup-mcp media-clean-audio media-karaoke media-build-short

# Domyślny cel
help:
	@echo "=========================================================="
	@echo "  WORKSTATION HUB — SYSTEM CONTROL INTERFACE"
	@echo "=========================================================="
	@echo "Dostępne komendy:"
	@echo "  make audit           - Wykonuje audyt fizycznego sprzętu (CPU, RAM, Storage, GPU, Audio, Kamery)"
	@echo "  make inventory       - Wykonuje inwentaryzację oprogramowania (APT, Flatpak, Repozytoria, Runtimes)"
	@echo "  make all-audits      - Uruchamia pełny zestaw audytów (sprzęt + oprogramowanie)"
	@echo "  make desktop-macos   - Wdraża profil emisyjny macOS (WhiteSur, traffic lights po lewej, Plank, CSD)"
	@echo "  make desktop-reset   - Przywraca stan fabryczny pulpitu Zorin OS (kropki po prawej, pasek na dole)"
	@echo "  make desktop-status  - Sprawdza aktywny stan konfiguracji pulpitu i doku"
	@echo "  make session-status  - Wyświetla aktualny stan z memory/SESSION_STATE.md"
	@echo "  make session-log MSG=\"...\" - Dopisuje wpis ze znacznikiem czasu do memory/JOURNAL.md"
	@echo "  make check           - Sprawdza integralność plików pamięci i inwentarza"
	@echo "  make restore-dry-run - Symuluje procedurę odtworzenia Disaster Recovery bez wprowadzania zmian"
	@echo "  --- Narzędzia Wideo & Audio (Kdenlive & Studio) ---"
	@echo "  make media-check-mcp - Sprawdza stan Kdenlive, wrapperów CLI i serwera MCP"
	@echo "  make media-setup-mcp - Instaluje Kdenlive (Flatpak user) i konfiguruje serwer MCP"
	@echo "  make media-clean-audio INPUT=... OUTPUT=... [START=...] [END=...] [LUFS=-14.0]"
	@echo "  make media-karaoke AUDIO=... OUTPUT=... [FAST=1] [FONT=...]"
	@echo "  make media-build-short WORKSPACE=... [NAME=EP002_Short]"
	@echo "=========================================================="

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
	@test -f recovery/DISASTER_RECOVERY.md && echo "  [✓] recovery/DISASTER_RECOVERY.md obecny" || echo "  [✗] Brak recovery/DISASTER_RECOVERY.md"

restore-dry-run:
	@chmod +x scripts/restore_workstation.sh
	@./scripts/restore_workstation.sh --dry-run

desktop-macos:
	@chmod +x scripts/desktop_ctl.sh
	@./scripts/desktop_ctl.sh apply-macos

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
		echo "  make media-karaoke AUDIO=voice.wav OUTPUT=subtitles.ass [FAST=1]"; \
		exit 1; \
	fi
	@chmod +x scripts/media/generate_karaoke.py
	@uv run scripts/media/generate_karaoke.py -a "$(AUDIO)" -o "$(OUTPUT)" \
		$(if $(FAST),--fast) \
		$(if $(FONT),--font "$(FONT)") \
		$(if $(HIGHLIGHT),--highlight "$(HIGHLIGHT)")

media-build-short:
	@if [ -z "$(WORKSPACE)" ]; then \
		echo "[BŁĄD] Wymagany parametr WORKSPACE. Przykład:"; \
		echo "  make media-build-short WORKSPACE=~/workspaces/EP002_Short [NAME=EP002_Short]"; \
		exit 1; \
	fi
	@chmod +x scripts/media/build_kdenlive_short.py
	@./scripts/media/build_kdenlive_short.py -w "$(WORKSPACE)" $(if $(NAME),-n "$(NAME)")

media-check-mcp:
	@chmod +x scripts/media/setup_kdenlive_mcp.sh
	@./scripts/media/setup_kdenlive_mcp.sh --check

media-setup-mcp:
	@chmod +x scripts/media/setup_kdenlive_mcp.sh
	@./scripts/media/setup_kdenlive_mcp.sh --setup


