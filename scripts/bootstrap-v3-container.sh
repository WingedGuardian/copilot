#!/usr/bin/env bash
# =============================================================================
# Genesis v3 Container Bootstrap Script
# =============================================================================
#
# Run this INSIDE a fresh Incus container (Ubuntu 24.04) to set up:
#   1. System dependencies
#   2. Claude Code (interactive + subprocess-invocable) with max permissions
#   3. Agent Zero
#   4. OpenCode
#   5. Genesis repo + directory structure
#
# BEFORE RUNNING THIS SCRIPT:
# ----------------------------
# From the Incus HOST, create and configure the container:
#
#   # Create container
#   incus launch ubuntu:24.04 genesis-v3
#
#   # Allocate resources (adjust to your host capacity)
#   incus config set genesis-v3 limits.memory=8GB
#   incus config set genesis-v3 limits.cpu=4
#
#   # Expand root disk (default 10GB is too small)
#   incus config device override genesis-v3 root size=40GB
#   # OR if using LVM:
#   # incus storage volume set default containers/genesis-v3 size=40GB
#
#   # Network: allow genesis-v3 to reach claude-agent's Qdrant
#   # Option A - containers on same bridge (check with: incus list)
#   #   They can reach each other by IP already
#   # Option B - proxy device:
#   #   incus config device add genesis-v3 qdrant proxy \
#   #     listen=tcp:0.0.0.0:6333 connect=tcp:<claude-agent-ip>:6333
#
#   # Enter the container
#   incus exec genesis-v3 -- sudo -u ubuntu -i
#
#   # Copy this script in (from host or curl from GitHub)
#   # Then run it:
#   bash bootstrap-v3-container.sh
#
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
info() { echo -e "${CYAN}[i]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# =============================================================================
# Section 1: System Dependencies
# =============================================================================
section_system() {
    info "Installing system dependencies..."

    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        git curl wget build-essential \
        python3 python3-venv python3-dev python3-pip \
        nodejs npm \
        sqlite3 jq ripgrep fd-find unzip \
        tmux htop \
        > /dev/null 2>&1

    log "System packages installed"

    # uv (fast Python package manager)
    if ! command -v uv &>/dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh 2>/dev/null
        export PATH="$HOME/.local/bin:$PATH"
        log "uv installed"
    else
        log "uv already installed"
    fi

    # GitHub CLI
    if ! command -v gh &>/dev/null; then
        curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
            sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | \
            sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
        sudo apt-get update -qq && sudo apt-get install -y -qq gh > /dev/null 2>&1
        log "GitHub CLI installed"
    else
        log "GitHub CLI already installed"
    fi
}

# =============================================================================
# Section 2: Claude Code
# =============================================================================
section_claude_code() {
    info "Installing Claude Code..."

    # Install via npm
    if ! command -v claude &>/dev/null; then
        sudo npm install -g @anthropic-ai/claude-code 2>/dev/null
        log "Claude Code installed: $(claude --version 2>/dev/null || echo 'check manually')"
    else
        log "Claude Code already installed: $(claude --version)"
    fi

    # Create config directory
    mkdir -p ~/.claude

    # ---------------------------------------------------------------------------
    # Global settings — maximum autonomy for sandboxed container
    #
    # This container IS the sandbox. Claude Code gets full permissions because
    # the Incus container boundary is the security perimeter, not the tool
    # permission system. This matches the claude-agent container's effective
    # permissions but without the incremental allow-list — just open everything.
    # ---------------------------------------------------------------------------
    cat > ~/.claude/settings.json << 'SETTINGS_EOF'
{
  "permissions": {
    "defaultMode": "bypassPermissions",
    "allow": [
      "Bash(*)",
      "Edit(*)",
      "Write(*)",
      "Read(*)",
      "Glob(*)",
      "Grep(*)",
      "WebSearch",
      "WebFetch(domain:*)",
      "Task(*)",
      "NotebookEdit(*)"
    ]
  },
  "skipDangerousModePermissionPrompt": true,
  "enabledPlugins": {
    "context7@claude-plugins-official": true,
    "code-review@claude-plugins-official": true,
    "github@claude-plugins-official": true,
    "feature-dev@claude-plugins-official": true,
    "superpowers@claude-plugins-official": true,
    "playwright@claude-plugins-official": true,
    "commit-commands@claude-plugins-official": true,
    "serena@claude-plugins-official": true,
    "plugin-dev@claude-plugins-official": true,
    "claude-md-management@claude-plugins-official": true,
    "firecrawl@claude-plugins-official": true,
    "frontend-design@claude-plugins-official": true,
    "code-simplifier@claude-plugins-official": true,
    "pinecone@claude-plugins-official": true,
    "coderabbit@claude-plugins-official": true,
    "huggingface-skills@claude-plugins-official": true,
    "playground@claude-plugins-official": true
  }
}
SETTINGS_EOF
    log "Claude Code global settings configured (bypassPermissions mode)"

    warn "ACTION REQUIRED: Authenticate Claude Code"
    warn "  Run: claude auth login"
    warn "  This links your Anthropic subscription (interactive)"
}

# =============================================================================
# Section 3: Agent Zero
# =============================================================================
section_agent_zero() {
    info "Installing Agent Zero..."

    local AZ_DIR="$HOME/agent-zero"

    if [ ! -d "$AZ_DIR" ]; then
        git clone https://github.com/frdel/agent-zero.git "$AZ_DIR"
        log "Agent Zero cloned"
    else
        log "Agent Zero already cloned"
    fi

    cd "$AZ_DIR"

    # Create venv
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
        log "Agent Zero venv created"
    fi

    source .venv/bin/activate
    pip install -q -r requirements.txt 2>/dev/null
    log "Agent Zero dependencies installed"

    # Also install the Anthropic SDK in Agent Zero's venv
    # (for the Claude SDK tool — programmatic API access)
    pip install -q anthropic 2>/dev/null
    log "Anthropic SDK installed in Agent Zero venv"

    # Create .env template (user fills in API keys)
    if [ ! -f ".env" ]; then
        cat > .env << 'ENV_EOF'
# =============================================================================
# Agent Zero Configuration — Genesis v3
# =============================================================================

# --- Model Configuration (via LiteLLM) ---
CHAT_MODEL=anthropic/claude-sonnet-4-6
UTILITY_MODEL=anthropic/claude-haiku-4-5
EMBEDDING_MODEL=text-embedding-3-small
BROWSER_MODEL=anthropic/claude-sonnet-4-6

# --- API Keys (fill in yours) ---
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=

# --- Optional: Bedrock/Vertex for cost optimization ---
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=
# AWS_REGION_NAME=us-east-1
# VERTEX_PROJECT=
# VERTEX_LOCATION=

# --- Agent Zero Settings ---
WEB_UI_PORT=8080

# --- Genesis-specific ---
# Qdrant endpoint (on the claude-agent container)
# Update this IP after checking: incus list  (from host)
QDRANT_URL=http://REPLACE_WITH_CLAUDE_AGENT_IP:6333
ENV_EOF
        log "Agent Zero .env template created"
        warn "ACTION REQUIRED: Edit ~/agent-zero/.env — fill in API keys + Qdrant URL"
    else
        log "Agent Zero .env already exists"
    fi

    deactivate
    cd "$HOME"
}

# =============================================================================
# Section 4: OpenCode
# =============================================================================
section_opencode() {
    info "Installing OpenCode..."

    if ! command -v opencode &>/dev/null; then
        # Try the official install script first
        curl -fsSL https://opencode.ai/install.sh 2>/dev/null | sh 2>/dev/null && {
            log "OpenCode installed via official script"
            return
        }

        # Fallback: try go install if Go is available
        if command -v go &>/dev/null; then
            go install github.com/opencode-ai/opencode@latest 2>/dev/null && {
                log "OpenCode installed via go install"
                return
            }
        fi

        # If nothing worked, give manual instructions
        warn "Could not auto-install OpenCode"
        warn "Install manually: https://github.com/opencode-ai/opencode"
        warn "Or install Go first: sudo apt install golang-go && go install github.com/opencode-ai/opencode@latest"
    else
        log "OpenCode already installed"
    fi
}

