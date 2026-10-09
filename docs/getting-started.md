# Getting started

> **From installation to a first handoff** between two agents in Herdr. Every
> command here is the real command; nothing is shortened.

The shell commands below use Linux syntax. On Windows, follow the
[Windows guide](guides/windows.md) for installation, approval, plugin actions and Codex
setup, then use the same ARDA messaging commands.

| Step | What | Command |
| --- | --- | --- |
| 1 | Install Herdr | see [herdr.dev](https://herdr.dev) |
| 2 | Install ARDA | `herdr plugin install Nirvaan05/arda` |
| 3 | Approve ARDA yourself | `arda-trust --yes` |
| 4 | Start agents named by role | `herdr agent start reviewer --kind codex --pane <pane> -- --no-daemon` |
| 5 | Introduce them | `herdr plugin action invoke introduce --plugin arda` |
| 6 | Hand over a task | an agent runs `arda task @reviewer -- '…'` |
| 7 | Get the result | it arrives in the sender's pane as a new prompt |

## Requirements

| | |
| --- | --- |
| Platform | Linux or Windows |
| Python | 3.11 or later (standard library only) |
| Herdr | 0.9.3 or later |
| Agents | Claude Code, Codex and other agents Herdr can prompt, including OpenCode and Gemini, are verified |

## 1. Install Herdr

Follow the instructions at [herdr.dev](https://herdr.dev). Then start a session:

```sh
herdr
```

## 2. Install ARDA

Install the plugin and put `arda` and `arda-trust` on your PATH:

```sh
herdr plugin install Nirvaan05/arda
plugin_root=$(herdr plugin list --plugin arda --json |
  python3 -c 'import json, sys; print(json.load(sys.stdin)["result"]["plugins"][0]["plugin_root"])')
mkdir -p "$HOME/.local/bin"
ln -s "$plugin_root/bin/arda" "$plugin_root/bin/arda-trust" "$HOME/.local/bin/"
export PATH="$HOME/.local/bin:$PATH"
```

Do this on every machine whose agents should take part. Keep `~/.local/bin` on your PATH
in future sessions; keep existing links if they already point to this installation.

## 3. Approve ARDA yourself

Agents need your approval to act on each other's messages. Run this **yourself, in a plain
terminal or a plain shell pane in Herdr**, not inside an agent's pane:

```sh
arda-trust          # shows what it would change
arda-trust --yes    # applies it
```

It also installs Herdr's Claude Code and Codex integrations, which give each agent a reply
address that survives renames. To check the setup at any time: `arda setup`.

Approval applies to the selected Claude Code and Codex profiles. Their permission
controls still apply to requested work; other harnesses need their own configuration.

What this changes, and why it must be run by you: [trust and consent](guides/trust-and-consent.md).

## 4. Start agents named by their roles

Name agents after what they do. In a pane at its shell prompt (`herdr pane current` shows
its ID):

```sh
herdr agent start implementer --kind claude --pane <pane>
herdr agent start reviewer --kind codex --pane <pane> -- --no-daemon
```

Codex needs `--no-daemon` so its commands run inside its pane; see the
[Codex guide](guides/codex.md). An agent you already started can be named with
`herdr agent rename <pane> <name>`.

## 5. Introduce the agents

```sh
herdr plugin action invoke introduce --plugin arda
```

Each idle, named agent receives a short note with its address, its peers and the commands
to reach them. To see the team at any time, run `arda peers` in a pane (or
`arda peers --session <name>` from outside Herdr):

```text
2 agents in 1 place: 2 idle

main · Herdr session on this machine (laptop) · you are here
  ○ @implementer  claude  idle  ~/src/app
  ○ @reviewer     codex   idle  ~/src/app

No description yet: @implementer, @reviewer (agents add one with arda describe).
```

Agents can then describe themselves, so peers know what to hand them:

```sh
arda describe --role 'reviews diffs for correctness' --tools 'git, pytest' --model auto
```

## 6. Hand over a task

Ask the implementer, in plain words: *"Ask the reviewer to review the last commit."* It
runs:

```text
$ arda task @reviewer -- 'Review the last commit. Done when: a list of issues with file:line, or "no issues".'
delivered: task_request 708d3e to @reviewer: @reviewer was seen working after the message was submitted.
Its ack and its result (or reject) will arrive here as ARDA messages; you do not need to wait or poll.
```

## 7. Get the result

The reviewer receives the task as a prompt, ending with the exact commands to answer it.
It answers with `arda ack`, does the work and sends `arda result`. Both arrive in the
implementer's pane as new prompts:

```text
[arda/1 result id=3b91c2 re=708d3e from=@reviewer.s… to=@implementer]
> Two issues: src/http.py:88 retries POST; no jitter in the backoff.
```

Nobody relays anything. The message types and delivery statuses are in the
[protocol](protocol.md).

## Update and remove

| Task | Command |
| --- | --- |
| Update | `herdr plugin install Nirvaan05/arda`, then `arda-trust --status` |
| Remove the approval | `arda-trust --revoke --yes` |
| Remove the plugin | `herdr plugin uninstall arda`, then delete the links in `~/.local/bin` |

Herdr keeps an installed plugin at a fixed path, so the links survive updates.

## Next

- [Claude Code guide](guides/claude-code.md) and [Codex guide](guides/codex.md).
- [Multi-machine guide](guides/multi-machine.md): agents on other machines.
- [Team workflow example](examples/team-workflow.md).
