#!/usr/bin/env python3
"""Sane Tool Use — PreToolUse hook evaluator."""

import sys
import json
import subprocess
import os
import re
import hashlib


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


def generate_signature(tool_name: str, tool_input: dict, cwd: str) -> str:
    """Generate a cache signature for a tool call."""
    if tool_name == "Bash":
        return tool_input.get("command", "")
    elif tool_name in ("Read", "Write", "Edit"):
        path = resolve_path(tool_input.get("file_path", ""), cwd)
        return f"{tool_name}:{path}"
    elif tool_name in ("Glob", "Grep"):
        pattern = tool_input.get("pattern", "")
        path = resolve_path(tool_input.get("path", cwd), cwd)
        return f"{tool_name}:{pattern}@{path}"
    elif tool_name == "WebFetch":
        return f"WebFetch:{tool_input.get('url', '')}"
    elif tool_name == "WebSearch":
        return f"WebSearch:{tool_input.get('query', '')}"
    elif tool_name == "Agent":
        return f"Agent:{tool_input.get('description', '')}"
    else:
        return f"{tool_name}:{json.dumps(tool_input, sort_keys=True)}"


def get_project_id(cwd: str) -> str:
    """Get a project identifier from git remote, falling back to path hash."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=cwd, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            url = result.stdout.strip()
            name = url.rstrip("/").rsplit("/", 1)[-1]
            if name.endswith(".git"):
                name = name[:-4]
            if name:
                return name
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return hashlib.sha256(cwd.encode()).hexdigest()[:16]


def get_cache_file_path(cwd: str) -> str:
    """Get the cache file path for the current project."""
    project_id = get_project_id(cwd)
    return os.path.expanduser(f"~/.claude/sane-tool-use-plugin/.cache/{project_id}.json")


def cache_read(cache_file: str) -> list[dict]:
    """Read cache entries from a JSON file. Returns [] on any error."""
    try:
        with open(cache_file, "r") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            return data["entries"]
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        pass
    return []


def cache_write(cache_file: str, tool_name: str, signature: str, decision: str, reason: str) -> None:
    """Append a cache entry to the JSON file. Creates file and dirs if needed."""
    try:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        entries = cache_read(cache_file)
        entries.append({
            "tool_name": tool_name,
            "tool_input_signature": signature,
            "decision": decision,
            "reason": reason,
        })
        with open(cache_file, "w") as f:
            json.dump({"entries": entries}, f, indent=2)
    except OSError:
        pass  # Can't write cache — non-fatal


def cache_lookup(cache_file: str, tool_name: str, signature: str) -> tuple[str, str] | None:
    """Look up a cached decision. Returns (decision, reason) or None."""
    entries = cache_read(cache_file)
    for entry in entries:
        if entry.get("tool_name") == tool_name and entry.get("tool_input_signature") == signature:
            return (entry["decision"], entry["reason"])
    return None


READ_ONLY_TOOLS = {"Read", "Glob", "Grep"}
WEB_TOOLS = {"WebFetch", "WebSearch"}


def evaluate_heuristic(tool_name: str, tool_input: dict, cwd: str, project_root: str) -> tuple[str, str] | None:
    """Apply deterministic heuristics. Returns (decision, reason) or None if ambiguous."""
    if tool_name in READ_ONLY_TOOLS:
        return _evaluate_file_read(tool_name, tool_input, cwd, project_root)
    if tool_name in WEB_TOOLS:
        return ("ask", f"Web access: {tool_name}")
    return None


def _evaluate_file_read(tool_name: str, tool_input: dict, cwd: str, project_root: str) -> tuple[str, str]:
    """Evaluate a read-only file tool against project boundaries and sensitivity."""
    if tool_name == "Read":
        path = tool_input.get("file_path", "")
    else:
        path = tool_input.get("path", cwd)

    resolved = resolve_path(path, cwd)

    # Check project boundaries first (matches spec ordering)
    if not is_within_project(resolved, project_root):
        return ("ask", f"File access outside project root: {resolved}")

    # Check sensitive files within project
    if is_sensitive_file(resolved):
        return ("ask", f"Sensitive file access: {resolved}")

    return ("allow", "Read-only access within project root")


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
