# Troubleshooting

> **Symptom, cause, fix.** Find the message you see, then follow the fix. If nothing here
> matches, run `arda setup` and `arda peers` and read what they report.

## ARDA refuses to run

| You see | Cause | Fix |
| --- | --- | --- |
| `not running inside a Herdr pane (HERDR_PANE_ID is not set)` | Messages are sent by agents from their own pane | Run it from the agent's pane. To list agents from outside Herdr: `arda peers --session <name>` |
| `HERDR_PANE_ID says w1:p2, but this command is not running inside that pane` | The harness runs commands outside its pane (Codex's shared background server), or a sandbox hides the pane's processes | Start Codex with `--no-daemon` ([Codex guide](guides/codex.md)) |
| `the Herdr socket cannot be reached from here ("Operation not permitted")` | The agent's sandbox blocks the Herdr socket | Run `arda-trust --yes` yourself, or approve the command when the agent asks |
| `cannot find herdr in ~/.local/bin, /usr/local/bin or /usr/bin` | ARDA runs outside Herdr and Herdr is installed elsewhere | Run ARDA from a Herdr pane, or install Herdr in one of those places |
| `the agent name 'arda' is reserved for ARDA itself` | `@arda` is used for messages from ARDA itself | Rename the agent: `herdr agent rename <pane> <name>` |
| `arda-trust must be run by the user in a terminal, not by an agent` | `arda-trust` refuses to run inside an agent's pane | Run it yourself in a plain terminal or a plain shell pane |

## A message was not sent

| You see | Cause | Fix |
| --- | --- | --- |
| `not_delivered` and the name runs in two places | ARDA never guesses between agents with the same name | Add the place: `@reviewer@desktop` (`arda peers` shows the choices) |
| `not_delivered` and a place did not answer | A name can be shown unique only when every place answers | Add the place, or `herdr machine disable <machine>` while it is offline |
| `not_delivered` with "Agents now: …" | The agent was renamed | Use a current name from the list |
| `not_delivered`: the agent is blocked | It is waiting at an approval or question prompt; ARDA never types into one | Answer the prompt in that pane, then send again |
| `not_delivered`: state unknown | Herdr cannot classify the agent's state | Check the pane; if it is ready, send again with `--force` |
| `uncertain` (exit 3) | The text may have arrived but Herdr could not confirm the agent started | Do not resend blindly: check `arda peers`, then ask with `arda send <to> --re <id> -- 'Did you get task <id>?'` |
| `cannot send an ARDA message to yourself` | The address resolves to your own pane | Check the name with `arda peers` |
| `message is … bytes; the limit is 32000` | The body is too long | Write it to a file and send the path, or use `--file` |
| `--file must be in the working directory … or in /tmp` | `--file` reads only visible files there | Move the file, or send its path in the text |

## A message arrived in the wrong place

| You see | Cause | Fix |
| --- | --- | --- |
| A Codex agent never answered after the integration was installed | Codex shows a **Hooks** review dialog once; Herdr does not see it as blocked, and the message was typed into it | Approve the hook in the Codex pane, then send again |
| A Claude Code agent shows the message inside a tips dialog | Herdr 0.9.3 does not always see Claude Code's end-of-turn dialogs as blocked | Close the dialog, then send again |

## Agents and descriptions

| You see | Cause | Fix |
| --- | --- | --- |
| `arda peers` shows no Role, Tools or Model | The agent has not described itself, or Herdr restarted (descriptions are not kept) | Ask the agent to run `arda describe --role '…' --tools '…' --model auto` |
| A model like "GPT-6 family" instead of the exact model | The agent guessed | `arda describe --model auto` reads the exact model from its session log |
| `--model auto cannot tell this agent's model: Herdr reports no conversation for this agent` | Herdr's integration for that harness is not installed or not trusted yet | `arda-trust --yes` installs it; or give the model: `--model '<model>'` |
| Replies to messages sent before a Herdr restart are refused | Without Herdr's integrations, the sender's terminal is gone after a restart | Install the integrations (`arda-trust --yes`) so agents and their conversations come back |
| `/list-agents` in Claude Code shows no other agents | It lists only Claude Code sessions | Use `/arda-peers` |
| `/arda-peers` is unrecognized in Codex | Codex has no custom slash commands | Type `$arda-peers`, or pick it from `/skills` |

## Saved machines

| You see | Cause | Fix |
| --- | --- | --- |
| `unreachable: machine_unreachable` | The machine cannot be reached over SSH | Check the network, or disable the machine while it is offline |
| `unreachable: server_not_running` | Herdr is not running there | Start Herdr on that machine |
| `unreachable: machine_auth` | SSH login refused | `herdr machine reconnect <machine>` in a terminal |
| The receiver cannot reply | Its machine has no saved machine pointing back | Save the sender's machine on the receiver's side ([multi-machine guide](guides/multi-machine.md)) |

## Development

| You see | Cause | Fix |
| --- | --- | --- |
| `herdr plugin install` refuses while developing | A plugin with the same id is linked | `herdr plugin unlink arda` first |
