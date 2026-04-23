# Session-Summary Subcommand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-22-session-summary-design.md`
**Tracks:** https://github.com/cbeaulieu-gt/claude-usage/issues/19
**Goal:** Add a `session-summary` subcommand emitting deterministic JSON session recaps for `/whats-next`, and refactor the CLI to argparse subparsers without behavior-regressing the dashboard.
**Architecture:** Introduce `claude_usage/cli/` subpackage with per-subcommand modules. `__main__.py` becomes a ~30-line subparser dispatcher. `session_summary.py` walks a transcript JSONL once, derives `project`, `intent`, `actions`, `stoppedNaturally` deterministically, and emits pretty-printed JSON to stdout.
**Tech Stack:** Python 3.11+, stdlib (argparse, dataclasses, json, pathlib), pytest, ruff, uv.

---

## Naming Conventions & Cross-Reference

All identifiers below are frozen. Later passes must use these exact names.

### Dataclasses (both live in `claude_usage/cli/session_summary.py`)

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionRecord:
    """A single classified tool-use action from a transcript."""

    type: str       # "edit" | "bash" | "agent_dispatch" | "mcp" | "other"
    raw_tool: str   # original tool name from the transcript
    target: str     # path, command, agent name — used for collapse keying
    summary: str    # past-tense human-readable string


@dataclass(frozen=True)
class SessionSummary:
    """Derived session recap emitted as JSON."""

    project: str
    intent: str
    actions: list[str]
    stopped_naturally: bool | None  # JSON: true | false | null
```

JSON key mapping: `stopped_naturally` (Python) → `stoppedNaturally` (JSON output).

### Public functions in `claude_usage/cli/session_summary.py`

| Name | Signature |
|---|---|
| `build_session_summary` | `(entries: list[dict], *, project_slug_fallback: str \| None = None, max_actions: int = DEFAULT_MAX_ACTIONS) -> SessionSummary` |
| `render_json` | `(summary: SessionSummary) -> str` |
| `render_text` | `(summary: SessionSummary) -> str` |

### Exit code constants (defined at module level in `session_summary.py`)

```python
EXIT_OK = 0
EXIT_IO_FAILURE = 1
EXIT_NO_USER_TURNS = 2
EXIT_NOT_JSONL = 3
```

### Test identifiers

- **Test file:** `tests/test_session_summary.py`
- **Test IDs** (match spec's minimum test matrix exactly):
  - `test_happy_path_emits_contract`
  - `test_missing_file_exits_1`
  - `test_empty_session_exits_2`
  - `test_malformed_file_exits_3`
  - `test_existing_dashboard_unchanged`
  - `test_action_classification_skips_reads`
  - `test_consecutive_edits_collapse`
  - `test_intent_falls_back_for_slash_command_only`
  - `test_stopped_naturally_false_on_max_tokens`
  - `test_stopped_naturally_false_on_prevented_continuation`
  - `test_stopped_naturally_null_on_no_assistant_turns`
  - `test_stopped_naturally_null_on_missing_stop_reason`
  - `test_actions_truncated_at_default_cap`
  - `test_actions_respects_max_actions_override`
  - `test_actions_cap_zero_disables_truncation`
  - `test_stdout_on_error_is_empty`
  - `test_stdout_on_success_is_pure_json`

### Paths & fixture locations

| Item | Path |
|---|---|
| Fixture directory | `tests/fixtures/session_summaries/` |
| Dashboard baseline snapshot | `tests/fixtures/dashboard_snapshot_pre_refactor.json` |
| Sanitizer helper | `tests/fixtures/sanitize_transcript.py` |
| Dashboard baseline input fixture tree | `tests/fixtures/session_summaries/dashboard_baseline_input/` |

### Shell & tooling conventions

- Shell: Bash (POSIX) in all steps.
- Run tests with: `uv run pytest`; single failing test: `uv run pytest -x`.
- Lint: `uv run ruff check .`
- Format check: `uv run ruff format --check .`
- Conventional-commit footer for all tasks: `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`
- Issue reference in commits: `part of #19` (plain text, no backticks).

---

## File Structure

### Create

| File | Responsibility |
|---|---|
| `claude_usage/cli/__init__.py` | Empty package marker; makes `claude_usage.cli` importable. |
| `claude_usage/cli/dashboard.py` | Contains all business logic moved verbatim from `__main__.py`, wrapped in a `run(args: argparse.Namespace) -> int` entry point callable by the dispatcher. |
| `claude_usage/cli/session_summary.py` | New subcommand: `ActionRecord` and `SessionSummary` dataclasses, all derivation functions, `render_json`, `render_text`, exit code constants, and `run(args: argparse.Namespace) -> int` entry point. |
| `tests/test_session_summary.py` | All 17 tests from the spec's minimum test matrix. |
| `tests/fixtures/session_summaries/` | JSONL fixture files used by the test suite (created in Phase 2). |
| `tests/fixtures/sanitize_transcript.py` | Standalone helper for sanitizing real transcripts into reproducible committed fixtures. |
| `tests/fixtures/dashboard_snapshot_pre_refactor.json` | Byte-identical capture of `claude-usage --format json` on `main` before the refactor lands; used by the Phase 1 snapshot regression test. |

### Modify

| File | Change |
|---|---|
| `claude_usage/__main__.py` | Rewritten to ~30 lines: top-level argparse with two subparsers (`dashboard`, `session-summary`), dispatching to `cli.dashboard.run` or `cli.session_summary.run`. |
| `README.md` | Document the new `session-summary` subcommand usage and the migration from bare `claude-usage --format json` to `claude-usage dashboard --format json`. |
| `pyproject.toml` | Update only if the `[project.scripts]` entry point binding needs changing after the refactor; otherwise leave untouched. |

---

## Phase 0 — Pre-Refactor Baseline

**Purpose:** Capture a byte-identical `claude-usage --format json` snapshot on `main` BEFORE any
refactor lands. This makes the Phase 1 regression test mechanical rather than aspirational,
and resolves Open Question #2 from the spec.

### Task 0: Capture Dashboard JSON Baseline

**Files:**
- Create: `tests/fixtures/session_summaries/dashboard_baseline_input/` (minimal fake `.claude` tree)
- Create: `tests/fixtures/dashboard_snapshot_pre_refactor.json`

- [x] **Step 1: Construct the minimal input fixture tree.**

  Create the directory structure that mimics what `parse_sessions` expects under a `.claude` data
  directory. The current `__main__.py` passes `args.data_dir` (a `Path`) to `parse_sessions`. The
  fixture tree must have at least one project with one JSONL file containing a parseable assistant
  message with usage data.

  Directory layout to create:

  ```
  tests/fixtures/session_summaries/dashboard_baseline_input/
  └── projects/
      └── fake-project-abc123/
          └── session-001.jsonl
  ```

  Contents of `session-001.jsonl` (two lines — each line is one JSON object):

  ```jsonl
  {"type":"user","message":{"role":"user","content":"Hello"},"uuid":"u-001","timestamp":"2026-03-01T10:00:00.000Z","sessionId":"sess-001","userType":"external"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hi there."}],"model":"claude-sonnet-4-6","stop_reason":"end_turn","usage":{"input_tokens":10,"output_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-001","timestamp":"2026-03-01T10:00:01.000Z","sessionId":"sess-001"}
  ```

  Write this file verbatim. The `fake-project-abc123` slug does not need to decode to a real path;
  `parse_sessions` reads the JSONL content, not the directory name.

- [x] **Step 2: Capture the baseline snapshot.**

  With `main` checked out (no refactor changes present), run:

  ```bash
  uv run claude-usage --from 2026-01-01 --to 2026-12-31 --format json \
      --data-dir tests/fixtures/session_summaries/dashboard_baseline_input \
      > tests/fixtures/dashboard_snapshot_pre_refactor.json
  ```

  Verify the output file is non-empty:

  ```bash
  wc -c tests/fixtures/dashboard_snapshot_pre_refactor.json
  ```

  Expected: output file contains valid JSON with at least the keys `generated_at`, `total_tokens`,
  `total_sessions`.

  > **Note on `--data-dir`:** The current `__main__.py` exposes `--data-dir` as a flag (line 49).
  > If that flag name has changed in the actual file on disk, read `claude_usage/__main__.py`
  > and adapt the command accordingly before running. Do not assume — verify.

- [x] **Step 3: Commit the baseline fixtures.**

  ```bash
  git -C "$(git rev-parse --show-toplevel)" add \
      tests/fixtures/session_summaries/dashboard_baseline_input/ \
      tests/fixtures/dashboard_snapshot_pre_refactor.json
  git -C "$(git rev-parse --show-toplevel)" commit -m "$(cat <<'EOF'
  test(cli): capture pre-refactor dashboard JSON baseline part of #19

  Adds a minimal fake .claude project fixture and the byte-identical
  JSON snapshot produced by the current CLI. Used as a regression gate
  in Phase 1 Task 1.3 to confirm the subparser refactor does not alter
  dashboard output.

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Phase 1 — CLI Subparser Refactor

### Task 1.1: Create `cli/` Package Skeleton + Move Dashboard Body

**Files:**
- Create: `claude_usage/cli/__init__.py`
- Create: `claude_usage/cli/dashboard.py`
- Modify: `claude_usage/__main__.py` (temporary intermediate state)

- [x] **Step 1: Create `claude_usage/cli/__init__.py`.**

  Exact file contents:

  ```python
  """CLI subcommands for claude-usage."""
  ```

  That is the entire file — one docstring line, nothing else.

- [x] **Step 2: Create `claude_usage/cli/dashboard.py`.**

  Move the body of `__main__.py`'s `main()` function into a new `run(args)` function. Preserve all
  imports and helper functions. The helper functions `_parse_window` and `_parse_date` move into
  this file as well because they are dashboard-specific argument types and belong with the
  dashboard argument parser.

  Skeleton (implementer must copy the full existing body verbatim into the marked region):

  ```python
  """Dashboard subcommand for claude-usage."""

  from __future__ import annotations

  import argparse
  import json
  import re
  import sys
  from datetime import datetime, timezone
  from pathlib import Path

  from claude_usage.aggregator import aggregate
  from claude_usage.parser import parse_sessions
  from claude_usage.renderer import render
  from claude_usage.skill_tracking import parse_skill_tracking


  def _parse_window(window_str: str) -> float:
      """Parse a window string like '5h' or '7d' into hours.

      Args:
          window_str: A string of the form '<number>h' or '<number>d'.

      Returns:
          The window duration expressed as a float number of hours.

      Raises:
          argparse.ArgumentTypeError: If the format is not recognised.
      """
      match = re.match(
          r"^(\d+(?:\.\d+)?)(h|d)$", window_str.strip().lower()
      )
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
      """Parse a date string (YYYY-MM-DD) into a timezone-aware datetime.

      Args:
          date_str: A date string in YYYY-MM-DD format.

      Returns:
          A UTC-aware datetime set to midnight on the given date.

      Raises:
          argparse.ArgumentTypeError: If the string is not YYYY-MM-DD.
      """
      try:
          dt = datetime.strptime(date_str, "%Y-%m-%d")
          return dt.replace(tzinfo=timezone.utc)
      except ValueError:
          raise argparse.ArgumentTypeError(
              f"Invalid date format: '{date_str}'. Use YYYY-MM-DD."
          )


  def build_parser(parent: argparse._SubParsersAction) -> argparse.ArgumentParser:
      """Register the 'dashboard' subparser and return it.

      Args:
          parent: The subparsers action from the top-level parser.

      Returns:
          The configured dashboard ArgumentParser.
      """
      p = parent.add_parser(
          "dashboard",
          help="Generate an HTML or JSON dashboard of Claude Code token usage.",
      )
      p.add_argument(
          "--data-dir",
          type=Path,
          default=Path.home() / ".claude",
          help=(
              "Path to Claude Code data directory (default: ~/.claude)"
          ),
      )
      p.add_argument(
          "--from", dest="from_date", type=_parse_date,
          help=(
              "Start date (YYYY-MM-DD). Only include data on or after this date."
          ),
      )
      p.add_argument(
          "--to", dest="to_date", type=_parse_date,
          help=(
              "End date (YYYY-MM-DD). Only include data before this date."
          ),
      )
      p.add_argument(
          "--window", type=_parse_window,
          help="Rolling window (e.g. '5h', '7d'). Overrides --from.",
      )
      p.add_argument(
          "--output", "-o", type=Path,
          help="Output file path. If omitted, writes to a temp file.",
      )
      p.add_argument(
          "--no-open", action="store_true",
          help="Don't open the dashboard in a browser.",
      )
      p.add_argument(
          "--limit-5h", type=int, default=None,
          help="Token budget for 5-hour rolling window.",
      )
      p.add_argument(
          "--limit-7d", type=int, default=None,
          help="Token budget for 7-day rolling window.",
      )
      p.add_argument(
          "--limit-sonnet-7d", type=int, default=None,
          help="Token budget for Sonnet-only 7-day window.",
      )
      p.add_argument(
          "--format", dest="output_format",
          choices=["html", "json"], default="html",
          help=(
              "Output format: 'html' (default) opens a dashboard; "
              "'json' writes structured data to stdout."
          ),
      )
      return p


  def run(args: argparse.Namespace) -> int:
      """Execute the dashboard subcommand.

      Args:
          args: Parsed argument namespace from the dashboard subparser.

      Returns:
          Integer exit code (0 on success).
      """
      # ... existing body of __main__.main() moved here verbatim ...
      # Replace `parser.parse_args()` call with the `args` parameter already
      # provided. Replace `return` statements that previously fell off the end
      # of main() with `return 0`. The final `print(f"Dashboard written to
      # {output}")` line should also return 0 after printing.
      #
      # IMPORTANT: preserve all logic exactly — this step is a move, not a
      # rewrite. The only structural change is the function signature and the
      # addition of `return 0` where the old function simply fell through.
      status_file = (
          sys.stderr if args.output_format == "json" else sys.stdout
      )

      print(f"Scanning sessions in {args.data_dir}...", file=status_file)
      sessions = parse_sessions(args.data_dir)
      print(f"Found {len(sessions)} sessions.", file=status_file)

      result = aggregate(
          sessions,
          from_date=args.from_date,
          to_date=args.to_date,
          window_hours=args.window,
      )
      print(
          f"Aggregated: {result.total_tokens:,} tokens across "
          f"{result.total_sessions} sessions.",
          file=status_file,
      )

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

      if args.output_format == "json":
          payload = {
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "total_tokens": result.total_tokens,
              "total_messages": result.total_messages,
              "total_sessions": result.total_sessions,
              "by_model": result.by_model,
              "by_agent": result.by_agent,
              "by_skill": result.by_skill,
              "by_project": result.by_project,
              "by_day": result.by_day,
              "sessions": result.sessions,
              "limits": limits,
          }
          print(json.dumps(payload, indent=2))
          return 0

      output = render(
          result,
          output_path=args.output,
          open_browser=not args.no_open,
          limits=limits,
      )
      print(f"Dashboard written to {output}")
      return 0
  ```

- [x] **Step 3: Run existing tests to confirm nothing is broken.**

  ```bash
  uv run pytest -x
  ```

  Expected: all tests pass. The old `main()` in `__main__.py` is still present (import surface
  intact); the new `cli/dashboard.py` is now importable but not yet wired to anything.

- [x] **Step 4: Commit.**

  ```bash
  git add claude_usage/cli/__init__.py claude_usage/cli/dashboard.py
  git commit -m "$(cat <<'EOF'
  refactor(cli): extract dashboard logic into cli/dashboard.py part of #19

  Moves the full body of __main__.main() into cli/dashboard.run(args) and
  adds the cli/ package skeleton. __main__.py is unchanged in this commit;
  wiring happens in the next task.

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 1.2: Rewrite `__main__.py` as Subparser Dispatcher

**Files:**
- Modify: `claude_usage/__main__.py` (full rewrite to ~30 lines)
- Create: `claude_usage/cli/session_summary.py` (stub only — full implementation in Phase 2+)
- Create: `tests/test_cli_subcommands.py`

- [x] **Step 1: Write the failing test first.**

  Create `tests/test_cli_subcommands.py` with the following content:

  ```python
  """Tests for top-level CLI subparser routing."""

  from __future__ import annotations

  import subprocess
  import sys


  def _run(*args: str) -> subprocess.CompletedProcess[str]:
      """Run claude_usage as a module and capture output.

      Args:
          *args: Command-line arguments to pass after the module name.

      Returns:
          CompletedProcess with stdout, stderr, and returncode populated.
      """
      return subprocess.run(
          [sys.executable, "-m", "claude_usage", *args],
          capture_output=True,
          text=True,
      )


  def test_bare_invocation_exits_0_and_shows_subcommands() -> None:
      """Bare 'claude-usage' with no args must exit 0 and list subcommands."""
      result = _run()
      assert result.returncode == 0
      combined = result.stdout + result.stderr
      assert "dashboard" in combined
      assert "session-summary" in combined


  def test_dashboard_help_exits_0() -> None:
      """'claude-usage dashboard --help' must exit 0."""
      result = _run("dashboard", "--help")
      assert result.returncode == 0


  def test_old_flag_only_form_exits_nonzero() -> None:
      """'claude-usage --format json' (old form) must exit non-zero post-refactor.

      The top-level parser no longer accepts --format; callers must migrate
      to 'claude-usage dashboard --format json'.
      """
      result = _run("--format", "json")
      assert result.returncode != 0
  ```

