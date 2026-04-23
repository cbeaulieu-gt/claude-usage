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
| `build_session_summary` | `(path: Path, max_actions: int = 50) -> SessionSummary` |
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

- [ ] **Step 1: Construct the minimal input fixture tree.**

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

- [ ] **Step 2: Capture the baseline snapshot.**

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

- [ ] **Step 3: Commit the baseline fixtures.**

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

- [ ] **Step 1: Create `claude_usage/cli/__init__.py`.**

  Exact file contents:

  ```python
  """CLI subcommands for claude-usage."""
  ```

  That is the entire file — one docstring line, nothing else.

- [ ] **Step 2: Create `claude_usage/cli/dashboard.py`.**

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

- [ ] **Step 3: Run existing tests to confirm nothing is broken.**

  ```bash
  uv run pytest -x
  ```

  Expected: all tests pass. The old `main()` in `__main__.py` is still present (import surface
  intact); the new `cli/dashboard.py` is now importable but not yet wired to anything.

- [ ] **Step 4: Commit.**

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

- [ ] **Step 1: Write the failing test first.**

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

- [ ] **Step 2: Run the test — confirm it fails.**

  ```bash
  uv run pytest tests/test_cli_subcommands.py -x -v
  ```

  Expected failures:
  - `test_bare_invocation_exits_0_and_shows_subcommands` — current CLI has no subparsers, output
    will not contain "session-summary".
  - `test_old_flag_only_form_exits_nonzero` — current CLI accepts `--format json` and exits 0.

- [ ] **Step 3: Create the `session_summary.py` stub.**

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

- [ ] **Step 4: Rewrite `claude_usage/__main__.py`.**

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

- [ ] **Step 5: Run the full test suite.**

  ```bash
  uv run pytest -x
  ```

  Expected: the three new tests in `test_cli_subcommands.py` pass. All pre-existing tests
  continue to pass. (Any test that previously invoked the old `main()` directly via
  `subprocess` will now hit the subparser dispatcher — confirm those still pass or update
  their invocation to `claude-usage dashboard [flags]`.)

- [ ] **Step 6: Commit.**

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

- [ ] **Step 1: Write the snapshot regression test.**

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

- [ ] **Step 2: Run the test.**

  ```bash
  uv run pytest tests/test_dashboard_snapshot.py -v
  ```

  Expected: `test_existing_dashboard_unchanged` passes. The refactor was a verbatim body move;
  dashboard behavior is unchanged.

- [ ] **Step 3: Commit.**

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

- [ ] **Step 1: Create `tests/fixtures/sanitize_transcript.py`.**

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

- [ ] **Step 2: Create `tests/fixtures/session_summaries/happy_path.jsonl`.**

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

- [ ] **Step 3: Create `tests/fixtures/session_summaries/empty_no_user_turns.jsonl`.**

  Contains only agent-setting and system entries — zero external user turns.
  Used by `test_empty_session_exits_2`.

  ```jsonl
  {"type":"agent-setting","agentSetting":"orchestrator","timestamp":"2026-04-20T10:00:00.000Z","sessionId":"sess-empty","uuid":"s-001"}
  {"type":"system","subtype":"init","timestamp":"2026-04-20T10:00:01.000Z","sessionId":"sess-empty","uuid":"sys-001"}
  ```

- [ ] **Step 4: Create `tests/fixtures/session_summaries/all_malformed.jsonl`.**

  Every non-blank line fails `json.loads`. Used by `test_malformed_file_exits_3`.

  ```
  not json at all
  {broken json here
  {"unterminated":
  ```

  Write these three lines verbatim — no quotes around the block, these are
  the actual file contents.

