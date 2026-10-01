import json
import time
from unittest import mock

from test_cli import CliCase, agent

from arda.envelope import parse


def sessions(*names):
    return [{'name': name, 'running': True, 'default': name == 'main', 'socket_path': f'/s/{name}.sock'}
            for name in names]


class PlacesTests(CliCase):
    """One Herdr environment: the caller's session, another local session and saved machines."""

    def setUp(self):
        super().setUp()
        self.env['HERDR_SOCKET_PATH'] = '/s/main.sock'
        self.environment()

    def environment(self, **overrides):
        state = {
            'sessions': sessions('main', 'other'),
            'session_agents': {'other': [agent('tester', 'w1:p1', kind='claude')]},
            'machines': {'d1': {'label': 'Desktop', 'agents': [agent('codex', 'w1:p1')]},
                         'g1': {'label': 'gpu', 'down': True}},
        }
        self.set_agents(agent('claude', 'w1:p1', terminal_id='term_0000aaaa1111'), agent('helper', 'w1:p2'),
                        **{**state, **overrides})

    def test_peers_covers_every_reachable_place_and_names_unreachable_ones(self):
        code, out, _ = self.run_cli('peers', '--json')
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual([(p['place'], p['kind'], p['reachable']) for p in data['places']],
                         [('main', 'session', True), ('other', 'session', True), ('desktop', 'machine', True),
                          ('gpu', 'machine', False)])
        self.assertEqual([(p['address'], p['place'], p['you']) for p in data['peers']],
                         [('@claude', 'main', True), ('@helper', 'main', False), ('@tester', 'other', False),
                          ('@codex', 'desktop', False)])
        text = self.run_cli('peers')[1]
        self.assertIn('gpu: saved machine gpu, Herdr session default: unreachable', text)

    def test_a_unique_name_is_found_wherever_it_runs(self):
        code, out, _ = self.run_cli('task', '@codex', '--json', '--', 'review it')
        result = json.loads(out)
        self.assertEqual((code, result['status'], result['to'], result['place']), (0, 'delivered', '@codex@desktop',
                                                                                  'desktop'))
        [prompt] = self.prompts()
        self.assertEqual((prompt['place'], prompt['target']), ('d1', 'codex'))
        message = parse(prompt['text'])
        self.assertEqual((message.sender, message.recipient), ('@claude.aaaa1111', '@codex'))
        self.assertIn('arda ack @claude.aaaa1111 ', prompt['text'])  # another machine: its own arda
        self.run_cli('send', '@tester', '--', 'hi')
        self.assertEqual(self.prompts()[-1]['place'], 'other')

    def test_a_name_in_two_places_is_never_guessed(self):
        self.environment(session_agents={'other': [agent('codex', 'w1:p3')]})
        code, out, _ = self.run_cli('send', '@codex', '--json', '--', 'hi')
        result = json.loads(out)
        self.assertEqual((code, result['status'], self.prompts()), (1, 'not_delivered', []))
        self.assertIn('@codex@other, @codex@desktop', result['detail'])
        self.assertEqual(self.run_cli('send', '@codex@desktop', '--', 'hi')[0], 0)
        self.assertEqual(self.prompts()[-1]['place'], 'd1')
        peers = json.loads(self.run_cli('peers', '--json')[1])['peers']
        self.assertIn('@codex@other', [p['address'] for p in peers])

    def test_a_reply_reaches_only_the_agent_that_sent_the_message(self):
        twin = agent('claude', 'w1:p1', terminal_id='term_00002222bbbb')
        self.environment(machines={'d1': {'label': 'desktop', 'agents': [twin, agent('codex', 'w1:p2')]}})
        self.env['HERDR_PANE_ID'] = 'w1:p2'  # @helper replies to the claude in its own session
        self.assertEqual(self.run_cli('result', '@claude.aaaa1111', 'abc123', '--', 'done')[0], 0)
        self.assertEqual(self.prompts()[-1]['place'], 'current')
        self.assertEqual(self.run_cli('result', '@claude.2222bbbb', 'abc123', '--', 'done')[0], 0)
        self.assertEqual(self.prompts()[-1]['place'], 'd1')
        code, out, _ = self.run_cli('result', '@claude.99999999', 'abc123', '--json', '--', 'done')
        self.assertEqual((code, json.loads(out)['status']), (1, 'not_delivered'))
        self.assertIn('the agent that sent the message is gone', json.loads(out)['detail'])
        self.assertEqual(len(self.prompts()), 2)

    def test_unreachable_places_fail_clearly_and_send_nothing(self):
        code, out, _ = self.run_cli('send', '@codex@gpu', '--json', '--', 'hi')
        self.assertEqual((code, json.loads(out)['status']), (1, 'not_delivered'))
        self.assertIn('gpu is unreachable, so nothing was sent', json.loads(out)['detail'])
        self.assertIn('saved machine gpu cannot be reached', json.loads(out)['detail'])
        code, out, _ = self.run_cli('send', '@reviewer', '--json', '--', 'hi')
        self.assertIn('(unreachable: gpu)', json.loads(out)['detail'])
        code, out, _ = self.run_cli('send', '@codex@nowhere', '--json', '--', 'hi')
        self.assertIn("no place called 'nowhere'", json.loads(out)['detail'])
        self.assertEqual(self.prompts(), [])

    def test_introduce_reaches_agents_in_every_reachable_place(self):
        code, _, _ = self.run_cli('introduce', env={'HERDR_PLUGIN_ID': 'arda'})
        self.assertEqual(code, 0)
        self.assertEqual([(p['place'], p['target']) for p in self.prompts()],
                         [('current', 'claude'), ('current', 'helper'), ('other', 'tester'), ('d1', 'codex')])
        body = parse(self.prompts()[-1]['text']).body
        self.assertIn('You are @codex.', body)
        self.assertIn('@tester (claude on ', body)

    def test_places_with_clashing_or_invalid_names_are_never_dropped(self):
        self.environment(sessions=sessions('main', 'Other', 'other', 'my work'),
                         session_agents={name: [agent('codex', 'w1:p1')] for name in ('Other', 'other', 'my work')},
                         machines={})
        places = json.loads(self.run_cli('peers', '--json')[1])['places']
        names = [p['place'] for p in places]
        self.assertEqual(len(names), 4)
        self.assertEqual(len(set(names)), 4)
        self.assertIn('my-work', names)
        code, out, _ = self.run_cli('send', '@codex', '--json', '--', 'hi')
        self.assertEqual((code, json.loads(out)['status'], self.prompts()), (1, 'not_delivered', []))
        self.assertEqual(json.loads(out)['detail'].count('@codex@'), 3)

    def test_the_callers_own_session_is_recognised_however_its_socket_is_written(self):
        self.env['HERDR_SOCKET_PATH'] = '/s/./main.sock'
        places = [p['place'] for p in json.loads(self.run_cli('peers', '--json')[1])['places']]
        self.assertEqual(places.count('main'), 1)
        self.assertEqual(self.run_cli('send', '@helper', '--', 'hi')[0], 0)

    def test_disabled_machines_are_not_part_of_the_environment(self):
        self.environment(machines={'d1': {'label': 'desktop', 'enabled': False, 'agents': [agent('codex', 'w1:p1')]}})
        places = [p['place'] for p in json.loads(self.run_cli('peers', '--json')[1])['places']]
        self.assertNotIn('desktop', places)

    def test_a_hung_machine_cannot_stall_a_send_for_long(self):
        self.environment(machines={'h1': {'label': 'slow', 'hang': 30, 'agents': []}})
        started = time.time()
        with mock.patch('arda.herdr.LOOKUP_TIMEOUT', 1):
            code, out, _ = self.run_cli('send', '@helper', '--json', '--', 'hi')
        self.assertLess(time.time() - started, 10)
        self.assertEqual((code, json.loads(out)['status']), (0, 'delivered'))

    def test_an_unnamed_agent_cannot_message_another_place(self):
        self.environment()
        self.set_agents(agent(None, 'w1:p2', kind='claude'), agent('helper', 'w1:p3'),
                        sessions=sessions('main', 'other'), session_agents={'other': [agent('tester', 'w1:p2')]},
                        machines={})
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        code, _, err = self.run_cli('send', '@tester', '--', 'hi')
        self.assertEqual((code, self.prompts()), (2, []))
        self.assertIn('herdr agent rename w1:p2', err)
        self.assertEqual(self.run_cli('send', '@helper', '--', 'same place is fine')[0], 0)

    def test_fingerprinted_delivery_types_into_the_verified_pane(self):
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        self.run_cli('result', '@claude.aaaa1111', 'abc123', '--', 'done')
        self.assertEqual(self.prompts()[-1]['target'], 'w1:p1')
        self.run_cli('send', '@claude', '--', 'by name')
        self.assertEqual(self.prompts()[-1]['target'], 'claude')

    def test_introduce_reports_unresolved_and_repeated_targets(self):
        code, out, _ = self.run_cli('introduce', '@nobody', '@codex', '@codex', '--json')
        result = json.loads(out)
        self.assertEqual((code, result['status']), (1, 'not_delivered'))
        self.assertEqual([(r['to'], r['status']) for r in result['results']],
                         [('@nobody', 'not_delivered'), ('@codex@desktop', 'delivered')])
