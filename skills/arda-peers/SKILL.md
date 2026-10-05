---
name: arda-peers
description: List the agents in this Herdr environment that ARDA can reach (every Herdr session on this machine and every saved machine), with their state, working directory and what each says it does. User-invoked only.
disable-model-invocation: true
---

# ARDA peers

Run `arda peers` and show the user its output as it is, in a code block so the columns
stay aligned. It only reads; it sends nothing.

If `arda` is not on PATH, use the plugin's copy:

```bash
herdr plugin list --plugin arda --json   # bin/arda under .plugin_root
```

Keep the output's own labels: a place that did not answer says why, and the Role, Tools
and Model lines are each agent's own description, not verified. Do not message any peer
as part of this command.
