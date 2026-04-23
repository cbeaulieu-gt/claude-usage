"""Tests for the session-summary subcommand."""

from __future__ import annotations

import dataclasses
import json as _json
from pathlib import Path as _Path

import pytest

from claude_usage.cli.session_summary import (
    EXIT_IO_FAILURE,
    EXIT_NOT_JSONL,
    EXIT_NO_USER_TURNS,
    EXIT_OK,
    ActionRecord,
    SessionSummary,
)


def _parse_fixture(fixture_path: _Path) -> list[dict]:
    """Read and parse a JSONL fixture into a list of dicts.

    Skips blank lines and lines that fail json.loads, matching the
    same tolerance as read_transcript in session_summary.py.

    Args:
        fixture_path: Path to a JSONL fixture file.

    Returns:
        List of successfully parsed entry dicts in file order.
    """
    entries: list[dict] = []
    with fixture_path.open(encoding="utf-8") as fh:
        for raw in fh:
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                entries.append(_json.loads(stripped))
            except _json.JSONDecodeError:
                pass
    return entries


class TestDataclasses:
    """Verify ActionRecord and SessionSummary structural contracts."""

    def test_session_summary_is_frozen(self) -> None:
        """SessionSummary must be immutable (frozen dataclass).

        Attempting to set any attribute after construction must raise
        FrozenInstanceError.
        """
        summary = SessionSummary(
            project="x",
            intent="y",
            actions=[],
            stopped_naturally=None,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            summary.project = "z"  # type: ignore[misc]

    def test_action_record_is_frozen(self) -> None:
        """ActionRecord must be immutable (frozen dataclass)."""
        record = ActionRecord(
            type="edit",
            raw_tool="Edit",
            target="foo.py",
            summary="Edited foo.py",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            record.target = "bar.py"  # type: ignore[misc]

    def test_exit_code_constants(self) -> None:
        """Exit-code constants must have the expected integer values."""
        assert EXIT_OK == 0
        assert EXIT_IO_FAILURE == 1
        assert EXIT_NO_USER_TURNS == 2
        assert EXIT_NOT_JSONL == 3


class TestBuildSessionSummary:
    """Tests for build_session_summary and the full derivation pipeline."""

    def test_happy_path_emits_contract(self) -> None:
        """build_session_summary on happy_path.jsonl returns a correctly
        populated SessionSummary.

        Asserts:
        - project == "claude-usage" (from cwd field)
        - intent contains the user's first sentence
        - actions is a non-empty list of strings
        - stopped_naturally is True (final stop_reason == "end_turn")
        """
        from pathlib import Path

        from claude_usage.cli.session_summary import build_session_summary

        fixture = Path(
            "tests/fixtures/session_summaries/happy_path.jsonl"
        )
        entries = _parse_fixture(fixture)
        summary = build_session_summary(
            entries,
            project_slug_fallback=fixture.parent.name,
        )

        assert summary.project == "claude-usage"
        assert "session-summary" in summary.intent.lower()
        assert isinstance(summary.actions, list)
        assert len(summary.actions) > 0
        assert summary.stopped_naturally is True

    def test_project_derived_from_cwd_field(self) -> None:
        """project is the basename of the cwd field on the first entry
        that has one.

        The happy_path fixture has cwd="/home/user/claude-usage" so the
        derived project name must be "claude-usage".
        """
        from pathlib import Path

        from claude_usage.cli.session_summary import build_session_summary

        fixture = Path(
            "tests/fixtures/session_summaries/happy_path.jsonl"
        )
        summary = build_session_summary(
            _parse_fixture(fixture),
            project_slug_fallback=fixture.parent.name,
        )
        assert summary.project == "claude-usage"

    def test_project_falls_back_to_unknown(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """When no cwd is present and the path slug is not decodable,
        project falls back to "unknown".
        """
        import json

        from claude_usage.cli.session_summary import build_session_summary

        # Fixture with no cwd field anywhere and a non-project-hash path.
        fixture = tmp_path / "no_cwd.jsonl"
        fixture.write_text(
            json.dumps({
                "type": "user",
                "message": {
                    "role": "user",
                    "content": "Hello with no cwd.",
                },
                "uuid": "u-001",
                "timestamp": "2026-04-20T09:00:00.000Z",
                "sessionId": "sess-nocwd",
                "userType": "external",
            }) + "\n",
            encoding="utf-8",
        )
        # Pass None as slug_fallback to exercise the final "unknown" path.
        summary = build_session_summary(
            _parse_fixture(fixture),
            project_slug_fallback=None,
        )
        assert summary.project == "unknown"

    def test_intent_plain_text_user_turn(self, tmp_path: pytest.TempPathFactory) -> None:
        """A plain-text user turn returns the first sentence as intent."""
        import json

        from claude_usage.cli.session_summary import build_session_summary

        fixture = tmp_path / "plain_text.jsonl"
        fixture.write_text(
            json.dumps({
                "type": "user",
                "message": {
                    "role": "user",
                    "content": (
                        "Implement the login feature. "
                        "Make it work with OAuth."
                    ),
                },
                "uuid": "u-001",
                "timestamp": "2026-04-20T09:00:00.000Z",
                "sessionId": "sess-plain",
                "userType": "external",
                "cwd": "/home/user/myproject",
            }) + "\n",
            encoding="utf-8",
        )
        summary = build_session_summary(_parse_fixture(fixture))
        assert summary.intent == "Implement the login feature"

    def test_intent_strips_system_reminder_wrapper(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """system-reminder XML wrapper is stripped; surviving text becomes intent."""
        import json

        from claude_usage.cli.session_summary import build_session_summary

        fixture = tmp_path / "reminder.jsonl"
        content = (
            "<system-reminder>You are an assistant.</system-reminder>"
            "Fix the parser bug in parser.py. It crashes on empty input."
        )
        fixture.write_text(
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": content},
                "uuid": "u-001",
                "timestamp": "2026-04-20T09:00:00.000Z",
                "sessionId": "sess-remind",
                "userType": "external",
                "cwd": "/home/user/myproject",
            }) + "\n",
            encoding="utf-8",
        )
        summary = build_session_summary(_parse_fixture(fixture))
        assert summary.intent == "Fix the parser bug in parser.py"

    def test_intent_falls_back_for_slash_command_only(self) -> None:
        """Pure slash-command session produces intent 'Ran /project-review'."""
        from pathlib import Path

        from claude_usage.cli.session_summary import build_session_summary

        fixture = Path(
            "tests/fixtures/session_summaries/slash_command_only.jsonl"
        )
        summary = build_session_summary(_parse_fixture(fixture))
        assert summary.intent == "Ran /project-review"

    def test_intent_empty_session_fallback(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """When there is a user turn but content is entirely whitespace after
        stripping, intent falls back to 'Session on <project>'.
        """
        import json

        from claude_usage.cli.session_summary import build_session_summary

        fixture = tmp_path / "empty_intent.jsonl"
        fixture.write_text(
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "   "},
                "uuid": "u-001",
                "timestamp": "2026-04-20T09:00:00.000Z",
                "sessionId": "sess-empty-intent",
                "userType": "external",
                "cwd": "/home/user/myproject",
            }) + "\n",
            encoding="utf-8",
        )
        summary = build_session_summary(_parse_fixture(fixture))
        assert summary.intent == "Session on myproject"


