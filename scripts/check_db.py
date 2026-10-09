"""Repository-root wrapper: python scripts/check_db.py [--init]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.check_db import main

if __name__ == "__main__":
    raise SystemExit(main())
