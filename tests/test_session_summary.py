"""Tests for the session-summary subcommand."""

from __future__ import annotations

import dataclasses

import pytest

from claude_usage.cli.session_summary import (
    EXIT_IO_FAILURE,
    EXIT_NOT_JSONL,
    EXIT_NO_USER_TURNS,
    EXIT_OK,
    ActionRecord,
    SessionSummary,
)


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