class TestToolClassification:
    """Tests for _classify_tool_use and _collect_tool_uses."""

    def test_action_classification_edit_tools(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Edit, Write, and NotebookEdit each produce an 'edit' ActionRecord.

        Each tool-use block should produce:
        - type == "edit"
        - raw_tool == the original tool name
        - target == the file_path input value
        - summary starting with "Edited "
        """
        import json

        from claude_usage.cli.session_summary import build_session_summary

        def _make_tool_use(
            uid: str, name: str, path: str
        ) -> dict:
            return {
                "type": "tool_use",
                "id": uid,
                "name": name,
                "input": {"file_path": path, "old_string": "a", "new_string": "b"},
            }

        fixture = tmp_path / "edit_tools.jsonl"
        lines = [
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "Edit three files."},
                "uuid": "u-001",
                "timestamp": "2026-04-20T09:00:00.000Z",
                "sessionId": "sess-edit",
                "userType": "external",
                "cwd": "/home/user/myproject",
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        _make_tool_use("tu-001", "Edit", "src/a.py"),
                    ],
                    "model": "claude-sonnet-4-6",
                    "stop_reason": "tool_use",
                    "usage": {"input_tokens": 50, "output_tokens": 10,
                              "cache_creation_input_tokens": 0,
                              "cache_read_input_tokens": 0},
                },
                "uuid": "a-001",
                "timestamp": "2026-04-20T09:00:01.000Z",
                "sessionId": "sess-edit",
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        _make_tool_use("tu-002", "Write", "src/b.py"),
                    ],
                    "model": "claude-sonnet-4-6",
                    "stop_reason": "tool_use",
                    "usage": {"input_tokens": 50, "output_tokens": 10,
                              "cache_creation_input_tokens": 0,
                              "cache_read_input_tokens": 0},
                },
                "uuid": "a-002",
                "timestamp": "2026-04-20T09:00:02.000Z",
                "sessionId": "sess-edit",
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        _make_tool_use("tu-003", "NotebookEdit", "notebook.ipynb"),
                    ],
                    "model": "claude-sonnet-4-6",
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 50, "output_tokens": 10,
                              "cache_creation_input_tokens": 0,
                              "cache_read_input_tokens": 0},
                },
                "uuid": "a-003",
                "timestamp": "2026-04-20T09:00:03.000Z",
                "sessionId": "sess-edit",
            }),
        ]
        fixture.write_text("\n".join(lines) + "\n", encoding="utf-8")

        summary = build_session_summary(_parse_fixture(fixture))

        assert len(summary.actions) == 3
        assert summary.actions[0] == "Edited src/a.py"
        assert summary.actions[1] == "Edited src/b.py"
        assert summary.actions[2] == "Edited notebook.ipynb"

    def test_action_classification_skips_reads(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Read, Grep, Glob, WebFetch, WebSearch, Skill, and TodoWrite
        tool uses are skipped — they are info-gathering or ceremony.

        Result: actions list is empty.
        """
        import json

        from claude_usage.cli.session_summary import build_session_summary

        skip_tools = [
            ("Read", {"file_path": "foo.py"}),
            ("Grep", {"pattern": "def ", "path": "."}),
            ("Glob", {"pattern": "**/*.py"}),
            ("WebFetch", {"url": "https://example.com"}),
            ("WebSearch", {"query": "python"}),
            ("Skill", {"skill": "python"}),
            ("TodoWrite", {"todos": []}),
        ]

        lines = [
            json.dumps({
                "type": "user",
                "message": {
                    "role": "user",
                    "content": "Look at things but do not change them.",
                },
                "uuid": "u-001",
                "timestamp": "2026-04-20T09:00:00.000Z",
                "sessionId": "sess-skip",
                "userType": "external",
                "cwd": "/home/user/myproject",
            }),
        ]
        for i, (tool_name, inp) in enumerate(skip_tools, start=1):
            lines.append(json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{
                        "type": "tool_use",
                        "id": f"tu-{i:03d}",
                        "name": tool_name,
                        "input": inp,
                    }],
                    "model": "claude-sonnet-4-6",
                    "stop_reason": (
                        "tool_use" if i < len(skip_tools) else "end_turn"
                    ),
                    "usage": {"input_tokens": 20, "output_tokens": 5,
                              "cache_creation_input_tokens": 0,
                              "cache_read_input_tokens": 0},
                },
                "uuid": f"a-{i:03d}",
                "timestamp": f"2026-04-20T09:00:{i:02d}.000Z",
                "sessionId": "sess-skip",
            }))

        fixture = tmp_path / "skip_tools.jsonl"
        fixture.write_text("\n".join(lines) + "\n", encoding="utf-8")

        summary = build_session_summary(_parse_fixture(fixture))
        assert summary.actions == []

    def test_action_classification_bash_tools(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Bash and PowerShell tool uses produce 'bash' ActionRecords.

        Three cases:
        (a) Short command renders fully in summary.
        (b) Command > 80 chars (after whitespace-collapse) is truncated
            with a unicode ellipsis suffix.
        (c) PowerShell tool name maps to the same "bash" action type.
        """
        import json

        from claude_usage.cli.session_summary import build_session_summary

        short_cmd = "uv run pytest -x"
        long_cmd = (
            "uv run pytest tests/ --tb=short --no-header "
            "-q --disable-warnings --timeout=60 "
            "tests/test_session_summary.py tests/test_cli_subcommands.py "
            "tests/test_dashboard_snapshot.py"
        )
        # Whitespace-collapsed long_cmd will exceed 80 chars.
        ps_cmd = "Get-ChildItem -Recurse *.py"

        lines = [
            json.dumps({
                "type": "user",
                "message": {
                    "role": "user",
                    "content": "Run some bash commands.",
                },
                "uuid": "u-001",
                "timestamp": "2026-04-20T09:00:00.000Z",
                "sessionId": "sess-bash",
                "userType": "external",
                "cwd": "/home/user/myproject",
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{
                        "type": "tool_use",
                        "id": "tu-001",
                        "name": "Bash",
                        "input": {
                            "command": short_cmd,
                            "description": "Run tests",
                        },
                    }],
                    "model": "claude-sonnet-4-6",
                    "stop_reason": "tool_use",
                    "usage": {"input_tokens": 30, "output_tokens": 10,
                              "cache_creation_input_tokens": 0,
                              "cache_read_input_tokens": 0},
                },
                "uuid": "a-001",
                "timestamp": "2026-04-20T09:00:01.000Z",
                "sessionId": "sess-bash",
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{
                        "type": "tool_use",
                        "id": "tu-002",
                        "name": "Bash",
                        "input": {
                            "command": long_cmd,
                            "description": "Run many tests",
                        },
                    }],
                    "model": "claude-sonnet-4-6",
                    "stop_reason": "tool_use",
                    "usage": {"input_tokens": 30, "output_tokens": 10,
                              "cache_creation_input_tokens": 0,
                              "cache_read_input_tokens": 0},
                },
                "uuid": "a-002",
                "timestamp": "2026-04-20T09:00:02.000Z",
                "sessionId": "sess-bash",
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{
                        "type": "tool_use",
                        "id": "tu-003",
                        "name": "PowerShell",
                        "input": {
                            "command": ps_cmd,
                        },
                    }],
                    "model": "claude-sonnet-4-6",
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 30, "output_tokens": 10,
                              "cache_creation_input_tokens": 0,
                              "cache_read_input_tokens": 0},
                },
                "uuid": "a-003",
                "timestamp": "2026-04-20T09:00:03.000Z",
                "sessionId": "sess-bash",
            }),
        ]
        fixture = tmp_path / "bash_tools.jsonl"
        fixture.write_text("\n".join(lines) + "\n", encoding="utf-8")

        summary = build_session_summary(_parse_fixture(fixture))

        assert len(summary.actions) == 3

        # (a) Short command — no truncation.
        assert summary.actions[0] == f"Ran `{short_cmd}`"

        # (b) Long command — truncated at 80 chars with ellipsis.
        collapsed = " ".join(long_cmd.split())
        expected_long = f"Ran `{collapsed[:80]}…`"
        assert summary.actions[1] == expected_long

        # (c) PowerShell uses same "bash" type.
        assert summary.actions[2] == f"Ran `{ps_cmd}`"

    def test_action_classification_agent_dispatch(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Agent tool use produces an 'agent_dispatch' ActionRecord."""
        import json

        from claude_usage.cli.session_summary import build_session_summary

        fixture = tmp_path / "agent_dispatch.jsonl"
        fixture.write_text(
            "\n".join([
                json.dumps({
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": "Review the code.",
                    },
                    "uuid": "u-001",
                    "timestamp": "2026-04-20T09:00:00.000Z",
                    "sessionId": "sess-agent",
                    "userType": "external",
                    "cwd": "/home/user/myproject",
                }),
                json.dumps({
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{
                            "type": "tool_use",
                            "id": "tu-001",
                            "name": "Agent",
                            "input": {
                                "subagent_type": "code-reviewer",
                                "description": "Review session_summary.py",
                            },
                        }],
                        "model": "claude-sonnet-4-6",
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 40, "output_tokens": 15,
                                  "cache_creation_input_tokens": 0,
                                  "cache_read_input_tokens": 0},
                    },
                    "uuid": "a-001",
                    "timestamp": "2026-04-20T09:00:01.000Z",
                    "sessionId": "sess-agent",
                }),
            ]) + "\n",
            encoding="utf-8",
        )
        summary = build_session_summary(_parse_fixture(fixture))
        assert len(summary.actions) == 1
        assert summary.actions[0] == "Dispatched code-reviewer sub-agent"