- [x] **Step 2: Run the test — confirm it fails.**

  ```bash
  uv run pytest tests/test_cli_subcommands.py -x -v
  ```

  Expected failures:
  - `test_bare_invocation_exits_0_and_shows_subcommands` — current CLI has no subparsers, output
    will not contain "session-summary".
  - `test_old_flag_only_form_exits_nonzero` — current CLI accepts `--format json` and exits 0.

- [x] **Step 3: Create the `session_summary.py` stub.**

  The stub must make `from claude_usage.cli import session_summary` succeed so `__main__.py` can
  import it. Full implementation comes in Phase 2+.

  Create `claude_usage/cli/session_summary.py`:

  ```python
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
  ```

- [x] **Step 4: Rewrite `claude_usage/__main__.py`.**

  Full new file contents (~30 lines):

  ```python
  """CLI entry point for claude-usage — subparser dispatcher."""

  from __future__ import annotations

  import sys

  from claude_usage.cli import dashboard, session_summary


  def main() -> None:
      """Parse top-level subcommand and dispatch to the appropriate runner."""
      import argparse

      parser = argparse.ArgumentParser(
          prog="claude-usage",
          description=(
              "Claude Code token usage tools. "
              "Run 'claude-usage <subcommand> --help' for details."
          ),
      )
      subparsers = parser.add_subparsers(
          dest="subcommand",
          metavar="subcommand",
      )

      dashboard.build_parser(subparsers)
      session_summary.build_parser(subparsers)

      args = parser.parse_args()

      if args.subcommand is None:
          parser.print_help()
          sys.exit(0)

      if args.subcommand == "dashboard":
          sys.exit(dashboard.run(args))

      if args.subcommand == "session-summary":
          sys.exit(session_summary.run(args))


  if __name__ == "__main__":
      main()
  ```

- [x] **Step 5: Run the full test suite.**

  ```bash
  uv run pytest -x
  ```

  Expected: the three new tests in `test_cli_subcommands.py` pass. All pre-existing tests
  continue to pass. (Any test that previously invoked the old `main()` directly via
  `subprocess` will now hit the subparser dispatcher — confirm those still pass or update
  their invocation to `claude-usage dashboard [flags]`.)

- [x] **Step 6: Commit.**

  ```bash
  git add claude_usage/__main__.py \
          claude_usage/cli/session_summary.py \
          tests/test_cli_subcommands.py
  git commit -m "$(cat <<'EOF'
  refactor(cli): rewrite __main__.py as subparser dispatcher part of #19

  Introduces top-level argparse subparsers for 'dashboard' and
  'session-summary'. The old flag-only form (claude-usage --format json)
  is removed; callers must migrate to claude-usage dashboard --format json.
  session_summary.py is a stub that raises NotImplementedError pending
  Phase 2 implementation.

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 1.3: Verify Dashboard Behavior Unchanged vs. Phase 0 Baseline

**Files:**
- Create: `tests/test_dashboard_snapshot.py`

- [x] **Step 1: Write the snapshot regression test.**

  Create `tests/test_dashboard_snapshot.py`:

  ```python
  """Regression test: dashboard JSON output is byte-identical after refactor.

  Compares 'claude-usage dashboard --format json' output against the
  snapshot captured on main before the subparser refactor (Phase 0).
  """

  from __future__ import annotations

  import json
  import subprocess
  import sys
  from pathlib import Path

  FIXTURE_DIR = (
      Path(__file__).parent
      / "fixtures"
      / "session_summaries"
      / "dashboard_baseline_input"
  )
  SNAPSHOT_FILE = (
      Path(__file__).parent
      / "fixtures"
      / "dashboard_snapshot_pre_refactor.json"
  )


  def test_existing_dashboard_unchanged() -> None:
      """dashboard --format json output must be byte-identical to pre-refactor.

      Runs the dashboard subcommand against the committed minimal fixture
      tree and compares stdout to the snapshot captured on main before the
      refactor. Any diff indicates a behavior regression in the refactor.

      Note: generated_at will differ between runs (it is the current
      timestamp). The comparison therefore normalises that field to a
      fixed sentinel before comparing, so only structural/data differences
      trigger a failure.
      """
      result = subprocess.run(
          [
              sys.executable, "-m", "claude_usage",
              "dashboard",
              "--from", "2026-01-01",
              "--to", "2026-12-31",
              "--format", "json",
              "--data-dir", str(FIXTURE_DIR),
          ],
          capture_output=True,
          text=True,
      )
      assert result.returncode == 0, (
          f"dashboard exited {result.returncode}.\nstderr: {result.stderr}"
      )

      actual = json.loads(result.stdout)
      expected = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))

      # Normalise the timestamp field — it will differ between runs.
      actual["generated_at"] = "__normalised__"
      expected["generated_at"] = "__normalised__"

      assert actual == expected, (
          "Dashboard JSON output differs from pre-refactor snapshot.\n"
          "If this is intentional, re-capture the snapshot (Phase 0 Task 0 "
          "Step 2) and commit the updated file."
      )
  ```

- [x] **Step 2: Run the test.**

  ```bash
  uv run pytest tests/test_dashboard_snapshot.py -v
  ```

  Expected: `test_existing_dashboard_unchanged` passes. The refactor was a verbatim body move;
  dashboard behavior is unchanged.

- [x] **Step 3: Commit.**

  ```bash
  git add tests/test_dashboard_snapshot.py
  git commit -m "$(cat <<'EOF'
  test(cli): add dashboard snapshot regression test part of #19

  Verifies byte-identical dashboard JSON output (modulo generated_at
  timestamp) after the subparser refactor, guarding against accidental
  behavior regression.

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

---

## Phase 2 — Test Fixtures & Dataclasses

### Task 2.1: Build Sanitizer Helper and Fixture Infrastructure

**Files:**
- Create: `tests/fixtures/sanitize_transcript.py`
- Create: `tests/fixtures/session_summaries/happy_path.jsonl`
- Create: `tests/fixtures/session_summaries/empty_no_user_turns.jsonl`
- Create: `tests/fixtures/session_summaries/all_malformed.jsonl`
- Create: `tests/fixtures/session_summaries/slash_command_only.jsonl`
- Create: `tests/fixtures/session_summaries/zero_byte.jsonl`
- Create: `tests/fixtures/session_summaries/whitespace_only.jsonl`
- Create: `tests/fixtures/session_summaries/max_tokens_stop.jsonl`
- Create: `tests/fixtures/session_summaries/prevented_continuation.jsonl`
- Create: `tests/fixtures/session_summaries/no_assistant_entries.jsonl`
- Create: `tests/fixtures/session_summaries/missing_stop_reason.jsonl`
- Create: `tests/fixtures/session_summaries/over_fifty_actions.jsonl`
- Create: `tests/fixtures/session_summaries/mcp_both_forms.jsonl`
- Create: `tests/fixtures/session_summaries/consecutive_edits_same_file.jsonl`

- [x] **Step 1: Create `tests/fixtures/sanitize_transcript.py`.**

  This script reads a real Claude Code transcript from a path given on the
  command line, strips identifying data, and writes sanitized JSONL to stdout.
  It removes `requestId` fields, drops the content of `thinking` blocks (which
  can be large and sensitive), and preserves everything else needed for the
  session-summary pipeline.

  Full file contents:

  ```python
  #!/usr/bin/env python3
  """Sanitize a Claude Code transcript for use as a committed test fixture.

  Reads a JSONL transcript from the path given as the first positional
  argument, sanitizes each entry (strips requestId, clears thinking-block
  content), and writes the result to stdout as JSONL.

  Usage:
      python tests/fixtures/sanitize_transcript.py ~/.claude/projects/<hash>/<session>.jsonl \
          > tests/fixtures/session_summaries/my_fixture.jsonl
  """

  from __future__ import annotations

  import json
  import sys
  from pathlib import Path


  _OMIT_TOP_LEVEL_KEYS: frozenset[str] = frozenset({"requestId"})


  def _sanitize_content_block(block: dict) -> dict:
      """Strip sensitive data from a single content block.

      Args:
          block: A content block dict (may have type, text, thinking, etc.).

      Returns:
          A new dict with thinking-block text replaced by a sentinel.
      """
      if block.get("type") == "thinking":
          return {**block, "thinking": "<redacted>"}
      return block


  def _sanitize_entry(entry: dict) -> dict:
      """Sanitize one JSONL entry.

      Args:
          entry: A parsed JSONL entry dict.

      Returns:
          A new dict with identifying fields removed and content sanitized.
      """
      result = {
          k: v for k, v in entry.items()
          if k not in _OMIT_TOP_LEVEL_KEYS
      }
      msg = result.get("message")
      if isinstance(msg, dict):
          content = msg.get("content")
          if isinstance(content, list):
              sanitized_content = [
                  _sanitize_content_block(b) if isinstance(b, dict) else b
                  for b in content
              ]
              result["message"] = {**msg, "content": sanitized_content}
      return result


  def main() -> None:
      """Read transcript path from argv, sanitize, write to stdout."""
      if len(sys.argv) != 2:
          print(
              f"Usage: {sys.argv[0]} <transcript.jsonl>",
              file=sys.stderr,
          )
          sys.exit(1)

      path = Path(sys.argv[1])
      if not path.is_file():
          print(f"Error: not a file: {path}", file=sys.stderr)
          sys.exit(1)

      with open(path, encoding="utf-8") as fh:
          for raw_line in fh:
              line = raw_line.strip()
              if not line:
                  continue
              try:
                  entry = json.loads(line)
              except json.JSONDecodeError:
                  continue
              sanitized = _sanitize_entry(entry)
              print(json.dumps(sanitized, ensure_ascii=False))


  if __name__ == "__main__":
      main()
  ```

- [x] **Step 2: Create `tests/fixtures/session_summaries/happy_path.jsonl`.**

  This fixture drives `test_happy_path_emits_contract` and provides edit,
  bash, and agent-dispatch tool-use blocks. The `cwd` field is present so
  project derivation resolves to `"claude-usage"`. The final assistant entry
  has `stop_reason: "end_turn"` so `stoppedNaturally` resolves to `true`.

  Full file contents (each line is one JSON object — no trailing commas):

  ```jsonl
  {"type":"agent-setting","agentSetting":"orchestrator","timestamp":"2026-04-20T09:00:00.000Z","sessionId":"sess-happy","uuid":"s-001"}
  {"type":"user","message":{"role":"user","content":"Implement the session-summary subcommand for the /whats-next skill."},"uuid":"u-001","timestamp":"2026-04-20T09:00:01.000Z","sessionId":"sess-happy","userType":"external","cwd":"/home/user/claude-usage"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"I will implement the subcommand now."},{"type":"tool_use","id":"tu-001","name":"Edit","input":{"file_path":"claude_usage/cli/session_summary.py","old_string":"raise NotImplementedError","new_string":"pass"}}],"model":"claude-sonnet-4-6","stop_reason":"tool_use","usage":{"input_tokens":100,"output_tokens":50,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-001","timestamp":"2026-04-20T09:00:02.000Z","sessionId":"sess-happy"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"tu-002","name":"Bash","input":{"command":"uv run pytest tests/test_session_summary.py -x","description":"Run tests"}}],"model":"claude-sonnet-4-6","stop_reason":"tool_use","usage":{"input_tokens":110,"output_tokens":30,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-002","timestamp":"2026-04-20T09:00:05.000Z","sessionId":"sess-happy"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"tu-003","name":"Agent","input":{"subagent_type":"code-reviewer","description":"Review the session_summary implementation"}}],"model":"claude-sonnet-4-6","stop_reason":"tool_use","usage":{"input_tokens":120,"output_tokens":40,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-003","timestamp":"2026-04-20T09:00:10.000Z","sessionId":"sess-happy"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Implementation complete."}],"model":"claude-sonnet-4-6","stop_reason":"end_turn","usage":{"input_tokens":130,"output_tokens":10,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-004","timestamp":"2026-04-20T09:00:15.000Z","sessionId":"sess-happy"}
  ```

- [x] **Step 3: Create `tests/fixtures/session_summaries/empty_no_user_turns.jsonl`.**

  Contains only agent-setting and system entries — zero external user turns.
  Used by `test_empty_session_exits_2`.

  ```jsonl
  {"type":"agent-setting","agentSetting":"orchestrator","timestamp":"2026-04-20T10:00:00.000Z","sessionId":"sess-empty","uuid":"s-001"}
  {"type":"system","subtype":"init","timestamp":"2026-04-20T10:00:01.000Z","sessionId":"sess-empty","uuid":"sys-001"}
  ```

- [x] **Step 4: Create `tests/fixtures/session_summaries/all_malformed.jsonl`.**

  Every non-blank line fails `json.loads`. Used by `test_malformed_file_exits_3`.

  ```
  not json at all
  {broken json here
  {"unterminated":
  ```

  Write these three lines verbatim — no quotes around the block, these are
  the actual file contents.

- [x] **Step 5: Create `tests/fixtures/session_summaries/slash_command_only.jsonl`.**

  The external user turn contains only the slash-command XML wrapper — no
  surviving text after stripping. Used by `test_intent_falls_back_for_slash_command_only`.

  ```jsonl
  {"type":"agent-setting","agentSetting":"orchestrator","timestamp":"2026-04-20T11:00:00.000Z","sessionId":"sess-slash","uuid":"s-001"}
  {"type":"user","message":{"role":"user","content":"<command-name>/project-review</command-name><command-args></command-args>"},"uuid":"u-001","timestamp":"2026-04-20T11:00:01.000Z","sessionId":"sess-slash","userType":"external","cwd":"/home/user/claude-usage"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Running project review."}],"model":"claude-sonnet-4-6","stop_reason":"end_turn","usage":{"input_tokens":20,"output_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-001","timestamp":"2026-04-20T11:00:02.000Z","sessionId":"sess-slash"}
  ```

- [x] **Step 6: Create `tests/fixtures/session_summaries/zero_byte.jsonl`.**

  Zero-byte file. Create it with:

  ```bash
  touch tests/fixtures/session_summaries/zero_byte.jsonl
  ```

  The file must be committed as empty (zero bytes). Git will track it as long
  as the parent directory is tracked.

- [x] **Step 7: Create `tests/fixtures/session_summaries/whitespace_only.jsonl`.**

  Three blank lines — no non-whitespace content. Git may strip trailing
  newlines; write a file whose every line is whitespace-only.

  ```
  (blank line)
  (blank line)
  (blank line)
  ```

  Concretely, the file contains three newline characters and nothing else.
  Create it with:

  ```bash
  printf '\n\n\n' > tests/fixtures/session_summaries/whitespace_only.jsonl
  ```

- [x] **Step 8: Create `tests/fixtures/session_summaries/max_tokens_stop.jsonl`.**

  Final assistant entry has `stop_reason: "max_tokens"`. Used by
  `test_stopped_naturally_false_on_max_tokens`.

  ```jsonl
  {"type":"user","message":{"role":"user","content":"Do a long task."},"uuid":"u-001","timestamp":"2026-04-20T12:00:00.000Z","sessionId":"sess-maxtok","userType":"external","cwd":"/home/user/claude-usage"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Working..."}],"model":"claude-sonnet-4-6","stop_reason":"max_tokens","usage":{"input_tokens":200,"output_tokens":1024,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-001","timestamp":"2026-04-20T12:00:10.000Z","sessionId":"sess-maxtok"}
  ```

- [x] **Step 9: Create `tests/fixtures/session_summaries/prevented_continuation.jsonl`.**

  Includes a `type: "system"` entry with `subtype: "stop_hook_summary"` and
  `preventedContinuation: true`. Used by
  `test_stopped_naturally_false_on_prevented_continuation`.

  ```jsonl
  {"type":"user","message":{"role":"user","content":"Run the build."},"uuid":"u-001","timestamp":"2026-04-20T13:00:00.000Z","sessionId":"sess-prev","userType":"external","cwd":"/home/user/claude-usage"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Building..."}],"model":"claude-sonnet-4-6","stop_reason":"end_turn","usage":{"input_tokens":50,"output_tokens":10,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-001","timestamp":"2026-04-20T13:00:05.000Z","sessionId":"sess-prev"}
  {"type":"system","subtype":"stop_hook_summary","preventedContinuation":true,"timestamp":"2026-04-20T13:00:06.000Z","sessionId":"sess-prev","uuid":"sys-001"}
  ```

- [x] **Step 10: Create `tests/fixtures/session_summaries/no_assistant_entries.jsonl`.**

  Has an external user turn but zero assistant entries. Used by
  `test_stopped_naturally_null_on_no_assistant_turns`.

  ```jsonl
  {"type":"user","message":{"role":"user","content":"Just a question, no response yet."},"uuid":"u-001","timestamp":"2026-04-20T14:00:00.000Z","sessionId":"sess-noassist","userType":"external","cwd":"/home/user/claude-usage"}
  ```

