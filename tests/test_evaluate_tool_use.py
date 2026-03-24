#!/usr/bin/env python3
"""Tests for evaluate_tool_use.py"""

import json
import sys
import os
import subprocess
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
