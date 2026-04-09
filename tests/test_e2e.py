"""End-to-end test: parse sample data -> aggregate -> render HTML."""

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