- [x] **Step 11: Create `tests/fixtures/session_summaries/missing_stop_reason.jsonl`.**

  Final assistant entry has no `stop_reason` key in the message. Used by
  `test_stopped_naturally_null_on_missing_stop_reason`.

  ```jsonl
  {"type":"user","message":{"role":"user","content":"What is 2+2?"},"uuid":"u-001","timestamp":"2026-04-20T15:00:00.000Z","sessionId":"sess-nostop","userType":"external","cwd":"/home/user/claude-usage"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"4."}],"model":"claude-sonnet-4-6","usage":{"input_tokens":10,"output_tokens":2,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-001","timestamp":"2026-04-20T15:00:01.000Z","sessionId":"sess-nostop"}
  ```

- [x] **Step 12: Create `tests/fixtures/session_summaries/over_fifty_actions.jsonl`.**

  Produces more than 50 distinct (non-collapsible) actions. Each assistant
  entry uses a different target file so consecutive-collapse does not reduce
  the count. 55 Edit tool-use blocks across 55 assistant entries is sufficient.
  Used by `test_actions_truncated_at_default_cap`,
  `test_actions_respects_max_actions_override`, and
  `test_actions_cap_zero_disables_truncation`.

  Generate the file contents programmatically — show the generation script
  inline, then run it to produce the file:

  ```python
  # Run this once to generate the fixture:
  # python -c "exec(open('_gen.py').read())"
  # or paste the block into a REPL.
  import json, pathlib

  lines = []
  lines.append(json.dumps({
      "type": "user",
      "message": {"role": "user", "content": "Edit fifty-five files."},
      "uuid": "u-001",
      "timestamp": "2026-04-20T16:00:00.000Z",
      "sessionId": "sess-many",
      "userType": "external",
      "cwd": "/home/user/claude-usage",
  }))
  for i in range(1, 56):
      lines.append(json.dumps({
          "type": "assistant",
          "message": {
              "role": "assistant",
              "content": [{
                  "type": "tool_use",
                  "id": f"tu-{i:03d}",
                  "name": "Edit",
                  "input": {
                      "file_path": f"src/file_{i:03d}.py",
                      "old_string": "pass",
                      "new_string": f"# edited {i}",
                  },
              }],
              "model": "claude-sonnet-4-6",
              "stop_reason": "tool_use" if i < 55 else "end_turn",
              "usage": {
                  "input_tokens": 50,
                  "output_tokens": 10,
                  "cache_creation_input_tokens": 0,
                  "cache_read_input_tokens": 0,
              },
          },
          "uuid": f"a-{i:03d}",
          "timestamp": f"2026-04-20T16:{i // 60:02d}:{i % 60:02d}.000Z",
          "sessionId": "sess-many",
      }))

  out = pathlib.Path(
      "tests/fixtures/session_summaries/over_fifty_actions.jsonl"
  )
  out.write_text("\n".join(lines) + "\n", encoding="utf-8")
  print(f"Wrote {len(lines)} lines to {out}")
  ```

  Save the script as `_gen_over_fifty.py` in the worktree root and run:

  ```bash
  python _gen_over_fifty.py
  rm _gen_over_fifty.py
  ```

- [x] **Step 13: Create `tests/fixtures/session_summaries/mcp_both_forms.jsonl`.**

  Contains two MCP tool-use entries — one plugin-scoped form and one direct
  form for the same logical server+method. Used by the MCP classification
  task (Task 3.6 in the next pass).

  ```jsonl
  {"type":"user","message":{"role":"user","content":"Create a GitHub issue and fetch docs."},"uuid":"u-001","timestamp":"2026-04-20T17:00:00.000Z","sessionId":"sess-mcp","userType":"external","cwd":"/home/user/claude-usage"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"tu-001","name":"mcp__plugin_github_github__create_issue","input":{"title":"Test issue","body":"body text"}}],"model":"claude-sonnet-4-6","stop_reason":"tool_use","usage":{"input_tokens":60,"output_tokens":20,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-001","timestamp":"2026-04-20T17:00:01.000Z","sessionId":"sess-mcp"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"tu-002","name":"mcp__github__create_issue","input":{"title":"Another issue","body":"more text"}}],"model":"claude-sonnet-4-6","stop_reason":"tool_use","usage":{"input_tokens":65,"output_tokens":20,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-002","timestamp":"2026-04-20T17:00:02.000Z","sessionId":"sess-mcp"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Done."}],"model":"claude-sonnet-4-6","stop_reason":"end_turn","usage":{"input_tokens":70,"output_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-003","timestamp":"2026-04-20T17:00:05.000Z","sessionId":"sess-mcp"}
  ```

- [x] **Step 14: Create `tests/fixtures/session_summaries/consecutive_edits_same_file.jsonl`.**

  Three consecutive Edit tool-use blocks all targeting the same file path.
  After collapse, only one `ActionRecord` for that file should remain. Used by
  `test_consecutive_edits_collapse`.

  ```jsonl
  {"type":"user","message":{"role":"user","content":"Fix the parser three times."},"uuid":"u-001","timestamp":"2026-04-20T18:00:00.000Z","sessionId":"sess-collapse","userType":"external","cwd":"/home/user/claude-usage"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"tu-001","name":"Edit","input":{"file_path":"claude_usage/parser.py","old_string":"a","new_string":"b"}}],"model":"claude-sonnet-4-6","stop_reason":"tool_use","usage":{"input_tokens":50,"output_tokens":10,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-001","timestamp":"2026-04-20T18:00:01.000Z","sessionId":"sess-collapse"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"tu-002","name":"Edit","input":{"file_path":"claude_usage/parser.py","old_string":"b","new_string":"c"}}],"model":"claude-sonnet-4-6","stop_reason":"tool_use","usage":{"input_tokens":50,"output_tokens":10,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-002","timestamp":"2026-04-20T18:00:02.000Z","sessionId":"sess-collapse"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"tu-003","name":"Edit","input":{"file_path":"claude_usage/parser.py","old_string":"c","new_string":"d"}}],"model":"claude-sonnet-4-6","stop_reason":"tool_use","usage":{"input_tokens":50,"output_tokens":10,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-003","timestamp":"2026-04-20T18:00:03.000Z","sessionId":"sess-collapse"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Fixed."}],"model":"claude-sonnet-4-6","stop_reason":"end_turn","usage":{"input_tokens":55,"output_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-004","timestamp":"2026-04-20T18:00:05.000Z","sessionId":"sess-collapse"}
  ```

- [x] **Step 15: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add tests/fixtures/sanitize_transcript.py \
          tests/fixtures/session_summaries/
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  test(session-summary): add fixture transcripts and sanitizer helper

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 2.2: Define Dataclasses in `session_summary.py`

**Files:**
- Modify: `claude_usage/cli/session_summary.py` (currently contains only
  the `NotImplementedError` stub from Task 1.2)

- [x] **Step 1: Replace the stub with full module scaffolding.**

  The stub defined by Task 1.2 raises `NotImplementedError` in `run()`. This
  step replaces the entire file with the final module skeleton: module
  docstring, imports, exit-code constants, `DEFAULT_MAX_ACTIONS`, the two
  frozen dataclasses (`ActionRecord` and `SessionSummary`), and the four
  public functions as stubs raising `NotImplementedError`. The `build_parser`
  function is preserved verbatim from the Task 1.2 stub — it is already
  complete.

  Show the complete file:

  ```python
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
              through to `_derive_project` for the `decode_project_hash`
              fallback when no `cwd` field appears on any entry.
          max_actions: Soft cap on emitted actions; 0 disables the cap.

      Returns:
          Fully-populated SessionSummary.

      Raises:
          NotImplementedError: Temporarily, until Phase 3 fills this in.
      """
      raise NotImplementedError("build_session_summary — implemented in Phase 3")


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
  ```

- [x] **Step 2: Write a minimal failing test for the dataclasses.**

  In `tests/test_session_summary.py`, add the following (this is the first
  content in that file — create the file if it does not yet exist):

  ```python
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
  ```

- [x] **Step 3: Run the test — confirm it passes.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all three tests pass. The dataclasses are defined and the
  constants are correct. The `build_session_summary` stub raises
  `NotImplementedError` but is not called by these tests.

- [x] **Step 4: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): add module scaffolding and dataclasses

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Phase 3 — Core Derivation (TDD)

Each task follows strict Red → Green → Refactor. Full code is shown at every
step. No placeholders.

### Task 3.1: Happy-Path Contract Test (Full JSON Shape End-to-End)

**Files:**
- Modify: `tests/test_session_summary.py`
- Modify: `claude_usage/cli/session_summary.py`

- [x] **Step 1: Write `test_happy_path_emits_contract` — confirm it fails.**

  Add this test class to `tests/test_session_summary.py` (also add the
  `_parse_fixture` helper at the top of the file, before any test class,
  so all subsequent Phase 3 tests can reuse it):

  ```python
  import json as _json
  from pathlib import Path as _Path


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
  ```

- [x] **Step 2: Run → confirm failure.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestBuildSessionSummary::test_happy_path_emits_contract -x
  ```

  Expected failure: `NotImplementedError` from the `build_session_summary`
  stub. This is the correct red state — not an import error.

- [x] **Step 3: Implement a minimal `build_session_summary` using internal stubs.**

  Replace the `build_session_summary` stub in `claude_usage/cli/session_summary.py`
  with the following. The four private helpers (`_derive_project`,
  `_derive_intent`, `_collect_tool_uses`, `_derive_stopped_naturally`) return
  hardcoded values that satisfy the happy-path fixture. They are expanded to
  real implementations in Tasks 3.2–3.5. Add all four helpers and the updated
  public function:

  ```python
  import json
  import sys


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
      # Stub — returns hardcoded value matching happy_path fixture.
      # Replaced by real logic in Task 3.2.
      return "claude-usage"


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
  ```

  Also add `import json` and `import sys` at the top of the file, in the
  stdlib imports block, after `import argparse` and before `from dataclasses`.

- [x] **Step 4: Run → confirm pass.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all existing tests plus `test_happy_path_emits_contract` pass.

- [x] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): stub build_session_summary to pass happy-path contract test

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3.2: Project Derivation

**Files:**
- Modify: `tests/test_session_summary.py`
- Modify: `claude_usage/cli/session_summary.py`

- [x] **Step 1: Add two failing tests.**

  Add to `TestBuildSessionSummary` in `tests/test_session_summary.py`:

  ```python
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
          from pathlib import Path

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
  ```

- [x] **Step 2: Run → confirm failures.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestBuildSessionSummary::test_project_falls_back_to_unknown -x
  ```

  The `test_project_falls_back_to_unknown` test fails because the stub
  returns `"claude-usage"` unconditionally. The `test_project_derived_from_cwd_field`
  test may pass accidentally via the stub; confirm by temporarily removing the
  stub's hardcoded return and verifying it then fails before restoring.

- [x] **Step 3: Implement `_derive_project` with real logic.**

  Replace the stub body of `_derive_project` in `claude_usage/cli/session_summary.py`:

  ```python
  def _derive_project(
      entries: list[dict],
      slug_fallback: str | None = None,
  ) -> str:
      """Derive the project name from transcript entries.

      Strategy:
      1. First entry with a non-empty ``cwd`` field → ``Path(cwd).name``.
      2. Fallback: apply ``decode_project_hash`` to ``slug_fallback``
         (the transcript-directory name supplied by ``run()``).
      3. Final fallback: ``"unknown"``.

      Args:
          entries: Parsed JSONL entries in file order.
          slug_fallback: Optional project-slug string (the parent-directory
              name of the transcript file, as extracted by ``run()``).

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
  ```

- [x] **Step 4: Run → confirm pass.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass, including both new project-derivation tests.

- [x] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): implement project derivation from cwd and path slug

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3.3: Intent Derivation

**Files:**
- Modify: `tests/test_session_summary.py`
- Modify: `claude_usage/cli/session_summary.py`

- [x] **Step 1: Add four failing tests.**

  Add to `TestBuildSessionSummary` in `tests/test_session_summary.py`:

  ```python
      def test_intent_plain_text_user_turn(self, tmp_path: pytest.TempPathFactory) -> None:
          """A plain-text user turn returns the first sentence as intent."""
          import json
          from pathlib import Path

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
          from pathlib import Path

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
          from pathlib import Path

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
  ```

- [x] **Step 2: Run → confirm failures.**

  ```bash
  uv run pytest tests/test_session_summary.py -k "intent" -x
  ```

  Expected: all four intent tests fail because `_derive_intent` returns a
  hardcoded string. [confirmed: all 4 failed at red phase]

- [x] **Step 3: Implement `_derive_intent` with real logic.**

  Replace the stub body of `_derive_intent` in `claude_usage/cli/session_summary.py`.
  Also add `import re` to the stdlib imports at the top of the file.

  ```python
  # At top of file, add to stdlib imports:
  import re
  ```

  ```python
  _XML_WRAPPER_RE = re.compile(
      r"<(system-reminder|command-message|command-name"
      r"|command-args|local-command-stdout)>.*?</\1>",
      flags=re.DOTALL,
  )
  _SLASH_COMMAND_RE = re.compile(
      r"<command-name>(/[^<]+)</command-name>"
  )
  _SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.\!\?])\s|\n")


  def _extract_text_from_content(
      content: str | list,
  ) -> str:
      """Extract plain text from a message content value.

      Args:
          content: Either a raw string or a list of content blocks. In the
              list form, only blocks with ``type == "text"`` are included;
              tool_result and other block types are skipped.

      Returns:
          A single string with all text joined by spaces, not yet stripped.
      """
      if isinstance(content, str):
          return content
      if isinstance(content, list):
          parts = [
              block["text"]
              for block in content
              if isinstance(block, dict)
              and block.get("type") == "text"
              and "text" in block
          ]
          return " ".join(parts)
      return ""


  def _first_sentence(text: str, max_chars: int = 200) -> str:
      """Return the first sentence of text, capped at max_chars.

      Splits on ". ", "! ", "? ", or a newline. If the first segment is
      longer than max_chars, truncates at max_chars. Trailing punctuation
      from the split is not included in the result.

      Args:
          text: Already-stripped input text.
          max_chars: Maximum character count for the returned string.

      Returns:
          The first sentence or the first max_chars characters.
      """
      parts = _SENTENCE_SPLIT_RE.split(text, maxsplit=1)
      sentence = parts[0].rstrip(". !?")
      return sentence[:max_chars]


  def _derive_intent(entries: list[dict], project: str) -> str:
      """Derive the user's intent from the first external user turn.

      Steps:
      1. Find the first ``type: "user"`` + ``userType: "external"`` entry.
      2. Extract text from ``message.content`` (string or list of blocks).
      3. Strip the five XML wrapper tag families via regex.
      4. Trim whitespace. If non-empty → take the first sentence (or 200
         chars, whichever is shorter).
      5. If empty, look for a ``<command-name>/<name></command-name>``
         pattern in the original content → ``"Ran /<name>"``.
      6. Final fallback → ``"Session on <project>"``.

      Args:
          entries: Parsed JSONL entries in file order.
          project: The already-derived project name (used as fallback).

      Returns:
          A non-empty intent string.
      """
      for entry in entries:
          if not (
              entry.get("type") == "user"
              and entry.get("userType") == "external"
          ):
              continue
          msg = entry.get("message", {})
          raw_content = msg.get("content", "")
          original_text = _extract_text_from_content(raw_content)

          # Strip XML wrappers.
          stripped = _XML_WRAPPER_RE.sub("", original_text).strip()

          if stripped:
              return _first_sentence(stripped)

          # Slash-command fallback.
          m = _SLASH_COMMAND_RE.search(original_text)
          if m:
              return f"Ran {m.group(1)}"

          # Generic fallback.
          return f"Session on {project}"

      # No external user turn found (should not reach here after LookupError
      # guard in build_session_summary, but keep defensive).
      return f"Session on {project}"
  ```

- [x] **Step 4: Run → confirm pass.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass, including all four new intent tests.

- [x] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): implement intent derivation with XML stripping and fallbacks

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3.4: Tool Classification — Edit Family

**Files:**
- Modify: `tests/test_session_summary.py`
- Modify: `claude_usage/cli/session_summary.py`

- [x] **Step 1: Add `test_action_classification_edit_tools` — confirm it fails.**

  Add a new test class to `tests/test_session_summary.py`:

  ```python
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
          from pathlib import Path

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
          from pathlib import Path

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
  ```

