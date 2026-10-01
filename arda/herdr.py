"""Thin client for the installed `herdr` CLI.

ARDA does not speak Herdr's socket protocol itself. The CLI is Herdr's public
interface, and inside a Herdr pane it already targets the caller's session.
"""

import json
import os
import subprocess


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


class Herdr:
    def __init__(self, binary=None, session=None):
        self.binary = binary or os.environ.get('HERDR_BIN_PATH') or 'herdr'
        self.session = session

    def call(self, *args, timeout=60):
        argv = [self.binary]
        if self.session:
            argv += ['--session', self.session]
        argv += [str(arg) for arg in args]
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
        raise HerdrError('herdr_failed', detail)

    def agents(self):
        return self.call('agent', 'list')['agents']

    def agent(self, target):
        return self.call('agent', 'get', target)['agent']

    def prompt(self, target, text, confirm_ms=None):
        """Submit text to an agent as one prompt.

        With confirm_ms, also wait until the receiver is observed working (or
        blocked) after the submission, which is the strongest delivery evidence
        Herdr offers short of the receiver replying.
        """
        args = ['agent', 'prompt', target, text]
        timeout = 60
        if confirm_ms:
            args += ['--wait', '--until', 'working', '--until', 'blocked', '--timeout', confirm_ms]
            timeout += confirm_ms / 1000
        return self.call(*args, timeout=timeout)
