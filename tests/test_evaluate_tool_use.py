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
