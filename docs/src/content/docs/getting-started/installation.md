---
title: Installation
description: Set up CyberPaw on your machine
---

## Requirements

| Tool | Version | Notes |
|------|---------|-------|
| Rust | 1.77+ | `rustup update` |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| Python | 3.11+ | [python.org](https://python.org) |
| Xcode CLT | latest | macOS only — `xcode-select --install` |

Minimum hardware: **8 GB RAM** (Gemma 4 E2B). Recommended: **16 GB RAM** (Gemma 4 E4B).

---

## One-shot setup

Run the setup script from the `cyberpaw/` directory:

```bash
cd cyberpaw
./scripts/setup.sh
```

This script:
1. Verifies Rust, Node.js, and Python are installed
2. Runs `npm install` for the frontend
3. Creates a `.venv/` and installs Python dependencies
4. Builds the Python sidecar binary into `src-tauri/binaries/`

### Apple Silicon — Metal GPU acceleration

```bash
./scripts/setup.sh --metal
```

This compiles `llama-cpp-python` with Metal support, which significantly speeds up inference on M-series Macs.

---

## Manual setup

If you prefer to run steps individually:

```bash
cd cyberpaw

# 1. Frontend dependencies
npm install

# 2. Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Python dependencies
pip install psutil jinja2 diff-match-patch httpx playwright

# 4. llama-cpp-python (CPU)
pip install llama-cpp-python

# 4. llama-cpp-python (macOS Metal)
CMAKE_ARGS="-DLLAMA_METAL=on" pip install llama-cpp-python --force-reinstall --no-cache-dir

# 5. Build the sidecar binary
./scripts/build-sidecar.sh
```

---

## Verifying the install

```bash
# Check the sidecar binary exists
ls src-tauri/binaries/

# Run agent unit tests
cd agent && ../.venv/bin/pytest test_task_tools.py -v
```
