# ARDA documentation

> **Start here.** The [project README](../README.md) is the two-minute overview. This page
> says which document answers which question.

## Find the right page

| I want to… | Read |
| --- | --- |
| Understand why ARDA exists | [Mental model](mental-model.md) |
| See how ARDA fits inside Herdr | [Architecture](architecture.md) |
| Understand how agents are found across sessions and machines | [Discovery and routing](discovery.md) |
| Know the exact addresses, messages and delivery rules | [Protocol](protocol.md) |
| Install ARDA and hand over a first task | [Getting started](getting-started.md) |
| Use ARDA with Claude Code | [Claude Code guide](guides/claude-code.md) |
| Use ARDA with Codex | [Codex guide](guides/codex.md) |
| Connect agents on other machines | [Multi-machine guide](guides/multi-machine.md) |
| Run ARDA on Windows | [Windows guide](guides/windows.md) |
| Know what approving ARDA changes and allows | [Trust and consent](guides/trust-and-consent.md) |
| See a real exchange between two agents | [Example: implement, review, fix](examples/team-workflow.md) |
| See a team spread over several machines | [Example: a distributed team](examples/distributed-team.md) |
| Look up a command, option, exit status or JSON field | [CLI reference](reference/cli.md) |
| Fix a problem | [Troubleshooting](troubleshooting.md) |
| Work on ARDA itself | [Contributing](contributing.md) |

## Layout

```text
docs/
├── README.md              this index
├── mental-model.md        why: different agents, one working team
├── architecture.md        Herdr vs ARDA, the path of a message, code map
├── discovery.md           the environment, name resolution, replies across machines
├── protocol.md            arda/1: addresses, messages, handoff conventions, delivery
├── getting-started.md     install, approve, start agents, first task
├── guides/
│   ├── claude-code.md
│   ├── codex.md
│   ├── multi-machine.md
│   ├── trust-and-consent.md
│   └── windows.md
├── examples/
│   ├── team-workflow.md   VERIFIED exchange between Claude Code and Codex
│   └── distributed-team.md
├── reference/
│   └── cli.md
├── troubleshooting.md
└── contributing.md
```

## Status labels

Every claim about support carries one of these labels.

| Label | Meaning |
| --- | --- |
| **VERIFIED** | Run live with real Herdr servers and real agents. |
| **EXPERIMENTAL** | Built and tested against real Herdr servers, but not yet in the full real-world setup (for example, physical machines). |
| **ILLUSTRATIVE** | Shows the idea with commands ARDA has; this exact setup has not been run. |
| **FUTURE** | Not built. |

## Terms

| Term | Meaning |
| --- | --- |
| Herdr environment | Your Herdr session, the other running Herdr sessions on the machine, and the machines saved in Herdr |
| Place | One Herdr session or one saved machine in that environment |
| Agent | A coding agent running in a Herdr pane (Claude Code, Codex, …) |
| Address | How an agent is named in a message: `@reviewer`, `@reviewer@desktop`, `@reviewer.s…` |
| Native token | The `s…` part of a reply address: a hash of the agent's conversation, so replies follow it across renames |
| Task | A `task_request` and its answers: `ack`, then `result` or `reject` |
| Delivery status | What Herdr could confirm: `delivered`, `submitted`, `uncertain`, `not_delivered` |
| Self-description | Role, tools and model an agent sets with `arda describe`; a claim, not verified |
