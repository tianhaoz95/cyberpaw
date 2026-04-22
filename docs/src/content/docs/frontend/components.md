---
title: Frontend Components
description: React components that make up the CyberPaw UI
---

The frontend lives in `cyberpaw/src/` and is a React 18 + TypeScript app bundled by Vite and hosted in a Tauri WebView.

## Component tree

```
App.tsx
├── MenuBar.tsx          — fixed 40px top bar
├── Terminal.tsx         — main xterm.js terminal
├── Settings.tsx         — slide-in right panel
│   └── ModelDownloader.tsx  — model catalog + download UI
├── PermissionDialog.tsx — tool approval modal
└── ModelLoadProgress.tsx — fixed bottom loading bar
```

---

## App.tsx

The root component. Responsibilities:

- Reads persisted config from `useConfig()` and auto-loads the model on mount
- Orchestrates the startup sequence: print working directory → start spinner → load model → print "Model ready."
- Passes all agent commands and state down to child components
- Owns the `spinnerTimerRef` that animates the loading spinner in the terminal

---

## MenuBar.tsx

Fixed 40px bar at the top of the window. Displays:

- **Folder** button — opens a directory picker, calls `setWorkingDirectory`
- **Session** button — resets the conversation
- **Working directory** badge — shortened current path
- **Agent phase** indicator — `idle` / `thinking` / `tool_running`
- **Model badge** — backend name + loaded state
- **Memory badges** — model weights MB, KV cache MB, total MB (from periodic status poll)
- **Token rate** — tokens/sec from the last generation
- **Settings** button
- **Window controls** — minimize, maximize, close (custom, because Tauri hides the native title bar)

---

## Terminal.tsx

The main user interface — an `xterm.js` terminal instance.

Key behaviours:
- Accumulates typed characters in `inputBufferRef`; submits on **Enter**
- **Ctrl-C** calls `onInterrupt()`
- **↑ / ↓** navigates `historyRef` (previous inputs)
- Prefix `!` bypasses the LLM and runs a shell command directly
- `writeToTerminalRef` is a stable ref exposed to `App.tsx` for writing output without re-renders

---

## Settings.tsx

A slide-in panel (380px, right edge). Fields:

| Field | Description |
|-------|-------------|
| Active Model | Shows filename of loaded model + **Clear** button |
| Models | `ModelDownloader` component — always visible |
| Working Directory | Text input + **Browse** button |
| Permission Mode | Radio group: Ask / Auto-read / Auto-all |
| Context Window | Toggle auto/manual + range slider |
| Max New Tokens | Toggle auto/manual + range slider |
| Network Access | Checkbox |

Clicking **Save** calls `onSave(draft)` which persists to `localStorage` and Tauri store.

---

## ModelDownloader.tsx

Embedded inside Settings. Shows the model catalog and handles download + load.

- Scans `~/CyberPaw/models/` (or custom `destDir`) on mount and after each download using `@tauri-apps/plugin-fs` `readDir`
- Models found on disk show a green **✓ Installed** badge and a **Load** button
- Clicking **Load** calls `onUseModel(path)` immediately — no download needed
- The **Download** button is disabled for already-installed models
- Destination directory input re-scans with 300ms debounce on change

---

## PermissionDialog.tsx

Fixed modal (bottom of screen, above the load progress bar). Shown when the agent requests approval for a tool call in `ask` mode.

Displays the tool name and truncated input JSON. **Allow** / **Deny** buttons. Auto-denies after 5 minutes if no response.

---

## ModelLoadProgress.tsx

Fixed bottom bar shown during model loading. Displays:
- Backend name and percentage
- Animated gradient progress bar
- Auto-hides 1.5 seconds after reaching 100%

Visibility is driven by `loadProgress` from `useAgent`. Only appears when a load is actually in flight (gated by `modelLoadingRef` to prevent the periodic status poll from re-triggering it).
