"""End-to-end test: parse sample data -> aggregate -> render HTML."""

import json
from pathlib import Path

from claude_usage.aggregator import aggregate
from claude_usage.parser import parse_sessions
from claude_usage.renderer import render


class TestEndToEnd:
    def test_full_pipeline(self, sample_session_dir: Path, tmp_path: Path):
        """Parse sample fixtures, aggregate, render to HTML file."""
        sessions = parse_sessions(sample_session_dir)
        assert len(sessions) == 1

        result = aggregate(sessions)
        assert result.total_tokens > 0
        assert result.total_sessions == 1
        assert "opus" in result.by_model
        assert "general-purpose" in result.by_agent

        output_path = tmp_path / "dashboard.html"
        rendered = render(result, output_path=output_path, open_browser=False)
        assert rendered.exists()

        html = rendered.read_text(encoding="utf-8")
        assert "Chart" in html or "chart" in html
        assert "claude" in html.lower()

    def test_full_pipeline_with_limits(self, sample_session_dir: Path, tmp_path: Path):
        sessions = parse_sessions(sample_session_dir)
        result = aggregate(sessions)

        limits = {"limit_5h": 600000, "limit_7d": 4000000, "limit_sonnet_7d": 2000000}
        output_path = tmp_path / "dashboard-limits.html"
        rendered = render(result, output_path=output_path, open_browser=False, limits=limits)
        assert rendered.exists()

        html = rendered.read_text(encoding="utf-8")
        assert "600000" in html or "limit_5h" in html

    def test_empty_data(self, tmp_path: Path):
        sessions = parse_sessions(tmp_path)
        result = aggregate(sessions)
        assert result.total_tokens == 0

        output_path = tmp_path / "empty.html"
        rendered = render(result, output_path=output_path, open_browser=False)
        assert rendered.exists()


class TestSkillAdoptionE2E:
    def test_adoption_data_in_rendered_html(self, sample_session_dir: Path, tmp_path: Path):
        """Verify skill adoption data appears in the rendered dashboard."""
        from claude_usage.aggregator import compute_skill_adoption
        from claude_usage.skill_tracking import parse_skill_tracking

        tracking_file = sample_session_dir / "skill-tracking.jsonl"
        lines = [
            json.dumps({"event": "skill_passed", "skill": "python", "target_agent": "code-writer", "timestamp": "2026-04-09T21:00:00Z", "session_id": "test-1"}),
            json.dumps({"event": "skill_invoked", "skill": "python", "timestamp": "2026-04-09T21:01:00Z", "session_id": "test-1"}),
        ]
        tracking_file.write_text("\n".join(lines) + "\n")

        sessions = parse_sessions(sample_session_dir)
        result = aggregate(sessions)

        passed, invoked = parse_skill_tracking(sample_session_dir)
        result.by_skill_adoption = compute_skill_adoption(passed, invoked)

        output = tmp_path / "test-dashboard.html"
        render(result, output_path=output, open_browser=False)

        html = output.read_text(encoding="utf-8")
        assert "Skill Adoption" in html
        assert "python" in html
