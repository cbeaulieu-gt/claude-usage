#!/usr/bin/env python3
"""Sanitize a Claude Code transcript for use as a committed test fixture.

Reads a JSONL transcript from the path given as the first positional
argument, sanitizes each entry (strips requestId, clears thinking-block
content), and writes the result to stdout as JSONL.

Usage:
    python tests/fixtures/sanitize_transcript.py ~/.claude/projects/<hash>/<session>.jsonl \
        > tests/fixtures/session_summaries/my_fixture.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


_OMIT_TOP_LEVEL_KEYS: frozenset[str] = frozenset({"requestId"})


def _sanitize_content_block(block: dict) -> dict:
    """Strip sensitive data from a single content block.

    Args:
        block: A content block dict (may have type, text, thinking, etc.).

    Returns:
        A new dict with thinking-block text replaced by a sentinel.
    """
    if block.get("type") == "thinking":
        return {**block, "thinking": "<redacted>"}
    return block


def _sanitize_entry(entry: dict) -> dict:
    """Sanitize one JSONL entry.

    Args:
        entry: A parsed JSONL entry dict.

    Returns:
        A new dict with identifying fields removed and content sanitized.
    """
    result = {
        k: v for k, v in entry.items()
        if k not in _OMIT_TOP_LEVEL_KEYS
    }
    msg = result.get("message")
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, list):
            sanitized_content = [
                _sanitize_content_block(b) if isinstance(b, dict) else b
                for b in content
            ]
            result["message"] = {**msg, "content": sanitized_content}
    return result


def main() -> None:
    """Read transcript path from argv, sanitize, write to stdout."""
    if len(sys.argv) != 2:
        print(
            f"Usage: {sys.argv[0]} <transcript.jsonl>",
            file=sys.stderr,
        )
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"Error: not a file: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            sanitized = _sanitize_entry(entry)
            print(json.dumps(sanitized, ensure_ascii=False))


if __name__ == "__main__":
    main()
