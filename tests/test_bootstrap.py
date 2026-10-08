import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

import isolation  # noqa: F401  (before any test runs: keeps tests away from real Herdr)

from arda import trust

ROOT = Path(__file__).resolve().parent.parent
ARDA = ROOT / 'bin' / 'arda'
TRUST = ARDA.with_name('arda-trust')
WINDOWS = sys.platform == 'win32'


def hostile(tmp):
    """An environment that would run code from tmp if anything took Python, its hooks or helpers from it."""
    root = Path(tmp)
    marker = root / 'ran'
    hook = f'open({str(marker)!r}, "a").write("hook\\n")\n'
    for name in ('sitecustomize.py', 'usercustomize.py', 'startup.py'):
        (root / name).write_text(hook)
    for tool in ('python3', 'python', 'py', 'readlink', 'dirname'):
        (root / tool).write_text(f'#!/bin/sh\necho {tool} >> {marker}\nexit 1\n')
        (root / tool).chmod(0o755)
        if WINDOWS:
            shutil.copy(sys.executable, root / f'{tool}.exe')  # a python that runs the hooks above
    env = {'PATH': os.pathsep.join([tmp, '/usr/bin', '/bin']), 'PYTHONPATH': tmp,
           'PYTHONSTARTUP': str(root / 'startup.py'), 'PYTHONUSERBASE': tmp, 'HOME': tmp, 'USERPROFILE': tmp,
           'CLAUDE_CONFIG_DIR': str(root / 'claude'), 'CODEX_HOME': str(root / 'codex')}
    if WINDOWS:
        env['SYSTEMROOT'] = os.environ['SYSTEMROOT']  # Python on Windows cannot start without it
    return env, marker


def shadow(tmp):
    fake = Path(tmp) / 'arda'
    fake.mkdir()
    (fake / '__init__.py').write_text('')
    (fake / '__main__.py').write_text('print("SHADOWED")\n')
    (fake / 'cli.py').write_text('def main():\n    print("SHADOWED")\n')


