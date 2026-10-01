# ARDA

**One plugin to rule them all.**

AI changed how much one person can take on. Work now runs in parallel across many
sessions, and much of it is done by agents. Development environments still organize
resources around people: a person owns a machine, opens a session and carries its
context. Resources should be organized around the work, and work should continue
without the person who started it.

[Herdr](https://herdr.dev) already treats terminals, sessions, machines and agents as a
shared working environment. ARDA adds what is still missing: the agents in it can find
and address one another. Claude knows that Codex is there, on this machine or another
one, and can hand it a task. Codex can accept it and send back the result. The human no
longer relays messages between them.

ARDA is a thin Herdr plugin, not a second runtime. Herdr provides discovery, agent
state, machines, routing, delivery and lifecycle. ARDA defines the messages and how
agents use them. It has no daemon, database, queue, registry or transport of its own,
and agents keep their own context and memory.

## What it looks like

A user asks Claude to get some work done by Codex. Claude runs:

```text
$ arda task @codex -- 'Count the Python functions whose names start with test_ under tests/.'
delivered: task_request 708d3e to @codex: @codex was seen working after the message was submitted.
Its ack and its result (or reject) will arrive here as ARDA messages; you do not need to wait or poll.
```

Codex receives a prompt that starts with
`[arda/1 task_request id=708d3e from=@claude#1806d161 to=@codex]` and ends with the
commands to answer it. Codex runs `arda ack @claude#1806d161 708d3e`, does the work, then
runs `arda result @claude#1806d161 708d3e -- '18'`. Each answer arrives in Claude's
session as a new prompt, and Claude carries on from it. See [PROTOCOL.md](PROTOCOL.md)
for the message format and delivery rules.

## One environment: sessions and machines

ARDA's scope is the Herdr environment of the machine it runs on. That is every running
Herdr session on the machine, plus every machine saved in Herdr (`herdr machine add`),
which Herdr reaches with `herdr --machine`. ARDA asks Herdr for this every time and keeps
no list of its own.

```text
$ arda peers
main: Herdr session main on this machine (laptop) (you are here)
  @claude              claude     working  (you)
desktop: saved machine desktop, Herdr session default
  @codex               codex      idle
gpu: saved machine gpu, Herdr session default: unreachable (machine_unreachable: ...)
```

- Address agents by name: `@codex`. ARDA looks the name up in every reachable place. If
  the same name runs in two places, ARDA refuses to guess and lists the choices, such as
  `@codex@desktop` and `@codex@main`.
- A reply goes to the sender's name plus a fingerprint of its Herdr terminal
  (`@claude#1806d161`). The route is looked up again when the reply is sent, and the
  fingerprint makes sure it reaches the agent that asked, not another agent that happens
  to have the same name.
- A pane ID such as `w1:p2` is a route in one Herdr server, not an identity.

For two machines to talk both ways, each must be able to reach the other through Herdr.
Each machine needs a saved Herdr machine for the other, and ARDA installed with `arda` on
its PATH. Herdr gives a remote server no route back to the caller, so a machine that
cannot reach the sender cannot reply to it, and ARDA reports that rather than guessing.

## Requirements

- Linux and Python 3.11 or later; no other dependencies.
- Herdr 0.9.3 or later.
- Agents running in Herdr panes and started with names, e.g.
  `herdr agent start codex --kind codex --pane <pane>`. Tested with Claude Code and
  Codex. Herdr only types prompts into agent kinds it supports.

## Install

From a clone of this repository, on every machine whose agents should take part:

```sh
herdr plugin link "$PWD"
ln -s "$PWD/bin/arda" ~/.local/bin/arda   # put arda on PATH
```

To remove it, run `herdr plugin unlink arda` and delete the link.

## Approve ARDA once

Agents treat a message from another agent as coming from that agent, not from you. Claude
Code asks you before acting on a peer's task, and its auto mode blocks such work. Codex
declines peer work you have not allowed, and its sandbox blocks the Herdr socket. Without
a standing approval you would be asked again for every message.

Run this yourself, in a terminal, to approve ARDA peer communication for your Claude Code
and Codex profiles on this machine:

```sh
arda trust          # shows what it would change
arda trust --yes    # applies it
arda trust --status
arda trust --revoke --yes
```

It writes only to each harness's own configuration: a rules file
(`rules/arda.md`) and `Bash(arda …)` permission rules for Claude Code, and for Codex a
marked section in its global `AGENTS.md` plus an execpolicy rule that lets the `arda`
command, and nothing else, run outside the sandbox. The approval says that ARDA messages
come from peer agents, may be answered without a per-message go-ahead, and must be
rejected when they ask for anything risky. Agents still decide what to take on, and the
harness's own permission prompts still apply. `arda trust` refuses to run from inside an
agent's pane. New agent sessions pick it up.

## Introduce the agents

Agents do not know about ARDA until someone tells them. Run the **ARDA: introduce the
agents to each other** action in Herdr, or:

```sh
herdr plugin action invoke introduce --plugin arda
```

Every idle named agent in every reachable place receives a short note with its own
address, its peers and the ARDA commands. For agents to know ARDA in every new session,
install the skill in [skills/arda](skills/arda/SKILL.md): copy it into
`$CLAUDE_CONFIG_DIR/skills/` (or a project's `.claude/skills/`) for Claude Code and into
`~/.agents/skills/` (or a project's `.agents/skills/`) for Codex.

## Commands

| Command | Purpose |
| --- | --- |
| `arda whoami` | Your own address, pane, session and machine. |
| `arda peers` | Active agents in every reachable Herdr session and machine. |
| `arda send @name -- 'text'` | Send a note. |
| `arda task @name -- 'text'` | Hand over a task. Expect `ack`, then `result` or `reject`. |
| `arda ack @name <id>` | Accept a task you received. |
| `arda result @name <id> -- 'text'` | Return the outcome of a task. |
| `arda reject @name <id> -- 'reason'` | Decline a task, or report that it failed. |
| `arda introduce [@name ...]` | Introduce ARDA to agents. Busy agents are skipped. |
| `arda trust` | Approve ARDA peer messages once (see above). |
| `arda status` | Plugin and protocol version. |

Put `--` before message text and single quotes around it, so it is never read as an
option or expanded by the shell. Text can also come from `--file PATH` or from stdin
(`-`). Add `--json` for machine-readable output. Exit status: 0 delivered or submitted,
1 not delivered or a Herdr error, 2 usage error, 3 uncertain. Run as Herdr plugin
actions, commands also show their result as a Herdr notification.

## Agent notes

- **Codex: background server.** When Codex uses its shared background server, its shell
  commands run outside the Herdr pane, so ARDA cannot tell who is calling; it refuses to
  send and says so. Start Codex with `--no-daemon`:
  `herdr agent start codex --kind codex --pane <pane> -- --no-daemon`.
- **Codex: sandbox.** Codex's workspace sandbox blocks the Herdr socket. `arda trust`
  allows the `arda` command; otherwise approve it when Codex asks.
- **Restarts.** Herdr restores the pane layout after a server restart. It relaunches
  agents and restores their names only when Herdr's official integration for that
  agent is installed (`herdr integration`). Otherwise start the agents again; replies to
  messages sent before the restart are refused, because the agent is not the one that
  sent them.

## Limits

- Messages are not authenticated. Any process that can use a Herdr session can send one.
- ARDA relies on Herdr's view of an agent's state. Herdr 0.9.3 does not always recognise
  a harness's own dialogs as "blocked" (Claude Code's end-of-turn tips, for example), and
  a message typed then lands in that dialog.
- Every send asks each reachable place for its agents, so messages to other machines
  cost a few Herdr round trips.
- Nothing is stored. If a message cannot be delivered, ARDA reports it and does not
  retry.
- Cross-machine messaging has been verified with real Herdr servers and Herdr's own
  machine routing on a single host, not yet between physical machines.

## Development

```sh
python3 -m unittest discover -s tests -v
ruff check arda tests
```

The tests drive the CLI against a fake `herdr` executable. Live behavior is verified in
named Herdr sessions with real Claude Code and Codex agents.
