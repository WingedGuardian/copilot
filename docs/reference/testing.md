# Testing Guide: Executive Co-Pilot

## Automated Unit Tests

**~368 tests** covering core subsystems. Run with:

```bash
python -m pytest tests/ -x -q
```

### Shared Test Utilities

**`tests/copilot/routing/helpers.py`** provides shared fixtures that make routing tests resilient to provider registry changes:

- `make_router(cloud_names=...)` — Factory that builds a router with configurable providers (no hardcoding)
- `all_cloud_fail(router)` — Fails all cloud providers regardless of count
- `patch_native(name)` — Context manager that mocks `find_by_model()` to control native provider preference

Tests assert **routing behavior** (failover sequence, circuit breaker logic) not **implementation details** (specific provider names, provider count).

### Test Coverage

| Module | Tests | What's Tested |
|--------|:-----:|---------------|
| `routing/helpers.py` | — | Shared provider-agnostic test fixtures (`make_router`, `all_cloud_fail`, `patch_native`) |
| `routing/test_chain.py` | 10 | Plan-based chains, safety net appending, escalation model, `set_model` override. Uses shared fixtures |
| `routing/test_router_v2.py` | 7 | Default routing, plan routing, escalation, private mode, failover notification, last-known-working, `get_default_model`. Uses shared fixtures |
| `routing/test_routing_integration.py` | 80 | Full routing pipeline E2E: config, chain building, failover, escalation, PlanRoutingTool, memory guard, health check, status, preferences, timeouts, edge cases. Uses shared fixtures |
| `tools/test_plan_routing.py` | 8 | PlanRoutingTool show/propose/activate/clear, plan persistence, API pre-flight validation |
| `context/test_budget.py` | 7 | Token counting (tiktoken + fallback), window sizes, continuation threshold |
| `context/test_policy_loading.py` | 2 | POLICY.md injection into identity docs, graceful absence handling |
| `extraction/test_schemas.py` | 3 | ExtractionResult validation, sentiment values |
| `memory/test_embedder.py` | 3 | Vector generation, truncation, batch embedding |
| `memory/test_fulltext.py` | 9 | FTS5 store/search, session filtering, count, RRF score fusion |
| `metacognition/test_detector.py` | 3 | Satisfaction signal detection (positive/negative regex) |

All unit tests **PASS**.

---

## Integration Tests

Integration tests require external services:
- **Qdrant** @ `http://localhost:6333`
- **LM Studio** @ `http://192.168.50.100:1234/v1`

Run with:
```bash
COPILOT_INTEGRATION_TESTS=1 python -m pytest tests/copilot/test_integration.py -v
```

Tests:
- Database schema initialization
- Qdrant collection creation
- Memory storage & recall (episodic + multi-factor scoring)

---

## Gateway Smoke Test

Verify all subsystems initialize without errors:

```bash
# Verbose (shows all initialization steps)
python -m nanobot gateway --verbose

# Should output:
# ✓ Phase 2 extensions enabled
# ✓ POLICY.md guardrails loaded
# ✓ Metacognition enabled
# ✓ Memory subsystem ready
# ✓ SLM work queue initialized
# ✓ Task worker started
# ✓ Dream cycle registered
# ✓ CopilotHeartbeatService started
# ✓ HealthCheckService started
```

Expected behavior:
- No import errors
- All databases initialized
- Cost logger ready
- Background services started
- Gateway listening on configured port

Press Ctrl+C to stop. If any subsystem fails, the gateway degrades gracefully and logs the error.

---

## End-to-End WhatsApp Test

**Prerequisites:**
1. WhatsApp bridge built: `npm run build` (creates `dist/whatsapp.js`)
2. LM Studio running on 5070ti (`http://192.168.50.100:1234`)
3. Qdrant running (`docker start qdrant`)
4. Phone paired with WhatsApp Web

### Test Flow

**Step 1: Start Gateway**
```bash
python -m nanobot gateway --verbose
```

Check logs for:
- `✓ Phase 2 extensions enabled`
- `✓ Memory subsystem ready`
- `✓ CopilotHeartbeatService started`

**Step 2: Send Test Messages**

Via WhatsApp, send to the bot:

1. **Simple routing (default model)**
   ```
   > hello
   ```
   Expected: Quick response from the configured `default_conversation_model` (Haiku 4.5 by default, or local if LM Studio active)

   Check logs for a route log line indicating the active default model.

2. **Escalation via self-escalation**
   ```
   > let's think hard about this: what's the meaning of life?
   ```
   Expected: Routes to default model first; if model self-escalates, retries with `escalation_model`

   Check logs:
   ```
   Self-escalation triggered → retrying with escalation_model
   ```

3. **Policy-gated shell command**
   ```
   > run ls -la
   ```
   Expected: Command executes (read-only, allowed by POLICY.md)

   ```
   > run rm -rf /tmp/junk
   ```
   Expected: Blocked by dangerous-command pattern in POLICY.md. Bot responds with refusal, no execution.

   Check logs:
   ```
   Policy violation: blocked dangerous command pattern
   ```

