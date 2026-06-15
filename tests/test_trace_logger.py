"""Tests for TraceLogger and NullTraceLogger."""

import json

import pytest

from extensions.tracing.logger import TraceLogger
from extensions.tracing import NullTraceLogger


class TestTraceLoggerDisabled:
    """Tests for TraceLogger when enabled=False."""

    def test_no_file_created(self, tmp_path):
        logger = TraceLogger(
            session_id="s-20260101-120000-abcd",
            trace_dir=tmp_path / "traces",
            enabled=False,
        )
        assert logger.enabled is False
        assert logger.session_id == "s-20260101-120000-abcd"
        assert logger._filepath is None

        logger.log_event("user_input", {"text": "hello"}, step=0)
        logger.log_system_messages([{"role": "system", "content": "be helpful"}])
        logger.finalize()

        jsonl_files = list((tmp_path / "traces").glob("trace-*.jsonl"))
        assert len(jsonl_files) == 0

    def test_events_are_no_ops(self, tmp_path):
        logger = TraceLogger(
            session_id="s-20260101-120000-abcd",
            trace_dir=tmp_path,
            enabled=False,
        )
        logger.log_event("user_input", {"text": "hello"})
        logger.log_event("model_output", {"raw": "hi", "usage": {"total_tokens": 10}})
        logger.log_system_messages([{"role": "system", "content": "be helpful"}])

        assert logger._total_steps == 0
        assert logger._tools_used == 0
        assert logger._total_usage["total_tokens"] == 0


class TestTraceLoggerEnabled:
    """Tests for TraceLogger when enabled=True."""

    def test_jsonl_file_created(self, tmp_path):
        logger = TraceLogger(
            session_id="s-test",
            trace_dir=tmp_path / "traces",
            enabled=True,
        )
        assert logger.enabled is True
        assert logger._filepath is not None
        assert logger._filepath.exists()
        logger.finalize()

    def test_log_event_writes_valid_jsonl(self, tmp_path):
        trace_dir = tmp_path / "traces"
        logger = TraceLogger(
            session_id="s-test",
            trace_dir=trace_dir,
            enabled=True,
        )
        logger.log_event("user_input", {"text": "hello"}, step=0)
        logger.log_event(
            "model_output",
            {
                "raw": "hi there",
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            },
            step=1,
        )
        logger.finalize()

        lines = logger._filepath.read_text(encoding="utf-8").strip().split("\n")
        # events: user_input, model_output, session_summary
        assert len(lines) >= 3

        for line in lines:
            obj = json.loads(line)
            for field in ("ts", "session_id", "step", "event", "payload"):
                assert field in obj, f"missing field '{field}' in line: {line}"

    def test_required_fields_in_each_event(self, tmp_path):
        """Each JSONL line must have ts, session_id, step, event, payload."""
        logger = TraceLogger(
            session_id="s-reqfields",
            trace_dir=tmp_path / "traces",
            enabled=True,
        )
        logger.log_event("tool_call", {"tool": "LS", "args": {}}, step=1)
        logger.log_event("tool_result", {"tool": "LS", "result": {"status": "ok"}}, step=1)
        logger.log_event("error", {"message": "something went wrong"}, step=2)
        logger.finalize()

        required = {"ts", "session_id", "step", "event", "payload"}
        for line in logger._filepath.read_text(encoding="utf-8").strip().split("\n"):
            obj = json.loads(line)
            assert obj["session_id"] == "s-reqfields"
            assert obj["event"]
            assert isinstance(obj["step"], int)
            assert isinstance(obj["payload"], dict)
            assert required <= set(obj.keys())

    def test_log_system_messages(self, tmp_path):
        logger = TraceLogger(
            session_id="s-sysmsg",
            trace_dir=tmp_path / "traces",
            enabled=True,
        )
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "system", "content": "Use tools when needed."},
        ]
        logger.log_system_messages(messages)
        # Calling again should be a no-op
        logger.log_system_messages([{"role": "system", "content": "again"}])
        logger.finalize()

        lines = logger._filepath.read_text(encoding="utf-8").strip().split("\n")
        system_message_events = [
            json.loads(line)
            for line in lines
            if json.loads(line)["event"] == "system_messages"
        ]
        assert len(system_message_events) == 1
        payload = system_message_events[0]["payload"]
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"

    def test_finalize_writes_session_summary(self, tmp_path):
        logger = TraceLogger(
            session_id="s-summary",
            trace_dir=tmp_path / "traces",
            enabled=True,
        )
        logger.log_event("model_output", {"raw": "a", "usage": {"total_tokens": 10}}, step=1)
        logger.log_event("tool_call", {"tool": "Read", "args": {"filePath": "x.py"}}, step=1)
        logger.log_event("model_output", {"raw": "b", "usage": {"total_tokens": 20}}, step=2)
        logger.finalize()

        lines = logger._filepath.read_text(encoding="utf-8").strip().split("\n")
        last = json.loads(lines[-1])
        assert last["event"] == "session_summary"
        summary = last["payload"]
        assert summary["steps"] == 2
        assert summary["tools_used"] == 1
        assert summary["total_usage"]["total_tokens"] == 30
        assert summary["total_usage"]["prompt_tokens"] == 0
        assert summary["total_usage"]["completion_tokens"] == 0

    def test_total_usage_tracks_tokens(self, tmp_path):
        logger = TraceLogger(
            session_id="s-usage",
            trace_dir=tmp_path / "traces",
            enabled=True,
        )
        assert logger._total_usage == {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        logger.log_event(
            "model_output",
            {
                "raw": "first",
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 30,
                    "total_tokens": 130,
                },
            },
            step=1,
        )
        logger.log_event(
            "model_output",
            {
                "raw": "second",
                "usage": {
                    "prompt_tokens": 200,
                    "completion_tokens": 50,
                    "total_tokens": 250,
                },
            },
            step=2,
        )
        logger.log_event("finish", {"final": "done"}, step=2)

        assert logger._total_usage["prompt_tokens"] == 300
        assert logger._total_usage["completion_tokens"] == 80
        assert logger._total_usage["total_tokens"] == 380
        assert logger._total_steps == 2

    def test_context_manager_auto_finalizes(self, tmp_path):
        trace_dir = tmp_path / "traces"
        with TraceLogger(
            session_id="s-ctx",
            trace_dir=trace_dir,
            enabled=True,
        ) as logger:
            logger.log_event("user_input", {"text": "hello"}, step=0)

        # After exiting the with block, finalize() should have been called
        content = logger._filepath.read_text(encoding="utf-8").strip().split("\n")
        assert len(content) >= 2
        last = json.loads(content[-1])
        assert last["event"] == "session_summary"


class TestNullTraceLogger:
    """Tests for the no-op NullTraceLogger."""

    def test_all_methods_are_no_ops(self):
        logger = NullTraceLogger()
        assert logger.enabled is False
        assert logger.session_id == "disabled"
        assert logger._total_usage == {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        # All methods should return None and not raise
        assert logger.log_event("user_input", {"text": "x"}) is None
        assert logger.log_system_messages([{"role": "system", "content": "x"}]) is None
        assert logger.finalize() is None

    def test_no_file_created(self, tmp_path):
        logger = NullTraceLogger()
        logger.log_event("user_input", {"text": "hello"})
        logger.finalize()

        # NullTraceLogger has no _filepath attribute, and no file should be created
        jsonl_files = list(tmp_path.glob("*.jsonl"))
        assert len(jsonl_files) == 0
