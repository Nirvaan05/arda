import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import isolation  # noqa: F401  (before any test runs: keeps tests away from real Herdr)

ARDA = Path(__file__).resolve().parent.parent / 'bin' / 'arda'
TRUST = ARDA.with_name('arda-trust')


class BootstrapTests(unittest.TestCase):
    def test_status_reports_plugin_and_protocol(self):
        proc = subprocess.run(['python3', '-m', 'arda', 'status', '--json'], capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['protocol'], 'arda/1')

    def test_wrapper_ignores_a_shadowing_package_in_the_current_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'arda'
            fake.mkdir()
            (fake / '__init__.py').write_text('')
            (fake / '__main__.py').write_text('print("SHADOWED")\n')
            (fake / 'cli.py').write_text('def main():\n    print("SHADOWED")\n')
            proc = subprocess.run([str(ARDA), 'status', '--json'], cwd=tmp, capture_output=True, text=True,
                                  check=False, env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': tmp})
        self.assertNotIn('SHADOWED', proc.stdout)
        self.assertEqual(json.loads(proc.stdout)['protocol'], 'arda/1')

    def test_the_approved_commands_run_no_code_the_caller_chooses(self):
        # Agents may run `arda` outside their sandbox, so nothing in the caller's environment may make it
        # run other code: Python start-up hooks, or other programs earlier on PATH (Codex review).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / 'ran'
            hook = f'open({str(marker)!r}, "a").write("hook\\n")\n'
            for name in ('sitecustomize.py', 'usercustomize.py', 'startup.py'):
                (root / name).write_text(hook)
            for tool in ('python3', 'readlink', 'dirname'):
                (root / tool).write_text(f'#!/bin/sh\necho {tool} >> {marker}\nexit 1\n')
                (root / tool).chmod(0o755)
            env = {'PATH': f'{tmp}:/usr/bin:/bin', 'PYTHONPATH': tmp, 'PYTHONSTARTUP': str(root / 'startup.py'),
                   'PYTHONUSERBASE': tmp, 'HOME': tmp, 'CLAUDE_CONFIG_DIR': str(root / 'claude'),
                   'CODEX_HOME': str(root / 'codex')}
            for argv in ([str(ARDA), 'status', '--json'], [str(TRUST), '--status', '--json']):
                proc = subprocess.run(argv, capture_output=True, text=True, check=False, env=env, cwd=tmp)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                json.loads(proc.stdout)
            self.assertFalse(marker.exists(), marker.read_text() if marker.exists() else '')

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


if __name__ == '__main__':
    unittest.main()
