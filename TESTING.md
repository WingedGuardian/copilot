# Testing Guide: Executive Co-Pilot

## Automated Unit Tests

**33 tests** covering core subsystems. Run with:

```bash
python -m pytest tests/copilot/ --ignore=tests/copilot/test_integration.py -v
```

### Test Coverage

| Module | Tests | What's Tested |
|--------|:-----:|---------------|
| `routing/test_heuristics.py` | 11 | Intent detection, complexity patterns, priority order, lesson overrides |
| `approval/test_parser.py` | 6 | NL approval parsing, rule creation, ambiguous responses |
| `context/test_budget.py` | 7 | Token counting (tiktoken + fallback), window sizes, continuation threshold |
| `extraction/test_schemas.py` | 3 | ExtractionResult validation, sentiment values |
| `memory/test_embedder.py` | 3 | Vector generation, truncation, batch embedding |
| `metacognition/test_detector.py` | 3 | Satisfaction signal detection (positive/negative regex) |

All unit tests **PASS** (85s runtime).

---

## Integration Tests

Integration tests require external services:
- **Qdrant** @ `http://localhost:6333`
- **Redis** @ `redis://localhost:6379/0`
- **LM Studio** @ `http://192.168.50.100:1234/v1`

Run with:
```bash
COPILOT_INTEGRATION_TESTS=1 python -m pytest tests/copilot/test_integration.py -v
```

Tests:
- Database schema initialization
- Qdrant collection creation
- Redis connection & health check
- Memory storage & recall (episodic + multi-factor scoring)

---

## Gateway Smoke Test

Verify all subsystems initialize without errors:

```bash
# Verbose (shows all initialization steps)
python -m nanobot gateway --verbose

# Should output:
# ✓ Phase 2 extensions enabled
# ✓ Approval system + metacognition enabled
# ✓ Memory subsystem ready
# ✓ Task worker started
# ✓ Dream cycle registered
# ✓ HeartbeatService started
# ✓ MonitorService started
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
4. Redis running (`systemctl start redis-server`)
5. Phone paired with WhatsApp Web

### Test Flow

**Step 1: Start Gateway**
```bash
python -m nanobot gateway --verbose
```

Check logs for:
- `✓ Phase 2 extensions enabled`
- `✓ Memory subsystem ready`
- `✓ HeartbeatService started`

**Step 2: Send Test Messages**

Via WhatsApp, send to the bot:

1. **Simple routing (local model)**
   ```
   > hello
   ```
   Expected: Quick response from local model (qwen2.5-14b-instruct)

   Check logs:
   ```
   Route: local (default) → qwen2.5-14b-instruct | tokens≈50 images=False
   ```

2. **Intent-based upgrade**
   ```
   > let's think hard about this: what's the meaning of life?
   ```
   Expected: Routes to big model (claude-sonnet-4)

   Check logs:
   ```
   Route: big (user_upgrade) → anthropic/claude-sonnet-4-20250514
   ```

3. **Approval flow (shell command)**
   ```
   > run ls -la
   ```
   Expected: Bot asks for approval via WhatsApp
   ```
   [Approval Needed]
   Tool: exec
   Command: ls -la
   Reply: approve / deny / modify
   ```

   Reply: `yes`

   Expected: Command executes, result returned

4. **Approval denial + lesson creation**
   ```
   > run rm -rf /
   ```
   Expected: Approval request

   Reply: `no, too dangerous`

   Check database:
   ```sql
   sqlite3 data/sqlite/copilot.db "SELECT * FROM lessons WHERE source='denial';"
   ```
   Should show new lesson: "User denied: too dangerous"

5. **Complexity routing**
   ```
   > Here's some code:
   > ```python
   > def foo():
   >   return 42
   > ```
   ```
   Expected: Routes to big model (complexity heuristic)

   Check logs:
   ```
   Route: big (complexity) → anthropic/claude-sonnet-4-20250514
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
   - Routes to local initially
   - Local model responds with `[ESCALATE] task too complex`
   - Router retries with big model

   Check logs:
   ```
   Route: local (default) → qwen2.5-14b-instruct
   Self-escalation triggered: task too complex → retrying with big model
   Route: big (escalation) → anthropic/claude-sonnet-4-20250514
   ```

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
  approved_by,
  denied,
  result_summary
FROM tool_audit_log
ORDER BY timestamp DESC
LIMIT 10;
"
```

---

## Verification Checklist

- [ ] All 33 unit tests pass
- [ ] Gateway boots clean (verbose mode)
- [ ] Simple message routes to local model
- [ ] Intent-based upgrade routes to big model
- [ ] Approval flow blocks shell commands
- [ ] Denial creates lesson in database
- [ ] Complexity routing works (code blocks → big)
- [ ] Memory stores and recalls facts
- [ ] Self-escalation triggers on complex tasks
- [ ] Conversations persist across restarts
- [ ] Cost logging tracks spend
- [ ] Tool audit log records all actions

---

## Troubleshooting

### Gateway won't start
- Check LM Studio is running: `curl http://192.168.50.100:1234/v1/models`
- Check Qdrant is running: `curl http://localhost:6333/healthz`
- Check Redis is running: `redis-cli ping`
- Check logs: `tail -f ~/.nanobot/logs/nanobot.log`

### Routing always goes to big model
- Check heuristics: `python -c "from nanobot.copilot.routing.heuristics import classify; print(classify('hello', False, 100))"`
- Verify local model is loaded in LM Studio

### Memory not recalling
- Check Qdrant collection: `curl http://localhost:6333/collections/episodic_memory`
- Check embeddings: `python -c "import asyncio; from nanobot.copilot.memory.embedder import Embedder; print(asyncio.run(Embedder().embed('test')))"`

### Approval not working
- Check approval queue: `sqlite3 data/sqlite/copilot.db "SELECT * FROM pending_approvals;"`
- Verify approval timeout (default 300s)
- Check WhatsApp delivery (bridge logs)

---

## Performance Benchmarks

Measured on Proxmox VM (no GPU) + 5070ti (LM Studio):

| Operation | Time | Model |
|-----------|-----:|-------|
| Local routing (simple message) | ~2s | qwen2.5-14b-instruct |
| Cloud routing (complex task) | ~4s | claude-sonnet-4 |
| Approval flow (round-trip) | <1s | Local + WhatsApp |
| Memory recall (semantic search) | <100ms | Qdrant |
| Background extraction | ~3s | llama-3.2-3b-instruct |

---

## Next Steps

1. **Full-Stack Test**: Run all 3 steps (commit, tests, e2e) after each major change
2. **Automated E2E**: Create pytest fixtures for WhatsApp simulation
3. **CI Pipeline**: GitHub Actions for unit tests on every PR
4. **Load Testing**: Measure performance under concurrent requests
5. **Observability**: Add OpenTelemetry tracing for request flows
