"""Makes bare imports (`import catalog_cache`, `import search_studies`,
etc.) resolve during tests, matching the bare-import convention used
throughout this project (see pipeline/conftest.py) -- and matching how the
real Lambda deployment actually runs: the zip's root directory (this
directory's contents) is what's on sys.path, so a module in tools/ can
still bare-import a sibling module from the root (e.g.
tools/search_studies.py does `from catalog_cache import get_catalog`).
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tools"))
