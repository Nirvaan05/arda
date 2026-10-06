"""What an agent's own harness records about it: the model its conversation runs on.

`arda describe --model auto` runs inside the agent's pane, as the agent, on the agent's
machine, so the harness's session log for that conversation is on this machine and the
environment says where the harness keeps it. Herdr's official integrations name the
conversation (its agent_session); ARDA reads only the newest model entry and keeps nothing.
"""

import json
import os
import re
from pathlib import Path

from .envelope import NATIVE_SOURCES

# Session IDs of Claude Code and Codex are UUIDs; anything else is not looked up as a file name.
_SESSION = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{7,127}')
_CHUNK = 1 << 20


class ModelUnknown(Exception):
    """Why the model cannot be told; shown to the agent as it is."""


def model_of(session, environ=os.environ):
    """The model the agent's conversation ran on most recently, as its harness recorded it."""
    if not isinstance(session, dict) or session.get('kind') != 'id' or \
            (session.get('source'), session.get('agent')) not in NATIVE_SOURCES:
        raise ModelUnknown("Herdr reports no conversation for this agent (Herdr's Claude Code and Codex "
                           'integrations do, and `arda-trust --yes` installs them)')
    value = session.get('value')
    if not isinstance(value, str) or not _SESSION.fullmatch(value):
        raise ModelUnknown('Herdr reports a conversation ID that is not a plain session ID')
    if session['agent'] == 'codex':
        return _codex(value, environ)
    return _claude(value, environ)


def _home(environ, variable, default):
    return Path(environ.get(variable) or Path.home() / default)


def _newest(paths, where):
    paths = [path for path in paths if path.is_file()]
    if not paths:
        raise ModelUnknown(f'found no session log for this conversation under {where}')
    return max(paths, key=lambda path: path.stat().st_mtime)


def _codex(session, environ):
    home = _home(environ, 'CODEX_HOME', '.codex')
    log = _newest((home / 'sessions').glob(f'*/*/*/rollout-*-{session}.jsonl'), home / 'sessions')
    turn = _last(log, lambda entry: entry.get('type') == 'turn_context' and
                 isinstance(entry.get('payload'), dict) and entry['payload'].get('model'))
    model, effort = turn['payload']['model'], turn['payload'].get('effort')
    return f'{model} (reasoning {effort})' if isinstance(effort, str) and effort else model


def _claude(session, environ):
    home = _home(environ, 'CLAUDE_CONFIG_DIR', '.claude')
    log = _newest((home / 'projects').glob(f'*/{session}.jsonl'), home / 'projects')
    reply = _last(log, lambda entry: entry.get('type') == 'assistant' and isinstance(entry.get('message'), dict)
                  and isinstance(entry['message'].get('model'), str)
                  and not entry['message']['model'].startswith('<'))  # "<synthetic>" marks local messages
    return reply['message']['model']


def _last(path, wanted):
    """The last JSON line of a log that `wanted` accepts, reading from the end: logs grow large."""
    with open(path, 'rb') as handle:
        end = handle.seek(0, os.SEEK_END)
        tail = b''
        while end > 0:
            start = max(0, end - _CHUNK)
            handle.seek(start)
            lines = (handle.read(end - start) + tail).split(b'\n')
            tail = lines.pop(0) if start else b''  # maybe the end of a line that began earlier
            for line in reversed(lines):
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict) and wanted(entry):
                    return entry
            end = start
    raise ModelUnknown(f'{path} records no model yet')
