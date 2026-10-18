"""저장소 루트용 래퍼 — python scripts/seed_indicators.py [--file 전처리본.json] [--status]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.seed_indicators import main

if __name__ == "__main__":
    raise SystemExit(main())