- [x] **Step 2: Run → confirm failures.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestToolClassification -x
  ```

  Expected: both tests fail. `test_action_classification_edit_tools` fails
  because `_collect_tool_uses` returns the hardcoded happy-path list.
  `test_action_classification_skips_reads` fails for the same reason.

- [x] **Step 3: Implement `_classify_tool_use` and `_collect_tool_uses`.**

  Replace the stub bodies of both functions in
  `claude_usage/cli/session_summary.py`. The edit family is handled fully.
  Bash/PowerShell, Agent, MCP, and "other" return `None` for now (expanded
  in Tasks 3.5–3.6).

  ```python
  _EDIT_TOOLS: frozenset[str] = frozenset({"Edit", "Write", "NotebookEdit"})
  _SKIP_TOOLS: frozenset[str] = frozenset({
      "Read", "Grep", "Glob",
      "WebFetch", "WebSearch",
      "Skill", "TodoWrite",
  })


  def _classify_tool_use(tool_use: dict) -> ActionRecord | None:
      """Classify a single tool-use content block into an ActionRecord.

      Returns None for tools that should be skipped (info-gathering,
      skill enablers, ceremony). Returns an ActionRecord for all
      state-changing tools. Unknown tool names produce an "other"-class
      record for forward compatibility.

      Args:
          tool_use: A content block dict with ``type == "tool_use"``.

      Returns:
          An ActionRecord, or None if this tool use should be skipped.
      """
      name: str = tool_use.get("name", "")
      inp: dict = tool_use.get("input", {})

      # Skip list — info-gathering and ceremony.
      if name in _SKIP_TOOLS:
          return None

      # Edit family.
      if name in _EDIT_TOOLS:
          target = inp.get("file_path", "")
          return ActionRecord(
              type="edit",
              raw_tool=name,
              target=target,
              summary=f"Edited {target}",
          )

      # Bash / PowerShell — implemented in Task 3.5.
      # Agent — implemented in Task 3.5.
      # MCP — implemented in Task 3.6 (next pass).

      # Placeholder for not-yet-classified tools: skip rather than
      # produce "other" until later tasks fill them in. Once Task 3.6
      # is complete this branch will handle the "other" catch-all.
      return None


  def _collapse_consecutive(
      records: list[ActionRecord],
  ) -> list[ActionRecord]:
      """Collapse consecutive ActionRecords that share (type, target).

      Non-adjacent duplicates are NOT collapsed — chronological order
      is preserved and the collapse is strictly sequential.

      Args:
          records: Chronologically ordered list of ActionRecords.

      Returns:
          Collapsed list with no two adjacent records sharing
          (type, target).
      """
      if not records:
          return []
      collapsed: list[ActionRecord] = [records[0]]
      for rec in records[1:]:
          prev = collapsed[-1]
          if rec.type == prev.type and rec.target == prev.target:
              continue  # Duplicate of the previous record — drop it.
          collapsed.append(rec)
      return collapsed


  def _collect_tool_uses(entries: list[dict]) -> list[ActionRecord]:
      """Classify all tool-use content blocks from assistant entries.

      Iterates entries in file order, collects tool_use blocks from
      assistant message content, classifies each, skips None results,
      then collapses consecutive duplicates.

      Args:
          entries: Parsed JSONL entries in file order.

      Returns:
          Chronologically ordered, collapsed list of ActionRecord
          instances.
      """
      raw: list[ActionRecord] = []
      for entry in entries:
          if entry.get("type") != "assistant":
              continue
          msg = entry.get("message", {})
          content = msg.get("content", [])
          if not isinstance(content, list):
              continue
          for block in content:
              if not isinstance(block, dict):
                  continue
              if block.get("type") != "tool_use":
                  continue
              record = _classify_tool_use(block)
              if record is not None:
                  raw.append(record)
      return _collapse_consecutive(raw)
  ```

- [x] **Step 4: Run → confirm pass.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass. Note that `test_happy_path_emits_contract` still
  passes because the happy_path fixture actions (Edit, Bash, Agent) now flow
  through real classification — Edit is handled; Bash and Agent return `None`
  temporarily, so only the Edit action appears. Update the contract test
  assertion from `len(summary.actions) > 0` (already satisfied by one Edit)
  to confirm it still holds before committing.

- [x] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): implement edit-family tool classification and collapse

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3.5: Tool Classification — Bash / PowerShell and Agent

**Files:**
- Modify: `tests/test_session_summary.py`
- Modify: `claude_usage/cli/session_summary.py`

- [x] **Step 1: Add `test_action_classification_bash_tools` — confirm it fails.**

  Add to `TestToolClassification` in `tests/test_session_summary.py`:

  ```python
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
          from pathlib import Path

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
          from pathlib import Path

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
  ```

- [x] **Step 2: Run → confirm failures.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestToolClassification::test_action_classification_bash_tools tests/test_session_summary.py::TestToolClassification::test_action_classification_agent_dispatch -x
  ```

  Expected: both tests fail because Bash, PowerShell, and Agent return `None`
  in the current `_classify_tool_use`.

- [x] **Step 3: Extend `_classify_tool_use` to handle Bash, PowerShell, and Agent.**

  Replace the Bash/PowerShell and Agent placeholder comments in
  `_classify_tool_use` with real dispatch blocks. Show the updated function
  in full (only the relevant new cases — insert them before the final
  `return None`):

  ```python
  _BASH_TOOLS: frozenset[str] = frozenset({"Bash", "PowerShell"})
  _MAX_COMMAND_CHARS: int = 80
  ```

  Inside `_classify_tool_use`, replace the placeholder comments with:

  ```python
      # Bash / PowerShell.
      if name in _BASH_TOOLS:
          raw_command: str = inp.get("command", "")
          collapsed_command = " ".join(raw_command.split())
          if len(collapsed_command) > _MAX_COMMAND_CHARS:
              rendered = collapsed_command[:_MAX_COMMAND_CHARS] + "…"
          else:
              rendered = collapsed_command
          return ActionRecord(
              type="bash",
              raw_tool=name,
              target=collapsed_command,
              summary=f"Ran `{rendered}`",
          )

      # Agent dispatch.
      if name == "Agent":
          subagent_type: str = inp.get("subagent_type", "unknown")
          return ActionRecord(
              type="agent_dispatch",
              raw_tool=name,
              target=subagent_type,
              summary=f"Dispatched {subagent_type} sub-agent",
          )
  ```

- [x] **Step 4: Run → confirm pass.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass. The happy_path contract test now benefits from
  real Bash and Agent classification in addition to Edit, so
  `len(summary.actions) > 0` remains trivially satisfied.

- [x] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): implement Bash, PowerShell, and Agent tool classification

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3.6: Tool Classification — `Agent` → `agent_dispatch` Action

> **Note:** Task 3.5 already added `test_action_classification_agent_dispatch`
> and the `Agent` dispatch branch as part of the Bash+Agent step. This task
> therefore serves as a **regression anchor** — verify the test that was
> written there still passes under its canonical ID, and confirm the
> `ActionRecord` contract fields exactly match what Tasks 3.7–3.12 will rely
> on.

**Files:**
- Modify: `tests/test_session_summary.py`
- Modify: `claude_usage/cli/session_summary.py`

- [x] **Step 1: Confirm `test_action_classification_agent_dispatch` exists and
  check its fixture contract.**

  The test was written in Task 3.5 and lives in `TestToolClassification`. It
  must assert all four `ActionRecord` fields. If the Task 3.5 version only
  asserts the rendered summary string, extend it now to also assert the raw
  record fields by calling `_collect_tool_uses` directly. Add the extended
  assertion block shown below — it does not remove the existing summary-level
  assertion, it adds a lower-level check:

  ```python
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
      import json
      from pathlib import Path

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
  ```

- [x] **Step 2: Run → confirm both agent tests pass (green from Task 3.5).**

  ```bash
  uv run pytest tests/test_session_summary.py::TestToolClassification \
      -k "agent_dispatch" -v
  ```

  Expected: both `test_action_classification_agent_dispatch` and
  `test_action_classification_agent_dispatch_record_fields` pass. This is not
  a red step — it is a contract-verification step.

- [x] **Step 3: Confirm the dispatch branch in `_classify_tool_use`.**

  The Agent branch sits after the Bash/PowerShell block and before the final
  `return None`. For reference, the surrounding context in the function
  (showing where the Agent branch slots in):

  ```python
      # Bash / PowerShell.
      if name in _BASH_TOOLS:
          raw_command: str = inp.get("command", "")
          collapsed_command = " ".join(raw_command.split())
          if len(collapsed_command) > _MAX_COMMAND_CHARS:
              rendered = collapsed_command[:_MAX_COMMAND_CHARS] + "…"
          else:
              rendered = collapsed_command
          return ActionRecord(
              type="bash",
              raw_tool=name,
              target=collapsed_command,
              summary=f"Ran `{rendered}`",
          )

      # Agent dispatch.         ← This branch is from Task 3.5.
      if name == "Agent":
          subagent_type: str = inp.get("subagent_type", "unknown")
          return ActionRecord(
              type="agent_dispatch",
              raw_tool=name,
              target=subagent_type,
              summary=f"Dispatched {subagent_type} sub-agent",
          )

      # MCP tools — implemented in Task 3.7 (below).
      # "other" default — implemented in Task 3.9 (below).

      return None   # ← temporary; removed once Task 3.9 adds the else branch
  ```

  No code change is needed here if Task 3.5 implemented the branch correctly.

- [x] **Step 4: Run full suite → confirm no regressions.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass.

- [x] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  test(session-summary): add agent_dispatch record-fields contract test

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3.7: MCP Tool Classification with Normalization (Both Forms + Malformed Edge Case)

This task implements the spec's "MCP tool name normalization" subsection in
full. Both the plugin-scoped form (`mcp__plugin_<plugin>_<server>__<method>`)
and the direct form (`mcp__<server>__<method>`) must normalize to the same
`<server>.<method>` target so consecutive-collapse unifies them. A malformed
name (prefix present but structural separators absent) falls through to the
`other` action class defined in Task 3.9.

**Files:**
- Modify: `tests/test_session_summary.py`
- Modify: `claude_usage/cli/session_summary.py`

- [x] **Step 1: Add four tests to `TestToolClassification`.**

  ```python
      def test_action_classification_mcp_plugin_scoped(
          self, tmp_path: pytest.TempPathFactory
      ) -> None:
          """Plugin-scoped MCP name normalizes to 'github.create_issue'.

          Raw: mcp__plugin_github_github__create_issue
          Expected target: "github.create_issue"
          Expected summary: "Called `github.create_issue` (MCP)"
          """
          import json

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
          import json

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
          import json

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
          import json

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
          assert records[0].target == "github.create_issue"
  ```

- [x] **Step 2: Run → confirm all four tests fail.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestToolClassification \
      -k "mcp" -v
  ```

  Expected: all four MCP tests fail. The `_classify_tool_use` function
  currently falls through to `return None` for any `mcp__*` name — the MCP
  branch does not yet exist.

- [x] **Step 3: Implement `_normalize_mcp_tool_name` and the MCP dispatch
  branch.**

  Add the helper function at module level in `claude_usage/cli/session_summary.py`,
  before `_classify_tool_use`. Show the full helper verbatim:

  ```python
  def _normalize_mcp_tool_name(raw: str) -> str | None:
      """Normalize an MCP tool name to '<server>.<method>'.

      Handles both forms:
      - Plugin-scoped: ``mcp__plugin_<plugin>_<server>__<method>``
        e.g. ``mcp__plugin_github_github__create_issue`` → ``github.create_issue``
      - Direct: ``mcp__<server>__<method>``
        e.g. ``mcp__azure__storage`` → ``azure.storage``

      Returns None when the name is malformed (starts with ``mcp__`` but
      does not contain the expected structural separators after stripping
      the plugin segment), so the caller can fall back to the ``other``
      action class. This provides forward-compatibility when new MCP naming
      conventions appear in future Claude Code versions.

      Args:
          raw: The raw tool name from the transcript.

      Returns:
          A normalised ``<server>.<method>`` string, or None if the name
          is structurally malformed.
      """
      if not raw.startswith("mcp__"):
          return None
      remainder = raw[len("mcp__"):]

      # Strip the plugin segment if present.
      # Plugin form: plugin_<plugin>_<server>__<method>
      # After stripping "plugin_", the next segment is "<plugin>_<server>"
      # which is separated from <method> by "__".
      if remainder.startswith("plugin_"):
          after_plugin = remainder[len("plugin_"):]
          # after_plugin is "<plugin>_<server>__<method>" — split once on "_"
          # to skip the plugin label, leaving "<server>__<method>".
          parts = after_plugin.split("_", 1)
          if len(parts) < 2:
              return None  # Malformed: nothing after plugin label.
          remainder = parts[1]

      # remainder is now "<server>__<method>" for both forms.
      if "__" not in remainder:
          return None  # Malformed: no method separator.
      server, _, method = remainder.partition("__")
      if not server or not method:
          return None  # Malformed: empty server or method.
      return f"{server}.{method}"
  ```

  Then extend `_classify_tool_use` — insert the MCP branch immediately after
  the Agent branch and before the temporary `return None`. Show the insertion
  point with surrounding context:

  ```python
      # Agent dispatch.
      if name == "Agent":
          subagent_type: str = inp.get("subagent_type", "unknown")
          return ActionRecord(
              type="agent_dispatch",
              raw_tool=name,
              target=subagent_type,
              summary=f"Dispatched {subagent_type} sub-agent",
          )

      # MCP tools — both plugin-scoped and direct forms.
      if name.startswith("mcp__"):
          normalised = _normalize_mcp_tool_name(name)
          if normalised is not None:
              return ActionRecord(
                  type="mcp",
                  raw_tool=name,
                  target=normalised,
                  summary=f"Called `{normalised}` (MCP)",
              )
          # Malformed MCP name — fall through to the "other" default below.
          # Do NOT return None here; let the catch-all produce an ActionRecord.
          return ActionRecord(
              type="other",
              raw_tool=name,
              target=name,
              summary=f"Used {name} tool",
          )

      # "other" default — implemented in Task 3.9.
      return None   # temporary; replaced in Task 3.9
  ```

  > **Implementation note:** the malformed MCP case returns an `other`
  > ActionRecord inline here (rather than falling through to the catch-all)
  > because the `name.startswith("mcp__")` guard is already true — the
  > catch-all in Task 3.9 will never be reached for an `mcp__*` name. This
  > is intentional and matches the spec's forward-compat requirement.

- [x] **Step 4: Run → confirm all four MCP tests pass.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass including all four new MCP tests. Existing tests
  are unaffected.

- [x] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): implement MCP tool classification with name normalization

  Handles both plugin-scoped (mcp__plugin_<p>_<s>__<m>) and direct
  (mcp__<s>__<m>) forms. Malformed names fall back to 'other' class for
  forward compatibility. Consecutive calls to the same normalized endpoint
  collapse into one action.

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3.8: Tool Classification — Skip Rules

The full skip set is `{"Read", "Grep", "Glob", "Skill", "TodoWrite",
"WebFetch", "WebSearch"}`. This task verifies the set is enforced as a
module-level constant and that `test_action_classification_skips_reads`
(written in Task 3.4) covers every member. It also adds a test that confirms
a mix of skipped tools plus one `Edit` call produces exactly one action — the
Edit.

**Files:**
- Modify: `tests/test_session_summary.py`
- Modify: `claude_usage/cli/session_summary.py`

- [x] **Step 1: Add `test_action_classification_skip_set_is_complete` to
  `TestToolClassification`.**

  ```python
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
  ```

- [x] **Step 2: Run → confirm failures.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestToolClassification \
      -k "skip_set_is_complete or skips_mix_with_edit" -v
  ```

  Expected: `test_action_classification_skip_set_is_complete` fails because
  the module exports `_SKIP_TOOLS` (private, underscore prefix from Task 3.4)
  but not `SKIPPED_TOOLS` (public, no underscore). The mix test passes if the
  skip logic is correct from Task 3.4.

- [x] **Step 3: Rename the private constant to the public name and ensure it
  is exported.**

  In `claude_usage/cli/session_summary.py`, rename `_SKIP_TOOLS` to
  `SKIPPED_TOOLS` everywhere it appears (module constant definition and the
  guard inside `_classify_tool_use`). The `_EDIT_TOOLS` and `_BASH_TOOLS`
  constants remain private (they are implementation details; callers do not
  need them).

  Find and replace `_SKIP_TOOLS` with `SKIPPED_TOOLS` throughout the file.
  The guard inside `_classify_tool_use` becomes:

  ```python
      # Skip list — info-gathering and ceremony.
      if name in SKIPPED_TOOLS:
          return None
  ```

  And the module-level constant declaration becomes:

  ```python
  SKIPPED_TOOLS: frozenset[str] = frozenset({
      "Read",
      "Grep",
      "Glob",
      "WebFetch",
      "WebSearch",
      "Skill",
      "TodoWrite",
  })
  ```

- [x] **Step 4: Run → confirm all tests pass.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass. `test_action_classification_skip_set_is_complete`
  now finds the public `SKIPPED_TOOLS` constant and the frozenset matches.

- [x] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): expose SKIPPED_TOOLS as public constant; add skip-set completeness test

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3.9: Tool Classification — `other` Default-Include for Unknown Tools

Any tool name that is not in `SKIPPED_TOOLS`, not in `_EDIT_TOOLS`, not in
`_BASH_TOOLS`, and not handled by the Agent or MCP branches falls through to
the "other" catch-all. This preserves forward compatibility when Claude Code
introduces new tool names.

**Files:**
- Modify: `tests/test_session_summary.py`
- Modify: `claude_usage/cli/session_summary.py`

- [x] **Step 1: Add `test_action_classification_unknown_tool_defaults_to_other`.**

  ```python
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
          import json

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
  ```

