# sane-tool-use

A Claude Code plugin that brings sanity to tool use permissions. Instead of choosing between babysitting every action or granting `node:*`, this plugin auto-allows safe operations and only prompts you when something is genuinely risky.

## How it works

Every tool call passes through three evaluation layers:

1. **Cache** — Has this exact tool call been evaluated before? Use the cached decision.
2. **Heuristic** — Is this clearly safe or clearly sensitive? Decide deterministically.
3. **Claude evaluation** — For ambiguous cases, spawn `claude -p` to evaluate against a security policy.

All failures default to ASK (prompting you). The plugin never silently allows something it can't evaluate.

### What gets auto-allowed

- `Read`, `Glob`, `Grep` on files within the project root (excluding sensitive files)

### What always prompts you

- Access to files outside the project root
- Sensitive files (`.env`, `credentials.json`, `.ssh/`, `.aws/`, secrets files)
- Web access (`WebFetch`, `WebSearch`)

### What Claude evaluates

Everything else — `Bash` commands, `Write`, `Edit`, `Agent`, and any tool not covered by heuristics. Claude uses a three-tier security policy:

- **ALLOW** — safe, non-destructive, or recoverable (build/test/lint, file writes within project, git-tracked file deletion)
- **ASK** — ambiguous, needs your judgment (untracked file deletion, opaque script execution, network-facing commands)
- **DENY** — clearly malicious or unrecoverable, hard-blocked (rm -rf /, git reset --hard, env exfiltration, curl | bash)

Decisions from Claude evaluation are cached per-project so the same command won't trigger re-evaluation.

## Installation

```bash
claude --plugin-dir /path/to/sane-tool-use-plugin
```

Or clone it somewhere and point to it:

```bash
git clone <repo-url> ~/.claude/plugins/sane-tool-use-plugin
claude --plugin-dir ~/.claude/plugins/sane-tool-use-plugin
```

### Requirements

- Python 3 (ships with macOS, no additional dependencies)
- Claude Code CLI (`claude` on PATH — used for evaluating ambiguous tool calls)

## Cache

Decisions are cached per-project at:

```
~/.claude/sane-tool-use-plugin/.cache/<project-id>.json
```

The project ID is derived from the git remote URL (repo name), or a hash of the working directory path for non-git projects.

Cache entries never expire. To reset decisions for a project, delete its cache file:

```bash
rm ~/.claude/sane-tool-use-plugin/.cache/<project-name>.json
```

To reset all cached decisions:

```bash
rm -rf ~/.claude/sane-tool-use-plugin/.cache/
```

## Project structure

```
sane-tool-use-plugin/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
├── hooks/
│   └── hooks.json               # PreToolUse hook configuration
├── scripts/
│   ├── evaluate_tool_use.py     # All evaluation logic (single file)
│   └── test_prompt.py           # Prompt test runner (43 scenarios)
└── tests/
    └── test_evaluate_tool_use.py  # 73 unit/integration/E2E tests
```

## Running tests

```bash
python3 -m pytest tests/ -v
```

## How the evaluation policy works

When Claude evaluates an ambiguous tool call, it applies this policy:

| Action | Decision |
|--------|----------|
| Read-only commands (ls, cat, grep, git status/log/diff) | ALLOW |
| Build/test/lint commands (npm test, pytest, eslint, make) | ALLOW |
| File writes/edits within project (recoverable via git) | ALLOW |
| Deleting git-tracked files (recoverable via git checkout) | ALLOW |
| Inline scripts with visible content (echo "..." \| node) | ALLOW |
| Git commits, branch creation, checkout | ALLOW |
| Package install for project (npm install, pip install -r) | ALLOW |
| Deleting untracked/git-ignored files | ASK |
| Opaque script execution (bash deploy.sh, node script.js) | ASK |
| Network-facing commands (starting servers, opening ports) | ASK |
| Package publish or global install | ASK |
| Anything uncertain | ASK |
| Destructive commands outside git (rm -rf /, dd, wipefs) | DENY |
| Rewriting git history (reset --hard, push --force) | DENY |
| Secret exfiltration (env \| curl, cat ~/.ssh/id_rsa \| nc) | DENY |
| Downloading and executing remote code (curl \| bash) | DENY |

## Testing the prompt

The prompt test runner validates evaluation behavior across Claude models:

```bash
# Run all 43 scenarios with default model (sonnet)
python3 scripts/test_prompt.py

# Test with cheapest/fastest model
python3 scripts/test_prompt.py --model haiku

# Test with opus at low effort
python3 scripts/test_prompt.py --model opus --effort low

# Run a single scenario for debugging
python3 scripts/test_prompt.py --scenario "rm -rf root"
```

The test runner reports pass/fail per scenario with latency, and exits non-zero if any scenario fails.

## Limitations

- Each ambiguous tool call spawns a `claude -p` subprocess, which adds a few seconds of latency on the first occurrence (cached after that)
- The 30-second hook timeout means very slow Claude evaluations fall through to prompting you (safe default)
- No custom policy rules — the evaluation prompt is hardcoded
- No cache expiry — stale decisions persist until manually cleared
- Concurrent sessions writing to the same cache file use last-write-wins (no locking)
