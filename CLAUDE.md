# CLAUDE.md

## Project overview

This is a Claude Code plugin called "sane-tool-use". It intercepts all tool calls via a PreToolUse hook and evaluates them through three layers: cache, deterministic heuristics, and Claude CLI evaluation. The goal is to auto-allow safe operations and only prompt the user for genuinely risky ones.

## Architecture

Single Python script (`scripts/evaluate_tool_use.py`) handles everything. No external dependencies — Python 3 stdlib only.

**Decision flow:** stdin JSON → parse → cache lookup → heuristic check → Claude evaluation → stdout JSON

**Three evaluation layers:**
1. Cache: exact match on `(tool_name, tool_input_signature)` in `~/.claude/sane-tool-use-plugin/.cache/<project>.json`
2. Heuristics: Read/Glob/Grep in project → ALLOW; sensitive files → ASK; web tools → ASK
3. Claude: spawns `claude -p` with a security policy prompt, parses `DECISION: ALLOW|ASK - reason`

**Key invariant:** Every failure mode defaults to ASK. The script must never crash or silently allow.

## File structure

- `.claude-plugin/plugin.json` — plugin manifest (name, version, hooks path)
- `hooks/hooks.json` — registers the PreToolUse hook pointing to the Python script
- `scripts/evaluate_tool_use.py` — all evaluation logic in one file (~300 lines)
- `tests/test_evaluate_tool_use.py` — unit, integration, and E2E tests
- `docs/superpowers/specs/` — design spec
- `docs/superpowers/plans/` — implementation plan

## Development

```bash
# Run tests
python3 -m pytest tests/ -v

# Test the plugin locally
claude --plugin-dir .

# Manual smoke test (pipe hook input to the script)
echo '{"session_id":"s1","cwd":"/path/to/project","tool_name":"Read","tool_input":{"file_path":"/path/to/project/file.py"},"hook_event_name":"PreToolUse","tool_use_id":"t1"}' | python3 scripts/evaluate_tool_use.py
```

## Important design decisions

- **Python, not Node** — Python 3 ships with macOS, avoiding an extra dependency.
- **JSON cache, not YAML** — YAML requires a custom parser (PyYAML not in stdlib) and breaks on values containing colons/quotes. JSON handles arbitrary strings natively.
- **Write/Edit go to Claude evaluation, not heuristics** — Even though writes to git-tracked files are recoverable, the judgment of whether a write is "safe" requires context that heuristics can't provide.
- **All Bash commands go to Claude evaluation** — We cannot deterministically distinguish `npm test` from `rm -rf /`. No allowlist of "safe" commands.
- **Heuristic results are NOT cached** — They're deterministic and fast, so caching would add complexity for no benefit.
- **25s timeout on `claude -p` (vs 30s hook timeout)** — Leaves 5s headroom so the script can return ASK before the hook timeout kills it.
- **Project root via `git rev-parse --show-toplevel`** — More reliable than using `cwd` which could be a subdirectory.

## Sensitive file patterns

Defined in `SENSITIVE_PATTERNS` in `evaluate_tool_use.py`. Currently matches:
- `.env`, `.env.*`
- `credentials.json`
- `.ssh/` directory
- `id_rsa` files
- `.aws/` directory
- `secret.json`, `secrets.yaml`, `secrets.toml` (and variants)

To add new patterns, add a compiled regex to the `SENSITIVE_PATTERNS` list and add a corresponding test.

## Cache signature format

Each tool type has a specific signature format for cache keying:

| Tool | Signature format |
|------|-----------------|
| Bash | raw command string |
| Read/Write/Edit | `ToolName:/absolute/path` |
| Glob/Grep | `ToolName:pattern@/absolute/path` |
| WebFetch | `WebFetch:url` |
| WebSearch | `WebSearch:query` |
| Agent | `Agent:description` |
| Unknown | `ToolName:json_of_input` |

## Hook I/O format

**Input (stdin):** JSON with `tool_name`, `tool_input`, `cwd` (required), plus `session_id`, `hook_event_name`, `tool_use_id`.

**Output (stdout):** `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"|"ask", "permissionDecisionReason": "..."}}`
