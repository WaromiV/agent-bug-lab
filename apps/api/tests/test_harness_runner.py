"""Unit tests for the harness abstraction — argv shaping, prompt wrapping, and
the forgiving JSON extraction that turns messy CLI output into a dict."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.harness_runner import (
    ClaudeCodeSpec,
    CodexSpec,
    build_prompt,
    get_harness,
    parse_model_json,
)

DATA = Path("/tmp/abl-test")


# ── parse_model_json ────────────────────────────────────────────────────────
def test_parse_plain_json():
    assert parse_model_json('{"status": "ok", "bugs": []}') == {"status": "ok", "bugs": []}


def test_parse_strips_json_code_fence():
    text = '```json\n{"status": "ok"}\n```'
    assert parse_model_json(text) == {"status": "ok"}


def test_parse_strips_bare_code_fence():
    assert parse_model_json('```\n{"a": 1}\n```') == {"a": 1}


def test_parse_recovers_object_from_surrounding_prose():
    text = 'Sure! Here is the result:\n{"status": "ok", "n": 2}\nLet me know if that helps.'
    assert parse_model_json(text) == {"status": "ok", "n": 2}


def test_parse_brace_balance_ignores_braces_inside_strings():
    # A naive "find last }" would mis-slice; the balance scanner must not be
    # fooled by braces living inside string literals.
    text = '{"desc": "use the {token} here", "ok": true}'
    assert parse_model_json(text) == {"desc": "use the {token} here", "ok": True}


def test_parse_handles_escaped_quote_in_string():
    text = '{"q": "she said \\"hi\\"", "n": 1}'
    assert parse_model_json(text) == {"q": 'she said "hi"', "n": 1}


def test_parse_picks_first_balanced_object_when_trailing_junk():
    text = '{"a": {"b": 1}} trailing noise {"c": 2}'
    assert parse_model_json(text) == {"a": {"b": 1}}


def test_parse_raises_without_any_object():
    with pytest.raises(json.JSONDecodeError):
        parse_model_json("no json here at all")


def test_parse_raises_on_unbalanced_braces():
    with pytest.raises(json.JSONDecodeError):
        parse_model_json('{"a": 1')


# ── build_prompt ──────────────────────────────────────────────────────────--
def test_build_prompt_embeds_payload_and_rules():
    prompt = build_prompt({"role": "searcher_agent", "x": 1})
    assert '"role": "searcher_agent"' in prompt
    assert "single JSON object" in prompt
    assert "READ-ONLY" in prompt


# ── CodexSpec argv ────────────────────────────────────────────────────────--
def test_codex_fresh_argv_shape():
    argv = CodexSpec().build_argv(
        binary="codex", model="gpt-x", resume_session=None, data_dir=DATA
    )
    assert argv[:2] == ["codex", "exec"]
    assert "--sandbox" in argv and "read-only" in argv
    assert argv[-1] == "-"  # reads prompt from stdin
    assert "resume" not in argv
    assert argv[argv.index("-m") + 1] == "gpt-x"


def test_codex_resume_uses_resume_subcommand():
    argv = CodexSpec().build_argv(
        binary="codex", model="gpt-x", resume_session="sess-42", data_dir=DATA
    )
    assert argv[:3] == ["codex", "exec", "resume"]
    assert argv[3] == "sess-42"


def test_codex_has_no_effort_flag():
    assert CodexSpec().effort_args("high") == []


# ── ClaudeCodeSpec argv ───────────────────────────────────────────────────--
def test_claude_fresh_argv_shape():
    argv = ClaudeCodeSpec().build_argv(
        binary="claude", model="opus", resume_session=None, data_dir=DATA
    )
    assert argv[0] == "claude"
    assert "--output-format" in argv and "json" in argv
    assert "--permission-mode" in argv and "bypassPermissions" in argv
    assert "--resume" not in argv


def test_claude_resume_appends_resume_flag():
    argv = ClaudeCodeSpec().build_argv(
        binary="claude", model="opus", resume_session="abc", data_dir=DATA
    )
    assert argv[-2:] == ["--resume", "abc"]


def test_claude_effort_flag():
    assert ClaudeCodeSpec().effort_args("max") == ["--effort", "max"]
    assert ClaudeCodeSpec().effort_args(None) == []


# ── extract_output: Codex (reads last-message file, falls back to stdout) ───--
def test_codex_extract_prefers_last_message_file(tmp_path):
    (tmp_path / "codex_last_message.txt").write_text('{"status": "ok"}')
    out, err = CodexSpec().extract_output(
        stdout="ignored", stderr="", exit_code=0, data_dir=tmp_path
    )
    assert err is None and out == {"status": "ok"}


def test_codex_extract_falls_back_to_stdout(tmp_path):
    out, err = CodexSpec().extract_output(
        stdout='{"status": "ok"}', stderr="", exit_code=0, data_dir=tmp_path
    )
    assert err is None and out == {"status": "ok"}


def test_codex_extract_empty_is_error(tmp_path):
    out, err = CodexSpec().extract_output(
        stdout="   ", stderr="", exit_code=0, data_dir=tmp_path
    )
    assert out is None and "empty" in err


def test_codex_extract_non_json_is_error(tmp_path):
    out, err = CodexSpec().extract_output(
        stdout="not json", stderr="", exit_code=0, data_dir=tmp_path
    )
    assert out is None and "not JSON" in err


# ── extract_output: Claude (unwraps the --output-format json envelope) ──────--
def test_claude_extract_unwraps_envelope_and_lifts_session_id(tmp_path):
    envelope = json.dumps(
        {"result": '{"status": "ok", "bugs": []}', "session_id": "sess-9"}
    )
    out, err = ClaudeCodeSpec().extract_output(
        stdout=envelope, stderr="", exit_code=0, data_dir=tmp_path
    )
    assert err is None
    assert out["status"] == "ok"
    # session_id is bubbled into the payload so --resume "just works".
    assert out["harness_session_id"] == "sess-9"


def test_claude_extract_does_not_clobber_existing_session_id(tmp_path):
    envelope = json.dumps(
        {"result": '{"status": "ok", "harness_session_id": "from-model"}',
         "session_id": "from-envelope"}
    )
    out, _ = ClaudeCodeSpec().extract_output(
        stdout=envelope, stderr="", exit_code=0, data_dir=tmp_path
    )
    assert out["harness_session_id"] == "from-model"


def test_claude_extract_bad_envelope_is_error(tmp_path):
    out, err = ClaudeCodeSpec().extract_output(
        stdout="not json", stderr="", exit_code=1, data_dir=tmp_path
    )
    assert out is None and "envelope not JSON" in err


def test_claude_extract_missing_result_is_error(tmp_path):
    out, err = ClaudeCodeSpec().extract_output(
        stdout=json.dumps({"session_id": "x"}), stderr="", exit_code=0, data_dir=tmp_path
    )
    assert out is None and "missing string `result`" in err


def test_claude_extract_result_not_json_is_error(tmp_path):
    out, err = ClaudeCodeSpec().extract_output(
        stdout=json.dumps({"result": "I refuse to emit JSON"}),
        stderr="", exit_code=0, data_dir=tmp_path,
    )
    assert out is None and "result text not JSON" in err


# ── registry ──────────────────────────────────────────────────────────────--
def test_get_harness_known():
    assert get_harness("codex").name == "codex"
    assert get_harness("claude_code").name == "claude_code"


def test_get_harness_unknown_raises():
    with pytest.raises(ValueError, match="unknown harness"):
        get_harness("gpt-cli")
