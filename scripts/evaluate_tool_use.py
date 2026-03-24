#!/usr/bin/env python3
"""Sane Tool Use — PreToolUse hook evaluator."""

import sys
import json
import subprocess


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
