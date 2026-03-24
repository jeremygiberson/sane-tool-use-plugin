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

Everything else — `Bash` commands, `Write`, `Edit`, `Agent`, and any tool not covered by heuristics. Claude uses a security policy that allows non-destructive, in-project actions and flags anything destructive, out-of-scope, or uncertain.

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
│   └── evaluate_tool_use.py     # All evaluation logic (single file)
└── tests/
    └── test_evaluate_tool_use.py  # 67 unit/integration/E2E tests
```

## Running tests

```bash
python3 -m pytest tests/ -v
```

## How the evaluation policy works

When Claude evaluates an ambiguous tool call, it applies this policy:

| Action | Decision |
|--------|----------|
| Non-destructive actions within project root | ALLOW |
| File writes/edits within project (recoverable via git) | ALLOW |
| Build/test/lint commands | ALLOW |
| Deleting files not tracked by git | ASK |
| Erasing git history (force push, reset --hard) | ASK |
| Access to files outside project root | ASK |
| Sensitive files (.env, credentials, secrets, keys) | ASK |
| Web access (fetching URLs, web searches) | ASK |
| Anything uncertain | ASK |

## Limitations

- Each ambiguous tool call spawns a `claude -p` subprocess, which adds a few seconds of latency on the first occurrence (cached after that)
- The 30-second hook timeout means very slow Claude evaluations fall through to prompting you (safe default)
- No custom policy rules — the evaluation prompt is hardcoded
- No cache expiry — stale decisions persist until manually cleared
- Concurrent sessions writing to the same cache file use last-write-wins (no locking)
