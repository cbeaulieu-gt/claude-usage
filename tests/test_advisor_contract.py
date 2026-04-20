"""Contract tests pinning the output shape of parse_advisor_output().

These tests are intentionally RED. The module under test —
``claude_usage.advisor_analyzer`` — does not exist yet. Task 4 of
the PM/Router Advisor Phase 1 plan will create it.

Running this file before Task 4 must fail with::

    ModuleNotFoundError: No module named 'claude_usage.advisor_analyzer'

Refs: cbeaulieu-gt/claude_personal_configs#69 (Task 2)
"""

from __future__ import annotations

import pytest

from claude_usage.advisor_analyzer import parse_advisor_output  # noqa: E402

# ---------------------------------------------------------------------------
# Sample output — verbatim copy of the format emitted by agents/advisor.md
# ---------------------------------------------------------------------------

SAMPLE_OUTPUT = """\
## Routing Recommendation

**Task summary:** Add a new REST endpoint to the user service

### Candidates

1. **code-writer** — confidence 0.85
   - Skills: python, fastapi
   - MCP: Use Context7 to fetch current FastAPI docs before writing endpoint code.
   - Why: Task is net-new feature work, which is exactly code-writer's mandate.

2. **debugger** — confidence 0.25
   - Skills: none
   - MCP: none
   - Why: Included only as a weak fallback if the endpoint already exists and is broken.

### Notes
- Project-scope skills directory found at <cwd>/skills/ — no matches against task context.
- No Category B/C agents applicable.
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parsed() -> dict:
    """Return parse_advisor_output(SAMPLE_OUTPUT) once for all assertions."""
    return parse_advisor_output(SAMPLE_OUTPUT)


# ---------------------------------------------------------------------------
# Contract: top-level shape
# ---------------------------------------------------------------------------

class TestTopLevelShape:
    """parse_advisor_output returns a dict with all required top-level keys."""

    def test_returns_dict(self) -> None:
        """Result is a plain dict."""
        assert isinstance(_parsed(), dict)

    def test_has_top_pick_key(self) -> None:
        """Result contains 'top_pick'."""
        assert "top_pick" in _parsed()

    def test_has_top_confidence_key(self) -> None:
        """Result contains 'top_confidence'."""
        assert "top_confidence" in _parsed()

    def test_has_candidates_key(self) -> None:
        """Result contains 'candidates'."""
        assert "candidates" in _parsed()

    def test_has_task_summary_key(self) -> None:
        """Result contains 'task_summary'."""
        assert "task_summary" in _parsed()

    def test_no_extra_top_level_keys(self) -> None:
        """Result contains exactly the four required keys — nothing more."""
        assert set(_parsed().keys()) == {
            "top_pick",
            "top_confidence",
            "candidates",
            "task_summary",
        }


# ---------------------------------------------------------------------------
# Contract: scalar field types and constraints
# ---------------------------------------------------------------------------

class TestScalarFields:
    """top_pick, top_confidence, and task_summary have correct types."""

    def test_top_pick_is_string(self) -> None:
        """top_pick is a str."""
        assert isinstance(_parsed()["top_pick"], str)

    def test_top_pick_is_highest_ranked_agent(self) -> None:
        """top_pick equals the first candidate's agent name."""
        result = _parsed()
        assert result["top_pick"] == "code-writer"

    def test_top_confidence_is_float(self) -> None:
        """top_confidence is a float."""
        assert isinstance(_parsed()["top_confidence"], float)

    def test_top_confidence_within_range(self) -> None:
        """top_confidence is in [0.0, 1.0]."""
        confidence = _parsed()["top_confidence"]
        assert 0.0 <= confidence <= 1.0

    def test_top_confidence_matches_sample(self) -> None:
        """top_confidence equals 0.85 as specified in SAMPLE_OUTPUT."""
        assert _parsed()["top_confidence"] == pytest.approx(0.85)

    def test_task_summary_is_string(self) -> None:
        """task_summary is a str."""
        assert isinstance(_parsed()["task_summary"], str)

    def test_task_summary_is_non_empty(self) -> None:
        """task_summary is not an empty string."""
        assert _parsed()["task_summary"].strip() != ""

    def test_task_summary_matches_sample(self) -> None:
        """task_summary reflects the line from SAMPLE_OUTPUT."""
        assert _parsed()["task_summary"] == (
            "Add a new REST endpoint to the user service"
        )


# ---------------------------------------------------------------------------
# Contract: candidates list shape
# ---------------------------------------------------------------------------

