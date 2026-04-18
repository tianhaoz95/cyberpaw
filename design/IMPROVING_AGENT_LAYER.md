# Research & Design: Improving the Agent Layer

This document outlines the findings from a comparative study between the current CyberPaw agent implementation and `claude-code`, and proposes a roadmap for enhancing CyberPaw's performance, quality, and reliability.

## 1. Comparative Analysis

### 1.1 Core Orchestration
| Feature | CyberPaw (Current) | Claude Code |
| :--- | :--- | :--- |
| **Agent Loop** | Sequential, single-turn focus. | Multi-turn, budget-aware, interruptible. |
| **Tool Calling** | XML-based, parsed via regex. | Highly structured, supports partial streaming. |
| **Sub-agents** | Basic nesting via `AgentTool`. | Deeply integrated, specialized roles (team, workers). |
| **Permissions** | Global mode (Ask/Auto). | Granular, rule-based (pattern matching), stateful. |

### 1.2 Context & Memory Management
| Feature | CyberPaw (Current) | Claude Code |
| :--- | :--- | :--- |
| **Token Counting** | Heuristic (chars / 4). | Exact counting via model-specific tokenizers. |
| **Compaction** | Simple truncation of old results. | Micro-compaction, "snipping," summarization. |
| **Large Outputs** | Truncated in memory. | Persisted to disk; model receives a "pointer" + preview. |
| **Project Context** | None (only CWD in prompt). | Dynamic injection of `CLAUDE.md`, file structure, etc. |

### 1.3 Tool Sophistication
| Feature | CyberPaw (Current) | Claude Code |
| :--- | :--- | :--- |
| **File Editing** | Exact string match only. | Quote normalization, staleness checks, diff generation. |
| **Fuzzy Matching** | None. | Suggests similar paths on `ENOENT`. |
| **Safety** | None. | Secret detection (PII/Keys), destructive action guards. |
| **UI Integration** | Generic terminal output. | Rich React-based UI for diffs, progress, and results. |

---

## 2. Proposed Improvements

### 2.1 High-Performance Context Management
The current heuristic-based approach leads to either wasted context or premature truncation.
- **Exact Tokenization:** Integrate `sentencepiece` or a similar lightweight tokenizer for Gemma to manage the 8,192 token window precisely.
- **Tiered Compaction:** Instead of simple truncation, implement a "forgetting" schedule:
  - **Tier 0 (Recent):** Last 3-5 turns are kept in full.
  - **Tier 1 (Intermediate):** Tool results are summarized by an LLM call or aggressive truncation.
  - **Tier 2 (Old):** Entire turns are summarized into a "Conversation History Summary" block.
- **Persistence to Disk:** For tool outputs exceeding ~4KB, save the full content to a `.cyberpaw/session/` directory and only pass the first/last 500 characters to the LLM.

### 2.2 Intelligent & Safe Tooling
Move from "dumb" file operations to "context-aware" edits.
- **FileEdit Enhancements:**
  - **Staleness Guard:** Compare file `mtime` with the timestamp of the last `Read`. If modified, force a re-read before allowing an edit.
  - **Normalization:** Automatically handle CRLF/LF and quote styles (smart quotes vs. straight quotes).
  - **Replace All:** Add a flag to replace all occurrences if the model explicitly requests it.
- **Fuzzy Discovery:** If a tool call fails with "File not found," perform a quick glob/search for similar filenames and suggest them in the error message.
- **Secret Scanning:** Implement a basic regex-based scanner to warn the user if an edit or bash command might leak credentials.

### 2.3 Prompt Engineering & Architecture
- **Dynamic System Prompt:** Inject a "Project Map" (directory tree summary) and "Recent Activity" into the system prompt.
- **Thinking Block:** Encourage the model to use `<thought>` blocks (supported by Gemma) to plan before emitting `<tool_use>`.
- **Validation Phase:** Add a `validate_input` method to all tools to catch semantic errors (e.g., editing a binary file) before the agent "commits" to a tool call.

### 2.4 Local Inference Optimization
- **Prompt Caching:** Explicitly manage the KV cache state in `llama.cpp`. Ensure the system prompt and stable history prefix are cached to achieve near-instantaneous TTFT (Time To First Token) in multi-turn sessions.
- **Speculative Execution (Optional):** Explore using a smaller model (Gemma 2B) to speculate tool calls while the larger model (Gemma 9B) validates.

---

## 3. Implementation Roadmap

### Phase 1: Foundations (Short term)
- [ ] Implement exact token counting for Gemma.
- [ ] Add staleness checks and `replace_all` to `EditTool`.
- [ ] Implement basic tiered compaction.

### Phase 2: Intelligence & Safety (Medium term)
- [ ] Add fuzzy path suggestions on tool failure.
- [ ] Implement secret scanning for `Write`/`Edit` tools.
- [ ] Add `<thought>` block support to the orchestrator.

### Phase 3: Performance & Scalability (Long term)
- [ ] Optimize KV cache management in `llamacpp_backend.py`.
- [ ] Implement "Persist to Disk" for large tool results.
- [ ] Dynamic system prompt generation with project context.
