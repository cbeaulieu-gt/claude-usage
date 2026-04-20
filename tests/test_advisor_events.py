"""Tests for the typed advisor event taxonomy.

Covers all 8 frozen dataclasses and the AdvisorEvent TypeAlias.
Each class is tested for: successful construction, required-field
enforcement (TypeError on omission), and frozen immutability
(FrozenInstanceError on attribute assignment).
"""
import dataclasses
import typing

import pytest

from claude_usage.advisor_analyzer.events import (
    AdvisorEvent,
    AgreementEvent,
    DeclaredSelfHandleEvent,
    DriftEvent,
    MalformedAdvisorOutputEvent,
    MalformedInstinctEvent,
    MalformedSkillsPassedEvent,
    SchemaViolationEvent,
    SelfHandleDriftEvent,
)


# ---------------------------------------------------------------------------
# AgreementEvent
# ---------------------------------------------------------------------------

class TestAgreementEvent:
    """Tests for AgreementEvent frozen dataclass."""

    def _make(self, **overrides) -> AgreementEvent:
        """Return a fully-populated AgreementEvent, with optional overrides."""
        defaults = dict(
            episode_id="ep-001",
            advisor_position=2,
            dispatch_position=4,
            pm_instinct="delegate",
            advisor_top_agent="code-writer",
            advisor_ranked_agents=("code-writer", "ops"),
            pm_final_agent="code-writer",
            advisor_skills=frozenset({"python"}),
            pm_skills=frozenset({"python"}),
            match_rank=0,
        )
        defaults.update(overrides)
        return AgreementEvent(**defaults)

    def test_construction_succeeds(self) -> None:
        """Happy path: all required fields supplied."""
        event = self._make()
        assert event.episode_id == "ep-001"
        assert event.advisor_position == 2
        assert event.dispatch_position == 4
        assert event.pm_instinct == "delegate"
        assert event.advisor_top_agent == "code-writer"
        assert event.advisor_ranked_agents == ("code-writer", "ops")
        assert event.pm_final_agent == "code-writer"
        assert event.advisor_skills == frozenset({"python"})
        assert event.pm_skills == frozenset({"python"})
        assert event.match_rank == 0

    def test_pm_instinct_none_is_legal(self) -> None:
        """pm_instinct=None pairs with a companion MalformedInstinctEvent."""
        event = self._make(pm_instinct=None)
        assert event.pm_instinct is None

    def test_match_rank_int_when_agent_in_list(self) -> None:
        """match_rank stores an int when pm_final_agent was in ranked list."""
        ranked = ("ops", "code-writer", "router")
        agent = "code-writer"
        rank = ranked.index(agent) if agent in ranked else None
        event = self._make(
            advisor_ranked_agents=ranked,
            pm_final_agent=agent,
            match_rank=rank,
        )
        assert isinstance(event.match_rank, int)
        assert event.match_rank == 1

    def test_match_rank_none_when_agent_not_in_list(self) -> None:
        """match_rank is None when pm_final_agent was absent from ranked list."""
        ranked = ("ops", "router")
        agent = "code-writer"
        rank = ranked.index(agent) if agent in ranked else None
        event = self._make(
            advisor_ranked_agents=ranked,
            pm_final_agent=agent,
            match_rank=rank,
        )
        assert event.match_rank is None

    def test_advisor_skills_none_is_legal(self) -> None:
        """advisor_skills=None is accepted (optional field)."""
        event = self._make(advisor_skills=None)
        assert event.advisor_skills is None

    def test_pm_skills_none_is_legal(self) -> None:
        """pm_skills=None is accepted (optional field)."""
        event = self._make(pm_skills=None)
        assert event.pm_skills is None

    def test_omit_episode_id_raises_type_error(self) -> None:
        """Omitting episode_id raises TypeError."""
        with pytest.raises(TypeError):
            AgreementEvent(
                advisor_position=2,
                dispatch_position=4,
                pm_instinct="delegate",
                advisor_top_agent="code-writer",
                advisor_ranked_agents=("code-writer",),
                pm_final_agent="code-writer",
                advisor_skills=None,
                pm_skills=None,
                match_rank=0,
            )

    def test_frozen_raises_on_attribute_set(self) -> None:
        """Assigning to any field raises FrozenInstanceError."""
        event = self._make()
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.episode_id = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DriftEvent
# ---------------------------------------------------------------------------

