# Sane Tool Use Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code plugin that auto-allows safe tool calls and escalates risky ones via a PreToolUse hook backed by heuristics and Claude evaluation.

**Architecture:** Single Python script handles all evaluation via three layers: cache lookup, deterministic heuristics for read-only file tools, and `claude -p` for everything ambiguous. Plugin is three files: manifest, hook config, and the script.

**Tech Stack:** Python 3 (stdlib only), Claude CLI (`claude -p`), JSON cache format

---

## File Structure

| File | Responsibility |
|------|---------------|
| `.claude-plugin/plugin.json` | Plugin manifest — name, version, hook path |
| `hooks/hooks.json` | Hook config — PreToolUse matcher and command |
| `scripts/evaluate_tool_use.py` | All evaluation logic: stdin parsing, cache, heuristics, Claude invocation, response output |
| `tests/test_evaluate_tool_use.py` | Unit tests for all evaluation logic |

---

### Task 1: Plugin Scaffolding

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `hooks/hooks.json`
- Create: `scripts/evaluate_tool_use.py` (empty entry point)

- [ ] **Step 1: Create plugin manifest**

`.claude-plugin/plugin.json`:
```json
{
  "name": "sane-tool-use",
  "description": "Intelligent tool use gating — auto-allows safe actions, escalates risky ones",
  "version": "1.0.0",
  "hooks": "./hooks/hooks.json"
}
```

- [ ] **Step 2: Create hook configuration**

`hooks/hooks.json`:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/evaluate_tool_use.py",
            "timeout": 30,
            "statusMessage": "Evaluating tool safety..."
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 3: Create empty script entry point**

`scripts/evaluate_tool_use.py`:
```python
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
```

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/plugin.json hooks/hooks.json scripts/evaluate_tool_use.py
git commit -m "feat: scaffold plugin structure with manifest, hook config, and entry point"
```

---

### Task 2: Decision Output Helpers

**Files:**
- Modify: `scripts/evaluate_tool_use.py`
- Create: `tests/test_evaluate_tool_use.py`

- [ ] **Step 1: Write failing tests for output helpers**

`tests/test_evaluate_tool_use.py`:
```python
#!/usr/bin/env python3
"""Tests for evaluate_tool_use.py"""

import json
import sys
import os

# Add scripts directory to path so we can import the module
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: FAIL with `AttributeError: module 'evaluate_tool_use' has no attribute 'make_decision'`

- [ ] **Step 3: Implement make_decision**

Add to `scripts/evaluate_tool_use.py` (before `main`):
```python
def make_decision(decision: str, reason: str) -> dict:
    """Build a PreToolUse decision control response."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason
        }
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_tool_use.py tests/test_evaluate_tool_use.py
git commit -m "feat: add make_decision helper with tests"
```

---

### Task 3: Stdin Parsing

**Files:**
- Modify: `scripts/evaluate_tool_use.py`
- Modify: `tests/test_evaluate_tool_use.py`

- [ ] **Step 1: Write failing tests for stdin parsing**

