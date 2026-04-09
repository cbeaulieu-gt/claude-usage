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
from claude_usage.skill_tracking import parse_skill_tracking


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
