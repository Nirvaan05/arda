"""Minimal stand-in for the `herdr` CLI, driven by a JSON state file.

State: {"agents": [{name, agent, agent_status, pane_id, prompt_error?}], "prompts": []}.
Each accepted `agent prompt` is appended to "prompts", each notification to "notifications".
"""

import json
import os
import sys


def reply(result=None, error=None):
    if error:
        print(json.dumps({'id': 'cli', 'error': {'code': error, 'message': error}}), file=sys.stderr)
        sys.exit(1)
    print(json.dumps({'id': 'cli', 'result': result}))
    sys.exit(0)


def main(argv):
    path = os.environ['FAKE_HERDR_STATE']
    with open(path) as handle:
        state = json.load(handle)
    if argv[:1] == ['--session']:
        argv = argv[2:]
    agents = state['agents']

    def find(target):
        for agent in agents:
            if target in (agent.get('name'), agent['pane_id']):
                return agent
        reply(error='agent_not_found')

    if argv[:2] == ['agent', 'list']:
        reply({'type': 'agent_list', 'agents': agents})
    if argv[:2] == ['agent', 'get']:
        reply({'type': 'agent_info', 'agent': find(argv[2])})
    if argv[:2] == ['notification', 'show']:
        state.setdefault('notifications', []).append(argv[2:])
        with open(path, 'w') as handle:
            json.dump(state, handle)
        reply({'type': 'ok'})
    if argv[:2] == ['agent', 'prompt']:
        agent = find(argv[2])
        if agent['agent_status'] == 'blocked':
            reply(error='agent_blocked')
        if agent.get('prompt_error'):
            reply(error=agent['prompt_error'])
        state['prompts'].append({'target': argv[2], 'text': argv[3], 'options': argv[4:]})
        with open(path, 'w') as handle:
            json.dump(state, handle)
        reply({'type': 'agent_prompted', 'agent': agent})
    print(f'fake herdr: unsupported {argv}', file=sys.stderr)
    sys.exit(2)


if __name__ == '__main__':
    main(sys.argv[1:])
