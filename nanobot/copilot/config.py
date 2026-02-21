"""Copilot configuration model."""

from pydantic import BaseModel, Field


class CopilotConfig(BaseModel):
    """Configuration for Executive Co-Pilot extensions.

    When ``enabled`` is False the system behaves exactly like stock nanobot.

    Model terminology (used everywhere):
        routing_model  — tiny SLM (~3B) for background tasks: extraction,
                         approval parsing, classification.  Runs on LM Studio.
        local_model    — primary conversational model (~14-20B) on the 5070ti.
                         Handles most interactive messages.
        fast_model     — cheap cloud tier for quick/simple tasks.
        big_model      — powerful cloud tier for complex reasoning, images,
                         long context, creative work.

    Every feature that uses a model has its own config field so you can tune
    cost/quality independently.  Empty string means "use the default" (the
    shared field it would normally inherit from).
    """

    enabled: bool = False

    # ── Local Model (primary conversation) ──────────────────────────────
    # Main model for interactive chat.  Runs on LM Studio / 5070ti (16GB).
    # Should be large enough for proper conversational responses (~14-20B).
    #
    # Suggestions (LM Studio, 5070ti 16GB VRAM, Q4 quantization):
    #   "huihui-qwen3-30b-a3b-instruct-2507-abliterated-i1@q4_k_m" — 30B MoE (3B active), strong reasoning
    #   "qwen2.5-14b-instruct"              — 14B, excellent all-rounder
    #   "mistral-small-3.2-24b-instruct-2506" — 24B, strong reasoning
    #   "llama-3.1-8b-instruct"             — 8B, conservative but fast
    local_model: str = "huihui-qwen3-30b-a3b-instruct-2507-abliterated-i1@q4_k_m"

    # ── Routing Model (lightweight background SLM) ──────────────────────
    # Tiny model (~3B) for background tasks that don't need a full
    # conversational response: extraction, approval parsing, utility work.
    # NOT used for routing decisions (those are heuristic-based).
    #
    # Suggestions (LM Studio, must be fast):
    #   "llama-3.2-3b-instruct"    — 3B, fast, reliable JSON output
    #   "phi-3-mini-4k-instruct"   — 3.8B, good structured output
    #   "qwen2.5-3b-instruct"      — 3B, multilingual
    #   "smollm2-1.7b-instruct"    — 1.7B, ultra-fast if accuracy is OK
    routing_model: str = "llama-3.2-3b-instruct"

    # ── Fast Model (cloud cheap tier) ───────────────────────────────────
    # Cloud model for quick, cheap tasks.  Used as fallback when local
    # is down, and for background work that doesn't need heavy reasoning.
    #
    # Suggestions (OpenRouter model IDs):
    #   "anthropic/claude-3.5-haiku"         — fast, cheap, good quality
    #   "anthropic/claude-3-haiku"           — cheapest Claude
    #   "openai/gpt-4o-mini"                — $0.15/$0.60 per MTok
    #   "google/gemini-2.0-flash"            — very fast, competitive pricing
    fast_model: str = "anthropic/claude-haiku-4.5"

    # ── Big Model (cloud powerful tier) ─────────────────────────────────
    # Cloud model for complex reasoning, creative tasks, images, and long
    # context.  Also the escalation target when the local model determines
    # a task is beyond its capabilities.
    #
    # Suggestions (OpenRouter model IDs):
    #   "anthropic/claude-sonnet-4-6"         — strong reasoning, cost-effective (DEFAULT)
    #   "anthropic/claude-opus-4-6"           — most capable (use via weekly_model or /use)
    #   "openai/gpt-4o"                       — strong all-rounder
    #   "google/gemini-2.0-pro"               — large context window
    big_model: str = "anthropic/claude-sonnet-4-6"

    # ── Routing Plan ───────────────────────────────────────────────────
    # LLM-generated, user-approved routing plan.  When set, the router
    # follows this plan instead of the default model.  Empty list = use default.
    default_conversation_model: str = "MiniMax-M2.5"
    escalation_model: str = "anthropic/claude-sonnet-4-6"
    routing_plan: list[dict] = Field(default_factory=list)
    routing_plan_notify: bool = True  # inline failover notes (toggle off later)

    # ── Background Extraction ───────────────────────────────────────────
    # Runs after every exchange to extract facts/decisions/entities/sentiment.
    # Needs structured JSON output.  Small models work fine here.
    #
    # Local suggestions (same pool as routing_model — small, structured output):
    #   "llama-3.2-3b-instruct"    — 3B, reliable JSON
    #   "phi-3-mini-4k-instruct"   — 3.8B, good structured output
    #   "qwen2.5-3b-instruct"      — 3B, good JSON compliance
    # Cloud suggestions (used when local is down):
    #   "anthropic/claude-3.5-haiku"          — cheap, reliable JSON
    #   "openai/gpt-4o-mini"                — cheap, excellent JSON
    #   "google/gemini-2.0-flash"            — fast, cheap
    extraction_local_model: str = ""   # empty = use routing_model
    extraction_cloud_model: str = ""   # empty = use fast_model

    # ── Embeddings (Local) ──────────────────────────────────────────────
    # Used for storing/recalling episodic memories via Qdrant.
    # Runs on LM Studio against the 5070ti.
    #
    # Suggestions (LM Studio compatible):
    #   "text-embedding-nomic-embed-text-v1.5"  — 768d, good quality/speed
    #   "snowflake-arctic-embed-m"              — 768d, strong retrieval
    #   "mxbai-embed-large-v1"                  — 1024d, highest quality
    #   "bge-small-en-v1.5"                     — 384d, very fast, lower quality
    #   "all-MiniLM-L6-v2"                      — 384d, tiny, fast
    embedding_local_model: str = "text-embedding-nomic-embed-text-v1.5"
    embedding_local_dimensions: int = 768

    # ── Embeddings (Cloud Fallback) ─────────────────────────────────────
    # Used when local LM Studio is unreachable.  Zero-vector stored + queued
    # for re-embedding if both local and cloud fail.
    #
    # Free providers (OpenAI-compatible, just set key + base + model):
    #   Jina AI    — jina-embeddings-v3, 768d, 1M tok/mo free
    #                key: https://jina.ai/embeddings  base: https://api.jina.ai/v1
    #   Voyage AI  — voyage-3-lite, 512d, 200M tok/mo free
    #                key: https://dash.voyageai.com   base: https://api.voyageai.com/v1
    #   Nomic      — nomic-embed-text-v1.5, 768d, 5M tok/mo free
    #                key: https://atlas.nomic.ai      base: https://api-atlas.nomic.ai/v1
    #
    # Paid providers:
    #   OpenAI     — text-embedding-3-small, 1536d, $0.02/MTok (no base needed)
    #   OpenAI     — text-embedding-3-large, 3072d, $0.13/MTok
    cloud_embedding_api_key: str = ""
    cloud_embedding_api_base: str = ""   # empty = default OpenAI endpoint
    cloud_embedding_model: str = "text-embedding-3-small"
    cloud_embedding_dimensions: int | None = None  # None = match local dims

    # ── Cloud Extraction Fallback ──────────────────────────────────────
    # When local SLM is down, extraction falls back to a cheap cloud model.
    # Uses its own API key (separate from main provider) so extraction
    # costs are isolated and trackable.
    cloud_extraction_api_key: str = ""
    cloud_extraction_api_base: str = ""  # empty = use main provider's base
    cloud_extraction_model: str = "anthropic/claude-haiku-4-5"  # cheap, fast, good at JSON

    # ── Dream Cycle ─────────────────────────────────────────────────────
    # Memory consolidation (nightly at 3 AM).  Runs through the router by
    # default: tries local model first, heuristic decides if too complex,
    # falls back to fast cloud if LM Studio is off at 3 AM.
    #
    # Suggestions:
    #   ""                                     — use router (local → fast fallback)
    #   "anthropic/claude-3.5-haiku"            — force cloud cheap for overnight
    #   "openai/gpt-4o-mini"                  — force cloud cheap
    dream_model: str = "gemini-3-flash-preview"  # Gemini 3 Flash via Google AI (free tier)

    # ── Heartbeat ───────────────────────────────────────────────────────
    # LLM heartbeat (every 2h) — reads HEARTBEAT.md, reviews pending tasks.
    # Defaults to dream_model if empty. Only nanobot chat uses the router.
    heartbeat_model: str = ""          # empty = use dream_model

    # ── Weekly / Monthly Reviews ──────────────────────────────────────
    # Strategic reviews run by the dream cycle. Default to dream_model.
    weekly_model: str = ""             # empty = use dream_model
    monthly_model: str = ""            # empty = use dream_model

    # ── Task Decomposition & Execution ──────────────────────────────────
    # Background task queue.  Decomposes tasks into steps, then executes
    # each step through the router.
    #
    # Suggestions:
    #   ""                                     — use router (local → fast → big)
    #   "anthropic/claude-sonnet-4-20250514"   — force big model for multi-step
    task_model: str = ""               # empty = use router (local → fast → big)
    decomposition_model: str = ""      # empty = use big_model (frontier for decomposition)

    # ── Navigator Duo ──────────────────────────────────────────────────
    # Thinking-model peer that reviews orchestrator work during task execution.
    # Opt-in: no navigator unless explicitly enabled.
    navigator_model: str = ""          # empty = use big_model (thinking model preferred)
    navigator_enabled: bool = False    # opt-in; no navigator unless explicitly enabled
    max_duo_rounds: int = 3            # max rounds per review cycle
    max_review_cycles: int = 3         # max review cycles per task (meta-loop protection)

    # ── Emergency Fallbacks ──────────────────────────────────────────────
    # Last-resort models appended to EVERY failover chain.  Used when all
    # configured models fail (e.g. stale model IDs, provider outage).
    # Priority: emergency_cloud_model → LM Studio (local).
    #
    # IMPORTANT: These are intentionally excluded from the weekly review
    # auto-update process.  They must be extremely stable model IDs that
    # are unlikely to be deprecated.  Change only manually.
    emergency_cloud_model: str = "openai/gpt-4o-mini"  # stable, widely available

    # ── Self-Escalation ─────────────────────────────────────────────────
    # When the local model determines a task is beyond its capabilities,
    # it can begin its response with [ESCALATE] and the router will retry
    # with the big model.  Disable to always accept local responses as-is.
    escalation_enabled: bool = True
    escalation_marker: str = "[ESCALATE]"

    # ── Timezone ───────────────────────────────────────────────────────
    # Used for status display, cron schedule rendering, and active-hours logic.
    timezone: str = "America/New_York"

    # ── Non-Model Settings ──────────────────────────────────────────────

    # Cost alerting
    daily_cost_alert: float = 50.0
    per_call_cost_alert: float = 0.50

    # Shadow period — conservative mode for first 2 weeks
    shadow_mode: bool = True

    # Context budget for injected system context (tokens)
    context_budget: int = 1500

    # Continuation threshold — rebuild context when token usage exceeds this
    # fraction of the current model's context window
    continuation_threshold: float = 0.70

    # Database path (relative to project data dir)
    db_path: str = "data/sqlite/copilot.db"

    # Metacognition
    lesson_injection_count: int = 3
    lesson_min_confidence: float = 0.30

    # Identity & config documents
    copilot_docs_dir: str = "data/copilot"

    # Memory infrastructure
    qdrant_url: str = "http://localhost:6333"
    memory_recall_limit: int = 5
    memory_min_score: float = 0.35

    # Tools
    aws_region: str = "us-east-1"
    aws_profile: str | None = None
    n8n_url: str = "http://localhost:5678"
    browser_headless: bool = True

    # Security: HTTP endpoint protection
    http_deny_list: list[str] = Field(
        default_factory=lambda: ["169.254.169.254", "metadata.google.internal"],
        description="Hostnames/IPs blocked for SSRF protection",
    )

    # Alert bus
    alert_dedup_hours: float = 4.0
    alert_mute_hours: float = 8.0  # default mute duration

    # Security: private mode timeout (seconds of inactivity)
    private_mode_timeout: int = 1800  # 30 minutes

    # /use override timeout (seconds of inactivity before auto-revert)
    use_override_timeout: int = 3600  # 60 minutes

    # Tasks
    task_worker_interval: int = 60

    # SLM deferred work queue
    slm_queue_enabled: bool = True
    slm_queue_size_limit: int = 500
    slm_drain_rate: int = 30  # items per minute when draining

    # Dream + Monitoring + Heartbeat
    dream_cron_expr: str = "0 12 * * *"  # 7 AM EST (UTC-5)
    weekly_review_cron_expr: str = "0 14 * * 0"  # Sunday 9 AM EST (UTC-5)
    monthly_review_cron_expr: str = "0 15 1 * *"  # 1st of month 10 AM EST (UTC-5)
    backup_dir: str = "/home/ubuntu/executive-copilot/backups"
    monitor_interval: int = 300
    health_check_interval: int = 1800  # 30 minutes (daytime only, programmatic health checks)
    monitor_channel: str = "whatsapp"
    monitor_chat_id: str = ""

    # ── Resolved Accessors ──────────────────────────────────────────────
    # These resolve empty-string overrides back to their defaults so callers
    # don't have to handle the fallback logic themselves.

    @property
    def resolved_extraction_local_model(self) -> str:
        return self.extraction_local_model or self.routing_model

    @property
    def resolved_extraction_cloud_model(self) -> str:
        return self.extraction_cloud_model or self.fast_model

    @property
    def resolved_dream_model(self) -> str:
        return self.dream_model or ""

    @property
    def resolved_heartbeat_model(self) -> str:
        return self.heartbeat_model or self.dream_model or ""

    @property
    def resolved_weekly_model(self) -> str:
        return self.weekly_model or self.dream_model or ""

    @property
    def resolved_monthly_model(self) -> str:
        return self.monthly_model or self.dream_model or ""

    @property
    def resolved_task_model(self) -> str:
        return self.task_model or ""

    @property
    def resolved_decomposition_model(self) -> str:
        return self.decomposition_model or self.big_model

    @property
    def resolved_navigator_model(self) -> str:
        return self.navigator_model or self.big_model