class TestDriftEvent:
    """Tests for DriftEvent frozen dataclass."""

    def _make(self, **overrides) -> DriftEvent:
        defaults = dict(
            episode_id="ep-002",
            dispatch_position=3,
            subagent_type="code-writer",
            had_trivial_allowlist_dispatch=False,
        )
        defaults.update(overrides)
        return DriftEvent(**defaults)

    def test_construction_succeeds(self) -> None:
        event = self._make()
        assert event.episode_id == "ep-002"
        assert event.dispatch_position == 3
        assert event.subagent_type == "code-writer"
        assert event.had_trivial_allowlist_dispatch is False

    def test_omit_required_field_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            DriftEvent(
                dispatch_position=3,
                subagent_type="code-writer",
                had_trivial_allowlist_dispatch=False,
            )

    def test_frozen_raises_on_attribute_set(self) -> None:
        event = self._make()
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.subagent_type = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DeclaredSelfHandleEvent
# ---------------------------------------------------------------------------

class TestDeclaredSelfHandleEvent:
    """Tests for DeclaredSelfHandleEvent frozen dataclass."""

    def _make(self, **overrides) -> DeclaredSelfHandleEvent:
        defaults = dict(
            episode_id="ep-003",
            instinct_position=1,
            reasoning_excerpt="PM decided to handle inline.",
        )
        defaults.update(overrides)
        return DeclaredSelfHandleEvent(**defaults)

    def test_construction_succeeds(self) -> None:
        event = self._make()
        assert event.episode_id == "ep-003"
        assert event.instinct_position == 1
        assert event.reasoning_excerpt == "PM decided to handle inline."

    def test_omit_required_field_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            DeclaredSelfHandleEvent(
                instinct_position=1,
                reasoning_excerpt="excerpt",
            )

    def test_frozen_raises_on_attribute_set(self) -> None:
        event = self._make()
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.reasoning_excerpt = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SelfHandleDriftEvent
# ---------------------------------------------------------------------------

class TestSelfHandleDriftEvent:
    """Tests for SelfHandleDriftEvent frozen dataclass."""

    def _make(self, **overrides) -> SelfHandleDriftEvent:
        defaults = dict(
            episode_id="ep-004",
            edit_position=5,
            tool_name="Edit",
            file_path="src/main.py",
            file_extension=".py",
            had_trivial_allowlist_dispatch=False,
            had_declared_self_handle=False,
        )
        defaults.update(overrides)
        return SelfHandleDriftEvent(**defaults)

    def test_construction_succeeds(self) -> None:
        event = self._make()
        assert event.episode_id == "ep-004"
        assert event.edit_position == 5
        assert event.tool_name == "Edit"
        assert event.file_path == "src/main.py"
        assert event.file_extension == ".py"
        assert event.had_trivial_allowlist_dispatch is False
        assert event.had_declared_self_handle is False

    def test_omit_required_field_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            SelfHandleDriftEvent(
                edit_position=5,
                tool_name="Edit",
                file_path="src/main.py",
                file_extension=".py",
                had_trivial_allowlist_dispatch=False,
                had_declared_self_handle=False,
            )

    def test_frozen_raises_on_attribute_set(self) -> None:
        event = self._make()
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.file_path = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MalformedInstinctEvent
# ---------------------------------------------------------------------------

class TestMalformedInstinctEvent:
    """Tests for MalformedInstinctEvent frozen dataclass."""

    def _make(self, **overrides) -> MalformedInstinctEvent:
        defaults = dict(
            episode_id="ep-005",
            advisor_position=2,
            preceding_message_first_160="No instinct sentinel found here.",
        )
        defaults.update(overrides)
        return MalformedInstinctEvent(**defaults)

    def test_construction_succeeds(self) -> None:
        event = self._make()
        assert event.episode_id == "ep-005"
        assert event.advisor_position == 2
        assert (
            event.preceding_message_first_160
            == "No instinct sentinel found here."
        )

    def test_omit_required_field_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            MalformedInstinctEvent(
                advisor_position=2,
                preceding_message_first_160="excerpt",
            )

    def test_frozen_raises_on_attribute_set(self) -> None:
        event = self._make()
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.advisor_position = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MalformedSkillsPassedEvent
# ---------------------------------------------------------------------------

