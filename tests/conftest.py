"""Shared test fixtures for claude-usage tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_session_dir(tmp_path: Path) -> Path:
    """Create a mock Claude Code projects directory with sample session data."""
    project_dir = tmp_path / "projects" / "C--Users-chris--myproject"
    project_dir.mkdir(parents=True)

    session_id = "abc-123-def"

    # Main session JSONL
    lines = [
        {
            "type": "agent-setting",
            "agentSetting": "general-purpose",
            "sessionId": session_id,
        },
        {
            "parentUuid": None,
            "type": "user",
            "message": {"role": "user", "content": "Hello"},
            "uuid": "msg-1",
            "timestamp": "2026-04-09T12:00:00.000Z",
            "sessionId": session_id,
        },
        {
            "parentUuid": "msg-1",
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-6",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi there"}],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 200,
                    "cache_creation_input_tokens": 300,
                },
            },
            "uuid": "msg-2",
            "timestamp": "2026-04-09T12:00:05.000Z",
            "sessionId": session_id,
        },
        {
            "parentUuid": "msg-2",
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-6",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Skill",
                        "input": {"skill": "superpowers:brainstorming"},
                    }
                ],
                "usage": {
                    "input_tokens": 50,
                    "output_tokens": 25,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            },
            "uuid": "msg-3",
            "timestamp": "2026-04-09T12:01:00.000Z",
            "sessionId": session_id,
        },
        {
            "parentUuid": "msg-3",
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-6",
                "role": "assistant",
                "content": [{"type": "text", "text": "Done"}],
                "usage": {
                    "input_tokens": 80,
                    "output_tokens": 40,
                    "cache_read_input_tokens": 100,
                    "cache_creation_input_tokens": 0,
                },
            },
            "uuid": "msg-4",
            "timestamp": "2026-04-09T12:30:00.000Z",
            "sessionId": session_id,
        },
    ]

    jsonl_path = project_dir / f"{session_id}.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(line) for line in lines),
        encoding="utf-8",
    )

    # Subagent directory
    subagent_dir = project_dir / session_id / "subagents"
    subagent_dir.mkdir(parents=True)

    # Subagent metadata
    meta = {"agentType": "code-writer", "description": "Write feature X"}
    (subagent_dir / "agent-sub1.meta.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )

    # Subagent JSONL
    sub_lines = [
        {
            "parentUuid": None,
            "type": "user",
            "agentId": "sub1",
            "message": {"role": "user", "content": "Implement feature X"},
            "uuid": "sub-msg-1",
            "timestamp": "2026-04-09T12:05:00.000Z",
            "sessionId": session_id,
        },
        {
            "parentUuid": "sub-msg-1",
            "type": "assistant",
            "agentId": "sub1",
            "message": {
                "model": "claude-sonnet-4-6",
                "role": "assistant",
                "content": [{"type": "text", "text": "Implementing..."}],
                "usage": {
                    "input_tokens": 500,
                    "output_tokens": 250,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 1000,
                },
            },
            "uuid": "sub-msg-2",
            "timestamp": "2026-04-09T12:10:00.000Z",
            "sessionId": session_id,
        },
    ]

    (subagent_dir / "agent-sub1.jsonl").write_text(
        "\n".join(json.dumps(line) for line in sub_lines),
        encoding="utf-8",
    )

    return tmp_path
