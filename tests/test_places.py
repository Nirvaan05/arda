import json
import time
from pathlib import Path
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
                         'g1': {'label': 'gpu', 'agents': []}},
        }
        self.set_agents(agent('claude', 'w1:p1', terminal_id='term_0000aaaa1111'), agent('helper', 'w1:p2'),
                        **{**state, **overrides})

    def test_peers_covers_every_reachable_place_and_names_unreachable_ones(self):
        self.environment(machines={'d1': {'label': 'Desktop', 'agents': [agent('codex', 'w1:p1')]}, 'g1': {'label': 'gpu', 'down': True}})
        code, out, _ = self.run_cli('peers', '--json')
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual([(p['place'], p['kind'], p['answered']) for p in data['places']],
                         [('main', 'session', True), ('other', 'session', True), ('desktop', 'machine', True),
                          ('gpu', 'machine', False)])
        self.assertEqual([(p['address'], p['place'], p['you']) for p in data['peers']],
                         [('@claude', 'main', True), ('@helper', 'main', False), ('@tester', 'other', False),
                          ('@codex', 'desktop', False)])
        text = self.run_cli('peers')[1]
        self.assertIn('\ngpu · saved machine gpu, Herdr session default\n  ✗ unreachable: machine_unreachable', text)
        self.assertTrue(text.startswith('4 agents in 3 places: 4 idle; 1 place did not answer\n'), text)
        self.assertIn('\nmain · Herdr session on this machine (', text)
        self.assertIn(') · you are here\n  ○ @claude  ', text)

    def test_a_unique_name_is_found_wherever_it_runs(self):
        code, out, _ = self.run_cli('task', '@codex', '--json', '--', 'review it')
        result = json.loads(out)
        self.assertEqual((code, result['status'], result['to'], result['place']), (0, 'delivered', '@codex@desktop',
                                                                                  'desktop'))
        [prompt] = self.prompts()
        self.assertEqual((prompt['place'], prompt['target']), ('d1', 'w1:p1'))  # the verified pane
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

    def calls(self):
        return json.loads(self.state_path.read_text())['calls']

    def test_a_reply_asks_every_place_and_needs_the_name_and_terminal(self):
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        self.assertEqual(self.run_cli('result', '@claude.aaaa1111', 'abc123', '--', 'done')[0], 0)
        self.assertEqual(sorted(c[1] for c in self.calls() if c[0] == '--machine' and c[2:4] == ['agent', 'list']),
                         ['d1', 'g1'])  # strict: a terminal hint is checked across the whole environment

    def test_the_receiver_is_read_again_right_before_typing(self):
        # Listed idle, working by the time of delivery: the fresh read decides (Codex's race, D3).
        busy = agent('codex', 'w1:p1', status='working', listed_status='idle')
        self.environment(machines={'d1': {'label': 'desktop', 'agents': [busy]}})
        code, out, _ = self.run_cli('send', '@codex', '--json', '--', 'hi')
        self.assertEqual((code, json.loads(out)['status']), (0, 'submitted'))
        self.assertEqual([c[2:4] for c in self.calls() if c[:2] == ['--machine', 'd1']],
                         [['agent', 'list'], ['agent', 'get'], ['agent', 'prompt']])
        prompts = len(self.prompts())
        self.run_cli('introduce', '@codex', '--json')
        self.assertEqual(len(self.prompts()), prompts)  # busy at delivery time: skipped, nothing typed

    def test_machine_failures_say_what_went_wrong(self):
        self.environment(machines={
            'n1': {'label': 'stopped', 'fail': {'*': 'remote SSH connection failed: failed to connect to remote '
                                                     'Herdr API socket /run/h.sock: No such file or directory'}},
            'a1': {'label': 'locked', 'fail': {'*': 'remote SSH connection failed: me@a1: Permission denied '
                                                     '(publickey).'}},
            'p1': {'label': 'old', 'error': 'protocol_mismatch'}})
        text = self.run_cli('peers')[1]
        self.assertIn('stopped · saved machine stopped, Herdr session default\n  ✗ unreachable: server_not_running: '
                      'saved machine stopped is reachable, but its Herdr session is not running', text)
        self.assertIn('unreachable: machine_auth: saved machine locked refused the SSH login; run `herdr machine '
                      'reconnect locked`', text)
        self.assertIn('old · saved machine old, Herdr session default\n  ✗ unreachable: protocol_mismatch', text)

    def test_a_connection_lost_during_a_prompt_is_uncertain_and_a_refused_login_sent_nothing(self):
        lost = 'remote SSH connection failed: Connection to d1 closed by remote host.'
        self.environment(machines={'d1': {'label': 'desktop', 'agents': [agent('codex', 'w1:p1')],
                                          'fail': {'agent prompt': lost}}})
        code, out, _ = self.run_cli('send', '@codex', '--json', '--', 'hi')
        self.assertEqual((code, json.loads(out)['status']), (3, 'uncertain'))
        self.environment(machines={'d1': {'label': 'desktop', 'agents': [agent('codex', 'w1:p1')],
                                          'fail': {'agent prompt': 'remote SSH connection failed: Host key '
                                                                   'verification failed.'}}})
        code, out, _ = self.run_cli('send', '@codex', '--json', '--', 'hi')
        self.assertEqual((code, json.loads(out)['status']), (1, 'not_delivered'))
        self.assertIn('nothing was sent', json.loads(out)['detail'])

    def test_a_refused_ssh_channel_is_tried_again_only_for_lookups(self):
        self.environment(machines={'d1': {'label': 'desktop', 'agents': [agent('codex', 'w1:p1')],
                                          'refuse_once': ['agent list']}})
        self.assertEqual(self.run_cli('send', '@codex', '--', 'hi')[0], 0)
        self.assertEqual([c[2:4] for c in self.calls() if c[:2] == ['--machine', 'd1']],
                         [['agent', 'list'], ['agent', 'list'], ['agent', 'get'], ['agent', 'prompt']])
        self.environment(machines={'d1': {'label': 'desktop', 'agents': [agent('codex', 'w1:p1')],
                                          'refuse_once': ['agent prompt']}})
        code, out, _ = self.run_cli('send', '@codex', '--json', '--', 'hi')
        self.assertEqual((code, json.loads(out)['status'], self.prompts()), (1, 'not_delivered', []))

    def test_two_routes_to_one_server_are_both_listed_never_merged(self):
        # A saved machine pointing back at this server: ARDA cannot prove it is the same server, so it
        # keeps both routes and refuses a name it sees twice (Codex review D4).
        mine = [agent('claude', 'w1:p1', terminal_id='term_0000aaaa1111'),
                agent('helper', 'w1:p2', terminal_id='term_0000bbbb2222')]
        self.set_agents(*mine, sessions=sessions('main'), machines={'l1': {'label': 'loop', 'agents': mine}})
        data = json.loads(self.run_cli('peers', '--json')[1])
        self.assertEqual([p['address'] for p in data['peers']], ['@claude@main', '@helper@main', '@claude@loop',
                                                                  '@helper@loop'])
        code, out, _ = self.run_cli('send', '@helper', '--json', '--', 'hi')
        self.assertEqual((code, json.loads(out)['status']), (1, 'not_delivered'))
        self.assertEqual(self.run_cli('send', '@helper@main', '--', 'hi')[0], 0)

    def test_a_bare_name_is_refused_while_a_place_does_not_answer(self):
        self.environment(machines={'d1': {'label': 'Desktop', 'agents': [agent('codex', 'w1:p1')]}, 'g1': {'label': 'gpu', 'down': True}})
        code, out, _ = self.run_cli('send', '@codex', '--json', '--', 'hi')
        result = json.loads(out)
        self.assertEqual((code, result['status'], self.prompts()), (1, 'not_delivered', []))
        self.assertEqual([u['place'] for u in result['resolution']['unanswered']], ['gpu'])
        self.assertEqual((result['resolution']['permitted'], result['resolution']['complete']), (False, False))
        self.assertIn('cannot be shown to be unique', result['detail'])
        self.assertIn('Found so far: @codex@desktop', result['detail'])
        self.assertIn('a setup choice for the user, not for an agent', result['detail'])
        self.assertEqual(self.run_cli('send', '@codex@desktop', '--', 'hi')[0], 0)  # its place: unrelated outage ok

    def test_failed_discovery_is_reported_not_treated_as_empty(self):
        self.environment(machine_list_error='cannot read the machine catalog')
        data = json.loads(self.run_cli('peers', '--json')[1])
        self.assertFalse(data['resolution']['domain_known'])
        self.assertEqual(data['resolution']['discovery_errors'][0]['operation'], 'machine list')
        self.assertIn('cannot list machine list', self.run_cli('peers')[1])

    def test_a_survey_has_one_budget_and_one_call_at_a_time_per_ssh_target(self):
        slow = {'label': 'slow', 'hang': 1.2, 'target': 'me@box', 'agents': []}
        self.environment(machines={'s1': dict(slow), 's2': {**slow, 'label': 'slow2'}})
        with mock.patch('arda.topology.SURVEY_BUDGET', 1.6):
            data = json.loads(self.run_cli('peers', '--json')[1])
        places = {p['place']: p for p in data['places']}
        # the two places share one SSH target, so they were asked one after the other; the second did
        # not fit in what was left of the budget
        self.assertEqual(sorted((places['slow']['skipped'], places['slow2']['skipped']), key=str), [None, 'budget'])
        self.assertIn({'place': 'slow2' if places['slow2']['skipped'] else 'slow', 'reason': 'budget'},
                      data['resolution']['unasked'])

    def test_a_timed_out_lookup_leaves_no_process_behind(self):
        marker = Path(self.tmp.name) / 'child.pid'
        self.environment(machines={'h1': {'label': 'slow', 'hang': 30, 'hang_child': str(marker)}})
        with mock.patch('arda.herdr.MACHINE_TIMEOUT', 1):
            self.assertEqual(self.run_cli('send', '@helper', '--', 'hi')[0], 1)  # strict: slow could not answer
        pid = int(marker.read_text())
        for _ in range(30):
            try:
                if Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                    break  # killed, waiting to be reaped
            except FileNotFoundError:
                break
            time.sleep(0.1)
        else:
            self.fail(f'process {pid} started by the timed-out herdr is still running')

    def test_introductions_reach_every_agent_on_one_machine(self):
        self.environment(machines={'d1': {'label': 'desktop', 'agents': [agent('codex', 'w1:p1'),
                                                                          agent('reviewer', 'w1:p2')]}})
        code, _, _ = self.run_cli('introduce', '--json', env={'HERDR_PLUGIN_ID': 'arda'})
        self.assertEqual(code, 0)
        self.assertEqual(sorted(p['target'] for p in self.prompts() if p['place'] == 'd1'), ['w1:p1', 'w1:p2'])

    def test_unreachable_places_fail_clearly_and_send_nothing(self):
        self.environment(machines={'d1': {'label': 'Desktop', 'agents': [agent('codex', 'w1:p1')]}, 'g1': {'label': 'gpu', 'down': True}})
        code, out, _ = self.run_cli('send', '@codex@gpu', '--json', '--', 'hi')
        self.assertEqual((code, json.loads(out)['status']), (1, 'not_delivered'))
        self.assertIn('gpu did not answer, so nothing was sent', json.loads(out)['detail'])
        self.assertIn('saved machine gpu cannot be reached', json.loads(out)['detail'])
        code, out, _ = self.run_cli('send', '@reviewer', '--json', '--', 'hi')
        self.assertIn('gpu did not answer', json.loads(out)['detail'])
        code, out, _ = self.run_cli('send', '@codex@nowhere', '--json', '--', 'hi')
        self.assertIn("no place called 'nowhere'", json.loads(out)['detail'])
        self.assertEqual(self.prompts(), [])

    def test_introduce_reaches_agents_in_every_reachable_place(self):
        code, out, _ = self.run_cli('introduce', '--json', env={'HERDR_PLUGIN_ID': 'arda'})
        self.assertEqual(code, 0)
        self.assertCountEqual([(p['place'], p['target']) for p in self.prompts()],
                              [('current', 'w1:p1'), ('current', 'w1:p2'), ('other', 'w1:p1'), ('d1', 'w1:p1')])
        self.assertEqual([r['to'] for r in json.loads(out)['results']],  # reported in a fixed order
                         ['@claude', '@helper', '@tester@other', '@codex@desktop'])
        self.assertEqual([c[2:4] for c in self.calls() if c[:1] == ['--machine']],
                         [['agent', 'list'], ['agent', 'list'], ['agent', 'get'], ['agent', 'prompt']])
        body = parse(next(p['text'] for p in self.prompts() if p['place'] == 'd1')).body
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
        with mock.patch('arda.herdr.MACHINE_TIMEOUT', 1):
            code, out, _ = self.run_cli('send', '@helper', '--json', '--', 'hi')
            self.assertEqual((code, json.loads(out)['status']), (1, 'not_delivered'))  # strict
            self.assertEqual(self.run_cli('send', '@helper@main', '--', 'hi')[0], 0)  # its place needs no survey
        self.assertLess(time.time() - started, 10)

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
        self.assertEqual(self.prompts()[-1]['target'], 'w1:p1')  # always the pane that was verified

    def test_introduce_reports_unresolved_and_repeated_targets(self):
        code, out, _ = self.run_cli('introduce', '@nobody', '@codex', '@codex', '--json')
        result = json.loads(out)
        self.assertEqual((code, result['status']), (1, 'not_delivered'))
        self.assertEqual([(r['to'], r['status']) for r in result['results']],
                         [('@nobody', 'not_delivered'), ('@codex@desktop', 'delivered')])

    def test_place_names_stay_unique_and_do_not_depend_on_what_is_running(self):
        clash = {'m0': {'label': 'other-x'}, 'm1': {'label': 'Other'}, 'm2': {'label': 'other'}}
        self.environment(machines=clash)
        running = {p['place'] for p in json.loads(self.run_cli('peers', '--json')[1])['places']}
        self.assertEqual(len(running), 5)  # main, other (session) and three machines
        stopped = sessions('main', 'other')
        stopped[1]['running'] = False
        self.environment(machines=clash, sessions=stopped)
        places = json.loads(self.run_cli('peers', '--json')[1])['places']
        self.assertEqual({p['place'] for p in places} | {'other'}, running)