Add to `tests/test_evaluate_tool_use.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: FAIL with `AttributeError: module 'evaluate_tool_use' has no attribute 'parse_hook_input'`

- [ ] **Step 3: Implement parse_hook_input**

Add to `scripts/evaluate_tool_use.py`:
```python
def parse_hook_input(raw: str) -> dict | None:
    """Parse hook input JSON from stdin. Returns None if invalid."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    # Require the three fields we need
    if not all(k in data for k in ("tool_name", "tool_input", "cwd")):
        return None
    return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_tool_use.py tests/test_evaluate_tool_use.py
git commit -m "feat: add stdin JSON parsing with validation"
```

---

### Task 4: Project Root Determination

**Files:**
- Modify: `scripts/evaluate_tool_use.py`
- Modify: `tests/test_evaluate_tool_use.py`

- [ ] **Step 1: Write failing tests for project root**

Add to `tests/test_evaluate_tool_use.py`:
```python
import subprocess
from unittest.mock import patch


def test_get_project_root_from_git(tmp_path):
    """When git works, return its output."""
    with patch("evaluate_tool_use.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=str(tmp_path) + "\n", stderr=""
        )
        result = etu.get_project_root("/some/subdir")
        assert result == str(tmp_path)


def test_get_project_root_git_fails():
    """When git fails, fall back to cwd."""
    with patch("evaluate_tool_use.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("git not found")
        result = etu.get_project_root("/fallback/dir")
        assert result == "/fallback/dir"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: FAIL with `AttributeError: module 'evaluate_tool_use' has no attribute 'get_project_root'`

- [ ] **Step 3: Implement get_project_root**

Add to `scripts/evaluate_tool_use.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_tool_use.py tests/test_evaluate_tool_use.py
git commit -m "feat: add project root detection via git rev-parse"
```

---

### Task 5: Path Resolution and Sensitive File Detection

**Files:**
- Modify: `scripts/evaluate_tool_use.py`
- Modify: `tests/test_evaluate_tool_use.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_evaluate_tool_use.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement path utilities**

Add to `scripts/evaluate_tool_use.py`:
```python
import os
import re


def resolve_path(file_path: str, cwd: str) -> str:
    """Resolve a file path against cwd to get an absolute path."""
    if os.path.isabs(file_path):
        return os.path.normpath(file_path)
    return os.path.normpath(os.path.join(cwd, file_path))


def is_within_project(resolved_path: str, project_root: str) -> bool:
    """Check if a resolved path is within the project root."""
    # Normalize both paths and ensure project_root ends with separator for prefix check
    rp = os.path.normpath(resolved_path)
    pr = os.path.normpath(project_root)
    return rp == pr or rp.startswith(pr + os.sep)


SENSITIVE_PATTERNS = [
    re.compile(r'(^|/)\.env($|\.)'),        # .env, .env.local, .env.production
    re.compile(r'(^|/)credentials\.json$'),  # credentials.json
    re.compile(r'(^|/)\.ssh/'),              # anything in .ssh/
    re.compile(r'(^|/)id_rsa'),              # SSH private keys
    re.compile(r'(^|/)\.aws/'),              # AWS credentials
    re.compile(r'(^|/)secrets?\.(json|ya?ml|toml)$'),  # secrets files
]


def is_sensitive_file(file_path: str) -> bool:
    """Check if a file path matches known sensitive patterns."""
    return any(p.search(file_path) for p in SENSITIVE_PATTERNS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: 19 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_tool_use.py tests/test_evaluate_tool_use.py
git commit -m "feat: add path resolution and sensitive file detection"
```

---

### Task 6: Signature Generation

**Files:**
- Modify: `scripts/evaluate_tool_use.py`
- Modify: `tests/test_evaluate_tool_use.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_evaluate_tool_use.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement generate_signature**

Add to `scripts/evaluate_tool_use.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: 31 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_tool_use.py tests/test_evaluate_tool_use.py
git commit -m "feat: add cache signature generation for all tool types"
```

---

### Task 7: JSON Cache Read/Write

**Files:**
- Modify: `scripts/evaluate_tool_use.py`
- Modify: `tests/test_evaluate_tool_use.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_evaluate_tool_use.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement JSON cache**

Add to `scripts/evaluate_tool_use.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: 39 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_tool_use.py tests/test_evaluate_tool_use.py
git commit -m "feat: add JSON cache read/write/lookup"
```

---

### Task 8: Project ID for Cache Path

**Files:**
- Modify: `scripts/evaluate_tool_use.py`
- Modify: `tests/test_evaluate_tool_use.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_evaluate_tool_use.py`:
```python
import hashlib


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement project ID and cache path**

Add to `scripts/evaluate_tool_use.py`:
```python
import hashlib


def get_project_id(cwd: str) -> str:
    """Get a project identifier from git remote, falling back to path hash."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=cwd, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            url = result.stdout.strip()
            # Extract repo name from URL (handles both HTTPS and SSH)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: 41 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_tool_use.py tests/test_evaluate_tool_use.py
