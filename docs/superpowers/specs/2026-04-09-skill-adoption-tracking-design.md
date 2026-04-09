# Skill Adoption Tracking — Design Spec

**Date**: 2026-04-09
**Status**: Draft
**Goal**: Track when the router passes skills to subagents via Agent dispatch prompts, correlate with actual Skill tool invocations, and surface adoption metrics in the claude-usage dashboard.

**Repos**: `claude_personal_configs` (hook script + settings.json) and `claude-usage` (parser, aggregator, dashboard)

**Issues**: cbeaulieu-gt/claude_personal_configs#24, cbeaulieu-gt/claude-usage#5

---

## Problem

When the router dispatches a subagent with instructions like "Use the `python` skill", there is no visibility into whether the subagent actually invokes that skill. Skills may be passed but silently ignored, making it impossible to evaluate which skills are worth maintaining and which agent types reliably follow skill instructions.

## Solution

A PreToolUse hook that logs two event types — `skill_passed` (extracted from Agent dispatch prompts) and `skill_invoked` (from Skill tool calls) — to a JSONL file. The claude-usage tool ingests this log, correlates the events, and displays per-skill adoption rates on the dashboard.

---

## Component 1: Hook Script (`hooks/skill-tracker.py`)

**Location**: `~/.claude/hooks/skill-tracker.py` (in `claude_personal_configs` repo)

**Trigger**: Two PreToolUse hook entries in `settings.json` — one matching `Skill`, one matching `Agent`.

**Input**: JSON on stdin from Claude Code's PreToolUse event. Key fields:
- `tool_name` — `"Skill"` or `"Agent"`
- `tool_input` — the tool's input payload
- `session_id` — current session identifier

### Event: `skill_invoked`

When `tool_name == "Skill"`:
- Extract `tool_input.skill` (e.g. `"python"`, `"superpowers:brainstorming"`)
- Write one JSONL line to `~/.claude/skill-tracking.jsonl`

Output format:
```json
{"event": "skill_invoked", "skill": "python", "timestamp": "2026-04-09T21:15:00Z", "session_id": "abc-123"}
```

### Event: `skill_passed`

When `tool_name == "Agent"`:
- Extract `tool_input.prompt` and `tool_input.subagent_type`
- Scan the prompt for skill references using two pattern types:
  1. **Backtick-quoted names**: `` `python` ``, `` `superpowers:test-driven-development` ``
  2. **Phrase patterns**: `"Use the X skill"`, `"invoke X skill"`, `"Use skill: X"`
- Validate each extracted name against the installed skill allowlist
- Write one JSONL line per matched skill

Output format:
```json
{"event": "skill_passed", "skill": "python", "target_agent": "code-writer", "timestamp": "2026-04-09T21:15:00Z", "session_id": "abc-123"}
```

### Skill Allowlist

Built at runtime by scanning the filesystem:
- `~/.claude/skills/` — user-created skills (directory names)
- `~/.claude/plugins/cache/*/superpowers/*/skills/` — plugin skills (e.g. superpowers)
- Plugin skills with prefixes: scan subdirectories to build `prefix:name` format (e.g. `commit-commands:commit`, `superpowers:brainstorming`)

The scan adds ~5-10ms per hook invocation. With ~30 installed skills, this is negligible against the 5s timeout budget.

### Error Handling

- Entire script wrapped in try/except — never crashes, never blocks Claude Code
- No stdout output (would interfere with hook protocol)
- Errors logged to stderr (visible in Claude Code debug logs if needed)
- If `skill-tracking.jsonl` can't be written, silently skip

### Log File

- **Path**: `~/.claude/skill-tracking.jsonl`
- **Format**: One JSON object per line, append-only
- **Growth**: ~200 bytes/event, ~20-50 events/session, ~10KB/day. No rotation needed for v1.

---

## Component 2: Hook Configuration (`settings.json`)

Two new entries in the `PreToolUse` hooks array:

```json
{
  "matcher": "Skill",
  "hooks": [
    {
      "type": "command",
      "command": "/c/Users/chris/.claude/.venv/Scripts/python.exe /c/Users/chris/.claude/hooks/skill-tracker.py",
      "timeout": 5
    }
  ]
},
{
  "matcher": "Agent",
  "hooks": [
    {
      "type": "command",
      "command": "/c/Users/chris/.claude/.venv/Scripts/python.exe /c/Users/chris/.claude/hooks/skill-tracker.py",
      "timeout": 5
    }
  ]
}
```

Both use the `.venv` Python (where dependencies are installed). Same command for both matchers — the script distinguishes events by reading `tool_name` from stdin JSON.

---

## Component 3: claude-usage Parser Addition

**New file**: `claude_usage/skill_tracker_parser.py`

**Data classes** (added to `models.py`):
- `SkillPassedEvent(frozen=True)`: skill, target_agent, timestamp, session_id
- `SkillInvokedEvent(frozen=True)`: skill, timestamp, session_id

