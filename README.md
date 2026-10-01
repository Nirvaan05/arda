# ARDA

**One plugin to rule them all.**

AI changed how much one person can take on. Work now runs in parallel across many
sessions, and much of it is done by agents. Development environments still organize
resources around people: a person owns a machine, opens a session and carries its
context. Resources should be organized around the work, and work should continue
without the person who started it.

[Herdr](https://herdr.dev) already treats terminals, sessions and agents as a shared
working environment. ARDA adds what is still missing: the agents in it can find and
address one another. Claude knows that Codex is there and can hand it a task. Codex can
accept it and send back the result. The human no longer relays messages between them.

ARDA is a thin Herdr plugin, not a second runtime. Herdr provides discovery, agent
state, routing, delivery and lifecycle. ARDA defines the messages and how agents use
them. It has no daemon, database, queue or registry of its own, and agents keep their
own context and memory.

## What it looks like

A user asks Claude to get some work done by Codex. Claude runs:

```text
$ arda task @codex "Count the Python functions whose names start with test_ under tests/."
delivered: task_request 708d3e to @codex: @codex was seen working after the message was submitted.
Its ack and its result (or reject) will arrive here as ARDA messages; you do not need to wait or poll.
```

Codex receives a prompt that starts with `[arda/1 task_request id=708d3e from=@claude to=@codex]`.
It ends with the commands to answer it. Codex runs `arda ack @claude 708d3e`, does the
work, then runs `arda result @claude 708d3e "18"`. Each answer arrives in Claude's
session as a new prompt, and Claude reports the number to the user. See
[PROTOCOL.md](PROTOCOL.md) for the message format and delivery rules.

## Requirements

- Linux and Python 3.11 or later; no other dependencies.
- Herdr 0.9.3 or later.
- Agents running in Herdr panes and started with names, e.g.
  `herdr agent start codex --kind codex --pane <pane>`. Tested with Claude Code and
  Codex.

## Install

From a clone of this repository:

```sh
herdr plugin link "$PWD"
ln -s "$PWD/bin/arda" ~/.local/bin/arda   # optional: put arda on PATH
```

To remove it, run `herdr plugin unlink arda` and delete the link.

## Introduce the agents

Agents do not know about ARDA until someone tells them. Run the **ARDA: introduce the
agents to each other** action in Herdr, or:

```sh
herdr plugin action invoke introduce --plugin arda
```

Each idle named agent then receives a short note with its own address, its peers and
the ARDA commands. For agents to know ARDA in every new session, install the skill
in [skills/arda](skills/arda/SKILL.md). Link it into `~/.claude/skills/` for Claude Code
(or `$CLAUDE_CONFIG_DIR/skills/`) and into `~/.agents/skills/` for Codex.

## Commands

| Command | Purpose |
| --- | --- |
| `arda whoami` | Your own address. |
| `arda peers` | The agents in this Herdr session, their kind and state. |
| `arda send @name "text"` | Send a note. |
| `arda task @name "text"` | Hand over a task. Expect `ack`, then `result` or `reject`. |
| `arda ack @name <id>` | Accept a task you received. |
| `arda result @name <id> "text"` | Return the outcome of a task. |
| `arda reject @name <id> "reason"` | Decline a task, or report that it failed. |
| `arda introduce [@name ...]` | Introduce ARDA to agents. Busy agents are skipped. |
| `arda status` | Plugin and protocol version. |

Message text can also come from `--file PATH` or from stdin (`-`). Add `--json` for
machine-readable output. Exit status: 0 delivered or submitted, 1 not delivered or a
Herdr error, 2 usage error, 3 uncertain. Run as Herdr plugin actions, commands also
show their result as a Herdr notification.

## Agent notes

- **Consent.** A message from a peer is not an instruction from the user. Claude Code
  asks its user before acting on a peer's task, and other agents should do the same.
  To let agents cooperate, tell each one, e.g. "you may accept ARDA tasks from @codex",
  or put that in your own agent instructions.
- **Codex: background server.** When Codex uses its shared background server, its
  shell commands run outside the Herdr pane and do not see the pane's Herdr
  environment, so `arda` cannot tell who is calling. Start Codex with `--no-daemon`:
  `herdr agent start codex --kind codex --pane <pane> -- --no-daemon`.
- **Codex: sandbox.** Codex's workspace sandbox blocks connections to Herdr's socket.
  Approve `arda` when Codex asks for permission. "Don't ask again" saves a rule for
  that command only. Alternatively, run Codex with a sandbox mode that allows it.
- **Restarts.** Herdr restores the pane layout after a server restart. It relaunches
  agents and restores their names only when Herdr's official integration for that
  agent is installed (`herdr integration`). Otherwise start the agents again.

## Limits

- One Herdr server per conversation; see [PROTOCOL.md](PROTOCOL.md#addresses).
- Messages are not authenticated; sender names are a convention.
- Nothing is stored. If a message cannot be delivered, ARDA reports it and does
  not retry.

## Development

```sh
python3 -m unittest discover -s tests -v
ruff check arda tests
```

The tests drive the CLI against a fake `herdr` executable. Live behavior is verified
in a named Herdr session with real agents.
