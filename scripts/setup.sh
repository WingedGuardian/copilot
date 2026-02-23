#!/usr/bin/env bash
# =============================================================================
# Nanobot Copilot — Quick Setup
# =============================================================================
# Run from the repo root: bash scripts/setup.sh
#
# What it does:
#   1. Creates ~/.nanobot/ directory
#   2. Copies config + secrets templates (won't overwrite existing)
#   3. Installs Python dependencies
#   4. Validates the setup
# =============================================================================

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
info() { echo -e "${CYAN}[i]${NC} $*"; }
fail() { echo -e "${RED}[x]${NC} $*"; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NANOBOT_DIR="$HOME/.nanobot"
FAILURES=0

echo ""
echo "============================================="
echo "  Nanobot Copilot — Setup"
echo "============================================="
echo ""

# ---- Check prerequisites ----
info "Checking prerequisites..."

if [ "$(id -u)" -eq 0 ]; then
    fail "Don't run as root."
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    fail "Python 3 not found. Install Python 3.11+ first."
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python version: $PY_VERSION"

# ---- Create ~/.nanobot/ ----
info "Setting up $NANOBOT_DIR..."
mkdir -p "$NANOBOT_DIR"
mkdir -p "$NANOBOT_DIR/workspace"
mkdir -p "$NANOBOT_DIR/logs"
mkdir -p "$NANOBOT_DIR/sessions"
log "Directory structure created"

# ---- Copy templates (never overwrite) ----
if [ ! -f "$NANOBOT_DIR/config.json" ]; then
    cp "$REPO_DIR/config.json.template" "$NANOBOT_DIR/config.json"
    log "config.json created from template"
    warn "Edit ~/.nanobot/config.json to configure your providers and channels"
else
    log "config.json already exists (skipped)"
fi

if [ ! -f "$NANOBOT_DIR/secrets.json" ]; then
    cp "$REPO_DIR/secrets.json.template" "$NANOBOT_DIR/secrets.json"
    chmod 600 "$NANOBOT_DIR/secrets.json"
    log "secrets.json created from template (mode 600)"
    warn "Edit ~/.nanobot/secrets.json to add your API keys"
else
    log "secrets.json already exists (skipped)"
fi

# ---- Install Python dependencies ----
info "Installing Python dependencies..."

cd "$REPO_DIR"
if command -v uv &>/dev/null; then
    uv pip install -e . 2>&1 | tail -1
    log "Dependencies installed (uv)"
elif [ -d ".venv" ]; then
    source .venv/bin/activate
    pip install -e . 2>&1 | tail -1
    log "Dependencies installed (venv pip)"
else
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e . 2>&1 | tail -1
    log "Created .venv and installed dependencies"
fi

# ---- Validate ----
echo ""
info "Validating setup..."

# Check config is valid JSON
if python3 -c "import json; json.load(open('$NANOBOT_DIR/config.json'))" 2>/dev/null; then
    log "config.json is valid JSON"
else
    fail "config.json is not valid JSON"
    FAILURES=$((FAILURES+1))
fi

# Check secrets is valid JSON
if python3 -c "import json; json.load(open('$NANOBOT_DIR/secrets.json'))" 2>/dev/null; then
    log "secrets.json is valid JSON"
else
    fail "secrets.json is not valid JSON"
    FAILURES=$((FAILURES+1))
fi

# Check secrets file permissions
PERMS=$(stat -c %a "$NANOBOT_DIR/secrets.json" 2>/dev/null || stat -f %Lp "$NANOBOT_DIR/secrets.json" 2>/dev/null)
if [ "$PERMS" = "600" ]; then
    log "secrets.json permissions OK (600)"
else
    warn "secrets.json permissions are $PERMS (should be 600)"
    chmod 600 "$NANOBOT_DIR/secrets.json"
    log "Fixed secrets.json permissions to 600"
fi

# Check if at least one provider has a real API key
HAS_KEY=$(python3 -c "
import json
with open('$NANOBOT_DIR/secrets.json') as f:
    s = json.load(f)
providers = s.get('providers', {})
for name, cfg in providers.items():
    key = cfg.get('apiKey', '')
    if key and not key.endswith('...') and key != 'lm-studio':
        print('yes')
        break
else:
    print('no')
" 2>/dev/null)

if [ "$HAS_KEY" = "yes" ]; then
    log "At least one provider API key is configured"
else
    warn "No provider API keys configured yet — edit ~/.nanobot/secrets.json"
fi

# Check nanobot importable
if python3 -c "import nanobot" 2>/dev/null; then
    log "nanobot package is importable"
else
    fail "nanobot package not importable — check installation"
    FAILURES=$((FAILURES+1))
fi

# ---- Summary ----
echo ""
echo "============================================="
if [ "$FAILURES" -eq 0 ]; then
    echo -e "  ${GREEN}Setup complete${NC}"
else
    echo -e "  ${RED}Setup complete with $FAILURES issue(s)${NC}"
fi
echo "============================================="
echo ""
info "Next steps:"
echo "  1. Edit ${CYAN}~/.nanobot/secrets.json${NC} — add your API keys"
echo "  2. Edit ${CYAN}~/.nanobot/config.json${NC}  — enable channels, set default model"
echo "  3. Run:  ${CYAN}nanobot${NC}  (or: python -m nanobot)"
echo ""
info "Optional (copilot mode):"
echo "  - Install Qdrant: https://qdrant.tech/documentation/quick-start/"
echo "  - Set copilot.enabled=true in config.json"
echo "  - Add copilot API keys to secrets.json (cloudEmbeddingApiKey, etc.)"
echo ""
