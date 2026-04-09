# Claude Usage Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI tool that parses Claude Code's local JSONL session data and generates an interactive HTML dashboard showing token consumption by model, agent, skill, project, and time period.

**Architecture:** Modular Python package with four layers — models (data classes), parser (JSONL reading), aggregator (grouping/filtering), renderer (HTML+Chart.js). CLI entry point orchestrates the pipeline. Jinja2 templates produce a self-contained HTML file.

**Tech Stack:** Python 3.10+, Jinja2, Chart.js (CDN), pytest

**Spec:** `docs/design.md`
**Issue:** fixes cbeaulieu-gt/claude-usage#1

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `pyproject.toml` | Create | Package config, dependencies, entry point |
| `claude_usage/__init__.py` | Create | Package init, version |
| `claude_usage/models.py` | Create | Data classes: MessageRecord, SessionRecord |
| `claude_usage/parser.py` | Create | JSONL reading, subagent metadata, project hash decoding |
| `claude_usage/aggregator.py` | Create | Grouping, filtering, rolling windows |
| `claude_usage/renderer.py` | Create | Jinja2 + Chart.js HTML generation |
| `claude_usage/__main__.py` | Create | CLI argument parsing and orchestration |
| `templates/dashboard.html` | Create | Jinja2 template matching approved mockup |
| `tests/test_models.py` | Create | Tests for data classes |
| `tests/test_parser.py` | Create | Tests for JSONL parsing and project hash decoding |
| `tests/test_aggregator.py` | Create | Tests for grouping and filtering |
| `tests/conftest.py` | Create | Shared fixtures (sample JSONL data, temp directories) |
| `tests/test_e2e.py` | Create | End-to-end smoke tests |
| `README.md` | Create | Usage instructions |

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `claude_usage/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "claude-usage"
version = "0.1.0"
description = "Parse Claude Code session data and generate an interactive HTML usage dashboard"
requires-python = ">=3.10"
dependencies = [
    "jinja2>=3.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]

[tool.setuptools.packages.find]
include = ["claude_usage*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create claude_usage/__init__.py**

```python
"""Claude Code usage analytics dashboard."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Create tests/__init__.py**

Empty file.

- [ ] **Step 4: Install the package in dev mode**

Run: `pip install -e ".[dev]"`
Expected: Installs successfully with jinja2 and pytest.

- [ ] **Step 5: Verify pytest runs**

Run: `pytest --co`
Expected: "no tests ran" (no test files yet), exit 0 or 5 (no tests collected).

- [ ] **Step 6: Commit**

```
git add pyproject.toml claude_usage/__init__.py tests/__init__.py
git commit -m "chore: scaffold project with pyproject.toml and package structure

fixes cbeaulieu-gt/claude-usage#1"
```

---

### Task 2: Data models

**Files:**
- Create: `claude_usage/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for MessageRecord**

```python
# tests/test_models.py
from datetime import datetime, timezone

from claude_usage.models import MessageRecord


class TestMessageRecord:
    def test_total_tokens(self):
        msg = MessageRecord(
            timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            model="claude-opus-4-6",
            agent_type="general-purpose",
            skill=None,
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=200,
            cache_creation_tokens=300,
        )
        assert msg.total_tokens == 650

    def test_total_tokens_all_zero(self):
        msg = MessageRecord(
            timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            model="claude-sonnet-4-6",
            agent_type="code-writer",
            skill="superpowers:brainstorming",
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        assert msg.total_tokens == 0

    def test_model_short_name_opus(self):
        msg = MessageRecord(
            timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            model="claude-opus-4-6",
            agent_type="general-purpose",
            skill=None,
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        assert msg.model_short == "opus"

    def test_model_short_name_sonnet(self):
        msg = MessageRecord(
            timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            model="claude-sonnet-4-6",
            agent_type="code-writer",
            skill=None,
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        assert msg.model_short == "sonnet"

    def test_model_short_name_haiku(self):
        msg = MessageRecord(
            timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            model="claude-haiku-4-5-20251001",
            agent_type="ops",
            skill=None,
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        assert msg.model_short == "haiku"

    def test_model_short_name_unknown(self):
        msg = MessageRecord(
            timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            model="claude-future-model-9",
            agent_type="general-purpose",
            skill=None,
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        assert msg.model_short == "claude-future-model-9"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'MessageRecord'`

- [ ] **Step 3: Implement MessageRecord**

```python
# claude_usage/models.py
"""Data classes for parsed Claude Code session data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MessageRecord:
    """A single assistant message with token usage, attributed to an agent."""

    timestamp: datetime
    model: str
    agent_type: str
    skill: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )

    @property
    def model_short(self) -> str:
        """Extract short model name: 'opus', 'sonnet', 'haiku', or full name."""
        for name in ("opus", "sonnet", "haiku"):
            if name in self.model:
                return name
        return self.model
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Write failing tests for SessionRecord**

Append to `tests/test_models.py`:

