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


SYSTEM_PROMPT_TEMPLATE = """You are a security evaluator for CLI tool calls in a software project. Evaluate whether each tool call is safe.

Project root: {project_root}

Rules (in priority order):

DENY — unrecoverable or clearly malicious:
- Commands that destroy data outside git tracking (rm -rf /, wipefs, dd)
- Commands that rewrite or erase git history (git reset --hard, git push --force, git rebase with destructive intent)
- Exfiltration of secrets or environment variables (env | curl, cat ~/.ssh/id_rsa | nc)
- Downloading and executing opaque remote code (curl ... | bash, wget ... && sh)
- Any command designed to damage the system, network, or other projects

ALLOW — safe, non-destructive, or recoverable:
- Read-only commands (ls, cat, grep, find, git status, git log, git diff)
- Build, test, lint, typecheck commands (npm test, pytest, eslint, make)
- Writing or editing files within the project root (recoverable via git)
- Deleting files within the project that are tracked by git (recoverable via git checkout)
- Running inline scripts where the full script content is visible in the command (e.g. echo "console.log('hi')" | node, python -c "print('hello')")
- Git commits, branch creation, checkout (non-destructive git operations)
- Package install for the project (npm install, pip install -r requirements.txt)

ASK — ambiguous, needs human review:
- Deleting files that are git-ignored or untracked (not recoverable)
- Commands that pipe or execute content not visible in the command itself (cat file.txt | bash, node script.js where script content is unknown)
- Network-facing commands (starting servers, opening ports)
- Package publish or global install (npm publish, pip install --global)
- Anything not clearly covered by ALLOW or DENY rules
- When uncertain, choose ASK"""

JSON_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["ALLOW", "ASK", "DENY"]},
        "reason": {"type": "string"}
    },
    "required": ["decision", "reason"]
})


def parse_claude_response(output: str) -> tuple[str, str] | None:
    """Parse Claude's structured JSON evaluation response. Returns (decision, reason) or None."""
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return None
    structured = data.get("structured_output")
    if not isinstance(structured, dict):
        return None
    decision = structured.get("decision")
    reason = structured.get("reason")
    if not isinstance(decision, str) or not isinstance(reason, str):
        return None
    decision_lower = decision.lower()
    if decision_lower not in ("allow", "ask", "deny"):
        return None
    return (decision_lower, reason)


def evaluate_with_claude(tool_name: str, tool_input: dict, project_root: str) -> tuple[str, str]:
    """Spawn claude -p to evaluate a tool call. Returns (decision, reason)."""
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(project_root=project_root)
    prompt = f"Tool: {tool_name}\nInput: {json.dumps(tool_input, indent=2)}"
    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--system-prompt", system_prompt,
                "--json-schema", JSON_SCHEMA,
                "--output-format", "json",
                "--max-turns", "2",
                "--disable-slash-commands",
            ],
            capture_output=True, text=True, timeout=25
        )
        if result.returncode == 0 and result.stdout.strip():
            parsed = parse_claude_response(result.stdout)
            if parsed:
                return parsed
            return ("ask", "Could not parse evaluation")
        return ("ask", "Claude evaluation returned no output")
    except subprocess.TimeoutExpired:
        return ("ask", "Evaluation timed out")
    except FileNotFoundError:
        return ("ask", "Claude CLI not available")
    except OSError as e:
        return ("ask", f"Claude evaluation error: {e}")


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
    try:
        raw_input = sys.stdin.read()
        hook_data = parse_hook_input(raw_input)
        if hook_data is None:
            json.dump(make_decision("ask", "Failed to parse tool input"), sys.stdout)
            return

        tool_name = hook_data["tool_name"]
        tool_input = hook_data["tool_input"]
        cwd = hook_data["cwd"]

        project_root = get_project_root(cwd)
        cache_file = get_cache_file_path(cwd)
        signature = generate_signature(tool_name, tool_input, cwd)

        # Layer 1: Cache
        cached = cache_lookup(cache_file, tool_name, signature)
        if cached:
            decision, reason = cached
            json.dump(make_decision(decision, reason), sys.stdout)
            return

        # Layer 2: Heuristics
        heuristic_result = evaluate_heuristic(tool_name, tool_input, cwd, project_root)
        if heuristic_result:
            decision, reason = heuristic_result
            json.dump(make_decision(decision, reason), sys.stdout)
            return

        # Layer 3: Claude evaluation
        decision, reason = evaluate_with_claude(tool_name, tool_input, project_root)
        cache_write(cache_file, tool_name, signature, decision, reason)
        json.dump(make_decision(decision, reason), sys.stdout)

    except Exception as e:
        json.dump(make_decision("ask", f"Unexpected error: {e}"), sys.stdout)


if __name__ == "__main__":
    main()
