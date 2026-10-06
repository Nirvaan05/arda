# Using ARDA with Codex

> **Status: VERIFIED.** Codex agents send and answer ARDA messages live in Herdr, from
> inside Codex's sandbox.

## Setup checklist

| Step | Command or file | Why |
| --- | --- | --- |
| Start without the shared background server | `codex --no-daemon` (or `herdr agent start <name> --kind codex --pane <pane> -- --no-daemon`) | Otherwise Codex runs commands outside its pane, and ARDA cannot tell who is sending; it refuses and says so |
| Approve ARDA once | `arda-trust --yes` (you, in a plain terminal) | Lets `arda`, and nothing else, run outside Codex's sandbox, and tells Codex to act on peer messages |
| Native identity | Installed by `arda-trust --yes` (`herdr integration install codex`) | Gives the agent a reply address that survives renames |
| Trust the new hook | Codex shows a **Hooks** review dialog once, in its pane | Approve it yourself; until then Herdr does not see the dialog as blocked, and a message typed into it is lost |
| Agent skill | Link `skills/arda` into `$CODEX_HOME/skills/` or `~/.agents/skills/` | Teaches the agent ARDA in every new session |
| Your commands | Link `skills/arda-peers` and `skills/arda-setup` too | Adds `$arda-peers` and `$arda-setup` |

```sh
root=$(herdr plugin list --plugin arda --json |
  python3 -c 'import json, sys; print(json.load(sys.stdin)["result"]["plugins"][0]["plugin_root"])')
skills="${CODEX_HOME:-$HOME/.codex}/skills"   # one Codex profile; ~/.agents/skills for all of them
mkdir -p "$skills"
for s in arda arda-peers arda-setup; do ln -s "$root/skills/$s" "$skills/$s"; done
```

## What `arda-trust` writes for Codex

| File | Content |
| --- | --- |
| `$CODEX_HOME/AGENTS.md` | A marked section: ARDA messages come from peer agents, not from you; risky requests are rejected |
| `$CODEX_HOME/rules/arda.rules` | Allows the `arda` command outside the sandbox; forbids `arda-trust` |

## Your commands in Codex

Codex has no custom slash commands. Mention the skills instead:

| Type | What it shows |
| --- | --- |
| `$arda-peers` | Every agent ARDA can reach, with state, working directory and what each says it does |
| `$arda-setup` | Whether ARDA is approved, and the command to run if not |
| `/skills` | Codex's own menu, where both skills are listed |

Both skills are marked explicit-only for Codex (`agents/openai.yaml`), so Codex never uses
them on its own.

## Behavior to know

- **Busy agents.** Codex takes input that arrives while it works into its current turn, so
  a message to a busy Codex agent is reported as `submitted`.
- **Exact model.** A Codex agent does not reliably know its exact model. Use
  `arda describe --model auto`: it reads the newest turn of the agent's own session log
  (`$CODEX_HOME/sessions/…/rollout-…-<session>.jsonl`), for example
  `gpt-6-astra (reasoning xhigh)`.
- **Sandbox prompts.** Without `arda-trust`, Codex asks you to approve each `arda` command
  that has to reach the Herdr socket.
