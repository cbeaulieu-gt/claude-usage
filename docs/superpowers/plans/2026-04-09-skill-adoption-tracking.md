# Skill Adoption Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track when the router passes skills to subagents and whether those subagents actually invoke them, then surface adoption metrics in the claude-usage dashboard.

**Architecture:** A PreToolUse hook script logs `skill_passed` and `skill_invoked` events to `~/.claude/skill-tracking.jsonl`. The claude-usage tool reads this log, correlates pass/invoke events per skill, and renders adoption rates in a new dashboard section. Two repos: `claude_personal_configs` (hook + config) and `claude-usage` (parser, aggregator, dashboard).

**Tech Stack:** Python 3.10+, pytest, Chart.js 4, Jinja2

**Repos:**
- `C:\Users\chris\.claude` — hook script at `hooks/skill-tracker.py`, config in `settings.json`
- `C:\Users\chris\.claude\claude-usage` — parser, aggregator, models, renderer, dashboard

**Design spec:** `docs/superpowers/specs/2026-04-09-skill-adoption-tracking-design.md`

---

## File Structure

### claude_personal_configs repo (`C:\Users\chris\.claude`)

| File | Action | Responsibility |
|---|---|---|
| `hooks/skill-tracker.py` | Create | PreToolUse hook: parse stdin JSON, extract skill events, write JSONL |
| `settings.json` | Modify | Add two PreToolUse hook entries (Skill matcher, Agent matcher) |

### claude-usage repo (`C:\Users\chris\.claude\claude-usage`)

| File | Action | Responsibility |
|---|---|---|
| `claude_usage/models.py` | Modify | Add `SkillPassedEvent` and `SkillInvokedEvent` dataclasses |
| `claude_usage/skill_tracking.py` | Create | Parse `skill-tracking.jsonl`, build allowlist, extract skill refs from prompts |
| `claude_usage/aggregator.py` | Modify | Add `by_skill_adoption` field, correlation logic |
| `claude_usage/renderer.py` | Modify | Pass `by_skill_adoption` to template |
| `templates/dashboard.html` | Modify | Add "Skill Adoption" chart section |
| `claude_usage/__main__.py` | Modify | Wire skill tracking parser into orchestration |
| `tests/test_skill_tracking.py` | Create | Tests for JSONL parsing, prompt extraction, allowlist |
| `tests/test_aggregator_adoption.py` | Create | Tests for pass/invoke correlation |

---

### Task 1: Event Dataclasses

**Repo:** `claude-usage` (`C:\Users\chris\.claude\claude-usage`)

**Files:**
- Modify: `claude_usage/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for new dataclasses**

Add to the bottom of `tests/test_models.py`:

```python
from claude_usage.models import SkillPassedEvent, SkillInvokedEvent


class TestSkillPassedEvent:
    def test_creation(self):
        from datetime import datetime, timezone
        evt = SkillPassedEvent(
            skill="python",
            target_agent="code-writer",
            timestamp=datetime(2026, 4, 9, tzinfo=timezone.utc),
            session_id="abc-123",
        )
        assert evt.skill == "python"
        assert evt.target_agent == "code-writer"
        assert evt.session_id == "abc-123"

    def test_frozen(self):
        from datetime import datetime, timezone
        evt = SkillPassedEvent(
            skill="python",
            target_agent="code-writer",
            timestamp=datetime(2026, 4, 9, tzinfo=timezone.utc),
            session_id="abc-123",
        )
        import pytest
        with pytest.raises(AttributeError):
            evt.skill = "other"


class TestSkillInvokedEvent:
    def test_creation(self):
        from datetime import datetime, timezone
        evt = SkillInvokedEvent(
            skill="python",
            timestamp=datetime(2026, 4, 9, tzinfo=timezone.utc),
            session_id="abc-123",
        )
        assert evt.skill == "python"
        assert evt.session_id == "abc-123"

    def test_frozen(self):
        from datetime import datetime, timezone
        evt = SkillInvokedEvent(
            skill="python",
            timestamp=datetime(2026, 4, 9, tzinfo=timezone.utc),
            session_id="abc-123",
        )
        import pytest
        with pytest.raises(AttributeError):
            evt.skill = "other"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py::TestSkillPassedEvent -v && pytest tests/test_models.py::TestSkillInvokedEvent -v`
Expected: FAIL with `ImportError: cannot import name 'SkillPassedEvent'`

- [ ] **Step 3: Implement the dataclasses**

Add to the bottom of `claude_usage/models.py` (after the `SessionRecord` class):

```python
@dataclass(frozen=True, slots=True)
class SkillPassedEvent:
    """A skill reference found in an Agent dispatch prompt."""

    skill: str
    target_agent: str
    timestamp: datetime
    session_id: str


