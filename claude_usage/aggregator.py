"""Aggregate parsed session data by model, agent, skill, project, and time."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from claude_usage.models import MessageRecord, SessionRecord


@dataclass
class AggregateResult:
    """Holds all aggregated data for rendering."""

    total_tokens: int = 0
    total_messages: int = 0
    total_sessions: int = 0

    by_model: dict[str, dict] = field(default_factory=dict)
    by_agent: dict[str, dict] = field(default_factory=dict)
    by_skill: dict[str, dict] = field(default_factory=dict)
    by_project: dict[str, dict] = field(default_factory=dict)
    by_day: dict[str, dict] = field(default_factory=dict)
    sessions: list[dict] = field(default_factory=list)


def _add_tokens(bucket: dict, msg: MessageRecord) -> None:
    """Add a message's token counts to an accumulator dict."""
    bucket["total_tokens"] = bucket.get("total_tokens", 0) + msg.total_tokens
    bucket["input_tokens"] = bucket.get("input_tokens", 0) + msg.input_tokens
    bucket["output_tokens"] = bucket.get("output_tokens", 0) + msg.output_tokens
    bucket["cache_read_tokens"] = bucket.get("cache_read_tokens", 0) + msg.cache_read_tokens
    bucket["cache_creation_tokens"] = bucket.get("cache_creation_tokens", 0) + msg.cache_creation_tokens
    bucket["message_count"] = bucket.get("message_count", 0) + 1


def aggregate(
    sessions: list[SessionRecord],
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    window_hours: float | None = None,
) -> AggregateResult:
    """Aggregate session data with optional time filtering.

    Args:
        sessions: Parsed session records.
        from_date: Only include messages on or after this time.
        to_date: Only include messages before this time.
        window_hours: Rolling window - only include messages from the last N hours.
                      Overrides from_date if set.
    """
    result = AggregateResult()

    if window_hours is not None:
        from_date = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        to_date = None

    filtered_messages: list[MessageRecord] = []
    session_ids_seen: set[str] = set()
    agent_models: dict[str, Counter] = defaultdict(Counter)
    project_sessions: dict[str, set] = defaultdict(set)

    for session in sessions:
        session_messages: list[MessageRecord] = []
        for msg in session.messages:
            if from_date and msg.timestamp < from_date:
                continue
            if to_date and msg.timestamp >= to_date:
                continue
            session_messages.append(msg)
            filtered_messages.append(msg)

        if session_messages:
            session_ids_seen.add(session.session_id)
            project_sessions[session.project].add(session.session_id)

            model_tokens: dict[str, int] = defaultdict(int)
            for m in session_messages:
                model_tokens[m.model_short] += m.total_tokens

            agents_in_session = sorted(set(m.agent_type for m in session_messages))

            result.sessions.append({
                "session_id": session.session_id,
                "project": session.project,
                "start_time": min(m.timestamp for m in session_messages).isoformat(),
                "root_agent": session.root_agent,
                "agents": agents_in_session,
                "total_tokens": sum(m.total_tokens for m in session_messages),
                "model_split": dict(model_tokens),
                "duration_minutes": session.duration_minutes,
                "message_count": len(session_messages),
            })

    result.total_tokens = sum(m.total_tokens for m in filtered_messages)
    result.total_messages = len(filtered_messages)
    result.total_sessions = len(session_ids_seen)

    for msg in filtered_messages:
        model = msg.model_short
        if model not in result.by_model:
            result.by_model[model] = {}
        _add_tokens(result.by_model[model], msg)

    for msg in filtered_messages:
        agent = msg.agent_type
        if agent not in result.by_agent:
            result.by_agent[agent] = {}
        _add_tokens(result.by_agent[agent], msg)
        agent_models[agent][msg.model_short] += 1

    for agent, counter in agent_models.items():
        result.by_agent[agent]["primary_model"] = counter.most_common(1)[0][0]

    agent_session_count: dict[str, set] = defaultdict(set)
    for session_summary in result.sessions:
        for agent in session_summary["agents"]:
            agent_session_count[agent].add(session_summary["session_id"])
    for agent in result.by_agent:
        result.by_agent[agent]["session_count"] = len(agent_session_count.get(agent, set()))

    for msg in filtered_messages:
        if msg.skill is None:
            continue
        if msg.skill not in result.by_skill:
            result.by_skill[msg.skill] = {"invocation_count": 0, "total_tokens": 0}
        result.by_skill[msg.skill]["invocation_count"] += 1
        result.by_skill[msg.skill]["total_tokens"] += msg.total_tokens

    result.by_project = {}
    for session_summary in result.sessions:
        proj = session_summary["project"]
        if proj not in result.by_project:
            result.by_project[proj] = {"total_tokens": 0, "session_count": 0, "message_count": 0}
        result.by_project[proj]["total_tokens"] += session_summary["total_tokens"]
        result.by_project[proj]["message_count"] += session_summary["message_count"]
    for proj, sess_ids in project_sessions.items():
        if proj in result.by_project:
            result.by_project[proj]["session_count"] = len(sess_ids)

    for msg in filtered_messages:
        day = msg.timestamp.strftime("%Y-%m-%d")
        if day not in result.by_day:
            result.by_day[day] = {"total_tokens": 0, "by_model": {}}
        result.by_day[day]["total_tokens"] += msg.total_tokens
        model = msg.model_short
        if model not in result.by_day[day]["by_model"]:
            result.by_day[day]["by_model"][model] = 0
        result.by_day[day]["by_model"][model] += msg.total_tokens

    result.sessions.sort(key=lambda s: s["start_time"], reverse=True)

    return result
