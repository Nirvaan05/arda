"""Thin client for the installed `herdr` CLI.

ARDA does not speak Herdr's socket protocol itself. The CLI is Herdr's public
interface, and inside a Herdr pane it already targets the caller's session.
"""

import json
import os
import subprocess

# Herdr 0.9.3 `--machine` failures raised while probing the machine, before a request is sent.
_UNREACHABLE = ('remote SSH connection failed', 'remote platform detection failed', 'remote binary discovery failed',
                'failed to connect to remote Herdr API socket', 'Connection refused', 'Could not resolve hostname')


# Bound every call, so one machine that hangs cannot stall a send for long. A whole
# send stays well under the two minutes agent harnesses typically allow a command.
LOOKUP_TIMEOUT = 15
PROMPT_TIMEOUT = 20


class HerdrError(Exception):
    """A Herdr request failed. `code` is Herdr's error code when it gave one."""

    def __init__(self, code, message):
        super().__init__(f'{code}: {message}')
        self.code = code
        self.message = message


def _json(text):
    try:
        return json.loads(text)
    except ValueError:
        return None


def _field(container, key, kind):
    value = container.get(key) if isinstance(container, dict) else None
    if not isinstance(value, kind):
        raise HerdrError('unexpected_reply', f'herdr reply has no {key!r}: {str(container)[:200]}')
    return value


class Herdr:
    """One Herdr server: the caller's own, a named local session, or a saved machine."""

    def __init__(self, binary=None, session=None, machine=None, label=None):
        self.binary = binary or os.environ.get('HERDR_BIN_PATH') or 'herdr'
        self.session = session
        self.machine = machine
        self.label = label or machine

    def at(self, session=None, machine=None, label=None):
        return Herdr(self.binary, session=session, machine=machine, label=label)

    def _argv(self, args):
        argv = [self.binary]
        if self.machine:
            argv += ['--machine', self.machine]
        elif self.session:
            argv += ['--session', self.session]
        return argv + [str(arg) for arg in args]

    def local_json(self, *args, timeout=30):
        """Run a client-side command that prints plain JSON (session and machine listings)."""
        try:
            proc = subprocess.run([self.binary, *args], capture_output=True, text=True, timeout=timeout, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired) as err:
            raise HerdrError('herdr_failed', str(err)) from None
        reply = _json(proc.stdout)
        if proc.returncode != 0 or reply is None:
            raise HerdrError('herdr_failed', (proc.stderr or proc.stdout).strip()[:300] or f'exit {proc.returncode}')
        return reply

    def call(self, *args, timeout=60):
        argv = self._argv(args)
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        except FileNotFoundError:
            raise HerdrError('herdr_not_found', f'cannot run {self.binary!r}; is Herdr installed?') from None
        except subprocess.TimeoutExpired:
            raise HerdrError('timeout', f'herdr did not answer within {timeout}s') from None
        reply = _json(proc.stdout) or _json(proc.stderr)
        if isinstance(reply, dict) and 'error' in reply:
            error = reply['error']
            raise HerdrError(error.get('code', 'herdr_error'), error.get('message', ''))
        if proc.returncode == 0 and isinstance(reply, dict) and 'result' in reply:
            return reply['result']
        detail = (proc.stderr or proc.stdout).strip() or f'exit status {proc.returncode}'
        if self.machine and any(sign in detail for sign in _UNREACHABLE):
            raise HerdrError('machine_unreachable', f'saved machine {self.label} cannot be reached: {detail[:300]}')
        if 'Operation not permitted' in detail or 'PermissionDenied' in detail:
            raise HerdrError('socket_denied', 'the Herdr socket cannot be reached from here ("Operation not '
                             'permitted"); the agent\'s sandbox probably blocks it. Ask the user to let arda run '
                             'outside the sandbox (see `arda trust`).')
        raise HerdrError('herdr_failed', detail)

    def agents(self):
        agents = _field(self.call('agent', 'list', timeout=LOOKUP_TIMEOUT), 'agents', list)
        for agent in agents:
            _field(agent, 'pane_id', str)
        return agents

    def agent(self, target):
        agent = _field(self.call('agent', 'get', target, timeout=LOOKUP_TIMEOUT), 'agent', dict)
        _field(agent, 'pane_id', str)
        return agent

    def pane_shell_pid(self, pane):
        info = _field(self.call('pane', 'process-info', '--pane', pane, timeout=LOOKUP_TIMEOUT), 'process_info', dict)
        return _field(info, 'shell_pid', int)

    def prompt(self, target, text, confirm_ms=None):
        """Submit text to an agent as one prompt.

        With confirm_ms, also wait until the receiver is observed working (or
        blocked) after the submission, which is the strongest delivery evidence
        Herdr offers short of the receiver replying.
        """
        args = ['agent', 'prompt', target, text]
        timeout = PROMPT_TIMEOUT
        if confirm_ms:
            args += ['--wait', '--until', 'working', '--until', 'blocked', '--timeout', confirm_ms]
            timeout += confirm_ms / 1000
        return self.call(*args, timeout=timeout)
