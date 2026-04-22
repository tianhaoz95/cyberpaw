---
title: Contributing
description: How to develop and extend CyberPaw
---

## Development setup

```bash
cd cyberpaw
./scripts/setup.sh
npm run tauri dev
```

The frontend hot-reloads on save. After changing Python agent code, rebuild the sidecar:

```bash
./scripts/build-sidecar.sh
```

---

## Adding a tool

1. Create `agent/tools/your_tool.py`:

```python
from harness.tool_registry import Tool, ToolContext, ToolResult

class YourTool(Tool):
    name = "YourTool"
    description = "One sentence description shown to the LLM."
    input_schema = {
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "What this param does"}
        },
        "required": ["param"]
    }

    def is_read_only(self, input: dict) -> bool:
        return True  # set False if the tool modifies state

    async def call(self, input: dict, ctx: ToolContext) -> ToolResult:
        result = do_something(input["param"], ctx.working_directory)
        return ToolResult.ok(result, summary="Did something")
```

2. Register it in `agent/main.py`:

```python
from tools.your_tool import YourTool
registry.register(YourTool())
```

That's it — the tool is automatically included in the system prompt and available to the LLM.

---

## Running tests

```bash
# Unit tests
cd cyberpaw/agent
../.venv/bin/pytest test_task_tools.py -v

# Integration tests (requires a loaded model)
PYTHONPATH=. ../.venv/bin/python ../tests/test_integration_tool_call.py
```

---

## Project conventions

**Python sidecar:**
- All tool `call()` methods are `async` — use `asyncio.to_thread` for blocking I/O
- Return `ToolResult.error(msg)` for expected failures; raise only for unexpected exceptions
- `ctx.working_directory` is the agent's current working directory — use it as the base for relative paths

**Frontend:**
- Config changes go through `updateConfig()` from `useConfig` — never write to `localStorage` directly
- Terminal output goes through `writeTerminal` (from `useAgent`) — never call `xterm` APIs directly from components
- All Tauri invocations are in `useAgent.ts` — keep components free of `invoke()` calls

**Protocol:**
- New sidecar → frontend message types: add to `useAgent.ts` event handler and document in the protocol page
- New Tauri commands: add to `src-tauri/src/lib.rs` and the capabilities file if new permissions are needed

---

## Building the docs site

```bash
cd docs
npm install
npm run dev       # local preview at localhost:4321
npm run build     # production build to docs/dist/
```

The docs deploy automatically to GitHub Pages on every push to `main` that touches `docs/`.