class BootstrapTests(unittest.TestCase):
    def test_the_plugin_status_action_reports_plugin_and_protocol(self):
        manifest = tomllib.loads((ROOT / 'herdr-plugin.toml').read_text(encoding='utf-8'))
        platform = 'windows' if WINDOWS else 'linux'
        action = next(a for a in manifest['actions'] if a['title'] == 'ARDA status'
                      and platform in a.get('platforms', manifest['platforms']))
        proc = subprocess.run([*action['command'], '--json'], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['protocol'], 'arda/1')

    @unittest.skipIf(WINDOWS, 'bin/arda is the Linux command; Windows runs bin/arda.exe')
    def test_wrapper_ignores_a_shadowing_package_in_the_current_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            shadow(tmp)
            proc = subprocess.run([str(ARDA), 'status', '--json'], cwd=tmp, capture_output=True, text=True,
                                  check=False, env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': tmp})
        self.assertNotIn('SHADOWED', proc.stdout)
        self.assertEqual(json.loads(proc.stdout)['protocol'], 'arda/1')

    @unittest.skipIf(WINDOWS, 'bin/arda is the Linux command; Windows runs bin/arda.exe')
    def test_the_approved_commands_run_no_code_the_caller_chooses(self):
        # Agents may run `arda` outside their sandbox, so nothing in the caller's environment may make it
        # run other code: Python start-up hooks, or other programs earlier on PATH (Codex review).
        with tempfile.TemporaryDirectory() as tmp:
            env, marker = hostile(tmp)
            for argv in ([str(ARDA), 'status', '--json'], [str(TRUST), '--status', '--json']):
                proc = subprocess.run(argv, capture_output=True, text=True, check=False, env=env, cwd=tmp)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                json.loads(proc.stdout)
            self.assertFalse(marker.exists(), marker.read_text() if marker.exists() else '')

    @unittest.skipIf(WINDOWS, 'bin/arda-trust is the Linux command; Windows runs bin/arda-trust.py')
    def test_arda_trust_refuses_to_run_under_another_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            alias = Path(tmp) / 'arda'
            alias.symlink_to(TRUST)  # e.g. a PATH link named arda that the approval would cover
            claude = Path(tmp) / 'claude'
            claude.mkdir()
            proc = subprocess.run([str(alias), '--yes'], capture_output=True, text=True, check=False,
                                  env={'PATH': '/usr/bin:/bin', 'CLAUDE_CONFIG_DIR': str(claude),
                                       'CODEX_HOME': str(Path(tmp) / 'codex')})
            self.assertEqual(proc.returncode, 2)
            self.assertIn('run it by its own name', proc.stderr)
            self.assertEqual(list(claude.iterdir()), [])


@unittest.skipUnless(WINDOWS, 'bin/arda.exe exists on Windows only')
class WindowsLauncherTests(unittest.TestCase):
    """bin/arda.exe as arda-trust writes it, built here in a temporary directory, never in bin/."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='arda-launcher-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.exe = Path(self.tmp) / 'bin' / 'arda.exe'
        self.exe.parent.mkdir()
        self.exe.write_bytes(trust.launcher(self.exe))

    def test_the_launcher_ignores_a_shadowing_package_in_the_current_directory(self):
        shadow(self.tmp)
        proc = subprocess.run([str(self.exe), 'status', '--json'], cwd=self.tmp, capture_output=True, text=True,
                              check=False, env={**os.environ, 'PYTHONPATH': self.tmp})
        self.assertNotIn('SHADOWED', proc.stdout)
        self.assertEqual(json.loads(proc.stdout)['protocol'], 'arda/1')

    def test_the_approved_command_runs_no_code_the_caller_chooses(self):
        env, marker = hostile(self.tmp)
        proc = subprocess.run([str(self.exe), 'status', '--json'], capture_output=True, text=True, check=False,
                              env=env, cwd=self.tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        json.loads(proc.stdout)
        self.assertFalse(marker.exists(), marker.read_text() if marker.exists() else '')

    def test_message_text_reaches_arda_exactly_as_typed(self):
        # No cmd.exe between the caller and Python: quotes, & and %VAR% are text, not syntax.
        text = 'he said "hi & calc" %PATH% ^ | <x> \'q\''
        proc = subprocess.run([str(self.exe), 'send', '@nobody', '--', text], capture_output=True, text=True,
                              check=False, env={**os.environ, 'HERDR_PANE_ID': ''})
        self.assertNotIn('is not recognized', proc.stderr)
        self.assertEqual(proc.returncode, 2, proc.stderr)  # outside a pane: refused, with nothing run on the way

    def test_arda_trust_refuses_to_run_under_another_name(self):
        alias = Path(self.tmp) / 'arda.py'
        shutil.copy(ROOT / 'bin' / 'arda-trust.py', alias)  # e.g. a copy the approval of arda would cover
        claude = Path(self.tmp) / 'claude'
        claude.mkdir()
        proc = subprocess.run([sys.executable, '-I', str(alias), '--yes'], capture_output=True, text=True,
                              check=False, env={**os.environ, 'CLAUDE_CONFIG_DIR': str(claude),
                                                'CODEX_HOME': str(Path(self.tmp) / 'codex')})
        self.assertEqual(proc.returncode, 1)
        self.assertIn('run it by its own name', proc.stderr)
        self.assertEqual(list(claude.iterdir()), [])

    def test_arda_trust_runs_isolated_from_the_callers_environment(self):
        env, marker = hostile(self.tmp)
        proc = subprocess.run([sys.executable, '-I', str(ROOT / 'bin' / 'arda-trust.py'), '--status', '--json'],
                              capture_output=True, text=True, check=False, env=env, cwd=self.tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        json.loads(proc.stdout)
        self.assertFalse(marker.exists(), marker.read_text() if marker.exists() else '')


if __name__ == '__main__':
    unittest.main()
