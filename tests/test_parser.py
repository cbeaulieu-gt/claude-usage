from claude_usage.parser import decode_project_hash


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
