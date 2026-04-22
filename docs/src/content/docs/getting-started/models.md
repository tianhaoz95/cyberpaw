---
title: Loading a Model
description: Download and load a local LLM for CyberPaw
---

## Supported models

| Model | Size | RAM needed | Best for |
|-------|------|-----------|---------|
| Gemma 4 E2B Q4_K_M *(recommended)* | 2.9 GB | 8 GB | Fast, everyday use |
| Gemma 4 E4B Q4_K_M | 4.6 GB | 8+ GB | Better code quality |

Models are saved to `~/CyberPaw/models/` by default.

---

## Downloading via the UI

1. Open **Settings** (⚙ top-right)
2. The **Models** panel lists all available models
3. Models already on disk show a green **✓ Installed** badge and a **Load** button
4. To download a new model, select it and click **Download**
5. After download completes, click **Load** — the terminal shows the loading spinner

---

## Downloading via script

```bash
cd cyberpaw
./scripts/download-model.sh
```

---

## Context window

CyberPaw auto-calculates the context window from available RAM:

```
budget = total_RAM × 0.75 − model_weight_size
n_ctx  = budget / kv_bytes_per_token  (rounded to nearest power of 2)
max    = 65,536 tokens
```

You can override this in **Settings → Context Window**.

---

## Switching models

Open **Settings**, find the new model in the Models panel, and click **Load**. The terminal shows a loading spinner and prints `Model ready.` when complete. The new model path is persisted and auto-loaded on next launch.

To clear the saved model path, open **Settings** and click **Clear** next to the Active Model field.
