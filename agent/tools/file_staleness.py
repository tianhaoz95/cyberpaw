"""
Agent Layer — File Staleness Guards
====================================
Stores the modification time of files when they are read by the model.
If the model tries to edit a file that has been modified since it was
last read, the edit is rejected.
"""

from __future__ import annotations

import os

# (session_id, abs_path) -> mtime_at_read
_read_timestamps: dict[tuple[str, str], float] = {}


def record_read(session_id: str, abs_path: str) -> None:
    """Record current mtime for *abs_path* in *session_id*."""
    try:
        _read_timestamps[(session_id, abs_path)] = os.path.getmtime(abs_path)
    except OSError:
        pass


def is_stale(session_id: str, abs_path: str) -> bool:
    """Return True if *abs_path* has been modified since it was last recorded."""
    recorded = _read_timestamps.get((session_id, abs_path))
    if recorded is None:
        return False
    try:
        current = os.path.getmtime(abs_path)
        # 10ms tolerance for filesystem timestamp jitter
        return current > recorded + 0.01
    except OSError:
        return False


def clear_staleness(session_id: str, abs_path: str) -> None:
    """Clear staleness record after a successful write/edit."""
    _read_timestamps.pop((session_id, abs_path), None)
