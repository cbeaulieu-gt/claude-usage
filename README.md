# claude-usage

Parse Claude Code session data and generate an interactive HTML dashboard showing token consumption by model, agent, skill, project, and time period.

## Why

Claude Code tracks three billing buckets (5h rolling, 7d rolling, Sonnet-only 7d) but provides no per-agent or per-skill visibility. This tool reads Claude Code's local JSONL session files and generates a dashboard that breaks down where your tokens are going.

## Install

```bash
pip install -e .
```

Requires Python 3.10+.

## Usage

```bash
# Default: last 7 days, opens in browser
python -m claude_usage

# Rolling window matching billing buckets
python -m claude_usage --window 5h
python -m claude_usage --window 7d

# Custom date range
python -m claude_usage --from 2026-04-01 --to 2026-04-09

# Output to file instead of opening browser
python -m claude_usage --output report.html --no-open

# Custom Claude data directory
python -m claude_usage --data-dir "D:\other\.claude"

# Set budget limits for gauge percentages
python -m claude_usage --limit-5h 600000 --limit-7d 4000000 --limit-sonnet-7d 2000000
```

## Dashboard

The generated HTML dashboard includes:

- **Budget gauges** - estimated usage against each billing bucket (5h, 7d, Sonnet-only 7d)
- **Model breakdown** - donut chart and daily stacked bar chart (Opus/Sonnet/Haiku)
- **Agent breakdown** - token usage per agent with model attribution
- **Skill usage** - invocation counts per skill
- **Project breakdown** - tokens per project
- **Session drill-down** - click a day to see individual sessions with agents, tokens, and model split

## How It Works

Reads JSONL session files from `~/.claude/projects/`. Each session file contains timestamped assistant messages with model name and token usage. Subagent metadata (`.meta.json`) maps child agent tokens to their agent type. Skill invocations are extracted from `Skill` tool-use entries.

## Development

```bash
pip install -e ".[dev]"
pytest
```
