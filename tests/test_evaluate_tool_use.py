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
