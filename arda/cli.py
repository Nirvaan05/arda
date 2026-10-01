"""ARDA command line, run by an agent inside its Herdr pane to reach its peers."""

import argparse
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

from . import __version__
from .envelope import MAX_BODY, PROTOCOL, AddressError, Message, address, target
from .herdr import Herdr, HerdrError

ROOT = Path(__file__).resolve().parent.parent
CONFIRM_MS = 15000
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_UNCERTAIN = 0, 1, 2, 3


class UsageError(Exception):
    pass


def command():
    """How another agent should invoke ARDA in the reply instructions we send it."""
    script = ROOT / 'bin' / 'arda'
    found = shutil.which('arda')
    if found and Path(found).resolve() == script.resolve():
        return 'arda'
    return shlex.quote(str(script))


def identity(herdr):
    """Describe the calling pane's agent, or return None outside a Herdr pane."""
    pane = os.environ.get('HERDR_PANE_ID')
    if not pane:
        return None
    try:
        agent = herdr.agent(pane)
    except HerdrError as err:
        if err.code != 'agent_not_found':
            raise
        return {'address': pane, 'name': None, 'agent': None, 'pane_id': pane}
    name = agent.get('name')
    return {
        'address': address(name) if name else agent['pane_id'],
        'name': name,
        'agent': agent.get('agent'),
        'pane_id': agent['pane_id'],
    }


def require_identity(herdr):
    me = identity(herdr)
    if me is None:
        raise UsageError('not running inside a Herdr pane (HERDR_PANE_ID is not set); '
                         'ARDA messages are sent by agents from their own pane')
    return me


def deliver(herdr, message, force=False):
    """Hand a message to Herdr and report what is actually known about delivery."""
    route = target(message.recipient)
    to = message.recipient

    def outcome(status, detail, pane=None):
        return {'status': status, 'type': message.type, 'id': message.id, 're': message.re,
                'from': message.sender, 'to': to, 'pane_id': pane, 'detail': detail}

    try:
        agent = herdr.agent(route)
    except HerdrError as err:
        if err.code == 'agent_not_found':
            return outcome('not_delivered', f'no live agent {to} in this Herdr session')
        raise
    state, pane = agent.get('agent_status'), agent.get('pane_id')
    if state == 'blocked':
        return outcome('not_delivered', f'{to} is waiting at an approval or question prompt; '
                                        'ARDA does not type into it. Try again once it is unblocked.', pane)
    if state == 'unknown' and not force:
        return outcome('not_delivered', f'Herdr cannot tell whether {to} is ready (state: unknown). '
                                        'Try again later, or pass --force to submit anyway.', pane)
    text = message.render(command())
    try:
        if state == 'working':
            herdr.prompt(route, text)
            return outcome('submitted', f'{to} is busy; its harness hands it the message at its next step.', pane)
        herdr.prompt(route, text, confirm_ms=CONFIRM_MS)
        return outcome('delivered', f'{to} received it and started a turn.', pane)
    except HerdrError as err:
        if err.code in ('agent_prompt_stalled', 'timeout'):
            return outcome('uncertain', f'the text was submitted, but {to} was not seen starting work. '
                                        f'Do not resend blindly; inspect it with: herdr agent read {route}', pane)
        if err.code == 'agent_blocked':
            return outcome('not_delivered', f'{to} became blocked at a prompt before delivery.', pane)
        if err.code == 'agent_not_found':
            return outcome('not_delivered', f'{to} left the Herdr session before delivery.', pane)
        raise


def read_body(text, path):
    if path:
        text = Path(path).read_text()
    elif text == '-':
        text = sys.stdin.read()
    if not text or not text.strip():
        raise UsageError('message text is empty')
    if len(text) > MAX_BODY:
        raise UsageError(f'message is {len(text)} characters; the limit is {MAX_BODY}. '
                         'Write it to a file and send the file path instead.')
    return text


def send(herdr, args, kind, re=None):
    me = require_identity(herdr)
    to = address(target(args.to))
    if to == me['address'] or (me['name'] and to == address(me['name'])):
        raise UsageError('cannot send an ARDA message to yourself')
    body = read_body(getattr(args, 'text', None), getattr(args, 'file', None))
    message = Message(type=kind, sender=me['address'], recipient=to, body=body, re=re)
    return deliver(herdr, message, force=getattr(args, 'force', False))


def summary(result):
    line = f'{result["status"]}: {result["type"]} {result["id"]} to {result["to"]}: {result["detail"]}'
    if result['type'] == 'task_request' and result['status'] in ('delivered', 'submitted'):
        line += ('\nIts ack and its result (or reject) will arrive here as ARDA messages; '
                 'you do not need to wait or poll.')
    return line


def cmd_status(herdr, args):
    return {'plugin': 'arda', 'version': __version__, 'protocol': PROTOCOL}, None