@dataclass(frozen=True, slots=True)
class SkillInvokedEvent:
    """An actual Skill tool invocation."""

    skill: str
    timestamp: datetime
    session_id: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: All tests PASS (existing 11 + new 4 = 15)

- [ ] **Step 5: Commit**

```bash
git add claude_usage/models.py tests/test_models.py
git commit -m "feat: add SkillPassedEvent and SkillInvokedEvent dataclasses"
```

---

### Task 2: Skill Tracking Parser

**Repo:** `claude-usage` (`C:\Users\chris\.claude\claude-usage`)

**Files:**
- Create: `claude_usage/skill_tracking.py`
- Create: `tests/test_skill_tracking.py`

- [ ] **Step 1: Write failing tests for JSONL parsing**

Create `tests/test_skill_tracking.py`:

```python
"""Tests for skill tracking JSONL parser and prompt skill extraction."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from claude_usage.models import SkillInvokedEvent, SkillPassedEvent
from claude_usage.skill_tracking import parse_skill_tracking


class TestParseSkillTracking:
    def test_empty_when_no_file(self, tmp_path: Path):
        passed, invoked = parse_skill_tracking(tmp_path)
        assert passed == []
        assert invoked == []

    def test_parses_skill_invoked_event(self, tmp_path: Path):
        log = tmp_path / "skill-tracking.jsonl"
        log.write_text(json.dumps({
            "event": "skill_invoked",
            "skill": "python",
            "timestamp": "2026-04-09T21:00:00Z",
            "session_id": "sess-001",
        }) + "\n")
        passed, invoked = parse_skill_tracking(tmp_path)
        assert len(passed) == 0
        assert len(invoked) == 1
        assert invoked[0].skill == "python"
        assert invoked[0].session_id == "sess-001"

    def test_parses_skill_passed_event(self, tmp_path: Path):
        log = tmp_path / "skill-tracking.jsonl"
        log.write_text(json.dumps({
            "event": "skill_passed",
            "skill": "superpowers:test-driven-development",
            "target_agent": "code-writer",
            "timestamp": "2026-04-09T21:00:00Z",
            "session_id": "sess-001",
        }) + "\n")
        passed, invoked = parse_skill_tracking(tmp_path)
        assert len(passed) == 1
        assert passed[0].skill == "superpowers:test-driven-development"
        assert passed[0].target_agent == "code-writer"
        assert len(invoked) == 0

    def test_parses_mixed_events(self, tmp_path: Path):
        log = tmp_path / "skill-tracking.jsonl"
        lines = [
            json.dumps({"event": "skill_passed", "skill": "python", "target_agent": "code-writer", "timestamp": "2026-04-09T21:00:00Z", "session_id": "s1"}),
            json.dumps({"event": "skill_invoked", "skill": "python", "timestamp": "2026-04-09T21:01:00Z", "session_id": "s1"}),
            json.dumps({"event": "skill_passed", "skill": "powershell", "target_agent": "debugger", "timestamp": "2026-04-09T21:02:00Z", "session_id": "s1"}),
        ]
        log.write_text("\n".join(lines) + "\n")
        passed, invoked = parse_skill_tracking(tmp_path)
        assert len(passed) == 2
        assert len(invoked) == 1

    def test_skips_malformed_lines(self, tmp_path: Path):
        log = tmp_path / "skill-tracking.jsonl"
        lines = [
            "not valid json",
            json.dumps({"event": "skill_invoked", "skill": "python", "timestamp": "2026-04-09T21:00:00Z", "session_id": "s1"}),
            json.dumps({"event": "unknown_event", "skill": "x"}),
        ]
        log.write_text("\n".join(lines) + "\n")
        passed, invoked = parse_skill_tracking(tmp_path)
        assert len(invoked) == 1
        assert len(passed) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_skill_tracking.py::TestParseSkillTracking -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'claude_usage.skill_tracking'`

- [ ] **Step 3: Implement the parser**

Create `claude_usage/skill_tracking.py`:

```python
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
                # Check for skills/ subdirectory within plugin versions
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_skill_tracking.py::TestParseSkillTracking -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Write failing tests for prompt extraction and allowlist**

Add to `tests/test_skill_tracking.py`:

```python
from claude_usage.skill_tracking import extract_skills_from_prompt, build_skill_allowlist