git commit -m "feat: add project ID detection and cache file path resolution"
```

---

### Task 9: Deterministic Heuristics

**Files:**
- Modify: `scripts/evaluate_tool_use.py`
- Modify: `tests/test_evaluate_tool_use.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_evaluate_tool_use.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement evaluate_heuristic**

Add to `scripts/evaluate_tool_use.py`:
```python
READ_ONLY_TOOLS = {"Read", "Glob", "Grep"}
WEB_TOOLS = {"WebFetch", "WebSearch"}


def evaluate_heuristic(tool_name: str, tool_input: dict, cwd: str, project_root: str) -> tuple[str, str] | None:
    """Apply deterministic heuristics. Returns (decision, reason) or None if ambiguous."""
    if tool_name in READ_ONLY_TOOLS:
        return _evaluate_file_read(tool_name, tool_input, cwd, project_root)
    if tool_name in WEB_TOOLS:
        return ("ask", f"Web access: {tool_name}")
    # Everything else (Bash, Write, Edit, Agent, etc.) → needs Claude evaluation
    return None


def _evaluate_file_read(tool_name: str, tool_input: dict, cwd: str, project_root: str) -> tuple[str, str]:
    """Evaluate a read-only file tool against project boundaries and sensitivity."""
    # Get the path to check
    if tool_name == "Read":
        path = tool_input.get("file_path", "")
    else:  # Glob, Grep
        path = tool_input.get("path", cwd)

    resolved = resolve_path(path, cwd)

    # Check project boundaries first (matches spec ordering)
    if not is_within_project(resolved, project_root):
        return ("ask", f"File access outside project root: {resolved}")

    # Check sensitive files within project
    if is_sensitive_file(resolved):
        return ("ask", f"Sensitive file access: {resolved}")

    return ("allow", "Read-only access within project root")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: 54 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_tool_use.py tests/test_evaluate_tool_use.py
git commit -m "feat: add deterministic heuristics for read-only and web tools"
```

---

### Task 10: Claude Evaluation

**Files:**
- Modify: `scripts/evaluate_tool_use.py`
- Modify: `tests/test_evaluate_tool_use.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_evaluate_tool_use.py`:
```python
def test_parse_claude_response_allow():
    output = "DECISION: ALLOW - Non-destructive test command"
    decision, reason = etu.parse_claude_response(output)
    assert decision == "allow"
    assert reason == "Non-destructive test command"


def test_parse_claude_response_ask():
    output = "DECISION: ASK - Potentially destructive operation"
    decision, reason = etu.parse_claude_response(output)
    assert decision == "ask"
    assert reason == "Potentially destructive operation"


def test_parse_claude_response_with_extra_lines():
    output = "Some preamble\nDECISION: ALLOW - Safe command\nMore text"
    decision, reason = etu.parse_claude_response(output)
    assert decision == "allow"
    assert reason == "Safe command"


def test_parse_claude_response_unparseable():
    output = "I think this is probably fine"
    result = etu.parse_claude_response(output)
    assert result is None


def test_parse_claude_response_empty():
    result = etu.parse_claude_response("")
    assert result is None


def test_evaluate_with_claude_allow():
    with patch("evaluate_tool_use.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="DECISION: ALLOW - Safe test command\n", stderr=""
        )
        result = etu.evaluate_with_claude("Bash", {"command": "npm test"}, "/project")
        assert result == ("allow", "Safe test command")


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement Claude evaluation**

Add to `scripts/evaluate_tool_use.py`:
```python
EVALUATION_PROMPT_TEMPLATE = """You are a security evaluator for Claude Code tool use. Evaluate whether this tool call is safe to auto-approve or should be escalated to the user.

Project root: {project_root}

Tool: {tool_name}
Input: {tool_input_json}

Policy:
- ALLOW non-destructive actions within the project root
- ALLOW file writes/edits within the project (recoverable via git)
- ALLOW running build/test/lint commands
- ASK for anything that deletes files not tracked by git
- ASK for anything that erases git history (force push, reset --hard)
- ASK for access to files outside the project root
- ASK for access to sensitive files (.env, credentials, secrets, keys)
- ASK for web access (fetching URLs, web searches)
- ASK for anything you're uncertain about

Respond with EXACTLY one line in this format:
DECISION: <ALLOW|ASK> - <brief reason>"""