- [x] **Step 2: Run → confirm failure.**

  ```bash
  uv run pytest \
      "tests/test_session_summary.py::TestToolClassification::test_action_classification_unknown_tool_defaults_to_other" \
      -v
  ```

  Expected: failure. `_collect_tool_uses` currently returns zero records for
  `"BrandNewTool"` because the temporary `return None` at the end of
  `_classify_tool_use` discards it.

- [x] **Step 3: Replace the temporary `return None` with the `other` catch-all.**

  In `claude_usage/cli/session_summary.py`, locate the line `return None` at
  the very end of `_classify_tool_use` (the one added as a placeholder in
  Task 3.4 and retained through Tasks 3.5–3.7). Replace it with the `other`
  ActionRecord. Show the full `_classify_tool_use` function as it now stands —
  this is the complete assembly of all branches from Tasks 3.4, 3.5, 3.7, and
  3.9, with a Google-style docstring:

  ```python
  def _classify_tool_use(tool_use: dict) -> ActionRecord | None:
      """Classify a single tool-use content block into an ActionRecord.

      Returns None only for tools in SKIPPED_TOOLS (info-gathering,
      skill enablers, ceremony). Every other tool name produces an
      ActionRecord — either a typed record for known tools or an
      ``other``-type record for forward compatibility with unknown tools.

      Classification priority:
      1. Skip list (SKIPPED_TOOLS) — return None immediately.
      2. Edit family (_EDIT_TOOLS) — return "edit" ActionRecord.
      3. Bash/PowerShell family (_BASH_TOOLS) — return "bash" ActionRecord.
      4. Agent dispatch — return "agent_dispatch" ActionRecord.
      5. MCP tools (mcp__* prefix) — normalise name; return "mcp" on success,
         "other" on malformed name.
      6. Catch-all — return "other" ActionRecord for forward compatibility.

      Args:
          tool_use: A content block dict with ``type == "tool_use"``.

      Returns:
          An ActionRecord, or None if this tool use is in the skip list.
      """
      name: str = tool_use.get("name", "")
      inp: dict = tool_use.get("input", {})

      # 1. Skip list — info-gathering and ceremony.
      if name in SKIPPED_TOOLS:
          return None

      # 2. Edit family.
      if name in _EDIT_TOOLS:
          target = inp.get("file_path", "")
          return ActionRecord(
              type="edit",
              raw_tool=name,
              target=target,
              summary=f"Edited {target}",
          )

      # 3. Bash / PowerShell.
      if name in _BASH_TOOLS:
          raw_command: str = inp.get("command", "")
          collapsed_command = " ".join(raw_command.split())
          if len(collapsed_command) > _MAX_COMMAND_CHARS:
              rendered = collapsed_command[:_MAX_COMMAND_CHARS] + "…"
          else:
              rendered = collapsed_command
          return ActionRecord(
              type="bash",
              raw_tool=name,
              target=collapsed_command,
              summary=f"Ran `{rendered}`",
          )

      # 4. Agent dispatch.
      if name == "Agent":
          subagent_type: str = inp.get("subagent_type", "unknown")
          return ActionRecord(
              type="agent_dispatch",
              raw_tool=name,
              target=subagent_type,
              summary=f"Dispatched {subagent_type} sub-agent",
          )

      # 5. MCP tools — both plugin-scoped and direct forms.
      if name.startswith("mcp__"):
          normalised = _normalize_mcp_tool_name(name)
          if normalised is not None:
              return ActionRecord(
                  type="mcp",
                  raw_tool=name,
                  target=normalised,
                  summary=f"Called `{normalised}` (MCP)",
              )
          # Malformed MCP name — treat as "other" (forward-compat safety).
          return ActionRecord(
              type="other",
              raw_tool=name,
              target=name,
              summary=f"Used {name} tool",
          )

      # 6. Catch-all — default-include unknown tools for forward compatibility.
      return ActionRecord(
          type="other",
          raw_tool=name,
          target=name,
          summary=f"Used {name} tool",
      )
  ```

- [x] **Step 4: Run → confirm all tests pass.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass. The `other` catch-all now handles `"BrandNewTool"`
  and any future unknown tool names.

- [x] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): add other catch-all branch to _classify_tool_use

  Unknown tool names now produce an 'other'-type ActionRecord instead of
  being silently dropped. This is the forward-compatibility default-include
  rule from the spec.

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3.10: Collapse Rule — Consecutive Same `(type, target)` Deduplication

The `_collapse_consecutive` helper was introduced in Task 3.4 as part of
`_collect_tool_uses`. This task adds the full collapse contract tests
(including the non-adjacent semantics) and verifies them end-to-end through
`build_session_summary` using the committed fixture files from Phase 2.

**Files:**
- Modify: `tests/test_session_summary.py`
- Modify: `claude_usage/cli/session_summary.py`

- [x] **Step 1: Add two tests — `test_consecutive_edits_collapse` and
  `test_non_adjacent_edits_do_not_collapse`.**

  ```python
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
  ```

- [x] **Step 2: Run → confirm both tests pass (green from Task 3.4).**

  ```bash
  uv run pytest tests/test_session_summary.py::TestCollapseConsecutive -v
  ```

  Expected: both tests pass. `_collapse_consecutive` was already implemented
  correctly in Task 3.4. This step is a contract-verification step, not a red
  step.

  If either test fails, the collapse logic from Task 3.4 is incorrect. Debug
  by inspecting `_collapse_consecutive` — the most likely cause is the
  function using global dedupe rather than consecutive-only dedupe. The correct
  implementation is:

  ```python
  def _collapse_consecutive(
      records: list[ActionRecord],
  ) -> list[ActionRecord]:
      """Drop consecutive ActionRecords sharing the same (type, target) pair.

      Non-adjacent duplicates are preserved to maintain the narrative sense
      of 'X, then Y, then X again'. No global deduplication is performed.

      Args:
          records: Chronologically ordered list of ActionRecords.

      Returns:
          A new list with no two adjacent records sharing identical
          (type, target). Input order is otherwise preserved.
      """
      collapsed: list[ActionRecord] = []
      for rec in records:
          if (
              collapsed
              and collapsed[-1].type == rec.type
              and collapsed[-1].target == rec.target
          ):
              continue
          collapsed.append(rec)
      return collapsed
  ```

  Verify this is what `session_summary.py` contains. If it differs, correct
  it and re-run.

- [x] **Step 3: Run full suite → confirm no regressions.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass.

- [x] **Step 4: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  test(session-summary): add collapse contract tests (consecutive and non-adjacent)

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3.11: `stoppedNaturally` Tri-State Derivation

This is the tri-state `bool | None` semantic defined in the spec's
"stoppedNaturally derivation — tri-state" subsection. The spec's resolution
table is the authoritative source. Five tests map one-to-one to the five
resolution-table rows that produce deterministic outcomes.

**Files:**
- Modify: `tests/test_session_summary.py`
- Modify: `claude_usage/cli/session_summary.py`

- [ ] **Step 1: Add five tests to a new `TestStoppedNaturally` class.**

  ```python
  class TestStoppedNaturally:
      """Tests for _derive_stopped_naturally tri-state resolution."""

      def test_stopped_naturally_true_on_end_turn(self) -> None:
          """stop_reason 'end_turn' with no prevented-continuation → True."""
          from pathlib import Path

          from claude_usage.cli.session_summary import build_session_summary

          fixture = Path(
              "tests/fixtures/session_summaries/happy_path.jsonl"
          )
          summary = build_session_summary(_parse_fixture(fixture))
          assert summary.stopped_naturally is True

      def test_stopped_naturally_false_on_max_tokens(self) -> None:
          """stop_reason 'max_tokens' → False (definitive interrupt)."""
          from pathlib import Path

          from claude_usage.cli.session_summary import build_session_summary

          fixture = Path(
              "tests/fixtures/session_summaries/max_tokens_stop.jsonl"
          )
          summary = build_session_summary(_parse_fixture(fixture))
          assert summary.stopped_naturally is False

      def test_stopped_naturally_false_on_prevented_continuation(self) -> None:
          """preventedContinuation: true in stop_hook_summary → False."""
          from pathlib import Path

          from claude_usage.cli.session_summary import build_session_summary

          fixture = Path(
              "tests/fixtures/session_summaries/prevented_continuation.jsonl"
          )
          summary = build_session_summary(_parse_fixture(fixture))
          assert summary.stopped_naturally is False

      def test_stopped_naturally_null_on_no_assistant_turns(self) -> None:
          """Zero assistant entries → None (nothing to judge)."""
          from pathlib import Path

          from claude_usage.cli.session_summary import build_session_summary

          fixture = Path(
              "tests/fixtures/session_summaries/no_assistant_entries.jsonl"
          )
          summary = build_session_summary(_parse_fixture(fixture))
          assert summary.stopped_naturally is None

      def test_stopped_naturally_null_on_missing_stop_reason(self) -> None:
          """Last assistant entry has no stop_reason key → None (signal absent)."""
          from pathlib import Path

          from claude_usage.cli.session_summary import build_session_summary

          fixture = Path(
              "tests/fixtures/session_summaries/missing_stop_reason.jsonl"
          )
          summary = build_session_summary(_parse_fixture(fixture))
          assert summary.stopped_naturally is None
  ```

- [ ] **Step 2: Run → confirm failures.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestStoppedNaturally -v
  ```

  Expected: most tests fail because `_derive_stopped_naturally` currently
  returns the hardcoded stub value `True` from Task 3.1. The
  `test_stopped_naturally_true_on_end_turn` test may pass accidentally through
  the stub; the other four will fail.

- [ ] **Step 3: Implement `_derive_stopped_naturally` with real tri-state logic.**

  Replace the stub body in `claude_usage/cli/session_summary.py` with the
  full implementation. Show the complete function:

  ```python
  def _derive_stopped_naturally(
      entries: list[dict],
  ) -> bool | None:
      """Resolve the tri-state stoppedNaturally field per the spec's table.

      Walks entries once, tracking:
      - ``has_any_assistant``: True once any assistant entry is seen.
      - ``last_stop_reason``: Updated on every assistant entry; last wins.
      - ``prevented_continuation``: True if any stop_hook_summary entry
        has ``preventedContinuation: true``.

      Resolution table (applied in priority order):
      - no assistant entries → None (nothing to judge)
      - last stop_reason absent/empty → None (signal absent)
      - prevented_continuation is True → False (definitive interrupt)
      - last stop_reason == "end_turn" → True
      - last stop_reason in {"max_tokens", "tool_use", "stop_sequence"} → False
      - any other non-empty stop_reason → None (unknown variant; don't guess)

      Callers emit None as JSON null so consumers can distinguish
      'unknown' from 'interrupted'.

      Args:
          entries: Parsed JSONL entries in file order.

      Returns:
          True for a clean natural end, False for a definitive interrupt
          signal, or None when the signal is genuinely indeterminate.
      """
      has_any_assistant: bool = False
      last_stop_reason: str | None = None
      prevented_continuation: bool = False

      for entry in entries:
          etype = entry.get("type")

          if etype == "assistant":
              has_any_assistant = True
              message = entry.get("message") or {}
              reason = message.get("stop_reason")
              # Update on every assistant entry — last one wins.
              last_stop_reason = reason if reason else None

          elif etype == "system":
              if entry.get("subtype") == "stop_hook_summary":
                  if entry.get("preventedContinuation") is True:
                      prevented_continuation = True

      # Resolution table — applied in priority order.
      if not has_any_assistant:
          return None
      if last_stop_reason is None:
          return None
      if prevented_continuation:
          return False
      if last_stop_reason == "end_turn":
          return True
      if last_stop_reason in ("max_tokens", "tool_use", "stop_sequence"):
          return False
      # Unknown non-empty stop_reason — don't guess.
      return None
  ```

  Wire it into `build_session_summary` by replacing the stub call. The call
  site is already correct from Task 3.1:

  ```python
      stopped_naturally = _derive_stopped_naturally(entries)
  ```

  No change to the call site is needed — only the function body changes.

- [ ] **Step 4: Run → confirm all five tests pass.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestStoppedNaturally -v
  ```

  Expected: all five tests pass. Then run the full suite:

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass.

- [ ] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): implement stoppedNaturally tri-state derivation

  Replaces the hardcoded True stub with real logic: walks entries once to
  track has_any_assistant, last_stop_reason, and prevented_continuation,
  then resolves per the spec's resolution table. None is emitted for
  genuinely indeterminate cases so consumers can distinguish unknown from
  interrupted.

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3.12: `--max-actions` Cap with Sentinel Truncation

When the action list exceeds `max_actions`, the first `max_actions - 1`
entries are kept and a sentinel string — `"… (<K> additional actions omitted)"
where `K` is the count of dropped entries — is appended. Setting
`max_actions=0` disables the cap entirely.

**Files:**
- Modify: `tests/test_session_summary.py`
- Modify: `claude_usage/cli/session_summary.py`

- [ ] **Step 1: Add three tests to a new `TestMaxActionsCap` class.**

  The `over_fifty_actions.jsonl` fixture from Phase 2 contains 55 assistant
  entries each with a distinct `Edit` target (`src/file_001.py` …
  `src/file_055.py`), producing 55 non-collapsible action records. These tests
  use that fixture.

  > **Implementer note:** if the fixture was generated with fewer than 51
  > distinct-target Bash calls, regenerate it using the Phase 2 script so that
  > it produces exactly 55 distinct Edit actions (as specified). The fixture
  > as written in Phase 2 Step 12 meets this requirement.

  ```python
  class TestMaxActionsCap:
      """Tests for _apply_max_actions_cap sentinel truncation."""

      def test_actions_truncated_at_default_cap(self) -> None:
          """Fixture with 55 distinct actions truncates to 50 at default cap.

          The last element must be the sentinel string matching the pattern
          '… (<K> additional actions omitted)' where K == 55 - 49 == 6.
          """
          from pathlib import Path

          from claude_usage.cli.session_summary import build_session_summary

          fixture = Path(
              "tests/fixtures/session_summaries/over_fifty_actions.jsonl"
          )
          # Default max_actions == 50.
          summary = build_session_summary(_parse_fixture(fixture))

          assert len(summary.actions) == 50
          assert summary.actions[-1].startswith("… (")
          assert summary.actions[-1].endswith("additional actions omitted)")

      def test_actions_respects_max_actions_override(self) -> None:
          """max_actions=5 keeps 4 real actions plus the sentinel."""
          from pathlib import Path

          from claude_usage.cli.session_summary import build_session_summary

          fixture = Path(
              "tests/fixtures/session_summaries/over_fifty_actions.jsonl"
          )
          summary = build_session_summary(_parse_fixture(fixture), max_actions=5)

          assert len(summary.actions) == 5
          assert summary.actions[-1].startswith("… (")
          assert summary.actions[-1].endswith("additional actions omitted)")
          # Sentinel must count the correct number of dropped actions.
          # 55 total, kept 4 = 49 + 1 sentinel → dropped = 55 - 4 = 51.
          assert "51" in summary.actions[-1]

      def test_actions_cap_zero_disables_truncation(self) -> None:
          """max_actions=0 disables the cap — all 55 actions are returned."""
          from pathlib import Path

          from claude_usage.cli.session_summary import build_session_summary

          fixture = Path(
              "tests/fixtures/session_summaries/over_fifty_actions.jsonl"
          )
          summary = build_session_summary(_parse_fixture(fixture), max_actions=0)

          assert len(summary.actions) == 55
          # No sentinel — every element is a real action string.
          assert not any(
              a.startswith("… (") for a in summary.actions
          )
  ```

- [ ] **Step 2: Run → confirm failures.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestMaxActionsCap -v
  ```

  Expected: `test_actions_truncated_at_default_cap` fails (the stub
  `_apply_max_actions_cap` from Task 3.1 takes `list[ActionRecord]` and
  converts to strings, but the current wiring may not correctly count 55
  actions after the other tasks have replaced stubs with real logic).
  `test_actions_respects_max_actions_override` and
  `test_actions_cap_zero_disables_truncation` also fail.

  If all three pass, inspect whether the fixture was properly generated with
  55 unique-target entries. Run:

  ```bash
  wc -l tests/fixtures/session_summaries/over_fifty_actions.jsonl
  ```

  Expected: 56 lines (1 user entry + 55 assistant entries). If fewer, the
  Phase 2 fixture must be regenerated.