class TestExtractSkillsFromPrompt:
    def setup_method(self):
        self.allowlist = {
            "python", "powershell", "superpowers:test-driven-development",
            "superpowers:brainstorming", "commit-commands:commit",
        }

    def test_backtick_quoted_skill(self):
        prompt = "Use the `python` skill for code style."
        result = extract_skills_from_prompt(prompt, self.allowlist)
        assert result == ["python"]

    def test_backtick_with_prefix(self):
        prompt = "Invoke `superpowers:test-driven-development` before writing code."
        result = extract_skills_from_prompt(prompt, self.allowlist)
        assert result == ["superpowers:test-driven-development"]

    def test_phrase_pattern_use_the(self):
        prompt = "Use the python skill for this task."
        result = extract_skills_from_prompt(prompt, self.allowlist)
        assert result == ["python"]

    def test_phrase_pattern_invoke(self):
        prompt = "Invoke the powershell skill for debugging."
        result = extract_skills_from_prompt(prompt, self.allowlist)
        assert result == ["powershell"]

    def test_multiple_skills_in_prompt(self):
        prompt = "Use the `python` skill and invoke `superpowers:brainstorming` first."
        result = extract_skills_from_prompt(prompt, self.allowlist)
        assert result == ["python", "superpowers:brainstorming"]

    def test_ignores_non_allowlisted_names(self):
        prompt = "Use the `nonexistent-skill` for this."
        result = extract_skills_from_prompt(prompt, self.allowlist)
        assert result == []

    def test_no_skills_in_prompt(self):
        prompt = "Write a function that adds two numbers."
        result = extract_skills_from_prompt(prompt, self.allowlist)
        assert result == []

    def test_deduplicates(self):
        prompt = "Use the `python` skill. Also invoke the python skill."
        result = extract_skills_from_prompt(prompt, self.allowlist)
        assert result == ["python"]


