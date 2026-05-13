"""Shared utility: `.env` loader.

This module used to host a full Anthropic-SDK CLI chatbot, but the project
moved to LangChain-based entrypoints (`ask.py`, `chat.py`) which only need
the dotenv loader. Everything else has been dropped; the file is kept under
this name only because `ask.py`, `chat.py`, and `eval/langsmith_eval.py`
already import from it.

If you ever want a direct-Anthropic-SDK CLI again, build it in a new file.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path = Path(".env")) -> None:
    """Populate `os.environ` from a KEY=VALUE `.env` file.

    Strips surrounding whitespace and matching quote pairs. Quietly skips
    blank lines, comments, and any line without `=`. Does nothing if the
    file is absent.

    Overwrite rule: an env var that's already set in the parent process
    wins — UNLESS it's set to an empty string. The empty-value carve-out
    exists because some parent environments (Claude Code, certain IDE
    test runners) pre-define `ANTHROPIC_API_KEY=""` and the dotenv value
    should still take effect.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if not os.environ.get(key):
            os.environ[key] = value
