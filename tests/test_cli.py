import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arda.cli import main
from arda.envelope import MAX_BODY, parse

FAKE = Path(__file__).with_name('fake_herdr.py')


def agent(name, pane, status='idle', kind=None, **extra):
    return {'name': name, 'agent': kind or name, 'agent_status': status, 'pane_id': pane, **extra}


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.state_path = tmp / 'state.json'
        binary = tmp / 'herdr'
        binary.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
        binary.chmod(0o755)
        self.env = {'HERDR_BIN_PATH': str(binary), 'FAKE_HERDR_STATE': str(self.state_path),
                    'HERDR_PANE_ID': 'w1:p1'}
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2'))

    def set_agents(self, *agents):
        self.state_path.write_text(json.dumps({'agents': list(agents), 'prompts': []}))

    def prompts(self):
        return json.loads(self.state_path.read_text())['prompts']

    def run_cli(self, *argv, env=None, stdin=''):
        out, err = io.StringIO(), io.StringIO()
        environment = {**self.env, **(env or {})}
        unset = [key for key, value in environment.items() if value is None]
        with mock.patch.dict(os.environ, {k: v for k, v in environment.items() if v is not None}), \
                mock.patch('sys.stdin', io.StringIO(stdin)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            for key in unset:
                os.environ.pop(key, None)
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_whoami_and_peers(self):
        code, out, _ = self.run_cli('whoami')
        self.assertEqual((code, out.strip()), (0, '@claude (claude) at w1:p1'))
        code, out, _ = self.run_cli('peers', '--json')
        peers = json.loads(out)
        self.assertEqual([(p['address'], p['you']) for p in peers], [('@claude', True), ('@codex', False)])

    def test_task_to_idle_agent_is_delivered_with_activity_confirmation(self):
        code, out, _ = self.run_cli('task', '@codex', 'Review the diff.', '--json')
        result = json.loads(out)
        self.assertEqual((code, result['status'], result['type']), (0, 'delivered', 'task_request'))
        [prompt] = self.prompts()
        self.assertEqual(prompt['target'], 'codex')
        self.assertIn('--wait', prompt['options'])
        self.assertEqual(prompt['options'].count('--until'), 2)
        message = parse(prompt['text'])
        self.assertEqual((message.type, message.sender, message.recipient, message.id),
                         ('task_request', '@claude', '@codex', result['id']))
        self.assertIn(f'ack @claude {result["id"]}', prompt['text'])

    def test_message_to_busy_agent_is_submitted_without_waiting(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2', status='working'))
        code, out, _ = self.run_cli('send', 'codex', 'FYI', '--json')
        self.assertEqual((code, json.loads(out)['status']), (0, 'submitted'))
        self.assertEqual(self.prompts()[0]['options'], [])

    def test_blocked_agent_is_never_typed_into(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2', status='blocked'))
        code, out, _ = self.run_cli('task', '@codex', 'x', '--json')
        self.assertEqual((code, json.loads(out)['status']), (1, 'not_delivered'))
        self.assertEqual(self.prompts(), [])

    def test_unknown_state_needs_force(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2', status='unknown'))
        code, _, _ = self.run_cli('send', '@codex', 'x')
        self.assertEqual((code, self.prompts()), (1, []))
        code, _, _ = self.run_cli('send', '@codex', 'x', '--force')
        self.assertEqual((code, len(self.prompts())), (0, 1))

    def test_unobserved_start_is_reported_as_uncertain(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2', prompt_error='agent_prompt_stalled'))
        code, out, _ = self.run_cli('task', '@codex', 'x', '--json')
        self.assertEqual((code, json.loads(out)['status']), (3, 'uncertain'))

    def test_missing_recipient_is_not_delivered(self):
        code, out, _ = self.run_cli('send', '@reviewer', 'x', '--json')
        result = json.loads(out)
        self.assertEqual((code, result['status']), (1, 'not_delivered'))
        self.assertIn('no live agent @reviewer', result['detail'])

    def test_replies_reference_the_task(self):
        self.env['HERDR_PANE_ID'] = 'w1:p2'
        code, _, _ = self.run_cli('ack', '@claude', 'abc123')
        self.assertEqual(code, 0)
        message = parse(self.prompts()[0]['text'])
        self.assertEqual((message.type, message.sender, message.re, message.body),
                         ('ack', '@codex', 'abc123', 'Accepted.'))
        report = Path(self.tmp.name) / 'report.md'
        report.write_text('All good.\n')
        self.run_cli('result', '@claude', 'abc123', '--file', str(report))
        self.run_cli('reject', '@claude', 'abc123', '-', stdin='Out of scope.')
        replies = [parse(p['text']) for p in self.prompts()[1:]]
        self.assertEqual([(m.type, m.body) for m in replies], [('result', 'All good.'), ('reject', 'Out of scope.')])

    def test_plain_shell_pane_can_send_notes_but_not_tasks(self):
        self.env['HERDR_PANE_ID'] = 'w1:p9'  # a pane with no agent in it
        self.assertEqual(self.run_cli('task', '@codex', 'x')[0], 2)
        self.assertEqual(self.run_cli('send', '@codex', 'x')[0], 0)
        self.assertEqual(parse(self.prompts()[0]['text']).sender, 'w1:p9')

    def test_unnamed_sender_uses_its_pane_as_address(self):
        self.set_agents(agent(None, 'w1:p1', kind='claude'), agent('codex', 'w1:p2'))
        self.run_cli('send', '@codex', 'hi')
        self.assertEqual(parse(self.prompts()[0]['text']).sender, 'w1:p1')

    def test_introduce_tells_each_idle_peer_who_it_is_and_who_is_here(self):
        self.set_agents(agent('claude', 'w1:p1'), agent('codex', 'w1:p2'),
                        agent('reviewer', 'w1:p3', status='working', kind='codex'), agent(None, 'w1:p4', kind='pi'))
        code, out, _ = self.run_cli('introduce')
        self.assertEqual(code, 1)  # the busy reviewer was not introduced
        [prompt] = self.prompts()
        message = parse(prompt['text'])
        self.assertEqual((prompt['target'], message.sender, message.type), ('codex', '@claude', 'note'))
        self.assertIn('You are @codex.', message.body)
        self.assertIn('@claude (claude), @reviewer (codex)', message.body)
        self.assertIn('@reviewer: @reviewer is busy', out)
        self.assertIn('herdr agent rename w1:p4 <name>', out)

    def test_introduce_as_plugin_action_speaks_for_arda(self):
        code, _, _ = self.run_cli('introduce', env={'HERDR_PLUGIN_ID': 'arda'})
        self.assertEqual(code, 0)
        texts = [p['text'] for p in self.prompts()]
        self.assertEqual([p['target'] for p in self.prompts()], ['claude', 'codex'])
        self.assertTrue(all(parse(text).sender == '@arda' for text in texts))
        self.assertIn('[arda] From ARDA itself. No reply needed.', texts[0])
        notifications = json.loads(self.state_path.read_text())['notifications']
        self.assertEqual(notifications[0][0], 'ARDA')

    def test_usage_errors(self):
        self.assertEqual(self.run_cli('send', '@claude', 'me')[0], 2)
        self.assertEqual(self.run_cli('send', 'w1:p1', 'me by pane')[0], 2)
        self.assertEqual(self.run_cli('ack', '@codex', 'not-an-id')[0], 2)
        self.assertEqual(self.run_cli('task', '@codex', 'x', '--session', 'other')[0], 2)
        self.assertEqual(self.run_cli('send', '@codex', '   ')[0], 2)
        self.assertEqual(self.run_cli('send', '@codex', 'x' * (MAX_BODY + 1))[0], 2)
        self.assertEqual(self.run_cli('send', 'Bad Name', 'x')[0], 2)
        self.assertEqual(self.run_cli('task', '@codex', 'x', env={'HERDR_PANE_ID': None})[0], 2)
        self.assertEqual(self.prompts(), [])


if __name__ == '__main__':
    unittest.main()
