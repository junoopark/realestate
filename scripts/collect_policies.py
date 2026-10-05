"""Repository-root convenience wrapper; no scheduled or external writes by default."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.collect_policies import main

if __name__ == "__main__":
    raise SystemExit(main())
