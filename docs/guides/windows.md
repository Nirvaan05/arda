# Using ARDA on Windows

> **Status: VERIFIED.** Claude Code and Codex hand work to each other live in one Herdr
> session on native Windows (Herdr 0.9.3, Codex 0.160).

ARDA runs on Herdr's native Windows build. It behaves as on Linux; only the install and
Codex's setup differ.

## Install

You need Python 3.11+ from python.org (it includes the `py` launcher and pip). In PowerShell:

```powershell
herdr plugin install Nirvaan05/arda
$root = (herdr plugin list --plugin arda --json | ConvertFrom-Json).result.plugins[0].plugin_root
py -I "$root\bin\arda-trust.py" --yes
```

Then add `$root\bin` to your PATH.

`arda-trust.py --yes` also writes `$root\bin\arda.exe`, the `arda` command. It runs ARDA with
the Python that ran `arda-trust.py`. Run it again after moving the plugin or changing Python.

The plugin actions have a `-windows` suffix, because Herdr needs a unique id for each action:

```powershell
herdr plugin action invoke introduce-windows --plugin arda
```

`setup-windows` and `status-windows` work the same way.

## Codex

On Windows, Codex needs two things beyond the [Codex guide](codex.md):

| Step | Why |
| --- | --- |
| Start it with `codex --no-daemon -c shell_environment_policy.inherit=all` | Codex's commands do not get the pane's environment otherwise, and ARDA cannot tell which pane is calling |
| Approve `arda` outside the sandbox the first time Codex asks | Codex's sandbox runs commands as a separate user that cannot reach Herdr; the rule that allows `arda` skips the prompt but keeps the command in the sandbox |

## Claude Code

Claude Code needs nothing extra. Its Bash tool runs `arda` from Git Bash.

## Development

Run the tests with `python -X utf8 -m unittest discover -s tests -v`.
