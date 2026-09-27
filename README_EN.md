# `pl-agentic-sysadmin` — Autonomous Workstation Hub & Agentic SysAdmin Protocol

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Channel: MnemoShift](https://img.shields.io/badge/YouTube-MnemoShift-red.svg)](https://www.youtube.com/@mnemoshift)

> 🇵🇱 **Polska Wersja:** Szukasz dokumentacji w języku polskim? [Przejdź do README.md](README.md).

> *Autonomous workstation control center, hardware audit, and disaster recovery protocol built for persistent Agentic AI workflows (Antigravity IDE, Claude Code) on Linux.*

The traditional approach to Linux desktop configuration (manual terminal tinkering, fragile dotfile symlinks, and browser chatbot amnesia) fails in the agentic era. **`pl-agentic-sysadmin`** transforms your Git repository into a living workstation hub that equips an AI agent with **eyes** (deterministic hardware audit), **hands** (declarative Makefile scripts), and **dual-layer persistence**.

---

## 📺 Video Screencast (YouTube)

Full walkthrough showing the contrast between 47 minutes of manual terminal configuration and a 60-second Agentic SysAdmin workflow:
* 🎬 **MnemoShift EP002:** *"Commands Are in the Man Pages." Why I Delegated Linux Config to an AI Agent* — **[Watch on YouTube](https://www.youtube.com/watch?v=wEVas1TWCns)**  
  *(Note: Audio is available in both Polish and English via YouTube's Multi-Language Audio feature).*

---

## 🚀 Quick Start: Running with Antigravity 2.0

### Step 1: Clone the Repository
Clone the hub into your local workspace directory:
```bash
git clone https://github.com/mnemoshift/pl-agentic-sysadmin.git ~/workspaces/pl-agentic-sysadmin
cd ~/workspaces/pl-agentic-sysadmin
```

### Step 2: Open and Configure in Antigravity 2.0
1. Launch **Antigravity 2.0** (from the Zorin application menu or via terminal: `antigravity`).
2. In the left sidebar, navigate to **Projects** $\rightarrow$ click **Add Project** (or **Open Folder**) and select:  
   `~/workspaces/pl-agentic-sysadmin`
3. **Security & Review Configuration:**
   * Open **Agent Settings $\rightarrow$ Security Preset** and set to `Default` (the agent will ask for confirmation before executing shell commands).
   * Set **Agent Behavior $\rightarrow$ Artifact Review Policy** to `Always Ask` (the agent will present an *Implementation Plan* before touching system configs).
   * *Tip: Once trust is established, you can relax these constraints for autonomous hands-free execution.*
4. **Ready!** The agent immediately bootstraps by reading `AGENTS.md` and loading the `desktop-manager` core skill.

---

## ⚡ Operational Interface (Makefile)

Prefer working directly from the command line? All agentic procedures are exposed via a deterministic Makefile:

```bash
# Display all available commands and descriptions
make help

# 🖥️ Desktop Profile Management (Featured in EP002)
make desktop-macos   # Deploy macOS broadcast profile (WhiteSur theme, left controls, Plank, CSD fix)
make desktop-reset   # Instant vanilla reset back to factory Zorin OS desktop (1 second)
make desktop-status  # Audit window decorations, Zorin panel position, and Plank state

# 🔍 System Audit & Disaster Recovery
make audit           # Audit CPU, RAM, GPU, audio daemons, cameras, and display outputs
make inventory       # Living inventory of installed APT packages, Flatpaks, and repositories
make restore-dry-run # Safe dry-run simulation of workstation disaster recovery
```

---

## 🏛️ Architecture: 4 Pillars of the System

```mermaid
graph TD
    User([Engineer / Architect / You]) <--> Agent[AI Agent in Antigravity 2.0]
    
    subgraph Protocol & Persistence
        AGENTS[AGENTS.md - Zero-Guessing Rule]
        STATE[memory/SESSION_STATE.md - Active RAM]
        MEMORY[memory/JOURNAL.md - Append-only Disk ISO]
    end

    subgraph Diagnostics & Facts
        Audit[scripts/audit_hardware.sh & make audit]
        Inventory[inventory/ - Living Resource List]
        Make[Makefile - Deterministic CLI Surface]
    end

    subgraph Skills & Adaptation
        Skills[.agents/skills/ - Core & Local Skills]
        LocalScripts[scripts/local_* - Idempotent Bash Scripts]
    end

    Agent --> AGENTS
    Agent <--> STATE
    Agent --> MEMORY
    Agent --> Audit
    Agent --> Inventory
    Agent --> Make
    Agent --> Skills
    Agent --> LocalScripts
```

### 1. The Zero-Guessing Rule & Conflict-Free Upstream Sync (`AGENTS.md` + `AGENTS.local.md`)
The AI agent **is never allowed to guess** your hardware state or user preferences. Every change begins with an automated pre-flight audit, executes atomically with backups, and concludes with post-flight verification.

To prevent merge hell, the framework strictly decouples upstream core logic (`AGENTS.md`) from your machine-specific overrides (`AGENTS.local.md`, git-ignored). You can run `git pull` anytime to receive framework updates without conflicting with your private multi-monitor setup or local sound routing.

### 2. Dual-Layer Cross-Session Memory
- **`memory/SESSION_STATE.md` (Working RAM):** Tracks the immediate objective, active session goals, and recently completed tasks.
- **`memory/JOURNAL.md` (Persistent Disk):** An append-only, ISO date-stamped (`[YYYY-MM-DD]`) record of architectural decisions, completed configurations, and operational milestones.

### 3. Core Skills vs. Local Skills
- **Core Skills (`.agents/skills/`):** Universal procedures versioned in Git (e.g., `desktop-manager`, addressing CSD quirks in Electron/Chromium apps).
- **Local Skills (`.agents/skills/local-*/`):** Machine-specific adaptations generated on-the-fly by the agent (e.g., custom 3-monitor geometry or RNNoise microphone filters), safely kept inside `.gitignore`.

### 4. Living Inventory & Disaster Recovery
Every installed tool, library, and system extension is continuously logged in `inventory/`. In the event of a disk failure or machine migration, `make restore-dry-run` and `scripts/restore_workstation.sh` recreate the entire developer environment in under 3 minutes.

---

## 📄 License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.
