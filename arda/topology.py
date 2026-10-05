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
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .envelope import Address, fingerprint
from .herdr import Herdr, HerdrError

# One invocation's whole survey: places not asked or not answered by then are reported so
# (reason "budget"), and an answer that needed them is refused rather than guessed.
SURVEY_BUDGET = 30.0
MAX_IN_FLIGHT = 8   # Herdr calls at a time per invocation; one at a time per SSH target


@dataclass
class Place:
    name: str
    kind: str          # 'session' (on this machine) or 'machine' (a saved Herdr machine)
    machine: str       # this machine's hostname, or the saved machine's label
    session: str
    herdr: Herdr
    current: bool = False
    agents: list = field(default_factory=list)
    target: str | None = None    # a saved machine's SSH target: calls to one target run one at a time
    asked: bool = False
    error: str | None = None
    failure: HerdrError | None = None
    skipped: str | None = None    # why the place was not asked
    observed_at: int | None = None  # unix ms of its answer or failure

    @property
    def answered(self):
        return self.asked and self.error is None

    @property
    def reachable(self):
        return self.error is None and self.skipped is None


class Places(list):
    """The places of one environment, plus the discovery calls that failed while finding them."""

    def __init__(self, places, discovery_errors=()):
        super().__init__(places)
        self.discovery_errors = list(discovery_errors)

    @property
    def domain_known(self):
        return not self.discovery_errors


def _label(text, taken, fallback):
    """An address-safe, unique place name for a Herdr session name or machine label.

    Names that are not valid place names are rewritten, and a name that is
    already taken gets a short suffix from `fallback`, so no place is ever dropped.
    """
    base = re.sub(r'[^a-z0-9._-]+', '-', (text or '').strip().lower()).strip('-._')[:40] or 'place'
    if not base[0].isalnum():
        base = 'p' + base
    name, salt = base, 0
    while name in taken:
        name = f'{base}-{hashlib.sha1(f"{fallback}/{salt}".encode()).hexdigest()[:6]}'
        salt += 1
    taken.add(name)
    return name


def _same_socket(a, b):
    return bool(a and b) and os.path.realpath(a) == os.path.realpath(b)


def discover(herdr):
    """The places of the caller's Herdr environment, current one first."""
    socket_path = os.environ.get('HERDR_SOCKET_PATH')
    host = socket.gethostname()
    taken = set()
    errors = []
    try:
        sessions = herdr.local_json('session', 'list', '--json').get('sessions', [])
    except (HerdrError, AttributeError) as err:
        sessions = []
        errors.append({'operation': 'session list', 'code': getattr(err, 'code', 'unexpected_reply'),
                       'message': getattr(err, 'message', str(err))})
    current = None
    if herdr.session:
        current = next((item for item in sessions if item.get('name') == herdr.session), {'name': herdr.session})
    elif socket_path:
        current = next((item for item in sessions if _same_socket(item.get('socket_path'), socket_path)), None)
    else:
        current = next((item for item in sessions if item.get('default')), None)
    current_name = (current or {}).get('name')
    try:
        machines = herdr.local_json('machine', 'list', '--json')
    except HerdrError as err:
        machines = []
        errors.append({'operation': 'machine list', 'code': err.code, 'message': err.message})
    if not isinstance(machines, list):
        errors.append({'operation': 'machine list', 'code': 'unexpected_reply', 'message': str(machines)[:200]})
        machines = []
    machines = [item for item in machines if isinstance(item, dict) and item.get('id')]
    # Name every known session and machine first, in a fixed order, so a place keeps its
    # name whichever of them happen to be running or enabled.
    names = {}
    if current_name is None:
        names[('session', None)] = _label('here', taken, 'here')
    for item in sessions:
        if item.get('name'):
            names[('session', item['name'])] = _label(item['name'], taken, item['name'])
    if current_name is not None and ('session', current_name) not in names:
        names[('session', current_name)] = _label(current_name, taken, current_name)
    for item in machines:
        names[('machine', item['id'])] = _label(item.get('label') or item['id'], taken, item['id'])
    places = [Place(names[('session', current_name)], 'session', host, current_name or '?', herdr, current=True)]
    for item in sessions:
        if item is current or not item.get('running') or not item.get('name'):
            continue
        if item.get('name') == current_name or _same_socket(item.get('socket_path'), socket_path):
            continue  # the caller's own server, however it is reached
        places.append(Place(names[('session', item['name'])], 'session', host, item['name'],
                            herdr.at(session=item['name'])))
    for item in machines:
        if not item.get('enabled', True):
            continue
        label = item.get('label') or item['id']
        places.append(Place(names[('machine', item['id'])], 'machine', label, item.get('session') or 'default',
                            herdr.at(machine=item['id'], label=label), target=item.get('target') or item['id']))
    return Places(places, errors)


