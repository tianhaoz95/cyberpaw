"""
Prompt Layer — Model-agnostic chat template renderer
=====================================================
Reads the Jinja2 chat template embedded in the GGUF file via the backend
and uses it to render the full prompt string.  Falls back to the hand-rolled
Gemma template when no embedded template is available (AirLLM backend, very
old GGUF files, or unit tests that use a stub backend).

Message serialisation
---------------------
Tool use and tool result blocks are converted to the same XML format used
throughout the agent, then embedded as plain text inside the "content" field
of each chat message dict.  The Jinja2 template sees a standard HF-style
message list:

  [
    {"role": "system",    "content": "<system prompt + tools XML>"},
    {"role": "user",      "content": "..."},
    {"role": "assistant", "content": "... <tool_use>...</tool_use>"},
    {"role": "user",      "content": "<tool_result ...>...</tool_result>"},
    ...
  ]

Jinja2 globals
--------------
Most HF chat templates reference ``bos_token``, ``eos_token``, and a
``raise_exception`` helper.  We inject these from the backend's vocabulary
metadata so the template renders correctly without crashing on undefined names.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backends.base import LLMBackend
    from harness.message import Message

log = logging.getLogger(__name__)


def _blocks_to_text(msg: "Message") -> str:
    """Serialise a Message's content blocks to a plain text string."""
    from harness.message import TextBlock, ToolUseBlock, ToolResultBlock
    parts: list[str] = []
    for block in msg.content:
        if isinstance(block, TextBlock):
            parts.append(block.text)
        elif isinstance(block, ToolUseBlock):
            parts.append(
                f"<tool_use>\n<name>{block.name}</name>\n"
                f"<input>\n{json.dumps(block.input, indent=2)}\n</input>\n</tool_use>"
            )
        elif isinstance(block, ToolResultBlock):
            status = "error" if block.is_error else "ok"
            parts.append(
                f'<tool_result id="{block.tool_use_id}" status="{status}">\n'
                f"{block.content}\n</tool_result>"
            )
    return "\n".join(parts)


def _messages_to_dicts(
    messages: list["Message"],
    system_prompt: str,
    tools_xml: str,
) -> list[dict]:
    """Convert Message objects to the HF chat-template dict format."""
    result: list[dict] = [
        {"role": "system", "content": f"{system_prompt}\n\n{tools_xml}"},
    ]
    for msg in messages:
        role = "assistant" if msg.role == "assistant" else "user"
        result.append({"role": role, "content": _blocks_to_text(msg)})
    return result


def _get_vocab_token(meta: dict, token_id_key: str) -> str:
    """Look up a token string from GGUF metadata by its ID key."""
    id_str = meta.get(token_id_key)
    if id_str is None:
        return ""
    try:
        token_id = int(id_str)
        raw = meta.get("tokenizer.ggml.tokens")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, list) and token_id < len(raw):
            return raw[token_id]
    except Exception:
        pass
    return ""


def render_prompt(
    messages: list["Message"],
    system_prompt: str,
    tools_xml: str,
    backend: "LLMBackend",
) -> str:
    """
    Render the full prompt string for the next generation step.

    Uses the Jinja2 chat template embedded in the GGUF when available;
    falls back to the hand-rolled Gemma template otherwise.
    """
    template_str = backend.chat_template()

    if template_str is None:
        # Fallback: delegate to the existing hand-rolled Gemma renderer.
        from prompt.gemma_template import render_prompt as _gemma_render
        return _gemma_render(messages, system_prompt, tools_xml)

    try:
        import jinja2
    except ImportError:
        log.warning("jinja2 not installed — falling back to Gemma template")
        from prompt.gemma_template import render_prompt as _gemma_render
        return _gemma_render(messages, system_prompt, tools_xml)

    chat_messages = _messages_to_dicts(messages, system_prompt, tools_xml)

    # Build Jinja2 globals expected by most HF templates.
    meta: dict = {}
    if hasattr(backend, "_llm") and backend._llm is not None:
        meta = getattr(backend._llm, "metadata", {})

    bos_token = _get_vocab_token(meta, "tokenizer.ggml.bos_token_id")
    eos_token = _get_vocab_token(meta, "tokenizer.ggml.eos_token_id")

    def _raise(msg: str) -> None:
        raise jinja2.TemplateError(msg)

    env = jinja2.Environment(
        undefined=jinja2.Undefined,
        keep_trailing_newline=True,
    )
    env.globals.update(
        bos_token=bos_token,
        eos_token=eos_token,
        raise_exception=_raise,
    )

    try:
        tmpl = env.from_string(template_str)
        return tmpl.render(
            messages=chat_messages,
            add_generation_prompt=True,
        )
    except Exception as exc:
        log.warning("Jinja2 template render failed (%s) — falling back to Gemma template", exc)
        from prompt.gemma_template import render_prompt as _gemma_render
        return _gemma_render(messages, system_prompt, tools_xml)
