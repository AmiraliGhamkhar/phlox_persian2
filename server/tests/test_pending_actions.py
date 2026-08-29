"""Tests for the mutating-tool confirmation gate (pending action store)."""

import time

from server.chat.tools.pending_actions import (
    pop_pending_action,
    register_pending_action,
    summarize_tool_args,
)


def _tool_call(name="create_note", args='{"patient_name": "Test Patient"}'):
    return {"id": "call_1", "function": {"name": name, "arguments": args}}


class TestPendingActions:
    def test_register_and_pop_roundtrip(self):
        action = register_pending_action(tool_call=_tool_call(), tool_name="create_note")
        assert action.tool_name == "create_note"
        popped = pop_pending_action(action.id)
        assert popped is not None
        assert popped.tool_name == "create_note"
        # Second pop fails: the action is single-use
        assert pop_pending_action(action.id) is None

    def test_unknown_id_is_none(self):
        assert pop_pending_action("does-not-exist") is None

    def test_expired_action_is_dropped(self):
        action = register_pending_action(tool_call=_tool_call(), tool_name="create_note")
        action.created_at = time.time() - 3600  # simulate expiry
        assert pop_pending_action(action.id) is None

    def test_store_is_bounded(self):
        for _ in range(150):
            register_pending_action(tool_call=_tool_call(), tool_name="create_note")
        assert len(_pending_dict()) <= 100


def _pending_dict():
    from server.chat.tools import pending_actions

    return pending_actions._pending


def test_summarize_tool_args_compact_and_safe():
    args = '{"patient_name": "Jane Doe", "initial_notes": "' + "x" * 500 + '"}'
    summary = summarize_tool_args(_tool_call(args=args))
    assert len(summary) <= 300
    assert "Jane Doe" in summary


def test_summarize_tool_args_malformed_json():
    summary = summarize_tool_args(_tool_call(args="{not json"))
    assert "arguments" in summary
