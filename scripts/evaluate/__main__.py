"""python -m core.scripts.evaluate --case <name>"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from scripts.evaluate.audit import main

if __name__ == "__main__":
    raise SystemExit(main())
