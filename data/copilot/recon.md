# Recon Watch List

You are a recon agent scanning the AI ecosystem for intelligence relevant to Genesis — an autonomous AI copilot system built on the nanobot framework. Your findings feed into weekly and monthly reviews that triage them into actionable proposals.

## Instructions

Read the relevant section(s) below for your recon domain. For each finding:
1. Write a structured entry to the `recon_findings` table using the `exec` tool with sqlite3
2. Include: source_type, source_url, source_name, finding_type, title, summary, relevance, proposed_action
3. Only report findings from the PAST 7 DAYS (or since last scan)
4. Skip anything already in recon_findings (check by title + source_url to avoid duplicates)
5. Assess relevance to Genesis specifically — not general AI news

## GitHub Repos

Watch these repositories for releases, significant PRs, and breaking changes:

| Repo | What to watch for |
|------|-------------------|
| `HKUDS/nanobot` | New releases, breaking changes, new features we should upstream-merge |
| `modelcontextprotocol/servers` | New MCP server implementations we could leverage |
| `modelcontextprotocol/specification` | Protocol changes that affect our MCP integrations |
| `open-interpreter/open-interpreter` | Architecture patterns, new capabilities |
| `crewAIInc/crewAI` | Multi-agent orchestration patterns |
| `microsoft/autogen` | Agent framework advances |
| `langchain-ai/langchain` | Tooling ecosystem, new integrations |
| `anthropics/anthropic-cookbook` | Best practices for Claude API usage |

For each repo: check releases page, recent merged PRs with >10 comments, and any issues tagged "breaking".

## Web Sources

Scan these curated sources for AI-relevant content:

| Source | URL Pattern | Focus |
|--------|-------------|-------|
| TLDR AI | tldrai.com | Daily AI newsletter archive — scan headlines for agent/tool/model news |
| Hacker News | hn.algolia.com/api/v1/search?tags=story&query=AI+agent | Top stories about AI agents, LLM tools, MCP |
| GitHub Trending | github.com/trending?since=weekly | Trending repos in AI/ML/agents space |
| ArXiv cs.AI | arxiv.org/list/cs.AI/recent | Papers on agent architectures, tool use, memory systems |

## Newsletter Filtering

When scanning email newsletters, extract items matching these criteria:
- New AI model releases (especially from Anthropic, OpenAI, Google, Meta, Mistral)
- MCP-related announcements or new MCP servers
- Agent framework releases or major updates
- New approaches to: memory systems, tool use, multi-agent coordination, autonomous reasoning
- Cost/pricing changes for LLM APIs we use

Ignore: marketing fluff, "AI will change everything" opinion pieces, enterprise sales announcements, AI art/image generation news (unless architecturally relevant).

## Model Landscape

When scanning for model updates (replaces weekly review's inline model scanning):
- New model releases from providers in our models.md (OpenRouter, Venice, Z.AI, Google AI, etc.)
- Pricing changes (especially new free tiers or significant cost reductions)
- Model deprecations or rename announcements
- New providers appearing on OpenRouter
- Context window expansions or capability upgrades

Cross-reference findings against our current `data/copilot/models.md` to identify:
- Models we should ADD (better price/performance than current options)
- Models we should REMOVE (deprecated or superseded)
- Pricing updates we should reflect

## Relevance Criteria

A finding is relevant to Genesis if it could lead to ANY of these concrete actions:
- **Add an MCP tool** — a new server we can integrate for expanded capabilities
- **Update models.md** — add, remove, or re-tier a model
- **Adopt an architecture pattern** — a better approach to memory, routing, task decomposition, or agent orchestration
- **Cherry-pick upstream** — a nanobot feature or fix we should merge
- **Add a capability** — something that enables a task Genesis can't currently do
- **Improve reliability** — a pattern that reduces failures or improves error handling

Relevance levels:
- **high** — directly applicable, could implement this week
- **medium** — interesting and applicable, but needs design work
- **low** — worth tracking, may become relevant later

## Self-Evolution

The weekly review may propose additions or removals to this watch list based on:
- New repos that produce consistently relevant findings
- Sources that produce only noise (candidates for removal)
- Emerging domains not yet covered (e.g., new MCP registries, new agent frameworks)

When the weekly review proposes changes, it writes them as evolution_proposals in dream_observations.
