---
title: Agent Harness
description: The orchestrator, context manager, and permission system
---

The agent harness lives in `cyberpaw/agent/harness/` and coordinates everything between the LLM and the tools.

## Orchestrator loop

`harness/orchestrator.py` — the main agent loop. Each call to `handle_input()` runs this cycle:

```
1. Append user message to history
2. Compact history if near context limit
3. Render full prompt (chat template from GGUF metadata)
4. Stream tokens from the LLM backend
5. Parse tool calls from the streamed text
6. For each tool call:
   a. Check permissions (may pause and wait for user approval)
   b. Execute the tool
   c. Append ToolResultBlock to history
7. If any tool calls were made → goto 2
8. Emit status: idle and return
```

The loop runs for up to **40 turns** before halting. A "turn" is one LLM generation + all tool calls it produced.

### Loop detection

The orchestrator tracks recent tool calls and detects when the same failing call repeats. After 2 identical failing calls within a 4-call window, it injects an intervention message telling the model to try a different approach.

### Empty response handling

If the model produces zero tokens (e.g. context overflow), the orchestrator emits `[model returned an empty response — retrying…]` and appends a nudge message. If the model produces only `<thought>` blocks with no visible text or tool calls, it emits `[model produced only internal thoughts — nudging…]`.

---

## Context manager

`harness/context_manager.py` — manages the token budget.

**Compaction trigger:** when the conversation history exceeds 80% of `n_ctx`.

**Compaction strategy:**
1. Keep the system prompt and last 2 messages intact
2. Summarize intermediate tool results to a one-line summary
3. Truncate very long tool outputs to a configurable limit

Token counting uses the model's own tokenizer via `backend.count_tokens()` for exact counts.

---

## Permission system

`harness/permissions.py` — three modes:

| Mode | Behaviour |
|------|-----------|
| `ask` | Pause and request user approval for all write/execute tools |
| `auto_read` | Auto-approve read-only tools; ask for writes/bash |
| `auto_all` | Auto-approve everything (no prompts) |

When a tool requires approval in `ask` mode, the orchestrator emits a `tool_permission_request` event and suspends until `tool_ack` arrives from the frontend.

**Read-only tools** (never require approval): `Read`, `Glob`, `Grep`, `ListDir`, `WebFetch`, `WebSearch`, `Sleep`, `TaskGet`, `TaskList`

**Modifying tools** (require approval in `ask` mode): `Write`, `Edit`, `MultiEdit`, `Bash`, `Move`, `DeleteFile`, `REPL`, `TaskCreate`, `TaskUpdate`

---

## Message types

`harness/message.py` defines the conversation history format:

```python
@dataclass
class TextBlock:
    text: str

@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict

@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str
    is_error: bool

@dataclass
class Message:
    role: str          # "user" or "assistant"
    content: list      # list of TextBlock | ToolUseBlock | ToolResultBlock
```

---

## Sub-agents

`harness/subagent.py` — the `Agent` tool spawns a nested orchestrator with a fresh message history and a sub-task prompt. Sub-agents share the same LLM backend and tool registry but have independent conversation state.

Sub-agent nesting is limited to **3 levels** to prevent runaway recursion.

---

## Session persistence

Conversation history is persisted to `.cyberpaw/sessions/<session_id>.jsonl` in the working directory. Each line is a JSON-serialised `Message`. Sessions can be resumed with `{"type": "resume", "session_id": "..."}`.