def parse_claude_response(output: str) -> tuple[str, str] | None:
    """Parse Claude's evaluation response. Returns (decision, reason) or None."""
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("DECISION:"):
            rest = line[len("DECISION:"):].strip()
            if rest.startswith("ALLOW"):
                reason = rest[len("ALLOW"):].strip().lstrip("- ").strip()
                return ("allow", reason or "Allowed by Claude evaluation")
            elif rest.startswith("ASK"):
                reason = rest[len("ASK"):].strip().lstrip("- ").strip()
                return ("ask", reason or "Flagged by Claude evaluation")
    return None


def evaluate_with_claude(tool_name: str, tool_input: dict, project_root: str) -> tuple[str, str]:
    """Spawn claude -p to evaluate a tool call. Returns (decision, reason)."""
    prompt = EVALUATION_PROMPT_TEMPLATE.format(
        project_root=project_root,
        tool_name=tool_name,
        tool_input_json=json.dumps(tool_input, indent=2)
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--max-turns", "1"],
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: 62 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_tool_use.py tests/test_evaluate_tool_use.py
git commit -m "feat: add Claude CLI evaluation with prompt and response parsing"
```

---

### Task 11: Wire Up main()

**Files:**
- Modify: `scripts/evaluate_tool_use.py`
- Modify: `tests/test_evaluate_tool_use.py`

- [ ] **Step 1: Write failing integration tests**

Add to `tests/test_evaluate_tool_use.py`:
```python
import io


def test_main_read_in_project(monkeypatch):
    """Full flow: Read within project → heuristic ALLOW, no Claude call."""
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
    """Full flow: Bash with cache hit → return cached decision."""
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
    """Full flow: Bash with no cache → Claude evaluation → cache write."""
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
    """Full flow: invalid stdin → ASK."""
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)
    etu.main()
    result = json.loads(output.getvalue())
    assert result["hookSpecificOutput"]["permissionDecision"] == "ask"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: FAIL (main still outputs placeholder)

- [ ] **Step 3: Implement main()**

Replace the `main()` function in `scripts/evaluate_tool_use.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_evaluate_tool_use.py -v`
Expected: 66 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_tool_use.py tests/test_evaluate_tool_use.py
git commit -m "feat: wire up main() with full three-layer evaluation pipeline"
```

---

### Task 12: End-to-End Smoke Test

**Files:**
- Modify: `tests/test_evaluate_tool_use.py`

- [ ] **Step 1: Write an end-to-end test that exercises the real script via subprocess**

Add to `tests/test_evaluate_tool_use.py`:
```python
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
```

- [ ] **Step 2: Run all tests**

Run: `python3 -m pytest tests/ -v`
Expected: 68 passed

- [ ] **Step 3: Commit**

```bash
git add tests/test_evaluate_tool_use.py
git commit -m "test: add end-to-end subprocess smoke tests"
```

---

### Task 13: Manual Integration Test

**Files:** None (manual testing)

- [ ] **Step 1: Test the plugin locally with Claude Code**

Run: `claude --plugin-dir .`

- [ ] **Step 2: Trigger a few tool calls and observe behavior**

Try these in the Claude session:
- Ask Claude to read a file in the project → should auto-ALLOW
- Ask Claude to read `.env` → should ASK
- Ask Claude to run `ls` → should go to Claude evaluation (first time), then cache
- Ask Claude to run `ls` again → should hit cache

- [ ] **Step 3: Inspect the cache file**

Run: `cat ~/.claude/sane-tool-use-plugin/.cache/*.json`

Verify entries look correct.

- [ ] **Step 4: Commit any fixes discovered during manual testing**