- [ ] **Step 5: Create `tests/fixtures/session_summaries/slash_command_only.jsonl`.**

  The external user turn contains only the slash-command XML wrapper — no
  surviving text after stripping. Used by `test_intent_falls_back_for_slash_command_only`.

  ```jsonl
  {"type":"agent-setting","agentSetting":"orchestrator","timestamp":"2026-04-20T11:00:00.000Z","sessionId":"sess-slash","uuid":"s-001"}
  {"type":"user","message":{"role":"user","content":"<command-name>/project-review</command-name><command-args></command-args>"},"uuid":"u-001","timestamp":"2026-04-20T11:00:01.000Z","sessionId":"sess-slash","userType":"external","cwd":"/home/user/claude-usage"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Running project review."}],"model":"claude-sonnet-4-6","stop_reason":"end_turn","usage":{"input_tokens":20,"output_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-001","timestamp":"2026-04-20T11:00:02.000Z","sessionId":"sess-slash"}
  ```

- [ ] **Step 6: Create `tests/fixtures/session_summaries/zero_byte.jsonl`.**

  Zero-byte file. Create it with:

  ```bash
  touch tests/fixtures/session_summaries/zero_byte.jsonl
  ```

  The file must be committed as empty (zero bytes). Git will track it as long
  as the parent directory is tracked.

- [ ] **Step 7: Create `tests/fixtures/session_summaries/whitespace_only.jsonl`.**

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

- [ ] **Step 8: Create `tests/fixtures/session_summaries/max_tokens_stop.jsonl`.**

  Final assistant entry has `stop_reason: "max_tokens"`. Used by
  `test_stopped_naturally_false_on_max_tokens`.

  ```jsonl
  {"type":"user","message":{"role":"user","content":"Do a long task."},"uuid":"u-001","timestamp":"2026-04-20T12:00:00.000Z","sessionId":"sess-maxtok","userType":"external","cwd":"/home/user/claude-usage"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Working..."}],"model":"claude-sonnet-4-6","stop_reason":"max_tokens","usage":{"input_tokens":200,"output_tokens":1024,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-001","timestamp":"2026-04-20T12:00:10.000Z","sessionId":"sess-maxtok"}
  ```

- [ ] **Step 9: Create `tests/fixtures/session_summaries/prevented_continuation.jsonl`.**

  Includes a `type: "system"` entry with `subtype: "stop_hook_summary"` and
  `preventedContinuation: true`. Used by
  `test_stopped_naturally_false_on_prevented_continuation`.

  ```jsonl
  {"type":"user","message":{"role":"user","content":"Run the build."},"uuid":"u-001","timestamp":"2026-04-20T13:00:00.000Z","sessionId":"sess-prev","userType":"external","cwd":"/home/user/claude-usage"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Building..."}],"model":"claude-sonnet-4-6","stop_reason":"end_turn","usage":{"input_tokens":50,"output_tokens":10,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-001","timestamp":"2026-04-20T13:00:05.000Z","sessionId":"sess-prev"}
  {"type":"system","subtype":"stop_hook_summary","preventedContinuation":true,"timestamp":"2026-04-20T13:00:06.000Z","sessionId":"sess-prev","uuid":"sys-001"}
  ```

- [ ] **Step 10: Create `tests/fixtures/session_summaries/no_assistant_entries.jsonl`.**

  Has an external user turn but zero assistant entries. Used by
  `test_stopped_naturally_null_on_no_assistant_turns`.

  ```jsonl
  {"type":"user","message":{"role":"user","content":"Just a question, no response yet."},"uuid":"u-001","timestamp":"2026-04-20T14:00:00.000Z","sessionId":"sess-noassist","userType":"external","cwd":"/home/user/claude-usage"}
  ```

- [ ] **Step 11: Create `tests/fixtures/session_summaries/missing_stop_reason.jsonl`.**

  Final assistant entry has no `stop_reason` key in the message. Used by
  `test_stopped_naturally_null_on_missing_stop_reason`.

  ```jsonl
  {"type":"user","message":{"role":"user","content":"What is 2+2?"},"uuid":"u-001","timestamp":"2026-04-20T15:00:00.000Z","sessionId":"sess-nostop","userType":"external","cwd":"/home/user/claude-usage"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"4."}],"model":"claude-sonnet-4-6","usage":{"input_tokens":10,"output_tokens":2,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-001","timestamp":"2026-04-20T15:00:01.000Z","sessionId":"sess-nostop"}
  ```

