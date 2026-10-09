# The user's own command for approving ARDA peer messages on Windows (see `arda-trust --help`):
#   py -I path\to\arda\bin\arda-trust.py --yes
# The Python that runs it is the one bin\arda.exe, which it writes, runs ARDA with. Like
# bin/arda-trust it refuses to run under any other name, and -I keeps the caller's
# environment and current directory out of Python's module search.
import sys
from pathlib import Path

if Path(sys.argv[0]).name != 'arda-trust.py':
    sys.exit('arda-trust: run it by its own name, arda-trust.py, yourself in a terminal')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from arda.cli import trust_main  # noqa: E402

raise SystemExit(trust_main())
