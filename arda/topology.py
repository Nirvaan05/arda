"""The Herdr environment as ARDA sees it: places, and the agents in them.

A place is a Herdr server an agent can be reached through: a running Herdr
session on this machine (named by its session name) or a machine saved in
Herdr (named by its label). Herdr does all routing, with `herdr --session NAME`
for local sessions and `herdr --machine ID` for saved machines. ARDA keeps no
list of its own; it asks Herdr every time.
"""

import hashlib
import os
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .envelope import Address, fingerprint
from .herdr import Herdr, HerdrError


@dataclass
class Place:
    name: str
    kind: str          # 'session' (on this machine) or 'machine' (a saved Herdr machine)
    machine: str       # this machine's hostname, or the saved machine's label
    session: str
    herdr: Herdr
    current: bool = False
    agents: list = field(default_factory=list)
    error: str | None = None
    failure: HerdrError | None = None

    @property
    def reachable(self):
        return self.error is None


def _label(text, taken, fallback):
    """An address-safe, unique place name for a Herdr session name or machine label.

    Names that are not valid place names are rewritten, and a name that is
    already taken gets a short suffix from `fallback`, so no place is ever dropped.
    """
    base = re.sub(r'[^a-z0-9._-]+', '-', (text or '').strip().lower()).strip('-._')[:40] or 'place'
    if not base[0].isalnum():
        base = 'p' + base
    name = base
    if name in taken:
        name = f'{base}-{hashlib.sha1(fallback.encode()).hexdigest()[:6]}'
    taken.add(name)
    return name


def _same_socket(a, b):
    return bool(a and b) and os.path.realpath(a) == os.path.realpath(b)


def discover(herdr):
    """The places of the caller's Herdr environment, current one first."""
    socket_path = os.environ.get('HERDR_SOCKET_PATH')
    host = socket.gethostname()
    taken = set()
    try:
        sessions = herdr.local_json('session', 'list', '--json').get('sessions', [])
    except (HerdrError, AttributeError):
        sessions = []
    current = None
    if herdr.session:
        current = next((item for item in sessions if item.get('name') == herdr.session), {'name': herdr.session})
    elif socket_path:
        current = next((item for item in sessions if _same_socket(item.get('socket_path'), socket_path)), None)
    else:
        current = next((item for item in sessions if item.get('default')), None)
    current_name = (current or {}).get('name')
    places = [Place(_label(current_name or 'here', taken, current_name or 'here'), 'session', host,
                    current_name or '?', herdr, current=True)]
    for item in sessions:
        if item is current or not item.get('running') or not item.get('name'):
            continue
        if item.get('name') == current_name or _same_socket(item.get('socket_path'), socket_path):
            continue  # the caller's own server, however it is reached
        places.append(Place(_label(item['name'], taken, item['name']), 'session', host, item['name'],
                            herdr.at(session=item['name'])))
    try:
        machines = herdr.local_json('machine', 'list', '--json')
    except HerdrError:
        machines = []
    for item in machines if isinstance(machines, list) else []:
        if not item.get('enabled', True) or not item.get('id'):
            continue
        label = item.get('label') or item['id']
        places.append(Place(_label(label, taken, item['id']), 'machine', label, item.get('session') or 'default',
                            herdr.at(machine=item['id'], label=label)))
    return places


def survey(places):
    """Fill in each place's agents (asked in parallel), or the error that made it unreachable."""
    def ask(place):
        try:
            place.agents = place.herdr.agents()
        except HerdrError as err:
            place.agents, place.error, place.failure = [], f'{err.code}: {err.message}', err
    with ThreadPoolExecutor(max_workers=max(1, len(places))) as pool:
        list(pool.map(ask, places))
    return places


class Unresolved(Exception):
    pass


def resolve(address, places):
    """Find the place and Herdr target for an address. Never guesses between agents with the same name."""
    current = places[0]
    if address.place:
        place = next((p for p in places if p.name == address.place), None)
        if place is None:
            known = ', '.join(p.name for p in places)
            raise Unresolved(f'no place called {address.place!r} in this Herdr environment (places: {known})')
        if address.name is None:
            return place
        survey([place])
        if not place.reachable:
            raise Unresolved(f'{place.name} is unreachable, so nothing was sent ({place.error})')
        candidates = [place]
    elif address.name is None:
        return current  # a bare pane ID is a route in the caller's own Herdr server
    else:
        candidates = places
    survey([p for p in candidates if not p.agents and p.error is None])
    matches = [(p, a) for p in candidates for a in p.agents if a.get('name') == address.name]
    if address.fingerprint:
        matches = [(p, a) for p, a in matches if fingerprint(a.get('terminal_id')) == address.fingerprint]
    unreachable = [p.name for p in candidates if not p.reachable]
    if not matches:
        detail = f'no live agent {address} in this Herdr environment'
        if address.fingerprint:
            detail = (f'no live agent {address}: the agent that sent the message is gone, or now runs in a '
                      'different terminal')
        if unreachable:
            detail += f' (unreachable: {", ".join(unreachable)})'
        raise Unresolved(detail)
    if len(matches) > 1:
        options = ', '.join(str(Address(address.name, p.name, address.fingerprint)) for p, _ in matches)
        raise Unresolved(f'@{address.name} is ambiguous in this Herdr environment; use one of: {options}')
    return matches[0][0]
