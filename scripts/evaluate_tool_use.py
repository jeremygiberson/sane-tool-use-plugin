#!/usr/bin/env python3
"""Sane Tool Use — PreToolUse hook evaluator."""

import sys
import json


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
