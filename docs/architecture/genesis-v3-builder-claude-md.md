# Genesis v3 Builder — CLAUDE.md Section

> **Purpose:** This content is intended to be added to the CLAUDE.md of the Claude Code instance
> that will build Genesis v3 on the Agent Zero container. Copy the section below into that
> instance's CLAUDE.md.

---

```markdown
# Genesis v3 Build Context

You are building Genesis v3 — an autonomous executive copilot system on the Agent Zero framework.

## Key Design Documents

All design documents live in `docs/architecture/`:
- `genesis-v3-vision.md` — Core philosophy and identity. READ THIS FIRST. It defines who Genesis is and what it aspires to be. Every implementation decision should be consistent with this document.
- `genesis-v3-build-phases.md` — Safety-ordered build plan. This is your roadmap. Build in phase order. Do not skip phases or start a phase before its dependencies are verified.
- `genesis-v3-autonomous-behavior-design.md` — Full architectural reference. The master design document with detailed specifications for every component. Consult this for implementation details, schemas, and rationale.
- `genesis-v3-dual-engine-plan.md` — Framework decisions, container architecture, migration plan.

## Build Order: Safety First

Phases are ordered from safest to riskiest. Each phase's verification criteria MUST pass before starting the next phase. The phases:

0. Data Foundation (schemas, MCP stubs) — pure CRUD, no LLM
1. The Metronome (awareness loop) — programmatic signal processing
2. Compute Routing (model hierarchy, fallback) — infrastructure plumbing
3. Perception (micro/light reflection) — first LLM calls, low stakes
4. Memory Operations (store, retrieve, activation) — extending existing system
5. Learning Fundamentals (outcome classification, procedures) — feedback loops
6. Surplus Infrastructure (queue, staging, cost rules) — free compute utilization
7. Deep Cognition (meta-prompting, strategic reflection) — complex LLM orchestration
8. Outreach (proactive messaging, engagement tracking) — user-facing, highest blast radius
9. Autonomy System (permission hierarchy, progression/regression) — trust management
10. Calibration & Evolution (drive/signal adaptation, meta-learning) — requires real data

## Critical Principles

- **LLM-first solutions**: Code handles structure (timeouts, validation, event wiring). Judgment calls belong to the LLM. Don't build code that overrides LLM judgment.
- **Verify before proceeding**: Each phase has verification criteria in the build phases doc. Run them. "It looks right" is not verification.
- **Simplicity**: If 50 lines solve it, don't write 200. If a simple heuristic works 95% of the time, ship it. Build the complex version when you have evidence the 5% matters.
- **Rollback readiness**: Each phase should be independently disableable via config. If Phase 7 breaks, you fall back to Phase 3 without losing anything.
- **3B model constraints**: The 3B model runs on CPU only. It handles embeddings and light extraction ONLY. No reflection, no reasoning, no surplus tasks. When in doubt, escalate to 20-30B or Gemini.
- **Local model is not 24/7**: The local machine running 20-30B models is intermittently available. Gemini Flash free tier is the default fallback. Build availability detection and automatic failover from day 1.
- **Null hypothesis**: Default to "current behavior is correct" until evidence says otherwise. Early system = aggressive learning (most things are novel). Mature system = conservative learning (most things are known).
```

---

## Notes for the User

This CLAUDE.md section is deliberately concise — it gives the building instance enough context to make correct decisions without overwhelming its context window. The detail lives in the design docs it references.

If the building instance needs more context on a specific component, it should read the relevant section of `genesis-v3-autonomous-behavior-design.md`. The section headers map cleanly to build phases:

| Build Phase | Design Doc Section |
|-------------|-------------------|
| Phase 0 | §4 MCP Servers, §Execution Trace Schema, §Procedural Memory Design |
| Phase 1 | §Layer 1: Awareness Loop, §Signal-Weighted Trigger System |
| Phase 2 | §LLM Weakness Compensation → Pattern 1: Compute Hierarchy |
| Phase 3 | §Layer 2: Reflection Engine → Depth Levels (Micro, Light) |
| Phase 4 | §Memory Separation, §What We Learned (Gap fixes: A-MEM, ACT-R) |
| Phase 5 | §Layer 3: Self-Learning Loop, §Procedural Memory Design, §LLM Weakness → Pattern 6 |
| Phase 6 | §Cognitive Surplus |
| Phase 7 | §Reflection Engine (Deep, Strategic), §LLM Weakness → Patterns 2-5 |
| Phase 8 | §Proactive Outreach, §Bootstrap / Cold Start Strategy |
| Phase 9 | §Self-Evolving Learning: The Autonomy Hierarchy |
| Phase 10 | §Loop Taxonomy → Tiers 3-4 |
