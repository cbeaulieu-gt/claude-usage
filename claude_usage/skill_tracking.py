"""Parse skill tracking JSONL log and extract skill references from prompts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from claude_usage.models import SkillInvokedEvent, SkillPassedEvent

TRACKING_FILE = "skill-tracking.jsonl"


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse an ISO 8601 timestamp string to a datetime."""
    ts_str = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(ts_str)


def parse_skill_tracking(
    data_dir: Path,
) -> tuple[list[SkillPassedEvent], list[SkillInvokedEvent]]:
    """Read skill-tracking.jsonl and return parsed events.

    Returns empty lists if the file doesn't exist.
    """
    tracking_file = data_dir / TRACKING_FILE
    if not tracking_file.exists():
        return [], []

    passed: list[SkillPassedEvent] = []
    invoked: list[SkillInvokedEvent] = []

    for line in tracking_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = entry.get("event")
        if event_type == "skill_passed":
            try:
                passed.append(SkillPassedEvent(
                    skill=entry["skill"],
                    target_agent=entry["target_agent"],
                    timestamp=_parse_timestamp(entry["timestamp"]),
                    session_id=entry["session_id"],
                ))
            except (KeyError, ValueError):
                continue
        elif event_type == "skill_invoked":
            try:
                invoked.append(SkillInvokedEvent(
                    skill=entry["skill"],
                    timestamp=_parse_timestamp(entry["timestamp"]),
                    session_id=entry["session_id"],
                ))
            except (KeyError, ValueError):
                continue

    return passed, invoked


def build_skill_allowlist(claude_dir: Path) -> set[str]:
    """Scan filesystem to build a set of installed skill names.

    Scans:
    - ~/.claude/skills/ (user skills — directory names)
    - ~/.claude/plugins/cache/*/superpowers/*/skills/ (plugin skills)
    - Plugin subdirectories for prefix:name format
    """
    skills: set[str] = set()
    skills_dir = claude_dir / "skills"
    if skills_dir.is_dir():
        for child in skills_dir.iterdir():
            if child.is_dir():
                skills.add(child.name)

    plugins_cache = claude_dir / "plugins" / "cache"
    if plugins_cache.is_dir():
        for marketplace in plugins_cache.iterdir():
            if not marketplace.is_dir():
                continue
            for plugin_dir in marketplace.iterdir():
                if not plugin_dir.is_dir():
                    continue
                for version_dir in plugin_dir.iterdir():
                    if not version_dir.is_dir():
                        continue
                    plugin_skills = version_dir / "skills"
                    if plugin_skills.is_dir():
                        prefix = plugin_dir.name
                        for skill_dir in plugin_skills.iterdir():
                            if skill_dir.is_dir():
                                skills.add(skill_dir.name)
                                skills.add(f"{prefix}:{skill_dir.name}")

    return skills


# Patterns for extracting skill references from Agent dispatch prompts
_BACKTICK_PATTERN = re.compile(r"`([a-zA-Z0-9_-]+(?::[a-zA-Z0-9_-]+)?)`")
_PHRASE_PATTERNS = [
    re.compile(r"[Uu]se (?:the )?[\"']?([a-zA-Z0-9_-]+(?::[a-zA-Z0-9_-]+)?)[\"']? skill", re.IGNORECASE),
    re.compile(r"[Ii]nvoke (?:the )?[\"']?([a-zA-Z0-9_-]+(?::[a-zA-Z0-9_-]+)?)[\"']? skill", re.IGNORECASE),
    re.compile(r"[Uu]se skill:?\s*[\"']?([a-zA-Z0-9_-]+(?::[a-zA-Z0-9_-]+)?)[\"']?", re.IGNORECASE),
]


def extract_skills_from_prompt(prompt: str, allowlist: set[str]) -> list[str]:
    """Extract skill names from an Agent dispatch prompt.

    Uses backtick-quoted names and phrase patterns, then validates
    against the allowlist to reduce false positives.
    """
    candidates: set[str] = set()

    for match in _BACKTICK_PATTERN.finditer(prompt):
        candidates.add(match.group(1))

    for pattern in _PHRASE_PATTERNS:
        for match in pattern.finditer(prompt):
            candidates.add(match.group(1))

    return sorted(c for c in candidates if c in allowlist)
