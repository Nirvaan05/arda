import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import isolation  # noqa: F401  (before any test runs: keeps tests away from real Herdr)
from test_cli import CliCase, agent

from arda import harness

CODEX = 'codex-0001-4000-8000-000000000001'
CLAUDE = 'claude-0001-4000-8000-000000000001'


def codex_session(value=CODEX):
    return {'source': 'herdr:codex', 'agent': 'codex', 'kind': 'id', 'value': value}


def claude_session(value=CLAUDE):
    return {'source': 'herdr:claude', 'agent': 'claude', 'kind': 'id', 'value': value}


def write(path, *entries, filler=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(entry) for entry in entries]
    lines += [json.dumps({'type': 'filler', 'text': 'x' * 100})] * filler  # later lines without a model
    path.write_text('\n'.join(lines) + '\n')


class ModelTests(unittest.TestCase):
    """`arda describe --model auto` reads the model from the agent's own session log."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.env = {'CODEX_HOME': str(self.home / 'codex'), 'CLAUDE_CONFIG_DIR': str(self.home / 'claude')}

    def codex_log(self, *models, day='05', filler=0):
        turns = [{'type': 'turn_context', 'payload': {'model': model, 'effort': 'xhigh'}} for model in models]
        write(self.home / 'codex' / 'sessions' / '2026' / '10' / day / f'rollout-2026-10-{day}T10-00-00-{CODEX}.jsonl',
              {'type': 'session_meta', 'payload': {'id': CODEX}}, *turns, filler=filler)

    def test_codex_reports_the_latest_turns_model_and_effort(self):
        self.codex_log('gpt-6-astra', 'gpt-6.1-sol')  # switched with /model during the session
        self.assertEqual(harness.model_of(codex_session(), self.env), 'gpt-6.1-sol (reasoning xhigh)')

    def test_the_newest_log_of_a_resumed_conversation_wins(self):
        self.codex_log('gpt-6-astra', day='04')
        self.codex_log('gpt-6.1-sol', day='05')
        os.utime(next((self.home / 'codex' / 'sessions').glob('*/*/04/*')), (1, 1))  # the older log
        self.assertEqual(harness.model_of(codex_session(), self.env), 'gpt-6.1-sol (reasoning xhigh)')

    def test_claude_reports_the_latest_replys_model(self):
        write(self.home / 'claude' / 'projects' / '-work-app' / f'{CLAUDE}.jsonl',
              {'type': 'assistant', 'message': {'model': 'claude-sonnet-5-5'}},
              {'type': 'assistant', 'message': {'model': 'claude-opus-5-5'}},
              {'type': 'assistant', 'message': {'model': '<synthetic>'}},
              {'type': 'user', 'message': {'content': 'hi'}})
        self.assertEqual(harness.model_of(claude_session(), self.env), 'claude-opus-5-5')

    def test_a_long_log_is_read_from_the_end_across_chunks(self):
        self.codex_log('gpt-6-astra', filler=50)
        with mock.patch.object(harness, '_CHUNK', 64):
            self.assertEqual(harness.model_of(codex_session(), self.env), 'gpt-6-astra (reasoning xhigh)')

    def test_it_refuses_rather_than_guesses(self):
        cases = [
            (None, 'no conversation'),
            ({**codex_session(), 'kind': 'path'}, 'no conversation'),
            ({**codex_session(), 'source': 'other'}, 'no conversation'),
            (codex_session('../../etc/passwd'), 'not a plain session ID'),
            (codex_session('*'), 'not a plain session ID'),
            (codex_session(), 'found no session log'),
        ]
        for session, reason in cases:
            with self.subTest(session=session), self.assertRaisesRegex(harness.ModelUnknown, reason):
                harness.model_of(session, self.env)
        write(self.home / 'codex' / 'sessions' / '2026' / '10' / '05' / f'rollout-x-{CODEX}.jsonl',
              {'type': 'session_meta', 'payload': {}})
        with self.assertRaisesRegex(harness.ModelUnknown, 'records no model yet'):
            harness.model_of(codex_session(), self.env)


class DescribeModelTests(CliCase):
    def test_describe_model_auto_stores_the_detected_model(self):
        tmp = Path(self.tmp.name)
        write(tmp / 'codex' / 'sessions' / '2026' / '10' / '05' / f'rollout-2026-10-05T10-00-00-{CODEX}.jsonl',
              {'type': 'turn_context', 'payload': {'model': 'gpt-6.1-sol', 'effort': 'xhigh'}})
        self.set_agents(agent('reviewer', 'w1:p1', kind='codex', agent_session=codex_session()))
        code, out, _ = self.run_cli('describe', '--model', 'auto', env={'CODEX_HOME': str(tmp / 'codex')})
        self.assertEqual(code, 0, out)
        self.assertIn('• Model: "gpt-6.1-sol (reasoning xhigh)"', out)

    def test_describe_model_auto_without_an_integration_says_what_to_do(self):
        self.set_agents(agent('reviewer', 'w1:p1', kind='codex', terminal_id='term_65cc151806d161'))
        code, _, err = self.run_cli('describe', '--model', 'auto')
        self.assertEqual(code, 2)
        self.assertIn("Herdr reports no conversation for this agent", err)
        self.assertIn("--model '<model>'", err)
        self.assertNotIn('tokens', json.loads(self.state_path.read_text())['agents'][0])


if __name__ == '__main__':
    unittest.main()
