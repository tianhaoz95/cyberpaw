"""
Agent Layer — Context Manager
==============================
Tracks conversation length and compacts old tool results when the
message list approaches the context window limit.

Strategy (mirrors claude-code's /compact command logic):
- Estimate token count via a simple characters-÷-4 heuristic.
- When usage exceeds ``COMPACTION_THRESHOLD`` (75 % of context_size),
  replace older ToolResultBlock content with a short summary.
- Keeps the last ``KEEP_RECENT_TURNS`` assistant+user turn pairs intact
  so the model retains recent context.
"""

from __future__ import annotations

import logging
from typing import Callable

from .message import Message, ToolResultBlock, TextBlock

log = logging.getLogger(__name__)

COMPACTION_THRESHOLD = 0.75   # compact when at 75 % of context
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
        # For efficiency, we join text content and count once, but messages
        # also have metadata (roles, tags) that gemma_template adds.
        # A perfectly accurate count would require rendering the full prompt,
        # but that's expensive. This is a "good enough" middle ground.
        total = 0
        for m in messages:
            total += count_tokens_fn(m.text_content())
            # Add a small constant for role tags (<start_of_turn>user\n)
            total += 10
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


def compact(messages: list[Message]) -> tuple[list[Message], int]:
    """
    Compact old tool results in *messages* in-place (returns new list).

    Returns
    -------
    (compacted_messages, n_compacted)
    """
    if len(messages) <= KEEP_RECENT_TURNS * 2:
        return messages, 0

    cutoff = len(messages) - KEEP_RECENT_TURNS * 2
    n_compacted = 0

    new_messages: list[Message] = []
    for i, msg in enumerate(messages):
        if i >= cutoff:
            new_messages.append(msg)
            continue

        # Replace large ToolResultBlock content with a summary
        new_content = []
        for block in msg.content:
            if isinstance(block, ToolResultBlock) and len(block.content) > 200:
                summary = block.content[:120].rstrip() + " … [compacted]"
                new_content.append(ToolResultBlock(
                    tool_use_id=block.tool_use_id,
                    content=summary,
                    is_error=block.is_error,
                ))
                n_compacted += 1
            else:
                new_content.append(block)
        new_messages.append(Message(role=msg.role, content=new_content))

    log.info("Compacted %d tool results", n_compacted)
    return new_messages, n_compacted


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
