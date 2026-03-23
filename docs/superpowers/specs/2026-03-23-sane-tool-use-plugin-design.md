# Sane Tool Use Plugin — Design Spec

## Problem

Claude Code's default permission model forces a binary choice: either babysit every tool call or grant overly broad permissions like `node:*` or `python:*`. There's no middle ground that allows non-destructive, project-scoped work to proceed automatically while still gating sensitive or destructive actions.

## Solution

A Claude Code plugin that intercepts all tool calls via a `PreToolUse` hook and evaluates them through three layers:

1. **Cache** — check if this exact tool call has been evaluated before
2. **Heuristic** — deterministic rules for clearly safe or clearly sensitive operations
3. **Claude evaluation** — spawn `claude -p` to evaluate ambiguous cases

Every layer either returns a decision (ALLOW or ASK) or passes through to the next. All failures default to ASK.

## Plugin Structure

```
sane-tool-use-plugin/
├── .claude-plugin/
│   └── plugin.json
├── hooks/
│   └── hooks.json
└── scripts/
    └── evaluate_tool_use.py
```

Three files total. Single entry point.

### Plugin Manifest

`.claude-plugin/plugin.json`:

```json
{
  "name": "sane-tool-use",
  "description": "Intelligent tool use gating — auto-allows safe actions, escalates risky ones",
  "version": "1.0.0",
  "hooks": "./hooks/hooks.json"
}
```

## Hook Configuration

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

- Matches all tools — the script handles routing internally
- 30s timeout — falls through to ASK if exceeded
- Python 3 used because it ships with macOS (no extra dependencies)

## Hook Input Schema

Claude Code sends this JSON to stdin for every PreToolUse hook:

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/current/working/directory",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": { "command": "npm test", "description": "Run tests" },
  "tool_use_id": "toolu_01ABC123"
}
```

Key `tool_input` field names by tool:

| Tool | Relevant fields in `tool_input` |
|------|------|
| `Bash` | `command`, `description` |
| `Read` | `file_path` |
| `Write` | `file_path`, `content` |
| `Edit` | `file_path`, `old_string`, `new_string` |
| `Glob` | `pattern`, `path` (optional, defaults to cwd) |
| `Grep` | `pattern`, `path` (optional, defaults to cwd) |
| `WebFetch` | `url` |
| `WebSearch` | `query` |
| `Agent` | `prompt`, `description` |

## Script Logic Flow

```
1. Parse stdin → tool_name, tool_input, cwd
2. Determine project root via `git rev-parse --show-toplevel` (fallback to cwd)
3. Check cache → if hit, return cached decision
4. Deterministic heuristics:
   a. Read-only file tools (Read, Glob, Grep):
      - Path outside project root → ASK
      - Sensitive file pattern (.env*) → ASK
      - Otherwise → ALLOW
   b. Web access tools (WebFetch, WebSearch) → ASK
   c. Everything else (Bash, Write, Edit, Agent, etc.) → step 5
5. Claude evaluation:
   - Spawn: claude -p "<policy prompt>" --max-turns 1
   - Parse response text for ALLOW or ASK
   - Cache the decision
   - Return it
6. On any error/timeout → ASK (safe default)
```

Note: `Write` and `Edit` are NOT in the auto-ALLOW heuristic bucket despite being file-based. They modify state, so they always go to Claude evaluation (which will typically ALLOW them for in-project git-tracked files, but that judgment requires context). All `Bash` commands also go to Claude evaluation — even common ones like `npm test` — because we cannot deterministically distinguish safe from destructive shell commands.

### Project Root Determination

The script runs `git rev-parse --show-toplevel` to find the true project root. This is more reliable than using `cwd` directly, which could be a subdirectory. If the git command fails (non-git project), `cwd` is used as the fallback.

### Path Resolution

For file-based tools (`Read`, `Glob`, `Grep`, `Edit`, `Write`), the script resolves paths against `cwd` from the hook input to get an absolute path, then checks whether it falls within the project root. This handles relative path attacks like `../../../etc/passwd`.

## Cache Design

### Location

`~/.claude/sane-tool-use-plugin/.cache/<project-id>.yml`

### Project Identification

1. Git repo name from `git remote get-url origin` (e.g., `sane-tool-use-plugin`)
2. Fallback: SHA-256 hash of the absolute working directory path

### Entry Structure

```yaml
entries:
  - tool_name: Bash
    tool_input_signature: "npm test"
    decision: allow
    reason: "Non-destructive test command within project"
  - tool_name: Write
    tool_input_signature: "Write:/Users/joe/projects/myapp/src/components/Button.tsx"
    decision: allow
    reason: "File write within project root, recoverable via git"
```

### Signature Generation

Each tool type produces a cache key from meaningful parts of `tool_input`:

| Tool | Signature |
|------|-----------|
| `Bash` | The command string |
| `Read`, `Write`, `Edit` | `ToolName:<resolved_absolute_path>` |
| `Glob`, `Grep` | `ToolName:<pattern>@<resolved_path>` |
| `WebFetch` | `WebFetch:<url>` |
| `WebSearch` | `WebSearch:<query>` |
| `Agent` | `Agent:<description>` |

### Matching

Exact string match on `tool_name` + `tool_input_signature`. No fuzzy matching — different command or path means re-evaluation.

### Expiry

No expiry. User can manually delete cache files to reset decisions.

### Format

Simple YAML with a custom parser/writer (no PyYAML dependency since it's not in Python stdlib). The parser only needs to support a flat list of mappings with string scalar values — no nested structures, anchors, or multi-line strings. Concurrent access from multiple sessions is acceptable for v1 (last-write-wins); no locking needed.

## Claude Evaluation Prompt

Spawned via:

```
claude -p "<prompt>" --max-turns 1
```

The output is plain text (no `--output-format json`) so we can parse the `DECISION:` line directly without unwrapping a JSON envelope.

Prompt template:

```
You are a security evaluator for Claude Code tool use. Evaluate whether this
tool call is safe to auto-approve or should be escalated to the user.

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
DECISION: <ALLOW|ASK> - <brief reason>
```

The script parses the first line for `ALLOW` or `ASK`, extracts the reason, caches both, and returns the hook decision JSON.

If parsing fails or Claude returns something unexpected → default to ASK.

## Error Handling

Every failure mode defaults to ASK:

| Failure | Behavior |
|---------|----------|
| Can't parse stdin JSON | ASK — "Failed to parse tool input" |
| Can't resolve file path | ASK — "Could not resolve path" |
| Cache file corrupt/unreadable | Ignore cache, proceed to evaluation |
| `claude -p` not found on PATH | ASK — "Claude CLI not available" |
| `claude -p` times out | ASK — "Evaluation timed out" |
| `claude -p` returns unparseable output | ASK — "Could not parse evaluation" |
| Cache directory not writable | Evaluate but skip caching |
| Git command fails (for project ID) | Fall back to path hash |

No exceptions bubble up. The script wraps everything in a top-level try/except that returns ASK.

## Decision Control Response Format

The script outputs JSON to stdout:

### ALLOW

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "Non-destructive read within project root"
  }
}
```

### ASK

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "Accessing sensitive file: .env"
  }
}
```

## Non-Goals for v1

- No web UI for managing cached decisions
- No fuzzy/pattern-based cache matching
- No support for custom policy rules beyond what's in the evaluation prompt
- No caching expiry or automatic invalidation
