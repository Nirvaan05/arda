import json
import shutil
import unittest
from pathlib import Path

from test_cli import CliCase

from arda import trust
from arda.cli import ROOT

SCRIPT = ROOT / 'bin' / 'arda'


class TrustTests(CliCase):
    def setUp(self):
        super().setUp()
        tmp = Path(self.tmp.name)
        self.claude, self.codex = tmp / 'claude', tmp / 'codex'
        self.claude.mkdir()
        self.codex.mkdir()
        (self.claude / 'settings.json').write_text(json.dumps({'model': 'x', 'permissions': {'allow': ['Bash(ls)']}}))
        # A plain shell pane (no agent), and no codex binary so rules are not validated here.
        self.env.update(CLAUDE_CONFIG_DIR=str(self.claude), CODEX_HOME=str(self.codex), HERDR_PANE_ID='w1:p9',
                        PATH='/usr/bin:/bin')

    def settings(self):
        return json.loads((self.claude / 'settings.json').read_text())

    def test_without_yes_nothing_changes(self):
        code, out, _ = self.run_cli('trust')
        self.assertEqual(code, 0)
        self.assertIn('Nothing was changed.', out)
        self.assertFalse((self.claude / 'rules' / 'arda.md').exists())
        self.assertFalse((self.codex / 'rules' / 'arda.rules').exists())
        self.assertEqual(self.settings()['permissions']['allow'], ['Bash(ls)'])

    def test_grant_is_idempotent_and_revoke_removes_only_what_it_added(self):
        self.assertEqual(self.run_cli('trust', '--yes')[0], 0)
        self.assertEqual(self.run_cli('trust', '--yes')[0], 0)
        rules = (self.claude / 'rules' / 'arda.md').read_text()
        self.assertIn('not from me', rules)
        self.assertIn('arda reject', rules)
        settings = self.settings()
        self.assertEqual(settings['model'], 'x')
        self.assertEqual(settings['permissions']['allow'], ['Bash(ls)', 'Bash(arda *)', f'Bash({SCRIPT} *)'])
        self.assertIn(json.dumps([str(SCRIPT)]), (self.codex / 'rules' / 'arda.rules').read_text())
        self.assertIn('installed', self.run_cli('trust', '--status')[1])

        self.assertEqual(self.run_cli('trust', '--revoke', '--yes')[0], 0)
        self.assertFalse((self.claude / 'rules' / 'arda.md').exists())
        self.assertFalse((self.codex / 'rules' / 'arda.rules').exists())
        self.assertEqual(self.settings(), {'model': 'x', 'permissions': {'allow': ['Bash(ls)']}})

    def test_an_agent_cannot_grant_itself_trust(self):
        self.env['HERDR_PANE_ID'] = 'w1:p1'  # claude's pane in the fake session
        code, _, err = self.run_cli('trust', '--yes')
        self.assertEqual(code, 2)
        self.assertIn('not by an agent', err)
        self.assertFalse((self.claude / 'rules').exists())

    def test_unexpected_settings_stop_the_change_before_anything_is_written(self):
        for bad in ('[]', '{not json', '{"permissions": []}', '{"permissions": {"allow": "x"}}'):
            (self.claude / 'settings.json').write_text(bad)
            self.assertEqual(self.run_cli('trust', '--yes')[0], 2, bad)
            self.assertEqual((self.claude / 'settings.json').read_text(), bad)
            self.assertFalse((self.claude / 'rules' / 'arda.md').exists(), bad)
            self.assertFalse((self.codex / 'rules' / 'arda.rules').exists(), bad)

    def test_missing_harness_directories_are_skipped(self):
        shutil.rmtree(self.codex)
        self.run_cli('trust', '--yes')
        self.assertFalse(self.codex.exists())
        self.assertTrue((self.claude / 'rules' / 'arda.md').exists())

    @unittest.skipUnless(shutil.which('codex'), 'codex is not installed')
    def test_codex_accepts_the_generated_rules(self):
        rules = Path(self.tmp.name) / 'arda.rules'
        rules.write_text(trust.CODEX_RULES.format(paths=json.dumps([str(SCRIPT)])))
        trust._check_codex_rules(rules, SCRIPT)  # raises (and deletes the file) if Codex rejects it
        self.assertTrue(rules.exists())


if __name__ == '__main__':
    unittest.main()
