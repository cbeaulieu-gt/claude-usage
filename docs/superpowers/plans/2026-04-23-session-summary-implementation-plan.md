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

<!-- PASS-1-END: next pass writes Phase 2 (fixtures + dataclasses) and Phase 3 (core derivation) beginning after this line -->
