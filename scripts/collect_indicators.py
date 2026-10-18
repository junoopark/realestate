"""저장소 루트용 래퍼 — python scripts/collect_indicators.py [--vars V002] [--force] [--probe V002] [--status] [--export …]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.collect_indicators import main

if __name__ == "__main__":
    raise SystemExit(main())
