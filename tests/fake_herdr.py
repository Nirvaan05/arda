"""Minimal stand-in for the `herdr` CLI, driven by a JSON state file.

State:
  "agents": agents of the caller's own server [{name, agent, agent_status, pane_id, terminal_id?, prompt_error?}]
  "sessions": local sessions for `session list --json` (default: one running session "main", the caller's)
  "session_agents": {session name: [agents]} for `--session NAME`
  "machines": {id: {"label", "session", "agents": [...], "down": bool, "enabled": bool}} for `machine list` and
              `--machine ID`
  "prompts": every accepted `agent prompt` as {place, target, text, options}
  "notifications", "calls": recorded as well
Optional "error" fails every call with that code; optional "raw" is printed verbatim instead of a
reply; optional "shell_pid" is the pane shell reported by `pane process-info` (default: the
process that ran this fake).
"""

import fcntl
import json
import os
import sys


def reply(result=None, error=None):
    if error:
        print(json.dumps({'id': 'cli', 'error': {'code': error, 'message': error}}), file=sys.stderr)
        sys.exit(1)
    print(json.dumps({'id': 'cli', 'result': result}))
    sys.exit(0)


def save(path, state):
    with open(path, 'w') as handle:
        json.dump(state, handle)


def main(argv):
    path = os.environ['FAKE_HERDR_STATE']
    # ARDA asks several places in parallel; serialise access to the state file.
    lock = open(path + '.lock', 'w')  # noqa: SIM115 - held until this process exits
    fcntl.flock(lock, fcntl.LOCK_EX)
    with open(path) as handle:
        state = json.load(handle)
    state.setdefault('calls', []).append(argv)
    save(path, state)
    place, agents = 'current', state['agents']
    if argv[:1] == ['--session']:
        place, argv = argv[1], argv[2:]
        agents = state.get('session_agents', {}).get(place, state['agents'] if place == 'main' else [])
    elif argv[:1] == ['--machine']:
        machine = state.get('machines', {}).get(argv[1])
        if machine is None:
            reply(error='machine_not_found')
        if machine.get('hang'):
            import time
            lock.close()  # a hung machine must not hold up calls to other places
            time.sleep(machine['hang'])
        if machine.get('down'):
            print(f'ssh: connect to host {argv[1]}: Connection refused', file=sys.stderr)
            sys.exit(255)
        place, argv, agents = argv[1], argv[2:], machine.get('agents', [])
    if state.get('error'):
        reply(error=state['error'])
    if 'raw' in state:
        print(state['raw'])
        sys.exit(0)
    if argv[:3] == ['session', 'list', '--json']:
        sessions = state.get('sessions') or [{'name': 'main', 'running': True, 'default': True,
                                              'socket_path': os.environ.get('HERDR_SOCKET_PATH', '/fake.sock')}]
        print(json.dumps({'sessions': sessions}))
        sys.exit(0)
    if argv[:3] == ['machine', 'list', '--json']:
        print(json.dumps([{'id': mid, 'label': m.get('label', mid), 'session': m.get('session', 'default'),
                           'enabled': m.get('enabled', True), 'target': f'user@{mid}'}
                          for mid, m in state.get('machines', {}).items()]))
        sys.exit(0)

    def find(target):
        for agent in agents:
            if target in (agent.get('name'), agent['pane_id']):
                return agent
        reply(error='agent_not_found')

    if argv[:2] == ['agent', 'list']:
        reply({'type': 'agent_list', 'agents': agents})
    if argv[:2] == ['agent', 'get']:
        reply({'type': 'agent_info', 'agent': find(argv[2])})
    if argv[:3] == ['pane', 'process-info', '--pane'] and argv[3] in state.get('stale_panes', []):
        reply(error='pane_not_found')
    if argv[:3] == ['pane', 'process-info', '--pane']:
        # By default the caller (the test process running arda) is the pane's shell.
        reply({'type': 'pane_process_info',
               'process_info': {'pane_id': argv[3], 'shell_pid': state.get('shell_pid', os.getppid())}})
    if argv[:2] == ['notification', 'show']:
        state.setdefault('notifications', []).append(argv[2:])
        save(path, state)
        reply({'type': 'ok'})
    if argv[:2] == ['agent', 'prompt']:
        agent = find(argv[2])
        if agent['agent_status'] == 'blocked':
            reply(error='agent_blocked')
        if agent.get('prompt_error'):
            reply(error=agent['prompt_error'])
        state['prompts'].append({'place': place, 'target': argv[2], 'text': argv[3], 'options': argv[4:]})
        save(path, state)
        if agent.get('null_reply'):
            reply({'type': 'agent_prompted', 'agent': None})
        reply({'type': 'agent_prompted', 'agent': {**agent, 'agent_status': agent.get('after_prompt', 'working')}})
    print(f'fake herdr: unsupported {argv}', file=sys.stderr)
    sys.exit(2)


if __name__ == '__main__':
    main(sys.argv[1:])