def survey(places, budget=None):
    """Ask each not-yet-asked place for its agents, within one budget for the whole survey.

    At most MAX_IN_FLIGHT calls run at a time and calls to one SSH target run one after
    another. A place that cannot be started before the budget ends is skipped with
    reason "budget"; a call never runs past it.
    """
    deadline = time.monotonic() + (SURVEY_BUDGET if budget is None else budget)
    queues = {}
    for place in places:
        if not place.asked and place.skipped is None:
            queues.setdefault(place.target if place.kind == 'machine' else id(place), []).append(place)

    def run(queue):
        for place in queue:
            remaining = deadline - time.monotonic()
            if remaining <= 0.5:
                place.skipped = 'budget'
                continue
            place.asked = True
            try:
                place.agents = place.herdr.agents(limit=remaining)
            except HerdrError as err:
                place.agents, place.error, place.failure = [], f'{err.code}: {err.message}', err
            place.observed_at = int(time.time() * 1000)
    with ThreadPoolExecutor(max_workers=max(1, min(MAX_IN_FLIGHT, len(queues)))) as pool:
        list(pool.map(run, queues.values()))
    return places


def resolution(places, policy, needed, matches=(), permitted=True, needs_catalogs=True):
    """The completeness record of one answer (see PROTOCOL.md): what was asked and what answered."""
    asked = [p for p in places if p.asked]
    return {
        'policy': policy,
        'permitted': permitted,
        'complete': (places.domain_known or not needs_catalogs) and all(p.answered for p in needed),
        'domain_known': places.domain_known,
        'domain_complete': places.domain_known and all(p.answered for p in places),
        'discovery_errors': places.discovery_errors,
        'asked': [p.name for p in asked],
        'unanswered': [{'place': p.name, 'error': p.error} for p in asked if p.error],
        'unasked': [{'place': p.name, 'reason': p.skipped or 'not needed'} for p in places if not p.asked],
        'observed_at': {p.name: p.observed_at for p in asked},
        'matches': [{'place': p.name, 'route': a.get('pane_id'), 'name': a.get('name')} for p, a in matches],
    }


class Unresolved(Exception):
    pass


def resolve(address, places):
    """Find the place of an address, and its agent when a listing already showed it.

    Returns (place, agent); agent is None for a pane ID or a bare place. Never guesses
    between agents with the same name. A fingerprinted address (a reply) names exactly
    one agent, so this machine's sessions are asked first and saved machines, which
    cost SSH round trips, only when the agent is not on this machine.
    """
    current = places[0]
    if address.place:
        place = next((p for p in places if p.name == address.place), None)
        if place is None:
            known = ', '.join(p.name for p in places)
            raise Unresolved(f'no place called {address.place!r} in this Herdr environment (places: {known})')
        if address.name is None:
            return place, None
        survey([place])
        if not place.reachable:
            raise Unresolved(f'{place.name} is unreachable, so nothing was sent ({place.error})')
        candidates = [place]
    elif address.name is None:
        return current, None  # a bare pane ID is a route in the caller's own Herdr server
    else:
        candidates = places
    tiers = [candidates]
    if address.fingerprint:
        tiers = [[p for p in candidates if p.kind == 'session'], [p for p in candidates if p.kind != 'session']]
    for tier in tiers:
        survey([p for p in tier if not p.asked])
        matches = [(p, a) for p in candidates for a in p.agents if a.get('name') == address.name]
        if address.fingerprint:
            matches = [(p, a) for p, a in matches if fingerprint(a.get('terminal_id')) == address.fingerprint]
        if matches:
            break
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
    return matches[0]
