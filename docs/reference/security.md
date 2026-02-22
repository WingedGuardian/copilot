# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in nanobot, please report it by:

1. **DO NOT** open a public GitHub issue
2. Create a private security advisory on GitHub or contact the repository maintainers
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We aim to respond to security reports within 48 hours.

## Security Best Practices

### 1. API Key Management

**CRITICAL**: Never commit API keys to version control.

```bash
# ✅ Good: Secrets automatically stored separately with restricted permissions
# Secrets are in ~/.nanobot/secrets.json (mode 0600)
# Config preferences are in ~/.nanobot/config.json

# ❌ Bad: Hardcoding keys in code or committing them
```

**Automatic Secrets Separation** (as of 2026-02-14):
- API keys, phone numbers (`allowFrom`), and chat IDs stored in `~/.nanobot/secrets.json` with file permissions `0600` (owner read/write only)
- Auto-migration on first load: extracts secrets from legacy `config.json`
- Deep merge on load: secrets override empty config values
- Cloud models and tools **cannot read** secrets — blocked by `_SENSITIVE_PATH_PATTERNS` (filesystem tools) and `_SECRETS_PATTERNS` (shell tool)

**Recommendations:**
- Secrets file is created automatically with secure permissions
- Rotate API keys regularly
- Use separate API keys for development and production
- Consider OS keyring/credential manager for enterprise deployments

### 2. Channel Access Control

**IMPORTANT**: Always configure `allowFrom` lists for production use.

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": ["123456789", "987654321"]
    },
    "whatsapp": {
      "enabled": true,
      "allowFrom": ["+1234567890"]
    }
  }
}
```

**Security Notes:**
- Empty `allowFrom` list will **ALLOW ALL** users (open by default for personal use)
- Get your Telegram user ID from `@userinfobot`
- Use full phone numbers with country code for WhatsApp
- Review access logs regularly for unauthorized access attempts

### 3. Shell Command Execution & POLICY.md Guardrails

The `exec` tool can execute shell commands. **POLICY.md guardrails** (as of 2026-02-13) provide runtime safety:

**Safety Features:**
- ✅ **Regex-based safety checks** block dangerous commands before execution
- ✅ **Forensic audit log** records all tool calls to SQLite `tool_audit_log` table
- ✅ **Policy violation reporting** logs blocked commands with reason
- ✅ **Read-only commands** (ls, cat, grep) execute without prompt
- ❌ **Destructive operations** are blocked and logged

**Blocked patterns (via POLICY.md):**
- `rm -rf /` - Root filesystem deletion
- Fork bombs
- Filesystem formatting (`mkfs.*`)
- Raw disk writes
- `dd` commands to sensitive devices
- Other destructive operations

**Best Practices:**
- ✅ Review `tool_audit_log` table regularly for security events
- ✅ Understand what commands the agent is running
- ✅ Use a dedicated user account with limited privileges
- ✅ Never run nanobot as root
- ❌ Don't disable security checks or modify POLICY.md without review
- ❌ Don't run on systems with sensitive data without careful review

**Forensic Review:**
```sql
# Check recent tool calls
sqlite3 ~/.nanobot/data/sqlite/copilot.db "
SELECT timestamp, tool_name, policy_check, result_summary
FROM tool_audit_log
ORDER BY timestamp DESC
LIMIT 20;
"
```

### 4. File System Access

File operations have path traversal protection, but:

- ✅ Run nanobot with a dedicated user account
- ✅ Use filesystem permissions to protect sensitive directories
- ✅ Regularly audit file operations in logs
- ❌ Don't give unrestricted access to sensitive files

### 5. Network Security

**API Calls:**
- All external API calls use HTTPS by default
- Timeouts are configured to prevent hanging requests
- Consider using a firewall to restrict outbound connections if needed

**WhatsApp Bridge:**
- The bridge binds to `127.0.0.1:3001` (localhost only, not accessible from external network)
- Set `bridgeToken` in config to enable shared-secret authentication between Python and Node.js
- Keep authentication data in `~/.nanobot/whatsapp-auth` secure (mode 0700)

### 6. Dependency Security

**Critical**: Keep dependencies updated!

```bash
# Check for vulnerable dependencies
pip install pip-audit
pip-audit

