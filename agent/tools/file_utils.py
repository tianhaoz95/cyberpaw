"""
Agent Layer — File Utilities
=============================
Common helpers for file-handling tools.
"""

from __future__ import annotations

import difflib
import glob as _glob
import os


def suggest_paths(
    missing: str, working_directory: str, n: int = 3, folders_only: bool = False
) -> list[str]:
    """Find similar-named files or directories in the working directory to suggest corrections."""
    # Start searching in the directory of the missing path if it exists, otherwise root
    parent = os.path.dirname(os.path.join(working_directory, missing))
    if not os.path.isdir(parent):
        parent = working_directory

    try:
        # Recursively list all items in parent
        candidates = _glob.glob(os.path.join(parent, "**", "*"), recursive=True)
        # Filter by type and relative to working_directory
        rel_paths = []
        for c in candidates:
            if folders_only:
                if os.path.isdir(c):
                    rel_paths.append(os.path.relpath(c, working_directory))
            else:
                if os.path.isfile(c):
                    rel_paths.append(os.path.relpath(c, working_directory))

        return difflib.get_close_matches(missing, rel_paths, n=n, cutoff=0.5)
    except Exception:
        return []


def format_suggestions(suggestions: list[str]) -> str:
    if not suggestions:
        return ""
    return "\nDid you mean one of:\n  " + "\n  ".join(suggestions)
