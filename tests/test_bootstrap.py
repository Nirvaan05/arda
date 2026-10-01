import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ARDA = Path(__file__).resolve().parent.parent / 'bin' / 'arda'


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


if __name__ == '__main__':
    unittest.main()
