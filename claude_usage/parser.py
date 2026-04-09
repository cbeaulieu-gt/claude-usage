"""Parse Claude Code session JSONL files and subagent metadata."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from claude_usage.models import MessageRecord, SessionRecord


def decode_project_hash(hash_name: str) -> str:
    """Decode a project hash directory name to a human-readable project name.

    Claude Code encodes project paths: '--' represents a path separator,
    '-' represents a hyphen or space within segment names. We split on '--'
    and take the last segment as the project name.

    Examples:
        'C--Users-chris--claude' -> 'claude'
        'i--games-raid-rsl-rule-generator' -> 'games-raid-rsl-rule-generator'
    """
    if not hash_name:
        return ""
    segments = hash_name.split("--")
    return segments[-1]
