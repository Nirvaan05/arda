"""The Herdr environment as ARDA sees it: places, and the agents in them.

A place is a Herdr server an agent can be reached through: a running Herdr
session on this machine (named by its session name) or a machine saved in
Herdr (named by its label). Herdr does all routing, with `herdr --session NAME`
for local sessions and `herdr --machine ID` for saved machines. ARDA keeps no
list of its own; it asks Herdr every time.
"""

import os
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .herdr import Herdr, HerdrError

_LABEL = re.compile(r'[a-z0-9][a-z0-9._-]{0,62}')


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

    @property
    def reachable(self):
        return self.error is None


def _label(text):
    text = (text or '').strip().lower()
    return text if _LABEL.fullmatch(text) else None


def discover(herdr):
    """The places of the caller's Herdr environment, current one first."""
    socket_path = os.environ.get('HERDR_SOCKET_PATH')
    host = socket.gethostname()
    places, names = [], set()
    try:
        sessions = herdr.local_json('session', 'list', '--json').get('sessions', [])
    except (HerdrError, AttributeError):
        sessions = []
    current_name = herdr.session
    for item in [] if herdr.session else sessions:
        if socket_path and item.get('socket_path') == socket_path:
            current_name = item['name']
    if current_name is None and not herdr.session and not socket_path:
        current_name = next((item['name'] for item in sessions if item.get('default')), 'default')
    places.append(Place(_label(current_name) or 'here', 'session', host, current_name or '?', herdr, current=True))
    names.add(places[0].name)
    for item in sessions:
        name = _label(item.get('name'))
        if item.get('running') and name and item.get('name') != current_name and name not in names:
            places.append(Place(name, 'session', host, item['name'], herdr.at(session=item['name'])))
            names.add(name)
    try:
        machines = herdr.local_json('machine', 'list', '--json')
    except HerdrError:
        machines = []
    for item in machines if isinstance(machines, list) else []:
        if not item.get('enabled', True) or not item.get('id'):
            continue
        name = _label(item.get('label'))
        if name is None or name in names:
            name = _label(item['id'])
        if name is None or name in names:
            continue
        places.append(Place(name, 'machine', item.get('label') or item['id'], item.get('session') or 'default',
                            herdr.at(machine=item['id'], label=item.get('label') or item['id'])))
        names.add(name)
    return places


def survey(places):
    """Fill in each place's agents (asked in parallel), or the error that made it unreachable."""
    def ask(place):
        try:
            place.agents = place.herdr.agents()
        except HerdrError as err:
            place.agents, place.error = [], f'{err.code}: {err.message}'
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
        from .envelope import fingerprint
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
        options = ', '.join(f'@{address.name}@{p.name}' for p, _ in matches)
        raise Unresolved(f'@{address.name} is ambiguous in this Herdr environment; use one of: {options}')
    return matches[0][0]