# =============================================================================
# Section 5: Genesis Repo + Directory Structure
# =============================================================================
section_genesis() {
    info "Setting up Genesis workspace..."

    # v3 development workspace
    mkdir -p "$HOME/genesis-v3/mcp-servers"    # MCP server code (memory, recon, health, outreach)
    mkdir -p "$HOME/genesis-v3/extensions"      # Agent Zero extensions (cognitive layer)
    mkdir -p "$HOME/genesis-v3/tools"           # Custom tools (claude_code, opencode)
    mkdir -p "$HOME/genesis-v3/prompts"         # System prompts, SOUL.md, identity files
    mkdir -p "$HOME/genesis-v3/tests"           # Phase 0 validation tests
    log "Genesis v3 directory structure created at ~/genesis-v3/"

    warn "ACTION REQUIRED: Clone Genesis repo"
    warn "  Run: gh auth login  (if not done)"
    warn "  Then: git clone https://github.com/WingedGuardian/GENesis.git ~/genesis"
}

# =============================================================================
# Section 6: Phase 0 Validation Script
# =============================================================================
section_validation() {
    info "Creating Phase 0 validation script..."

    cat > "$HOME/genesis-v3/tests/phase0-validate.sh" << 'VALIDATE_EOF'
#!/usr/bin/env bash
# Genesis v3 — Phase 0 Validation Tests
# Run after setup is complete and all manual steps are done.
set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; FAILURES=$((FAILURES+1)); }
skip() { echo -e "${YELLOW}[SKIP]${NC} $*"; }
FAILURES=0

