# CyberPaw

A fully local, offline-first coding agent desktop app. No API keys required. Runs on your machine using local LLMs via a Python sidecar.

**Stack:** Tauri 2 (Rust) · React 18 + TypeScript · Python asyncio sidecar · llama-cpp-python

---

## Requirements

| Tool | Version |
|------|---------|
| Rust | 1.77+ (`rustup update`) |
| Node.js | 18+ |
| Python | 3.11+ |
| Xcode CLT | (macOS) `xcode-select --install` |

---

## Setup

Run the one-shot setup script from `cyberpaw/`:

```bash
cd cyberpaw
./scripts/setup.sh
```

This will:
1. Check prerequisites (Rust, Node, Python)
2. Install npm dependencies
3. Create a `.venv/` and install Python dependencies (llama-cpp-python, psutil, jinja2, etc.)
4. Build the Python sidecar binary into `src-tauri/binaries/`

**macOS Metal GPU acceleration** (recommended if you have Apple Silicon):

```bash
./scripts/setup.sh --metal
```

---

## Running

```bash
cd cyberpaw
npm run tauri dev
```

On first launch:
1. Open **Settings** (⚙ top-right)
2. The **Models** panel shows available models — any already downloaded show a green **✓ Installed** badge with a **Load** button
3. To download a new model, select it and click **Download**
4. Once downloaded, click **Load** — the model loads and the terminal shows progress

---

## Downloading a Model

Models are saved to `~/CyberPaw/models/` by default. Supported models:

| Model | Size | RAM needed |
|-------|------|------------|
| Gemma 4 E2B Q4_K_M *(recommended)* | 2.9 GB | 8 GB |
| Gemma 4 E4B Q4_K_M | 4.6 GB | 8+ GB |

You can also use the download script directly:

```bash
./scripts/download-model.sh
```

---

## Testing

### Agent unit tests

```bash
cd cyberpaw/agent
../.venv/bin/pytest test_task_tools.py -v
```

### Integration tests (tool call roundtrips)

Requires a model loaded at `~/CyberPaw/models/gemma-4-E2B-it-Q4_K_M.gguf`.

```bash
cd cyberpaw/agent
PYTHONPATH=. ../.venv/bin/python ../tests/test_integration_tool_call.py
PYTHONPATH=. ../.venv/bin/python ../tests/test_model_loading_flow.py
```

---

## Production Build

```bash
cd cyberpaw
npm run build && npm run tauri build
```

Output: `src-tauri/target/release/bundle/macos/CyberPaw.app`

---

## Project Layout

```
cyberpaw/
├── agent/                  # Python sidecar
│   ├── main.py             # NDJSON event loop
│   ├── harness/            # Orchestrator, context manager, permissions
│   ├── tools/              # 18 tool implementations (Read, Write, Edit, Bash, …)
│   ├── backends/           # llama.cpp backend + auto-selector
│   └── prompt/             # System prompt + chat template renderer
├── src/                    # React frontend
│   ├── App.tsx
│   ├── components/         # Terminal, MenuBar, Settings, ModelDownloader, …
│   └── hooks/              # useAgent (IPC bridge), useConfig (persistence)
├── src-tauri/              # Rust/Tauri native shell
│   ├── src/                # sidecar.rs, commands, config
│   └── capabilities/       # Tauri permission scopes
├── scripts/
│   ├── setup.sh            # One-shot setup
│   ├── build-sidecar.sh    # PyInstaller sidecar build
│   └── download-model.sh   # Model downloader
└── tests/                  # Integration tests
```

---

## Architecture

All communication between the Tauri shell and the Python agent is **NDJSON over stdin/stdout**.

```
WebView (React)  ←→  Tauri (Rust)  ←→  Python sidecar
     IPC invoke          pipe            asyncio loop
```

Key sidecar events: `token`, `tool_start`, `tool_end`, `status`, `model_progress`, `model_status`, `download_progress`, `download_done`

Key Tauri commands: `send_input`, `set_working_directory`, `load_model`, `get_model_status`, `interrupt`
