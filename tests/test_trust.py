import json
import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

import isolation
from test_cli import CliCase, agent

from arda import trust
from arda.cli import ROOT, SCRIPT, trust_main

WINDOWS = sys.platform == 'win32'
if WINDOWS:  # arda-trust writes bin/arda.exe; the tests' copy goes to a temporary root, never the checkout
    SCRIPT = Path(isolation._ROOT) / 'install' / 'bin' / 'arda.exe'
TRUST = trust.trust_script(SCRIPT)
PATHS = [str(SCRIPT), *([SCRIPT.as_posix()] if WINDOWS else [])]  # Windows: also the forward-slash form
EXE = '.exe' if WINDOWS else ''


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
                        PATH=os.pathsep.join(['/usr/bin', '/bin']))
        # Whatever the test runner itself runs in, never consult a real Herdr server.
        under_herdr = mock.patch('arda.cli._under_herdr', return_value=None)
        under_herdr.start()
        self.addCleanup(under_herdr.stop)
        if WINDOWS:  # each test starts without arda.exe, which is in the tests' temporary root
            self.addCleanup(SCRIPT.unlink, missing_ok=True)
        script = mock.patch('arda.cli.SCRIPT', SCRIPT)
        script.start()
        self.addCleanup(script.stop)

    def run_trust(self, *argv, **options):
        return self.run_cli(*argv, entry=trust_main, **options)

    def settings(self):
        return json.loads((self.claude / 'settings.json').read_text())

    def test_revoke_leaves_no_empty_traces(self):
        (self.claude / 'settings.json').write_text(json.dumps({'model': 'x'}))
        self.run_trust('--yes')
        self.run_trust('--revoke', '--yes')
        self.assertEqual(self.settings(), {'model': 'x'})
        self.assertFalse((self.claude / 'rules' / 'arda.md').exists())
        self.assertFalse((self.codex / 'rules' / 'arda.rules').exists())

    def test_grant_then_revoke_restores_files_byte_for_byte(self):
        shapes = ['# Mine\r\nCRLF line\r\n', '# Mine\n\n\n', '# Mine\nno final newline', '']
        for original in shapes:
            agents = self.codex / 'AGENTS.md'
            agents.write_bytes(original.encode())
            (self.claude / 'settings.json').write_text('{"model": "é", "permissions": {"allow": ["Bash(ls)"]}}')
            self.run_trust('--yes')
            if '\r\n' in original:
                self.assertNotIn(b'\n<!--', agents.read_bytes().replace(b'\r\n', b''))
            self.run_trust('--revoke', '--yes')
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
        self.assertEqual(self.run_trust('--yes')[0], 0)
        self.assertTrue((target / 'arda.md').exists())
        self.assertTrue((self.codex / 'AGENTS.md').is_symlink())
        self.assertIn('arda-trust:begin', dangling.read_text())
        self.assertEqual(self.run_trust('--revoke', '--yes')[0], 0)
        self.assertFalse((target / 'arda.md').exists())
        self.assertTrue((self.claude / 'rules').is_symlink())

    def test_a_user_file_quoting_arda_is_not_taken_for_arda_s_own(self):
        rules = self.claude / 'rules' / 'arda.md'
        rules.parent.mkdir()
        rules.write_text('# My notes\nARDA says: ' + trust.OWNED + '\n')
        self.assertEqual(self.run_trust('--yes')[0], 2)
        self.assertIn('My notes', rules.read_text())

    def test_without_yes_nothing_changes(self):
        code, out, _ = self.run_trust()
        self.assertEqual(code, 0)
        self.assertIn('Nothing was changed.', out)
        self.assertFalse((self.claude / 'rules' / 'arda.md').exists())
        self.assertFalse((self.codex / 'rules' / 'arda.rules').exists())
        self.assertEqual(self.settings()['permissions']['allow'], ['Bash(ls)'])

    def test_grant_is_idempotent_and_revoke_removes_only_what_it_added(self):
        self.assertEqual(self.run_trust('--yes')[0], 0)
        self.assertEqual(self.run_trust('--yes')[0], 0)
        rules = (self.claude / 'rules' / 'arda.md').read_text()
        self.assertIn('not from me', rules)
        self.assertIn('arda reject', rules)
        settings = self.settings()
        self.assertEqual(settings['model'], 'x')
        self.assertEqual(settings['permissions']['allow'], ['Bash(ls)', 'Bash(arda *)',
                                                            *[f'Bash({path} *)' for path in PATHS]])
        self.assertEqual(settings['permissions']['deny'][:4], ['Bash(arda-trust)', 'Bash(arda-trust *)',
                                                               f'Bash({TRUST})', f'Bash({TRUST} *)'])
        self.assertIn('decision="forbidden"', (self.codex / 'rules' / 'arda.rules').read_text())
        self.assertIn(json.dumps(PATHS), (self.codex / 'rules' / 'arda.rules').read_text())
        agents = (self.codex / 'AGENTS.md').read_text()
        self.assertTrue(agents.startswith('# My own instructions\n\n<!-- arda-trust:begin -->'))
        self.assertEqual(agents.count('arda-trust:begin'), 1)
        self.assertNotIn('older', self.run_trust('--status')[1])
        older = trust.CODEX_RULES.split('\n', 1)[0] + '\n# ' + trust.OWNED + ' (an older version)\n'
        (self.codex / 'rules' / 'arda.rules').write_text(older)
        self.assertIn('installed by an older ARDA', self.run_trust('--status')[1])
        self.run_trust('--yes')

        self.assertEqual(self.run_trust('--revoke', '--yes')[0], 0)
        self.assertFalse((self.claude / 'rules' / 'arda.md').exists())
        self.assertFalse((self.codex / 'rules' / 'arda.rules').exists())
        self.assertEqual(self.settings(), {'model': 'x', 'permissions': {'allow': ['Bash(ls)']}})
        self.assertEqual((self.codex / 'AGENTS.md').read_text(), '# My own instructions\n')

    def test_arda_itself_never_changes_trust(self):
        for argv in (['trust'], ['trust', '--yes'], ['--', 'trust', '--yes'], ['trust', '--revoke', '--yes', '--json']):
            code, _, err = self.run_cli(*argv)
            self.assertEqual(code, 2, argv)
            self.assertIn('run `arda-trust` yourself', err)
        self.assertFalse((self.claude / 'rules').exists())
        self.assertNotIn('arda-trust', (self.codex / 'AGENTS.md').read_text())

    def test_an_install_by_the_old_arda_trust_is_upgraded_and_revoked_cleanly(self):
        legacy = trust.LEGACY_OWNED
        (self.claude / 'rules').mkdir()
        (self.claude / 'rules' / 'arda.md').write_text(trust.CLAUDE_RULES.replace(trust.OWNED, legacy))
        old_deny = [f'Bash({name} trust)' for name in ('arda', SCRIPT)] + [f'Bash({name} trust *)'
                                                                         for name in ('arda', SCRIPT)]
        (self.claude / 'settings.json').write_text(json.dumps(
            {'permissions': {'allow': ['Bash(ls)', 'Bash(arda *)'], 'deny': ['Bash(rm *)', *old_deny]}}))
        self.assertIn('installed by an older ARDA', self.run_trust('--status')[1])
        self.assertEqual(self.run_trust('--yes')[0], 0)
        deny = self.settings()['permissions']['deny']
        self.assertEqual([rule for rule in old_deny if rule in deny], [])
        self.assertIn('Bash(rm *)', deny)
        self.assertIn('Bash(arda-trust *)', deny)
        self.assertNotIn(legacy, (self.claude / 'rules' / 'arda.md').read_text())
        self.assertEqual(self.run_trust('--revoke', '--yes')[0], 0)
        self.assertEqual(self.settings(), {'permissions': {'allow': ['Bash(ls)'], 'deny': ['Bash(rm *)']}})

    def test_a_planted_staging_link_cannot_redirect_a_write(self):
        victim = Path(self.tmp.name) / 'unrelated.txt'
        victim.write_text('keep me\n')
        (self.codex / 'AGENTS.md.arda-tmp').symlink_to(victim)  # the old, predictable staging name
        self.assertEqual(self.run_trust('--yes')[0], 0)
        self.assertEqual(victim.read_text(), 'keep me\n')
        self.assertFalse((self.codex / 'AGENTS.md').is_symlink())
        self.assertIn('arda-trust:begin', (self.codex / 'AGENTS.md').read_text())
        self.assertEqual([p.name for p in self.codex.iterdir() if p.name.endswith('.arda-tmp') and not p.is_symlink()],
                         [])  # no staging file left behind

    def test_grant_refuses_when_the_arda_on_path_is_another_install(self):
        bindir = Path(self.tmp.name) / 'bin'
        bindir.mkdir()
        (bindir / f'arda{EXE}').symlink_to(sys.executable if WINDOWS else '/bin/true')  # anything else named arda
        code, _, err = self.run_trust('--yes', env={'PATH': os.pathsep.join([str(bindir), '/usr/bin', '/bin'])})
        self.assertEqual(code, 2)
        self.assertIn('is not this installation', err)
        self.assertFalse((self.claude / 'rules').exists())

    def test_rules_from_a_moved_or_older_install_are_cleaned_up_and_user_rules_kept(self):
        old = ['Bash(/old/root/bin/arda *)', 'Bash(/old/root/bin/arda trust)', 'Bash(/old/root/bin/arda trust *)']
        (self.claude / 'settings.json').write_text(json.dumps({'permissions': {
            'allow': ['Bash(ls)', old[0], 'Bash(ardavark *)'], 'deny': ['Bash(rm *)', *old[1:]]}}))
        self.assertIn('rules for another ARDA install', self.run_trust('--status')[1])
        self.assertEqual(self.run_trust('--yes')[0], 0)
        permissions = self.settings()['permissions']
        self.assertEqual([rule for rule in old if rule in permissions['allow'] + permissions['deny']], [])
        self.assertIn('Bash(ardavark *)', permissions['allow'])
        self.assertEqual(self.run_trust('--revoke', '--yes')[0], 0)
        self.assertEqual(self.settings(), {'permissions': {'allow': ['Bash(ls)', 'Bash(ardavark *)'],
                                                           'deny': ['Bash(rm *)']}})

    def test_a_path_link_outside_a_bin_directory_is_revoked_too(self):
        commands = Path(self.tmp.name) / 'commands'
        commands.mkdir()
        SCRIPT.parent.mkdir(parents=True, exist_ok=True)
        SCRIPT.touch()  # the link's target, as on Linux; on Windows arda-trust writes the real one over it
        (commands / f'arda{EXE}').symlink_to(SCRIPT)
        path = {'PATH': os.pathsep.join([str(commands), '/usr/bin', '/bin'])}
        self.assertEqual(self.run_trust('--yes', env=path)[0], 0)
        self.assertIn(f'Bash({commands / f"arda{EXE}"} *)', self.settings()['permissions']['allow'])
        self.assertEqual(self.run_trust('--revoke', '--yes')[0], 0)  # even with the link no longer on PATH
        self.assertEqual(self.settings()['permissions'], {'allow': ['Bash(ls)']})

    def test_only_rule_shapes_arda_wrote_are_touched(self):
        spaced = 'Bash(/old root/bin/arda *)'
        (self.claude / 'settings.json').write_text(json.dumps({'permissions': {
            'allow': [spaced, 'Bash(ls)'], 'deny': ['Bash(arda *)', 'Bash(/old root/bin/arda trust *)']}}))
        self.assertEqual(self.run_trust('--yes')[0], 0)
        permissions = self.settings()['permissions']
        self.assertNotIn(spaced, permissions['allow'])                    # an old root with a space
        self.assertNotIn('Bash(/old root/bin/arda trust *)', permissions['deny'])
        self.assertIn('Bash(arda *)', permissions['deny'])                 # the user's own deny: never ARDA's
        self.assertEqual(self.run_trust('--revoke', '--yes')[0], 0)
        self.assertEqual(self.settings(), {'permissions': {'allow': ['Bash(ls)'], 'deny': ['Bash(arda *)']}})

    def test_consent_follows_the_instruction_file_codex_reads(self):
        agents, override = self.codex / 'AGENTS.md', self.codex / 'AGENTS.override.md'
        self.assertEqual(self.run_trust('--yes')[0], 0)
        override.write_text('# Override\n')  # Codex now reads this file instead
        self.assertIn('which Codex does not read now', self.run_trust('--status')[1])
        self.assertEqual(self.run_trust('--yes')[0], 0)  # the section moves
        self.assertIn('arda-trust:begin', override.read_text())
        self.assertEqual(agents.read_text(), '# My own instructions\n')
        override.write_text('# Override\n')
        self.run_trust('--yes')
        override.write_text(override.read_text())  # unchanged; now revoke with both present
        agents.write_text(agents.read_text() + '\n' + trust.CODEX_BLOCK)  # a stray section left elsewhere
        self.assertEqual(self.run_trust('--revoke', '--yes')[0], 0)
        self.assertNotIn('arda-trust', agents.read_text() + override.read_text())

    def integrations(self):
        return json.loads(self.state_path.read_text()).get('integrations', [])

    def test_granting_also_installs_herdrs_integrations_and_revoke_keeps_them(self):
        code, out, _ = self.run_trust()
        self.assertIn('install Herdr\'s codex integration (herdr integration install codex)', out)
        self.assertEqual(self.integrations(), [])  # a plan changes nothing
        code, out, _ = self.run_trust('--yes')
        self.assertEqual(code, 0)
        self.assertEqual(sorted(self.integrations()), ['claude', 'codex'])
        self.assertIn('Codex asks once to review this hook', out)
        self.assertIn('codex integration: current', self.run_trust('--status')[1])
        code, out, _ = self.run_trust('--revoke', '--yes')
        self.assertEqual(sorted(self.integrations()), ['claude', 'codex'])  # Herdr's, left installed
        self.assertIn('herdr integration uninstall', out)

    def test_integrations_can_be_left_out(self):
        self.assertEqual(self.run_trust('--yes', '--no-integrations')[0], 0)
        self.assertEqual(self.integrations(), [])

    def snapshot(self):
        return {path: path.read_bytes() for home in (self.claude, self.codex) for path in home.rglob('*')
                if path.is_file()}

    def test_arda_setup_only_shows_the_plan_and_the_command(self):
        before = self.snapshot()
        code, out, _ = self.run_cli('setup', '--json')  # arda itself, from an agent's pane: read-only
        data = json.loads(out)
        self.assertEqual((code, data['ready']), (0, False))
        self.assertRegex(data['command'], r'arda-trust(\.py")? --yes$')  # Windows: py -I "...\arda-trust.py" --yes
        self.assertEqual(self.snapshot(), before)
        text = self.run_cli('setup')[1]
        self.assertIn('Run it yourself in a plain terminal', text)
        self.assertIn("install Herdr's codex integration", text)
        self.run_trust('--yes')
        code, out, _ = self.run_cli('setup', '--json')
        self.assertTrue(json.loads(out)['ready'])
        self.assertNotIn('Run it yourself', self.run_cli('setup')[1])

    def test_the_setup_skill_cannot_be_invoked_by_the_model(self):
        skill = (ROOT / 'skills' / 'arda-setup' / 'SKILL.md').read_text()
        self.assertIn('disable-model-invocation: true', skill.split('---')[1])
        self.assertIn('arda setup', skill)

    def test_the_peers_skill_is_user_invoked_and_only_lists(self):
        skill = (ROOT / 'skills' / 'arda-peers' / 'SKILL.md').read_text()
        front = skill.split('---')[1]
        self.assertIn('name: arda-peers', front)
        self.assertIn('disable-model-invocation: true', front)
        self.assertIn('Run `arda peers`', skill)

    def test_user_invoked_skills_are_explicit_only_in_codex_too(self):
        for name in ('arda-peers', 'arda-setup'):
            policy = (ROOT / 'skills' / name / 'agents' / 'openai.yaml').read_text()
            self.assertIn('policy:\n  allow_implicit_invocation: false', policy, name)
            self.assertIn(f'${name}', policy, name)

    def test_codex_override_file_takes_the_section_when_codex_reads_it(self):
        (self.codex / 'AGENTS.override.md').write_text('# Override\n')
        self.run_trust('--yes')
        self.assertIn('arda-trust:begin', (self.codex / 'AGENTS.override.md').read_text())
        self.assertNotIn('arda-trust', (self.codex / 'AGENTS.md').read_text())

    def test_an_agent_cannot_grant_itself_trust(self):
        self.env['HERDR_PANE_ID'] = 'w1:p1'  # claude's pane in the fake session
        code, _, err = self.run_trust('--yes')
        self.assertEqual(code, 2)
        self.assertIn('not by an agent', err)
        self.assertEqual(self.run_trust('--yes', '--session', 'anything')[0], 2)  # no way to point it elsewhere
        with mock.patch('arda.cli._under_herdr', return_value=True):  # inside Herdr, pane variable removed
            self.assertEqual(self.run_trust('--yes', env={'HERDR_PANE_ID': None})[0], 2)
        self.set_agents(agent('claude', 'w1:p1'), shell_pid=999999999)  # names a pane it is not running in
        self.env['HERDR_PANE_ID'] = 'w1:p9'
        self.assertEqual(self.run_trust('--yes')[0], 2)
        self.assertFalse((self.claude / 'rules').exists())
        self.assertFalse((self.codex / 'rules').exists())

    def test_a_terminal_outside_herdr_may_grant_trust(self):
        with mock.patch('arda.cli._under_herdr', return_value=False):
            self.assertEqual(self.run_trust('--yes', env={'HERDR_PANE_ID': None})[0], 0)

    def test_marked_section_is_found_only_when_intact(self):
        agents = self.codex / 'AGENTS.md'
        agents.write_text('# Mine\nI mention <!-- arda-trust:begin --> inline.\n')
        self.run_trust('--yes')
        self.run_trust('--revoke', '--yes')
        self.assertEqual(agents.read_text(), '# Mine\nI mention <!-- arda-trust:begin --> inline.\n')
        for broken in ('a\n<!-- arda-trust:end -->\nb\n<!-- arda-trust:begin -->\n',
                       '<!-- arda-trust:begin -->\nx\n<!-- arda-trust:begin -->\n<!-- arda-trust:end -->\n'):
            agents.write_text(broken)
            self.assertEqual(self.run_trust('--yes')[0], 2)
            self.assertEqual(agents.read_text(), broken)
            self.assertFalse((self.claude / 'rules' / 'arda.md').exists())

    def test_files_arda_did_not_write_are_left_alone(self):
        foreign = self.claude / 'rules' / 'arda.md'
        foreign.parent.mkdir()
        foreign.write_text('my own notes about arda\n')
        self.assertEqual(self.run_trust('--yes')[0], 2)
        self.run_trust('--revoke', '--yes')
        self.assertEqual(foreign.read_text(), 'my own notes about arda\n')

    def test_symlinked_settings_are_updated_in_place(self):
        real = Path(self.tmp.name) / 'dotfiles-settings.json'
        real.write_text(json.dumps({'permissions': {'allow': []}}))
        os.chmod(real, 0o600)
        link = self.claude / 'settings.json'
        link.unlink()
        link.symlink_to(real)
        self.assertEqual(self.run_trust('--yes')[0], 0)
        self.assertTrue(link.is_symlink())
        self.assertIn('Bash(arda *)', json.loads(real.read_text())['permissions']['allow'])
        if not WINDOWS:  # Windows file modes have no permission bits to keep
            self.assertEqual(real.stat().st_mode & 0o777, 0o600)

    def test_unexpected_settings_stop_the_change_before_anything_is_written(self):
        for bad in ('[]', '{not json', '{"permissions": []}', '{"permissions": {"allow": "x"}}',
                    '{"permissions": {"deny": {}}}'):
            (self.claude / 'settings.json').write_text(bad)
            self.assertEqual(self.run_trust('--yes')[0], 2, bad)
            self.assertEqual((self.claude / 'settings.json').read_text(), bad)
            self.assertFalse((self.claude / 'rules' / 'arda.md').exists(), bad)
            self.assertFalse((self.codex / 'rules' / 'arda.rules').exists(), bad)

    def test_missing_harness_directories_are_skipped(self):
        shutil.rmtree(self.codex)
        self.run_trust('--yes')
        self.assertFalse(self.codex.exists())
        self.assertTrue((self.claude / 'rules' / 'arda.md').exists())

    @unittest.skipUnless(WINDOWS, 'bin/arda.exe exists on Windows only')
    def test_windows_grant_writes_the_arda_command_and_revoke_keeps_it(self):
        code, out, _ = self.run_trust()
        self.assertIn(f'arda: write {SCRIPT}, which runs ARDA with {sys.executable}', out)
        self.assertFalse(SCRIPT.exists())  # a plan changes nothing
        self.assertEqual(self.run_trust('--yes')[0], 0)
        self.assertEqual(SCRIPT.read_bytes(), trust.launcher(SCRIPT))
        self.assertIn(f'arda: {SCRIPT}: installed', self.run_trust('--status')[1])
        SCRIPT.write_bytes(b'an arda.exe for another Python')
        self.assertIn('for another Python or install', self.run_trust('--status')[1])
        self.assertEqual(self.run_trust('--revoke', '--yes')[0], 0)
        self.assertTrue(SCRIPT.exists())  # the command stays; without trust it asks for approval like any other

    @unittest.skipUnless(shutil.which('codex'), 'codex is not installed')
    def test_codex_accepts_the_generated_rules(self):
        # raises unless Codex allows arda and forbids `arda-trust` with these rules
        trust._check_codex_rules(trust.CODEX_RULES.format(paths=json.dumps(PATHS),
                                                          trust_paths=json.dumps(trust.trust_host_paths(SCRIPT))),
                                 SCRIPT)
        with self.assertRaises(trust.TrustError):
            trust._check_codex_rules('prefix_rule(pattern=["arda"], decision="allow")\n', SCRIPT)


if __name__ == '__main__':
    unittest.main()
