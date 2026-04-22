---
title: Running the App
description: Start CyberPaw in development or production mode
---

## Development mode

```bash
cd cyberpaw
npm run tauri dev
```

The frontend hot-reloads on file changes. The Python sidecar must be rebuilt manually after changes to `agent/`.

On startup the terminal prints:

```
Working directory: ~/your/project
⠋ Loading gemma-4-E2B-it-Q4_K_M.gguf…
Model ready.
❯
```

---

## Production build

```bash
cd cyberpaw
npm run build && npm run tauri build
```

Output: `src-tauri/target/release/bundle/macos/CyberPaw.app`

---

## Terminal usage

Type your request at the `❯` prompt and press **Enter**.

| Key | Action |
|-----|--------|
| `Enter` | Submit input |
| `Ctrl-C` | Interrupt the running agent |
| `↑` / `↓` | Navigate input history |

### Special prefix

Prefix a command with `!` to run it directly as a shell command, bypassing the LLM:

```
❯ ! ls -la
```

---

## Settings

Click the **⚙** icon in the top-right to open Settings:

- **Working Directory** — the root directory the agent operates in
- **Models** — download and load models; installed models show a **✓ Installed** badge
- **Permission Mode** — controls which tool calls require approval
- **Context Window** — token budget (auto-calculated from RAM by default)
- **Network Access** — enables WebFetch, WebSearch, and Playwright tools

---

## Testing

```bash
# Unit tests
cd cyberpaw/agent
../.venv/bin/pytest test_task_tools.py -v

# Integration tests (requires a model at ~/CyberPaw/models/)
PYTHONPATH=. ../.venv/bin/python ../tests/test_integration_tool_call.py
PYTHONPATH=. ../.venv/bin/python ../tests/test_model_loading_flow.py
```