```python
from claude_usage.models import SessionRecord


class TestSessionRecord:
    def _make_msg(self, model="claude-opus-4-6", agent="general-purpose",
                  input_t=100, output_t=50, cache_read=0, cache_create=0,
                  skill=None, ts=None):
        return MessageRecord(
            timestamp=ts or datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            model=model,
            agent_type=agent,
            skill=skill,
            input_tokens=input_t,
            output_tokens=output_t,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_create,
        )

    def test_total_tokens_sums_messages(self):
        session = SessionRecord(
            session_id="abc-123",
            project="my-project",
            start_time=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            root_agent="general-purpose",
            messages=[
                self._make_msg(input_t=100, output_t=50),
                self._make_msg(input_t=200, output_t=100),
            ],
            subagent_types=["code-writer"],
        )
        assert session.total_tokens == 450

    def test_total_tokens_empty_messages(self):
        session = SessionRecord(
            session_id="abc-123",
            project="my-project",
            start_time=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            root_agent="general-purpose",
            messages=[],
            subagent_types=[],
        )
        assert session.total_tokens == 0

    def test_duration_from_timestamps(self):
        session = SessionRecord(
            session_id="abc-123",
            project="my-project",
            start_time=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            root_agent="general-purpose",
            messages=[
                self._make_msg(ts=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)),
                self._make_msg(ts=datetime(2026, 4, 9, 12, 30, 0, tzinfo=timezone.utc)),
                self._make_msg(ts=datetime(2026, 4, 9, 13, 5, 0, tzinfo=timezone.utc)),
            ],
            subagent_types=[],
        )
        assert session.duration_minutes == 65

    def test_duration_single_message(self):
        session = SessionRecord(
            session_id="abc-123",
            project="my-project",
            start_time=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            root_agent="general-purpose",
            messages=[
                self._make_msg(ts=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)),
            ],
            subagent_types=[],
        )
        assert session.duration_minutes == 0

    def test_duration_no_messages(self):
        session = SessionRecord(
            session_id="abc-123",
            project="my-project",
            start_time=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            root_agent="general-purpose",
            messages=[],
            subagent_types=[],
        )
        assert session.duration_minutes == 0
```

- [ ] **Step 6: Run tests to verify new tests fail**

Run: `pytest tests/test_models.py -v`
Expected: New SessionRecord tests FAIL — `ImportError: cannot import name 'SessionRecord'`

- [ ] **Step 7: Implement SessionRecord**

Append to `claude_usage/models.py`:

```python
@dataclass(frozen=True, slots=True)
class SessionRecord:
    """A parsed session with all its messages (including subagent messages)."""

    session_id: str
    project: str
    start_time: datetime
    root_agent: str
    messages: list[MessageRecord]
    subagent_types: list[str]

    @property
    def total_tokens(self) -> int:
        return sum(m.total_tokens for m in self.messages)

    @property
    def duration_minutes(self) -> int:
        """Duration from first to last message timestamp, in minutes."""
        if len(self.messages) < 2:
            return 0
        timestamps = [m.timestamp for m in self.messages]
        delta = max(timestamps) - min(timestamps)
        return int(delta.total_seconds() / 60)
```

- [ ] **Step 8: Run all tests**

Run: `pytest tests/test_models.py -v`
Expected: All 11 tests PASS.

- [ ] **Step 9: Commit**

```
git add claude_usage/models.py tests/test_models.py
git commit -m "feat: add MessageRecord and SessionRecord data classes

MessageRecord holds per-message token usage attributed to an agent.
SessionRecord holds a full session with all messages and subagent info.
Both compute total_tokens; SessionRecord computes duration_minutes."
```

---

### Task 3: Parser — project hash decoding

**Files:**
- Create: `claude_usage/parser.py`
- Create: `tests/test_parser.py`

- [ ] **Step 1: Write failing tests for decode_project_hash**

```python
# tests/test_parser.py
from claude_usage.parser import decode_project_hash


class TestDecodeProjectHash:
    def test_windows_path_deep(self):
        # C:\Users\chris\.claude -> C--Users-chris--claude -> last segment 'claude'
        assert decode_project_hash("C--Users-chris--claude") == "claude"

    def test_windows_path_shallow(self):
        # i:\games\... -> only one '--' so last segment is everything after
        assert decode_project_hash("i--games-raid-rsl-rule-generator") == "games-raid-rsl-rule-generator"

    def test_single_segment(self):
        assert decode_project_hash("myproject") == "myproject"

    def test_three_segments(self):
        assert decode_project_hash("C--Users-chris--code-deep-nested--project") == "project"

    def test_empty_string(self):
        assert decode_project_hash("") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_parser.py::TestDecodeProjectHash -v`
Expected: FAIL — `ImportError: cannot import name 'decode_project_hash'`

- [ ] **Step 3: Implement decode_project_hash**

```python
# claude_usage/parser.py
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
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_parser.py::TestDecodeProjectHash -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```
git add claude_usage/parser.py tests/test_parser.py
git commit -m "feat: add project hash decoder for session directory names

