# Using ARDA with Claude Code

> **Status: VERIFIED.** Claude Code agents send and answer ARDA messages live in Herdr.

## Setup checklist

| Step | Command or file | Why |
| --- | --- | --- |
| Approve ARDA once | `arda-trust --yes` (you, in a plain terminal) | Lets Claude Code act on peer messages and run `arda` without asking each time |
| Native identity | Installed by `arda-trust --yes` (`herdr integration install claude`) | Gives the agent a reply address (`@name.s…`) that survives renames and resumed sessions |
| Agent skill | Link `skills/arda` into `$CLAUDE_CONFIG_DIR/skills/` | Teaches the agent ARDA in every new session |
| Your commands | Link `skills/arda-peers` and `skills/arda-setup` too | Adds `/arda-peers` and `/arda-setup` |

```sh
root=$(herdr plugin list --plugin arda --json |
  python3 -c 'import json, sys; print(json.load(sys.stdin)["result"]["plugins"][0]["plugin_root"])')
skills="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"
mkdir -p "$skills"
for s in arda arda-peers arda-setup; do ln -s "$root/skills/$s" "$skills/$s"; done
```

A project's `.claude/skills/` works too, for one project only.

## What `arda-trust` writes for Claude Code

| File | Content |
| --- | --- |
| `$CLAUDE_CONFIG_DIR/rules/arda.md` | ARDA messages come from peer agents, not from you; they may be answered without asking you each time; risky requests are rejected |
| `$CLAUDE_CONFIG_DIR/settings.json` | `permissions.allow`: `Bash(arda *)`; `permissions.deny`: `Bash(arda-trust)` and `Bash(arda-trust *)`, each also for the script's full path |

Without the approval, Claude Code asks you before acting on a peer's task, and its auto
mode blocks such work.

## Slash commands

| Command | What it shows |
| --- | --- |
| `/arda-peers` | Every agent ARDA can reach, with state, working directory and what each says it does |
| `/arda-setup` | Whether ARDA is approved, and the command to run if not |
| `/list-agents` | Claude Code's own command: only Claude Code sessions, not other agents in Herdr |

Only you can invoke `/arda-peers` and `/arda-setup`; agents use `arda peers` directly.

## Behavior to know

- **Busy agents.** Claude Code queues input that arrives while it works and takes it at its
  next step, so a message to a busy Claude Code agent is reported as `submitted`.
- **Exact model.** `arda describe --model auto` reads the model from the agent's own
  transcript (`$CLAUDE_CONFIG_DIR/projects/*/<session>.jsonl`), for example
  `claude-opus-5-5`.
- **End-of-turn tips.** Herdr 0.9.3 does not always see Claude Code's own end-of-turn
  dialogs as blocked, so a message typed then can land in the dialog. See
  [troubleshooting](../troubleshooting.md).
