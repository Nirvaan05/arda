"""Keep every test away from real Herdr servers and real agent harnesses.

The test runner may itself run inside a Herdr pane (an agent running the tests). Its
environment then names a live Herdr server (HERDR_SOCKET_PATH) and real Herdr state, and a
test that reached them would type fixture messages into real agents. Imported first by
every test module: it removes the Herdr variables and points Herdr's config and state at
an empty temporary directory, so even a real `herdr` binary finds no server.
"""

import atexit
import os
import shutil
import tempfile

for _key in [key for key in os.environ if key.startswith('HERDR_')]:
    del os.environ[_key]
_ROOT = tempfile.mkdtemp(prefix='arda-tests-')
atexit.register(shutil.rmtree, _ROOT, True)
os.environ['XDG_CONFIG_HOME'] = os.path.join(_ROOT, 'config')
os.environ['XDG_STATE_HOME'] = os.path.join(_ROOT, 'state')
