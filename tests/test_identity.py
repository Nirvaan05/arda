"""Native conversation identity, strict resolution and rename propagation (contracts K3-K6)."""

import json

from test_cli import CliCase, agent

from arda.envelope import native_token, parse


def session(value, source='herdr:claude', name='claude', kind='id'):
    return {'source': source, 'agent': name, 'kind': kind, 'value': value}


LEAD = session('11111111-2222-4333-8444-555555555555')
TOKEN = native_token(LEAD)


def sessions(*names):
    return [{'name': name, 'running': True, 'default': name == 'main', 'socket_path': f'/s/{name}.sock'}
            for name in names]


class IdentityTests(CliCase):
    def setUp(self):
        super().setUp()
        self.env['HERDR_SOCKET_PATH'] = '/s/main.sock'

    def world(self, me, others=(), machines=None):
        self.set_agents(me, *others, sessions=sessions('main'), machines=machines or {})

    def test_whoami_and_from_carry_the_native_token_when_herdr_has_one(self):
        self.world(agent('claude', 'w1:p1', terminal_id='term_0000aaaa1111', agent_session=LEAD),
                   [agent('codex', 'w1:p2')])
        self.assertTrue(self.run_cli('whoami')[1].startswith(f'@claude.{TOKEN} (claude)'))
        self.run_cli('task', '@codex', '--', 'do it')
        message = parse(self.prompts()[-1]['text'])
        self.assertEqual(message.sender, f'@claude.{TOKEN}')
        self.assertIn(f'arda ack @claude.{TOKEN} ', self.prompts()[-1]['text'])

    def test_path_references_and_unknown_sources_fall_back_to_the_terminal_hint(self):
        for ref in (session('/home/u/.pi/x.jsonl', source='herdr:pi', name='pi', kind='path'),
                    session('abc', source='custom:x', name='claude'), {'source': 'herdr:claude'}):
            self.world(agent('claude', 'w1:p1', terminal_id='term_0000aaaa1111', agent_session=ref))
            self.assertTrue(self.run_cli('whoami')[1].startswith('@claude.aaaa1111 '), ref)

    def test_a_native_reply_follows_the_agent_across_a_rename(self):
        lead = agent('lead', 'w1:p1', terminal_id='term_0000aaaa1111', agent_session=LEAD)  # was @claude
        self.world(agent('helper', 'w1:p2'), [lead])
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        code, out, _ = self.run_cli('result', f'@claude.{TOKEN}', 'abc123', '--json', '--', 'done')
        result = json.loads(out)
        self.assertEqual((code, result['status'], result['to']), (0, 'delivered', '@lead'))
        self.assertEqual(result['requested'], f'@claude.{TOKEN}')
        self.assertIn('is now named @lead', result['detail'])
        prompt = self.prompts()[-1]
        self.assertEqual((prompt['target'], parse(prompt['text']).recipient), ('w1:p1', '@lead'))

    def test_one_conversation_seen_twice_is_refused_even_with_a_place_down(self):
        clone = agent('clone', 'w1:p1', agent_session=LEAD)
        self.world(agent('helper', 'w1:p2'), [agent('lead', 'w1:p1', agent_session=LEAD)],
                   machines={'d1': {'label': 'desktop', 'agents': [clone]}})
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        code, out, _ = self.run_cli('result', f'@claude.{TOKEN}', 'abc123', '--json', '--', 'done')
        self.assertEqual((code, json.loads(out)['status'], self.prompts()), (1, 'not_delivered', []))
        self.assertIn('matches more than one agent', json.loads(out)['detail'])
        # Codex's counterexample: the original is partitioned, only the clone answers -> still refused
        self.world(agent('helper', 'w1:p2'), machines={'d1': {'label': 'desktop', 'agents': [clone]},
                                                      'a1': {'label': 'away', 'down': True}})
        code, out, _ = self.run_cli('result', f'@claude.{TOKEN}', 'abc123', '--json', '--', 'done')
        self.assertEqual((code, self.prompts()), (1, []))
        self.assertIn('away did not answer', json.loads(out)['detail'])
        # naming the place sends to that instance, still checking its identity
        code, out, _ = self.run_cli('result', f'@claude.{TOKEN}@desktop', 'abc123', '--json', '--', 'done')
        self.assertEqual((code, json.loads(out)['status']), (0, 'delivered'))

    def test_a_conversation_that_changed_after_the_lookup_is_not_typed_into(self):
        other = session('99999999-2222-4333-8444-555555555555')
        lead = agent('lead', 'w1:p1', agent_session=other, listed={'agent_session': LEAD})
        self.world(agent('helper', 'w1:p2'), [lead])
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        code, out, _ = self.run_cli('result', f'@claude.{TOKEN}', 'abc123', '--json', '--', 'done')
        self.assertEqual((code, json.loads(out)['status'], self.prompts()), (1, 'not_delivered', []))
        self.assertIn('agent_session differs', json.loads(out)['detail'])

    def test_an_old_name_is_refused_with_the_agents_there_are_now(self):
        self.world(agent('claude', 'w1:p1'), [agent('tester', 'w1:p2', kind='codex')])  # codex renamed to tester
        code, out, _ = self.run_cli('send', '@codex', '--json', '--', 'hi')
        self.assertEqual((code, self.prompts()), (1, []))
        self.assertIn('Agents now: @claude@main (claude), @tester@main (codex)', json.loads(out)['detail'])
        self.assertEqual(self.run_cli('send', '@tester', '--', 'hi')[0], 0)  # the new name works at once

    def test_a_terminal_hint_whose_terminal_has_another_name_only_suggests_it(self):
        self.world(agent('helper', 'w1:p2'), [agent('lead', 'w1:p1', terminal_id='term_0000aaaa1111')])
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        code, out, _ = self.run_cli('result', '@claude.aaaa1111', 'abc123', '--json', '--', 'done')
        self.assertEqual((code, self.prompts()), (1, []))
        self.assertIn('the agent in that terminal is now @lead.aaaa1111@main', json.loads(out)['detail'])

    def test_a_native_reply_is_not_mistaken_for_a_message_to_yourself(self):
        # the replier now carries the name the sender had when it asked
        self.world(agent('lead', 'w1:p2'), [agent('helper', 'w1:p1', agent_session=LEAD)])
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        self.set_agents(agent('claude', 'w1:p2'), agent('helper', 'w1:p1', agent_session=LEAD),
                        sessions=sessions('main'), machines={})
        code, out, _ = self.run_cli('result', f'@claude.{TOKEN}', 'abc123', '--json', '--', 'done')
        self.assertEqual((code, json.loads(out)['to']), (0, '@helper'))

    def test_a_rename_between_lookup_and_typing_is_addressed_by_the_new_name(self):
        lead = agent('lead', 'w1:p1', agent_session=LEAD, listed={'name': 'claude'})
        self.world(agent('helper', 'w1:p2'), [lead])
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        code, out, _ = self.run_cli('result', f'@claude.{TOKEN}', 'abc123', '--json', '--', 'done')
        self.assertEqual((code, json.loads(out)['to']), (0, '@lead'))
        self.assertEqual(parse(self.prompts()[-1]['text']).recipient, '@lead')

    def test_introducing_a_native_address_keeps_its_identity(self):
        other = session('99999999-2222-4333-8444-555555555555')
        lead = agent('lead', 'w1:p1', agent_session=other, listed={'agent_session': LEAD})  # replaced since
        self.world(agent('helper', 'w1:p2'), [lead])
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        self.run_cli('introduce', f'@lead.{TOKEN}', '--json')
        self.assertEqual(self.prompts(), [])
