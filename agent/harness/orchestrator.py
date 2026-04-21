"""
Harness — Orchestrator
=======================
The main agent loop.  Mirrors the QueryEngine + runAgent pattern from
claude-code but adapted for local LLM XML-based tool calling.

Loop
----
1. Append user message to history.
2. Compact history if near context limit.
3. Render full prompt (Gemma template).
4. Stream tokens from the LLM backend.
5. Parse <tool_use> blocks from the streamed text.
6. For each tool call:
   a. Check permissions (may suspend and wait for user approval).
   b. Execute the tool.
   c. Append ToolResultBlock to history.
7. If any tool calls were made → goto 2.
8. Emit ``status: idle`` and return the final text response.

The orchestrator is also used by sub-agents (via subagent.py) with a
clean message history and a sub-task prompt.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Callable

from backends.base import GenerateParams, LLMBackend
from prompt.model_template import render_prompt
from prompt.system_prompt import build_system_prompt, build_session_context
from prompt.tools_xml import render_tools_xml
from .context_manager import compact, should_compact, truncate_tool_result
from .message import Message, TextBlock, ToolResultBlock, ToolUseBlock
from .permissions import PermissionDenied, PermissionManager, PermissionMode
from .tool_registry import ToolContext, ToolRegistry

log = logging.getLogger(__name__)

MAX_TURNS = 40  # hard cap on tool-call iterations per user message


class Orchestrator:
    """
    Stateful agent loop for a single conversation session.

    Parameters
    ----------
    backend:
        Loaded LLM backend (model must be ready before first call).
    registry:
        Tool registry with all available tools.
    system_prompt:
        Pre-built system prompt string.
    working_directory:
        Absolute path to the user's project directory.
    permission_mode:
        Controls which tool calls require user approval.
    emit_fn:
        Callable that accepts a dict and sends it as an NDJSON line to
        the Tauri frontend.  All agent output goes through this.
    depth:
        Nesting depth (0 = root agent, 1+ = sub-agents).
    generate_params:
        Inference hyperparameters.
    context_size:
        Model context window in tokens (used for compaction decisions).
    """

    def __init__(
        self,
        backend: LLMBackend,
        registry: ToolRegistry,
        system_prompt: str,
        working_directory: str,
        permission_mode: PermissionMode,
        emit_fn: Callable[[dict], None],
        depth: int = 0,
        generate_params: GenerateParams | None = None,
        context_size: int = 8192,
        session_id: str = "",
        network_enabled: bool = False,
    ) -> None:
        self._backend = backend
        self._registry = registry
        self._system_prompt = system_prompt
        self._working_directory = working_directory
        self._permission_mode = permission_mode
        self._emit = emit_fn
        self._depth = depth
        self._params = generate_params or GenerateParams()
        self._context_size = context_size
        self._session_id = session_id
        self._network_enabled = network_enabled

        self._messages: list[Message] = []
        self._permission_manager = PermissionManager()
        self._interrupted = False

    # ── Public API ─────────────────────────────────────────────────────────────

    def interrupt(self) -> None:
        """Signal the running loop to stop after the current tool completes."""
        self._interrupted = True

    def set_working_directory(self, path: str) -> None:
        self._working_directory = path
        self._system_prompt = build_system_prompt()

    def resolve_permission(self, request_id: str, approved: bool) -> None:
        """Called when a tool_ack arrives from the frontend."""
        self._permission_manager.resolve(request_id, approved)

    async def handle_input(self, text: str) -> None:
        """Process a user message and run the agent loop."""
        self._interrupted = False
        
        # Inject session context into the first user message for KV caching
        # of the system prompt prefix.
        if not self._messages:
            context = build_session_context(self._working_directory)
            text = f"{context}\n\nUser: {text}"
            
        self._messages.append(Message.user(text))
        self._emit({"type": "status", "phase": "thinking"})
        try:
            await self._agent_loop()
        except asyncio.CancelledError:
            self._emit({"type": "error", "message": "Cancelled"})
        except Exception as exc:
            log.exception("Agent loop error")
            self._emit({"type": "error", "message": str(exc)})
        finally:
            self._emit({"type": "status", "phase": "idle"})

    async def run_task(self, task: str) -> str:
        """
        Run a single task to completion (used by sub-agents).
        Returns the final assistant text response.
        """
        # Inject session context into the first user message
        if not self._messages:
            context = build_session_context(self._working_directory)
            task = f"{context}\n\nUser: {task}"
            
        self._messages.append(Message.user(task))
        await self._agent_loop()
        # Return the last assistant text
        for msg in reversed(self._messages):
            if msg.role == "assistant":
                return msg.text_content()
        return ""

    def reset(self) -> None:
        """Clear conversation history."""
        self._messages = []
        self._interrupted = False

    # ── Internal loop ─────────────────────────────────────────────────────────

    async def _agent_loop(self) -> None:
        tools_xml = render_tools_xml(self._registry)

        # Derive stop sequences from the model's own EOS vocabulary so that
        # every model family (Gemma, Qwen, …) stops on its correct token.
        backend_eos = self._backend.eos_strings()
        if backend_eos:
            self._params.stop_sequences = backend_eos

        # Prime the KV cache with the static system prefix.
        # Render a single-turn prompt with an empty user message to get the
        # header portion, then strip the empty message body so only the
        # static prefix (BOS + system turn) is cached.
        from harness.message import Message as _Msg
        _primer = render_prompt([_Msg.user("")], self._system_prompt, tools_xml, self._backend)
        await self._backend.prime_cache(_primer)

        for turn in range(MAX_TURNS):
            if self._interrupted:
                self._emit({"type": "token", "text": "\n[interrupted]\n"})
                break

            # Compact if near context limit
            if should_compact(
                self._messages,
                self._context_size,
                count_tokens_fn=self._backend.count_tokens,
            ):
                self._messages, n = compact(self._messages)
                if n:
                    self._emit({
                        "type": "system",
                        "text": f"[compacted {n} tool results to save context]",
                    })

            # Render prompt and call the LLM
            prompt = render_prompt(self._messages, self._system_prompt, tools_xml, self._backend)
            response_text = await self._stream_llm(prompt)

            # Parse tool calls from the response
            tool_uses = _parse_tool_uses(response_text)

            # Build assistant message (text + tool_use blocks)
            assistant_content = []
            # Text before the first tool_use tag
            pre_text = _text_before_first_tool(response_text)
            if pre_text.strip():
                assistant_content.append(TextBlock(text=pre_text))
            for tu in tool_uses:
                assistant_content.append(tu)

            if assistant_content:
                self._messages.append(
                    Message(role="assistant", content=assistant_content)
                )

            # Detect failed tool calls (Gap 9)
            if not tool_uses and ("<tool_use>" in response_text or "<name>" in response_text):
                error_msg = (
                    "Your tool call was malformed. Ensure you use the exact "
                    "<tool_use><name>...</name><input>...</input></tool_use> format "
                    "with valid, single-line JSON in the <input> block."
                )
                self._messages.append(Message.user(error_msg))
                self._emit({
                    "type": "token",
                    "text": f"\n[error: malformed tool call, retrying...]\n",
                })
                # continue to next turn to let the model retry
                continue

            if not tool_uses:
                if not response_text.strip():
                    # Backend returned nothing — surface this rather than silently
                    # ending the turn with no output visible to the user.
                    self._emit({
                        "type": "token",
                        "text": "\n[model returned an empty response — the model may be overloaded or the context window may be full]\n",
                    })
                break

            # Execute tool calls and collect results
            result_blocks = await self._execute_tool_uses(tool_uses)

            # Append tool results as a user message
            self._messages.append(
                Message(role="user", content=result_blocks)
            )

        else:
            self._emit({
                "type": "system",
                "text": f"[reached maximum turn limit of {MAX_TURNS}]",
            })

    async def _stream_llm(self, prompt: str) -> str:
        """Stream tokens from the LLM and emit them; return full response."""
        full = ""
        # Buffer until we hit a <tool_use> open tag to avoid partial-tag display.
        # The tail kept in the buffer must be at least as long as the longest
        # stop sequence so that a partial stop token is never emitted mid-stream.
        # "<end_of_turn>" is 13 chars; use 16 to cover any variant.
        _TAIL = 16
        buffer = ""
        in_tool_block = False
        token_count = 0
        t_start = time.monotonic()

        async for token in self._backend.generate(prompt, self._params):
            if self._interrupted:
                break

            full += token
            buffer += token
            token_count += 1

            if not in_tool_block:
                if "<tool_use>" in buffer:
                    # Emit everything up to the tag, then suppress the rest
                    pre, _, rest = buffer.partition("<tool_use>")
                    if pre:
                        self._emit({"type": "token", "text": _strip_stop(pre, self._params.stop_sequences)})
                    buffer = "<tool_use>" + rest
                    in_tool_block = True
                elif len(buffer) > _TAIL * 2:
                    safe = buffer[:-_TAIL]
                    self._emit({"type": "token", "text": safe})
                    buffer = buffer[-_TAIL:]
            else:
                if "</tool_use>" in buffer:
                    in_tool_block = False
                    # Emit what comes after the closing tag
                    _, _, after = buffer.partition("</tool_use>")
                    buffer = after

        # Flush remaining buffer.
        # Strip any stop sequence that llama.cpp included in its final chunk
        # (some versions append the stop string to the last yielded token).
        # If we're still inside a tool block the model stopped mid-tag; emit
        # the raw fragment so the malformed-tool-call check can trigger a retry.
        if buffer:
            self._emit({"type": "token", "text": _strip_stop(buffer, self._params.stop_sequences)})

        # Also strip from the full accumulated text so _parse_tool_uses never
        # sees the stop token.
        full = _strip_stop(full, self._params.stop_sequences)

        elapsed = time.monotonic() - t_start
        tps = token_count / elapsed if elapsed > 0 else 0.0
        self._emit({
            "type": "generation_stats",
            "tokens": token_count,
            "elapsed_ms": round(elapsed * 1000),
            "tokens_per_sec": round(tps, 1),
        })

        return full

    async def _execute_tool_uses(
        self, tool_uses: list[ToolUseBlock]
    ) -> list[ToolResultBlock]:
        """Execute a list of tool calls, respecting permissions."""
        result_blocks: list[ToolResultBlock] = []

        for tu in tool_uses:
            if self._interrupted:
                result_blocks.append(ToolResultBlock(
                    tool_use_id=tu.id,
                    content="Interrupted by user.",
                    is_error=True,
                ))
                continue

            tool = self._registry.get(tu.name)
            if tool is None:
                self._emit({
                    "type": "tool_end",
                    "tool": tu.name,
                    "summary": f"Unknown tool: {tu.name}",
                    "is_error": True,
                })
                result_blocks.append(ToolResultBlock(
                    tool_use_id=tu.id,
                    content=f"Tool '{tu.name}' is not available.",
                    is_error=True,
                ))
                continue

            # Permission check
            if tool.requires_permission(tu.input, self._permission_mode):
                request_id = f"perm_{uuid.uuid4().hex[:8]}"
                approved = await self._permission_manager.request_permission(
                    request_id=request_id,
                    emit_fn=self._emit,
                    tool_name=tu.name,
                    tool_input=tu.input,
                )
                if not approved:
                    self._emit({
                        "type": "tool_end",
                        "tool": tu.name,
                        "summary": "Denied by user",
                        "is_error": True,
                    })
                    result_blocks.append(ToolResultBlock(
                        tool_use_id=tu.id,
                        content="Tool call denied by user.",
                        is_error=True,
                    ))
                    continue

            # Emit tool_start
            self._emit({
                "type": "tool_start",
                "id": tu.id,
                "tool": tu.name,
                "input": tu.input,
            })
            self._emit({"type": "status", "phase": "tool_running", "tool": tu.name})

            ctx = ToolContext(
                working_directory=self._working_directory,
                permission_mode=self._permission_mode,
                depth=self._depth,
                session_id=self._session_id,
                network_enabled=self._network_enabled,
            )

            try:
                result = await tool.call(tu.input, ctx)
            except Exception as exc:
                log.exception("Tool %s raised an exception", tu.name)
                result_content = f"Tool error: {exc}"
                is_error = True
                summary = f"Error in {tu.name}"
            else:
                result_content = truncate_tool_result(result.output)
                is_error = result.is_error
                summary = result.summary

            self._emit({
                "type": "tool_end",
                "id": tu.id,
                "tool": tu.name,
                "summary": summary,
                "is_error": is_error,
            })
            self._emit({"type": "status", "phase": "thinking"})

            result_blocks.append(ToolResultBlock(
                tool_use_id=tu.id,
                content=result_content,
                is_error=is_error,
            ))

        return result_blocks


# ── Helpers ────────────────────────────────────────────────────────────────────

# Regex to extract <tool_use> blocks from streamed LLM output.
# The closing </tool_use> is made optional: the model may stop generating
# exactly at the stop sequence boundary, leaving the tag absent.
_TOOL_USE_RE = re.compile(
    r"<tool_use>.*?<name>(.*?)</name>.*?<input>(.*?)</input>.*?(?:</tool_use>|$)",
    re.DOTALL | re.IGNORECASE,
)

# Fallback 1: <tool_use> with bare JSON (no <input> tags)
_TOOL_USE_BARE_JSON_RE = re.compile(
    r"<tool_use>.*?<name>(.*?)</name>\s*(\{.*?\})\s*(?:</tool_use>|$)",
    re.DOTALL | re.IGNORECASE,
)

# Fallback 2: Fenced JSON block that looks like a tool call
_FENCED_JSON_RE = re.compile(
    r"```json\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)

# Fallback 3: Bare JSON object on its own line containing "name" and "input"
_BARE_JSON_RE = re.compile(
    r"(?:^|\n)\s*(\{\s*\"name\":\s*\"[^\"]+\".*?\})\s*(?:\n|$)",
    re.DOTALL | re.IGNORECASE,
)


def _parse_tool_uses(text: str) -> list[ToolUseBlock]:
    """
    Extract all tool calls from LLM output, with fallbacks for fragile
    small-model output.

    Returns a list of parsed tool calls.  When a <name> tag is present but
    JSON parsing fails for every fallback, the function returns an empty list;
    the malformed-tool-call heuristic in _agent_loop (which checks for
    "<tool_use>" or "<name>" in the raw text) will then fire and ask the model
    to retry with correct formatting.
    """
    results: list[ToolUseBlock] = []
    seen_ids: set[str] = set()

    def add_result(name: str, input_data: dict):
        if not name:
            return
        call_id = f"{name}:{json.dumps(input_data, sort_keys=True)}"
        if call_id not in seen_ids:
            results.append(ToolUseBlock(name=name, input=input_data))
            seen_ids.add(call_id)

    # 1. Primary XML-ish format
    for m in _TOOL_USE_RE.finditer(text):
        name = m.group(1).strip()
        raw_input = m.group(2).strip()
        try:
            add_result(name, json.loads(raw_input))
        except json.JSONDecodeError:
            log.debug("Primary XML parse: JSON decode failed for tool %r: %s", name, raw_input[:120])

    # 2. Fallback: <tool_use> with bare JSON
    for m in _TOOL_USE_BARE_JSON_RE.finditer(text):
        name = m.group(1).strip()
        raw_input = m.group(2).strip()
        try:
            add_result(name, json.loads(raw_input))
        except json.JSONDecodeError:
            log.debug("Bare-JSON fallback: JSON decode failed for tool %r: %s", name, raw_input[:120])

    # 3. Fallback: Fenced JSON
    for m in _FENCED_JSON_RE.finditer(text):
        try:
            data = json.loads(m.group(1))
            if "name" in data and "input" in data:
                add_result(data["name"], data["input"])
        except json.JSONDecodeError:
            log.debug("Fenced-JSON fallback: JSON decode failed: %s", m.group(1)[:120])

    # 4. Fallback: Bare JSON line
    for m in _BARE_JSON_RE.finditer(text):
        try:
            data = json.loads(m.group(1))
            if "name" in data and "input" in data:
                add_result(data["name"], data["input"])
        except json.JSONDecodeError:
            log.debug("Bare-line fallback: JSON decode failed: %s", m.group(1)[:120])

    return results


def _text_before_first_tool(text: str) -> str:
    """Return the text portion before the first <tool_use> tag."""
    idx = text.find("<tool_use>")
    if idx == -1:
        return text
    return text[:idx]


def _strip_stop(text: str, stop_sequences: list[str]) -> str:
    """
    Remove any stop sequence that appears at the tail of *text*.

    llama-cpp-python (and some other backends) include the matched stop string
    in the last yielded token.  Stripping it here prevents chat-template tokens
    like <end_of_turn> or </start_of_turn> from leaking into the displayed
    output or being passed to _parse_tool_uses.
    """
    for seq in stop_sequences:
        if text.endswith(seq):
            return text[: -len(seq)]
        # Also strip if the stop token is followed only by whitespace/newlines
        stripped = text.rstrip()
        if stripped.endswith(seq):
            return stripped[: -len(seq)]
    return text
