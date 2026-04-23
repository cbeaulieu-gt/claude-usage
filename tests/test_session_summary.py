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
