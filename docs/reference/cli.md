# CLI reference

> **Every command, option and exit status** of `arda` and `arda-trust`. Agents run `arda`
> from their own Herdr pane; only the user runs `arda-trust`.

## Commands

| Command | Purpose |
| --- | --- |
| `arda peers` | List the agents in every reachable Herdr session and saved machine, with what each says it does |
| `arda whoami` | Show your own address, pane, session and machine |
| `arda describe [--role R] [--tools T] [--model M\|auto] [--clear]` | Tell peers what you do; without options, show it |
| `arda send <to> [--re ID] -- '<text>'` | Send a note; with `--re`, a note about a task (a question, an answer, a change of plan) |
| `arda task <to> -- '<text>'` | Hand over a task; expect `ack`, then `result` or `reject` |
| `arda ack <to> <id> [-- '<text>']` | Accept a task you received |
| `arda result <to> <id> -- '<text>'` | Return the outcome of a task |
| `arda reject <to> <id> -- '<text>'` | Decline a task, or report that it could not be finished |
| `arda introduce [<to> ...]` | Tell agents their address, their peers and how to reach them; busy agents are skipped |
| `arda setup` | Show whether ARDA is approved and the command to run (read-only) |
| `arda status` | Show the plugin and protocol version |
| `arda-trust [--yes] [--revoke] [--status] [--no-integrations]` | The user's one-time approval; see [trust and consent](../guides/trust-and-consent.md) |

`<to>` is an address such as `@reviewer`, `@reviewer@desktop` or a reply address copied
from a message (`@implementer.s…`). See [addresses](../protocol.md#addresses).

## Message text

| Rule | Example |
| --- | --- |
| Put `--` before the text and single quotes around it | `arda task @reviewer -- 'Review src/http.py.'` |
| Read the text from stdin | `printf '%s' "$text" \| arda task @reviewer -` |
| Read the text from a file | `arda task @reviewer --file task.md` |

- `--` stops the text from being read as an option; single quotes stop the shell from
  expanding it.
- A body is at most 32,000 bytes of UTF-8. Put larger content in a file and refer to it.
- `--file` reads only visible files from the working directory or `/tmp`.
- Control and invisible characters are removed from message text before it is typed.

## Options

| Option | Commands | Effect |
| --- | --- | --- |
| `--json` | all | Print machine-readable JSON |
| `--session NAME` | all | Use a Herdr session from outside Herdr (for `peers`, `status`, `setup`); messages are sent only from an agent's own pane |
| `--force` | `send`, `task`, `ack`, `result`, `reject`, `introduce` | Type even when Herdr cannot classify the receiver's state |
| `--file FILE` | `send`, `task`, `result`, `reject` | Read the text from a file |
| `--re ID` | `send` | The task this note is about |
| `--role`, `--tools` | `describe` | One line each, at most 80 characters; an empty value clears the field |
| `--model M` | `describe` | The model, at most 80 characters; `auto` reads it from your own Claude Code or Codex session log (needs Herdr's integration) |
| `--clear` | `describe` | Remove your description (fields given with it are set instead) |

## Exit status

| Code | Meaning |
| --- | --- |
| 0 | Delivered or submitted, or the command succeeded |
| 1 | Not delivered, or a Herdr error |
| 2 | Usage error (bad address, missing text, not inside an agent's pane, …) |
| 3 | Uncertain: the text may have arrived; do not resend blindly |

The delivery statuses (`delivered`, `submitted`, `uncertain`, `not_delivered`) are defined
in the [protocol](../protocol.md#delivery).

## JSON output

| Command | Top-level fields |
| --- | --- |
| `send`, `task`, `ack`, `result`, `reject` | `status`, `type`, `id`, `re`, `from`, `to`, `place`, `pane_id`, `detail`, `resolution` |
| `introduce` | `status`, `results` (one entry per agent, as above) |
| `peers` | `places`, `peers`, `resolution` |
| `describe` | `status`, `address`, and `role`, `tools`, `model` when set |

Each peer in `peers` has `address`, `name`, `agent` (harness), `state`, `place`,
`machine`, `session`, `pane_id`, `cwd`, `observed_at`, `described` and `you`. The
`resolution` record says which places were asked, which answered and when.

## Herdr plugin actions

| Action | Same as |
| --- | --- |
| **ARDA status** | `arda status` |
| **ARDA: show setup** | `arda setup` |
| **ARDA: introduce the agents to each other** | `arda introduce` |

Run from Herdr (`herdr plugin action invoke <id> --plugin arda`), they also show their
result as a Herdr notification.

## Skills

| Skill | For | Invoke |
| --- | --- | --- |
| [`arda`](../../skills/arda/SKILL.md) | Agents | Loaded when an ARDA message arrives or the user asks to involve another agent |
| [`arda-peers`](../../skills/arda-peers/SKILL.md) | You | `/arda-peers` in Claude Code, `$arda-peers` in Codex |
| [`arda-setup`](../../skills/arda-setup/SKILL.md) | You | `/arda-setup` in Claude Code, `$arda-setup` in Codex |
