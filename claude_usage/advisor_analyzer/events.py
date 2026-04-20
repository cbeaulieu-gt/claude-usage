"""Typed event taxonomy for Phase 1 advisor analysis.

Each transcript-analysis observation produces exactly one event of a specific
type. The aggregator computes metrics by matching on the type, not by
inspecting sentinel strings. See
docs/superpowers/specs/2026-04-19-typed-event-taxonomy.md in the
claude_personal_configs repo for full design rationale.
"""
from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True)
class AgreementEvent:
    """Successful pairing: Advisor was consulted and a specialist was dispatched."""

    episode_id: str
    advisor_position: int
    dispatch_position: int
    pm_instinct: str | None
    advisor_top_agent: str
    advisor_ranked_agents: tuple[str, ...]
    pm_final_agent: str
    advisor_skills: frozenset[str] | None
    pm_skills: frozenset[str] | None
    match_rank: int | None


@dataclass(frozen=True)
class DriftEvent:
    """Category-A specialist dispatched without any prior Advisor call in this episode."""

    episode_id: str
    dispatch_position: int
    subagent_type: str
    had_trivial_allowlist_dispatch: bool


@dataclass(frozen=True)
class DeclaredSelfHandleEvent:
    """PM emitted PM-instinct: self-handle. Not drift on its own — flagged for qualitative review."""

    episode_id: str
    instinct_position: int
    reasoning_excerpt: str


@dataclass(frozen=True)
class SelfHandleDriftEvent:
    """PM edited a code file without a prior Category-A Agent dispatch in this episode."""

    episode_id: str
    edit_position: int
    tool_name: str
    file_path: str
    file_extension: str
    had_trivial_allowlist_dispatch: bool
    had_declared_self_handle: bool


@dataclass(frozen=True)
class MalformedInstinctEvent:
    """Advisor was consulted but no PM-instinct: sentinel was present in the preceding assistant message."""

    episode_id: str
    advisor_position: int
    preceding_message_first_160: str


@dataclass(frozen=True)
class MalformedSkillsPassedEvent:
    """Specialist dispatch prompt had no Skills-passed: sentinel."""

    episode_id: str
    dispatch_position: int
    subagent_type: str
    prompt_first_160: str


@dataclass(frozen=True)
class MalformedAdvisorOutputEvent:
    """The Advisor's response could not be parsed into a ranked list."""

    episode_id: str
    advisor_position: int
    raw_output_first_300: str
    parse_error: str


@dataclass(frozen=True)
class SchemaViolationEvent:
    """The transcript contains a structure we didn't expect — roster drift, new tool name, etc."""

    episode_id: str
    position: int
    kind: str
    detail: str


AdvisorEvent: TypeAlias = (
    AgreementEvent
    | DriftEvent
    | DeclaredSelfHandleEvent
    | SelfHandleDriftEvent
    | MalformedInstinctEvent
    | MalformedSkillsPassedEvent
    | MalformedAdvisorOutputEvent
    | SchemaViolationEvent
)