class TestCandidatesShape:
    """candidates is a list of well-formed dicts."""

    def test_candidates_is_list(self) -> None:
        """candidates is a list."""
        assert isinstance(_parsed()["candidates"], list)

    def test_candidates_has_two_items(self) -> None:
        """SAMPLE_OUTPUT contains exactly two candidates."""
        assert len(_parsed()["candidates"]) == 2

    def test_each_candidate_is_dict(self) -> None:
        """Every entry in candidates is a dict."""
        for candidate in _parsed()["candidates"]:
            assert isinstance(candidate, dict)

    def test_each_candidate_has_required_keys(self) -> None:
        """Every candidate dict has exactly agent, confidence, skills,
        mcp_notes, and why."""
        required = {"agent", "confidence", "skills", "mcp_notes", "why"}
        for candidate in _parsed()["candidates"]:
            assert set(candidate.keys()) == required

    def test_candidate_agent_is_string(self) -> None:
        """agent field on each candidate is a str."""
        for candidate in _parsed()["candidates"]:
            assert isinstance(candidate["agent"], str)

    def test_candidate_confidence_is_float(self) -> None:
        """confidence field on each candidate is a float."""
        for candidate in _parsed()["candidates"]:
            assert isinstance(candidate["confidence"], float)

    def test_candidate_confidence_within_range(self) -> None:
        """confidence on each candidate is in [0.0, 1.0]."""
        for candidate in _parsed()["candidates"]:
            assert 0.0 <= candidate["confidence"] <= 1.0

    def test_candidate_skills_is_frozenset(self) -> None:
        """skills field on each candidate is a frozenset."""
        for candidate in _parsed()["candidates"]:
            assert isinstance(candidate["skills"], frozenset)

    def test_candidate_skills_are_lowercase_strings(self) -> None:
        """Every skill string inside skills is lowercase."""
        for candidate in _parsed()["candidates"]:
            for skill in candidate["skills"]:
                assert isinstance(skill, str)
                assert skill == skill.lower()

    def test_candidate_mcp_notes_is_string(self) -> None:
        """mcp_notes field on each candidate is a str."""
        for candidate in _parsed()["candidates"]:
            assert isinstance(candidate["mcp_notes"], str)

    def test_candidate_why_is_string(self) -> None:
        """why field on each candidate is a str."""
        for candidate in _parsed()["candidates"]:
            assert isinstance(candidate["why"], str)


# ---------------------------------------------------------------------------
# Contract: candidate values from SAMPLE_OUTPUT
# ---------------------------------------------------------------------------

class TestCandidateValues:
    """Parsed candidate field values match the SAMPLE_OUTPUT literals."""

    def test_first_candidate_agent_name(self) -> None:
        """First candidate is 'code-writer'."""
        assert _parsed()["candidates"][0]["agent"] == "code-writer"

    def test_first_candidate_confidence(self) -> None:
        """First candidate confidence is 0.85."""
        assert _parsed()["candidates"][0]["confidence"] == pytest.approx(0.85)

    def test_first_candidate_skills(self) -> None:
        """First candidate skills are {python, fastapi}."""
        assert _parsed()["candidates"][0]["skills"] == frozenset(
            {"python", "fastapi"}
        )

    def test_second_candidate_agent_name(self) -> None:
        """Second candidate is 'debugger'."""
        assert _parsed()["candidates"][1]["agent"] == "debugger"

    def test_second_candidate_confidence(self) -> None:
        """Second candidate confidence is 0.25."""
        assert _parsed()["candidates"][1]["confidence"] == pytest.approx(0.25)

    def test_second_candidate_skills_none_becomes_empty_frozenset(self) -> None:
        """A Skills line of 'none' is represented as an empty frozenset."""
        assert _parsed()["candidates"][1]["skills"] == frozenset()


# ---------------------------------------------------------------------------
# Contract: ordering invariant
# ---------------------------------------------------------------------------

class TestCandidateOrdering:
    """Candidates are returned in descending order of confidence."""

    def test_candidates_ordered_by_descending_confidence(self) -> None:
        """Each candidate's confidence >= the next candidate's confidence."""
        candidates = _parsed()["candidates"]
        for i in range(len(candidates) - 1):
            assert candidates[i]["confidence"] >= candidates[i + 1]["confidence"]


# ---------------------------------------------------------------------------
# Contract: error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """parse_advisor_output raises ValueError for malformed input."""

    def test_plain_string_raises_value_error(self) -> None:
        """A string with no advisor structure raises ValueError."""
        with pytest.raises(ValueError):
            parse_advisor_output("not a recommendation")

    def test_empty_string_raises_value_error(self) -> None:
        """An empty string raises ValueError."""
        with pytest.raises(ValueError):
            parse_advisor_output("")

    def test_partial_header_only_raises_value_error(self) -> None:
        """A string with just the heading but no candidates raises ValueError."""
        with pytest.raises(ValueError):
            parse_advisor_output("## Routing Recommendation\n")
