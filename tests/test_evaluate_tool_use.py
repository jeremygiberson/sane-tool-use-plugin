#!/usr/bin/env python3
"""Tests for evaluate_tool_use.py"""

import json
import sys
import os
import subprocess
import hashlib
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import evaluate_tool_use as etu


def test_make_allow_decision():
    result = etu.make_decision("allow", "Safe read within project")
    assert result == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "Safe read within project"
        }
    }


def test_make_ask_decision():
    result = etu.make_decision("ask", "Sensitive file access")
    assert result == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "Sensitive file access"
        }
    }


def test_parse_hook_input_valid():
    raw = json.dumps({
        "session_id": "abc",
        "cwd": "/home/user/project",
        "tool_name": "Read",
        "tool_input": {"file_path": "/home/user/project/src/main.py"},
        "hook_event_name": "PreToolUse"
    })
    result = etu.parse_hook_input(raw)
    assert result["tool_name"] == "Read"
    assert result["tool_input"]["file_path"] == "/home/user/project/src/main.py"
    assert result["cwd"] == "/home/user/project"


def test_parse_hook_input_invalid_json():
    result = etu.parse_hook_input("not json")
    assert result is None


def test_parse_hook_input_missing_fields():
    raw = json.dumps({"session_id": "abc"})
    result = etu.parse_hook_input(raw)
    assert result is None


def test_get_project_root_from_git(tmp_path):
    with patch("evaluate_tool_use.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=str(tmp_path) + "\n", stderr=""
        )
        result = etu.get_project_root("/some/subdir")
        assert result == str(tmp_path)


