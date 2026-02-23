# Copilot

An autonomous AI copilot built on [nanobot](https://github.com/HKUDS/nanobot). Multi-provider LLM routing, episodic memory, cognitive background services, and multi-channel messaging (WhatsApp, Telegram, Discord, Slack, Email).

## Quick Start

```bash
# Clone
git clone https://github.com/WingedGuardian/copilot.git
cd copilot

# Run setup (creates ~/.nanobot/, copies templates, installs deps)
bash scripts/setup.sh

# Add your API keys
nano ~/.nanobot/secrets.json

# Configure providers and channels
nano ~/.nanobot/config.json

# Start
nanobot
```

The web UI will be available at `http://localhost:18790`.

## Configuration

All runtime config lives in `~/.nanobot/` (not in the repo):

| File | Purpose |
|------|---------|
| `config.json` | Providers, channels, copilot settings, gateway config |
| `secrets.json` | API keys, tokens, passwords (mode 600) |

Templates are in the repo root: `config.json.template` and `secrets.json.template`.

The config loader automatically merges `secrets.json` on top of `config.json` at startup. API keys in config.json are extracted to secrets.json on save.

### Minimal config (one provider)

**config.json:**
```json
{
  "agents": { "defaults": { "model": "gpt-4o" } },
  "providers": { "openai": { "defaultModel": "gpt-4o" } }
}
```

**secrets.json:**
```json
{
  "providers": { "openai": { "apiKey": "sk-..." } }
}
```

### Copilot mode

Set `copilot.enabled: true` in config.json for cognitive features:
- Episodic memory (requires [Qdrant](https://qdrant.tech/documentation/quick-start/))
- Dream cycle (nightly memory consolidation)
- Health checks and monitoring
- Multi-model routing with automatic failover
- Weekly/monthly strategic reviews

See `config.json.template` for all copilot settings.

## Channels

Enable channels in `config.json`, add tokens in `secrets.json`:

| Channel | Config key | Requires |
|---------|-----------|----------|
| WhatsApp | `channels.whatsapp` | WhatsApp bridge (`bridge/`) |
| Telegram | `channels.telegram` | Bot token from @BotFather |
| Discord | `channels.discord` | Bot token + gateway intents |
| Slack | `channels.slack` | Bot + app tokens |
| Email | `channels.email` | IMAP/SMTP credentials |

## Project Structure

```
nanobot/              # Core Python package
  agent/              # LLM agent, tools, routing
  copilot/            # Copilot extensions (dream cycle, memory, health)
  channels/           # Channel adapters (WhatsApp, Telegram, etc.)
  config/             # Config schema + loader
  web/                # Web UI + API routes
data/copilot/         # Runtime identity files (heartbeat.md, dream.md, etc.)
workspace/            # Runtime workspace (SOUL.md, MEMORY.md, etc.)
bridge/               # WhatsApp bridge (Node.js)
scripts/              # Setup and utility scripts
```

## License

See upstream [nanobot](https://github.com/HKUDS/nanobot) for license terms.
