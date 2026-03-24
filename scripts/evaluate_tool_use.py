#!/usr/bin/env python3
"""Sane Tool Use — PreToolUse hook evaluator."""

import sys
import json
import subprocess
import os
import re


def resolve_path(file_path: str, cwd: str) -> str:
    """Resolve a file path against cwd to get an absolute path."""
    if os.path.isabs(file_path):
        return os.path.normpath(file_path)
    return os.path.normpath(os.path.join(cwd, file_path))


def is_within_project(resolved_path: str, project_root: str) -> bool:
    """Check if a resolved path is within the project root."""
    rp = os.path.normpath(resolved_path)
    pr = os.path.normpath(project_root)
    return rp == pr or rp.startswith(pr + os.sep)


SENSITIVE_PATTERNS = [
    re.compile(r'(^|/)\.env($|\.)'),
    re.compile(r'(^|/)credentials\.json$'),
    re.compile(r'(^|/)\.ssh/'),
    re.compile(r'(^|/)id_rsa'),
    re.compile(r'(^|/)\.aws/'),
    re.compile(r'(^|/)secrets?\.(json|ya?ml|toml)$'),
]


def is_sensitive_file(file_path: str) -> bool:
    """Check if a file path matches known sensitive patterns."""
    return any(p.search(file_path) for p in SENSITIVE_PATTERNS)


def get_project_root(cwd: str) -> str:
    """Get project root via git, falling back to cwd."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, cwd=cwd, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return cwd


def parse_hook_input(raw: str) -> dict | None:
    """Parse hook input JSON from stdin. Returns None if invalid."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not all(k in data for k in ("tool_name", "tool_input", "cwd")):
        return None
    return data


def make_decision(decision: str, reason: str) -> dict:
    """Build a PreToolUse decision control response."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason
        }
    }


def main():
    """Entry point. Reads hook input from stdin, outputs decision JSON to stdout."""
    # Placeholder — always ASK until logic is implemented
    decision = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "Evaluation not yet implemented"
        }
    }
    json.dump(decision, sys.stdout)


if __name__ == "__main__":
    main()
