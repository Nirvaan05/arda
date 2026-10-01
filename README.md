# ARDA

**One plugin to rule them all.**

Development environments traditionally organize resources around people: a person owns a machine, opens a session, and carries its context. With several agents working in parallel, those resources become shared. Resources should serve the work, and work should continue beyond the person who started it.

Agents in that environment need a shared language. The human often relays a request from Claude to Codex and carries the answer back. ARDA is a thin [Herdr](https://herdr.dev) plugin for cross-agent communication and work handoffs.

Herdr provides discovery, identity, machine routing, agent state, delivery and waiting. ARDA's focus is the communication protocol; agents retain their own context and memory.

## Status

ARDA is in early development. The current plugin provides a `status` action only. Cross-agent messaging is not yet available.

## Install locally

Requires Linux, Python 3.11+ and Herdr 0.9.0 or later. From the repository directory:

```sh
herdr plugin link "$PWD"
herdr plugin action invoke arda.status
```

Run the action in your intended Herdr session. To unlink the plugin:

```sh
herdr plugin unlink arda
```

## Development

Run the available tests and inspect the status command:

```sh
python3 -m unittest discover -s tests -v
python3 -m arda status
```

ARDA is Herdr-only. It does not provide a separate service, runtime or network transport.
