"""저장소 루트용 래퍼 — python scripts/collect_rtms.py [--budget 1000] [--kinds apt_rent] [--no-apply] [--status]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.collect_rtms import main

if __name__ == "__main__":
    raise SystemExit(main())
