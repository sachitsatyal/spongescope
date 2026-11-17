"""Put app/ on the import path.

The Streamlit app imports `data` as a sibling, because that is how `streamlit run` resolves
imports. The tests import the same module under the same name so there is exactly one import
path for it, rather than the app and the tests loading two copies under different names.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
