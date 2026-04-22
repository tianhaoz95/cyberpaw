---
title: Execution Tools
description: Bash, REPL, and Sleep tools
---

## Bash

Runs a shell command and returns stdout + stderr.

```json
{"tool": "Bash", "input": {"command": "npm test"}}
{"tool": "Bash", "input": {"command": "pytest tests/", "working_dir": "agent"}}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `command` | string | Shell command to run |
| `working_dir` | string? | Subdirectory to run in (relative to working directory) |
| `timeout` | int? | Timeout in seconds (default: 30) |

:::caution
Each Bash call runs in a **fresh shell**. `cd` does not persist between calls. Use `working_dir` to run commands inside a subdirectory.
:::

Output is truncated to 10,000 characters. The exit code is included in the result.

---

## REPL

Executes Python code in a **persistent** interpreter session. State (variables, imports) is preserved across calls within the same conversation.

```json
{"tool": "REPL", "input": {"code": "x = [1, 2, 3]\nprint(sum(x))"}}
```

Useful for data analysis, calculations, or iterative scripting where you want to build up state across multiple tool calls.

The REPL session is reset when the conversation is reset.

---

## Sleep

Pauses agent execution for a specified duration. Useful for waiting for background processes or rate-limiting.

```json
{"tool": "Sleep", "input": {"seconds": 2}}
```

Maximum sleep duration: 60 seconds.
