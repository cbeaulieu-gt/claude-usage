# Design: `session-summary` subcommand

**Issue:** [cbeaulieu-gt/claude-usage#19](https://github.com/cbeaulieu-gt/claude-usage/issues/19)
**Date:** 2026-04-22
**Status:** Awaiting review (producer-side + consumer-side) before implementation planning
**Consumer:** [`/whats-next` skill](https://github.com/cbeaulieu-gt/claude_personal_configs/blob/main/skills/whats-next/SKILL.md) in `cbeaulieu-gt/claude_personal_configs`

---

## Context

The `/whats-next` skill expects a subcommand that does not exist:

```
claude-usage session-summary --path "<transcript.jsonl>" --format json
```

When the call fails (unrecognized argument), the skill's error path silently falls back to `source: "none"`, producing an empty Recent Work section without surfacing the failure. Users relying on transcript-based session recap get a degraded experience without knowing why.

This spec defines the subcommand's contract, implementation approach, and test gates.

## Goals

1. **Add `session-summary` as a proper subcommand** of `claude-usage`, with its own flags and exit codes.
2. **Emit JSON matching the exact shape `/whats-next` consumes** — see "Output contract" below.
3. **Derive intent, actions, project, and stopped-naturally deterministically** from a Claude Code transcript JSONL file, no LLM calls.
4. **Refactor the existing CLI** to support subcommands cleanly, without bifurcating the parsing layer.
5. **Preserve all existing dashboard functionality** (every current flag and semantic unchanged, just moved under the `dashboard` subcommand).

## Non-goals (v1)

- **Sub-agent transcript recursion** (`--recursive` flag). Sub-agent linkage convention in Claude Code's JSONL schema is unclear in the current schema (zero `isSidechain:true` entries observed across recent transcripts). Defer until flat mode proves insufficient.
- **LLM-assisted intent/action synthesis.** Out of genre for this repo (deterministic JSONL→metrics).
- **Streaming / incremental parsing.** Whole-file read is fine for typical transcript sizes.
- **Downstream action-count limiting.** `/whats-next` already truncates to 3–5 bullets; pushing that knob here would duplicate responsibility.

---

## CLI grammar

### After refactor

```
claude-usage dashboard [--data-dir PATH] [--from DATE] [--to DATE] [--window WIN]
                       [--output PATH] [--no-open]
                       [--limit-5h N] [--limit-7d N] [--limit-sonnet-7d N]
                       [--format {html,json}]

claude-usage session-summary --path PATH [--format {json,text}]
```

### Grammar rules

- **No implicit default subcommand.** Bare `claude-usage` prints help and exits 0.
- **Old flag-only form removed.** `claude-usage --format json` no longer works; callers migrate to `claude-usage dashboard --format json`.
- **Dashboard flags unchanged** in name, semantics, and defaults — only their location moves (now under `dashboard` subparser).
- **`--format` choices differ by subcommand**: `dashboard` is `{html, json}`; `session-summary` is `{json, text}`. `text` is a human-readable debug view, not consumed by `/whats-next`.

### Cross-repo migration work (post-merge)

In `cbeaulieu-gt/claude_personal_configs`, grep for `claude-usage` invocations:

```powershell
Select-String -Path .\**\* -Pattern 'claude-usage' -SimpleMatch
```

Expected hits: `/whats-next` skill, possibly `/project-review`, a handful of scripts. Update each to `claude-usage dashboard [...]` or `claude-usage session-summary [...]`. Tracked as a checklist in the implementation PR body.

---

## Module layout

### Current

```
claude_usage/
  __main__.py              # 158 lines — all CLI in one function
  aggregator.py
  models.py
  parser.py
  renderer.py
  skill_tracking.py
```

### After refactor

```
claude_usage/
  __main__.py              # ~30 lines — subparser wiring + dispatch only
  cli/
    __init__.py
    dashboard.py           # existing __main__.py body, moved verbatim
    session_summary.py     # new subcommand implementation
  aggregator.py            # unchanged
  models.py                # unchanged (or + new dataclasses; see "Data shapes")
  parser.py                # unchanged
  renderer.py              # unchanged
  skill_tracking.py        # unchanged
```

**Rationale:** `__main__.py` stays focused on routing; each subcommand has a clean import surface for tests; future subcommands drop in naturally.

### Helpers reused from `parser.py`

- `decode_project_hash(hash_name)` — useful as fallback for `project` derivation when `cwd` is unavailable.
- `_parse_timestamp(ts_str)` — standard ISO 8601 handling.

**Not reused:** `_parse_jsonl_messages` filters to `type == "assistant"` with `usage` present (token-counting focus). `session-summary` needs a broader walk (user turns + assistant tool_use blocks + system terminal markers), so it gets its own walk function.

---

## Output contract

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

### Invariants

| Field | Type | Invariant |
|---|---|---|
| `project` | `string` | Always non-empty. Fallback to `"unknown"` if undetectable. |
| `intent` | `string` | Always non-empty. Fallback to `"Ran /<command>"` for pure slash-command sessions. |
| `actions` | `array[string]` | Always present. May be an empty array if the session contained no state-changing tool uses (exit still 0 as long as there was at least one external user turn). |
| `stoppedNaturally` | `bool` | Strict bool. Derived from schema markers, not a heuristic. |

### Key order and formatting

- Pretty-printed with `json.dumps(obj, indent=2, ensure_ascii=False)`.
- Key order matches the snippet above. Python 3.7+ dict-insertion order makes this deterministic.
- `stoppedNaturally` uses camelCase in the output JSON (matches the consumer's existing key) but is `stopped_naturally` in internal Python code.

---

## Summarization pipeline

### Data flow

```
JSONL file at --path
   │
   ▼
[1] Walk lines → json.loads each → skip blanks → tolerate individual JSON decode failures
   │
   ▼
[2] For each entry, dispatch on entry.type:
      "user"        → if first external user turn with content, capture → intent
      "assistant"   → for each content block with type=tool_use → classify → ActionRecord
      "system"      → if subtype=stop_hook_summary, capture preventedContinuation
   │
   ▼
[3] Track last assistant message's stop_reason (for stoppedNaturally)
   │
   ▼
[4] Collapse consecutive ActionRecords where (type, target) match
   │
   ▼
[5] Render each ActionRecord → past-tense string
   │
   ▼
[6] Derive project from cwd field; derive stoppedNaturally from tracked state
   │
   ▼
[7] Assemble final SessionSummary → render JSON or text per --format
```

### Tool-use classification table

| Tool | Action type | Included? | Past-tense summary template |
|---|---|---|---|
| `Edit`, `Write`, `NotebookEdit` | `edit` | ✅ | `Edited <path>` (or `Created <path>` when implementer can distinguish; `Edited` is safe default) |
| `Bash`, `PowerShell` | `bash` | ✅ | `` Ran `<command — whitespace-collapsed, truncated to 80 chars>` `` |
| `Agent` | `agent_dispatch` | ✅ | `Dispatched <subagent_type> sub-agent` |
| `mcp__*` (MCP tools) | `mcp` | ✅ | `` Called `<namespace.method>` (MCP) `` (strip `mcp__plugin_<plugin>_<server>__` prefix; dot-separate remainder) |
| `WebFetch` | — | ❌ skip | Info-gathering — not state-changing |
| `WebSearch` | — | ❌ skip | Info-gathering — not state-changing |
| `Skill` | — | ❌ skip | Enabler, not action — the resulting Edits/Bash/Agent dispatches are the actual work |
| `Read` | — | ❌ skip | Info-gathering |
| `Grep`, `Glob` | — | ❌ skip | Info-gathering |
| `TodoWrite` | — | ❌ skip | Internal ceremony |
| Anything else (unknown tool name) | `other` | ✅ | `Used <tool_name> tool` — default-include for forward compatibility |

**Rule:** include only state-changing tools. Skip info-gathering, skill loading, and internal ceremony.

### Collapse rule

After classification, collapse **consecutive** records where `(type, target)` match:

- 5 consecutive `Edit` calls to `parser.py` → one `Edited parser.py` action
- 3 consecutive `Bash` calls with identical command → one `` Ran `<cmd>` `` action
- `Edit parser.py` → `Edit models.py` → `Edit parser.py` stays as **three** records (non-adjacent, preserves chronology)

No global dedupe. Preserves the narrative sense of "the user did X, then Y, then X again."

### `intent` derivation

1. Scan entries for first `type: "user"` AND `userType: "external"` entry.
2. Unpack `message.content`:
   - If string → that's the text.
   - If array → concatenate only `type: "text"` blocks; skip `tool_result` blocks.
3. Strip XML-like wrappers: `<system-reminder>…</system-reminder>`, `<command-message>…</command-message>`, `<command-name>…</command-name>`, `<command-args>…</command-args>`, `<local-command-stdout>…</local-command-stdout>`.
4. Trim whitespace.
5. If result is empty (pure slash-command session):
   - Look for `<command-name>/<name></command-name>` in the original content → `intent = "Ran /<name>"`.
   - If even that isn't present → `intent = "Session on <project>"`.
6. Else, take first sentence (split on `. `, `! `, `? `, or newline) OR first 200 chars, whichever comes first.

### `project` derivation

1. First entry with a `cwd` field → `Path(cwd).name` → e.g., `"claude-usage"`.
2. Fallback: if transcript lives under `~/.claude/projects/<slug>/`, apply `decode_project_hash(slug)`.
3. Final fallback: `"unknown"`.

In practice, `cwd` is on every entry — the fallbacks are defensive.

### `stoppedNaturally` derivation

Walk entries once, track:

- `last_assistant_stop_reason`: updated to `entry.message.stop_reason` on every `type: "assistant"` entry.
- `prevented_continuation`: set to `True` if any `type: "system"` entry has `subtype: "stop_hook_summary"` AND `preventedContinuation: true`.

Return `True` iff:
- `last_assistant_stop_reason == "end_turn"`, AND
- `not prevented_continuation`.

Return `False` otherwise — specifically when:
- Last assistant stop_reason is `"max_tokens"`, `"tool_use"`, or `"stop_sequence"`.
- `preventedContinuation: true` was recorded.
- No assistant entries exist (malformed/empty session).

This is derivable from the schema — not a heuristic.

---

## Data shapes (internal)

### Dataclasses

Likely in a new `claude_usage/cli/_session_summary_types.py` (small enough to live alongside `session_summary.py`; implementer can fold into the module if preferred).

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ActionRecord:
    type: str        # "edit" | "bash" | "agent_dispatch" | "mcp" | "other"
    raw_tool: str    # original tool name
    target: str      # path, command, agent name, etc. — used for collapse
    summary: str     # past-tense rendered string

@dataclass(frozen=True)
class SessionSummary:
    project: str
    intent: str
    actions: list[str]
    stopped_naturally: bool
```

### `--format text` shape (debug view)

```
Project: claude-usage
Intent: Implement the session-summary subcommand...
Stopped naturally: yes

Actions:
  - Edited claude_usage/cli/session_summary.py
  - Created tests/test_session_summary.py
  - Ran pytest tests/test_session_summary.py -x
  - Dispatched code-reviewer sub-agent
```

Not a consumer contract — developer-only.

---

## Error handling & exit codes

| Code | Condition | Stderr message |
|---|---|---|
| `0` | Success — JSON written to stdout | *(silent)* |
| `1` | `--path` missing, unreadable, permission denied, or a directory | `session-summary: cannot read transcript at '<path>': <OS error>` |
| `2` | Transcript parsed successfully but contains zero entries with `type: "user"` AND `userType: "external"` (e.g. transcript consists only of agent-setting / attachment / system entries, or the file is effectively empty after JSONL parse) | `session-summary: transcript '<path>' contains no user turns` |
| `3` | File readable but contains no valid JSONL (every non-blank line fails `json.loads`) | `session-summary: transcript '<path>' is not valid JSONL` |

**Partial-malformed tolerance:** individual lines failing `json.loads` are skipped silently. Exit 3 fires only when **zero** lines parse. Matches existing `parser.py` line-skip behavior.

**Non-zero exits produce nothing on stdout** — no partial JSON, no header text. Stdout is reserved for the success contract.

---

## Testing

### Fixture strategy

All fixtures are JSONL files in `tests/fixtures/session_summaries/`:

- **Real transcripts** — copied from `~/.claude/projects/` and sanitized (strip API request IDs, trim thinking blocks, keep essential structure).
- **Hand-written edge cases** — empty, malformed, slash-command-only.

Sanitization helper lives at `tests/fixtures/sanitize_transcript.py` so future fixtures are reproducible.

### Minimum test matrix

| Test | Fixture | Expected | AC coverage |
|---|---|---|---|
| `test_happy_path_emits_contract` | Real session with edits+bash+agent | Exit 0; JSON matches contract; all four fields populated; `stoppedNaturally: true` | #1 |
| `test_missing_file_exits_1` | — (nonexistent path) | Exit 1; stderr contains "cannot read" | #2 |
| `test_empty_session_exits_2` | Transcript with only agent-setting/attachment/system entries, no user turns | Exit 2 | #3 |
| `test_malformed_file_exits_3` | Invalid-JSON lines only | Exit 3 | #4 |
| `test_existing_dashboard_unchanged` | N/A — CLI snapshot | `claude-usage dashboard --format json` output byte-identical to pre-refactor (or documented diff) | #5 |
| `test_action_classification_skips_reads` | User turn + only Read/Grep/Glob tool uses | Exit 0, `actions: []`, intent populated | Design: skip list |
| `test_consecutive_edits_collapse` | 3 Edits to same file | Actions contains single `Edited <path>` entry | Design: collapse |
| `test_intent_falls_back_for_slash_command_only` | Pure `/project-review` session | `intent == "Ran /project-review"` | Design: fallback |
| `test_stopped_naturally_false_on_max_tokens` | Final stop_reason=max_tokens | `stoppedNaturally: false` | Design: terminal markers |
| `test_stopped_naturally_false_on_prevented_continuation` | system entry with preventedContinuation=true | `stoppedNaturally: false` | Design: terminal markers |

~10 tests. All AC items (acceptance criteria #1–#5 from issue #19) covered. No new dev dependencies beyond existing `pytest`.

### Coverage gate

No percentage target. Every test in the matrix above passes before merge; that is the gate.

---

## Acceptance criteria (from issue #19)

- [ ] `claude-usage session-summary --path <valid-jsonl> --format json` exits 0 and emits JSON matching contract
- [ ] `claude-usage session-summary --path <missing>` exits 1 with one-line stderr
- [ ] `claude-usage session-summary --path <empty-session.jsonl>` exits 2
- [ ] `claude-usage session-summary --path <malformed.jsonl>` exits 3
- [ ] Existing CLI invocations (dashboard behavior) continue to work (modulo explicit migration to `dashboard` subcommand)
- [ ] At least one test covers each exit code path
- [ ] `/whats-next` produces a populated Recent Work section when run against a repo with no `save-context` file but a recent transcript

The last item is a **consumer-side validation** — testable only after the consumer's invocation path is migrated to `claude-usage dashboard [...]` / `claude-usage session-summary [...]` in `claude_personal_configs`.

---

## Cross-repo coordination

This feature's contract spans two repositories:

| Repo | Role | Required changes |
|---|---|---|
| `cbeaulieu-gt/claude-usage` (this repo) | Producer | Add `session-summary` subcommand; refactor CLI to subparsers |
| `cbeaulieu-gt/claude_personal_configs` | Consumer (`/whats-next` skill) | Update invocation from `claude-usage --format json` to `claude-usage dashboard --format json`; verify `session-summary` output matches skill's `SessionSummary` mapping |

**Sequencing:** ship producer first on a branch and release (or at least tag). Consumer migration PR lands after, pinned to the producer version.

**Consumer review required:** the consumer's skill author (effectively the repo owner wearing the consumer hat) must acknowledge the contract in "Output contract" and the migration in "CLI grammar / Cross-repo migration work" before this spec moves to implementation planning.

---

## Open questions / risks

1. **Sub-agent linkage convention.** Zero `isSidechain:true` entries observed — how does the top-level transcript actually reference sub-agent JSONL files? Not a v1 blocker, but a v2 investigation item.
2. **`dashboard` JSON snapshot test.** Establishing the "unchanged behavior" snapshot cleanly — need to decide whether to fixture a real pre-refactor run or capture during the refactor itself.
3. **Sanitization scope.** How aggressive should `sanitize_transcript.py` be? Minimum: strip request IDs, preserve structure. Do we also want to strip user prose for privacy in checked-in fixtures?

Items 1 and 3 are implementation-time decisions, not spec-level. Item 2 is a minor testing decision that can be resolved in the plan stage.

---

## Deferred (v2 scope, not in this spec)

- `--recursive` flag for sub-agent transcript linkage
- Streaming / incremental parsing
- `--limit` flag for action count
- Additional output formats (YAML, CSV)
