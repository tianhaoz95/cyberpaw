---
title: Sidecar Protocol
description: NDJSON communication between Tauri and the Python agent
---

All communication between the Tauri Rust core and the Python sidecar is **newline-delimited JSON (NDJSON)** over the process's stdin/stdout pipe. Each message is a single JSON object on one line.

## Tauri → Sidecar (stdin)

### User input
```json
{"type": "input", "text": "refactor this function to use async/await"}
```

### Change working directory
```json
{"type": "cd", "path": "/Users/alice/projects/myapp"}
```

### Reset conversation
```json
{"type": "reset"}
```

### Interrupt running agent
```json
{"type": "interrupt"}
```

### Load a model
```json
{"type": "load_model", "model_path": "~/CyberPaw/models/gemma-4-E4B-it-Q4_K_M.gguf", "backend": "llamacpp"}
```

### Update config at runtime
```json
{"type": "config", "patch": {"permission_mode": "auto_read", "max_new_tokens": 2048}}
```

### Tool permission response
```json
{"type": "tool_ack", "id": "perm_a1b2c3d4", "decision": "allow"}
```

### Download a model
```json
{"type": "download_start", "model_id": "gemma-4-e2b-q4km", "dest_dir": "~/CyberPaw/models"}
```

### Request current model status
```json
{"type": "status_request"}
```

---

## Sidecar → Tauri (stdout)

### Streamed token
```json
{"type": "token", "text": "Here is the refactored function:"}
```

### Tool call started
```json
{"type": "tool_start", "id": "tu_abc123", "tool": "Read", "input": {"file_path": "src/main.py"}}
```

### Tool call completed
```json
{"type": "tool_end", "id": "tu_abc123", "tool": "Read", "summary": "Read 142 lines", "is_error": false}
```

### Agent phase change
```json
{"type": "status", "phase": "thinking"}
{"type": "status", "phase": "tool_running", "tool": "Bash"}
{"type": "status", "phase": "idle"}
```

### Model load progress
```json
{"type": "model_progress", "pct": 42}
```

### Model ready
```json
{"type": "model_status", "loaded": true, "backend": "llama.cpp", "context_size": 32768, "max_new_tokens": 4096}
```

### Memory stats (from status_request poll)
```json
{"type": "model_status", "backend": "llama.cpp", "loaded": true, "vram_used_mb": 4200, "model_size_mb": 3800, "kv_cache_mb": 400}
```

### Generation stats (after each turn)
```json
{"type": "generation_stats", "tokens": 312, "elapsed_ms": 8400, "tokens_per_sec": 37.1}
```

### Permission request (tool needs user approval)
```json
{"type": "tool_permission_request", "id": "perm_a1b2c3d4", "tool": "Bash", "input": {"command": "rm -rf dist/"}}
```

### Download progress
```json
{"type": "download_progress", "model_id": "gemma-4-e2b-q4km", "pct": 67, "downloaded_mb": 1940.2, "total_mb": 2900.0, "speed_mbps": 12.4}
```

### Download complete
```json
{"type": "download_done", "model_id": "gemma-4-e2b-q4km", "path": "/Users/alice/CyberPaw/models/gemma-4-E2B-it-Q4_K_M.gguf"}
```

### Error
```json
{"type": "error", "message": "Model not loaded yet."}
```

---

## Message ordering

A typical agent turn looks like:

```
← {"type": "status", "phase": "thinking"}
← {"type": "token", "text": "I'll read the file first.\n"}
← {"type": "tool_start", "id": "t1", "tool": "Read", ...}
← {"type": "status", "phase": "tool_running", "tool": "Read"}
← {"type": "tool_end", "id": "t1", ...}
← {"type": "status", "phase": "thinking"}
← {"type": "token", "text": "The file contains..."}
← {"type": "generation_stats", ...}
← {"type": "status", "phase": "idle"}
```
