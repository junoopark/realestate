"""Repository-root convenience wrapper: python scripts/collect_rone.py [--full] [--include-legacy]."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.collect_rone import main

if __name__ == "__main__":
    raise SystemExit(main())
