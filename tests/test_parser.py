from datetime import datetime, timezone
from pathlib import Path

from claude_usage.parser import decode_project_hash, parse_sessions


class TestDecodeProjectHash:
    def test_windows_path_deep(self):
        assert decode_project_hash("C--Users-chris--claude") == "claude"

    def test_windows_path_shallow(self):
        assert decode_project_hash("i--games-raid-rsl-rule-generator") == "games-raid-rsl-rule-generator"

    def test_single_segment(self):
        assert decode_project_hash("myproject") == "myproject"

    def test_three_segments(self):
        assert decode_project_hash("C--Users-chris--code-deep-nested--project") == "project"

    def test_empty_string(self):
        assert decode_project_hash("") == ""


class TestParseSessions:
    def test_parses_single_session(self, sample_session_dir: Path):
        sessions = parse_sessions(sample_session_dir)
        assert len(sessions) == 1

    def test_session_metadata(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        assert session.session_id == "abc-123-def"
        assert session.project == "myproject"
        assert session.root_agent == "general-purpose"

    def test_session_start_time(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        expected = datetime(2026, 4, 9, 12, 0, 5, tzinfo=timezone.utc)
        assert session.start_time == expected

    def test_message_count_includes_subagent(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        # 3 parent assistant messages + 1 subagent assistant message = 4
        assert len(session.messages) == 4

    def test_parent_messages_attributed_to_root_agent(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        parent_msgs = [m for m in session.messages if m.agent_type == "general-purpose"]
        assert len(parent_msgs) == 3

    def test_subagent_messages_attributed_to_agent_type(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        sub_msgs = [m for m in session.messages if m.agent_type == "code-writer"]
        assert len(sub_msgs) == 1
        assert sub_msgs[0].input_tokens == 500
        assert sub_msgs[0].output_tokens == 250

    def test_skill_extracted_from_tool_use(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        skill_msgs = [m for m in session.messages if m.skill is not None]
        assert len(skill_msgs) == 1
        assert skill_msgs[0].skill == "superpowers:brainstorming"

    def test_subagent_types_listed(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        assert session.subagent_types == ["code-writer"]

    def test_token_totals(self, sample_session_dir: Path):
        session = parse_sessions(sample_session_dir)[0]
        # Parent: (100+50+200+300) + (50+25+0+0) + (80+40+100+0) = 650+75+220 = 945
        # Subagent: 500+250+0+1000 = 1750
        # Total: 2695
        assert session.total_tokens == 2695

    def test_empty_projects_dir(self, tmp_path: Path):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        sessions = parse_sessions(tmp_path)
        assert sessions == []

    def test_no_projects_dir(self, tmp_path: Path):
        sessions = parse_sessions(tmp_path)
        assert sessions == []
