---
title: LLM Backends
description: llama.cpp backend and auto-selection logic
---

The backend layer lives in `cyberpaw/agent/backends/` and provides a uniform async interface over local LLM inference engines.

## Interface

`backends/base.py` defines `LLMBackend`:

```python
class LLMBackend(abc.ABC):
    async def load(self, model_path: str, on_progress: Callable[[int], None]) -> None: ...
    def is_loaded(self) -> bool: ...
    def unload(self) -> None: ...
    async def generate(self, prompt: str, params: GenerateParams) -> AsyncIterator[str]: ...
    def count_tokens(self, text: str) -> int: ...
    def chat_template(self) -> str | None: ...
    def eos_strings(self) -> list[str]: ...
    def context_size(self) -> int: ...
```

`generate()` is an async generator — it yields individual token strings as they are produced by the model.

---

## llama.cpp backend

`backends/llamacpp_backend.py` — wraps `llama-cpp-python` for GGUF model inference.

**Loading:** runs in a thread via `asyncio.to_thread` to keep the event loop responsive. Reports load progress (0–100%) via the `on_progress` callback.

**Inference:** runs in a thread pool via `loop.run_in_executor`. Tokens are passed back to the async generator through an `asyncio.Queue`.

**Chat template:** reads the Jinja2 chat template embedded in the GGUF metadata (`tokenizer.chat_template`). Falls back to a hand-rolled Gemma template if absent.

**Stop sequences:** reads EOS token IDs from GGUF metadata keys `tokenizer.ggml.eos_token_id`, `tokenizer.ggml.eot_token_id`, and `tokenizer.ggml.eom_token_id` to build a complete stop sequence list.

---

## Auto-selection and context sizing

`backends/selector.py` — `calculate_context_size()` determines the largest safe context window for the available hardware:

```
budget_gb     = total_RAM_gb × 0.75
kv_budget_gb  = budget_gb − model_weight_gb
raw_n_ctx     = kv_budget_gb × 1024³ / kv_bytes_per_token
n_ctx         = round_down_to_power_of_2(raw_n_ctx)
n_ctx         = clamp(n_ctx, 4096, 65536)
```

KV cache bytes per token for known models:

| Model | Bytes/token |
|-------|------------|
| Gemma 4 E2B | 106,496 |
| Gemma 4 E4B | 139,264 |
| Unknown | 80,000 (conservative) |

The 65,536 token cap is a hard limit — `n_ctx=131072` causes `llama_decode` errors on Apple Silicon with llama-cpp-python 0.3.x.

---

## GenerateParams

```python
@dataclass
class GenerateParams:
    max_new_tokens: int = 4096
    temperature: float = 1.0
    top_p: float = 0.95
    repetition_penalty: float = 1.1
    stop_sequences: list[str] = ["<end_of_turn>", "</start_of_turn>"]
```

Temperature is set per model family: `0.0` for Gemma (deterministic coding), `0.2` for others.

---

## Prompt rendering

`prompt/model_template.py` — renders the full prompt string for each generation step:

1. Reads the Jinja2 chat template from the GGUF metadata
2. Converts `Message` objects to HF-style `{"role": ..., "content": ...}` dicts
3. Serialises `ToolUseBlock` and `ToolResultBlock` as XML inside the content field
4. Renders with `add_generation_prompt=True` to append the assistant turn opener
5. Falls back to the hand-rolled Gemma template if Jinja2 is unavailable or the template fails