echo "=== Genesis v3 Phase 0 Validation ==="
echo ""

# Test 1: Claude Code basic
echo "--- Test 1: Claude Code ---"
if claude --version &>/dev/null; then
    pass "Claude Code installed: $(claude --version)"
    RESULT=$(claude -p "Reply with exactly the text: GENESIS_OK" --dangerously-skip-permissions --max-budget-usd 0.05 2>/dev/null || echo "FAILED")
    if echo "$RESULT" | grep -q "GENESIS_OK"; then
        pass "Claude Code responds correctly"
    else
        fail "Claude Code did not respond (auth issue?)"
    fi
else
    fail "Claude Code not installed"
fi

# Test 2: Claude Code subprocess mode (Agent Zero will use this)
echo "--- Test 2: Claude CLI subprocess mode ---"
OUTPUT=$(claude --print -p "Print only: subprocess_ok" --dangerously-skip-permissions --max-budget-usd 0.05 2>/dev/null || echo "")
if echo "$OUTPUT" | grep -qi "subprocess_ok"; then
    pass "Claude CLI subprocess mode works (Agent Zero can invoke this)"
else
    fail "Claude CLI subprocess mode failed"
fi

# Test 3: Agent Zero Python environment
echo "--- Test 3: Agent Zero ---"
if [ -f "$HOME/agent-zero/run_ui.py" ]; then
    cd "$HOME/agent-zero" && source .venv/bin/activate
    python3 -c "print('Agent Zero venv OK')" 2>/dev/null && \
        pass "Agent Zero Python environment OK" || \
        fail "Agent Zero venv broken"
    deactivate && cd "$HOME"
else
    fail "Agent Zero not found at ~/agent-zero/"
fi

# Test 4: Qdrant connectivity
echo "--- Test 4: Qdrant ---"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
if curl -sf "$QDRANT_URL/collections" >/dev/null 2>&1; then
    COLLECTIONS=$(curl -sf "$QDRANT_URL/collections" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['result']['collections']))" 2>/dev/null || echo "?")
    pass "Qdrant reachable at $QDRANT_URL ($COLLECTIONS collections)"
else
    fail "Qdrant not reachable at $QDRANT_URL — check container networking"
fi

# Test 5: OpenCode
echo "--- Test 5: OpenCode ---"
if command -v opencode &>/dev/null; then
    pass "OpenCode installed"
else
    skip "OpenCode not installed (install manually if needed)"
fi

# Test 6: GitHub CLI
echo "--- Test 6: GitHub CLI ---"
if gh auth status &>/dev/null 2>&1; then
    pass "GitHub CLI authenticated"
else
    fail "GitHub CLI not authenticated (run: gh auth login)"
fi

# Test 7: Anthropic SDK
echo "--- Test 7: Anthropic SDK ---"
if python3 -c "import anthropic; print(f'anthropic {anthropic.__version__}')" 2>/dev/null; then
    pass "Anthropic SDK importable"
