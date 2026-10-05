# ARDA

**Agents shouldn’t live in separate worlds.**

*One plugin to rule them all.*

[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](#quickstart)
[![Herdr 0.9.3+](https://img.shields.io/badge/herdr-0.9.3%2B-blueviolet)](https://herdr.dev)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)](#development)
![Platform: Linux](https://img.shields.io/badge/platform-linux-lightgrey)

AI has made it normal for one team to work with many agents at once. One coding agent
implements a feature, another reviews it, another runs the tests, another uses a local model
for heavy analysis. They run in different harnesses, in different sessions, on different
machines, and each is good at something different. Yet they still work as isolated
workers, and the human becomes the relay that carries context from one to the next.

[Herdr](https://herdr.dev) already brings the sessions and machines those agents run on
into one environment. **ARDA is the Herdr plugin that lets the agents inside it work as one
team:** they find each other, address each other by name, hand work over and get the results
back, with no human in between.

**Different agents. Different capabilities. One working team.** The machine is a resource;
the agent is a worker; the work moves between them.

```text
                        ONE HERDR ENVIRONMENT

   implementer      reviewer        tester        security     agents with different roles
        \               |              |              /
         ───────────────────── ARDA ─────────────────          how they reach each other

     laptop         desktop        GPU workstation    …        shared resources, wherever they run
```

### Why a team of different agents

- **They are worth having because they differ:** in model, tools, runtime, cost, speed and
  the machine they sit on. Give each piece of work to the agent it fits (an independent
  reviewer on another model, a quick agent for routine checks, a specialist next to a local
  model), not to the strongest agent every time.
- **The agent holding the task decides whom to ask.** It has the context. ARDA does not
  route, rank or pick agents; it only lets them reach each other.
- **Name agents by role** (`@reviewer`, `@tester`), so whatever agent fills a role can change
  without changing how the team works.
- **Hand off when the work calls for it,** at any point an agent finds a sub-task, and say
  what done looks like: the outcome wanted and what to send back.
- **More agents is not automatically better.** Watch whether the handoffs actually improve
  the work.

ARDA is not one developer driving several machines, a chat tool, a bridge between two
particular agents, a remote terminal wrapper or a control plane. It is a thin Herdr
plugin: Herdr does the discovery, routing and delivery, and ARDA gives the agents
addresses and a small protocol for handing work to each other. It is pure Python standard
library: no daemon, no database, no queue and no MCP server.

### What works today

| | Status |
| --- | --- |
| Agents in the same Herdr session | Works; used live between Claude Code and Codex agents. |
| Agents in other Herdr sessions on the machine | Works; tested with real Herdr servers. |
| Agents on machines saved in Herdr (`herdr machine add`) | Works through Herdr's own machine routing; validated with real Herdr servers on one host, not yet between physical machines. |
| Reply addresses that follow an agent across renames | Works with Herdr's official Claude Code and Codex integrations; tested live with Codex. |
| Claude Code and Codex | Tested. Other agents Herdr can prompt are not tested yet. |
| Sandboxes, cloud runtimes and other agent hosts | Not built: their agents can take part once Herdr can reach them. |

## What it looks like

Three agents run in Herdr, named by their roles: `@implementer` (Claude Code), `@reviewer`
(Codex) and `@tester`. The implementer finishes a change and hands the review over:

```text
$ arda task @reviewer -- 'Review the parser change in src/parser.py for unhandled edge cases.'
delivered: task_request 708d3e to @reviewer: @reviewer was seen working after the message was submitted.
Its ack and its result (or reject) will arrive here as ARDA messages; you do not need to wait or poll.
```

The reviewer receives a prompt that starts with
`[arda/1 task_request id=708d3e from=@implementer.s3f9a… to=@reviewer]` and ends with the
commands to answer it. It runs `arda ack`, reviews the change, and sends `arda result` with
its findings, which arrive in the implementer's session as a new prompt. The implementer
fixes them and hands validation to `@tester` the same way. Nobody relays anything. More
scenarios are in [examples/](examples/README.md).

## Quickstart

You need Linux, Python 3.11 or later, Herdr 0.9.3 or later, and agents running in Herdr
panes. On every machine whose agents should take part:

```sh
# 1. Install the plugin and put `arda` and `arda-trust` on PATH
herdr plugin install Nirvaan05/arda
root=$(herdr plugin list --plugin arda --json |
  python3 -c 'import json, sys; print(json.load(sys.stdin)["result"]["plugins"][0]["plugin_root"])')
ln -s "$root/bin/arda" "$root/bin/arda-trust" ~/.local/bin/

# 2. Approve ARDA peer messages once, yourself, in a plain terminal or a plain shell pane in
#    Herdr (not inside an agent's pane). This also installs Herdr's Claude Code and Codex
#    integrations for native identity. `arda setup` shows what is approved and what is not.
arda-trust          # shows what it would change
arda-trust --yes    # applies it

# 3. Start agents named by their roles, then introduce them to each other
herdr agent start implementer --kind claude --pane <pane>
herdr agent start reviewer --kind codex --pane <pane> -- --no-daemon
herdr plugin action invoke introduce --plugin arda
```

Then ask the implementer something like *"Ask the reviewer to review the last commit."*

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
| Herdr's Claude Code and Codex integrations | `herdr integration install claude` / `codex`: a `SessionStart` hook that reports each agent's conversation to Herdr (Codex also gets `[features] hooks = true`). Skip with `--no-integrations` | `herdr integration uninstall claude` / `codex` (revoke leaves them, they are Herdr's) |

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
- **The approval covers `arda`, and `arda` cannot change it.** Trust is changed only by
  `arda-trust`, a separate command. It refuses to run under another name or from an agent's
  pane, both commands run Python isolated with the interpreter from the standard system PATH,
  and the installed rules tell Claude Code (deny rules) and Codex (a forbidden rule) not to
  let agents run it. These are guards, not a boundary: Claude Code documents its Bash deny
  rules as not a security boundary (they miss commands wrapped in `sh -c`, for example), and
  any process running as you that can reach Herdr can type into a pane, including a
  Claude Code `!` shell command. Codex's sandbox is the strongest of them. Approve ARDA only
  where every agent may work for every other, and check `arda-trust --status`. `--file`
  reads only visible files from the working directory or /tmp, checked on the file it
  opened; that keeps accidents small but is not a boundary against a determined agent.
- **Delivery is at most once,** with no retry, queue, replay protection or completion
  guarantee.

## Commands

| Command | Purpose |
| --- | --- |
| `arda whoami` | Your own address, pane, session and machine. |
| `arda peers` | Active agents in every reachable Herdr session and machine, with what each says it does. |
| `arda describe --role '…' --tools '…' --model '…'` | Tell peers what you do, which tools you use and which model you run. Without options, show it. |
| `arda send @name -- 'text'` | Send a note. |
| `arda task @name -- 'text'` | Hand over a task. Expect `ack`, then `result` or `reject`. |
| `arda ack @name <id>` | Accept a task you received. |
| `arda result @name <id> -- 'text'` | Return the outcome of a task. |
| `arda reject @name <id> -- 'reason'` | Decline a task, or report that it failed. |
| `arda introduce [@name ...]` | Introduce ARDA to agents. Busy agents are skipped. |
| `arda setup` | Show whether ARDA is approved, what approving would change, and the command to run (read-only). |
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
  @implementer         claude     working  ~/src/app (you)
      self-described: role "implements features in src/"  tools "pytest, ruff"
desktop: saved machine desktop, Herdr session default
  @reviewer            codex      idle     /home/me/src/app
      self-described: role "reviews diffs for correctness and security"
gpu: saved machine gpu, Herdr session default: unreachable (machine_unreachable: ...)
```

- **Peers say what they do.** An agent describes itself once with
  `arda describe --role '…' --tools '…' --model '…'`. Herdr keeps the description as
  metadata on the agent's pane, and `arda peers` shows it next to what Herdr observes:
  harness, state, working directory and place. A description is the agent's own claim, and
  it disappears when another agent takes over the pane or Herdr restarts.

- **Addresses are names, and names stay unique.** `@codex` is looked up in every place
  and sent only when exactly one agent has that name and every place answered. If the
  name runs in two places, or a place does not answer, ARDA sends nothing and lists the
  choices, such as `@codex@desktop`; an address with its place needs only that place.
- **Renames carry through.** Names are read from Herdr on every send, so after
  `herdr agent rename` the new name works at once and the old one is refused with the
  agents there are now.
- **Replies find their way back.** With Herdr's official integrations installed
  (`herdr integration install claude` / `codex`), a sender is identified by its native
  conversation (`@claude.s…`), so replies follow it across renames and resumed restarts.
  Without them, the reply address is the sender's name plus the end of its terminal ID
  (`@claude.1806d161`), a best-effort hint that cannot tell apart two agents started one
  after another in the same terminal under the same name.
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
  not match. While a saved machine is offline, address agents with their place, or take the
  machine out of the environment yourself (`herdr machine disable`). ARDA cannot prove that two routes reach
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
- **Native identity.** Herdr's Claude Code and Codex integrations, which `arda-trust --yes`
  installs, make Herdr report each agent's conversation, which ARDA uses as its reply
  address. Codex asks you once to review and trust the new hook (a Hooks dialog in its pane);
  until you do, Herdr does not see that dialog as blocked, and a message typed into it is
  lost.
- **Restarts.** Herdr restores the pane layout after a server restart. It relaunches agents
  and restores their names only when Herdr's official integration for that agent is
  installed (`herdr integration`). Otherwise start the agents again; replies to messages
  sent before the restart are refused, because the sender's terminal is gone.
- **Skills.** For agents to know ARDA in every new session, install the skill in
  [skills/arda](skills/arda/SKILL.md): copy it into `$CLAUDE_CONFIG_DIR/skills/` (or a
  project's `.claude/skills/`) for Claude Code and into `~/.agents/skills/` (or a project's
  `.agents/skills/`) for Codex. [skills/arda-setup](skills/arda-setup/SKILL.md) adds a
  `/arda-setup` command to Claude Code that only you can invoke; it shows the setup and the
  command to run. The Herdr action **ARDA: show setup** does the same in Herdr.
- **Why approval happens in a plain terminal.** Herdr and the agent harnesses offer no way
  to tell your keystroke or click in an agent's pane from the agent's own, so anything that
  approves from inside an agent's pane could be triggered by an agent. The shortcuts above
  therefore only show the setup; `arda-trust` makes the change.

## Limits

- ARDA relies on Herdr's view of an agent's state. Herdr 0.9.3 does not always recognise a
  harness's own dialogs as "blocked" (Claude Code's end-of-turn tips, for example), and a
  message typed then lands in that dialog.
- A message or reply that is not tied to a place asks every place for its agents (at most
  eight at a time, one at a time per saved machine), because it must be unique among them;
  then it reads the receiver again and types. An address with its place asks only that
  place. A lookup gives up after 5 seconds on this machine and 15 on a saved machine and
  stops the `ssh` it started, and a whole survey stops after 30 seconds. Herdr shares one
  SSH connection per saved machine by default (`[remote] manage_ssh_config`).
- Nothing is stored. If a message cannot be delivered, ARDA reports it and does not retry.
- Descriptions are self-reported and unverified, at most 80 characters per field, and lost
  when a Herdr server restarts.
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
