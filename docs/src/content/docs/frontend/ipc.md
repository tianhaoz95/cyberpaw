---
title: IPC Bridge
description: How the frontend communicates with Tauri and the Python sidecar
---

## useAgent hook

`src/hooks/useAgent.ts` is the single source of truth for all agent communication. It:

1. Listens on the `agent://stream` Tauri event — each event payload is one NDJSON line from the sidecar stdout
2. Routes each message type to state updates or terminal writes
3. Exposes command dispatchers as stable `useCallback` refs

### Returned values

```typescript
// State
agentPhase: "idle" | "thinking" | "tool_running"
modelStatus: { backend, loaded, vramUsedMb, modelSizeMb, kvCacheMb }
loadProgress: { pct, backend } | null
generationStats: { totalTokens, tokensPerSec }
pendingPermission: { id, tool, input } | null
downloadProgress: DownloadProgress | null
downloadedModelPath: string | null
modelCatalog: ModelCatalogEntry[]

// Refs for terminal writes
writeToTerminal: React.RefObject<(text: string) => void>

// Commands
sendInput(text: string): Promise<void>
interrupt(): void
resetSession(): void
setWorkingDirectory(path: string, silent?: boolean): Promise<void>
loadModel(modelPath: string, backend?: string): Promise<void>
fetchCatalog(): Promise<void>
startDownload(modelId, destDir?, hfToken?): Promise<void>
cancelDownload(): Promise<void>
resolvePermission(id: string, approved: boolean): void
checkInstalledModels(dir: string): Promise<Set<string>>
```

### Model loading flow

`loadModel()` sets `modelLoadingRef.current = true` before invoking Tauri. The sidecar sends `model_progress` events (pct 0–100) which update `loadProgress`. When the sidecar sends `model_status` with `loaded: true`, `useAgent` checks `modelLoadingRef` — if true, it sets `loadProgress` to `pct: 100` and clears the ref. This prevents the periodic status poll (every 10s) from re-triggering the progress bar.

---

## useConfig hook

`src/hooks/useConfig.ts` — persists the `AppConfig` to two layers:

1. **`localStorage`** (synchronous) — ensures `config.model_path` is available on the very first render, before any async work
2. **Tauri `set_config` invoke** (async, fire-and-forget) — backup persistence via `tauri-plugin-store`

```typescript
interface AppConfig {
  working_directory: string;
  model_path: string;        // persisted for startup auto-load; not editable in UI
  context_size: number;      // 0 = auto-calculate from RAM
  max_new_tokens: number;
  auto_context: boolean;
  auto_max_tokens: boolean;
  permission_mode: "ask" | "auto_read" | "auto_all";
  network_enabled: boolean;
}
```

---

## Tauri commands

The Rust core exposes these commands to the frontend via `invoke()`:

| Command | Description |
|---------|-------------|
| `send_input` | Forward user text to sidecar stdin |
| `set_working_directory` | Send `cd` message to sidecar |
| `get_config` | Read persisted config |
| `set_config` | Write config to Tauri store |
| `load_model` | Send `load_model` message to sidecar |
| `get_model_status` | Send `status_request` to sidecar |
| `interrupt` | Send `interrupt` to sidecar |
| `get_download_catalog` | Send `download_catalog` request |
| `start_model_download` | Send `download_start` to sidecar |
| `cancel_model_download` | Send `download_cancel` to sidecar |

---

## Tauri capabilities

Permissions granted to the WebView (in `src-tauri/capabilities/default.json`):

| Permission | Used for |
|-----------|---------|
| `core:default` | Core Tauri APIs |
| `core:window:*` | Window controls (minimize, maximize, close) |
| `shell:allow-execute` | Running the sidecar |
| `shell:allow-open` | Opening URLs in the system browser |
| `dialog:default` | File/directory picker dialogs |
| `fs:default` | App-specific directory access |
| `fs:allow-read-dir` | `readDir` for installed model detection |
| `fs:scope-home-recursive` | Access to `~/CyberPaw/models/` |
| `store:default` | Config persistence via tauri-plugin-store |