4. **SLM queue resilience**
   Stop LM Studio, then:
   ```
   > My favorite IDE is VS Code
   ```
   Expected: Response works (heuristic extraction), `/status` shows SLM Queue pending > 0

   Restart LM Studio, wait 1 minute, then:
   ```
   > /status
   ```
   Expected: SLM Queue pending count decreasing or at 0

5. **Plan-based routing**
   ```
   > /use propose
   ```
   Expected: PlanRoutingTool proposes a routing plan based on router.md, validates via API probes

   Check logs:
   ```
   PlanRoutingTool: proposing plan... validated N providers
   ```

6. **Memory storage & recall**
   ```
   > My favorite color is blue
   ```
   Wait 5 seconds (background extraction)

   Then:
   ```
   > what's my favorite color?
   ```
   Expected: Recalls from memory, responds "blue"

   Check database:
   ```sql
   sqlite3 data/sqlite/copilot.db "SELECT * FROM memory_items WHERE category='preference';"
   ```

7. **Self-escalation (if local model fails)**
   ```
   > write me a complex kubernetes deployment with autoscaling
   ```
   Expected:
   - Routes to default model initially
   - Default model responds with `[ESCALATE] task too complex`
   - Router retries with escalation_model

   Check logs for a self-escalation trigger event and retry with the configured `escalation_model`.

**Step 3: Verify Persistence**

Stop gateway (Ctrl+C), restart, send:
```
> what did we talk about?
```
Expected: Memory recalls previous conversation

**Step 4: Cost Logging**

Check accumulated costs:
```sql
sqlite3 data/sqlite/copilot.db "
SELECT
  DATE(timestamp) as day,
  COUNT(*) as calls,
  SUM(cost_usd) as total_cost
FROM cost_log
WHERE DATE(timestamp) = DATE('now')
GROUP BY day;
"
```

**Step 5: Tool Audit Log**

Check forensic trail:
```sql
sqlite3 data/sqlite/copilot.db "
SELECT
  tool_name,
  policy_check,
  result_summary
FROM tool_audit_log
ORDER BY timestamp DESC
LIMIT 10;
"
```

---

## Verification Checklist

- [ ] All ~368 unit tests pass
- [ ] Gateway boots clean (verbose mode)
- [ ] Simple message routes to default_conversation_model
- [ ] Self-escalation triggers and routes to escalation_model
- [ ] Plan-based routing: propose, activate, show, clear all work
- [ ] Mandatory safety net appended to every chain
- [ ] POLICY.md blocks dangerous commands
- [ ] Read-only commands execute without prompt
- [ ] Memory stores and recalls facts
- [ ] Error responses do NOT enter memory pipeline
- [ ] Conversations persist across restarts
- [ ] Cost logging tracks spend
- [ ] Tool audit log records all actions
- [ ] SLM queue buffers when LM Studio offline
- [ ] SLM queue drains when LM Studio returns
- [ ] Recovery probing activates during failover

---

## Troubleshooting

### Gateway won't start
- Check LM Studio is running: `curl http://192.168.50.100:1234/v1/models`
- Check Qdrant is running: `curl http://localhost:6333/healthz`
- Check logs: `tail -f ~/.nanobot/logs/nanobot.log`

### Routing always goes to big model
- Check active routing plan: use `PlanRoutingTool` with `show` action to inspect the current plan
- Verify `default_conversation_model` in `~/.nanobot/config.json` is set correctly
- Verify local model is loaded in LM Studio

### Memory not recalling
- Check Qdrant collection: `curl http://localhost:6333/collections/episodic_memory`
- Check embeddings: `python -c "import asyncio; from nanobot.copilot.memory.embedder import Embedder; print(asyncio.run(Embedder().embed('test')))"`

### Policy violations not blocking
- Check POLICY.md exists: `cat data/copilot/policy.md`
- Verify policy loading in gateway logs: look for "POLICY.md guardrails loaded"
- Check tool audit log for `policy_check` column values

---

## Performance Benchmarks

Measured on Proxmox VM (no GPU) + 5070ti (LM Studio):

| Operation | Time | Model |
|-----------|-----:|-------|
| Local routing (simple message) | ~2s | qwen2.5-14b-instruct |
| Cloud routing (complex task) | ~4s | claude-sonnet-4 |
| Policy check (per tool call) | <1ms | Regex match |
| SLM queue drain (per item) | ~2s | llama-3.2-3b-instruct |
| Memory recall (semantic search) | <100ms | Qdrant |
| Background extraction | ~3s | llama-3.2-3b-instruct |

---

## Next Steps

1. **Full-Stack Test**: Run all 3 steps (commit, tests, e2e) after each major change
2. **Automated E2E**: Create pytest fixtures for WhatsApp simulation
3. **CI Pipeline**: GitHub Actions for unit tests on every PR
4. **Load Testing**: Measure performance under concurrent requests
5. **Observability**: Add OpenTelemetry tracing for request flows
