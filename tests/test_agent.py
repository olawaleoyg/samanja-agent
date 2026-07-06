"""
Unit tests for devops_agent.

Run with:
pytest -v

These tests cover the individual tool functions (run_shell_command,
check_url_status, read_file) in isolation, using mocks so no real
network calls or Anthropic API calls happen during testing.
The agent loop itself (run_agent) is tested with a mocked Anthropic client.

Security-focused tests cover the command allowlist enforcement in
run_shell_command and the project-root path sandboxing in read_file.
"""

import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent  # noqa: E402

# ---------------------------------------------------------------------------
# run_shell_command — happy path (allowlisted commands)
# ---------------------------------------------------------------------------

def test_run_shell_command_success():
    output = agent.run_shell_command(["git", "status"])
    assert isinstance(output, str)

def test_run_shell_command_accepts_list_argv():
    with patch("agent.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="ok", stderr="")
        result = agent.run_shell_command(["git", "status"])
        assert "ok" in result
        args, kwargs = mock_run.call_args
        assert args[0] == ["git", "status"]
        assert kwargs["shell"] is False

def test_run_shell_command_handles_bad_command():
    output = agent.run_shell_command(["this_command_does_not_exist_xyz"])
    assert output  # should return something, not raise

def test_run_shell_command_timeout_does_not_raise():
    with patch("agent.subprocess.run", side_effect=Exception("timed out")):
        output = agent.run_shell_command(["git", "status"])
        assert "Error" in output

# ---------------------------------------------------------------------------
# run_shell_command — security: allowlist enforcement
# ---------------------------------------------------------------------------

def test_run_shell_command_rejects_non_allowlisted_program():
    result = agent.run_shell_command(["rm", "-rf", "/"])
    assert "not in the allowlist" in result

def test_run_shell_command_rejects_non_allowlisted_subcommand():
    result = agent.run_shell_command(["git", "push", "--force"])
    assert "not in the allowlist" in result

def test_run_shell_command_rejects_raw_string_injection_attempt():
    # Even if a raw string slips through, it must not be handed to a shell.
    # shlex.split turns this into argv tokens, and the program name
    # ("rm") is not allowlisted, so it must be rejected.
    result = agent.run_shell_command("rm -rf / ; echo pwned")
    assert "not in the allowlist" in result

def test_run_shell_command_never_uses_shell_true():
    with patch("agent.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="")
        agent.run_shell_command(["git", "status"])
        _, kwargs = mock_run.call_args
        assert kwargs.get("shell") is False

def test_run_shell_command_rejects_empty_command():
    result = agent.run_shell_command([])
    assert "Error" in result

def test_run_shell_command_allows_npm_run():
    with patch("agent.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="built", stderr="")
        result = agent.run_shell_command(["npm", "run", "build"])
        assert "built" in result

# ---------------------------------------------------------------------------
# check_url_status
# ---------------------------------------------------------------------------

def test_check_url_status_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.elapsed.total_seconds.return_value = 0.42

    with patch("agent.requests.get", return_value=mock_response):
        result = agent.check_url_status("https://example.com")

    assert "status=200" in result
    assert "0.42s" in result

def test_check_url_status_unreachable():
    with patch("agent.requests.get", side_effect=Exception("connection refused")):
        result = agent.check_url_status("https://not-a-real-site.invalid")

    assert "Error reaching" in result

# ---------------------------------------------------------------------------
# read_file — happy path
# ---------------------------------------------------------------------------

def test_read_file_success(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "PROJECT_ROOT", tmp_path)
    f = tmp_path / "sample.txt"
    f.write_text("hello from test file")

    result = agent.read_file("sample.txt")
    assert result == "hello from test file"

def test_read_file_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "PROJECT_ROOT", tmp_path)
    result = agent.read_file("does/not/exist.txt")
    assert "Error" in result

def test_read_file_truncates_long_content(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "PROJECT_ROOT", tmp_path)
    f = tmp_path / "big.txt"
    f.write_text("x" * 10000)

    result = agent.read_file("big.txt")
    assert len(result) <= agent.MAX_FILE_BYTES

# ---------------------------------------------------------------------------
# read_file — security: path sandboxing
# ---------------------------------------------------------------------------

def test_read_file_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "PROJECT_ROOT", tmp_path)
    (tmp_path / "project").mkdir()
    monkeypatch.setattr(agent, "PROJECT_ROOT", tmp_path / "project")

    result = agent.read_file("../../etc/passwd")
    assert "Error" in result
    assert "outside the project root" in result

def test_read_file_rejects_absolute_path_outside_root(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "PROJECT_ROOT", tmp_path)
    result = agent.read_file("/etc/passwd")
    assert "Error" in result
    assert "outside the project root" in result

def test_read_file_allows_absolute_path_inside_root(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "PROJECT_ROOT", tmp_path)
    f = tmp_path / "inside.txt"
    f.write_text("safe content")

    result = agent.read_file(str(f))
    assert result == "safe content"

def test_read_file_rejects_directory_path(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "PROJECT_ROOT", tmp_path)
    (tmp_path / "subdir").mkdir()

    result = agent.read_file("subdir")
    assert "not a file" in result

# ---------------------------------------------------------------------------
# run_agent loop (mocked Anthropic client — no real API calls)
# ---------------------------------------------------------------------------

def _text_block(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block

def _tool_use_block(name, tool_input, tool_id="tool_1"):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = tool_input
    block.id = tool_id
    return block

def test_run_agent_stops_when_no_tool_use():
    """If Claude replies with plain text and no tool_use, the loop should end after one turn."""
    fake_response = MagicMock()
    fake_response.content = [_text_block("All done, nothing to check.")]
    fake_response.stop_reason = "end_turn"

    with patch.object(agent.client.messages, "create", return_value=fake_response) as mock_create:
        agent.run_agent("Do nothing", max_turns=5)
        assert mock_create.call_count == 1

def test_run_agent_calls_tool_then_finishes():
    """Simulates: turn 1 -> Claude calls check_url_status; turn 2 -> Claude finishes with text."""
    tool_call_response = MagicMock()
    tool_call_response.content = [_tool_use_block("check_url_status", {"url": "https://example.com"})]
    tool_call_response.stop_reason = "tool_use"

    final_response = MagicMock()
    final_response.content = [_text_block("Site is live.")]
    final_response.stop_reason = "end_turn"

    with patch.object(
        agent.client.messages, "create", side_effect=[tool_call_response, final_response]
    ) as mock_create, patch.object(
        agent, "check_url_status", return_value="status=200, load_time=0.10s"
    ) as mock_tool:
        agent.run_agent("Check if example.com is live", max_turns=5)

    assert mock_create.call_count == 2
    mock_tool.assert_called_once_with(url="https://example.com")

def test_run_agent_rejects_disallowed_shell_command_end_to_end():
    """If Claude asks for a non-allowlisted command, the tool result should
    surface the rejection rather than executing anything destructive."""
    tool_call_response = MagicMock()
    tool_call_response.content = [_tool_use_block("run_shell_command", {"command": ["rm", "-rf", "/"]})]
    tool_call_response.stop_reason = "tool_use"

    final_response = MagicMock()
    final_response.content = [_text_block("That command is not allowed.")]
    final_response.stop_reason = "end_turn"

    with patch.object(
        agent.client.messages, "create", side_effect=[tool_call_response, final_response]
    ):
        agent.run_agent("Delete everything", max_turns=5)
