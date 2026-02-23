# Genesis v3 Container — Setup Handoff

You are running inside an Incus container called `genesis`. This container is the
foundation for the Genesis v3 project — an autonomous AI agent system built on
Agent Zero + Claude SDK + OpenCode.

## Your Immediate Job

Fix the incomplete bootstrap and get this container fully operational. Then validate.

## What's Already Done

- Ubuntu 24.04 container with 166GB disk, 8GB RAM
- System deps installed: git, python3, node 20, sqlite3, jq, ripgrep, gfortran, libopenblas-dev, cmake, gh (GitHub CLI)
- Claude Code installed and authenticated (you're running on it now)
- Claude Code settings.json configured with `bypassPermissions` mode
- Agent Zero cloned at `~/agent-zero/` (v0.9.8.1, latest)
- Agent Zero `.env` template exists but API keys are NOT filled in yet

## What's Broken / Not Done

### 1. Agent Zero pip install failed repeatedly

The venv at `~/agent-zero/.venv` has a broken partial install (only ~29 packages).
The `unstructured[all-docs]` dependency pulls in scipy, scikit-learn, opencv, etc.
which kept failing due to missing build deps (now installed: gfortran, libopenblas-dev, cmake).

**Fix:** Nuke the venv and reinstall clean:
```bash
cd ~/agent-zero
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install anthropic
deactivate
```

If scipy still fails to build, use: `pip install -r requirements.txt --only-binary scipy`

### 2. Agent Zero .env needs API keys

Edit `~/agent-zero/.env` and fill in:
- `ANTHROPIC_API_KEY` (required)
- `OPENAI_API_KEY` (optional but useful)
- `GOOGLE_API_KEY` (optional)
- `QDRANT_URL` — needs the claude-agent container IP (see networking below)

### 3. Networking — Qdrant access

The existing Genesis v1 system runs in a sibling Incus container called `claude-agent`
which has Qdrant on port 6333. This container needs to reach it.

Test: `curl -s http://<claude-agent-ip>:6333/collections`

If the IP isn't known, the user needs to run `incus list` from the VM host
(`zorror@assistbot`) to get it. The containers are on the same Incus bridge
so they should be able to reach each other by IP directly.

### 4. OpenCode not installed

OpenCode is a coding tool we want alongside Claude Code. Install it:
- Try: `curl -fsSL https://opencode.ai/install.sh | sh`
- Or install Go and: `go install github.com/opencode-ai/opencode@latest`
- Manual: https://github.com/opencode-ai/opencode

### 5. GitHub CLI not authenticated

Run `gh auth login` to authenticate.

### 6. Workspace directories not created

```bash
mkdir -p ~/genesis-v3/{mcp-servers,extensions,tools,prompts,tests}
```

## Validation

After fixing everything above, test:

```bash
# Agent Zero venv works
cd ~/agent-zero && source .venv/bin/activate && python3 -c "print('OK')" && deactivate

# Qdrant reachable
curl -s http://<QDRANT_IP>:6333/collections

# Agent Zero web UI starts
cd ~/agent-zero && source .venv/bin/activate && python run_ui.py
# Should be accessible at http://<this-container-ip>:8080

# Claude Code subprocess mode (what Agent Zero will use)
claude --print -p "Reply with: subprocess_ok" --dangerously-skip-permissions

# OpenCode
opencode --version
```

## Project Context (for reference, not for immediate action)

Genesis v3 replaces the nanobot-based v1/v2 system with:
- **Agent Zero** as the core framework (LiteLLM routing, subordinate agents, extensions)
- **Claude Agent SDK** as a premium code tool (API billing — expensive, use selectively)
- **Claude CLI subprocess** as an experimental cheaper code tool (uses subscription)
- **OpenCode** as the workhorse code engine for routine tasks

The architecture docs live in the `claude-agent` container at:
`/home/ubuntu/genesis/docs/architecture/`

Key docs:
- `genesis-v3-autonomous-behavior-design.md` — primary v3 architecture
- `genesis-v3-gap-assessment.md` — pre-implementation gaps and risks
- `genesis-v3-dual-engine-plan.md` — appendix/decision history (NOT the active plan)

The GitHub repo is `WingedGuardian/GENesis` (private).

## Infrastructure

- **This container:** `genesis` (Incus, Ubuntu 24.04)
- **Sibling container:** `claude-agent` (runs nanobot v1/v2, Qdrant, existing system)
- **VM host:** `zorror@assistbot` (manages Incus containers)
- **Proxmox host:** above the VM

You cannot run `incus` commands from inside this container. Container management
happens from the VM host.
