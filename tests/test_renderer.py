"""Tests for the HTML dashboard renderer, including responsiveness."""

from __future__ import annotations

from pathlib import Path

from claude_usage.aggregator import AggregateResult
from claude_usage.renderer import render


def _minimal_result() -> AggregateResult:
    """Build a minimal AggregateResult with no sessions."""
    return AggregateResult()


def _render_html(tmp_path: Path, result: AggregateResult | None = None) -> str:
    """Render the dashboard and return the HTML string.

    Args:
        tmp_path: Pytest temporary directory.
        result: Aggregate result to render. Defaults to a minimal result.

    Returns:
        Rendered HTML as a string.
    """
    if result is None:
        result = _minimal_result()
    output = tmp_path / "dashboard.html"
    render(result, output_path=output, open_browser=False)
    return output.read_text(encoding="utf-8")


class TestResponsiveness:
    """Verify the rendered dashboard HTML is responsive."""

    def test_rendered_html_contains_media_query(self, tmp_path: Path) -> None:
        """Rendered dashboard must contain at least one @media query.

        Without @media queries the layout cannot adapt to narrow viewports.
        This is the minimal gate for a responsive dashboard.
        """
        html = _render_html(tmp_path)
        assert "@media" in html, (
            "Rendered dashboard HTML must contain at least one @media query "
            "so the layout adapts to different viewport sizes."
        )

    def test_viewport_meta_tag_present(self, tmp_path: Path) -> None:
        """Rendered HTML must contain a viewport meta tag.

        The viewport meta tag is required so mobile browsers scale the
        layout to the device width rather than rendering a zoomed-out
        desktop view.
        """
        html = _render_html(tmp_path)
        assert (
            'name="viewport"' in html
        ), "Rendered HTML must contain a viewport meta tag."
        assert (
            "width=device-width" in html
        ), "Viewport meta tag must include width=device-width."

    def test_gauge_grid_uses_auto_fill(self, tmp_path: Path) -> None:
        """Gauge grid must use auto-fill or responsive grid-template-columns.

        A fixed ``repeat(3, 1fr)`` column definition will not wrap on narrow
        screens. The fix uses ``repeat(auto-fill, minmax(...))`` or media
        queries to allow the grid to collapse.
        """
        html = _render_html(tmp_path)
        has_autofill = "auto-fill" in html or "auto-fit" in html
        has_gauge_media = "@media" in html and ".gauges" in html
        assert has_autofill or has_gauge_media, (
            "Gauge grid must use auto-fill/auto-fit or a media query so it "
            "collapses from 3 columns to fewer on narrow screens."
        )

    def test_grid2_collapses_on_narrow_screens(self, tmp_path: Path) -> None:
        """Two-column card sections must collapse to one column via @media.

        The .grid-2 class currently uses a fixed two-column layout. On
        screens below ~800 px it must become a single column.
        """
        html = _render_html(tmp_path)
        # The template must define a breakpoint that makes .grid-2
        # single-column. We accept any media query that references grid-2.
        assert "@media" in html and "grid-2" in html, (
            "A @media query targeting .grid-2 must be present to collapse "
            "the two-column layout on narrow screens."
        )

    def test_session_list_responsive(self, tmp_path: Path) -> None:
        """Session list must be responsive: stacked cards or scroll container.

        The fixed grid-template-columns on .session-row forces horizontal
        overflow at narrow widths. The fix must either switch to a stacked
        card layout via @media, or wrap the list in an overflow-x:auto
        container so scrolling is contained rather than page-wide.
        """
        html = _render_html(tmp_path)
        has_session_media = "@media" in html and "session" in html
        has_overflow_scroll = (
            "overflow-x" in html or "overflow: auto" in html or "overflow:auto" in html
        )
        assert has_session_media or has_overflow_scroll, (
            "Session list must handle narrow viewports: either use a @media "
            "query to reflow as stacked cards, or use overflow-x:auto on a "
            "containing element."
        )