- [ ] **Step 3: Implement `_apply_max_actions_cap` (standalone function) and
  wire it into `build_session_summary`.**

  The Task 3.1 stub named this function `_apply_max_actions_cap` but had it
  accept `list[ActionRecord]` and convert to strings internally. Refactor it
  to accept `list[str]` (already-rendered summaries) so the cap operates on
  the final string list, not raw records. This separation makes the function
  independently testable and aligns with the spec's data-flow diagram (step 5
  renders to strings, step 6 derives fields, step 7 assembles — the cap is
  applied after rendering).

  Replace the existing `_apply_max_actions_cap` in
  `claude_usage/cli/session_summary.py` with the following:

  ```python
  def _apply_max_actions_cap(
      actions: list[str],
      max_actions: int,
  ) -> list[str]:
      """Apply the --max-actions cap with sentinel truncation.

      When ``max_actions`` is 0, the cap is disabled and the full list is
      returned. Otherwise, if ``len(actions) > max_actions``, keep the
      first ``max_actions - 1`` entries and append a sentinel string of
      the form ``'… (<K> additional actions omitted)'`` where ``K`` is the
      number of dropped entries.

      Args:
          actions: Already-rendered past-tense action strings.
          max_actions: Cap value. 0 means no cap.

      Returns:
          The (possibly truncated) list of action strings.
      """
      if max_actions <= 0:
          return list(actions)
      if len(actions) <= max_actions:
          return list(actions)
      kept = actions[: max_actions - 1]
      dropped = len(actions) - (max_actions - 1)
      sentinel = f"… ({dropped} additional actions omitted)"
      return [*kept, sentinel]
  ```

  Update the call site in `build_session_summary` to pass the rendered string
  list instead of the raw `ActionRecord` list. The assembly snippet in
  `build_session_summary` becomes:

  ```python
      project = _derive_project(entries, project_slug_fallback)
      intent = _derive_intent(entries, project)
      records = _collect_tool_uses(entries)
      stopped_naturally = _derive_stopped_naturally(entries)

      # Render ActionRecords to strings, then apply the cap.
      action_strings_full = [r.summary for r in records]
      action_strings = _apply_max_actions_cap(
          action_strings_full, max_actions
      )

      return SessionSummary(
          project=project,
          intent=intent,
          actions=action_strings,
          stopped_naturally=stopped_naturally,
      )
  ```

- [ ] **Step 4: Run → confirm all three tests pass.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestMaxActionsCap -v
  ```

  Expected: all three pass. Then run the full suite:

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass. The refactor of `_apply_max_actions_cap` to accept
  `list[str]` does not break any earlier tests because the function was only
  called from `build_session_summary`.

- [ ] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): implement --max-actions cap with sentinel truncation

  _apply_max_actions_cap now operates on the already-rendered string list.
  max_actions=0 disables the cap; otherwise the first (N-1) actions are
  kept and a sentinel counting the dropped remainder is appended.

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

---

## Phase 4 — Error handling & exit codes

> **Goal:** Implement `run(args)` incrementally across four tasks. After Task 4.4
> the function is complete. Each task adds exactly one error path or the success
> wiring; the prior task's `NotImplementedError` sentinel marks the boundary so
> each step's test targets only the new behavior.

---

### Task 4.1 — Exit 1: IO failures from `open()` / iteration

**Files modified:**
- `tests/test_session_summary.py`
- `claude_usage/cli/session_summary.py`

---

- [ ] **Step 1: Write the failing test.**

  Add to `tests/test_session_summary.py` (inside `class TestErrorPaths` or at
  module level — implementer chooses; be consistent):

  ```python
  import subprocess
  import sys


  class TestErrorPaths:
      """Tests for non-zero exit codes and stdout/stderr discipline."""

      def test_missing_file_exits_1(self, tmp_path: pytest.fixture) -> None:
          """Exit 1 when --path points to a non-existent file.

          Asserts:
            - Exit code is EXIT_IO_FAILURE (1).
            - stdout is empty (no partial output).
            - stderr contains the expected message fragments.
          """
          nonexistent = tmp_path / "nonexistent.jsonl"
          result = subprocess.run(
              [
                  sys.executable, "-m", "claude_usage",
                  "session-summary",
                  "--path", str(nonexistent),
              ],
              capture_output=True,
              text=True,
          )
          assert result.returncode == 1
          assert result.stdout == ""
          assert "cannot read transcript at" in result.stderr
          assert str(nonexistent) in result.stderr
          # stderr should name one of the OSError subclass names
          assert any(
              name in result.stderr
              for name in (
                  "FileNotFoundError",
                  "OSError",
                  "No such file or directory",
              )
          )
  ```

- [ ] **Step 2: Run → confirm it fails.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestErrorPaths::test_missing_file_exits_1 -v
  ```

  Expected failure reason: `session-summary` subcommand does not exist yet, or
  `run()` raises `NotImplementedError`. Either way the exit code is not 1.

- [ ] **Step 3: Implement `read_transcript` + partial `run`.**

  In `claude_usage/cli/session_summary.py`, add the following helper and wire it
  into a partial `run`. The function returns a tuple so Task 4.3 can extend it
  without changing the call site. `run()` becomes the **single I/O site** —
  `build_session_summary` receives already-parsed `entries` and does no file I/O.

  ```python
  from __future__ import annotations

  import json
  import sys
  from pathlib import Path
  from typing import TYPE_CHECKING

  if TYPE_CHECKING:
      import argparse

  EXIT_OK = 0
  EXIT_IO_FAILURE = 1
  EXIT_NO_USER_TURNS = 2
  EXIT_NOT_JSONL = 3


  def read_transcript(
      path: Path,
  ) -> tuple[list[dict], int]:
      """Read and parse a JSONL transcript file.

      Opens *path*, iterates its lines, skips blanks, silently skips
      individual lines that fail ``json.loads``, and returns the
      successfully parsed entries together with the total non-blank
      line count.

      The non-blank count is used by ``run`` to distinguish an
      empty/whitespace-only file (exit 2) from a file that has content
      but none of it parses (exit 3).

      Args:
          path: Absolute or relative path to the JSONL transcript file.

      Returns:
          A 2-tuple ``(entries, non_blank_lines)`` where *entries* is
          the list of successfully parsed dicts and *non_blank_lines*
          is the count of non-empty, non-whitespace lines seen.

      Raises:
          OSError: Any subclass raised by ``open()`` or line iteration
              (``FileNotFoundError``, ``PermissionError``, etc.).
      """
      entries: list[dict] = []
      non_blank_lines = 0
      with path.open(encoding="utf-8") as fh:
          for raw in fh:
              stripped = raw.strip()
              if not stripped:
                  continue
              non_blank_lines += 1
              try:
                  entries.append(json.loads(stripped))
              except json.JSONDecodeError:
                  pass  # tolerate individual-line failures
      return entries, non_blank_lines


  def run(args: argparse.Namespace) -> int:
      """Entry point for the session-summary subcommand.

      Dispatches ``--path`` through the full parse → summarise → render
      pipeline, printing JSON (or text) to stdout on success and a
      single diagnostic line to stderr on failure.

      Args:
          args: Parsed CLI namespace.  Expected attributes:
              ``args.path`` (str), ``args.format`` (str),
              ``args.max_actions`` (int).

      Returns:
          Integer exit code (one of ``EXIT_OK``, ``EXIT_IO_FAILURE``,
          ``EXIT_NO_USER_TURNS``, ``EXIT_NOT_JSONL``).
      """
      path = Path(args.path)

      # ── Phase 4.1: IO failure ────────────────────────────────────────
      try:
          entries, non_blank_lines = read_transcript(path)
      except OSError as exc:
          print(
              f"session-summary: cannot read transcript at '{path}': "
              f"{type(exc).__name__}: {exc}",
              file=sys.stderr,
          )
          return EXIT_IO_FAILURE

      # Remaining logic lands in Tasks 4.2, 4.3, 4.4.
      raise NotImplementedError(
          "remaining logic lands in Tasks 4.2, 4.3, 4.4"
      )
  ```

  The `run` function must be registered in `claude_usage/__main__.py` as the
  handler for the `session-summary` subparser (that wiring was done in Phase 1).
  Confirm it is already wired; if not, add:

  ```python
  # inside build_parser() or wherever session-summary parser is set up:
  from claude_usage.cli import session_summary as ss_mod
  ss_parser.set_defaults(func=ss_mod.run)
  ```

- [ ] **Step 4: Run → confirm the test passes.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestErrorPaths::test_missing_file_exits_1 -v
  ```

  Expected: PASSED. The `OSError` from opening a nonexistent path propagates
  up through `read_transcript`, is caught, and the function returns exit code 1.

- [ ] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): implement read_transcript + exit-1 IO failure path

  Adds read_transcript() helper that opens --path, skips blank lines,
  tolerates per-line json.JSONDecodeError, and raises OSError naturally.
  run() wraps it; any OSError prints one stderr line and returns exit 1.

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 4.2 — Exit 2: no user turns (three sub-cases)

**Files modified:**
- `tests/test_session_summary.py`
- `claude_usage/cli/session_summary.py`

---

- [ ] **Step 1: Write the failing tests.**

  The three sub-cases each require a fixture file. Add fixture creation inline
  in the tests using `tmp_path` so no checked-in fixture is required (the
  checked-in `empty_no_user_turns.jsonl` fixture already exists for the
  subprocess test; use it where available, fall back to `tmp_path`):

  ```python
  import pytest


  class TestExitNoUserTurns:
      """Exit 2 when readable transcript has no external user turns."""

      def test_empty_session_exits_2(self) -> None:
          """Agent-setting / system-only transcript → exit 2."""
          fixture = (
              Path("tests/fixtures/session_summaries")
              / "empty_no_user_turns.jsonl"
          )
          result = subprocess.run(
              [
                  sys.executable, "-m", "claude_usage",
                  "session-summary",
                  "--path", str(fixture),
              ],
              capture_output=True,
              text=True,
          )
          assert result.returncode == 2
          assert result.stdout == ""
          assert "contains no user turns" in result.stderr

      def test_zero_byte_file_exits_2(self, tmp_path: pytest.fixture) -> None:
          """Zero-byte file → exit 2 (not exit 3)."""
          zero_byte = tmp_path / "zero_byte.jsonl"
          zero_byte.write_text("")
          result = subprocess.run(
              [
                  sys.executable, "-m", "claude_usage",
                  "session-summary",
                  "--path", str(zero_byte),
              ],
              capture_output=True,
              text=True,
          )
          assert result.returncode == 2
          assert result.stdout == ""
          assert "contains no user turns" in result.stderr

      def test_whitespace_only_file_exits_2(
          self, tmp_path: pytest.fixture
      ) -> None:
          """File with only blank lines → exit 2 (not exit 3)."""
          ws_only = tmp_path / "whitespace_only.jsonl"
          ws_only.write_text("\n   \n\t\n")
          result = subprocess.run(
              [
                  sys.executable, "-m", "claude_usage",
                  "session-summary",
                  "--path", str(ws_only),
              ],
              capture_output=True,
              text=True,
          )
          assert result.returncode == 2
          assert result.stdout == ""
          assert "contains no user turns" in result.stderr
  ```

- [ ] **Step 2: Run → confirm all three fail.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestExitNoUserTurns -v
  ```

  Expected failure: the subprocess exits with the `NotImplementedError`
  traceback, which produces a non-zero exit code (likely 1 from the exception),
  not exit code 2.

- [ ] **Step 3: Add the exit-2 branch to `run`.**

  Replace the `NotImplementedError` sentinel in `run` with the exit-2 check,
  leaving a new sentinel for the remaining path:

  ```python
      # ── Phase 4.2: no user turns ─────────────────────────────────────
      has_user_turns = any(
          entry.get("type") == "user"
          and entry.get("userType") == "external"
          for entry in entries
      )
      if not has_user_turns:
          print(
              f"session-summary: transcript '{path}' contains no user turns",
              file=sys.stderr,
          )
          return EXIT_NO_USER_TURNS

      # Remaining logic lands in Tasks 4.3, 4.4.
      raise NotImplementedError(
          "remaining logic lands in Tasks 4.3, 4.4"
      )
  ```

  **Why this covers all three sub-cases:** `read_transcript` returns an empty
  `entries` list for both zero-byte and whitespace-only files (no non-blank
  lines → nothing appended). An empty list fails the `any(...)` check →
  exits 2. The system-entries-only fixture also has no `userType == "external"`
  entries → same path.

- [ ] **Step 4: Run → confirm all three pass; re-run Task 4.1 test to confirm
  no regression.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestExitNoUserTurns \
               tests/test_session_summary.py::TestErrorPaths -v
  ```

  Expected: all four tests PASSED.

- [ ] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): implement exit-2 path for transcripts with no user turns

  Three sub-cases all reach exit 2: zero-byte file, whitespace-only file,
  and a transcript that parsed successfully but has no external user turns.
  Empty files return an empty entries list from read_transcript, so the
  has_user_turns check naturally handles them without a special branch.

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 4.3 — Exit 3: ≥1 non-blank line, every line fails `json.loads`

**Files modified:**
- `tests/test_session_summary.py`
- `claude_usage/cli/session_summary.py`

---

- [ ] **Step 1: Write the failing test.**

  ```python
  class TestExitNotJsonl:
      """Exit 3 when the file has content but none parses as JSONL."""

      def test_malformed_file_exits_3(self, tmp_path: pytest.fixture) -> None:
          """File with non-blank, non-JSON lines → exit 3.

          This is distinct from exit 2: bytes are present, attempted,
          and rejected — not an empty/whitespace file.
          """
          malformed = tmp_path / "all_malformed.jsonl"
          malformed.write_text(
              "this is not json\n"
              "{also not json\n"
              "definitely: not: json: either\n"
          )
          result = subprocess.run(
              [
                  sys.executable, "-m", "claude_usage",
                  "session-summary",
                  "--path", str(malformed),
              ],
              capture_output=True,
              text=True,
          )
          assert result.returncode == 3
          assert result.stdout == ""
          assert "is not valid JSONL" in result.stderr

      def test_empty_is_not_exit_3(self, tmp_path: pytest.fixture) -> None:
          """Zero-byte file must exit 2, not 3 — spec requirement.

          Exit 3 requires at least one non-blank line that was attempted.
          """
          empty = tmp_path / "empty.jsonl"
          empty.write_text("")
          result = subprocess.run(
              [
                  sys.executable, "-m", "claude_usage",
                  "session-summary",
                  "--path", str(empty),
              ],
              capture_output=True,
              text=True,
          )
          # Must be 2, not 3.
          assert result.returncode == 2
  ```

- [ ] **Step 2: Run → confirm both tests fail.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestExitNotJsonl -v
  ```

  Expected: both fail. `test_malformed_file_exits_3` exits from the
  `NotImplementedError` (not code 3); `test_empty_is_not_exit_3` may already
  pass (exit 2 is wired), but confirm.

- [ ] **Step 3: Add the exit-3 branch to `run`.**

  The `read_transcript` signature already returns `non_blank_lines`. Insert the
  exit-3 check between the IO catch and the exit-2 check. The critical ordering
  is: IO failure → malformed check → no-user-turns check → success path.

  Updated `run` body (replace existing try/except + two sentinels with):

  ```python
      path = Path(args.path)

      # ── Phase 4.1: IO failure ────────────────────────────────────────
      try:
          entries, non_blank_lines = read_transcript(path)
      except OSError as exc:
          print(
              f"session-summary: cannot read transcript at '{path}': "
              f"{type(exc).__name__}: {exc}",
              file=sys.stderr,
          )
          return EXIT_IO_FAILURE

      # ── Phase 4.3: not JSONL ─────────────────────────────────────────
      # Condition: file had parseable-attempt content (non_blank_lines > 0)
      # but zero entries survived json.loads.
      # NOTE: non_blank_lines == 0 means empty/whitespace-only → fall
      # through to the no-user-turns check (exit 2), not here.
      if not entries and non_blank_lines > 0:
          print(
              f"session-summary: transcript '{path}' is not valid JSONL",
              file=sys.stderr,
          )
          return EXIT_NOT_JSONL

      # ── Phase 4.2: no user turns ─────────────────────────────────────
      has_user_turns = any(
          entry.get("type") == "user"
          and entry.get("userType") == "external"
          for entry in entries
      )
      if not has_user_turns:
          print(
              f"session-summary: transcript '{path}' contains no user turns",
              file=sys.stderr,
          )
          return EXIT_NO_USER_TURNS

      # Remaining logic lands in Task 4.4.
      raise NotImplementedError("remaining logic lands in Task 4.4")
  ```

  **Why empty → exit 2 and not exit 3:** when `non_blank_lines == 0`, the exit-3
  condition `not entries and non_blank_lines > 0` is `False`. Execution falls
  through to the exit-2 check where `has_user_turns` is `False` (empty list).
  This matches the spec's explicit amendment: "Zero-byte and whitespace-only
  files fall under exit 2, not exit 3."

- [ ] **Step 4: Run → both new tests pass; re-run full test class suite.**

  ```bash
  uv run pytest \
      tests/test_session_summary.py::TestExitNotJsonl \
      tests/test_session_summary.py::TestExitNoUserTurns \
      tests/test_session_summary.py::TestErrorPaths \
      -v
  ```

  Expected: all six tests PASSED. Specifically confirm `test_empty_is_not_exit_3`
  exits 2 and `test_zero_byte_file_exits_2` still exits 2.

- [ ] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): implement exit-3 path for content that is not valid JSONL

  Exit 3 fires when non_blank_lines > 0 AND entries is empty — meaning
  the file had bytes that were attempted as JSON and all failed.
  Empty and whitespace-only files have non_blank_lines == 0, so they
  fall through to exit 2 as specified.

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 4.4 — stdout/stderr discipline: success path emits JSON only on stdout

**Files modified:**
- `tests/test_session_summary.py`
- `claude_usage/cli/session_summary.py`

---

