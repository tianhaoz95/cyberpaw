# CyberPaw — Feature Task List

---

## Task 1 — Input history navigation (↑ / ↓ arrow keys)

### Issue Description

`Terminal.tsx` handles keystrokes inside `term.onData()`. The handler currently recognises Enter, Ctrl-C, Backspace, and printable characters. Arrow keys arrive as ANSI escape sequences (`\x1b[A` = Up, `\x1b[B` = Down) and fall through to the `code >= 32` branch, which does nothing because `\x1b` has char code 27. The result is that pressing ↑ or ↓ has no effect — there is no way to recall previous inputs.

### Suggested Implementation

All changes are contained within `src/components/Terminal.tsx`.

**Step 1 — Add history refs** (alongside the existing `inputBufferRef`):

```ts
const historyRef    = useRef<string[]>([]);  // submitted entries, oldest first
const historyIdxRef = useRef<number>(-1);    // -1 = not navigating
const savedInputRef = useRef<string>("");    // snapshot of input before navigation started
```

**Step 2 — Push to history on Enter** (inside the `data === "\r"` branch, after `onInput(line)` is called):

```ts
if (line.trim()) {
  historyRef.current.push(line);
  historyIdxRef.current = -1;   // reset navigation cursor
  savedInputRef.current = "";
  onInput(line);
}
```

**Step 3 — Handle arrow key sequences** (add before the `code >= 32` branch):

Arrow keys arrive as the 3-byte sequence `\x1b[A` / `\x1b[B`. `onData` may deliver these in one call or across multiple calls. The safest approach is to match the full string:

```ts
} else if (data === "\x1b[A") {
  // ↑  — go back in history
  const hist = historyRef.current;
  if (hist.length === 0) return;

  if (historyIdxRef.current === -1) {
    // First press: save current draft
    savedInputRef.current = inputBufferRef.current;
    historyIdxRef.current = hist.length - 1;
  } else if (historyIdxRef.current > 0) {
    historyIdxRef.current -= 1;
  }
  _replaceInput(term, inputBufferRef, hist[historyIdxRef.current]);

} else if (data === "\x1b[B") {
  // ↓  — go forward in history
  const hist = historyRef.current;
  if (historyIdxRef.current === -1) return;

  if (historyIdxRef.current < hist.length - 1) {
    historyIdxRef.current += 1;
    _replaceInput(term, inputBufferRef, hist[historyIdxRef.current]);
  } else {
    // Past the end: restore the draft
    historyIdxRef.current = -1;
    _replaceInput(term, inputBufferRef, savedInputRef.current);
  }
}
```

**Step 4 — Add the `_replaceInput` helper** (module-level function):

```ts
function _replaceInput(
  term: XTerm,
  bufRef: React.MutableRefObject<string>,
  newText: string,
) {
  // Erase current input with backspace-space-backspace for each character,
  // then write the replacement.
  const erase = "\b \b".repeat(bufRef.current.length);
  term.write(erase + newText);
  bufRef.current = newText;
}
```

**Step 5 — Persist history across sessions (optional enhancement)**

Store `historyRef.current` in `sessionStorage` on each push and reload on mount so history survives page refreshes but not full app restarts. Cap at 200 entries.

```ts
// On mount, reload history:
historyRef.current = JSON.parse(sessionStorage.getItem("cyberpaw_history") ?? "[]");

// On each push:
historyRef.current.push(line);
if (historyRef.current.length > 200) historyRef.current.shift();
sessionStorage.setItem("cyberpaw_history", JSON.stringify(historyRef.current));
```

### Verification

1. Run `npm run tauri dev`.
2. Type `hello world` and press Enter. Type `second command` and press Enter.
3. Press ↑ once → terminal input should display `second command`.
4. Press ↑ again → terminal input should display `hello world`.
5. Press ↓ once → terminal input should display `second command`.
6. Press ↓ again → input should be blank (restored draft).
7. Type partial text, press ↑ → history entry appears. Press ↓ → partial text is restored.
8. Press ↑ when history is empty → nothing happens, no crash.

---

## Task 2 — Persist and auto-restore workspace directory; show it in the app bar

### Issue Description

**Problem A — not persisted on change:** When the user clicks "Open" and picks a folder, `setWorkingDirectory` in `useAgent.ts` sends `set_working_directory` to the sidecar but never calls `updateConfig({ working_directory: path })`. The chosen folder is therefore lost on restart.

