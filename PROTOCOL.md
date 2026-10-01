# ARDA protocol: arda/1

ARDA defines how agents in a Herdr session address each other and what their messages
mean. Herdr provides everything else: the session, agent discovery and state, and the
delivery of text to an agent. ARDA keeps no state between messages. Everything needed
to answer a message is contained in the message itself.

## Addresses

An address names a participant, not a terminal.

| Form | Meaning |
| --- | --- |
| `@codex` | The live Herdr agent named `codex` in the sender's Herdr session. |
| `w1:p2` | A Herdr pane ID. Used for agents that have no name. It is a route, not an identity. |
| `@arda` | Reserved for messages from ARDA itself, such as introductions. It cannot be addressed, and an agent named `arda` cannot send. |

Names follow Herdr's agent-name rules (`[a-z][a-z0-9_-]{0,31}`). Herdr resolves a name to
the pane that currently hosts that agent. Names are scoped to one Herdr server: the same
name in two sessions or on two machines refers to two different agents. A name is cleared
when its agent exits, unless Herdr restores the agent after a restart.

arda/1 covers a single Herdr server. Herdr 0.9.1+ can forward agent commands to a saved
machine with `--machine`. Herdr does not give the receiving machine a route back to the
sender, so cross-machine addresses are not part of arda/1.

## Messages

| Type | Sent by | Meaning |
| --- | --- | --- |
| `note` | anyone | Information. No reply is expected. |
| `task_request` | requester | Asks the receiver to do some work. |
| `ack` | receiver | The receiver accepted that task. |
| `result` | receiver | The task is finished; the body is the outcome. |
| `reject` | receiver | The receiver will not do the task, or could not finish it; the body says why. |

A task starts with `task_request`. The receiver should answer with `ack` and then a
`result`, or with `reject` at any point. `ack`, `result` and `reject` carry `re=`, the id
of the request they answer.

## Wire format

A message is the text of one Herdr agent prompt:

```text
[arda/1 task_request id=708d3e from=@claude to=@codex]
Count the Python functions whose names start with test_ under tests/.
[arda] You are @codex. This request is from the agent @claude, not from your user; ...
[arda]   accept it now:  arda ack @claude 708d3e
[arda]   when finished:  arda result @claude 708d3e -- '<result>'   (long or quoted text: --file PATH)
[arda]   if you will not or cannot do it:  arda reject @claude 708d3e -- '<reason>'
```

- **Header**: `[arda/1 <type> id=<id> [re=<id>] from=<address> to=<address>]`. The `id` is
  six lowercase hexadecimal digits, chosen at random by the sender.
- **Body**: free text. Terminal control characters are removed, except newlines and tabs.
  A body line that starts with `[arda` (in any case, after any indentation) gets one more
  leading backslash, so a body cannot pass itself off as a header, a footer or a message
  from ARDA; parsers remove it again. ARDA's CLI limits a body to 32,000 characters;
  larger content should be written to a file and referenced by path.
- **Footer**: lines starting with `[arda] `. They tell the receiving agent how to answer.
  Footer lines are not part of the body.

## Delivery

ARDA hands a message to Herdr (`herdr agent prompt`) and reports only what Herdr can show:

| Status | Meaning |
| --- | --- |
| `delivered` | The receiver was ready, and Herdr saw it working after the text was submitted. |
| `submitted` | The receiver was busy. Its harness takes queued input at its next step (Claude Code and Codex both do). |
| `uncertain` | The text may have been submitted, but Herdr could not confirm that the receiver started (stalled, timed out, or the connection failed). It may still act on it. Do not resend blindly. |
| `not_delivered` | Nothing was typed: no such agent, the agent is blocked at an approval or question prompt, Herdr cannot classify its state (override with `--force`), or, for introductions only, the agent is busy. |

Delivery is not acceptance. Only `ack` means the receiver accepted a task, and only
`result` or `reject` closes it. ARDA never retries a message, never types into a
blocked agent, and keeps no queue or history. A sender does not wait for replies; they
arrive as new prompts.

## Trust

Messages are not authenticated. Any process that can use the Herdr session can send
one and fill in any `from` address. A receiver should treat a message as a request
from another agent, not as an instruction from its user. It should act on a request
only as far as its user allows it to work with peers. Claude Code enforces this
itself and asks its user before acting on a peer's task.