# Update to latest secure versions
pip install --upgrade nanobot-ai
```

For Node.js dependencies (WhatsApp bridge):
```bash
cd bridge
npm audit
npm audit fix
```

**Important Notes:**
- Keep `litellm` updated to the latest version for security fixes
- We've updated `ws` to `>=8.17.1` to fix DoS vulnerability
- Run `pip-audit` or `npm audit` regularly
- Subscribe to security advisories for nanobot and its dependencies

### 7. Production Deployment

For production use:

1. **Isolate the Environment**
   ```bash
   # Run in a container or VM
   docker run --rm -it python:3.11
   pip install nanobot-ai
   ```

2. **Use a Dedicated User**
   ```bash
   sudo useradd -m -s /bin/bash nanobot
   sudo -u nanobot nanobot gateway
   ```

3. **Set Proper Permissions**
   ```bash
   chmod 700 ~/.nanobot
   chmod 600 ~/.nanobot/config.json
   chmod 600 ~/.nanobot/secrets.json  # Auto-created with 0600
   chmod 700 ~/.nanobot/whatsapp-auth
   ```

4. **Enable Logging**
   ```bash
   # Configure log monitoring
   tail -f ~/.nanobot/logs/nanobot.log
   ```

5. **Use Rate Limiting**
   - Configure rate limits on your API providers
   - Monitor usage for anomalies
   - Set spending limits on LLM APIs

6. **Regular Updates**
   ```bash
   # Check for updates weekly
   pip install --upgrade nanobot-ai
   ```

### 8. Development vs Production

**Development:**
- Use separate API keys
- Test with non-sensitive data
- Enable verbose logging
- Use a test Telegram bot

**Production:**
- Use dedicated API keys with spending limits
- Restrict file system access
- Enable audit logging
- Regular security reviews
- Monitor for unusual activity

### 9. Data Privacy

- **Logs may contain sensitive information** - secure log files appropriately
- **LLM providers see your prompts** - review their privacy policies
- **Chat history is stored locally** - protect the `~/.nanobot` directory
- **API keys stored in secrets.json** (mode 0600) - separate from config, not accessible to tools
- **Tool audit log** contains forensic trail - protect `copilot.db` database file

### 10. Incident Response

If you suspect a security breach:

1. **Immediately revoke compromised API keys**
2. **Review logs for unauthorized access**
   ```bash
   grep "Access denied" ~/.nanobot/logs/nanobot.log
   ```
3. **Check for unexpected file modifications**
4. **Rotate all credentials**
5. **Update to latest version**
6. **Report the incident** to maintainers

## Security Features

### Built-in Security Controls

✅ **Input Validation**
- Path traversal protection on file operations
- Dangerous command pattern detection via POLICY.md
- Input length limits on HTTP requests

✅ **Authentication & Authorization**
- Allow-list based access control (`allowFrom` config)
- Failed authentication attempt logging
- Open by default (configure allowFrom for production use)
- POLICY.md guardrails for runtime safety checks
- Forensic audit log for all tool calls

✅ **Resource Protection**
- Command execution timeouts (60s default)
- Output truncation (10KB limit)
- HTTP request timeouts (10-30s)

✅ **Secure Communication**
- HTTPS for all external API calls
- TLS for Telegram API
- WhatsApp bridge: localhost-only binding + optional token auth

## Known Limitations

⚠️ **Current Security Limitations:**

1. **No Rate Limiting** - Users can send unlimited messages (add your own if needed)
2. **Session Cache Growth** - SessionManager cache capped at 256 entries (LRU eviction, added 2026-02-16)
3. **No Session Management** - No automatic session expiry timeout
4. **Regex-based Command Filtering** - POLICY.md uses pattern matching (not semantic analysis)
5. **Audit Log Retention** - No automatic pruning of `tool_audit_log` (grows unbounded)

## Security Checklist

Before deploying nanobot:

- [ ] API keys stored securely (not in code)
- [ ] Config file permissions set to 0600
- [ ] `allowFrom` lists configured for all channels
- [ ] Running as non-root user
- [ ] File system permissions properly restricted
- [ ] Dependencies updated to latest secure versions
- [ ] Logs monitored for security events
- [ ] Rate limits configured on API providers
- [ ] Backup and disaster recovery plan in place
- [ ] Security review of custom skills/tools

## Updates

**Last Updated**: 2026-02-16

For the latest security updates and announcements, check:
- GitHub Security Advisories: https://github.com/HKUDS/nanobot/security/advisories
- Release Notes: https://github.com/HKUDS/nanobot/releases

## License

See LICENSE file for details.