**Problem B — not applied on startup:** `App.tsx` auto-loads `config.model_path` on mount but never sends the stored `config.working_directory` to the sidecar. The sidecar always starts in its own working directory (the binary's location), ignoring the last-used workspace.

**Problem C — no visible indicator:** The current workspace is only visible inside the Settings panel. There is no indication in the main UI, so the user has no way to confirm which folder is active without opening Settings.

### Suggested Implementation

**Fix A — persist on folder pick** (`src/App.tsx`, `onOpenFolder` handler):

```ts
onOpenFolder={async () => {
  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({ directory: true, multiple: false });
  if (typeof selected === "string") {
    setWorkingDirectory(selected);
    updateConfig({ working_directory: selected });  // ← add this line
  }
}}
```

**Fix B — send saved directory to sidecar on startup** (`src/App.tsx`, inside the existing `setTimeout` auto-load block):

```ts
setTimeout(() => {
  // Restore last-used workspace before loading the model
  if (config.working_directory && config.working_directory !== "~") {
    invoke("set_working_directory", { path: config.working_directory }).catch(() => {});
  }

  if (config.model_path) {
    // ... existing spinner + loadModel logic ...
  }
}, 50);
```

**Fix C — workspace badge in `MenuBar`**

Add a `workingDirectory` prop to `MenuBar`:

```ts
// MenuBar.tsx — Props interface
interface Props {
  agentPhase: AgentPhase;
  modelStatus: ModelStatus;
  workingDirectory: string;   // ← new
  onOpenFolder: () => void;
  onNewSession: () => void;
  onOpenSettings: () => void;
}
```

Insert a small folder-path badge between the "Open" button and the spacer:

```tsx
{/* Current workspace indicator */}
{workingDirectory && workingDirectory !== "~" && (
  <span
    title={workingDirectory}
    style={{
      fontSize: 11,
      color: "#888888",
      fontFamily: "monospace",
      maxWidth: 200,
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap",
      cursor: "default",
    }}
  >
    {shortenPath(workingDirectory)}
  </span>
)}
```

Add a `shortenPath` helper (module-level in `MenuBar.tsx`) that shows only the last two path segments:

```ts
function shortenPath(p: string): string {
  const parts = p.replace(/\\/g, "/").split("/").filter(Boolean);
  return parts.length > 2 ? "…/" + parts.slice(-2).join("/") : p;
}
```

Pass the prop from `App.tsx`:

```tsx
<MenuBar
  workingDirectory={config.working_directory}
  ...
/>
```

### Verification

1. Launch the app fresh (clear localStorage to simulate first run).
2. Click "Open" and pick a directory. The app bar should immediately show the shortened path.
3. Quit and relaunch the app. The app bar should still show the same path from the previous session — no need to pick it again.
4. Open a terminal shell, `cd /tmp` via a `! cd /tmp` command — verify the sidecar's working directory matches (check via `! pwd`).
5. In the sidecar's startup log, verify `set_working_directory` is called before any model load.

---

## Task 3 — Memory usage indicator in the app bar (total / model weights / KV cache)

### Issue Description

`ModelStatus` has a `vramUsedMb` field, and the `model_status` event carries `vram_used_mb`. However:

1. `LlamaCppBackend.vram_used_mb()` in `agent/backends/llamacpp_backend.py` is not implemented — it returns `0` unconditionally.
2. The `model_status` event carries only a single `vram_used_mb` number with no breakdown.
3. `MenuBar.tsx` shows the backend name badge but no memory figures.
4. Memory is only queried on an explicit `status_request` message (sent by the frontend's `get_model_status` command, which itself is never called from the UI). There is no automatic polling.

`llama-cpp-python` exposes the underlying C API functions needed:
- `lib.llama_model_size(model)` → bytes of model weights in RAM/VRAM.
- `lib.llama_state_get_size(ctx)` → bytes of the KV cache state.

### Suggested Implementation

**Step 1 — Implement memory reporting in the backend** (`agent/backends/llamacpp_backend.py`):

Add a `memory_breakdown_mb()` method:

```python
def memory_breakdown_mb(self) -> dict:
    """Return a dict with model_mb, kv_mb, total_mb (all in MiB)."""
    if self._llm is None:
        return {"model_mb": 0, "kv_mb": 0, "total_mb": 0}
    try:
        import llama_cpp.llama_cpp as lib
        model_bytes = lib.llama_model_size(self._llm.model)
        kv_bytes    = lib.llama_state_get_size(self._llm.ctx)
        model_mb    = model_bytes // (1024 * 1024)
        kv_mb       = kv_bytes   // (1024 * 1024)
        return {"model_mb": model_mb, "kv_mb": kv_mb, "total_mb": model_mb + kv_mb}
    except Exception:
        return {"model_mb": 0, "kv_mb": 0, "total_mb": 0}
```

Also override `vram_used_mb()` to use this:

```python
def vram_used_mb(self) -> int:
    return self.memory_breakdown_mb()["total_mb"]
```

**Step 2 — Add breakdown to the `model_status` event** (`agent/main.py`):

Wherever `model_status` is emitted with `vram_used_mb`, enrich it with the breakdown:

```python
# In the status_request handler and the load-complete emit:
breakdown = backend.memory_breakdown_mb() if hasattr(backend, "memory_breakdown_mb") else {}
emit({
    "type": "model_status",
    "backend": backend.name,
    "loaded": backend.is_loaded(),
    "vram_used_mb":  breakdown.get("total_mb", 0),
    "model_size_mb": breakdown.get("model_mb", 0),
    "kv_cache_mb":   breakdown.get("kv_mb",   0),
})
```

Update `agent/main.py` line 30 comment to document the new fields.

**Step 3 — Update the `ModelStatus` interface** (`src/hooks/useAgent.ts`):

```ts
export interface ModelStatus {
  backend: string;
  loaded: boolean;
  vramUsedMb: number;
  modelSizeMb: number;   // ← new
  kvCacheMb: number;     // ← new
}
```

Initialize the new fields to `0` in the `useState` call. Map them from the event payload in the `model_status` handler:

```ts
} else if (type === "model_status") {
  setModelStatus({
    backend:      (msg.backend as string)        ?? "unknown",
    loaded:       (msg.loaded as boolean)        ?? false,
    vramUsedMb:   (msg.vram_used_mb as number)   ?? 0,
    modelSizeMb:  (msg.model_size_mb as number)  ?? 0,
    kvCacheMb:    (msg.kv_cache_mb as number)    ?? 0,
  });
}
```

**Step 4 — Poll for memory updates from the frontend** (`src/hooks/useAgent.ts`):

After the model loads (when `modelStatus.loaded` becomes true), start a polling interval that sends `status_request` every 10 seconds. Cancel it when the model unloads or the component unmounts:

```ts
useEffect(() => {
  if (!modelStatus.loaded) return;
  const id = setInterval(() => {
    invoke("get_model_status").catch(() => {});
  }, 10_000);
  return () => clearInterval(id);
}, [modelStatus.loaded]);
```

Note: `get_model_status` already sends `{"type": "status_request"}` to the sidecar via `write_to_sidecar`.

**Step 5 — Add memory badge to `MenuBar`** (`src/components/MenuBar.tsx`):

Add `modelStatus.modelSizeMb` and `modelStatus.kvCacheMb` to the display. Replace or extend the existing model badge:

```tsx
{/* Memory indicator — only shown when model is loaded and sizes are known */}
{modelStatus.loaded && modelStatus.vramUsedMb > 0 && (
  <span
    title={`Model weights: ${modelStatus.modelSizeMb} MiB\nKV cache: ${modelStatus.kvCacheMb} MiB\nTotal: ${modelStatus.vramUsedMb} MiB`}
    style={{
      fontSize: 11,
      background: "#0a000a",
      color: "#cc88ff",
      border: "1px solid #cc88ff44",
      borderRadius: 10,
      padding: "1px 8px",
      fontFamily: "monospace",
      cursor: "default",
    }}
  >
    {formatMb(modelStatus.vramUsedMb)} RAM
  </span>
)}
```

Add a `formatMb` helper in `MenuBar.tsx`:

```ts
function formatMb(mb: number): string {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`;
}
```

The tooltip (`:title`) provides the full breakdown on hover without cluttering the bar. If a more persistent breakdown is needed, a small popover on click can be added as a follow-up.

### Verification

1. Run `npm run tauri dev` and load a model.
2. Once the model is ready, the app bar should show a memory badge such as `3.5 GB RAM`.
3. Hover the badge — tooltip should show three lines:
   ```
   Model weights: 3584 MiB
   KV cache: 512 MiB
   Total: 4096 MiB
   ```
4. After 10 seconds with the model idle, the values should refresh automatically (confirm in sidecar logs that `status_request` is received periodically).
5. Send a long prompt to fill the KV cache; after the response completes, wait for the next poll — the KV cache figure should increase.
6. When no model is loaded, the memory badge should not appear.
7. Run `python3 -c "import llama_cpp.llama_cpp as lib; print(lib.llama_model_size)"` in the venv to confirm the API is available before implementation.
