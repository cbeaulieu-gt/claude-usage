# tests/test_models.py
from datetime import datetime, timezone

from claude_usage.models import MessageRecord, SessionRecord


class TestMessageRecord:
    def test_total_tokens(self):
        msg = MessageRecord(
            timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            model="claude-opus-4-6",
            agent_type="general-purpose",
            skill=None,
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=200,
            cache_creation_tokens=300,
        )
        assert msg.total_tokens == 650

    def test_total_tokens_all_zero(self):
        msg = MessageRecord(
            timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            model="claude-sonnet-4-6",
            agent_type="code-writer",
            skill="superpowers:brainstorming",
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        assert msg.total_tokens == 0

    def test_model_short_name_opus(self):
        msg = MessageRecord(
            timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            model="claude-opus-4-6",
            agent_type="general-purpose",
            skill=None,
            input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_creation_tokens=0,
        )
        assert msg.model_short == "opus"

    def test_model_short_name_sonnet(self):
        msg = MessageRecord(
            timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            model="claude-sonnet-4-6",
            agent_type="code-writer",
            skill=None,
            input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_creation_tokens=0,
        )
        assert msg.model_short == "sonnet"

    def test_model_short_name_haiku(self):
        msg = MessageRecord(
            timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            model="claude-haiku-4-5-20251001",
            agent_type="ops",
            skill=None,
            input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_creation_tokens=0,
        )
        assert msg.model_short == "haiku"

    def test_model_short_name_unknown(self):
        msg = MessageRecord(
            timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            model="claude-future-model-9",
            agent_type="general-purpose",
            skill=None,
            input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_creation_tokens=0,
        )
        assert msg.model_short == "claude-future-model-9"


class TestSessionRecord:
    def _make_msg(self, model="claude-opus-4-6", agent="general-purpose",
                  input_t=100, output_t=50, cache_read=0, cache_create=0,
                  skill=None, ts=None):
        return MessageRecord(
            timestamp=ts or datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            model=model,
            agent_type=agent,
            skill=skill,
            input_tokens=input_t,
            output_tokens=output_t,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_create,
        )

    def test_total_tokens_sums_messages(self):
        session = SessionRecord(
            session_id="abc-123",
            project="my-project",
            start_time=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            root_agent="general-purpose",
            messages=[
                self._make_msg(input_t=100, output_t=50),
                self._make_msg(input_t=200, output_t=100),
            ],
            subagent_types=["code-writer"],
        )
        assert session.total_tokens == 450

    def test_total_tokens_empty_messages(self):
        session = SessionRecord(
            session_id="abc-123",
            project="my-project",
            start_time=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            root_agent="general-purpose",
            messages=[],
            subagent_types=[],
        )
        assert session.total_tokens == 0

    def test_duration_from_timestamps(self):
        session = SessionRecord(
            session_id="abc-123",
            project="my-project",
            start_time=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            root_agent="general-purpose",
            messages=[
                self._make_msg(ts=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)),
                self._make_msg(ts=datetime(2026, 4, 9, 12, 30, 0, tzinfo=timezone.utc)),
                self._make_msg(ts=datetime(2026, 4, 9, 13, 5, 0, tzinfo=timezone.utc)),
            ],
            subagent_types=[],
        )
        assert session.duration_minutes == 65

    def test_duration_single_message(self):
        session = SessionRecord(
            session_id="abc-123",
            project="my-project",
            start_time=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            root_agent="general-purpose",
            messages=[
                self._make_msg(ts=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)),
            ],
            subagent_types=[],
        )
        assert session.duration_minutes == 0

    def test_duration_no_messages(self):
        session = SessionRecord(
            session_id="abc-123",
            project="my-project",
            start_time=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
            root_agent="general-purpose",
            messages=[],
            subagent_types=[],
        )
        assert session.duration_minutes == 0