- [ ] **Step 12: Create `tests/fixtures/session_summaries/over_fifty_actions.jsonl`.**

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

- [ ] **Step 13: Create `tests/fixtures/session_summaries/mcp_both_forms.jsonl`.**

  Contains two MCP tool-use entries — one plugin-scoped form and one direct
  form for the same logical server+method. Used by the MCP classification
  task (Task 3.6 in the next pass).

  ```jsonl
  {"type":"user","message":{"role":"user","content":"Create a GitHub issue and fetch docs."},"uuid":"u-001","timestamp":"2026-04-20T17:00:00.000Z","sessionId":"sess-mcp","userType":"external","cwd":"/home/user/claude-usage"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"tu-001","name":"mcp__plugin_github_github__create_issue","input":{"title":"Test issue","body":"body text"}}],"model":"claude-sonnet-4-6","stop_reason":"tool_use","usage":{"input_tokens":60,"output_tokens":20,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-001","timestamp":"2026-04-20T17:00:01.000Z","sessionId":"sess-mcp"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"tu-002","name":"mcp__github__create_issue","input":{"title":"Another issue","body":"more text"}}],"model":"claude-sonnet-4-6","stop_reason":"tool_use","usage":{"input_tokens":65,"output_tokens":20,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-002","timestamp":"2026-04-20T17:00:02.000Z","sessionId":"sess-mcp"}
  {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Done."}],"model":"claude-sonnet-4-6","stop_reason":"end_turn","usage":{"input_tokens":70,"output_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"uuid":"a-003","timestamp":"2026-04-20T17:00:05.000Z","sessionId":"sess-mcp"}
  ```

- [ ] **Step 14: Create `tests/fixtures/session_summaries/consecutive_edits_same_file.jsonl`.**

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

- [ ] **Step 15: Commit.**

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

