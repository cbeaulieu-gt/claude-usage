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

    def test_action_classification_agent_dispatch_record_fields(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Agent tool_use classifies to ActionRecord with correct field values.

        Asserts all four ActionRecord fields explicitly:
        - type == "agent_dispatch"
        - raw_tool == "Agent"
        - target == subagent_type value from input
        - summary == "Dispatched <subagent_type> sub-agent"
        """
        from claude_usage.cli.session_summary import (
            ActionRecord,
            _collect_tool_uses,
        )

        # Minimal JSONL — one assistant entry with an Agent tool use.
        entry = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "tu-001",
                    "name": "Agent",
                    "input": {
                        "subagent_type": "code-writer",
                        "description": "Write the implementation",
                    },
                }],
                "model": "claude-sonnet-4-6",
                "stop_reason": "tool_use",
                "usage": {
                    "input_tokens": 40,
                    "output_tokens": 15,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
            "uuid": "a-001",
            "timestamp": "2026-04-20T09:00:01.000Z",
            "sessionId": "sess-agent",
        }
        records = _collect_tool_uses([entry])

        assert len(records) == 1
        assert records[0] == ActionRecord(
            type="agent_dispatch",
            raw_tool="Agent",
            target="code-writer",
            summary="Dispatched code-writer sub-agent",
        )

    def test_action_classification_mcp_plugin_scoped(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Plugin-scoped MCP name normalizes to 'github.create_issue'.

        Raw: mcp__plugin_github_github__create_issue
        Expected target: "github.create_issue"
        Expected summary: "Called `github.create_issue` (MCP)"
        """
        from claude_usage.cli.session_summary import (
            ActionRecord,
            _collect_tool_uses,
        )

        raw_name = "mcp__plugin_github_github__create_issue"
        entry = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "tu-001",
                    "name": raw_name,
                    "input": {"title": "Test issue", "body": "body"},
                }],
                "model": "claude-sonnet-4-6",
                "stop_reason": "tool_use",
                "usage": {
                    "input_tokens": 60,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
            "uuid": "a-001",
            "timestamp": "2026-04-20T09:00:01.000Z",
            "sessionId": "sess-mcp",
        }
        records = _collect_tool_uses([entry])

        assert len(records) == 1
        assert records[0] == ActionRecord(
            type="mcp",
            raw_tool=raw_name,
            target="github.create_issue",
            summary="Called `github.create_issue` (MCP)",
        )

    def test_action_classification_mcp_direct(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Direct MCP name normalizes to 'azure.storage'.

        Raw: mcp__azure__storage
        Expected target: "azure.storage"
        Expected summary: "Called `azure.storage` (MCP)"
        """
        from claude_usage.cli.session_summary import (
            ActionRecord,
            _collect_tool_uses,
        )

        raw_name = "mcp__azure__storage"
        entry = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "tu-001",
                    "name": raw_name,
                    "input": {"container": "my-bucket"},
                }],
                "model": "claude-sonnet-4-6",
                "stop_reason": "tool_use",
                "usage": {
                    "input_tokens": 40,
                    "output_tokens": 10,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
            "uuid": "a-001",
            "timestamp": "2026-04-20T09:00:01.000Z",
            "sessionId": "sess-mcp-direct",
        }
        records = _collect_tool_uses([entry])

        assert len(records) == 1
        assert records[0] == ActionRecord(
            type="mcp",
            raw_tool=raw_name,
            target="azure.storage",
            summary="Called `azure.storage` (MCP)",
        )

    def test_action_classification_mcp_malformed_falls_back_to_other(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Malformed MCP name (no second __ separator) falls back to 'other'.

        Raw: mcp__plugin_broken
        The name starts with 'mcp__' and 'plugin_' but has no '__' after
        the plugin segment, so normalization returns None. The forward-compat
        fallback produces an 'other'-type ActionRecord.
        """
        from claude_usage.cli.session_summary import (
            ActionRecord,
            _collect_tool_uses,
        )

        raw_name = "mcp__plugin_broken"
        entry = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "tu-001",
                    "name": raw_name,
                    "input": {},
                }],
                "model": "claude-sonnet-4-6",
                "stop_reason": "tool_use",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
            "uuid": "a-001",
            "timestamp": "2026-04-20T09:00:01.000Z",
            "sessionId": "sess-mcp-bad",
        }
        records = _collect_tool_uses([entry])

        assert len(records) == 1
        assert records[0] == ActionRecord(
            type="other",
            raw_tool=raw_name,
            target=raw_name,
            summary=f"Used {raw_name} tool",
        )

    def test_action_classification_mcp_collapse_unifies_forms(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Plugin-scoped and direct MCP forms for the same endpoint normalize
        to an identical target string, so consecutive occurrences collapse.

        Two consecutive tool uses — one plugin-scoped, one direct — both
        resolve to target "github.create_issue". After _collect_tool_uses
        (which includes collapse), only one ActionRecord is returned.
        """
        from claude_usage.cli.session_summary import _collect_tool_uses

        plugin_entry = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "tu-001",
                    "name": "mcp__plugin_github_github__create_issue",
                    "input": {"title": "First", "body": "b1"},
                }],
                "model": "claude-sonnet-4-6",
                "stop_reason": "tool_use",
                "usage": {
                    "input_tokens": 60,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
            "uuid": "a-001",
            "timestamp": "2026-04-20T09:00:01.000Z",
            "sessionId": "sess-mcp-collapse",
        }
        direct_entry = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "tu-002",
                    "name": "mcp__github__create_issue",
                    "input": {"title": "Second", "body": "b2"},
                }],
                "model": "claude-sonnet-4-6",
                "stop_reason": "tool_use",
                "usage": {
                    "input_tokens": 65,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
            "uuid": "a-002",
            "timestamp": "2026-04-20T09:00:02.000Z",
            "sessionId": "sess-mcp-collapse",
        }
        records = _collect_tool_uses([plugin_entry, direct_entry])

        # Both normalize to the same target → collapse reduces to one.
        assert len(records) == 1

    def test_action_classification_skip_set_is_complete(self) -> None:
        """The SKIPPED_TOOLS module constant contains all seven skip-list members.

        This test is a contract assertion on the constant itself. If a new
        tool is added to or removed from the skip list in the spec, this
        test must be updated in lockstep.
        """
        from claude_usage.cli.session_summary import SKIPPED_TOOLS

        expected = frozenset({
            "Read",
            "Grep",
            "Glob",
            "Skill",
            "TodoWrite",
            "WebFetch",
            "WebSearch",
        })
        assert SKIPPED_TOOLS == expected

    def test_action_classification_skips_mix_with_edit(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Seven skipped tool uses plus one Edit produces exactly one action.

        Verifies that the skip-set check fires before any other dispatch,
        that the Edit is still classified after skipped tools, and that the
        resulting action list has exactly one entry.
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
                    "content": "Look at things, then edit one.",
                },
                "uuid": "u-001",
                "timestamp": "2026-04-20T09:00:00.000Z",
                "sessionId": "sess-mix",
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
                    "stop_reason": "tool_use",
                    "usage": {
                        "input_tokens": 20,
                        "output_tokens": 5,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                    },
                },
                "uuid": f"a-{i:03d}",
                "timestamp": f"2026-04-20T09:00:{i:02d}.000Z",
                "sessionId": "sess-mix",
            }))
        # One Edit at the end — must survive into the action list.
        lines.append(json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "tu-008",
                    "name": "Edit",
                    "input": {
                        "file_path": "src/result.py",
                        "old_string": "x",
                        "new_string": "y",
                    },
                }],
                "model": "claude-sonnet-4-6",
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 5,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
            "uuid": "a-008",
            "timestamp": "2026-04-20T09:00:08.000Z",
            "sessionId": "sess-mix",
        }))

        fixture = tmp_path / "skip_mix.jsonl"
        fixture.write_text("\n".join(lines) + "\n", encoding="utf-8")

        summary = build_session_summary(_parse_fixture(fixture))
        assert len(summary.actions) == 1
        assert summary.actions[0] == "Edited src/result.py"

    def test_action_classification_unknown_tool_defaults_to_other(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """An unrecognised tool name produces an 'other'-type ActionRecord.

        This verifies the forward-compatibility catch-all: any tool that
        does not match the skip list, edit family, bash family, Agent, or
        MCP prefix produces:
        - type == "other"
        - raw_tool == the original tool name
        - target == the original tool name
        - summary == "Used <tool_name> tool"
        """
        from claude_usage.cli.session_summary import (
            ActionRecord,
            _collect_tool_uses,
        )

        entry = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "tu-001",
                    "name": "BrandNewTool",
                    "input": {"some_param": "some_value"},
                }],
                "model": "claude-sonnet-4-6",
                "stop_reason": "tool_use",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
            "uuid": "a-001",
            "timestamp": "2026-04-20T09:00:01.000Z",
            "sessionId": "sess-unknown",
        }
        records = _collect_tool_uses([entry])

        assert len(records) == 1
        assert records[0] == ActionRecord(
            type="other",
            raw_tool="BrandNewTool",
            target="BrandNewTool",
            summary="Used BrandNewTool tool",
        )


class TestCollapseConsecutive:
    """Tests for _collapse_consecutive semantics."""

    def test_consecutive_edits_collapse(self) -> None:
        """Three consecutive Edits to the same file collapse to one action.

        Uses the consecutive_edits_same_file.jsonl fixture from Phase 2
        which has three Edit tool-use blocks all targeting
        'claude_usage/parser.py'. After _collect_tool_uses (which calls
        _collapse_consecutive internally), only one ActionRecord remains.
        """
        from pathlib import Path

        from claude_usage.cli.session_summary import build_session_summary

        fixture = Path(
            "tests/fixtures/session_summaries/"
            "consecutive_edits_same_file.jsonl"
        )
        summary = build_session_summary(_parse_fixture(fixture))

        assert len(summary.actions) == 1
        assert summary.actions[0] == "Edited claude_usage/parser.py"

    def test_non_adjacent_edits_do_not_collapse(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Edits interleaved by a different file are not collapsed.

        Sequence: Edit A → Edit B → Edit A again.
        The two Edit A calls are non-adjacent, so all three records are
        preserved — chronological order and narrative sense are maintained.
        """
        import json

        from claude_usage.cli.session_summary import build_session_summary

        def _edit_entry(uid: str, file_path: str, seq: int) -> dict:
            """Build one assistant entry with a single Edit tool use."""
            return {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{
                        "type": "tool_use",
                        "id": f"tu-{seq:03d}",
                        "name": "Edit",
                        "input": {
                            "file_path": file_path,
                            "old_string": f"old{seq}",
                            "new_string": f"new{seq}",
                        },
                    }],
                    "model": "claude-sonnet-4-6",
                    "stop_reason": (
                        "end_turn" if seq == 3 else "tool_use"
                    ),
                    "usage": {
                        "input_tokens": 30,
                        "output_tokens": 10,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                    },
                },
                "uuid": uid,
                "timestamp": f"2026-04-20T09:00:0{seq}.000Z",
                "sessionId": "sess-nonadj",
            }

        user_entry = {
            "type": "user",
            "message": {
                "role": "user",
                "content": "Edit A, then B, then A again.",
            },
            "uuid": "u-001",
            "timestamp": "2026-04-20T09:00:00.000Z",
            "sessionId": "sess-nonadj",
            "userType": "external",
            "cwd": "/home/user/myproject",
        }

        lines = [
            json.dumps(user_entry),
            json.dumps(_edit_entry("a-001", "src/a.py", 1)),
            json.dumps(_edit_entry("a-002", "src/b.py", 2)),
            json.dumps(_edit_entry("a-003", "src/a.py", 3)),
        ]
        fixture = tmp_path / "non_adjacent.jsonl"
        fixture.write_text("\n".join(lines) + "\n", encoding="utf-8")

        summary = build_session_summary(_parse_fixture(fixture))

        # All three edits must be present — none collapsed.
        assert len(summary.actions) == 3
        assert summary.actions[0] == "Edited src/a.py"
        assert summary.actions[1] == "Edited src/b.py"
        assert summary.actions[2] == "Edited src/a.py"
