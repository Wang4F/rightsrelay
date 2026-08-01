from __future__ import annotations

import sys
from pathlib import Path

# Keep the suite runnable from a Unicode Windows workspace even when an
# editable-install .pth file is written by a tool that assumes an ANSI codepage.
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