- [ ] **Step 1: Write the failing tests.**

  ```python
  class TestStdoutStderrDiscipline:
      """stdout/stderr contract: errors → stderr only; success → stdout only."""

      def test_stdout_on_error_is_empty(self, tmp_path: pytest.fixture) -> None:
          """Any error path must emit nothing to stdout.

          Uses the missing-file path (exit 1) as a representative error.
          Asserts stdout is completely empty and stderr is exactly one line.
          """
          nonexistent = tmp_path / "missing.jsonl"
          result = subprocess.run(
              [
                  sys.executable, "-m", "claude_usage",
                  "session-summary",
                  "--path", str(nonexistent),
              ],
              capture_output=True,
              text=True,
          )
          assert result.stdout == ""
          # stderr must be exactly one non-empty line
          stderr_lines = [
              ln for ln in result.stderr.splitlines() if ln.strip()
          ]
          assert len(stderr_lines) == 1

      def test_stdout_on_success_is_pure_json(self) -> None:
          """Success path stdout is a parseable JSON document, nothing else.

          Asserts:
            - ``json.loads(stdout)`` succeeds without error.
            - stdout has exactly one trailing newline (no header text,
              no progress banners, no leading whitespace).
            - All four contract keys are present.
          """
          fixture = (
              Path("tests/fixtures/session_summaries") / "happy_path.jsonl"
          )
          result = subprocess.run(
              [
                  sys.executable, "-m", "claude_usage",
                  "session-summary",
                  "--path", str(fixture),
                  "--format", "json",
              ],
              capture_output=True,
              text=True,
          )
          assert result.returncode == 0
          # Must parse cleanly — no leading/trailing non-JSON text
          parsed = json.loads(result.stdout)
          assert set(parsed.keys()) >= {
              "project", "intent", "actions", "stoppedNaturally"
          }
          # Exactly one trailing newline — the JSON document ends cleanly
          assert result.stdout.endswith("\n")
          assert not result.stdout.endswith("\n\n")
  ```

- [ ] **Step 2: Run → confirm both tests fail.**

  ```bash
  uv run pytest \
      tests/test_session_summary.py::TestStdoutStderrDiscipline -v
  ```

  Expected: `test_stdout_on_success_is_pure_json` fails because the success
  path still hits `NotImplementedError`.

- [ ] **Step 3: Wire the success path and implement `render_json` minimally.**

  First, implement `render_json` and its private helper. The helper produces an
  explicitly ordered dict so key order in the JSON output is deterministic
  (Task 5.1 will add a dedicated key-order test to lock it down; the
  implementation is correct here already):

  ```python
  def _summary_to_dict(summary: SessionSummary) -> dict:
      """Convert a SessionSummary to an ordered dict matching the JSON contract.

      Key order matches the spec: project → intent → actions →
      stoppedNaturally.  Python 3.7+ preserves insertion order, so
      ``json.dumps`` will emit keys in this sequence.

      Args:
          summary: The session summary to convert.

      Returns:
          An ordered dict with camelCase keys ready for ``json.dumps``.
      """
      return {
          "project": summary.project,
          "intent": summary.intent,
          "actions": summary.actions,
          "stoppedNaturally": summary.stopped_naturally,
      }


  def render_json(summary: SessionSummary) -> str:
      """Render a SessionSummary as a pretty-printed JSON string.

      Uses ``indent=2`` and ``ensure_ascii=False`` per the output
      contract. Key order is deterministic: project, intent, actions,
      stoppedNaturally.

      Args:
          summary: The session summary dataclass instance.

      Returns:
          A JSON string, not terminated with a newline (the caller
          adds exactly one trailing newline before printing to stdout).
      """
      return json.dumps(
          _summary_to_dict(summary), indent=2, ensure_ascii=False
      )
  ```

  Then add a stub `render_text` to prevent `AttributeError` until Task 5.2:

  ```python
  def render_text(summary: SessionSummary) -> str:
      """Render a SessionSummary as a human-readable debug string.

      Args:
          summary: The session summary dataclass instance.

      Returns:
          Multi-line human-readable string.

      Raises:
          NotImplementedError: Until Task 5.2 is implemented.
      """
      raise NotImplementedError("implemented in Task 5.2")
  ```

  Now complete `run` by replacing the final `NotImplementedError` sentinel with
  the success path. Show the **complete `run` function** as it stands after
  Task 4.4 (consolidating 4.1 through 4.4):

  ```python
  def run(args: argparse.Namespace) -> int:
      """Entry point for the session-summary subcommand.

      Full pipeline: read → validate → summarise → render → emit.
      Writes JSON (or text) to stdout on success; one diagnostic line
      to stderr on any failure.  Never mixes stdout and stderr on the
      same code path.

      Args:
          args: Parsed CLI namespace with attributes:
              ``path`` (str), ``format`` (str), ``max_actions`` (int).

      Returns:
          Exit code: ``EXIT_OK`` (0), ``EXIT_IO_FAILURE`` (1),
          ``EXIT_NO_USER_TURNS`` (2), or ``EXIT_NOT_JSONL`` (3).
      """
      path = Path(args.path)

      # ── IO failure (exit 1) ──────────────────────────────────────────
      try:
          entries, non_blank_lines = read_transcript(path)
      except OSError as exc:
          print(
              f"session-summary: cannot read transcript at '{path}': "
              f"{type(exc).__name__}: {exc}",
              file=sys.stderr,
          )
          return EXIT_IO_FAILURE

      # ── Not JSONL (exit 3) ───────────────────────────────────────────
      if not entries and non_blank_lines > 0:
          print(
              f"session-summary: transcript '{path}' is not valid JSONL",
              file=sys.stderr,
          )
          return EXIT_NOT_JSONL

      # ── No user turns (exit 2) ───────────────────────────────────────
      has_user_turns = any(
          entry.get("type") == "user"
          and entry.get("userType") == "external"
          for entry in entries
      )
      if not has_user_turns:
          print(
              f"session-summary: transcript '{path}' contains no user turns",
              file=sys.stderr,
          )
          return EXIT_NO_USER_TURNS

      # ── Success path (exit 0) ────────────────────────────────────────
      # Non-fatal warning: malformed lines were skipped.
      skipped = non_blank_lines - len(entries)
      if skipped > 0:
          print(
              f"session-summary: skipped {skipped} malformed line(s)"
              f" in '{path}'",
              file=sys.stderr,
          )

      # run() is the single I/O site. Pass already-parsed entries so
      # build_session_summary performs no file I/O.
      slug = path.parent.name if path.parent.name else None
      summary = build_session_summary(
          entries,
          project_slug_fallback=slug,
          max_actions=args.max_actions,
      )

      if args.format == "json":
          output = render_json(summary)
      else:
          output = render_text(summary)

      # Exactly one trailing newline — the JSON/text contract.
      print(output, flush=True)
      return EXIT_OK
  ```

- [ ] **Step 4: Run → both new tests pass; run the full test file.**

  ```bash
  uv run pytest tests/test_session_summary.py -v
  ```

  Expected: all tests pass, including all prior error-path tests and the two
  new discipline tests.

- [ ] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): wire success path; implement render_json; stdout/stderr discipline

  run() is now complete for all four exit codes. Success path calls
  build_session_summary(), renders via render_json() or render_text()
  (latter stubbed until Task 5.2), and prints exactly one trailing
  newline. Non-fatal skipped-line warnings go to stderr only.

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Phase 5 — Output formats

---

### Task 5.1 — `render_json`: key order, camelCase, and tri-state values

**Files modified:**
- `tests/test_session_summary.py`
- `claude_usage/cli/session_summary.py`

---

- [ ] **Step 1: Write the tests.**

  ```python
  class TestRenderJson:
      """Unit tests for render_json() and _summary_to_dict()."""

      def _make_summary(
          self,
          stopped_naturally: bool | None = True,
      ) -> SessionSummary:
          """Factory for a minimal SessionSummary for render tests."""
          return SessionSummary(
              project="my-project",
              intent="Test the renderer",
              actions=["Edited foo.py", "Ran pytest"],
              stopped_naturally=stopped_naturally,
          )

      def test_render_json_key_order_and_camelcase(self) -> None:
          """Keys appear in contract order: project, intent, actions,
          stoppedNaturally; camelCase is used for stoppedNaturally."""
          summary = self._make_summary(stopped_naturally=True)
          output = render_json(summary)
          parsed = json.loads(output)
          keys = list(parsed.keys())
          assert keys == ["project", "intent", "actions", "stoppedNaturally"]

      def test_render_json_indented_two_spaces(self) -> None:
          """Output uses indent=2 (spec: pretty-printed)."""
          summary = self._make_summary()
          output = render_json(summary)
          # A two-space-indented JSON will have lines like '  "project"'
          assert '  "project"' in output

      def test_render_json_no_trailing_whitespace_per_line(self) -> None:
          """No line ends with trailing whitespace."""
          summary = self._make_summary()
          output = render_json(summary)
          for line in output.splitlines():
              assert line == line.rstrip(), (
                  f"Trailing whitespace on line: {line!r}"
              )

      def test_render_json_handles_tri_state_true(self) -> None:
          """stopped_naturally=True → JSON literal ``true``."""
          output = render_json(self._make_summary(stopped_naturally=True))
          assert '"stoppedNaturally": true' in output

      def test_render_json_handles_tri_state_false(self) -> None:
          """stopped_naturally=False → JSON literal ``false``."""
          output = render_json(self._make_summary(stopped_naturally=False))
          assert '"stoppedNaturally": false' in output

      def test_render_json_handles_tri_state_none(self) -> None:
          """stopped_naturally=None → JSON literal ``null``."""
          output = render_json(self._make_summary(stopped_naturally=None))
          assert '"stoppedNaturally": null' in output

      def test_render_json_does_not_add_trailing_newline(self) -> None:
          """render_json returns the bare document; run() adds the newline."""
          output = render_json(self._make_summary())
          assert not output.endswith("\n")
  ```

- [ ] **Step 2: Run → confirm results.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestRenderJson -v
  ```

  Many of these tests likely already pass from the Task 4.4 implementation.
  If all pass, the tests still serve their purpose: they lock down the
  invariants so a future refactor cannot break them silently.

- [ ] **Step 3: Formalize `render_json` and `_summary_to_dict`.**

  The implementations written in Task 4.4 are already correct. Confirm the
  functions have full Google-style docstrings (added in Task 4.4). If any
  docstring is missing, add it now. No logic changes are needed.

  The finalised pair (duplicated here for clarity, since this is the task that
  locks them down with tests):

  ```python
  def _summary_to_dict(summary: SessionSummary) -> dict:
      """Convert a SessionSummary to an ordered dict matching the JSON contract.

      Key order matches the spec: project → intent → actions →
      stoppedNaturally.  Python 3.7+ preserves dict insertion order,
      making ``json.dumps`` output deterministic across runs.

      Args:
          summary: The session summary dataclass instance to convert.

      Returns:
          An ordered dict with camelCase keys ready for ``json.dumps``.
          Keys: ``project``, ``intent``, ``actions``,
          ``stoppedNaturally``.
      """
      return {
          "project": summary.project,
          "intent": summary.intent,
          "actions": summary.actions,
          "stoppedNaturally": summary.stopped_naturally,
      }


  def render_json(summary: SessionSummary) -> str:
      """Render a SessionSummary as a pretty-printed JSON string.

      Produces the exact wire format consumed by the ``/whats-next``
      skill.  Uses ``indent=2`` and ``ensure_ascii=False`` per spec.
      Key order is deterministic: project, intent, actions,
      stoppedNaturally.

      Does **not** append a trailing newline — the caller (``run``)
      adds exactly one before printing to stdout, ensuring the
      stdout/stderr discipline invariant.

      Args:
          summary: The session summary dataclass instance.

      Returns:
          A JSON string without a trailing newline.
      """
      return json.dumps(
          _summary_to_dict(summary), indent=2, ensure_ascii=False
      )
  ```

- [ ] **Step 4: Run → all `TestRenderJson` tests pass; run full suite.**

  ```bash
  uv run pytest tests/test_session_summary.py -v
  ```

  Expected: all tests pass.

- [ ] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  test(session-summary): lock down render_json key order, camelCase, tri-state

  Seven unit tests cover: key ordering, two-space indent, no trailing
  whitespace per line, and all three stoppedNaturally values (true /
  false / null). render_json does not add a trailing newline — run()
  owns that responsibility.

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 5.2 — `render_text`: human-readable debug view

**Files modified:**
- `tests/test_session_summary.py`
- `claude_usage/cli/session_summary.py`

---

- [ ] **Step 1: Write the failing tests.**

  ```python
  class TestRenderText:
      """Unit tests for render_text() human-readable debug view."""

      def _make_summary(
          self,
          stopped_naturally: bool | None = True,
          actions: list[str] | None = None,
      ) -> SessionSummary:
          """Factory for SessionSummary instances used in render_text tests."""
          return SessionSummary(
              project="my-project",
              intent="Build something useful",
              actions=actions if actions is not None
                  else ["Edited foo.py", "Ran pytest"],
              stopped_naturally=stopped_naturally,
          )

      def test_render_text_happy_path(self) -> None:
          """Full debug-view string matches expected template."""
          summary = self._make_summary(stopped_naturally=True)
          output = render_text(summary)
          assert "Project: my-project" in output
          assert "Intent: Build something useful" in output
          assert "Stopped naturally: yes" in output
          assert "Actions:" in output
          assert "  - Edited foo.py" in output
          assert "  - Ran pytest" in output

      def test_render_text_stopped_naturally_true(self) -> None:
          """True → 'yes'."""
          output = render_text(self._make_summary(stopped_naturally=True))
          assert "Stopped naturally: yes" in output

      def test_render_text_stopped_naturally_false(self) -> None:
          """False → 'no'."""
          output = render_text(self._make_summary(stopped_naturally=False))
          assert "Stopped naturally: no" in output

      def test_render_text_stopped_naturally_none(self) -> None:
          """None → 'unknown'."""
          output = render_text(self._make_summary(stopped_naturally=None))
          assert "Stopped naturally: unknown" in output

      def test_render_text_empty_actions(self) -> None:
          """Empty actions list → 'Actions:' section present, no bullets."""
          summary = self._make_summary(actions=[])
          output = render_text(summary)
          assert "Actions:" in output
          assert "  - " not in output
  ```

- [ ] **Step 2: Run → confirm all five tests fail.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestRenderText -v
  ```

  Expected: all fail with `NotImplementedError` from the Task 4.4 stub.

- [ ] **Step 3: Implement `render_text` and `_tri_state_to_word`.**

  ```python
  def _tri_state_to_word(value: bool | None) -> str:
      """Convert a tri-state boolean to a display word.

      Args:
          value: ``True``, ``False``, or ``None``.

      Returns:
          ``"yes"`` for ``True``, ``"no"`` for ``False``,
          ``"unknown"`` for ``None``.
      """
      if value is True:
          return "yes"
      if value is False:
          return "no"
      return "unknown"


  def render_text(summary: SessionSummary) -> str:
      """Render a SessionSummary as a human-readable debug string.

      Intended for ``--format text`` — not consumed by ``/whats-next``.
      Useful for manual inspection and debugging.

      Output template::

          Project: {project}
          Intent: {intent}
          Stopped naturally: {yes|no|unknown}

          Actions:
            - {action 1}
            - {action 2}
            ...

      Args:
          summary: The session summary dataclass instance.

      Returns:
          Multi-line string.  Does not end with a trailing newline —
          the caller (``run``) adds exactly one.
      """
      lines = [
          f"Project: {summary.project}",
          f"Intent: {summary.intent}",
          f"Stopped naturally: {_tri_state_to_word(summary.stopped_naturally)}",
          "",
          "Actions:",
      ]
      for action in summary.actions:
          lines.append(f"  - {action}")
      return "\n".join(lines)
  ```

- [ ] **Step 4: Run → all five tests pass; run full suite.**

  ```bash
  uv run pytest tests/test_session_summary.py -v
  ```

  Expected: all tests pass.

- [ ] **Step 5: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add claude_usage/cli/session_summary.py \
          tests/test_session_summary.py
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  feat(session-summary): implement render_text with tri-state word mapping

  render_text() produces a human-readable debug view for --format text.
  _tri_state_to_word() maps True/False/None → yes/no/unknown.
  Five unit tests cover: happy path, each tri-state word, empty actions.

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Phase 6 — Polish

---

### Task 6.1 — README update: document `session-summary` and CLI migration

**Files modified:**
- `README.md`

---