def cmd_whoami(herdr, args):
    me = require_identity(herdr)
    kind = f' ({me["agent"]})' if me['agent'] else ''
    hint = '' if me['name'] else ('\nYou have no Herdr agent name, so peers can reach you only by pane ID. '
                                  f'Name yourself with: herdr agent rename {me["pane_id"]} <name>')
    return me, f'{me["address"]}{kind} at {me["pane_id"]}{hint}'


def cmd_peers(herdr, args):
    me = identity(herdr)
    peers = []
    for agent in herdr.agents():
        name = agent.get('name')
        peers.append({
            'address': address(name) if name else agent['pane_id'],
            'name': name,
            'agent': agent.get('agent'),
            'state': agent.get('agent_status'),
            'pane_id': agent['pane_id'],
            'you': bool(me and me['pane_id'] == agent['pane_id']),
        })
    if not peers:
        return peers, 'no agents in this Herdr session'
    rows = []
    for peer in peers:
        note = ' (you)' if peer['you'] else ('' if peer['name'] else ' (unnamed: address it by pane ID)')
        rows.append(f'{peer["address"]:<14} {peer["agent"] or "?":<10} {peer["state"] or "?":<8} '
                    f'{peer["pane_id"]}{note}')
    return peers, '\n'.join(rows)


def cmd_send(herdr, args):
    result = send(herdr, args, 'note')
    return result, summary(result)


def cmd_task(herdr, args):
    result = send(herdr, args, 'task_request')
    return result, summary(result)


def cmd_ack(herdr, args):
    if not args.text:
        args.text = 'Accepted.'
    result = send(herdr, args, 'ack', re=args.id)
    return result, summary(result)


def cmd_result(herdr, args):
    result = send(herdr, args, 'result', re=args.id)
    return result, summary(result)


def cmd_reject(herdr, args):
    result = send(herdr, args, 'reject', re=args.id)
    return result, summary(result)


def parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--json', action='store_true', help='print machine-readable JSON')
    common.add_argument('--session', help='Herdr session to use when not running inside a Herdr pane')

    def body(sub, required=True):
        sub.add_argument('text', nargs=None if required else '?',
                         help='message text, or - to read it from stdin')
        sub.add_argument('--file', help='read the message text from this file instead')

    root = argparse.ArgumentParser(
        prog='arda', description='ARDA: let the agents in a Herdr session address each other.')
    root.add_argument('--version', action='version', version=f'arda {__version__} ({PROTOCOL})')
    commands = root.add_subparsers(dest='command', required=True, metavar='command')

    commands.add_parser('status', parents=[common], help='show the plugin and protocol version')
    commands.add_parser('whoami', parents=[common], help='show your own ARDA address')
    commands.add_parser('peers', parents=[common], help='list the agents in this Herdr session')

    sub = commands.add_parser('send', parents=[common], help='send a note to another agent')
    sub.add_argument('to', help='recipient, e.g. @codex')
    body(sub, required=False)
    sub.add_argument('--force', action='store_true', help='submit even if Herdr cannot classify the recipient')

    sub = commands.add_parser('task', parents=[common], help='ask another agent to do work')
    sub.add_argument('to', help='recipient, e.g. @codex')
    body(sub, required=False)
    sub.add_argument('--force', action='store_true', help='submit even if Herdr cannot classify the recipient')

    sub = commands.add_parser('ack', parents=[common], help='accept a task you were sent')
    sub.add_argument('to', help='the agent that sent the task')
    sub.add_argument('id', help='id of the task being accepted')
    sub.add_argument('text', nargs='?', help='optional short note')

    for name, what in (('result', 'return the result of a task'), ('reject', 'decline or abandon a task')):
        sub = commands.add_parser(name, parents=[common], help=what)
        sub.add_argument('to', help='the agent that sent the task')
        sub.add_argument('id', help='id of the task being answered')
        body(sub, required=False)

    return root


HANDLERS = {
    'status': cmd_status, 'whoami': cmd_whoami, 'peers': cmd_peers, 'send': cmd_send,
    'task': cmd_task, 'ack': cmd_ack, 'result': cmd_result, 'reject': cmd_reject,
}
EXIT_FOR_STATUS = {'delivered': EXIT_OK, 'submitted': EXIT_OK, 'uncertain': EXIT_UNCERTAIN,
                   'not_delivered': EXIT_FAILED}


def main(argv=None):
    args = parser().parse_args(argv)
    herdr = Herdr(session=args.session)
    try:
        data, text = HANDLERS[args.command](herdr, args)
    except (UsageError, AddressError, OSError) as err:
        print(f'arda: {err}', file=sys.stderr)
        return EXIT_USAGE
    except HerdrError as err:
        print(f'arda: herdr: {err}', file=sys.stderr)
        return EXIT_FAILED
    if args.json or text is None:
        print(json.dumps(data))
    else:
        print(text)
    return EXIT_FOR_STATUS.get(data.get('status'), EXIT_OK) if isinstance(data, dict) else EXIT_OK
