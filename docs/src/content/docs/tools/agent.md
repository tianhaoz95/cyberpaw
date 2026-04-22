---
title: Agent Tools
description: Sub-agent spawning and task management tools
---

## Agent

Spawns a nested agent to complete a focused sub-task. The sub-agent gets a fresh conversation history and runs the full agent loop independently.

```json
{
  "tool": "Agent",
  "input": {
    "task": "Read all TypeScript files in src/components/ and write a summary of each component's props interface to components.md"
  }
}
```

The sub-agent has access to all the same tools as the parent. Its final response is returned as the tool result.

**Nesting limit:** 3 levels deep.

Use sub-agents to:
- Parallelize independent research tasks
- Isolate a focused sub-task from the main conversation context
- Prevent tool output from a large scan from filling the parent's context window

---

## Task tools

Task tools let the agent create and track a structured to-do list, visible to the user in the terminal.

### TaskCreate

```json
{
  "tool": "TaskCreate",
  "input": {
    "subject": "Add error handling to the login flow",
    "description": "Wrap the auth call in try/catch and show a user-friendly error message"
  }
}
```

### TaskList

```json
{"tool": "TaskList", "input": {}}
```

Returns all tasks with their status (`pending`, `in_progress`, `completed`).

### TaskGet

```json
{"tool": "TaskGet", "input": {"taskId": "1"}}
```

Returns full details of a single task including description and dependencies.

### TaskUpdate

```json
{
  "tool": "TaskUpdate",
  "input": {
    "taskId": "1",
    "status": "in_progress"
  }
}
```

Valid statuses: `pending`, `in_progress`, `completed`, `deleted`.

Can also update `subject`, `description`, set dependencies with `addBlockedBy`/`addBlocks`.

### TaskStop / TaskOutput

Used by sub-agents to stop a background task or retrieve its output. Generally not called directly by the LLM.
