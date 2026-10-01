import json
import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from test_cli import CliCase, agent

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
        (self.codex / 'AGENTS.md').write_text('# My own instructions\n')
        # A plain shell pane (no agent), and no codex binary so rules are not validated here.
        self.env.update(CLAUDE_CONFIG_DIR=str(self.claude), CODEX_HOME=str(self.codex), HERDR_PANE_ID='w1:p9',
                        PATH='/usr/bin:/bin')

    def settings(self):
        return json.loads((self.claude / 'settings.json').read_text())

    def test_revoke_leaves_no_empty_traces(self):
        (self.claude / 'settings.json').write_text(json.dumps({'model': 'x'}))
        self.run_cli('trust', '--yes')
        self.run_cli('trust', '--revoke', '--yes')
        self.assertEqual(self.settings(), {'model': 'x'})
        self.assertFalse((self.claude / 'rules' / 'arda.md').exists())
        self.assertFalse((self.codex / 'rules' / 'arda.rules').exists())

    def test_grant_then_revoke_restores_files_byte_for_byte(self):
        shapes = ['# Mine\r\nCRLF line\r\n', '# Mine\n\n\n', '# Mine\nno final newline', '']
        for original in shapes:
            agents = self.codex / 'AGENTS.md'
            agents.write_bytes(original.encode())
            (self.claude / 'settings.json').write_text('{"model": "é", "permissions": {"allow": ["Bash(ls)"]}}')
            self.run_cli('trust', '--yes')
            if '\r\n' in original:
                self.assertNotIn(b'\n<!--', agents.read_bytes().replace(b'\r\n', b''))
            self.run_cli('trust', '--revoke', '--yes')
            if original == '':
                self.assertFalse(agents.exists())
            elif original.endswith('\n'):
                self.assertEqual(agents.read_bytes(), original.encode(), repr(original))
            else:  # a final newline is added when the section is appended; the text is otherwise unchanged
                self.assertEqual(agents.read_bytes(), (original + '\n').encode())
            settings = json.loads((self.claude / 'settings.json').read_text())
            # the user's own rules stay; lists that only ARDA's rules filled are removed again
            self.assertEqual(settings, {'model': 'é', 'permissions': {'allow': ['Bash(ls)']}})
            self.assertIn('"é"', (self.claude / 'settings.json').read_text())

    def test_symlinked_and_dangling_paths_are_written_through(self):
        target = Path(self.tmp.name) / 'elsewhere'
        target.mkdir()
        (self.claude / 'rules').symlink_to(target)
        dangling = Path(self.tmp.name) / 'agents-target.md'
        (self.codex / 'AGENTS.md').unlink()
        (self.codex / 'AGENTS.md').symlink_to(dangling)
        self.assertEqual(self.run_cli('trust', '--yes')[0], 0)
        self.assertTrue((target / 'arda.md').exists())
        self.assertTrue((self.codex / 'AGENTS.md').is_symlink())
        self.assertIn('arda-trust:begin', dangling.read_text())
        self.assertEqual(self.run_cli('trust', '--revoke', '--yes')[0], 0)
        self.assertFalse((target / 'arda.md').exists())
        self.assertTrue((self.claude / 'rules').is_symlink())

    def test_a_user_file_quoting_arda_is_not_taken_for_arda_s_own(self):
        rules = self.claude / 'rules' / 'arda.md'
        rules.parent.mkdir()
        rules.write_text('# My notes\nARDA says: ' + trust.OWNED + '\n')
        self.assertEqual(self.run_cli('trust', '--yes')[0], 2)
        self.assertIn('My notes', rules.read_text())

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
        self.assertEqual(settings['permissions']['deny'], ['Bash(arda trust)', 'Bash(arda trust *)',
                                                           f'Bash({SCRIPT} trust)', f'Bash({SCRIPT} trust *)'])
        self.assertIn('decision="forbidden"', (self.codex / 'rules' / 'arda.rules').read_text())
        self.assertIn(json.dumps([str(SCRIPT)]), (self.codex / 'rules' / 'arda.rules').read_text())
        agents = (self.codex / 'AGENTS.md').read_text()
        self.assertTrue(agents.startswith('# My own instructions\n\n<!-- arda-trust:begin -->'))
        self.assertEqual(agents.count('arda-trust:begin'), 1)
        self.assertNotIn('older', self.run_cli('trust', '--status')[1])
        older = trust.CODEX_RULES.split('\n', 1)[0] + '\n# ' + trust.OWNED + ' (an older version)\n'
        (self.codex / 'rules' / 'arda.rules').write_text(older)
        self.assertIn('installed by an older arda trust', self.run_cli('trust', '--status')[1])
        self.run_cli('trust', '--yes')

        self.assertEqual(self.run_cli('trust', '--revoke', '--yes')[0], 0)
        self.assertFalse((self.claude / 'rules' / 'arda.md').exists())
        self.assertFalse((self.codex / 'rules' / 'arda.rules').exists())
        self.assertEqual(self.settings(), {'model': 'x', 'permissions': {'allow': ['Bash(ls)']}})
        self.assertEqual((self.codex / 'AGENTS.md').read_text(), '# My own instructions\n')

    def test_codex_override_file_takes_the_section_when_codex_reads_it(self):
        (self.codex / 'AGENTS.override.md').write_text('# Override\n')
        self.run_cli('trust', '--yes')
        self.assertIn('arda-trust:begin', (self.codex / 'AGENTS.override.md').read_text())
        self.assertNotIn('arda-trust', (self.codex / 'AGENTS.md').read_text())

    def test_an_agent_cannot_grant_itself_trust(self):
        self.env['HERDR_PANE_ID'] = 'w1:p1'  # claude's pane in the fake session
        for extra in ([], ['--session', 'anything']):
            code, _, err = self.run_cli('trust', '--yes', *extra)
            self.assertEqual(code, 2, extra)
            self.assertIn('not by an agent', err)
        with mock.patch('arda.cli._under_herdr', return_value=True):  # inside Herdr, pane variable removed
            self.assertEqual(self.run_cli('trust', '--yes', env={'HERDR_PANE_ID': None})[0], 2)
        self.set_agents(agent('claude', 'w1:p1'), shell_pid=999999999)  # names a pane it is not running in
        self.env['HERDR_PANE_ID'] = 'w1:p9'
        self.assertEqual(self.run_cli('trust', '--yes')[0], 2)
        self.assertFalse((self.claude / 'rules').exists())
        self.assertFalse((self.codex / 'rules').exists())

    def test_a_terminal_outside_herdr_may_grant_trust(self):
        with mock.patch('arda.cli._under_herdr', return_value=False):
            self.assertEqual(self.run_cli('trust', '--yes', env={'HERDR_PANE_ID': None})[0], 0)

    def test_marked_section_is_found_only_when_intact(self):
        agents = self.codex / 'AGENTS.md'
        agents.write_text('# Mine\nI mention <!-- arda-trust:begin --> inline.\n')
        self.run_cli('trust', '--yes')
        self.run_cli('trust', '--revoke', '--yes')
        self.assertEqual(agents.read_text(), '# Mine\nI mention <!-- arda-trust:begin --> inline.\n')
        for broken in ('a\n<!-- arda-trust:end -->\nb\n<!-- arda-trust:begin -->\n',
                       '<!-- arda-trust:begin -->\nx\n<!-- arda-trust:begin -->\n<!-- arda-trust:end -->\n'):
            agents.write_text(broken)
            self.assertEqual(self.run_cli('trust', '--yes')[0], 2)
            self.assertEqual(agents.read_text(), broken)
            self.assertFalse((self.claude / 'rules' / 'arda.md').exists())

    def test_files_arda_did_not_write_are_left_alone(self):
        foreign = self.claude / 'rules' / 'arda.md'
        foreign.parent.mkdir()
        foreign.write_text('my own notes about arda\n')
        self.assertEqual(self.run_cli('trust', '--yes')[0], 2)
        self.run_cli('trust', '--revoke', '--yes')
        self.assertEqual(foreign.read_text(), 'my own notes about arda\n')

    def test_symlinked_settings_are_updated_in_place(self):
        real = Path(self.tmp.name) / 'dotfiles-settings.json'
        real.write_text(json.dumps({'permissions': {'allow': []}}))
        os.chmod(real, 0o600)
        link = self.claude / 'settings.json'
        link.unlink()
        link.symlink_to(real)
        self.assertEqual(self.run_cli('trust', '--yes')[0], 0)
        self.assertTrue(link.is_symlink())
        self.assertIn('Bash(arda *)', json.loads(real.read_text())['permissions']['allow'])
        self.assertEqual(real.stat().st_mode & 0o777, 0o600)

    def test_unexpected_settings_stop_the_change_before_anything_is_written(self):
        for bad in ('[]', '{not json', '{"permissions": []}', '{"permissions": {"allow": "x"}}',
                    '{"permissions": {"deny": {}}}'):
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
        # raises unless Codex allows arda and forbids `arda trust` with these rules
        trust._check_codex_rules(trust.CODEX_RULES.format(paths=json.dumps([str(SCRIPT)])), SCRIPT)
        with self.assertRaises(trust.TrustError):
            trust._check_codex_rules('prefix_rule(pattern=["arda"], decision="allow")\n', SCRIPT)


if __name__ == '__main__':
    unittest.main()