else
    skip "Anthropic SDK not in system Python (OK if only in Agent Zero venv)"
fi

# Test 8: Disk space
echo "--- Test 8: Disk space ---"
AVAIL=$(df -BG --output=avail "$HOME" | tail -1 | tr -d ' G')
if [ "$AVAIL" -ge 10 ]; then
    pass "Disk space OK: ${AVAIL}GB free"
else
    fail "Low disk: only ${AVAIL}GB free (want 10+)"
fi

echo ""
echo "=== Results: $((8 - FAILURES))/8 passed, $FAILURES failed ==="
[ "$FAILURES" -eq 0 ] && echo -e "${GREEN}All clear — ready for Phase 0 validation tests${NC}" || \
    echo -e "${RED}Fix failures above before proceeding${NC}"
VALIDATE_EOF

    chmod +x "$HOME/genesis-v3/tests/phase0-validate.sh"
    log "Validation script created at ~/genesis-v3/tests/phase0-validate.sh"
}

# =============================================================================
# Summary
# =============================================================================
section_summary() {
    echo ""
    echo "============================================="
    echo "  Genesis v3 Container Bootstrap Complete"
    echo "============================================="
    echo ""
    info "Installed:"
    echo "  - System deps (git, python3, node, sqlite3, ripgrep, etc.)"
    echo "  - Claude Code (bypassPermissions — full autonomy)"
    echo "  - Agent Zero (~/agent-zero/)"
    echo "  - Anthropic SDK (in Agent Zero venv)"
    echo "  - OpenCode (if install succeeded)"
    echo "  - Genesis v3 workspace (~/genesis-v3/)"
    echo "  - Phase 0 validation script"
    echo ""
    warn "MANUAL STEPS (do these in order):"
    echo ""
    echo "  1. ${CYAN}claude auth login${NC}"
    echo "     Links your Anthropic subscription for interactive + subprocess use"
    echo ""
    echo "  2. ${CYAN}gh auth login${NC}"
    echo "     Authenticates GitHub CLI for repo access"
    echo ""
    echo "  3. ${CYAN}git clone https://github.com/WingedGuardian/GENesis.git ~/genesis${NC}"
    echo ""
    echo "  4. ${CYAN}nano ~/agent-zero/.env${NC}"
    echo "     Fill in: ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY, QDRANT_URL"
    echo "     (Get claude-agent IP from host: incus list)"
    echo ""
    echo "  5. ${CYAN}bash ~/genesis-v3/tests/phase0-validate.sh${NC}"
    echo "     Verify everything works"
    echo ""
    echo "  6. ${CYAN}cd ~/agent-zero && source .venv/bin/activate && python run_ui.py${NC}"
    echo "     Start Agent Zero web UI (http://<container-ip>:8080)"
    echo ""
    info "Permissions summary:"
    echo "  Claude Code:  bypassPermissions (all tools, all domains, all bash)"
    echo "  Agent Zero:   invokes Claude CLI with --dangerously-skip-permissions"
    echo "  SDK calls:    use ANTHROPIC_API_KEY (API billing, not subscription)"
    echo ""
    info "Claude Code + OpenCode coexistence:"
    echo "  - Separate config dirs (~/.claude/ vs ~/.config/opencode/)"
    echo "  - Use git worktrees for parallel file isolation"
    echo "  - Agent Zero dispatches to one or the other, never both simultaneously"
    echo ""
}

# =============================================================================
# Main
# =============================================================================
main() {
    echo "============================================="
    echo "  Genesis v3 Container Bootstrap"
    echo "============================================="
    echo ""

    if [ "$(id -u)" -eq 0 ]; then
        fail "Don't run as root. Run as your normal user (e.g. ubuntu)."
    fi

    AVAIL_GB=$(df -BG --output=avail "$HOME" | tail -1 | tr -d ' G')
    if [ "$AVAIL_GB" -lt 10 ]; then
        fail "Only ${AVAIL_GB}GB free. Need at least 10GB. Expand container disk first."
    fi
    log "Disk space OK: ${AVAIL_GB}GB available"

    section_system
    section_claude_code
    section_agent_zero
    section_opencode
    section_genesis
    section_validation
    section_summary
}

main "$@"
