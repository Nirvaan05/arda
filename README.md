# ARDA

**Agents shouldn’t live in separate worlds.**

*One plugin to rule them all.*

[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](#quickstart)
[![Herdr 0.9.3+](https://img.shields.io/badge/herdr-0.9.3%2B-blueviolet)](https://herdr.dev)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)](#development)
![Platform: Linux](https://img.shields.io/badge/platform-linux-lightgrey)

ARDA is a [Herdr](https://herdr.dev) plugin that lets the coding agents in your Herdr
environment discover each other and hand off work, across sessions and machines. Herdr is
where your agents live; ARDA is how they reach each other. An agent finds another by name,
hands it a task with `arda task @name -- '…'`, and the acknowledgement and the result come
back to it as new prompts. The machines underneath are shared resources, not separate
worlds, and you stop being the relay between your agents. ARDA is pure Python standard
library: no daemon, no database, no queue and no MCP server.

**Works with:** Claude Code and Codex (tested). Other agents that Herdr can prompt are not
tested yet.

## What it looks like

You ask Claude to get some work done by Codex. Claude runs:

```text
$ arda task @codex -- 'Count the Python functions whose names start with test_ under tests/.'
delivered: task_request 708d3e to @codex: @codex was seen working after the message was submitted.
Its ack and its result (or reject) will arrive here as ARDA messages; you do not need to wait or poll.
```

Codex receives a prompt that starts with
`[arda/1 task_request id=708d3e from=@claude.1806d161 to=@codex]` and ends with the
commands to answer it. Codex runs `arda ack @claude.1806d161 708d3e`, does the work, then
`arda result @claude.1806d161 708d3e -- '18'`. Each answer arrives in Claude's session as
a new prompt, and Claude carries on from it. No human relays anything.

## Quickstart

You need Linux, Python 3.11 or later, Herdr 0.9.3 or later, and agents running in Herdr
panes. On every machine whose agents should take part:

```sh
# 1. Install the plugin and put `arda` and `arda-trust` on PATH
herdr plugin install Nirvaan05/arda
root=$(herdr plugin list --plugin arda --json |
  python3 -c 'import json, sys; print(json.load(sys.stdin)["result"]["plugins"][0]["plugin_root"])')
ln -s "$root/bin/arda" "$root/bin/arda-trust" ~/.local/bin/

# 2. Approve ARDA peer messages once. Run this yourself, not through an agent.
arda-trust          # shows what it would change
arda-trust --yes    # applies it

# 3. Start named agents, then introduce them to each other
herdr agent start claude --kind claude --pane <pane>
herdr agent start codex --kind codex --pane <pane> -- --no-daemon
herdr plugin action invoke introduce --plugin arda
```

Then ask Claude something like *"Ask Codex to review the last commit."*

To update, run `herdr plugin install Nirvaan05/arda` again (Herdr has no separate update
command), then `arda-trust --status`. Herdr keeps an installed plugin at a fixed path, so
the link survives updates.

## What ARDA changes on your machine

| Where | What | Undo |
| --- | --- | --- |
| Herdr's plugin registry | The `arda` plugin, with two actions: status and introduce | `herdr plugin uninstall arda` |
| `~/.local/bin/arda` | A link to the plugin's `bin/arda` | Delete the link |
| `$CLAUDE_CONFIG_DIR/rules/arda.md` | Rules for Claude Code: ARDA messages come from peer agents, may be answered without asking you each time, and risky requests must be rejected | `arda-trust --revoke --yes` |
| `$CLAUDE_CONFIG_DIR/settings.json` | `permissions.allow`: `Bash(arda *)`; `permissions.deny`: `Bash(arda-trust)` and `Bash(arda-trust *)`; each also for the full path of the script | `arda-trust --revoke --yes` |
| `$CODEX_HOME/AGENTS.md` | A marked section with the same rules for Codex | `arda-trust --revoke --yes` |
| `$CODEX_HOME/rules/arda.rules` | Lets the `arda` command, and nothing else, run outside Codex's sandbox; forbids `arda-trust` | `arda-trust --revoke --yes` |

Nothing else is changed. ARDA runs no service and keeps no files of its own.
`arda-trust --status` shows what is installed and whether it is current, including rules an older
version installed as `arda trust`; `arda-trust --yes` upgrades them.

## Security

ARDA is a convenience layer, not a security boundary.

- **Messages are not authenticated.** Any process running as you that can reach a Herdr
  socket, and any machine you saved in Herdr, can send one under any name. `from=` is
  accurate only for messages sent with `arda` by an agent from its own pane.
- **Peer messages are requests, not instructions from you.** The approval tells agents
  exactly that, and to reject anything risky. A message can still carry prompt injection
  from wherever its sender read it. ARDA removes terminal control characters and quotes
  every line of a message, but the receiving agent decides what to do.
- **The approval widens what agents can do.** Agents may act on peer messages without
  asking you, and Codex may run `arda` outside its sandbox. A trusted agent can therefore
  send whatever it can read to any agent in your Herdr environment, including on other
  machines. Each harness's own permission prompts and sandbox still govern what the
  receiver does. Grant trust only where every agent may work for every other.
- **Only you can extend the approval.** It allows the `arda` command, which has no way to
  change trust. Trust is changed only by `arda-trust`, a separate command the approval does
  not cover: Claude Code's deny rules and a Codex forbidden rule keep agents from running it,
  and it also refuses when it detects an agent's pane (a best-effort extra check). Run it
  yourself and check `arda-trust --status`. `--file` reads only from the working directory or
  the temporary directory, which keeps accidents small but is not a boundary against a
  determined agent.
- **Delivery is at most once,** with no retry, queue, replay protection or completion
  guarantee.

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
| `arda-trust` | Approve ARDA peer messages once; a separate command you run yourself (see above). |
| `arda status` | Plugin and protocol version. |

Put `--` before message text and single quotes around it, so it is never read as an
option or expanded by the shell. Text can also come from stdin (`-`) or `--file PATH`.
Add `--json` for machine-readable output. Exit status: 0 delivered or submitted, 1 not
delivered or a Herdr error, 2 usage error, 3 uncertain. Run as Herdr plugin actions,
commands also show their result as a Herdr notification.

## How it works

ARDA is a thin Herdr plugin, not a second runtime. Herdr provides discovery, agent state,
machines, routing, delivery and lifecycle. ARDA defines the addresses and messages and
asks Herdr every time; it keeps no list of its own, and agents keep their own context and
memory. The message format and delivery rules are in [PROTOCOL.md](PROTOCOL.md).

**One environment: sessions and machines.** ARDA's scope is the Herdr environment of the
machine it runs on: every running Herdr session on the machine, plus every machine saved
in Herdr (`herdr machine add`), which Herdr reaches with `herdr --machine`.

```text
$ arda peers
main: Herdr session main on this machine (laptop) (you are here)
  @claude              claude     working  (you)
desktop: saved machine desktop, Herdr session default
  @codex               codex      idle
gpu: saved machine gpu, Herdr session default: unreachable (machine_unreachable: ...)
```

- **Addresses are names.** `@codex` is looked up in every reachable place. If the same
  name runs in two places, ARDA refuses to guess and lists the choices, such as
  `@codex@desktop` and `@codex@main`.
- **Replies find their way back.** A reply goes to the sender's name plus a fingerprint of
  its Herdr terminal (`@claude.1806d161`), and the route is looked up again when the reply
  is sent. The fingerprint keeps a reply away from another terminal that has the same
  name. It cannot tell apart two agents started one after another in the same terminal
  under the same name, because Herdr does not show which conversation runs in a terminal.
- **Pane IDs are routes, not identities.** An agent without a Herdr name can only message
  agents in its own place, since a pane ID such as `w1:p2` would point at the wrong pane
  anywhere else.
- **Delivery is not acceptance.** `delivered` means Herdr saw the receiver start working
  after the message was typed; `submitted` means it was busy and its harness takes the
  message at its next step; `uncertain` means the text may have arrived; `not_delivered`
  means nothing was typed. Only `ack` means a task was accepted. ARDA never types into an
  agent that is waiting at an approval prompt, and never retries on its own.
- **Unreachable places say why:** the machine cannot be reached, its Herdr session is not
  running, it refused the SSH login (`herdr machine reconnect`), or its Herdr version does
  not match. A name found once while another place did not answer is still sent, and the
  result names the places that were not checked. ARDA cannot prove that two routes reach
  the same Herdr server, such as a saved machine that points back at this one, so it lists
  both and a name seen through both needs its place (`@name@place`).

For two machines to talk both ways, each needs a saved Herdr machine for the other and
`arda` on its PATH. Herdr gives a remote server no route back to the caller, so a machine
that cannot reach the sender cannot reply to it, and ARDA reports that rather than
guessing. A saved machine reaches one Herdr session on its host; to include another
session there, save it as another machine:
`herdr machine add HOST --remote-session NAME --label NAME`.

## Compared with other approaches

| | ARDA | Relaying by hand | Plain `herdr agent prompt` | Mailbox tools (e.g. MCP Agent Mail, agmsg) | A2A |
| --- | --- | --- | --- | --- | --- |
| Extra server, daemon or database | None | None | None | A message store; MCP Agent Mail also runs an HTTP server | An HTTP server per agent |
| Finds agents by name across Herdr sessions and saved machines | Yes | You do it | One Herdr server at a time | Within their own project registry | Through Agent Cards and URLs |
| Task, ack, result convention | Yes | You do it | No | Messages and threads | Yes, with task states |
| Works with the Claude Code and Codex you already run in Herdr | Yes | Yes | Yes | Through MCP tools or hooks | Needs an A2A server around each agent |
| Durable message history | No; agents keep their own context | No | No | Yes | Depends on the server |

## FAQ

**How do I make Claude Code and Codex talk to each other?**
Run both in Herdr panes with names, install ARDA, run `arda-trust --yes` once and invoke
the introduce action. Then ask one of them to involve the other; it uses
`arda task @name`, and the answer comes back as a prompt.

**Can Claude hand a task to Codex on another machine?**
Yes, if that machine is saved in Herdr (`herdr machine add`) and has ARDA installed. For
the reply, the other machine needs a saved Herdr machine pointing back.

**Do I need an MCP server, a daemon or a database?**
No. ARDA is a command that agents run; it calls the `herdr` CLI and exits.

**What happens if the other agent is busy or waiting for approval?**
A busy agent gets the message from its harness at its next step (`submitted`). An agent
waiting at an approval or question prompt gets nothing typed (`not_delivered`); try again
once it is unblocked.

**Does ARDA retry or queue messages?**
No. It reports exactly what Herdr can confirm and leaves retries to the agents, which see
the status and can check with `arda peers`.

**Which agents are supported?**
Claude Code and Codex are tested. Herdr types prompts only into agent kinds it supports.

## Agent notes

- **Codex: background server.** When Codex uses its shared background server, its shell
  commands run outside the Herdr pane, so ARDA cannot tell who is calling; it refuses to
  send and says so. Start Codex with `--no-daemon`.
- **Codex: sandbox.** Codex's workspace sandbox blocks the Herdr socket. `arda-trust`
  allows the `arda` command; otherwise approve it when Codex asks.
- **Restarts.** Herdr restores the pane layout after a server restart. It relaunches agents
  and restores their names only when Herdr's official integration for that agent is
  installed (`herdr integration`). Otherwise start the agents again; replies to messages
  sent before the restart are refused, because the sender's terminal is gone.
- **Skill.** For agents to know ARDA in every new session, install the skill in
  [skills/arda](skills/arda/SKILL.md): copy it into `$CLAUDE_CONFIG_DIR/skills/` (or a
  project's `.claude/skills/`) for Claude Code and into `~/.agents/skills/` (or a project's
  `.agents/skills/`) for Codex.

## Limits

- ARDA relies on Herdr's view of an agent's state. Herdr 0.9.3 does not always recognise a
  harness's own dialogs as "blocked" (Claude Code's end-of-turn tips, for example), and a
  message typed then lands in that dialog.
- A message addressed by name asks every reachable place for its agents, in parallel,
  because the name must be unique among them: one Herdr round trip per saved machine, plus
  the prompt itself. A reply asks saved machines only when the sender is not on this
  machine. A lookup gives up after 5 seconds on this machine and 15 on a saved machine, and
  stops the `ssh` it started. Herdr shares one SSH connection per saved machine by default
  (`[remote] manage_ssh_config`).
- Nothing is stored. If a message cannot be delivered, ARDA reports it and does not retry.
- Cross-machine messaging has been verified with real Herdr servers and Herdr's own machine
  routing on a single host, not yet between physical machines.
- ARDA has no adapters of its own for sandboxes, cloud runtimes or other agent hosts. Their
  agents can take part once Herdr can reach them, for example as a saved Herdr machine.

## Development

To work on ARDA, link a clone instead of installing it: `herdr plugin link "$PWD"` and
`ln -s "$PWD/bin/arda" ~/.local/bin/arda`. Herdr refuses to install a plugin from GitHub
while one with the same id is linked; `herdr plugin unlink arda` first.

```sh
python3 -m unittest discover -s tests -v
ruff check arda tests
```

The tests drive the CLI against a fake `herdr` executable. Live behavior is verified in
named Herdr sessions with real Claude Code and Codex agents.

## License

[MIT](LICENSE)