Decodes Claude Code's project hash format (e.g. 'C--Users-chris--claude'
-> 'claude') by splitting on '--' and taking the last segment."
```

---

### Task 4: Parser — JSONL reading

**Files:**
- Modify: `claude_usage/parser.py`
- Create: `tests/conftest.py`
- Modify: `tests/test_parser.py`

- [ ] **Step 1: Create test fixtures with sample JSONL data**

```python
# tests/conftest.py
"""Shared test fixtures for claude-usage tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_session_dir(tmp_path: Path) -> Path:
    """Create a mock Claude Code projects directory with sample session data."""
    project_dir = tmp_path / "projects" / "C--Users-chris--myproject"
    project_dir.mkdir(parents=True)

    session_id = "abc-123-def"

    # Main session JSONL
    lines = [
        {
            "type": "agent-setting",
            "agentSetting": "general-purpose",
            "sessionId": session_id,
        },
        {
            "parentUuid": None,
            "type": "user",
            "message": {"role": "user", "content": "Hello"},
            "uuid": "msg-1",
            "timestamp": "2026-04-09T12:00:00.000Z",
            "sessionId": session_id,
        },
        {
            "parentUuid": "msg-1",
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-6",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi there"}],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 200,
                    "cache_creation_input_tokens": 300,
                },
            },
            "uuid": "msg-2",
            "timestamp": "2026-04-09T12:00:05.000Z",
            "sessionId": session_id,
        },
        {
            "parentUuid": "msg-2",
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-6",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Skill",
                        "input": {"skill": "superpowers:brainstorming"},
                    }
                ],
                "usage": {
                    "input_tokens": 50,
                    "output_tokens": 25,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            },
            "uuid": "msg-3",
            "timestamp": "2026-04-09T12:01:00.000Z",
            "sessionId": session_id,
        },
        {
            "parentUuid": "msg-3",
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-6",
                "role": "assistant",
                "content": [{"type": "text", "text": "Done"}],
                "usage": {
                    "input_tokens": 80,
                    "output_tokens": 40,
                    "cache_read_input_tokens": 100,
                    "cache_creation_input_tokens": 0,
                },
            },
            "uuid": "msg-4",
            "timestamp": "2026-04-09T12:30:00.000Z",
            "sessionId": session_id,
        },
    ]

    jsonl_path = project_dir / f"{session_id}.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(line) for line in lines),
        encoding="utf-8",
    )

    # Subagent directory
    subagent_dir = project_dir / session_id / "subagents"
    subagent_dir.mkdir(parents=True)

    # Subagent metadata
    meta = {"agentType": "code-writer", "description": "Write feature X"}
    (subagent_dir / "agent-sub1.meta.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )

    # Subagent JSONL
    sub_lines = [
        {
            "parentUuid": None,
            "type": "user",
            "agentId": "sub1",
            "message": {"role": "user", "content": "Implement feature X"},
            "uuid": "sub-msg-1",
            "timestamp": "2026-04-09T12:05:00.000Z",
            "sessionId": session_id,
        },
        {
            "parentUuid": "sub-msg-1",
            "type": "assistant",
            "agentId": "sub1",
            "message": {
                "model": "claude-sonnet-4-6",
                "role": "assistant",
                "content": [{"type": "text", "text": "Implementing..."}],
                "usage": {
                    "input_tokens": 500,
                    "output_tokens": 250,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 1000,
                },
            },
            "uuid": "sub-msg-2",
            "timestamp": "2026-04-09T12:10:00.000Z",
            "sessionId": session_id,
        },
    ]

    (subagent_dir / "agent-sub1.jsonl").write_text(
        "\n".join(json.dumps(line) for line in sub_lines),
        encoding="utf-8",
    )

    return tmp_path
```

- [ ] **Step 2: Write failing tests for parse_sessions**

Append to `tests/test_parser.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from claude_usage.parser import parse_sessions


class TestParseSessions:
    def test_parses_single_session(self, sample_session_dir: Path):
        sessions = parse_sessions(sample_session_dir)
        assert len(sessions) == 1

    def test_session_metadata(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        assert session.session_id == "abc-123-def"
        assert session.project == "myproject"
        assert session.root_agent == "general-purpose"

    def test_session_start_time(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        expected = datetime(2026, 4, 9, 12, 0, 5, tzinfo=timezone.utc)
        assert session.start_time == expected

    def test_message_count_includes_subagent(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        # 3 parent assistant messages + 1 subagent assistant message = 4
        assert len(session.messages) == 4

    def test_parent_messages_attributed_to_root_agent(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        parent_msgs = [m for m in session.messages if m.agent_type == "general-purpose"]
        assert len(parent_msgs) == 3

    def test_subagent_messages_attributed_to_agent_type(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        sub_msgs = [m for m in session.messages if m.agent_type == "code-writer"]
        assert len(sub_msgs) == 1
        assert sub_msgs[0].input_tokens == 500
        assert sub_msgs[0].output_tokens == 250

    def test_skill_extracted_from_tool_use(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        skill_msgs = [m for m in session.messages if m.skill is not None]
        assert len(skill_msgs) == 1
        assert skill_msgs[0].skill == "superpowers:brainstorming"

    def test_subagent_types_listed(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        assert session.subagent_types == ["code-writer"]

    def test_token_totals(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        # Parent: (100+50+200+300) + (50+25+0+0) + (80+40+100+0) = 650+75+220 = 945
        # Subagent: 500+250+0+1000 = 1750
        # Total: 2695
        assert session.total_tokens == 2695

    def test_empty_projects_dir(self, tmp_path: Path):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        sessions = parse_sessions(tmp_path)
        assert sessions == []

    def test_no_projects_dir(self, tmp_path: Path):
        sessions = parse_sessions(tmp_path)
        assert sessions == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_parser.py::TestParseSessions -v`
Expected: FAIL — `ImportError: cannot import name 'parse_sessions'`

- [ ] **Step 4: Implement parse_sessions and helpers**

Add to `claude_usage/parser.py`:

```python
def _parse_timestamp(ts_str: str) -> datetime:
    """Parse an ISO 8601 timestamp string to a datetime."""
    ts_str = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(ts_str)


def _extract_skill(content: list[dict]) -> str | None:
    """Extract skill name from assistant message content blocks."""
    for block in content:
        if (
            block.get("type") == "tool_use"
            and block.get("name") == "Skill"
            and isinstance(block.get("input"), dict)
        ):
            return block["input"].get("skill")
    return None


def _parse_jsonl_messages(
    jsonl_path: Path, agent_type: str
) -> list[MessageRecord]:
    """Parse assistant messages from a JSONL file, attributing to agent_type."""
    messages: list[MessageRecord] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") != "assistant":
                continue

            msg = entry.get("message", {})
            usage = msg.get("usage")
            model = msg.get("model")
            if not usage or not model:
                continue

            content = msg.get("content", [])
            skill = _extract_skill(content) if isinstance(content, list) else None

            timestamp = _parse_timestamp(entry["timestamp"])

            messages.append(
                MessageRecord(
                    timestamp=timestamp,
                    model=model,
                    agent_type=agent_type,
                    skill=skill,
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                    cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
                )
            )
    return messages


def _parse_session(
    jsonl_path: Path, project_name: str
) -> SessionRecord | None:
    """Parse a single session JSONL file and its subagents."""
    session_id = jsonl_path.stem

    # Read agent-setting from first line
    root_agent = "unknown"
    with open(jsonl_path, "r", encoding="utf-8") as f:
        first_line = f.readline().strip()
        if first_line:
            try:
                first = json.loads(first_line)
                if first.get("type") == "agent-setting":
                    root_agent = first.get("agentSetting", "unknown")
            except json.JSONDecodeError:
                pass

    # Parse parent session messages
    messages = _parse_jsonl_messages(jsonl_path, root_agent)

    # Parse subagent messages
    subagent_types: list[str] = []
    subagent_dir = jsonl_path.parent / session_id / "subagents"
    if subagent_dir.is_dir():
        for meta_path in subagent_dir.glob("*.meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                agent_type = meta.get("agentType", "unknown")
            except (json.JSONDecodeError, OSError):
                agent_type = "unknown"

            subagent_types.append(agent_type)

            # Find matching JSONL
            agent_id = meta_path.stem.replace(".meta", "")
            sub_jsonl = subagent_dir / f"{agent_id}.jsonl"
            if sub_jsonl.is_file():
                messages.extend(_parse_jsonl_messages(sub_jsonl, agent_type))

    if not messages:
        start_time = datetime.now(timezone.utc)
    else:
        start_time = min(m.timestamp for m in messages)

    return SessionRecord(
        session_id=session_id,
        project=project_name,
        start_time=start_time,
        root_agent=root_agent,
        messages=messages,
        subagent_types=sorted(set(subagent_types)),
    )


def parse_sessions(data_dir: Path) -> list[SessionRecord]:
    """Parse all sessions from a Claude Code data directory.

    Args:
        data_dir: Path to the Claude data directory (e.g. ~/.claude).
                  Sessions are in data_dir/projects/<hash>/<session>.jsonl

    Returns:
        List of SessionRecord objects, sorted by start_time descending.
    """
    projects_dir = data_dir / "projects"
    if not projects_dir.is_dir():
        return []

    sessions: list[SessionRecord] = []

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue

        project_name = decode_project_hash(project_dir.name)

        for jsonl_path in project_dir.glob("*.jsonl"):
            session = _parse_session(jsonl_path, project_name)
            if session is not None:
                sessions.append(session)

    sessions.sort(key=lambda s: s.start_time, reverse=True)
    return sessions
```

- [ ] **Step 5: Run all parser tests**

Run: `pytest tests/test_parser.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```
git add claude_usage/parser.py tests/conftest.py tests/test_parser.py
git commit -m "feat: implement JSONL session parser with subagent support

Reads session JSONL files from ~/.claude/projects/, extracts assistant
message token usage, maps subagent messages via .meta.json, and extracts
skill invocations from Skill tool_use entries."
```

---

### Task 5: Aggregator

**Files:**
- Create: `claude_usage/aggregator.py`
- Create: `tests/test_aggregator.py`

- [ ] **Step 1: Write failing tests for aggregate functions**

```python
# tests/test_aggregator.py
from datetime import datetime, timedelta, timezone

from claude_usage.aggregator import aggregate
from claude_usage.models import MessageRecord, SessionRecord


def _msg(model="claude-opus-4-6", agent="general-purpose", skill=None,
         input_t=100, output_t=50, cache_read=0, cache_create=0,
         ts=None):
    return MessageRecord(
        timestamp=ts or datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
        model=model,
        agent_type=agent,
        skill=skill,
        input_tokens=input_t,
        output_tokens=output_t,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_create,
    )


def _session(messages, session_id="s1", project="proj", root_agent="general-purpose",
             subagent_types=None):
    start = min(m.timestamp for m in messages) if messages else datetime(2026, 4, 9, tzinfo=timezone.utc)
    return SessionRecord(
        session_id=session_id,
        project=project,
        start_time=start,
        root_agent=root_agent,
        messages=messages,
        subagent_types=subagent_types or [],
    )


class TestAggregateByModel:
    def test_groups_by_model_short(self):
        sessions = [_session([
            _msg(model="claude-opus-4-6", input_t=100, output_t=50),
            _msg(model="claude-sonnet-4-6", input_t=200, output_t=100),
            _msg(model="claude-opus-4-6", input_t=50, output_t=25),
        ])]
        result = aggregate(sessions)
        assert result.by_model["opus"]["total_tokens"] == 225
        assert result.by_model["sonnet"]["total_tokens"] == 300

    def test_model_message_count(self):
        sessions = [_session([
            _msg(model="claude-opus-4-6"),
            _msg(model="claude-opus-4-6"),
            _msg(model="claude-sonnet-4-6"),
        ])]
        result = aggregate(sessions)
        assert result.by_model["opus"]["message_count"] == 2
        assert result.by_model["sonnet"]["message_count"] == 1


class TestAggregateByAgent:
    def test_groups_by_agent_type(self):
        sessions = [_session([
            _msg(agent="general-purpose", input_t=100, output_t=50),
            _msg(agent="code-writer", model="claude-sonnet-4-6", input_t=200, output_t=100),
        ])]
        result = aggregate(sessions)
        assert result.by_agent["general-purpose"]["total_tokens"] == 150
        assert result.by_agent["code-writer"]["total_tokens"] == 300

    def test_agent_includes_model(self):
        sessions = [_session([
            _msg(agent="general-purpose", model="claude-opus-4-6"),
        ])]
        result = aggregate(sessions)
        assert result.by_agent["general-purpose"]["primary_model"] == "opus"


class TestAggregateBySkill:
    def test_groups_by_skill(self):
        sessions = [_session([
            _msg(skill="superpowers:brainstorming", input_t=100, output_t=50),
            _msg(skill="superpowers:brainstorming", input_t=200, output_t=100),
            _msg(skill="commit-commands:commit-push-pr", input_t=50, output_t=25),
            _msg(skill=None, input_t=1000, output_t=500),
        ])]
        result = aggregate(sessions)
        assert result.by_skill["superpowers:brainstorming"]["invocation_count"] == 2
        assert result.by_skill["commit-commands:commit-push-pr"]["invocation_count"] == 1
        assert None not in result.by_skill


class TestAggregateByProject:
    def test_groups_by_project(self):
        sessions = [
            _session([_msg(input_t=100, output_t=50)], project="proj-a"),
            _session([_msg(input_t=200, output_t=100)], session_id="s2", project="proj-b"),
        ]
        result = aggregate(sessions)
        assert result.by_project["proj-a"]["total_tokens"] == 150
        assert result.by_project["proj-b"]["total_tokens"] == 300


class TestAggregateDaily:
    def test_groups_by_day(self):
        day1 = datetime(2026, 4, 8, 10, 0, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 4, 9, 14, 0, 0, tzinfo=timezone.utc)
        sessions = [_session([
            _msg(ts=day1, input_t=100, output_t=50),
            _msg(ts=day2, input_t=200, output_t=100),
        ])]
        result = aggregate(sessions)
        assert "2026-04-08" in result.by_day
        assert "2026-04-09" in result.by_day
        assert result.by_day["2026-04-08"]["total_tokens"] == 150
        assert result.by_day["2026-04-09"]["total_tokens"] == 300


class TestAggregateTimeFilter:
    def test_filter_by_date_range(self):
        old = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
        recent = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
        sessions = [_session([
            _msg(ts=old, input_t=100, output_t=50),
            _msg(ts=recent, input_t=200, output_t=100),
        ])]
        from_date = datetime(2026, 4, 5, tzinfo=timezone.utc)
        result = aggregate(sessions, from_date=from_date)
        assert result.total_tokens == 300

    def test_filter_by_window(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=10)
        recent = now - timedelta(hours=2)
        sessions = [_session([
            _msg(ts=old, input_t=100, output_t=50),
            _msg(ts=recent, input_t=200, output_t=100),
        ])]
        result = aggregate(sessions, window_hours=5)
        assert result.total_tokens == 300
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_aggregator.py -v`
Expected: FAIL — `ImportError: cannot import name 'aggregate'`

- [ ] **Step 3: Implement the aggregator**

```python
# claude_usage/aggregator.py
"""Aggregate parsed session data by model, agent, skill, project, and time."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from claude_usage.models import MessageRecord, SessionRecord


