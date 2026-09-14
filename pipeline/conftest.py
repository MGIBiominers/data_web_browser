"""Makes `import pipeline.<module>` resolve when pytest is run from inside
pipeline/ (as the repo's own test runner does) by putting this directory's
parent -- the one that actually contains the `pipeline` package -- on
sys.path.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
