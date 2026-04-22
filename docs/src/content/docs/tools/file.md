---
title: File Tools
description: Read, Write, Edit, Glob, Grep, and directory tools
---

## Read

Reads a file and returns its contents with line numbers.

```json
{"tool": "Read", "input": {"file_path": "src/main.py"}}
{"tool": "Read", "input": {"file_path": "src/main.py", "offset": 100, "limit": 50}}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_path` | string | Absolute or relative path |
| `offset` | int? | Line to start reading from (1-based) |
| `limit` | int? | Max lines to return |

Output is formatted as `cat -n` style with line numbers.

---

## Write

Creates or overwrites a file. Requires a prior `Read` if the file already exists.

```json
{"tool": "Write", "input": {"file_path": "output.txt", "content": "Hello, world!"}}
```

---

## Edit

Replaces an exact string in a file. The `old_string` must come verbatim from a prior `Read` result — never constructed from memory.

```json
{
  "tool": "Edit",
  "input": {
    "file_path": "src/app.py",
    "old_string": "def foo():\n    pass",
    "new_string": "def foo():\n    return 42"
  }
}
```

Edit uses `diff-match-patch` for fuzzy matching when exact string match fails. It also checks file `mtime` to detect if the file was modified externally since the last `Read` (staleness guard).

---

## MultiEdit

Applies multiple edits to a single file in one call. Edits are applied sequentially.

```json
{
  "tool": "MultiEdit",
  "input": {
    "file_path": "src/app.py",
    "edits": [
      {"old_string": "foo", "new_string": "bar"},
      {"old_string": "baz", "new_string": "qux"}
    ]
  }
}
```

---

## Glob

Finds files matching a glob pattern, sorted by modification time.

```json
{"tool": "Glob", "input": {"pattern": "src/**/*.tsx"}}
{"tool": "Glob", "input": {"pattern": "**/*.py", "path": "agent/"}}
```

---

## Grep

Searches file contents with a regex pattern using ripgrep.

```json
{"tool": "Grep", "input": {"pattern": "def handle_input", "path": "agent/"}}
{"tool": "Grep", "input": {"pattern": "TODO", "glob": "*.py", "output_mode": "files_with_matches"}}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `pattern` | string | Regex pattern |
| `path` | string? | Directory to search |
| `glob` | string? | File filter (e.g. `*.ts`) |
| `output_mode` | string? | `content` / `files_with_matches` / `count` |
| `-i` | bool? | Case-insensitive |

---

## ListDir

Lists files and directories at a path.

```json
{"tool": "ListDir", "input": {"path": "src/components"}}
```

---

## Move

Moves or renames a file or directory.

```json
{"tool": "Move", "input": {"source": "old_name.py", "destination": "new_name.py"}}
```

---

## DeleteFile

Deletes a file. Irreversible — use with care.

```json
{"tool": "DeleteFile", "input": {"file_path": "temp/scratch.txt"}}
```