**Function**: `parse_skill_tracking(data_dir: Path) -> tuple[list[SkillPassedEvent], list[SkillInvokedEvent]]`
- Reads `data_dir / "skill-tracking.jsonl"`
- Parses each line, constructs event objects
- Returns empty lists if file doesn't exist (graceful degradation)

Called alongside `parse_sessions()` in `__main__.py`.

---

## Component 4: claude-usage Aggregator Addition

**New field on `AggregateResult`**: `by_skill_adoption: dict[str, dict]`

Structure per skill:
```json
{
  "python": {
    "times_passed": 12,
    "times_invoked": 8,
    "adoption_rate": 0.667,
    "by_target_agent": {
      "code-writer": {"passed": 5, "invoked": 4},
      "debugger": {"passed": 3, "invoked": 2},
      "refactor": {"passed": 4, "invoked": 2}
    }
  }
}
```

**Correlation logic**:
- Filter both event lists to the selected time window
- Group `skill_passed` events by skill name, count per target_agent
- Group `skill_invoked` events by skill name
- For per-agent breakdown: match invoked events to the most recent passed event for the same skill+session to infer which agent invoked it
- Compute adoption_rate = times_invoked / times_passed (0.0 if never passed)

**Relationship to existing `by_skill`**: The existing field (from JSONL parsing) tracks ALL skill invocations including direct user invocations. `by_skill_adoption` specifically tracks the router→subagent pass-through pipeline. Both remain independent — no changes to existing `by_skill` logic.

---

## Component 5: Dashboard Addition

**New section**: "Skill Adoption" — positioned after the existing "Skills" bar chart.

**Chart**: Horizontal grouped bar chart (Chart.js):
- Each skill gets two bars: "Passed" (gray `#8b949e`) and "Invoked" (green `#2ea043`)
- Adoption percentage label displayed at the end of each invoked bar
- Skills sorted by times_passed descending (most-passed skills at top)

**Detail table below chart**: Per-skill expandable rows showing:
- Skill name, times passed, times invoked, adoption rate
- Per-agent breakdown: which agent types invoke vs. ignore

**Graceful degradation**: Section only renders when `by_skill_adoption` has data. If `skill-tracking.jsonl` doesn't exist or is empty, the section is hidden entirely. The rest of the dashboard is unaffected.

**Time filtering**: Skill adoption data filters with the same date range / rolling window as other dashboard sections.

---

## Edge Cases & Limitations

**Skills invoked directly by the user**: Shows up as `skill_invoked` with no matching `skill_passed`. These are excluded from adoption metrics — only skills with at least one `skill_passed` event appear in the adoption section.

**Skills mentioned descriptively in prompts**: If a prompt says "The `python` skill was used previously" (descriptive, not instructive), the parser may extract it as a pass. The allowlist validation reduces false positives but can't distinguish intent. Accepted trade-off — these cases are rare and the data is directional.

**Skills loaded via system prompt**: Skills injected at session start (e.g. `superpowers:using-superpowers`) are followed without a `Skill` tool call. No hook event is generated. Known blind spot — only explicit `Skill` tool invocations are tracked.

**Session ID for correlation**: PreToolUse stdin includes `session_id`, allowing pass/invoke correlation within the same session. Cross-session correlation is not needed — subagents run within the dispatching session.

**Log file growth**: ~10KB/day at typical usage. No rotation for v1. The aggregator's time window filtering keeps performance constant.

---

## Trade-offs

| Trade-off | Accepted because |
|---|---|
| Prompt parsing uses heuristics, not structured data | Agent dispatch prompts are unstructured text; heuristics + allowlist validation catches the vast majority of cases |
| Allowlist scans filesystem on every hook invocation | ~30 skills, ~5ms scan — negligible against 5s timeout; always accurate, no cache staleness |
| Can't track skills followed from system prompt injection | No hook fires for "agent follows embedded instructions" — this is a platform limitation, not solvable at the hook level |
| Separate JSONL file instead of enriching session JSONL | Session files are written by Claude Code, not us; a separate log is the only option without modifying Claude Code internals |
| Per-agent invocation attribution is approximate | Based on matching invoked events to the most recent passed event in the same session; good enough for adoption rates |

---

## Implementation Scope

### claude_personal_configs repo (issue #24)
1. Create `hooks/skill-tracker.py` — event parsing, prompt scanning, allowlist, JSONL logging
2. Add two PreToolUse hook entries to `settings.json`
3. Write tests for prompt parsing and allowlist logic

### claude-usage repo (issue #5)
4. Add `SkillPassedEvent` and `SkillInvokedEvent` to `models.py`
5. Create `skill_tracker_parser.py` — JSONL log reader
6. Add `by_skill_adoption` to aggregator
7. Update `__main__.py` to call the new parser and pass data through
8. Add "Skill Adoption" section to `dashboard.html`
9. Update `renderer.py` to pass adoption data to the template
10. Write tests for parser, aggregator correlation, and edge cases