- [ ] **Step 1: Read the current README and identify the Usage section.**

  The current README (as of plan authoring) has a `## Usage` section showing
  `python -m claude_usage` invocations with bare flags. After the Phase 1
  CLI refactor, those flags move under the `dashboard` subcommand.

  Add the following content. Insert it **immediately after the existing
  `## Usage` section**, before `## Dashboard`:

  ````markdown
  ## Subcommands

  After the subparser refactor, all functionality is accessed through named
  subcommands. Bare `claude-usage` prints help and exits 0.

  ### `dashboard` — interactive HTML dashboard

  ```bash
  # Default: last 7 days, opens in browser
  claude-usage dashboard

  # Rolling window matching Claude billing buckets
  claude-usage dashboard --window 5h
  claude-usage dashboard --window 7d

  # Custom date range
  claude-usage dashboard --from 2026-04-01 --to 2026-04-09

  # Output to file instead of opening browser
  claude-usage dashboard --output report.html --no-open

  # Custom Claude data directory
  claude-usage dashboard --data-dir "D:\other\.claude"

  # Set budget limits for gauge percentages
  claude-usage dashboard --limit-5h 600000 --limit-7d 4000000 \
      --limit-sonnet-7d 2000000

  # Emit JSON (for scripting / CI)
  claude-usage dashboard --format json
  ```

  All flags are unchanged from the pre-refactor form — only their location
  moved (now under the `dashboard` subparser).

  ### `session-summary` — deterministic session recap (new in v0.2.0)

  Reads a single Claude Code transcript JSONL file and emits a structured
  JSON summary suitable for consumption by the `/whats-next` skill or any
  other tool that needs to know what a session did.

  ```bash
  claude-usage session-summary --path ~/.claude/projects/<hash>/<session>.jsonl
  ```

  **Flags:**

  | Flag | Default | Description |
  |---|---|---|
  | `--path PATH` | *(required)* | Path to the transcript JSONL file |
  | `--format {json,text}` | `json` | Output format. `json` is the machine-readable contract; `text` is a human-readable debug view |
  | `--max-actions N` | `50` | Cap on emitted actions. `0` disables the cap |

  **Sample output (`--format json`):**

  ```json
  {
    "project": "claude-usage",
    "intent": "Implement the session-summary subcommand for the /whats-next skill",
    "actions": [
      "Edited claude_usage/cli/session_summary.py",
      "Created tests/test_session_summary.py",
      "Ran pytest tests/test_session_summary.py -x",
      "Dispatched code-reviewer sub-agent"
    ],
    "stoppedNaturally": true
  }
  ```

  **Exit codes:**

  | Code | Meaning | stderr |
  |---|---|---|
  | `0` | Success — JSON written to stdout | *(silent)* |
  | `1` | IO failure reading `--path` (file missing, permission denied, etc.) | `session-summary: cannot read transcript at '<path>': <OSError class>: <message>` |
  | `2` | File readable but contains no external user turns (empty session, zero-byte file, whitespace-only file) | `session-summary: transcript '<path>' contains no user turns` |
  | `3` | File has content but none of it parses as JSONL | `session-summary: transcript '<path>' is not valid JSONL` |

  On any non-zero exit, stdout is empty and stderr contains exactly one line.

  ### Migration note

  The old flag-only form **no longer works** after v0.2.0:

  ```bash
  # REMOVED — will print help and exit 0, not run the dashboard
  claude-usage --format json

  # CORRECT — migrate all callers to:
  claude-usage dashboard --format json
  ```

  Any script, skill, or CI step that invokes `claude-usage` with bare flags
  (no subcommand) must be updated to use `claude-usage dashboard [flags]`.
  ````

- [ ] **Step 2: Version bump in `pyproject.toml`.**

  The project currently has `version = "0.1.0"`. The subparser refactor and
  new subcommand constitute a minor-version change (new public interface,
  backward-incompatible CLI change for bare-flag callers). Bump to `0.2.0`:

  ```toml
  version = "0.2.0"
  ```

- [ ] **Step 3: Commit.**

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add README.md pyproject.toml
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "$(cat <<'EOF'
  docs: document session-summary subcommand and CLI migration in README

  Adds Subcommands section covering dashboard and session-summary flags,
  sample JSON output, exit-code table, and migration note for callers
  using the pre-refactor bare-flag form. Bumps version to 0.2.0 to
  signal the breaking CLI change.

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 6.2 — Final verification: full suite green

**Files modified:** none (verification only; small fixup commits if needed).

---

- [ ] **Step 1: Run the full test suite.**

  ```bash
  uv run pytest -v
  ```

  Expected: all tests pass — both pre-existing dashboard/aggregator tests and
  all new `test_session_summary.py` tests. Zero failures, zero errors, zero
  skips.

  If any test fails, diagnose and fix in the same step before proceeding. If
  the fix touches implementation files, commit with:
  `fix(session-summary): <description> (part of #19)`.

- [ ] **Step 2: Lint check.**

  ```bash
  uv run ruff check .
  ```

  Expected: zero errors. If any are found, fix inline:

  ```bash
  uv run ruff check --fix .
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add -u
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "chore: resolve ruff lint findings in session-summary module

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
  ```

- [ ] **Step 3: Format check.**

  ```bash
  uv run ruff format --check .
  ```

  Expected: zero diff. If a diff is reported:

  ```bash
  uv run ruff format .
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      add -u
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan \
      commit -m "chore: apply ruff format to session-summary module

  part of #19

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
  ```

- [ ] **Step 4: Manual CLI sanity check.**

  Run each of the following and confirm the described output:

  ```bash
  # 1. Bare invocation → help text, exit 0
  uv run claude-usage
  # Expected: usage/help text listing 'dashboard' and 'session-summary'
  # subcommands. Exit 0.

  # 2. Dashboard subcommand help → shows all dashboard flags
  uv run claude-usage dashboard --help
  # Expected: --data-dir, --from, --to, --window, --output, --no-open,
  # --limit-5h, --limit-7d, --limit-sonnet-7d, --format listed.

  # 3. Session-summary help → shows session-summary flags
  uv run claude-usage session-summary --help
  # Expected: --path (required), --format {json,text}, --max-actions.

  # 4. Happy-path invocation → valid JSON on stdout, exit 0
  uv run claude-usage session-summary \
      --path tests/fixtures/session_summaries/happy_path.jsonl
  # Expected: pretty-printed JSON with keys project, intent, actions,
  # stoppedNaturally. No other text on stdout. Exit 0.

  # 5. Missing-file invocation → one-line stderr, empty stdout, exit 1
  uv run claude-usage session-summary --path /tmp/nonexistent.jsonl
  # Expected: stdout empty, stderr = exactly one line containing
  # "cannot read transcript at '/tmp/nonexistent.jsonl'". Exit 1.
  ```

- [ ] **Step 5: No-op commit gate.**

  If Steps 1–3 required no fixes, no commit is needed. If fixes were made,
  they are already committed per Steps 2–3 above. Either way, run a final
  status check:

  ```bash
  git -C /i/other/claude-usage/.worktrees/docs-session-summary-plan status
  ```

  Expected: "nothing to commit, working tree clean."

---

## Acceptance Criteria Coverage Matrix

### Spec test matrix → plan tasks

Every row from the spec's minimum test matrix (section "Testing → Minimum test
matrix") maps to one or more plan tasks below. No row is unmapped.

| Spec test ID | Fixture / scenario | Plan task(s) |
|---|---|---|
| `test_happy_path_emits_contract` | Real session with edits+bash+agent | 3.1 + 4.4 + 5.1 |
| `test_missing_file_exits_1` | Nonexistent path | 4.1 |
| `test_empty_session_exits_2` (first sub-case) | Agent-setting / system-only transcript | 4.2 |
| `test_zero_byte_file_exits_2` (second sub-case, implicit) | Zero-byte file | 4.2 |
| `test_whitespace_only_file_exits_2` (third sub-case, implicit) | Whitespace-only file | 4.2 |
| `test_malformed_file_exits_3` | Non-blank lines, all unparseable | 4.3 |
| `test_empty_is_not_exit_3` (guard) | Zero-byte file must exit 2 not 3 | 4.3 |
| `test_existing_dashboard_unchanged` | CLI snapshot comparison | 1.1 + 1.2 + 0.1 |
| `test_action_classification_skips_reads` | User turn + Read/Grep/Glob only | 3.3 |
| `test_consecutive_edits_collapse` | 3 Edits to same file | 3.8 |
| `test_intent_falls_back_for_slash_command_only` | Pure slash-command session | 3.5 |
| `test_stopped_naturally_false_on_max_tokens` | Final stop_reason=max_tokens | 3.10 |
| `test_stopped_naturally_false_on_prevented_continuation` | system entry with preventedContinuation=true | 3.10 |
| `test_stopped_naturally_null_on_no_assistant_turns` | User turns, zero assistant entries | 3.11 |
| `test_stopped_naturally_null_on_missing_stop_reason` | Final assistant entry lacks stop_reason | 3.11 |
| `test_actions_truncated_at_default_cap` | Transcript > 50 distinct actions | 3.12 |
| `test_actions_respects_max_actions_override` | Same, invoked with --max-actions 5 | 3.12 |
| `test_actions_cap_zero_disables_truncation` | Same, invoked with --max-actions 0 | 3.12 |
| `test_stdout_on_error_is_empty` | Missing-file path (exit 1) | 4.4 |
| `test_stdout_on_success_is_pure_json` | Happy-path fixture | 4.4 |
| `test_render_json_key_order_and_camelcase` | Constructed SessionSummary | 5.1 |
| `test_render_json_handles_tri_state` (three variants) | True / False / None | 5.1 |
| `test_render_text_happy_path` | Constructed SessionSummary | 5.2 |
| `test_render_text_stopped_naturally_tri_state_words` (three variants) | yes / no / unknown | 5.2 |

**No unmapped spec test rows.** All 17 spec test IDs (including the
three sub-cases of `test_empty_session_exits_2`) are covered.

---

### Issue #19 acceptance criteria → plan tasks

Every AC item from the spec's "Acceptance criteria (from issue #19)" section
maps to one or more plan tasks below.

| Issue #19 AC | Plan task(s) | Notes |
|---|---|---|
| `claude-usage session-summary --path <valid-jsonl> --format json` exits 0 and emits JSON matching contract | 3.1 + 4.4 + 5.1 | 3.1 builds the summary; 4.4 wires the success path and render_json call; 5.1 locks down key order and camelCase |
| `claude-usage session-summary --path <missing>` exits 1 with one-line stderr | 4.1 + 4.4 | 4.1 implements read_transcript + exit-1 branch; 4.4 completes run() and tests stdout/stderr discipline |
| `claude-usage session-summary --path <empty-session.jsonl>` exits 2 | 4.2 | Covers all three sub-cases: system-entries-only, zero-byte, whitespace-only |
| `claude-usage session-summary --path <malformed.jsonl>` exits 3 | 4.3 | Includes guard test ensuring empty files do not exit 3 |
| Existing CLI invocations (dashboard behavior) continue to work (modulo explicit migration to `dashboard` subcommand) | 0.1 + 1.1 + 1.2 | Phase 0 captures the pre-refactor snapshot; Phase 1 moves the dashboard body and verifies snapshot parity |
| At least one test covers each exit code path | 4.1 (exit 1) + 4.2 (exit 2) + 4.3 (exit 3) + 4.4 (exit 0 success test) | Each exit code has a dedicated test class |
| `/whats-next` produces a populated Recent Work section when run against a repo with no `save-context` file but a recent transcript | Post-merge consumer-side work (out of scope for this plan) | Tracked in spec section "Acceptance criteria" as "The last item is a consumer-side validation — testable only after the consumer's invocation path is migrated" |

**No unmapped AC items.** Six of the seven ACs are covered by plan tasks;
the seventh is explicitly deferred to consumer-side post-merge work as
documented in the spec.

---

## Self-Review

> This section records the results of the author's due-diligence pass
> performed before committing the final plan document. The three checks below
> correspond to the `superpowers:writing-plans` self-review requirements.

### 1. Spec coverage

Walk of the spec's section headings against plan tasks:

| Spec section | Covered by |
|---|---|
| Context | Background / goal statement in plan header |
| Goals (1–5) | Goals 1–3: Phase 1 + Phase 3; Goal 4: Phase 1; Goal 5: Phase 0 + Task 1.2 |
| Non-goals | Acknowledged in Phase 0 note; no tasks contradict them |
| CLI grammar (`dashboard` + `session-summary`) | Phase 1 (dashboard subparser), Phase 1 (session-summary subparser + flags) |
| Grammar rules (no implicit default, old form removed, --format differences, --max-actions) | Tasks 1.1, 1.2, 3.12 |
| Module layout (before / after) | Phase 1 + Phase 2 fixture/dataclass tasks |
| Output contract (JSON shape, invariants) | Tasks 3.1 (happy path), 5.1 (render_json locks down shape) |
| Key order and formatting | Task 5.1 |
| Summarization pipeline (steps 1–7) | Tasks 3.2 (walk), 3.3–3.9 (classify/collapse/render), 3.10–3.11 (stopped_naturally), 3.5–3.6 (intent/project derivation) |
| Tool-use classification table | Task 3.3 |
| MCP tool name normalization | Task 3.7 |
| Intent derivation (content extraction rules) | Task 3.5 |
| Project derivation (cwd field) | Task 3.4 |
| `stoppedNaturally` tri-state | Tasks 3.10, 3.11 |
| Action collapse | Task 3.8 |
| Action rendering (past-tense templates) | Task 3.9 |
| `--max-actions` cap and sentinel | Task 3.12 |
| Error handling & exit codes (all four codes) | Tasks 4.1, 4.2, 4.3, 4.4 |
| stdout/stderr discipline | Task 4.4 |
| Testing — fixture strategy | Phase 2 + Task 0.1 |
| Testing — minimum test matrix (17 rows) | AC matrix above, all mapped |
| Acceptance criteria (7 items) | AC matrix above, all mapped |

**Spec coverage: complete — every section maps to one or more tasks (see AC
matrix above).**

### 2. Placeholder scan

Searched the plan text for: `TBD`, `TODO`, `implement later`, `similar to`,
`add appropriate`, `handle edge cases`.

- **"implement later"** appears once as part of the `NotImplementedError`
  message `"implemented in Task 5.2"` — this is intentional scaffolding
  language inside a code block, not a deferred plan item. The actual
  implementation is written in Task 5.2 immediately after.
- **No other placeholder terms found.**

**Placeholder scan: clean. No deferred or vague task bodies.**

### 3. Type and name consistency scan

Cross-check of all identifiers across every task against the Naming
cross-reference table at the top of the plan:

| Identifier | Declared in naming table | Used consistently | Notes |
|---|---|---|---|
| `ActionRecord` | Yes — `dataclass(frozen=True)` with `type`, `raw_tool`, `target`, `summary` | Tasks 3.3, 3.7, 3.8, 3.9 | Consistent |
| `SessionSummary` | Yes — `dataclass(frozen=True)` with `project`, `intent`, `actions`, `stopped_naturally` | Tasks 3.1, 3.4–3.12, 4.4, 5.1, 5.2 | Consistent |
| `build_session_summary` | `(entries: list[dict], *, project_slug_fallback: str \| None = None, max_actions: int = DEFAULT_MAX_ACTIONS) -> SessionSummary` | Task 3.1 (stub), 3.12 (final body), 4.4 (called in run — single I/O site) | Consistent |
| `render_json` | `(summary: SessionSummary) -> str` | Tasks 4.4, 5.1 | Consistent |
| `render_text` | `(summary: SessionSummary) -> str` | Tasks 4.4 (stub), 5.2 (impl) | Consistent |
| `run` | `(args: argparse.Namespace) -> int` | Tasks 4.1–4.4 | Consistent |
| `read_transcript` | Not in naming table (private helper, introduced Task 4.1) | Tasks 4.1, 4.2, 4.3, 4.4 | Signature `(path: Path) -> tuple[list[dict], int]` — stable across all tasks |
| `_summary_to_dict` | Not in naming table (private helper, introduced Task 4.4) | Tasks 4.4, 5.1 | Signature `(summary: SessionSummary) -> dict` — consistent |
| `_tri_state_to_word` | Not in naming table (private helper, introduced Task 5.2) | Task 5.2 | Signature `(value: bool \| None) -> str` — consistent |
| `EXIT_OK`, `EXIT_IO_FAILURE`, `EXIT_NO_USER_TURNS`, `EXIT_NOT_JSONL` | Yes — `0`, `1`, `2`, `3` | Tasks 4.1–4.4, AC matrix | Consistent |
| `stopped_naturally` (Python) → `stoppedNaturally` (JSON) | Yes — naming table explicitly documents the mapping | Tasks 3.11, 5.1 (`_summary_to_dict`), 5.2 (`_tri_state_to_word`) | Consistent |

**Type/name consistency: clean. All public identifiers match the naming
cross-reference. Three private helpers introduced in Phase 4–5 are
internally consistent across all tasks that reference them.**

### Self-review outcome

All three checks pass:

1. **Spec coverage: complete.** Every spec section heading maps to at least
   one task. The AC matrix confirms full traceability in both directions
   (spec test IDs → tasks, issue ACs → tasks).
2. **Placeholder scan: clean.** One intentional `NotImplementedError` stub
   message appears as planned scaffolding; no deferred or vague task bodies.
3. **Type/name consistency: clean.** Ten identifiers (public + private)
   checked; all are consistent across their declaring task and every
   subsequent task that references them.

---

> **Post-plan signature refactor:** `build_session_summary` now takes
> pre-parsed `entries: list[dict]` rather than `path: Path`.
> `run()` is the single I/O site via `read_transcript`. This eliminates
> a double-open that would have shipped with the v1 implementation —
> `read_transcript` was already called in `run()` for the exit-2/exit-3
> validation checks, so `build_session_summary` would have silently
> re-opened and re-parsed the same file on the success path. The refactored
> shape keeps I/O concerns in `run()` and makes `build_session_summary` a
> pure function suitable for direct unit-testing without touching the
> filesystem (tests now use `_parse_fixture` instead of passing a file path).