class TestMalformedSkillsPassedEvent:
    """Tests for MalformedSkillsPassedEvent frozen dataclass."""

    def _make(self, **overrides) -> MalformedSkillsPassedEvent:
        defaults = dict(
            episode_id="ep-006",
            dispatch_position=7,
            subagent_type="ops",
            prompt_first_160="Dispatch prompt without skills sentinel.",
        )
        defaults.update(overrides)
        return MalformedSkillsPassedEvent(**defaults)

    def test_construction_succeeds(self) -> None:
        event = self._make()
        assert event.episode_id == "ep-006"
        assert event.dispatch_position == 7
        assert event.subagent_type == "ops"
        assert (
            event.prompt_first_160
            == "Dispatch prompt without skills sentinel."
        )

    def test_omit_required_field_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            MalformedSkillsPassedEvent(
                dispatch_position=7,
                subagent_type="ops",
                prompt_first_160="excerpt",
            )

    def test_frozen_raises_on_attribute_set(self) -> None:
        event = self._make()
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.subagent_type = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MalformedAdvisorOutputEvent
# ---------------------------------------------------------------------------

class TestMalformedAdvisorOutputEvent:
    """Tests for MalformedAdvisorOutputEvent frozen dataclass."""

    def _make(self, **overrides) -> MalformedAdvisorOutputEvent:
        defaults = dict(
            episode_id="ep-007",
            advisor_position=3,
            raw_output_first_300="Could not parse ranked list from: ...",
            parse_error="No numbered list found",
        )
        defaults.update(overrides)
        return MalformedAdvisorOutputEvent(**defaults)

    def test_construction_succeeds(self) -> None:
        event = self._make()
        assert event.episode_id == "ep-007"
        assert event.advisor_position == 3
        assert event.raw_output_first_300 == (
            "Could not parse ranked list from: ..."
        )
        assert event.parse_error == "No numbered list found"

    def test_omit_required_field_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            MalformedAdvisorOutputEvent(
                advisor_position=3,
                raw_output_first_300="raw",
                parse_error="err",
            )

    def test_frozen_raises_on_attribute_set(self) -> None:
        event = self._make()
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.parse_error = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SchemaViolationEvent
# ---------------------------------------------------------------------------

class TestSchemaViolationEvent:
    """Tests for SchemaViolationEvent frozen dataclass."""

    def _make(self, **overrides) -> SchemaViolationEvent:
        defaults = dict(
            episode_id="ep-008",
            position=10,
            kind="unknown_tool_name",
            detail="Encountered tool 'NewTool' not in known roster.",
        )
        defaults.update(overrides)
        return SchemaViolationEvent(**defaults)

    def test_construction_succeeds(self) -> None:
        event = self._make()
        assert event.episode_id == "ep-008"
        assert event.position == 10
        assert event.kind == "unknown_tool_name"
        assert event.detail == (
            "Encountered tool 'NewTool' not in known roster."
        )

    def test_omit_required_field_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            SchemaViolationEvent(
                position=10,
                kind="unknown_tool_name",
                detail="detail",
            )

    def test_frozen_raises_on_attribute_set(self) -> None:
        event = self._make()
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.kind = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AdvisorEvent TypeAlias
# ---------------------------------------------------------------------------

class TestAdvisorEventTypeAlias:
    """Tests for the AdvisorEvent union TypeAlias."""

    def test_advisor_event_is_importable(self) -> None:
        """AdvisorEvent can be imported from events module."""
        # Import already at top of file; just assert the name is bound.
        assert AdvisorEvent is not None

    def test_advisor_event_is_type_alias(self) -> None:
        """AdvisorEvent is a typing.TypeAlias resolving to a union."""
        # typing.get_args returns the union members for a Union / X|Y alias.
        args = typing.get_args(AdvisorEvent)
        assert len(args) == 8, (
            f"Expected 8 union members, got {len(args)}: {args}"
        )

    def test_advisor_event_union_contains_all_classes(self) -> None:
        """All 8 event classes appear in the AdvisorEvent union."""
        args = set(typing.get_args(AdvisorEvent))
        expected = {
            AgreementEvent,
            DriftEvent,
            DeclaredSelfHandleEvent,
            SelfHandleDriftEvent,
            MalformedInstinctEvent,
            MalformedSkillsPassedEvent,
            MalformedAdvisorOutputEvent,
            SchemaViolationEvent,
        }
        assert expected == args