@dataclass
class AggregateResult:
    """Holds all aggregated data for rendering."""

    total_tokens: int = 0
    total_messages: int = 0
    total_sessions: int = 0

    by_model: dict[str, dict] = field(default_factory=dict)
    by_agent: dict[str, dict] = field(default_factory=dict)
    by_skill: dict[str, dict] = field(default_factory=dict)
    by_project: dict[str, dict] = field(default_factory=dict)
    by_day: dict[str, dict] = field(default_factory=dict)
    sessions: list[dict] = field(default_factory=list)


def _add_tokens(bucket: dict, msg: MessageRecord) -> None:
    """Add a message's token counts to an accumulator dict."""
    bucket["total_tokens"] = bucket.get("total_tokens", 0) + msg.total_tokens
    bucket["input_tokens"] = bucket.get("input_tokens", 0) + msg.input_tokens
    bucket["output_tokens"] = bucket.get("output_tokens", 0) + msg.output_tokens
    bucket["cache_read_tokens"] = bucket.get("cache_read_tokens", 0) + msg.cache_read_tokens
    bucket["cache_creation_tokens"] = bucket.get("cache_creation_tokens", 0) + msg.cache_creation_tokens
    bucket["message_count"] = bucket.get("message_count", 0) + 1


def aggregate(
    sessions: list[SessionRecord],
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    window_hours: float | None = None,
) -> AggregateResult:
    """Aggregate session data with optional time filtering.

    Args:
        sessions: Parsed session records.
        from_date: Only include messages on or after this time.
        to_date: Only include messages before this time.
        window_hours: Rolling window - only include messages from the last N hours.
                      Overrides from_date if set.
    """
    result = AggregateResult()

    if window_hours is not None:
        from_date = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        to_date = None

    filtered_messages: list[MessageRecord] = []
    session_ids_seen: set[str] = set()
    agent_models: dict[str, Counter] = defaultdict(Counter)
    project_sessions: dict[str, set] = defaultdict(set)

    for session in sessions:
        session_messages: list[MessageRecord] = []
        for msg in session.messages:
            if from_date and msg.timestamp < from_date:
                continue
            if to_date and msg.timestamp >= to_date:
                continue
            session_messages.append(msg)
            filtered_messages.append(msg)

        if session_messages:
            session_ids_seen.add(session.session_id)
            project_sessions[session.project].add(session.session_id)

            model_tokens: dict[str, int] = defaultdict(int)
            for m in session_messages:
                model_tokens[m.model_short] += m.total_tokens

            agents_in_session = sorted(set(m.agent_type for m in session_messages))

            result.sessions.append({
                "session_id": session.session_id,
                "project": session.project,
                "start_time": min(m.timestamp for m in session_messages).isoformat(),
                "root_agent": session.root_agent,
                "agents": agents_in_session,
                "total_tokens": sum(m.total_tokens for m in session_messages),
                "model_split": dict(model_tokens),
                "duration_minutes": session.duration_minutes,
                "message_count": len(session_messages),
            })

    result.total_tokens = sum(m.total_tokens for m in filtered_messages)
    result.total_messages = len(filtered_messages)
    result.total_sessions = len(session_ids_seen)

    for msg in filtered_messages:
        model = msg.model_short
        if model not in result.by_model:
            result.by_model[model] = {}
        _add_tokens(result.by_model[model], msg)

    for msg in filtered_messages:
        agent = msg.agent_type
        if agent not in result.by_agent:
            result.by_agent[agent] = {}
        _add_tokens(result.by_agent[agent], msg)
        agent_models[agent][msg.model_short] += 1

    for agent, counter in agent_models.items():
        result.by_agent[agent]["primary_model"] = counter.most_common(1)[0][0]

    agent_session_count: dict[str, set] = defaultdict(set)
    for session_summary in result.sessions:
        for agent in session_summary["agents"]:
            agent_session_count[agent].add(session_summary["session_id"])
    for agent in result.by_agent:
        result.by_agent[agent]["session_count"] = len(agent_session_count.get(agent, set()))

    for msg in filtered_messages:
        if msg.skill is None:
            continue
        if msg.skill not in result.by_skill:
            result.by_skill[msg.skill] = {"invocation_count": 0, "total_tokens": 0}
        result.by_skill[msg.skill]["invocation_count"] += 1
        result.by_skill[msg.skill]["total_tokens"] += msg.total_tokens

    result.by_project = {}
    for session_summary in result.sessions:
        proj = session_summary["project"]
        if proj not in result.by_project:
            result.by_project[proj] = {"total_tokens": 0, "session_count": 0, "message_count": 0}
        result.by_project[proj]["total_tokens"] += session_summary["total_tokens"]
        result.by_project[proj]["message_count"] += session_summary["message_count"]
    for proj, sess_ids in project_sessions.items():
        if proj in result.by_project:
            result.by_project[proj]["session_count"] = len(sess_ids)

    for msg in filtered_messages:
        day = msg.timestamp.strftime("%Y-%m-%d")
        if day not in result.by_day:
            result.by_day[day] = {"total_tokens": 0, "by_model": {}}
        result.by_day[day]["total_tokens"] += msg.total_tokens
        model = msg.model_short
        if model not in result.by_day[day]["by_model"]:
            result.by_day[day]["by_model"][model] = 0
        result.by_day[day]["by_model"][model] += msg.total_tokens

    result.sessions.sort(key=lambda s: s["start_time"], reverse=True)

    return result
