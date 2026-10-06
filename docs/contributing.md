# Contributing

> **Working on ARDA itself.** Coding agents: start with [AGENTS.md](../AGENTS.md).

## Set up a development copy

Link a clone instead of installing ARDA from GitHub:

```sh
herdr plugin link "$PWD"
ln -s "$PWD/bin/arda" "$PWD/bin/arda-trust" ~/.local/bin/
```

Herdr refuses to install a plugin from GitHub while one with the same id is linked; run
`herdr plugin unlink arda` first.

## Test and lint

```sh
python3 -m unittest discover -s tests -v
ruff check arda tests
```

| Rule | Why |
| --- | --- |
| Tests never reach a real Herdr server | They drive the CLI against `tests/fake_herdr.py`; `tests/isolation.py` removes `HERDR_*` variables first. A test that typed into a real agent would message a live agent. |
| Python standard library only | ARDA has no dependencies, so it runs wherever Herdr and `python3` do. |
| Python 3.11 or later, Linux | The supported platform. |
| No state | ARDA keeps no files, queue or service; it asks Herdr every time. |

Live behavior is verified separately, in named Herdr sessions with real Claude Code and
Codex agents.

## Changes

- Keep commits small, with a message that says what changed and why.
- Update the docs in the same change when behavior changes: the [CLI reference](reference/cli.md)
  for commands, the [protocol](protocol.md) for messages and delivery.
- Mark support honestly: VERIFIED, EXPERIMENTAL, ILLUSTRATIVE or FUTURE (see the
  [docs index](README.md#status-labels)).
- Footer and skill text steer every receiving agent. Change them with care, and check the
  change with real agents.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](../LICENSE).