def test_get_project_root_git_fails():
    with patch("evaluate_tool_use.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("git not found")
        result = etu.get_project_root("/fallback/dir")
        assert result == "/fallback/dir"


def test_resolve_path_absolute():
    result = etu.resolve_path("/absolute/path/file.py", "/project")
    assert result == "/absolute/path/file.py"


def test_resolve_path_relative():
    result = etu.resolve_path("src/main.py", "/project")
    assert result == "/project/src/main.py"


def test_resolve_path_relative_escape():
    result = etu.resolve_path("../../etc/passwd", "/project/src")
    assert result == "/etc/passwd"


def test_is_within_project_true():
    assert etu.is_within_project("/project/src/main.py", "/project") is True


def test_is_within_project_false():
    assert etu.is_within_project("/etc/passwd", "/project") is False


def test_is_within_project_exact_root():
    assert etu.is_within_project("/project", "/project") is True


def test_is_sensitive_file_env():
    assert etu.is_sensitive_file("/project/.env") is True


def test_is_sensitive_file_env_local():
    assert etu.is_sensitive_file("/project/.env.local") is True


def test_is_sensitive_file_normal():
    assert etu.is_sensitive_file("/project/src/main.py") is False


def test_is_sensitive_file_credentials():
    assert etu.is_sensitive_file("/project/credentials.json") is True


def test_is_sensitive_file_id_rsa():
    assert etu.is_sensitive_file("/home/user/.ssh/id_rsa") is True


def test_signature_bash():
    sig = etu.generate_signature("Bash", {"command": "npm test"}, "/project")
    assert sig == "npm test"


def test_signature_read():
    sig = etu.generate_signature("Read", {"file_path": "src/main.py"}, "/project")
    assert sig == "Read:/project/src/main.py"


def test_signature_write():
    sig = etu.generate_signature("Write", {"file_path": "/project/out.txt", "content": "hi"}, "/project")
    assert sig == "Write:/project/out.txt"


def test_signature_edit():
    sig = etu.generate_signature("Edit", {"file_path": "foo.py", "old_string": "a", "new_string": "b"}, "/project")
    assert sig == "Edit:/project/foo.py"


def test_signature_glob():
    sig = etu.generate_signature("Glob", {"pattern": "**/*.py", "path": "/project/src"}, "/project")
    assert sig == "Glob:**/*.py@/project/src"


def test_signature_glob_no_path():
    sig = etu.generate_signature("Glob", {"pattern": "**/*.py"}, "/project")
    assert sig == "Glob:**/*.py@/project"


def test_signature_grep():
    sig = etu.generate_signature("Grep", {"pattern": "TODO", "path": "/project"}, "/project")
    assert sig == "Grep:TODO@/project"


def test_signature_webfetch():
    sig = etu.generate_signature("WebFetch", {"url": "https://example.com"}, "/project")
    assert sig == "WebFetch:https://example.com"


def test_signature_websearch():
    sig = etu.generate_signature("WebSearch", {"query": "python async"}, "/project")
    assert sig == "WebSearch:python async"


def test_signature_agent():
    sig = etu.generate_signature("Agent", {"description": "search codebase", "prompt": "find X"}, "/project")
    assert sig == "Agent:search codebase"


def test_signature_unknown_tool():
    sig = etu.generate_signature("SomeTool", {"foo": "bar"}, "/project")
    assert sig == 'SomeTool:{"foo": "bar"}'


def test_cache_write_and_read(tmp_path):
    cache_file = tmp_path / "test-project.json"
    etu.cache_write(str(cache_file), "Bash", "npm test", "allow", "safe command")
    entries = etu.cache_read(str(cache_file))
    assert len(entries) == 1
    assert entries[0]["tool_name"] == "Bash"
    assert entries[0]["tool_input_signature"] == "npm test"
    assert entries[0]["decision"] == "allow"
    assert entries[0]["reason"] == "safe command"


def test_cache_append(tmp_path):
    cache_file = tmp_path / "test-project.json"
    etu.cache_write(str(cache_file), "Bash", "npm test", "allow", "safe")
    etu.cache_write(str(cache_file), "Read", "Read:/project/foo.py", "allow", "in project")
    entries = etu.cache_read(str(cache_file))
    assert len(entries) == 2


def test_cache_roundtrip_special_chars(tmp_path):
    """Values with colons, quotes, and newlines survive round-trip."""
    cache_file = tmp_path / "test-project.json"
    sig = 'echo "status: active"'
    etu.cache_write(str(cache_file), "Bash", sig, "allow", 'reason with "quotes"')
    result = etu.cache_lookup(str(cache_file), "Bash", sig)
    assert result == ("allow", 'reason with "quotes"')


def test_cache_lookup_hit(tmp_path):
    cache_file = tmp_path / "test-project.json"
    etu.cache_write(str(cache_file), "Bash", "npm test", "allow", "safe command")
    result = etu.cache_lookup(str(cache_file), "Bash", "npm test")
    assert result == ("allow", "safe command")


def test_cache_lookup_miss(tmp_path):
    cache_file = tmp_path / "test-project.json"
    etu.cache_write(str(cache_file), "Bash", "npm test", "allow", "safe command")
    result = etu.cache_lookup(str(cache_file), "Bash", "npm run deploy")
    assert result is None


def test_cache_read_nonexistent(tmp_path):
    cache_file = tmp_path / "nonexistent.json"
    entries = etu.cache_read(str(cache_file))
    assert entries == []


def test_cache_read_corrupt(tmp_path):
    cache_file = tmp_path / "bad.json"
    cache_file.write_text("this is not valid json!!")
    entries = etu.cache_read(str(cache_file))
    assert entries == []


def test_cache_write_creates_directories(tmp_path):
    cache_file = tmp_path / "deep" / "nested" / "dir" / "cache.json"
    etu.cache_write(str(cache_file), "Bash", "ls", "allow", "safe")
    assert cache_file.exists()
    entries = etu.cache_read(str(cache_file))
    assert len(entries) == 1


def test_get_project_id_from_git_remote(tmp_path):
    with patch("evaluate_tool_use.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="https://github.com/user/my-project.git\n", stderr=""
        )
        result = etu.get_project_id("/some/dir")
        assert result == "my-project"


def test_get_project_id_ssh_remote(tmp_path):
    with patch("evaluate_tool_use.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="git@github.com:user/my-project.git\n", stderr=""
        )
        result = etu.get_project_id("/some/dir")
        assert result == "my-project"


def test_get_project_id_fallback_to_hash():
    with patch("evaluate_tool_use.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("git not found")
        result = etu.get_project_id("/some/project/dir")
        expected = hashlib.sha256("/some/project/dir".encode()).hexdigest()[:16]
        assert result == expected


def test_get_cache_file_path():
    with patch("evaluate_tool_use.get_project_id", return_value="my-project"):
        result = etu.get_cache_file_path("/some/dir")
        expected = os.path.expanduser("~/.claude/sane-tool-use-plugin/.cache/my-project.json")
        assert result == expected


# Task 9: Deterministic Heuristics

def test_heuristic_read_in_project():
    result = etu.evaluate_heuristic("Read", {"file_path": "/project/src/main.py"}, "/project", "/project")
    assert result == ("allow", "Read-only access within project root")


def test_heuristic_read_outside_project():
    result = etu.evaluate_heuristic("Read", {"file_path": "/etc/passwd"}, "/project", "/project")
    assert result == ("ask", "File access outside project root: /etc/passwd")


def test_heuristic_read_sensitive():
    result = etu.evaluate_heuristic("Read", {"file_path": "/project/.env"}, "/project", "/project")
    assert result == ("ask", "Sensitive file access: /project/.env")


def test_heuristic_glob_in_project():
    result = etu.evaluate_heuristic("Glob", {"pattern": "**/*.py", "path": "/project"}, "/project", "/project")
    assert result == ("allow", "Read-only access within project root")


def test_heuristic_glob_no_path_defaults_to_cwd():
    result = etu.evaluate_heuristic("Glob", {"pattern": "**/*.py"}, "/project", "/project")
    assert result == ("allow", "Read-only access within project root")


def test_heuristic_grep_outside_project():
    result = etu.evaluate_heuristic("Grep", {"pattern": "TODO", "path": "/other"}, "/project", "/project")
    assert result == ("ask", "File access outside project root: /other")


def test_heuristic_webfetch():
    result = etu.evaluate_heuristic("WebFetch", {"url": "https://example.com"}, "/project", "/project")
    assert result == ("ask", "Web access: WebFetch")


def test_heuristic_websearch():
    result = etu.evaluate_heuristic("WebSearch", {"query": "python async"}, "/project", "/project")
    assert result == ("ask", "Web access: WebSearch")


def test_heuristic_bash_returns_none():
    result = etu.evaluate_heuristic("Bash", {"command": "npm test"}, "/project", "/project")
    assert result is None


def test_heuristic_write_returns_none():
    result = etu.evaluate_heuristic("Write", {"file_path": "/project/foo.py", "content": "x"}, "/project", "/project")
    assert result is None


def test_heuristic_edit_returns_none():
    result = etu.evaluate_heuristic("Edit", {"file_path": "/project/foo.py"}, "/project", "/project")
    assert result is None


def test_heuristic_agent_returns_none():
    result = etu.evaluate_heuristic("Agent", {"description": "explore"}, "/project", "/project")
    assert result is None


# Task 10: Claude Evaluation

def test_parse_claude_response_allow():
    output = json.dumps({
        "result": "",
        "structured_output": {"decision": "ALLOW", "reason": "Non-destructive test command"}
    })
    decision, reason = etu.parse_claude_response(output)
    assert decision == "allow"
    assert reason == "Non-destructive test command"


def test_parse_claude_response_ask():
    output = json.dumps({
        "result": "",
        "structured_output": {"decision": "ASK", "reason": "Potentially destructive"}
    })
    decision, reason = etu.parse_claude_response(output)
    assert decision == "ask"
    assert reason == "Potentially destructive"


def test_parse_claude_response_deny():
    output = json.dumps({
        "result": "",
        "structured_output": {"decision": "DENY", "reason": "Destroys filesystem"}
    })
    decision, reason = etu.parse_claude_response(output)
    assert decision == "deny"
    assert reason == "Destroys filesystem"


def test_parse_claude_response_missing_structured_output():
    output = json.dumps({"result": "some text"})
    result = etu.parse_claude_response(output)
    assert result is None


def test_parse_claude_response_invalid_json():
    result = etu.parse_claude_response("not json at all")
    assert result is None


def test_parse_claude_response_empty():
    result = etu.parse_claude_response("")
    assert result is None


def test_parse_claude_response_missing_decision():
    output = json.dumps({
        "result": "",
        "structured_output": {"reason": "no decision field"}
    })
    result = etu.parse_claude_response(output)
    assert result is None


def test_evaluate_with_claude_allow():
    mock_stdout = json.dumps({
        "result": "",
        "structured_output": {"decision": "ALLOW", "reason": "Safe test command"}
    })
    with patch("evaluate_tool_use.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=mock_stdout, stderr=""
        )
        result = etu.evaluate_with_claude("Bash", {"command": "npm test"}, "/project")
        assert result == ("allow", "Safe test command")
        call_args = mock_run.call_args[0][0]
        assert "--system-prompt" in call_args
        assert "--json-schema" in call_args
        assert "--output-format" in call_args
        max_turns_idx = call_args.index("--max-turns")
        assert call_args[max_turns_idx + 1] == "2"


def test_evaluate_with_claude_deny():
    mock_stdout = json.dumps({
        "result": "",
        "structured_output": {"decision": "DENY", "reason": "Destroys filesystem"}
    })
    with patch("evaluate_tool_use.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=mock_stdout, stderr=""
        )
        result = etu.evaluate_with_claude("Bash", {"command": "rm -rf /"}, "/project")
        assert result == ("deny", "Destroys filesystem")


def test_evaluate_with_claude_timeout():
    with patch("evaluate_tool_use.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=25)
        result = etu.evaluate_with_claude("Bash", {"command": "npm test"}, "/project")
        assert result == ("ask", "Evaluation timed out")


def test_evaluate_with_claude_not_found():
    with patch("evaluate_tool_use.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("claude not found")
        result = etu.evaluate_with_claude("Bash", {"command": "npm test"}, "/project")
        assert result == ("ask", "Claude CLI not available")


def test_evaluate_with_claude_parse_failure():
    with patch("evaluate_tool_use.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not json", stderr=""
        )
        result = etu.evaluate_with_claude("Bash", {"command": "npm test"}, "/project")
        assert result == ("ask", "Could not parse evaluation")


# Task 11: Wire Up main()

import io


def test_main_read_in_project(monkeypatch):
    """Full flow: Read within project -> heuristic ALLOW, no Claude call."""
    hook_input = json.dumps({
        "session_id": "s1", "cwd": "/project",
        "tool_name": "Read",
        "tool_input": {"file_path": "/project/src/main.py"},
        "hook_event_name": "PreToolUse", "tool_use_id": "t1"
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(hook_input))
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)
    with patch("evaluate_tool_use.get_project_root", return_value="/project"):
        with patch("evaluate_tool_use.get_cache_file_path", return_value="/tmp/test-cache.yml"):
            with patch("evaluate_tool_use.cache_lookup", return_value=None):
                etu.main()
    result = json.loads(output.getvalue())
    assert result["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_main_bash_cached(monkeypatch):
    """Full flow: Bash with cache hit -> return cached decision."""
    hook_input = json.dumps({
        "session_id": "s1", "cwd": "/project",
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "hook_event_name": "PreToolUse", "tool_use_id": "t1"
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(hook_input))
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)
    with patch("evaluate_tool_use.get_project_root", return_value="/project"):
        with patch("evaluate_tool_use.get_cache_file_path", return_value="/tmp/test-cache.yml"):
            with patch("evaluate_tool_use.cache_lookup", return_value=("allow", "cached safe")):
                etu.main()
    result = json.loads(output.getvalue())
    assert result["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert result["hookSpecificOutput"]["permissionDecisionReason"] == "cached safe"


def test_main_bash_uncached_calls_claude(monkeypatch):
    """Full flow: Bash with no cache -> Claude evaluation -> cache write."""
    hook_input = json.dumps({
        "session_id": "s1", "cwd": "/project",
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "hook_event_name": "PreToolUse", "tool_use_id": "t1"
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(hook_input))
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)
    with patch("evaluate_tool_use.get_project_root", return_value="/project"):
        with patch("evaluate_tool_use.get_cache_file_path", return_value="/tmp/test-cache.yml"):
            with patch("evaluate_tool_use.cache_lookup", return_value=None):
                with patch("evaluate_tool_use.evaluate_with_claude", return_value=("allow", "safe cmd")):
                    with patch("evaluate_tool_use.cache_write") as mock_write:
                        etu.main()
    result = json.loads(output.getvalue())
    assert result["hookSpecificOutput"]["permissionDecision"] == "allow"
    mock_write.assert_called_once_with("/tmp/test-cache.yml", "Bash", "npm test", "allow", "safe cmd")


def test_main_invalid_stdin(monkeypatch):
    """Full flow: invalid stdin -> ASK."""
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)
    etu.main()
    result = json.loads(output.getvalue())
    assert result["hookSpecificOutput"]["permissionDecision"] == "ask"


def _init_git_repo(path):
    """Initialize a git repo in the given path so get_project_root resolves correctly."""
    subprocess.run(["git", "init"], cwd=str(path), capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=str(path), capture_output=True)


def test_e2e_script_read_in_project(tmp_path):
    """Run the actual script as a subprocess with a Read tool input."""
    _init_git_repo(tmp_path)
    script_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'evaluate_tool_use.py')
    hook_input = json.dumps({
        "session_id": "s1", "cwd": str(tmp_path),
        "tool_name": "Read",
        "tool_input": {"file_path": str(tmp_path / "file.py")},
        "hook_event_name": "PreToolUse", "tool_use_id": "t1"
    })
    result = subprocess.run(
        ["python3", script_path],
        input=hook_input, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_e2e_script_env_file(tmp_path):
    """Run the actual script — .env file should trigger ASK."""
    _init_git_repo(tmp_path)
    script_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'evaluate_tool_use.py')
    hook_input = json.dumps({
        "session_id": "s1", "cwd": str(tmp_path),
        "tool_name": "Read",
        "tool_input": {"file_path": str(tmp_path / ".env")},
        "hook_event_name": "PreToolUse", "tool_use_id": "t1"
    })
    result = subprocess.run(
        ["python3", script_path],
        input=hook_input, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["hookSpecificOutput"]["permissionDecision"] == "ask"