```

- [ ] **Step 4: Run all aggregator tests**

Run: `pytest tests/test_aggregator.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```
git add claude_usage/aggregator.py tests/test_aggregator.py
git commit -m "feat: implement aggregator with model/agent/skill/project/daily grouping

Groups parsed messages by model, agent, skill, project, and day.
Supports time filtering via date range or rolling window. Produces
per-session summaries for drill-down view."
```

---

### Task 6: HTML template and renderer

**Files:**
- Create: `templates/dashboard.html`
- Create: `claude_usage/renderer.py`

- [ ] **Step 1: Create the Jinja2 dashboard template**

Create `templates/dashboard.html`. Base it on the approved mockup at `C:\Users\chris\AppData\Local\Temp\claude-mockups\dashboard-mockup.html`, converting hardcoded sample data to Jinja2 template variables.

The template receives these variables:
- `{{ data_json }}` — full AggregateResult serialized as JSON, embedded in a `<script>` tag as `const DATA = {{ data_json | safe }};`
- `{{ generated_at }}` — ISO timestamp of when the report was generated
- `{{ limits_json }}` — `{limit_5h, limit_7d, limit_sonnet_7d}` or `null`, embedded as `const LIMITS = {{ limits_json | safe }};`

The template must contain:
- All CSS inline (same dark theme as mockup: `#0d1117` background, `#161b22` cards, model colors Opus=`#8b5cf6`, Sonnet=`#2ea043`, Haiku=`#58a6ff`)
- Chart.js loaded from `https://cdn.jsdelivr.net/npm/chart.js@4`
- JavaScript that reads `DATA` and renders: budget gauges, model donut, daily stacked bar, agent horizontal bar, agent details table, skill bar, project bar, session drill-down table
- Budget gauges: show percentage if LIMITS is provided, otherwise show raw token count
- Date range picker and metric toggle wired to client-side filtering
- Session drill-down with columns: Time, Project, Agents, Tokens, Model Split, Duration