- [ ] **Step 1: Replace the stub with full module scaffolding.**

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
      path: Path,
      max_actions: int = DEFAULT_MAX_ACTIONS,
  ) -> SessionSummary:
      """Derive a SessionSummary by walking a transcript JSONL file once.

      Args:
          path: Absolute or relative path to the JSONL transcript file.
          max_actions: Soft cap on the number of emitted action strings.
              When 0, the cap is disabled and all actions are emitted.

      Returns:
          A fully populated SessionSummary instance.

      Raises:
          OSError: If the file cannot be opened or read.
          ValueError: If the file has content but contains no parseable
              JSONL lines (caller should map to EXIT_NOT_JSONL).
          LookupError: If the transcript contains no external user turns
              (caller should map to EXIT_NO_USER_TURNS).
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

- [ ] **Step 2: Write a minimal failing test for the dataclasses.**

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

- [ ] **Step 3: Run the test — confirm it passes.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all three tests pass. The dataclasses are defined and the
  constants are correct. The `build_session_summary` stub raises
  `NotImplementedError` but is not called by these tests.

- [ ] **Step 4: Commit.**

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

- [ ] **Step 1: Write `test_happy_path_emits_contract` — confirm it fails.**

  Add this test class to `tests/test_session_summary.py`:

  ```python
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
          summary = build_session_summary(fixture)

          assert summary.project == "claude-usage"
          assert "session-summary" in summary.intent.lower()
          assert isinstance(summary.actions, list)
          assert len(summary.actions) > 0
          assert summary.stopped_naturally is True
  ```

- [ ] **Step 2: Run → confirm failure.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestBuildSessionSummary::test_happy_path_emits_contract -x
  ```

  Expected failure: `NotImplementedError` from the `build_session_summary`
  stub. This is the correct red state — not an import error.

- [ ] **Step 3: Implement a minimal `build_session_summary` using internal stubs.**

  Replace the `build_session_summary` stub in `claude_usage/cli/session_summary.py`
  with the following. The four private helpers (`_derive_project`,
  `_derive_intent`, `_collect_tool_uses`, `_derive_stopped_naturally`) return
  hardcoded values that satisfy the happy-path fixture. They are expanded to
  real implementations in Tasks 3.2–3.5. Add all four helpers and the updated
  public function:

  ```python
  import json
  import sys


  def _load_entries(path: Path) -> list[dict]:
      """Read and parse all JSONL entries from a transcript file.

      Blank lines are skipped. Lines that fail json.loads are skipped
      silently (partial-malformed tolerance). Raises OSError on IO
      failure and ValueError when the file has content but zero lines
      parse successfully.

      Args:
          path: Path to the JSONL file to read.

      Returns:
          List of parsed entry dicts in file order.

      Raises:
          OSError: If the file cannot be opened or read.
          ValueError: If the file has >=1 non-blank line but none parse.
      """
      entries: list[dict] = []
      non_blank_count = 0
      with open(path, encoding="utf-8") as fh:
          for raw in fh:
              line = raw.strip()
              if not line:
                  continue
              non_blank_count += 1
              try:
                  entries.append(json.loads(line))
              except json.JSONDecodeError:
                  continue
      if non_blank_count > 0 and not entries:
          raise ValueError(
              f"No parseable JSONL lines found in {path}"
          )
      return entries


  def _derive_project(entries: list[dict], path: Path) -> str:
      """Derive the project name from transcript entries.

      Strategy:
      1. First entry with a non-empty ``cwd`` field → ``Path(cwd).name``.
      2. Fallback: apply ``decode_project_hash`` to the grandparent
         directory name (the project slug in ~/.claude/projects/<slug>/).
      3. Final fallback: ``"unknown"``.

      Args:
          entries: Parsed JSONL entries in file order.
          path: Path to the transcript file (used for slug fallback).

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
      path: Path,
      max_actions: int = DEFAULT_MAX_ACTIONS,
  ) -> SessionSummary:
      """Derive a SessionSummary by walking a transcript JSONL file once.

      Args:
          path: Absolute or relative path to the JSONL transcript file.
          max_actions: Soft cap on the number of emitted action strings.
              When 0, the cap is disabled and all actions are emitted.

      Returns:
          A fully populated SessionSummary instance.

      Raises:
          OSError: If the file cannot be opened or read.
          ValueError: If the file has content but contains no parseable
              JSONL lines (caller should map to EXIT_NOT_JSONL).
          LookupError: If the transcript contains no external user turns
              (caller should map to EXIT_NO_USER_TURNS).
      """
      entries = _load_entries(path)

      # Check for zero external user turns.
      has_user_turn = any(
          e.get("type") == "user"
          and e.get("userType") == "external"
          for e in entries
      )
      if not has_user_turn:
          raise LookupError(
              f"Transcript '{path}' contains no external user turns"
          )

      project = _derive_project(entries, path)
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

- [ ] **Step 4: Run → confirm pass.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all existing tests plus `test_happy_path_emits_contract` pass.

- [ ] **Step 5: Commit.**

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

- [ ] **Step 1: Add two failing tests.**

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
          summary = build_session_summary(fixture)
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
          summary = build_session_summary(fixture)
          assert summary.project == "unknown"
  ```

- [ ] **Step 2: Run → confirm failures.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestBuildSessionSummary::test_project_falls_back_to_unknown -x
  ```

  The `test_project_falls_back_to_unknown` test fails because the stub
  returns `"claude-usage"` unconditionally. The `test_project_derived_from_cwd_field`
  test may pass accidentally via the stub; confirm by temporarily removing the
  stub's hardcoded return and verifying it then fails before restoring.

- [ ] **Step 3: Implement `_derive_project` with real logic.**

  Replace the stub body of `_derive_project` in `claude_usage/cli/session_summary.py`:

  ```python
  def _derive_project(entries: list[dict], path: Path) -> str:
      """Derive the project name from transcript entries.

      Strategy:
      1. First entry with a non-empty ``cwd`` field → ``Path(cwd).name``.
      2. Fallback: apply ``decode_project_hash`` to the grandparent
         directory of the transcript path (the project slug directory
         under ~/.claude/projects/<slug>/<session>.jsonl).
      3. Final fallback: ``"unknown"``.

      Args:
          entries: Parsed JSONL entries in file order.
          path: Path to the transcript file (used for slug fallback).

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

      # Strategy 2: decode the project-hash slug from the path.
      # Expected layout: .../.claude/projects/<slug>/<session>.jsonl
      slug = path.parent.name
      decoded = decode_project_hash(slug)
      if decoded:
          return decoded

      # Strategy 3: final fallback.
      return "unknown"
  ```

