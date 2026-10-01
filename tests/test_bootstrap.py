import json
import subprocess
import unittest


class BootstrapTests(unittest.TestCase):
    def test_status_reports_plugin_and_protocol(self):
        proc = subprocess.run(['python3', '-m', 'arda', 'status'], capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['protocol'], 'arda/1')