Reference the mockup HTML file for the exact layout, styling, and chart configuration.

- [ ] **Step 2: Implement the renderer**

```python
# claude_usage/renderer.py
"""Render aggregated data as a self-contained HTML dashboard."""

from __future__ import annotations

import json
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from jinja2 import Environment, FileSystemLoader

from claude_usage.aggregator import AggregateResult

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def render(
    result: AggregateResult,
    output_path: Path | None = None,
    open_browser: bool = True,
    limits: dict[str, int] | None = None,
) -> Path:
    """Render the dashboard HTML from aggregated data.

    Args:
        result: Aggregated usage data.
        output_path: Where to write the HTML. If None, writes to a temp file.
        open_browser: Whether to open the result in the default browser.
        limits: Optional budget limits: {limit_5h, limit_7d, limit_sonnet_7d}.

    Returns:
        Path to the generated HTML file.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("dashboard.html")

    data = {
        "total_tokens": result.total_tokens,
        "total_messages": result.total_messages,
        "total_sessions": result.total_sessions,
        "by_model": result.by_model,
        "by_agent": result.by_agent,
        "by_skill": result.by_skill,
        "by_project": result.by_project,
        "by_day": result.by_day,
        "sessions": result.sessions,
    }

    html = template.render(
        data_json=json.dumps(data, indent=2, default=str),
        generated_at=datetime.now(timezone.utc).isoformat(),
        limits_json=json.dumps(limits) if limits else "null",
    )

    if output_path is None:
        tmp = NamedTemporaryFile(
            suffix=".html", prefix="claude-usage-", delete=False, mode="w",
            encoding="utf-8",
        )
        tmp.write(html)
        tmp.close()
        output_path = Path(tmp.name)
    else:
        output_path.write_text(html, encoding="utf-8")

    if open_browser:
        webbrowser.open(output_path.as_uri())

    return output_path
```

