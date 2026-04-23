"""
Agent Layer — Context Manager
==============================
Tracks conversation length and compacts the message history when it
approaches the context window limit.

Strategy:
- Estimate token count via a simple characters-÷-4 heuristic.
- When usage exceeds COMPACTION_THRESHOLD (75% of context_size), drop
  all but the last KEEP_RECENT_TURNS turn pairs and prepend a single
  summary message listing what tools were called and what they returned.
- This gives the model a clean, coherent history rather than garbled
  truncated snippets, which prevents malformed tool call errors.
"""

from __future__ import annotations

import logging
from typing import Callable

from .message import Message, ToolResultBlock, ToolUseBlock, TextBlock

log = logging.getLogger(__name__)

COMPACTION_THRESHOLD = 0.75   # compact when at 75% of context
KEEP_RECENT_TURNS = 6         # keep last N user+assistant message pairs
MAX_TOOL_RESULT_CHARS = 4000  # truncate individual tool results beyond this


def estimate_tokens(
    messages: list[Message],
    count_tokens_fn: Callable[[str], int] | None = None,
) -> int:
    """
    Estimate token count of *messages*.
    Uses *count_tokens_fn* if provided, otherwise falls back to
    the characters-÷-4 heuristic.
    """
    if count_tokens_fn:
        total = 0
        for m in messages:
            total += count_tokens_fn(m.text_content())
            total += 10  # role tags overhead
        return total

    return sum(m.char_count() for m in messages) // 4


def should_compact(
    messages: list[Message],
    context_size: int,
    count_tokens_fn: Callable[[str], int] | None = None,
) -> bool:
    used = estimate_tokens(messages, count_tokens_fn)
    threshold = int(context_size * COMPACTION_THRESHOLD)
    return used > threshold


def compact(
    messages: list[Message],
    session_id: str = "",
    working_directory: str = ".",
) -> tuple[list[Message], int]:
    """
    Compact the message history by dropping old turns and replacing them
    with a single clean summary message.

    Dropping old turns (rather than snipping tool results) gives the model
    a coherent history and prevents malformed tool calls caused by seeing
    garbled truncated content.

    Returns (compacted_messages, n_turns_dropped).
    """
    if len(messages) <= KEEP_RECENT_TURNS * 2:
        return messages, 0

    cutoff = len(messages) - KEEP_RECENT_TURNS * 2
    old_messages = messages[:cutoff]
    recent_messages = messages[cutoff:]

    # Build a plain-text summary of what happened in the dropped turns.
    summary_lines: list[str] = [
        "[Earlier conversation compacted. Summary of actions taken:]",
    ]
    for msg in old_messages:
        for block in msg.content:
            if isinstance(block, ToolUseBlock):
                args = ", ".join(f"{k}={repr(v)[:60]}" for k, v in block.input.items())
                summary_lines.append(f"- Called {block.name}({args})")
            elif isinstance(block, ToolResultBlock):
                preview = block.content[:120].replace("\n", " ").strip()
                status = "error" if block.is_error else "ok"
                summary_lines.append(f"  → [{status}] {preview}")
            elif isinstance(block, TextBlock) and msg.role == "assistant" and block.text.strip():
                preview = block.text[:120].replace("\n", " ").strip()
                summary_lines.append(f"  (assistant: {preview})")

    summary_text = "\n".join(summary_lines)
    summary_message = Message.user(summary_text)

    n_dropped = len(old_messages)
    log.info("Compacted: dropped %d old messages, kept last %d", n_dropped, len(recent_messages))
    return [summary_message] + recent_messages, n_dropped


def truncate_tool_result(content: str) -> str:
    """Truncate a single tool result to MAX_TOOL_RESULT_CHARS."""
    if len(content) <= MAX_TOOL_RESULT_CHARS:
        return content
    half = MAX_TOOL_RESULT_CHARS // 2
    return (
        content[:half]
        + f"\n\n… [{len(content) - MAX_TOOL_RESULT_CHARS} chars truncated] …\n\n"
        + content[-half:]
    )
