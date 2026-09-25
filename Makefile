.PHONY: help audit inventory all-audits session-status session-log check restore-dry-run

# Domyślny cel
help:
	@echo "=========================================================="
	@echo "  WORKSTATION HUB — SYSTEM CONTROL INTERFACE"
	@echo "=========================================================="
	@echo "Dostępne komendy:"
	@echo "  make audit           - Wykonuje audyt fizycznego sprzętu (CPU, RAM, Storage, GPU, Audio, Kamery)"
	@echo "  make inventory       - Wykonuje inwentaryzację oprogramowania (APT, Flatpak, Repozytoria, Runtimes)"
	@echo "  make all-audits      - Uruchamia pełny zestaw audytów (sprzęt + oprogramowanie)"
	@echo "  make session-status  - Wyświetla aktualny stan z memory/SESSION_STATE.md"
	@echo "  make session-log MSG=\"...\" - Dopisuje wpis ze znacznikiem czasu do memory/JOURNAL.md"
	@echo "  make check           - Sprawdza integralność plików pamięci i inwentarza"
	@echo "  make restore-dry-run - Symuluje procedurę odtworzenia Disaster Recovery bez wprowadzania zmian"
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
