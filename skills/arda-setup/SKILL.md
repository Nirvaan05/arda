---
name: arda-setup
description: Show whether ARDA peer messaging is approved and how the user approves it. User-invoked only.
disable-model-invocation: true
---

# ARDA setup

Run `arda setup` (it only reads; it changes nothing) and show the user its output as it is.

If ARDA is not approved yet, tell the user to run the command it prints themselves, in a
plain terminal or a plain shell pane in Herdr. Do not run `arda-trust` yourself, do not try
another way to run it, and do not type it into another pane: approving ARDA is the user's
decision, and the command refuses agents.
