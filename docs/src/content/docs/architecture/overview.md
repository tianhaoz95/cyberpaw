---
title: Architecture Overview
description: High-level design of CyberPaw
---

CyberPaw is split into three processes that communicate over well-defined interfaces.

```
┌─────────────────────────────────────────────────────┐
│                   Tauri Window                       │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │         React Frontend (WebView)              │   │
│  │  Terminal · MenuBar · Settings · Dialogs      │   │
│  └──────────────────┬───────────────────────────┘   │
│                     │  Tauri invoke() / events       │
│  ┌──────────────────▼───────────────────────────┐   │
│  │           Rust Core (Tauri)                   │   │
│  │  sidecar.rs · commands · config persistence   │   │
│  └──────────────────┬───────────────────────────┘   │
│                     │  NDJSON over stdin/stdout      │
└─────────────────────┼───────────────────────────────┘
                      │
         ┌────────────▼───────────────┐
         │    Python Sidecar          │
         │  orchestrator · tools      │
         │  llama-cpp-python backend  │
         └────────────────────────────┘
```

## Component responsibilities

### React frontend
- Renders the terminal UI using **xterm.js**
- Manages user config via `localStorage` + Tauri store plugin
- Displays tool call events, permission dialogs, and model load progress
- Communicates with Rust via `invoke()` commands and `agent://stream` events

### Rust core (Tauri)
- Spawns and owns the Python sidecar process
- Bridges WebView ↔ sidecar: forwards `invoke()` calls as NDJSON to stdin, emits sidecar stdout as Tauri events
- Persists config via `tauri-plugin-store`
- Manages window lifecycle and native OS integration

### Python sidecar
- Reads NDJSON commands from stdin, writes NDJSON events to stdout
- Runs the agent loop: LLM inference → tool execution → repeat
- Manages conversation history, context compaction, and permissions
- Hosts the llama.cpp backend for local inference

## Key design decisions

**Why a sidecar instead of a Tauri plugin?**
Python has a richer ML ecosystem (llama-cpp-python, huggingface-hub, playwright). A sidecar lets the agent layer be developed and tested independently of the Rust/Tauri build cycle.

**Why NDJSON over stdin/stdout?**
Simple, language-agnostic, and debuggable. Any process that can read/write lines of JSON can be a CyberPaw sidecar.

**Why XML tool calls?**
Local models (Gemma, Llama) are trained on XML more than JSON for structured outputs. The XML format is more robust to partial generation and easier to parse incrementally.

## Directory structure

```
cyberpaw/
├── agent/              # Python sidecar
│   ├── main.py         # NDJSON event loop entry point
│   ├── harness/        # Orchestrator, context, permissions
│   ├── tools/          # 20 tool implementations
│   ├── backends/       # llama.cpp backend + selector
│   └── prompt/         # System prompt + chat template renderer
├── src/                # React frontend
│   ├── App.tsx
│   ├── components/
│   └── hooks/
├── src-tauri/          # Rust/Tauri native shell
│   ├── src/
│   └── capabilities/   # Tauri permission scopes
└── scripts/            # setup.sh, build-sidecar.sh, download-model.sh
```
