---
title: Tool System
description: How tools work and how to add new ones
---

Tools are the actions the agent can take. Each tool is a Python class in `cyberpaw/agent/tools/` that the orchestrator calls when the LLM emits a tool call.

## Tool call format

The LLM emits tool calls as a JSON object on a single line:

```json
{"tool": "Read", "input": {"file_path": "src/main.py"}}
```

The orchestrator parses these with a multi-strategy parser (`_parse_tool_uses` in `orchestrator.py`) that handles:
1. Single-line JSON `{"tool": ...}`
2. Multi-line pretty-printed JSON
3. XML fallback `<tool_use><name>...</name><input>...</input></tool_use>`

---

## Tool base class

Every tool inherits from `Tool` in `harness/tool_registry.py`:

```python
class Tool(abc.ABC):
    name: str           # exact name the LLM uses in tool calls
    description: str    # shown to the LLM in the system prompt
    input_schema: dict  # JSON Schema for the input parameters

    @abc.abstractmethod
    async def call(self, input: dict, ctx: ToolContext) -> ToolResult: ...

    def is_read_only(self, input: dict) -> bool:
        return False  # override to True for read-only tools
```

`ToolResult` has three fields: `output: str`, `is_error: bool`, `summary: str`.

`ToolContext` carries runtime state: `working_directory`, `permission_mode`, `depth` (sub-agent nesting level), `session_id`, `network_enabled`.

---

## Registering a tool

1. Create a class in `agent/tools/your_tool.py` inheriting from `Tool`
2. Import and register it in `agent/main.py`:

```python
from tools.your_tool import YourTool
registry.register(YourTool())
```

The tool's `name`, `description`, and `input_schema` are automatically included in the system prompt so the LLM knows the tool exists.

---

## All tools

| Tool | Category | Read-only |
|------|----------|-----------|
| `Read` | File | ✓ |
| `Write` | File | |
| `Edit` | File | |
| `MultiEdit` | File | |
| `Glob` | File | ✓ |
| `Grep` | File | ✓ |
| `ListDir` | File | ✓ |
| `Move` | File | |
| `DeleteFile` | File | |
| `Bash` | Execution | |
| `REPL` | Execution | |
| `Sleep` | Execution | ✓ |
| `WebFetch` | Web | ✓ |
| `WebSearch` | Web | ✓ |
| `Playwright` | Web | |
| `Agent` | Multi-agent | |
| `TaskCreate` | Task | |
| `TaskGet` | Task | ✓ |
| `TaskList` | Task | ✓ |
| `TaskUpdate` | Task | |

Web tools require **Network Access** to be enabled in Settings.
