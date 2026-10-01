"""The ARDA message envelope.

A message travels as the text of a single Herdr agent prompt: one header line,
the body, and footer lines that tell the receiving agent how to answer through
ARDA. Everything a reply needs (who to answer, which message it answers) is in
the text the receiver already has, so ARDA keeps no state between messages.
"""

import re
import secrets
from dataclasses import dataclass, field

PROTOCOL = 'arda/1'
TYPES = ('note', 'task_request', 'ack', 'result', 'reject')
REPLY_TYPES = ('ack', 'result', 'reject')
FOOTER = '[arda] '
MAX_BODY = 32000

_NAME = re.compile(r'^[a-z][a-z0-9_-]{0,31}$')
_PANE = re.compile(r'^w\d+:p\d+$')
_HEADER = re.compile(r'^\[arda/1 (?P<type>[a-z_]+)(?P<fields>(?: [a-z]+=\S+)*)\]$')
# Herdr types prompts into a terminal (inside bracketed paste when the agent
# enables it), so a body must not carry escape sequences or other controls.
_CONTROL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f-\x9f]')


class AddressError(ValueError):
    pass


def clean(text):
    """Drop terminal control characters, keeping newlines and tabs."""
    return _CONTROL.sub('', text.replace('\r\n', '\n'))


def new_id():
    return secrets.token_hex(3)


def target(address):
    """Return the Herdr target for an address: `@codex`, `codex` or a pane ID."""
    value = address.strip()
    if _PANE.match(value):
        return value
    name = value.removeprefix('@')
    if not _NAME.match(name):
        raise AddressError(f'not an agent address: {address!r} (expected @name or a pane ID such as w1:p2)')
    return name


def address(name_or_pane):
    return name_or_pane if _PANE.match(name_or_pane) else f'@{name_or_pane}'


@dataclass(frozen=True)
class Message:
    type: str
    sender: str
    recipient: str
    body: str
    re: str | None = None
    id: str = field(default_factory=new_id)

    def __post_init__(self):
        if self.type not in TYPES:
            raise ValueError(f'unknown message type: {self.type}')
        if (self.type in REPLY_TYPES) != (self.re is not None):
            raise ValueError(f'{self.type} messages {"need" if self.type in REPLY_TYPES else "cannot have"} re=')

    def header(self):
        fields = [f'id={self.id}']
        if self.re:
            fields.append(f're={self.re}')
        fields += [f'from={self.sender}', f'to={self.recipient}']
        return f'[{PROTOCOL} {self.type} {" ".join(fields)}]'

    def render(self, command='arda'):
        lines = [self.header(), clean(self.body).strip()]
        lines += [FOOTER + line for line in _footer(self, command)]
        return '\n'.join(lines)


def _footer(message, cmd):
    sender, me, ref = message.sender, message.recipient, message.re
    if message.type == 'task_request':
        return [
            f'You are {me}. {sender} asked you to do this task and cannot see your chat, so answer only through ARDA:',
            f'  accept it now:  {cmd} ack {sender} {message.id}',
            f'  when finished:  {cmd} result {sender} {message.id} "<result>"   (long result: --file PATH)',
            f'  if you will not or cannot do it:  {cmd} reject {sender} {message.id} "<reason>"',
        ]
    if message.type == 'note':
        return [f'Note for you ({me}) from {sender}. No reply needed. To answer: {cmd} send {sender} "<text>"']
    if message.type == 'ack':
        return [f'{sender} accepted task {ref}. Its result will arrive as another ARDA message. No reply needed.']
    if message.type == 'result':
        return [f'{sender} finished task {ref}. No reply needed.']
    return [f'{sender} will not complete task {ref}. No reply needed.']


def parse(text):
    """Parse a rendered message. Returns None if the text is not an ARDA message."""
    lines = text.strip('\n').split('\n')
    match = _HEADER.match(lines[0]) if lines else None
    if not match or match['type'] not in TYPES:
        return None
    fields = dict(item.split('=', 1) for item in match['fields'].split())
    body = lines[1:]
    while body and body[-1].startswith(FOOTER):
        body.pop()
    try:
        return Message(
            type=match['type'], sender=fields['from'], recipient=fields['to'],
            body='\n'.join(body), re=fields.get('re'), id=fields['id'],
        )
    except (KeyError, ValueError):
        return None
