---
title: Introduction
description: What is CyberPaw and how it works
---

CyberPaw is a desktop coding agent that runs a local LLM on your machine and gives it access to your filesystem and shell — the same capabilities as cloud-based coding assistants, but entirely offline.

## Stack

| Layer | Technology |
|-------|-----------|
| Desktop shell | Tauri 2 (Rust) |
| Frontend | React 18 + TypeScript + xterm.js |
| Agent sidecar | Python 3.11+ asyncio |
| LLM inference | llama-cpp-python (GGUF) |
| Communication | NDJSON over stdin/stdout |

## Key design decisions

**Why a sidecar instead of a Tauri plugin?**
Python has a richer ML ecosystem. A sidecar lets the agent layer be developed and tested independently of the Rust/Tauri build cycle.

**Why NDJSON over stdin/stdout?**
Simple, language-agnostic, and debuggable. Any process that can read/write lines of JSON can be a CyberPaw sidecar.

**Why local-first?**
No API keys, no data leaving your machine, no latency from network calls, no monthly bill.

## Next steps

- [Install CyberPaw](/cyberpaw/getting-started/installation)
- [Architecture overview](/cyberpaw/architecture/overview)
- [Tool reference](/cyberpaw/tools/overview)