- [ ] **Step 4: Run → confirm pass.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass, including both new project-derivation tests.

- [ ] **Step 5: Commit.**

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

- [ ] **Step 1: Add four failing tests.**

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
          summary = build_session_summary(fixture)
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
          summary = build_session_summary(fixture)
          assert summary.intent == "Fix the parser bug in parser.py"

      def test_intent_falls_back_for_slash_command_only(self) -> None:
          """Pure slash-command session produces intent 'Ran /project-review'."""
          from pathlib import Path

          from claude_usage.cli.session_summary import build_session_summary

          fixture = Path(
              "tests/fixtures/session_summaries/slash_command_only.jsonl"
          )
          summary = build_session_summary(fixture)
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
          summary = build_session_summary(fixture)
          assert summary.intent == "Session on myproject"
  ```

- [ ] **Step 2: Run → confirm failures.**

  ```bash
  uv run pytest tests/test_session_summary.py -k "intent" -x
  ```

  Expected: all four intent tests fail because `_derive_intent` returns a
  hardcoded string.

- [ ] **Step 3: Implement `_derive_intent` with real logic.**

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

- [ ] **Step 4: Run → confirm pass.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass, including all four new intent tests.

- [ ] **Step 5: Commit.**

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

- [ ] **Step 1: Add `test_action_classification_edit_tools` — confirm it fails.**

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

          summary = build_session_summary(fixture)

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

          summary = build_session_summary(fixture)
          assert summary.actions == []
  ```

- [ ] **Step 2: Run → confirm failures.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestToolClassification -x
  ```

  Expected: both tests fail. `test_action_classification_edit_tools` fails
  because `_collect_tool_uses` returns the hardcoded happy-path list.
  `test_action_classification_skips_reads` fails for the same reason.

- [ ] **Step 3: Implement `_classify_tool_use` and `_collect_tool_uses`.**

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

- [ ] **Step 4: Run → confirm pass.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass. Note that `test_happy_path_emits_contract` still
  passes because the happy_path fixture actions (Edit, Bash, Agent) now flow
  through real classification — Edit is handled; Bash and Agent return `None`
  temporarily, so only the Edit action appears. Update the contract test
  assertion from `len(summary.actions) > 0` (already satisfied by one Edit)
  to confirm it still holds before committing.

- [ ] **Step 5: Commit.**

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

- [ ] **Step 1: Add `test_action_classification_bash_tools` — confirm it fails.**

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

          summary = build_session_summary(fixture)

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
          summary = build_session_summary(fixture)
          assert len(summary.actions) == 1
          assert summary.actions[0] == "Dispatched code-reviewer sub-agent"
  ```

- [ ] **Step 2: Run → confirm failures.**

  ```bash
  uv run pytest tests/test_session_summary.py::TestToolClassification::test_action_classification_bash_tools tests/test_session_summary.py::TestToolClassification::test_action_classification_agent_dispatch -x
  ```

  Expected: both tests fail because Bash, PowerShell, and Agent return `None`
  in the current `_classify_tool_use`.

- [ ] **Step 3: Extend `_classify_tool_use` to handle Bash, PowerShell, and Agent.**

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

- [ ] **Step 4: Run → confirm pass.**

  ```bash
  uv run pytest tests/test_session_summary.py -x
  ```

  Expected: all tests pass. The happy_path contract test now benefits from
  real Bash and Agent classification in addition to Edit, so
  `len(summary.actions) > 0` remains trivially satisfied.

- [ ] **Step 5: Commit.**

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

<!-- PASS-2-END: next pass continues Phase 3 from Task 3.6 (agent_dispatch classification) onward -->
