<!-- Read by the routing planner when creating/updating routing plans. -->
<!-- Auto-updated by dream cycle (weekly) and heartbeat (on failover events). -->
<!-- Do NOT merge with models.md — that file serves the orchestrator. -->

# Routing Directory

## Configured Providers
_Last refreshed: 2026-02-20 by initial setup_

| Provider | API Key | Health | Default Model | Cost/MTok (in/out) | Free Tier | Constraints |
|----------|---------|--------|--------------|-------------------|-----------|-------------|
| openai | yes | healthy | gpt-4o | $2.50/$10.00 | none | Direct API |
| gemini | yes | healthy | gemini-3-flash-preview | $0.00/$0.00 | 1500 RPD, 15 RPM | Google AI free tier; data MAY be used for training; resets midnight PT |
| minimax | yes | healthy | MiniMax-M2.5 | $0.30/$1.20 | none | Direct API via api.minimax.io |
| venice | yes | healthy | (gateway) | varies | none | OpenAI-compatible gateway |
| nvidia | yes | untested | moonshotai/kimi-k2.5 | $0.00 | ~5000 credits TOTAL | Credits do NOT refresh; best for testing only |
| groq | yes | rate-limited | llama-3.3-70b | $0.00 | 12K TPM | Very small quota, exhaust quickly on long conversations |
| openrouter | yes | DOWN (401) | (gateway) | varies | none | Auth failure since Feb 19 — key may be revoked |
| anthropic | no | — | — | — | — | No direct API key configured |
| deepseek | no | — | — | — | — | |
| zhipu | no | — | — | — | — | |

## Free Tier Terms & Gotchas

### Gemini (Google AI Studio)
- 1500 RPD, 15 RPM for gemini-3-flash-preview
- Free tier data MAY be used for training — do NOT send proprietary/sensitive data
- Limits can change without warning (Google cut them 50-80% in Dec 2025)
- EU/EEA/UK/Switzerland restricted

### Nvidia NIM
- ~5000 total credits across ALL models (NOT per-model)
- Credits do NOT refresh — once gone, they're gone
- 40 RPM limit
- Available: Kimi K2.5, Llama 4 Scout, DeepSeek V3.2, GLM-5

### Groq
- 12,000 TPM — a single long conversation can exhaust this
- Best for short, fast queries only

## Current Routing Plan
(none configured — using default: MiniMax-M2.5 on all providers)

## Escalation Model
anthropic/claude-sonnet-4-6

## Mandatory Safety Net (always appended by system)
1. Last known working provider/model
2. LM Studio local (when online)
3. openai/gpt-4o-mini on all providers (emergency)

## User Preferences
(none recorded yet — user can say "keep costs low" or "leverage free tiers" and the routing planner will create a plan accordingly)
