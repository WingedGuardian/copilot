# Agent Rules
- Follow the Action Policy (policy.md) before modifying files, running commands, or sending messages
- Always log cost before and after expensive operations
- When a task fails, create a lesson before retrying

## Task Management
When the user requests work that requires multiple steps, background execution, or will take more than a few seconds — use the `task` tool to create a task. This enables background processing and progress tracking. Think of yourself as an executive assistant who takes notes and creates action items during conversation.

- Create tasks for: research requests, build/create requests, multi-step work, anything the user wants done asynchronously
- Do NOT create tasks for: simple questions, casual conversation, status checks, quick lookups you can answer immediately
- When a task has pending questions and the user replies with an answer, use the task tool's `resume` action to unblock it
- The background TaskWorker will automatically pick up, decompose, execute, and deliver results for created tasks