class TestBuildSkillAllowlist:
    def test_reads_user_skills(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        (skills_dir / "python").mkdir(parents=True)
        (skills_dir / "powershell").mkdir(parents=True)
        result = build_skill_allowlist(tmp_path)
        assert "python" in result
        assert "powershell" in result

    def test_reads_plugin_skills_with_prefix(self, tmp_path: Path):
        plugin_skills = tmp_path / "plugins" / "cache" / "official" / "superpowers" / "5.0.7" / "skills"
        (plugin_skills / "brainstorming").mkdir(parents=True)
        (plugin_skills / "test-driven-development").mkdir(parents=True)
        result = build_skill_allowlist(tmp_path)
        assert "brainstorming" in result
        assert "superpowers:brainstorming" in result
        assert "test-driven-development" in result
        assert "superpowers:test-driven-development" in result

    def test_empty_when_no_dirs(self, tmp_path: Path):
        result = build_skill_allowlist(tmp_path)
        assert result == set()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_skill_tracking.py -v`
Expected: All 14 tests PASS (5 parser + 8 extraction + 3 allowlist = 16... wait let me count: 5 + 8 + 3 = 16, but setup_method isn't a test). All 16 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add claude_usage/skill_tracking.py tests/test_skill_tracking.py
git commit -m "feat: add skill tracking parser with prompt extraction and allowlist"
```

---

### Task 3: Aggregator Adoption Logic

**Repo:** `claude-usage` (`C:\Users\chris\.claude\claude-usage`)

**Files:**
- Modify: `claude_usage/aggregator.py` (lines 22 and 38-43)
- Create: `tests/test_aggregator_adoption.py`

- [ ] **Step 1: Write failing tests for adoption correlation**

Create `tests/test_aggregator_adoption.py`:

```python
"""Tests for skill adoption correlation in aggregator."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from claude_usage.aggregator import compute_skill_adoption
from claude_usage.models import SkillInvokedEvent, SkillPassedEvent


class TestComputeSkillAdoption:
    def test_empty_inputs(self):
        result = compute_skill_adoption([], [])
        assert result == {}

    def test_passed_but_never_invoked(self):
        passed = [
            SkillPassedEvent("python", "code-writer", datetime(2026, 4, 9, tzinfo=timezone.utc), "s1"),
            SkillPassedEvent("python", "debugger", datetime(2026, 4, 9, tzinfo=timezone.utc), "s1"),
        ]
        result = compute_skill_adoption(passed, [])
        assert result["python"]["times_passed"] == 2
        assert result["python"]["times_invoked"] == 0
        assert result["python"]["adoption_rate"] == 0.0
        assert result["python"]["by_target_agent"]["code-writer"]["passed"] == 1
        assert result["python"]["by_target_agent"]["code-writer"]["invoked"] == 0

    def test_invoked_without_pass(self):
        invoked = [
            SkillInvokedEvent("python", datetime(2026, 4, 9, tzinfo=timezone.utc), "s1"),
        ]
        result = compute_skill_adoption([], invoked)
        # Direct invocations without a pass event are excluded from adoption metrics
        assert result == {}

    def test_full_adoption(self):
        passed = [
            SkillPassedEvent("python", "code-writer", datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc), "s1"),
        ]
        invoked = [
            SkillInvokedEvent("python", datetime(2026, 4, 9, 12, 1, tzinfo=timezone.utc), "s1"),
        ]
        result = compute_skill_adoption(passed, invoked)
        assert result["python"]["times_passed"] == 1
        assert result["python"]["times_invoked"] == 1
        assert result["python"]["adoption_rate"] == 1.0

    def test_partial_adoption(self):
        passed = [
            SkillPassedEvent("python", "code-writer", datetime(2026, 4, 9, tzinfo=timezone.utc), "s1"),
            SkillPassedEvent("python", "code-writer", datetime(2026, 4, 9, tzinfo=timezone.utc), "s2"),
            SkillPassedEvent("python", "debugger", datetime(2026, 4, 9, tzinfo=timezone.utc), "s3"),
        ]
        invoked = [
            SkillInvokedEvent("python", datetime(2026, 4, 9, tzinfo=timezone.utc), "s1"),
            SkillInvokedEvent("python", datetime(2026, 4, 9, tzinfo=timezone.utc), "s2"),
        ]
        result = compute_skill_adoption(passed, invoked)
        assert result["python"]["times_passed"] == 3
        assert result["python"]["times_invoked"] == 2
        assert abs(result["python"]["adoption_rate"] - 0.667) < 0.01

    def test_multiple_skills(self):
        passed = [
            SkillPassedEvent("python", "code-writer", datetime(2026, 4, 9, tzinfo=timezone.utc), "s1"),
            SkillPassedEvent("powershell", "debugger", datetime(2026, 4, 9, tzinfo=timezone.utc), "s1"),
        ]
        invoked = [
            SkillInvokedEvent("python", datetime(2026, 4, 9, tzinfo=timezone.utc), "s1"),
        ]
        result = compute_skill_adoption(passed, invoked)
        assert result["python"]["adoption_rate"] == 1.0
        assert result["powershell"]["adoption_rate"] == 0.0

    def test_per_agent_breakdown(self):
        passed = [
            SkillPassedEvent("python", "code-writer", datetime(2026, 4, 9, tzinfo=timezone.utc), "s1"),
            SkillPassedEvent("python", "code-writer", datetime(2026, 4, 9, tzinfo=timezone.utc), "s2"),
            SkillPassedEvent("python", "debugger", datetime(2026, 4, 9, tzinfo=timezone.utc), "s3"),
        ]
        invoked = [
            SkillInvokedEvent("python", datetime(2026, 4, 9, tzinfo=timezone.utc), "s1"),
            SkillInvokedEvent("python", datetime(2026, 4, 9, tzinfo=timezone.utc), "s3"),
        ]
        result = compute_skill_adoption(passed, invoked)
        agents = result["python"]["by_target_agent"]
        assert agents["code-writer"]["passed"] == 2
        assert agents["code-writer"]["invoked"] == 1
        assert agents["debugger"]["passed"] == 1
        assert agents["debugger"]["invoked"] == 1

    def test_time_filtering(self):
        cutoff = datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc)
        passed = [
            SkillPassedEvent("python", "code-writer", datetime(2026, 4, 9, 11, 0, tzinfo=timezone.utc), "s1"),
            SkillPassedEvent("python", "code-writer", datetime(2026, 4, 9, 13, 0, tzinfo=timezone.utc), "s2"),
        ]
        invoked = [
            SkillInvokedEvent("python", datetime(2026, 4, 9, 11, 1, tzinfo=timezone.utc), "s1"),
            SkillInvokedEvent("python", datetime(2026, 4, 9, 13, 1, tzinfo=timezone.utc), "s2"),
        ]
        result = compute_skill_adoption(passed, invoked, from_date=cutoff)
        assert result["python"]["times_passed"] == 1
        assert result["python"]["times_invoked"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aggregator_adoption.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_skill_adoption'`

- [ ] **Step 3: Implement the correlation function**

Add to `claude_usage/aggregator.py`, after the existing `aggregate()` function:

```python
def compute_skill_adoption(
    passed_events: list[SkillPassedEvent],
    invoked_events: list[SkillInvokedEvent],
    from_date: datetime | None = None,
    to_date: datetime | None = None,
) -> dict[str, dict]:
    """Correlate skill_passed and skill_invoked events into adoption metrics.

    Only skills with at least one skill_passed event appear in the result.
    Direct invocations (no matching pass) are excluded.
    """
    # Filter by time window
    if from_date:
        passed_events = [e for e in passed_events if e.timestamp >= from_date]
        invoked_events = [e for e in invoked_events if e.timestamp >= from_date]
    if to_date:
        passed_events = [e for e in passed_events if e.timestamp < to_date]
        invoked_events = [e for e in invoked_events if e.timestamp < to_date]

    # Build sets of (skill, session_id) for invoked events for fast lookup
    invoked_sessions: dict[str, set[str]] = defaultdict(set)
    for evt in invoked_events:
        invoked_sessions[evt.skill].add(evt.session_id)

    # Group passed events by skill
    passed_by_skill: dict[str, list[SkillPassedEvent]] = defaultdict(list)
    for evt in passed_events:
        passed_by_skill[evt.skill].append(evt)

    result: dict[str, dict] = {}
    for skill, pass_list in passed_by_skill.items():
        # Count invocations that match a session where this skill was passed
        times_invoked = sum(
            1 for evt in pass_list
            if evt.session_id in invoked_sessions.get(skill, set())
        )
        times_passed = len(pass_list)

        # Per-agent breakdown
        by_agent: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "invoked": 0})
        for evt in pass_list:
            by_agent[evt.target_agent]["passed"] += 1
            if evt.session_id in invoked_sessions.get(skill, set()):
                by_agent[evt.target_agent]["invoked"] += 1

        result[skill] = {
            "times_passed": times_passed,
            "times_invoked": times_invoked,
            "adoption_rate": round(times_invoked / times_passed, 3) if times_passed > 0 else 0.0,
            "by_target_agent": dict(by_agent),
        }

    return result
```

Also add the import at the top of `aggregator.py`:

```python
from claude_usage.models import MessageRecord, SessionRecord, SkillPassedEvent, SkillInvokedEvent
```

(Replace the existing `from claude_usage.models import MessageRecord, SessionRecord` line.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_aggregator_adoption.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Add `by_skill_adoption` to `AggregateResult`**

In `claude_usage/aggregator.py`, add a new field to the `AggregateResult` dataclass after line 25 (`sessions`):

```python
    by_skill_adoption: dict[str, dict] = field(default_factory=dict)  # line 26
```

- [ ] **Step 6: Run full test suite to verify nothing broke**

Run: `pytest -v`
Expected: All existing tests PASS (the new field has a default so nothing breaks)

- [ ] **Step 7: Commit**

```bash
git add claude_usage/aggregator.py tests/test_aggregator_adoption.py
git commit -m "feat: add skill adoption correlation to aggregator"
```

---

### Task 4: Hook Script

**Repo:** `claude_personal_configs` (`C:\Users\chris\.claude`)

**Files:**
- Create: `hooks/skill-tracker.py`
- Create: `tests/test_skill_tracker_hook.py` (optional — this repo may not have a test setup)

**Note:** This hook runs in the `claude_personal_configs` repo but uses `extract_skills_from_prompt` and `build_skill_allowlist` from the `claude-usage` package (installed in `.venv`). The hook script itself is standalone — it reads stdin JSON, calls those functions, and appends to a JSONL file.

- [ ] **Step 1: Create the hook script**

Create `hooks/skill-tracker.py`:

```python
"""PreToolUse hook that tracks skill pass-through and invocation.

Registered for both 'Skill' and 'Agent' tool matchers. Reads the
PreToolUse JSON from stdin and appends events to skill-tracking.jsonl.

Events:
- skill_invoked: when the Skill tool is called directly
- skill_passed: when an Agent dispatch prompt references a skill
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
TRACKING_FILE = CLAUDE_DIR / "skill-tracking.jsonl"


def _get_allowlist() -> set[str]:
    """Build allowlist of installed skill names by scanning the filesystem."""
    try:
        from claude_usage.skill_tracking import build_skill_allowlist
        return build_skill_allowlist(CLAUDE_DIR)
    except ImportError:
        # claude-usage not installed — fall back to basic directory scan
        skills: set[str] = set()
        skills_dir = CLAUDE_DIR / "skills"
        if skills_dir.is_dir():
            for child in skills_dir.iterdir():
                if child.is_dir():
                    skills.add(child.name)
        return skills


def _extract_skills(prompt: str, allowlist: set[str]) -> list[str]:
    """Extract skill references from a prompt, validated against allowlist."""
    try:
        from claude_usage.skill_tracking import extract_skills_from_prompt
        return extract_skills_from_prompt(prompt, allowlist)
    except ImportError:
        # Fallback: simple backtick extraction
        import re
        pattern = re.compile(r"`([a-zA-Z0-9_-]+(?::[a-zA-Z0-9_-]+)?)`")
        candidates = set(pattern.findall(prompt))
        return sorted(c for c in candidates if c in allowlist)


def _append_event(event: dict) -> None:
    """Append a JSON event line to the tracking file."""
    with open(TRACKING_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    session_id = data.get("session_id", "unknown")
    now = datetime.now(timezone.utc).isoformat()

    if tool_name == "Skill":
        skill = tool_input.get("skill")
        if skill:
            _append_event({
                "event": "skill_invoked",
                "skill": skill,
                "timestamp": now,
                "session_id": session_id,
            })

    elif tool_name == "Agent":
        prompt = tool_input.get("prompt", "")
        target_agent = tool_input.get("subagent_type", "unknown")
        if not prompt:
            return

        allowlist = _get_allowlist()
        skills = _extract_skills(prompt, allowlist)

        for skill in skills:
            _append_event({
                "event": "skill_passed",
                "skill": skill,
                "target_agent": target_agent,
                "timestamp": now,
                "session_id": session_id,
            })


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never crash, never block Claude Code
        pass
```

- [ ] **Step 2: Verify the script doesn't crash with empty stdin**

Run: `echo '{}' | & "C:\Users\chris\.claude\.venv\Scripts\python.exe" "C:\Users\chris\.claude\hooks\skill-tracker.py"`
Expected: No output, no error, exit code 0

- [ ] **Step 3: Verify it handles a Skill event**

Run: `echo '{"tool_name":"Skill","tool_input":{"skill":"python"},"session_id":"test-001"}' | & "C:\Users\chris\.claude\.venv\Scripts\python.exe" "C:\Users\chris\.claude\hooks\skill-tracker.py"`
Then: `Get-Content "C:\Users\chris\.claude\skill-tracking.jsonl" | Select-Object -Last 1`
Expected: A JSON line with `"event": "skill_invoked", "skill": "python", "session_id": "test-001"`

- [ ] **Step 4: Verify it handles an Agent event with skill references**

Run: `echo '{"tool_name":"Agent","tool_input":{"prompt":"Use the `python` skill for this.","subagent_type":"code-writer"},"session_id":"test-002"}' | & "C:\Users\chris\.claude\.venv\Scripts\python.exe" "C:\Users\chris\.claude\hooks\skill-tracker.py"`
Then: `Get-Content "C:\Users\chris\.claude\skill-tracking.jsonl" | Select-Object -Last 1`
Expected: A JSON line with `"event": "skill_passed", "skill": "python", "target_agent": "code-writer"`

- [ ] **Step 5: Clean up test data and commit**

Run: `Remove-Item "C:\Users\chris\.claude\skill-tracking.jsonl" -ErrorAction SilentlyContinue`

```bash
git add hooks/skill-tracker.py
git commit -m "feat: add PreToolUse hook for skill adoption tracking"
```

---

### Task 5: Hook Configuration

**Repo:** `claude_personal_configs` (`C:\Users\chris\.claude`)

**Files:**
- Modify: `settings.json` (PreToolUse hooks array)

- [ ] **Step 1: Add Skill matcher hook entry**

In the `PreToolUse` array in `settings.json`, add a new object:

```json
{
  "matcher": "Skill",
  "hooks": [
    {
      "type": "command",
      "command": "/c/Users/chris/.claude/.venv/Scripts/python.exe /c/Users/chris/.claude/hooks/skill-tracker.py",
      "timeout": 5
    }
  ]
}
```

- [ ] **Step 2: Add Agent matcher hook entry**

In the same `PreToolUse` array, add another object:

```json
{
  "matcher": "Agent",
  "hooks": [
    {
      "type": "command",
      "command": "/c/Users/chris/.claude/.venv/Scripts/python.exe /c/Users/chris/.claude/hooks/skill-tracker.py",
      "timeout": 5
    }
  ]
}
```

- [ ] **Step 3: Validate JSON syntax**

Run: `& "C:\Users\chris\.claude\.venv\Scripts\python.exe" -c "import json; json.load(open(r'C:\Users\chris\.claude\settings.json')); print('Valid JSON')"`
Expected: `Valid JSON`

- [ ] **Step 4: Commit**

```bash
git add settings.json
git commit -m "feat: register skill-tracker PreToolUse hooks for Skill and Agent matchers

closes #24"
```

---

### Task 6: Dashboard Integration — Renderer and Template

**Repo:** `claude-usage` (`C:\Users\chris\.claude\claude-usage`)

**Files:**
- Modify: `claude_usage/renderer.py` (line 47, add by_skill_adoption)
- Modify: `templates/dashboard.html` (after skill bar chart section)

- [ ] **Step 1: Pass adoption data to template**

In `claude_usage/renderer.py`, add `by_skill_adoption` to the `data` dict (after line 47, `"by_skill"`):

```python
        "by_skill_adoption": result.by_skill_adoption,
```

- [ ] **Step 2: Add Skill Adoption chart section to dashboard**

In `templates/dashboard.html`, after the `renderSkillBar` function (around line 521), add the new render function:

```javascript
// ── Skill Adoption ───────────────────────────────────────────────────────────

function renderSkillAdoption(bySkillAdoption) {
  const container = document.getElementById('skillAdoptionSection');
  if (!bySkillAdoption || Object.keys(bySkillAdoption).length === 0) {
    container.style.display = 'none';
    return;
  }
  container.style.display = '';

  destroyChart('skillAdoption');
  const skills = Object.entries(bySkillAdoption)
    .sort((a, b) => b[1].times_passed - a[1].times_passed);

  const labels = skills.map(([s]) => s);
  const passedData = skills.map(([, info]) => info.times_passed);
  const invokedData = skills.map(([, info]) => info.times_invoked);

  charts['skillAdoption'] = new Chart(document.getElementById('skillAdoption'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Passed',
          data: passedData,
          backgroundColor: '#8b949e',
          borderRadius: 4
        },
        {
          label: 'Invoked',
          data: invokedData,
          backgroundColor: '#2ea043',
          borderRadius: 4
        }
      ]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { grid: { color: GRID }, stacked: false },
        y: { grid: { display: false } }
      },
      plugins: {
        legend: { labels: { color: TEXT } },
        tooltip: {
          callbacks: {
            afterBody: function(context) {
              const idx = context[0].dataIndex;
              const skill = labels[idx];
              const info = bySkillAdoption[skill];
              return `Adoption: ${(info.adoption_rate * 100).toFixed(0)}%`;
            }
          }
        }
      }
    }
  });

  // Render detail table
  const tbody = document.getElementById('skillAdoptionTableBody');
  tbody.innerHTML = skills.map(([skill, info]) => {
    const rate = (info.adoption_rate * 100).toFixed(0);
    const agents = Object.entries(info.by_target_agent || {})
      .map(([agent, counts]) => `${agent}: ${counts.invoked}/${counts.passed}`)
      .join(', ');
    return `<tr>
      <td>${skill}</td>
      <td>${info.times_passed}</td>
      <td>${info.times_invoked}</td>
      <td>${rate}%</td>
      <td style="font-size:0.85em;color:#8b949e">${agents}</td>
    </tr>`;
  }).join('');
}
```

- [ ] **Step 3: Add HTML elements for the Skill Adoption section**

In the HTML body of `dashboard.html`, after the existing skill chart `<div>` (the one containing `<canvas id="skillBar">`), add:

```html
    <!-- Skill Adoption -->
    <div id="skillAdoptionSection" class="card" style="display:none">
      <h2>Skill Adoption (Pass-Through Tracking)</h2>
      <div style="height:300px"><canvas id="skillAdoption"></canvas></div>
      <table class="detail-table">
        <thead>
          <tr>
            <th>Skill</th>
            <th>Passed</th>
            <th>Invoked</th>
            <th>Rate</th>
            <th>Per Agent</th>
          </tr>
        </thead>
        <tbody id="skillAdoptionTableBody"></tbody>
      </table>
    </div>
```

- [ ] **Step 4: Wire the render call into the dashboard's update function**

In the `renderAll()` or equivalent main render function in `dashboard.html`, add:

```javascript
  renderSkillAdoption(data.by_skill_adoption);
```

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add claude_usage/renderer.py templates/dashboard.html
git commit -m "feat: add Skill Adoption section to dashboard"
```

---

### Task 7: CLI Wiring

**Repo:** `claude-usage` (`C:\Users\chris\.claude\claude-usage`)

**Files:**
- Modify: `claude_usage/__main__.py` (import and call skill tracking parser)
- Modify: `claude_usage/aggregator.py` (wire adoption into aggregate or keep separate)

- [ ] **Step 1: Import and call the skill tracking parser**

In `claude_usage/__main__.py`, add the import:

```python
from claude_usage.skill_tracking import parse_skill_tracking
```

After the `aggregate()` call (line 96), add:

```python
    # Skill adoption tracking (from PreToolUse hook log)
    passed_events, invoked_events = parse_skill_tracking(args.data_dir)
    if passed_events or invoked_events:
        from claude_usage.aggregator import compute_skill_adoption
        result.by_skill_adoption = compute_skill_adoption(
            passed_events,
            invoked_events,
            from_date=args.from_date,
            to_date=args.to_date,
        )
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 3: Manual smoke test — generate dashboard with no tracking data**

Run: `& "C:\Users\chris\.claude\.venv\Scripts\python.exe" -m claude_usage --window 7d`
Expected: Dashboard opens in browser. The "Skill Adoption" section should be hidden (no data yet). All other sections render normally.

- [ ] **Step 4: Manual smoke test — generate dashboard with test tracking data**

Create a temporary test file:

```powershell
$testData = @(
  '{"event":"skill_passed","skill":"python","target_agent":"code-writer","timestamp":"2026-04-09T21:00:00Z","session_id":"test-1"}'
  '{"event":"skill_invoked","skill":"python","timestamp":"2026-04-09T21:01:00Z","session_id":"test-1"}'
  '{"event":"skill_passed","skill":"powershell","target_agent":"debugger","timestamp":"2026-04-09T21:02:00Z","session_id":"test-2"}'
) -join "`n"
$testData | Set-Content "C:\Users\chris\.claude\skill-tracking.jsonl"
```

Run: `& "C:\Users\chris\.claude\.venv\Scripts\python.exe" -m claude_usage --window 7d`
Expected: Dashboard shows "Skill Adoption" section with python (1 passed, 1 invoked, 100%) and powershell (1 passed, 0 invoked, 0%).

Clean up: `Remove-Item "C:\Users\chris\.claude\skill-tracking.jsonl"`

- [ ] **Step 5: Commit**

```bash
git add claude_usage/__main__.py
git commit -m "feat: wire skill adoption tracking into CLI pipeline

closes #5"
```

---

### Task 8: End-to-End Test

**Repo:** `claude-usage` (`C:\Users\chris\.claude\claude-usage`)

**Files:**
- Create or modify: `tests/test_e2e.py`

- [ ] **Step 1: Write an E2E test that verifies adoption data flows through**

Add to `tests/test_e2e.py`:

```python
class TestSkillAdoptionE2E:
    def test_adoption_data_in_rendered_html(self, sample_session_dir: Path, tmp_path: Path):
        """Verify skill adoption data appears in the rendered dashboard."""
        import json
        from claude_usage.parser import parse_sessions
        from claude_usage.aggregator import aggregate, compute_skill_adoption
        from claude_usage.skill_tracking import parse_skill_tracking
        from claude_usage.renderer import render

        # Create a skill-tracking.jsonl in the data dir
        tracking_file = sample_session_dir.parent / "skill-tracking.jsonl"
        lines = [
            json.dumps({"event": "skill_passed", "skill": "python", "target_agent": "code-writer", "timestamp": "2026-04-09T21:00:00Z", "session_id": "test-1"}),
            json.dumps({"event": "skill_invoked", "skill": "python", "timestamp": "2026-04-09T21:01:00Z", "session_id": "test-1"}),
        ]
        tracking_file.write_text("\n".join(lines) + "\n")

        sessions = parse_sessions(sample_session_dir.parent)
        result = aggregate(sessions)

        passed, invoked = parse_skill_tracking(sample_session_dir.parent)
        result.by_skill_adoption = compute_skill_adoption(passed, invoked)

        output = tmp_path / "test-dashboard.html"
        render(result, output_path=output, open_browser=False)

        html = output.read_text(encoding="utf-8")
        assert "Skill Adoption" in html
        assert "python" in html
        assert "by_skill_adoption" in html or "skillAdoption" in html
```

- [ ] **Step 2: Run the E2E test**

Run: `pytest tests/test_e2e.py::TestSkillAdoptionE2E -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: add E2E test for skill adoption tracking in dashboard"
```