- [ ] **Step 3: Verify template loads**

Run: `python -c "from claude_usage.renderer import render; print('renderer imports OK')"`
Expected: Prints "renderer imports OK".

- [ ] **Step 4: Commit**

```
git add templates/dashboard.html claude_usage/renderer.py
git commit -m "feat: add Jinja2 dashboard template and HTML renderer

Template uses Chart.js (CDN) with dark theme matching approved mockup.
Renderer serializes AggregateResult as embedded JSON, generates a
self-contained HTML file, and optionally opens it in the browser."
```

---

### Task 7: CLI entry point

**Files:**
- Create: `claude_usage/__main__.py`

- [ ] **Step 1: Implement the CLI**

```python
# claude_usage/__main__.py
"""CLI entry point for claude-usage dashboard."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from claude_usage.aggregator import aggregate
from claude_usage.parser import parse_sessions
from claude_usage.renderer import render


def _parse_window(window_str: str) -> float:
    """Parse a window string like '5h' or '7d' into hours."""
    match = re.match(r"^(\d+(?:\.\d+)?)(h|d)$", window_str.strip().lower())
    if not match:
        raise argparse.ArgumentTypeError(
            f"Invalid window format: '{window_str}'. Use e.g. '5h' or '7d'."
        )
    value = float(match.group(1))
    unit = match.group(2)
    if unit == "d":
        value *= 24
    return value


def _parse_date(date_str: str) -> datetime:
    """Parse a date string (YYYY-MM-DD) into a timezone-aware datetime."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date format: '{date_str}'. Use YYYY-MM-DD."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="claude-usage",
        description="Generate an HTML dashboard of Claude Code token usage.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path.home() / ".claude",
        help="Path to Claude Code data directory (default: ~/.claude)",
    )
    parser.add_argument(
        "--from", dest="from_date", type=_parse_date,
        help="Start date (YYYY-MM-DD). Only include data on or after this date.",
    )
    parser.add_argument(
        "--to", dest="to_date", type=_parse_date,
        help="End date (YYYY-MM-DD). Only include data before this date.",
    )
    parser.add_argument(
        "--window", type=_parse_window,
        help="Rolling window (e.g. '5h', '7d'). Overrides --from.",
    )
    parser.add_argument(
        "--output", "-o", type=Path,
        help="Output file path. If omitted, writes to a temp file.",
    )
    parser.add_argument(
        "--no-open", action="store_true",
        help="Don't open the dashboard in a browser.",
    )
    parser.add_argument(
        "--limit-5h", type=int, default=None,
        help="Token budget for 5-hour rolling window (for gauge percentage).",
    )
    parser.add_argument(
        "--limit-7d", type=int, default=None,
        help="Token budget for 7-day rolling window (for gauge percentage).",
    )
    parser.add_argument(
        "--limit-sonnet-7d", type=int, default=None,
        help="Token budget for Sonnet-only 7-day window (for gauge percentage).",
    )

    args = parser.parse_args()

    print(f"Scanning sessions in {args.data_dir}...")
    sessions = parse_sessions(args.data_dir)
    print(f"Found {len(sessions)} sessions.")

    result = aggregate(
        sessions,
        from_date=args.from_date,
        to_date=args.to_date,
        window_hours=args.window,
    )
    print(f"Aggregated: {result.total_tokens:,} tokens across {result.total_sessions} sessions.")

    limits = None
    if any([args.limit_5h, args.limit_7d, args.limit_sonnet_7d]):
        limits = {
            "limit_5h": args.limit_5h,
            "limit_7d": args.limit_7d,
            "limit_sonnet_7d": args.limit_sonnet_7d,
        }

    output = render(
        result,
        output_path=args.output,
        open_browser=not args.no_open,
        limits=limits,
    )
    print(f"Dashboard written to {output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI runs with --help**

Run: `python -m claude_usage --help`
Expected: Prints usage information with all flags.

- [ ] **Step 3: Commit**

```
git add claude_usage/__main__.py
git commit -m "feat: add CLI entry point with date range, window, and limit flags

