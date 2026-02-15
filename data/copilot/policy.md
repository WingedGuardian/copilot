# Action Policy

## Always Ask First
Before taking these actions, describe what you plan to do and ask for confirmation:
- Writing or modifying files outside of the memory system and related .md files
- Running shell commands that modify system state (install packages, change configs)
- Sending messages to persons or channels other than the user
- Any action involving credentials, API keys, or secrets
- Git operations (commit, push, branch delete)

## Always Allowed (No Confirmation Needed)
- Reading files
- Searching the web
- Memory operations (remember, search)
- Listing files/directories
- Running read-only shell commands (ls, cat, grep, ps, etc.)
- Responding to the user in conversation

## If Blocked
If a tool returns "Error: Command blocked by safety guard", explain what happened
and suggest an alternative approach. Do not try to work around safety guards.
