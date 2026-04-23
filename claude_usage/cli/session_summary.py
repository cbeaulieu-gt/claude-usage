"""Session-summary subcommand for claude-usage (stub).

Full implementation added in Phase 2. This file exists so that
__main__.py can import it without ImportError during the Phase 1
refactor tasks.
"""

from __future__ import annotations

import argparse

EXIT_OK = 0
EXIT_IO_FAILURE = 1
EXIT_NO_USER_TURNS = 2
EXIT_NOT_JSONL = 3


def build_parser(parent: argparse._SubParsersAction) -> argparse.ArgumentParser:
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
        "--max-actions", type=int, default=50,
        dest="max_actions",
        help=(
            "Soft cap on emitted actions. 0 disables the cap. "
            "Default: 50."
        ),
    )
    return p


def run(args: argparse.Namespace) -> int:
    """Execute the session-summary subcommand.

    Args:
        args: Parsed argument namespace from the session-summary subparser.

    Returns:
        Integer exit code.

    Raises:
        NotImplementedError: Always — full implementation pending Phase 2.
    """
    raise NotImplementedError(
        "session-summary is not yet implemented. "
        "Full implementation arrives in Phase 2."
    )
