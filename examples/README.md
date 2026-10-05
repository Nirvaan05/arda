# ARDA examples

Each example is a small team of agents with different roles in one Herdr environment.
Agents are named after what they do (`herdr agent start reviewer --kind codex ...`), and
ARDA lets them hand work to each other. The commands shown are the ones the agents run
themselves; you only ask the first agent for the outcome you want.

The status line under each example says how far it has been tested.

## 1. Implement, review, test

Three agents in the same Herdr session: `@implementer` (Claude Code), `@reviewer` (Codex) and
`@tester` (any agent Herdr can prompt).

You ask the implementer: *"Add retry support to the HTTP client, get it reviewed, then have it
tested."*

```text
implementer$ arda task @reviewer -- 'Review the retry change in src/http.py: backoff, idempotency, error paths. Done when: a list of issues with file:line, or "no issues".'
delivered: task_request 3a91c0 to @reviewer: @reviewer was seen working after the message was submitted.

reviewer   $ arda ack @implementer.s5d0e… 3a91c0
reviewer   $ arda result @implementer.s5d0e… 3a91c0 -- 'Two issues: POST is retried; no jitter. Details in review.md.'

implementer$ arda task @tester -- 'Run the HTTP client tests and a retry test against a flaky server. Done when: pass/fail counts and any failing test names.'
tester     $ arda ack @implementer.s5d0e… 7c2b18
tester     $ arda result @implementer.s5d0e… 7c2b18 -- 'All 41 tests pass; the flaky-server test passes 20/20.'
```

Each `ack` and `result` arrives in the implementer's session as a new prompt, and it carries
on from there. You see the outcome, not the relaying.

*Status: same-session messaging between Claude Code and Codex agents is tested live. The
implementer → reviewer → tester chain is the same mechanism with a third agent.*

## 2. A reviewer on another machine

The implementer runs on a laptop; a reviewer runs on a desktop that the laptop has saved in
Herdr (`herdr machine add desktop`), and the desktop has the laptop saved too, so replies
can come back. ARDA is installed on both.

```text
implementer$ arda peers
2 agents in 2 places: 1 working, 1 idle

main · Herdr session on this machine (laptop) · you are here
  ● @implementer  claude  working  ~/src/app  (you)

desktop · saved machine desktop, Herdr session default
  ○ @reviewer     codex   idle     /home/me/src/app

implementer$ arda task @reviewer -- 'Review the migration in db/0042.sql; it must be safe to run twice.'
```

The name is enough: ARDA looks it up across every session and saved machine, and refuses to
guess if the name runs in two places or a place does not answer. Use `@reviewer@desktop`
then.

*Status: works through Herdr's own machine routing; validated with real Herdr servers on one
host (with SSH simulated), not yet between physical machines.*

## 3. Heavy analysis on a GPU workstation

A specialist agent runs next to a local model on a GPU workstation saved in Herdr, named
`@analyst`. Any agent on the team can hand it work that needs that machine:

```text
reviewer   $ arda task @analyst -- 'Profile the embedding job in jobs/embed.py on the full dataset; report the top 5 hotspots.'
```

ARDA does not care which harness or model `@analyst` runs, only that Herdr can see it as an
agent and type into it.

*Status: the routing is the same as in example 2. The agent on the workstation must be one
Herdr can prompt; agents other than Claude Code and Codex are not tested with ARDA yet.*

## Answering, declining and replies

- A receiver answers with `arda ack`, then `arda result`, or `arda reject` with a reason
  when it will not or cannot do the work. Every message ends with the exact commands.
- Messages from peers are requests, not instructions from the user: a receiver takes on a
  task only as far as its user allows it to work with peers.
- A reply address such as `@implementer.s5d0e…` follows the agent that asked, even if it
  has been renamed since (with Herdr's official integrations installed).
