"""Thin client for the installed `herdr` CLI.

ARDA does not speak Herdr's socket protocol itself. The CLI is Herdr's public
interface, and inside a Herdr pane it already targets the caller's session.
"""

import contextlib
import json
import re
import subprocess

from . import system

# How Herdr 0.9.3 reports a saved machine it cannot use, most specific first. Each of
# these happens before a request reaches the machine's Herdr server, so nothing was sent.
_NOT_REACHED = (
    ('failed to connect to remote Herdr API socket', 'server_not_running',
     'is reachable, but its Herdr session is not running'),
    (re.compile(r'Permission denied \((publickey|password|keyboard|hostbased|gssapi)|Host key verification failed|'
                r'REMOTE HOST IDENTIFICATION HAS CHANGED'), 'machine_auth',
     'refused the SSH login; run `herdr machine reconnect {label}` in a terminal'),
    (re.compile(r'Could not resolve hostname|Connection refused|Connection timed out|No route to host|'
                r'Network is unreachable|remote platform detection failed|remote binary discovery failed'),
     'machine_unreachable', 'cannot be reached'),
)
# Any other broken SSH connection may have dropped after a request was sent.
_CONNECTION_LOST = ('remote SSH connection failed', 'ssh bridge exited')
# OpenSSH refusing one more channel on a shared connection (sshd MaxSessions); nothing was sent.
_CHANNEL_REFUSED = ('open failed', 'Session open refused')


# Bound every call, so one machine that hangs cannot stall a send for long. Herdr on
# this machine answers in milliseconds; a saved machine gets longer than Herdr's own
# 10 s SSH connect timeout, so Herdr's reason is reported rather than ours. At worst a
# send makes five lookups here (two listings, two identity checks, the survey of this
# machine's sessions), two on saved machines (their survey, the agent) and one prompt:
# 5 x 5 s + 2 x 15 s + 20 s + the 15 s confirmation, under the two minutes agent
# harnesses typically allow a command.
LOOKUP_TIMEOUT = 5
MACHINE_TIMEOUT = 15
PROMPT_TIMEOUT = 20


def _run(argv, timeout):
    """Run a herdr command. If it overruns or is interrupted, stop it and every process it
    started, such as the ssh of a saved machine, rather than leaving them behind."""
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8',
                            errors='replace', **system.POPEN)
    try:
        out, err = proc.communicate(timeout=timeout)
    except BaseException:
        system.kill_tree(proc)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.communicate(timeout=2)
        raise
    return proc.returncode, out, err


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
        self.binary = binary or 'herdr'  # callers pass a trusted path (arda.cli.herdr_binary), never the environment's
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

    def local_json(self, *args, timeout=None):
        """Run a client-side command that prints plain JSON (session and machine listings)."""
        try:
            code, out, err = _run([self.binary, *args], timeout or LOOKUP_TIMEOUT)
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            raise HerdrError('herdr_failed', str(error)) from None
        reply = _json(out)
        if code != 0 or reply is None:
            raise HerdrError('herdr_failed', (err or out).strip()[:300] or f'exit {code}')
        return reply

    def call(self, *args, timeout=60, silent=False):
        """Run herdr and return its result; `silent` commands print nothing when they succeed."""
        argv = self._argv(args)
        try:
            code, out, err = _run(argv, timeout)
        except FileNotFoundError:
            raise HerdrError('herdr_not_found', f'cannot run {self.binary!r}; is Herdr installed?') from None
        except subprocess.TimeoutExpired:
            raise HerdrError('timeout', f'herdr did not answer within {timeout}s') from None
        reply = _json(out) or _json(err)
        if isinstance(reply, dict) and 'error' in reply:
            error = reply['error']
            raise HerdrError(error.get('code', 'herdr_error'), error.get('message', ''))
        if code == 0 and isinstance(reply, dict) and 'result' in reply:
            return reply['result']
        if code == 0 and silent and not (out + err).strip():
            return {}
        detail = (err or out).strip() or f'exit status {code}'
        if self.machine:
            self._machine_failure(detail)
        if 'Operation not permitted' in detail or 'PermissionDenied' in detail:
            raise HerdrError('socket_denied', 'the Herdr socket cannot be reached from here ("Operation not '
                             'permitted"); the agent\'s sandbox probably blocks it. Ask the user to let arda run '
                             'outside the sandbox (see `arda trust`).')
        raise HerdrError('herdr_failed', detail)

    def _machine_failure(self, detail):
        for sign, code, text in _NOT_REACHED:
            if (sign in detail) if isinstance(sign, str) else sign.search(detail):
                raise HerdrError(code, f'saved machine {self.label} {text.format(label=self.label)}: {detail[:300]}')
        if any(sign in detail for sign in _CHANNEL_REFUSED):
            raise HerdrError('channel_refused', f'saved machine {self.label} refused another SSH channel: '
                                                f'{detail[:300]}')
        if any(sign in detail for sign in _CONNECTION_LOST):
            raise HerdrError('connection_lost', f'the SSH connection to saved machine {self.label} failed: '
                                                f'{detail[:300]}')

    def lookup(self, *args, limit=None):
        """A read-only call: bounded for the place it goes to (and by `limit`, what is left of a
        larger budget), tried once more if a saved machine refused the SSH channel, since
        nothing was sent then."""
        timeout = MACHINE_TIMEOUT if self.machine else LOOKUP_TIMEOUT
        if limit is not None:
            timeout = max(0.5, min(timeout, limit))
        try:
            return self.call(*args, timeout=timeout)
        except HerdrError as err:
            if err.code != 'channel_refused':
                raise
        return self.call(*args, timeout=timeout)

    def agents(self, limit=None):
        agents = _field(self.lookup('agent', 'list', limit=limit), 'agents', list)
        for agent in agents:
            _field(agent, 'pane_id', str)
        return agents

    def agent(self, target):
        agent = _field(self.lookup('agent', 'get', target), 'agent', dict)
        _field(agent, 'pane_id', str)
        return agent

    def pane_shell_pid(self, pane):
        info = _field(self.lookup('pane', 'process-info', '--pane', pane), 'process_info', dict)
        return _field(info, 'shell_pid', int)

    def report_metadata(self, pane, tokens=None, clear=()):
        """Set or clear Herdr metadata tokens on a pane (Herdr owns them; values are at most 80 characters)."""
        args = ['pane', 'report-metadata', pane, '--source', 'arda']
        for key, value in (tokens or {}).items():
            args += ['--token', f'{key}={value}']
        for key in clear:
            args += ['--clear-token', key]
        return self.call(*args, timeout=LOOKUP_TIMEOUT, silent=True)

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