Orchestrates parse -> aggregate -> render pipeline. Supports --from/--to
date range, --window rolling window (5h, 7d), --output path, --no-open,
and --limit-* flags for budget gauge percentages."
```

---

### Task 8: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

```markdown
# claude-usage

Parse Claude Code session data and generate an interactive HTML dashboard showing token consumption by model, agent, skill, project, and time period.

## Why

Claude Code tracks three billing buckets (5h rolling, 7d rolling, Sonnet-only 7d) but provides no per-agent or per-skill visibility. This tool reads Claude Code's local JSONL session files and generates a dashboard that breaks down where your tokens are going.

## Install

```bash
pip install -e .
```

Requires Python 3.10+.

## Usage

```bash
# Default: last 7 days, opens in browser
python -m claude_usage

# Rolling window matching billing buckets
python -m claude_usage --window 5h
python -m claude_usage --window 7d

# Custom date range
python -m claude_usage --from 2026-04-01 --to 2026-04-09

# Output to file instead of opening browser
python -m claude_usage --output report.html --no-open

# Custom Claude data directory
python -m claude_usage --data-dir "D:\other\.claude"

# Set budget limits for gauge percentages
python -m claude_usage --limit-5h 600000 --limit-7d 4000000 --limit-sonnet-7d 2000000
```

## Dashboard

The generated HTML dashboard includes:

- **Budget gauges** - estimated usage against each billing bucket (5h, 7d, Sonnet-only 7d)
- **Model breakdown** - donut chart and daily stacked bar chart (Opus/Sonnet/Haiku)
- **Agent breakdown** - token usage per agent with model attribution
- **Skill usage** - invocation counts per skill
- **Project breakdown** - tokens per project
- **Session drill-down** - click a day to see individual sessions with agents, tokens, and model split

## How It Works

Reads JSONL session files from `~/.claude/projects/`. Each session file contains timestamped assistant messages with model name and token usage. Subagent metadata (`.meta.json`) maps child agent tokens to their agent type. Skill invocations are extracted from `Skill` tool-use entries.

## Development

```bash
pip install -e ".[dev]"
pytest
```
```

- [ ] **Step 2: Commit**

```
git add README.md
git commit -m "docs: add README with install, usage, and development instructions"
```

---

### Task 9: End-to-end smoke test

**Files:**
- Create: `tests/test_e2e.py`

- [ ] **Step 1: Write an end-to-end test**

```python
# tests/test_e2e.py
"""End-to-end test: parse sample data -> aggregate -> render HTML."""

from pathlib import Path

from claude_usage.aggregator import aggregate
from claude_usage.parser import parse_sessions
from claude_usage.renderer import render


class TestEndToEnd:
    def test_full_pipeline(self, sample_session_dir: Path, tmp_path: Path):
        """Parse sample fixtures, aggregate, render to HTML file."""
        sessions = parse_sessions(sample_session_dir)
        assert len(sessions) == 1

        result = aggregate(sessions)
        assert result.total_tokens > 0
        assert result.total_sessions == 1
        assert "opus" in result.by_model
        assert "general-purpose" in result.by_agent

        output_path = tmp_path / "dashboard.html"
        rendered = render(result, output_path=output_path, open_browser=False)
        assert rendered.exists()

        html = rendered.read_text(encoding="utf-8")
        assert "Chart" in html or "chart" in html
        assert "claude" in html.lower()

    def test_full_pipeline_with_limits(self, sample_session_dir: Path, tmp_path: Path):
        sessions = parse_sessions(sample_session_dir)
        result = aggregate(sessions)

        limits = {"limit_5h": 600000, "limit_7d": 4000000, "limit_sonnet_7d": 2000000}
        output_path = tmp_path / "dashboard-limits.html"
        rendered = render(result, output_path=output_path, open_browser=False, limits=limits)
        assert rendered.exists()

        html = rendered.read_text(encoding="utf-8")
        assert "600000" in html or "limit_5h" in html

    def test_empty_data(self, tmp_path: Path):
        sessions = parse_sessions(tmp_path)
        result = aggregate(sessions)
        assert result.total_tokens == 0

        output_path = tmp_path / "empty.html"
        rendered = render(result, output_path=output_path, open_browser=False)
        assert rendered.exists()
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: All tests across all files PASS.

- [ ] **Step 3: Commit**

```
git add tests/test_e2e.py
git commit -m "test: add end-to-end smoke tests for full pipeline

Tests parse -> aggregate -> render with sample fixtures, with budget
limits, and with empty data."
```

---

## Self-Review

**Spec coverage:**
- Models: MessageRecord, SessionRecord with total_tokens, model_short, duration_minutes
- Parser: JSONL reading, agent-setting, subagent meta.json, skill extraction, project hash decoding
- Aggregator: group by model/agent/skill/project/day, rolling window, date range filter
- Renderer: Jinja2 + Chart.js HTML generation, browser opening, budget limits
- Template: matches approved mockup layout
- CLI: --from/--to/--window/--output/--no-open/--data-dir/--limit-* flags
- pyproject.toml: package config with jinja2 dependency
- Tests: models, parser, aggregator, e2e
- README: usage instructions
- Separate repo: cbeaulieu-gt/claude-usage
- Future extensions explicitly excluded

**Placeholder scan:** No TBDs or TODOs. Task 6 template is the largest unit — implementer references the mockup HTML and template variable documentation.

**Type consistency:** MessageRecord, SessionRecord, AggregateResult field names consistent across all modules. model_short property used consistently. decode_project_hash interface stable.
