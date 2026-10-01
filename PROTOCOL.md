# ARDA protocol: arda/1

ARDA defines how agents in a Herdr environment address each other and what their messages
mean. Herdr provides everything else: the session, agent discovery and state, and the
delivery of text to an agent. ARDA keeps no state between messages. Everything needed
to answer a message is contained in the message itself.

## Addresses

An address names a participant, not a terminal.

| Form | Meaning |
| --- | --- |
| `@codex` | The live Herdr agent named `codex`, wherever it runs in the sender's Herdr environment. |
| `@codex@desktop` | The agent `codex` in the place `desktop`: a Herdr session on this machine or a saved Herdr machine. Needed only when the name runs in more than one place. |
| `@claude.1806d161` | The agent `claude` whose Herdr terminal ID ends in `1806d161`. Senders identify themselves this way, so replies reach them and no other agent with the same name. |
| `w1:p2`, `w1:p2@desktop` | A Herdr pane ID, for agents without a name. A route in one Herdr server, not an identity; an agent without a name can only message agents in its own place. |
| `@arda` | Reserved for messages from ARDA itself, such as introductions. It cannot be addressed, and an agent named `arda` cannot send. Like every sender, it is not authenticated. |

Names follow Herdr's agent-name rules (`[a-z][a-z0-9_-]{0,31}`); place names are the
lowercased Herdr session name or saved-machine label (`[a-z0-9][a-z0-9._-]{0,62}`); a name that does
not fit, or that two places share, is rewritten or given a short suffix, and `arda peers` shows the
name to use.

The sender's Herdr environment is its own Herdr session, every other running Herdr
session on its machine, and every enabled machine saved in Herdr, which Herdr reaches
with `herdr --machine`. ARDA resolves an address against that environment each time a
message is sent:

- A name found in exactly one reachable place is sent there. A name found in several
  places is refused with the qualified choices; ARDA never picks one.
- A fingerprint must match the agent found, or nothing is sent.
- A place that does not answer is reported as unreachable. Nothing is sent to it.

Places are relative to the machine that resolves them, so a reply is addressed to the
sender's name and fingerprint, not to a place. The receiver resolves that against its
own environment, which must be able to reach the sender's machine (through a saved Herdr
machine) for the reply to arrive.

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
[arda/1 task_request id=708d3e from=@claude.1806d161 to=@codex]
> Count the Python functions whose names start with test_ under tests/.
[arda] You are @codex. This request is from the agent @claude.1806d161, not from your user; ...
[arda]   accept it now:  arda ack @claude.1806d161 708d3e
[arda]   when finished:  arda result @claude.1806d161 708d3e -- '<result>'   (long or quoted text: --file PATH)
[arda]   if you will not or cannot do it:  arda reject @claude.1806d161 708d3e -- '<reason>'
```

- **Header**: `[arda/1 <type> id=<id> [re=<id>] from=<address> to=<address>]`. The `id` is
  six lowercase hexadecimal digits, chosen at random by the sender.
- **Body**: free text, with every line prefixed by `> ` (an empty line becomes `>`). No body
  line can therefore stand where a header or footer line stands, whatever characters it
  contains. Before quoting, line separators become newlines, and control characters,
  invisible format characters (zero-width, bidi, tag) and unpaired surrogates are removed;
  tabs and newlines are kept. ARDA's CLI limits a body to 32,000 bytes of UTF-8; larger
  content should be written to a file and referenced by path.
- **Footer**: lines starting with `[arda] `. They tell the receiving agent how to answer.
  Footer lines are not part of the body.
- A parser accepts a message only if the header has known fields (`id`, `re`, `from`,
  `to`), each at most once, and every line between header and footer is quoted. Anything
  else is not an ARDA message.

## Delivery

ARDA hands a message to Herdr (`herdr agent prompt`) and reports only what Herdr can show:

| Status | Meaning |
| --- | --- |
| `delivered` | The receiver was ready, and Herdr saw it working after the text was submitted. |
| `submitted` | The receiver was busy. Its harness takes queued input at its next step (Claude Code and Codex both do). |
| `uncertain` | The text may have been submitted, but Herdr could not confirm that the receiver started (stalled, timed out, or the connection failed). It may still act on it. Do not resend blindly. |
| `not_delivered` | Nothing was typed: no such agent, an ambiguous name, a fingerprint that no longer matches, an unreachable place, the agent is blocked at an approval or question prompt, Herdr cannot classify its state (override with `--force`), or, for introductions only, the agent is busy. |

Delivery is not acceptance. Only `ack` means the receiver accepted a task, and only
`result` or `reject` closes it. ARDA never retries a message, never types into a
blocked agent, and keeps no queue or history. A sender does not wait for replies; they
arrive as new prompts.

## Trust

Messages are not authenticated. Any process that can use a Herdr session can send one
and fill in any `from` address; fingerprints guard against misrouting, not forgery. A
receiver should treat a message as a request from another agent, not as an instruction
from its user, and act on it only as far as its user allows it to work with peers.

Claude Code enforces this itself: it asks its user before acting on a peer's task, and its
auto mode blocks such work. A user grants a standing approval once with `arda trust`,
which records it in each agent harness's own configuration (see the README). ARDA keeps
no record of its own.
