"""Session-summary subcommand: derive a structured recap from a transcript.

Walks a Claude Code transcript JSONL once, derives project, intent,
actions, and stoppedNaturally deterministically, and emits the result
as pretty-printed JSON to stdout.

Exit codes:
    0  Success — JSON written to stdout.
    1  IO failure — file missing, unreadable, or other OSError.
    2  No user turns — transcript has no external user entries.
    3  Not JSONL — file has content but every line fails json.loads.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_IO_FAILURE = 1
EXIT_NO_USER_TURNS = 2
EXIT_NOT_JSONL = 3

DEFAULT_MAX_ACTIONS: int = 50


@dataclass(frozen=True)
class ActionRecord:
    """A single classified tool-use action from a transcript.

    Attributes:
        type: Action category — one of "edit", "bash", "agent_dispatch",
            "mcp", or "other".
        raw_tool: The original tool name as it appears in the transcript.
        target: The primary subject of the action (file path, command,
            agent name, MCP server.method) — used as the collapse key.
        summary: A past-tense human-readable string suitable for display.
    """

    type: str
    raw_tool: str
    target: str
    summary: str


@dataclass(frozen=True)
class SessionSummary:
    """Derived session recap ready for JSON serialisation.

    Attributes:
        project: Repository or project name. Never empty; falls back to
            "unknown" when undetectable.
        intent: One-sentence description of what the session set out to do.
            Never empty; falls back to "Ran /<command>" for slash-command
            sessions or "Session on <project>" as a final fallback.
        actions: Chronologically ordered list of past-tense action strings,
            bounded by the max_actions cap. May be empty when the session
            contained no state-changing tool uses.
        stopped_naturally: True when the last assistant turn ended cleanly
            ("end_turn"), False on any definitive interrupt signal, or None
            when the signal is indeterminate (no assistant entries, or
            stop_reason absent/unrecognised).
    """

    project: str
    intent: str
    actions: list[str]
    stopped_naturally: bool | None


def _derive_project(entries: list[dict], slug_fallback: str | None = None) -> str:
    """Derive the project name from transcript entries.

    Strategy:
    1. First entry with a non-empty ``cwd`` field → ``Path(cwd).name``.
    2. Fallback: apply ``decode_project_hash`` to ``slug_fallback``
       (the transcript-directory name passed in by ``run()``).
    3. Final fallback: ``"unknown"``.

    Args:
        entries: Parsed JSONL entries in file order.
        slug_fallback: Optional project-slug string from the transcript
            directory name, used when no ``cwd`` field appears on any
            entry.

    Returns:
        A non-empty project name string.
    """
    from claude_usage.parser import decode_project_hash

    # Strategy 1: cwd field on any entry.
    for entry in entries:
        cwd = entry.get("cwd")
        if cwd and isinstance(cwd, str):
            name = Path(cwd).name
            if name:
                return name

    # Strategy 2: decode the project-hash slug supplied by the caller.
    if slug_fallback:
        decoded = decode_project_hash(slug_fallback)
        if decoded:
            return decoded

    # Strategy 3: final fallback.
    return "unknown"


def _derive_intent(entries: list[dict], project: str) -> str:
    """Derive the user's intent from the first external user turn.

    Args:
        entries: Parsed JSONL entries in file order.
        project: The already-derived project name (used as fallback).

    Returns:
        A non-empty intent string.
    """
    # Stub — returns hardcoded value matching happy_path fixture.
    # Replaced by real logic in Task 3.3.
    return (
        "Implement the session-summary subcommand for the /whats-next skill"
    )


def _collect_tool_uses(entries: list[dict]) -> list[ActionRecord]:
    """Classify all tool-use content blocks from assistant entries.

    Args:
        entries: Parsed JSONL entries in file order.

    Returns:
        Chronologically ordered list of ActionRecord instances, with
        consecutive records sharing (type, target) collapsed to one.
    """
    # Stub — returns hardcoded actions matching happy_path fixture.
    # Replaced by real logic in Tasks 3.4–3.6.
    return [
        ActionRecord(
            type="edit",
            raw_tool="Edit",
            target="claude_usage/cli/session_summary.py",
            summary="Edited claude_usage/cli/session_summary.py",
        ),
        ActionRecord(
            type="bash",
            raw_tool="Bash",
            target="uv run pytest tests/test_session_summary.py -x",
            summary=(
                "Ran `uv run pytest tests/test_session_summary.py -x`"
            ),
        ),
        ActionRecord(
            type="agent_dispatch",
            raw_tool="Agent",
            target="code-reviewer",
            summary="Dispatched code-reviewer sub-agent",
        ),
    ]


def _derive_stopped_naturally(
    entries: list[dict],
) -> bool | None:
    """Determine whether the session ended naturally.

    Args:
        entries: Parsed JSONL entries in file order.

    Returns:
        True if last assistant stop_reason == "end_turn" and no
        prevented-continuation marker was seen. False on a definitive
        interrupt signal. None when the signal is indeterminate.
    """
    # Stub — returns True matching happy_path fixture.
    # Replaced by real logic in Task 3.7 (next pass).
    return True


def _apply_max_actions_cap(
    records: list[ActionRecord],
    max_actions: int,
) -> list[str]:
    """Convert ActionRecords to summary strings, applying the cap.

    When max_actions > 0 and len(records) > max_actions, keep the first
    max_actions - 1 records and append a sentinel string describing how
    many were omitted.

    Args:
        records: Classified, collapsed ActionRecord list.
        max_actions: Cap value. 0 means no cap.

    Returns:
        List of past-tense action strings, bounded by the cap.
    """
    summaries = [r.summary for r in records]
    if max_actions == 0 or len(summaries) <= max_actions:
        return summaries
    kept = summaries[: max_actions - 1]
    dropped = len(summaries) - (max_actions - 1)
    kept.append(f"… ({dropped} additional actions omitted)")
    return kept


def build_session_summary(
    entries: list[dict],
    *,
    project_slug_fallback: str | None = None,
    max_actions: int = DEFAULT_MAX_ACTIONS,
) -> SessionSummary:
    """Build a SessionSummary from already-parsed transcript entries.

    Pure function — no I/O. The caller (run()) is responsible for reading
    the file and parsing JSONL; this function only classifies, derives,
    and renders.

    Args:
        entries: Parsed JSONL entries (already filtered for successfully
            decoded objects).
        project_slug_fallback: Optional transcript-directory slug passed
            through to ``_derive_project`` for the ``decode_project_hash``
            fallback when no ``cwd`` field appears on any entry.
        max_actions: Soft cap on emitted actions; 0 disables the cap.

    Returns:
        Fully-populated SessionSummary.
    """
    project = _derive_project(entries, project_slug_fallback)
    intent = _derive_intent(entries, project)
    records = _collect_tool_uses(entries)
    stopped_naturally = _derive_stopped_naturally(entries)
    action_strings = _apply_max_actions_cap(records, max_actions)

    return SessionSummary(
        project=project,
        intent=intent,
        actions=action_strings,
        stopped_naturally=stopped_naturally,
    )


def render_json(summary: SessionSummary) -> str:
    """Render a SessionSummary as a pretty-printed JSON string.

    Key order matches the output contract: project, intent, actions,
    stoppedNaturally. Uses json.dumps with indent=2 and ensure_ascii=False.

    Args:
        summary: The session summary to serialise.

    Returns:
        A JSON string ending with a trailing newline.

    Raises:
        NotImplementedError: Temporarily, until Phase 3 fills this in.
    """
    raise NotImplementedError("render_json — implemented in Phase 3")


def render_text(summary: SessionSummary) -> str:
    """Render a SessionSummary as a human-readable debug string.

    Output format::

        Project: <project>
        Intent: <intent>
        Stopped naturally: yes | no | unknown

        Actions:
          - <action 1>
          - <action 2>

    Args:
        summary: The session summary to render.

    Returns:
        A multi-line string suitable for writing to stdout.

    Raises:
        NotImplementedError: Temporarily, until Phase 3 fills this in.
    """
    raise NotImplementedError("render_text — implemented in Phase 3")


def build_parser(
    parent: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    """Register the 'session-summary' subparser and return it.

    Args:
        parent: The subparsers action from the top-level parser.

    Returns:
        The configured session-summary ArgumentParser.
    """
    p = parent.add_parser(
        "session-summary",
        help="Emit a deterministic JSON recap of a Claude Code transcript.",
    )
    p.add_argument(
        "--path",
        required=True,
        help="Path to the transcript JSONL file.",
    )
    p.add_argument(
        "--format", dest="output_format",
        choices=["json", "text"], default="json",
        help="Output format: 'json' (default) or 'text' (debug view).",
    )
    p.add_argument(
        "--max-actions", type=int, default=DEFAULT_MAX_ACTIONS,
        dest="max_actions",
        help=(
            "Soft cap on emitted actions. 0 disables the cap. "
            f"Default: {DEFAULT_MAX_ACTIONS}."
        ),
    )
    return p


def run(args: argparse.Namespace) -> int:
    """Execute the session-summary subcommand.

    Args:
        args: Parsed argument namespace from the session-summary subparser.

    Returns:
        Integer exit code (EXIT_OK, EXIT_IO_FAILURE, EXIT_NO_USER_TURNS,
        or EXIT_NOT_JSONL).

    Raises:
        NotImplementedError: Temporarily, until Phase 3 fills this in.
    """
    raise NotImplementedError(
        "session-summary is not yet implemented. "
        "Full implementation arrives in Phase 3."
    )
