"""Sync reviewed JSON into the separately deployed Render root (backend).

Run after editing knowledge.json, policies.json, or policy-history.json in frontend/data.
Use --check in CI to catch stale deploy copies; never requests external data.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("knowledge.json", "policies.json", "policy-history.json", "warning.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for name in FILES:
        source = ROOT / "frontend" / "data" / name
        target = ROOT / "backend" / "data" / name
        payload = source.read_bytes()
        json.loads(payload)
        if not target.exists() or target.read_bytes() != payload:
            if args.check:
                stale.append(name)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                print(f"Synced: {name}")
    if stale:
        raise SystemExit(f"Stale deploy data: {', '.join(stale)}. Run python scripts/sync_qualitative_data.py")
    print("Deploy content is synchronized.")


if __name__ == "__main__":
    main()
