"""Build authenticated CSV downloads from the dashboard's existing public sample.

The exported copies live only under the backend deploy root. This does not make
the public chart JSON confidential. --check checks reproducibility without writes.
"""
import argparse
import csv
import io
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "backend" / "data"


def safe_cell(value):
    """Neutralize spreadsheet formulas in text, preserving numeric observations."""
    if value is None:
        return ""
    if isinstance(value, (float, int)):
        if not math.isfinite(value):
            raise ValueError("Non-finite observations cannot be exported")
        return value
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def csv_bytes(header, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows([safe_cell(value) for value in row] for row in rows)
    return output.getvalue().encode("utf-8-sig")


def build_exports():
    sample = json.loads((ROOT / "frontend/data/factor_sample.json").read_text(encoding="utf-8"))
    dictionary = json.loads((ROOT / "frontend/data/drivers.json").read_text(encoding="utf-8"))
    rows = []
    for metric in sample["metrics"]:
        periods = metric["periods"]
        for region, values in metric["series"].items():
            if len(values) != len(periods):
                raise ValueError(f"Period/value length mismatch: {metric['var']}")
            for period, value in zip(periods, values):
                rows.append((metric["var"], metric["label"], region, period, value,
                             metric["unit"], metric["freq"], metric["scope"],
                             "잠정" if metric.get("provisional_from") and period >= metric["provisional_from"] else ""))
    drivers = {item["id"]: item["name"] for item in dictionary["drivers"]}
    columns = ("id", "name", "driver", "driver2", "role", "type", "sign", "lead",
               "leakage", "transform", "period", "freq", "release", "region", "source", "code")
    variable_rows = []
    for variable in dictionary["variables"]:
        row = dict(variable)
        for field in ("driver", "driver2"):
            row[field] = drivers.get(row.get(field), row.get(field))
        variable_rows.append([row.get(field) for field in columns])
    registry = {variable["id"]: {"id": variable["id"], "name": variable["name"], "driver": variable["driver"]}
                for variable in dictionary["variables"]}
    for metric in sample["metrics"]:
        registry.setdefault(metric["var"], {"id": metric["var"], "name": metric["label"], "driver": "overview"})
    return {
        "member-downloads/factor-sample.csv": csv_bytes(
            ["변수ID", "지표명", "지역", "기준시점", "값", "단위", "주기", "지역단위", "잠정여부"], rows),
        "member-downloads/variable-dictionary.csv": csv_bytes(
            ["변수ID", "변수명", "주동인", "보조동인", "역할", "유형", "예상부호", "선행기간",
             "누출위험", "변환", "수록기간", "주기", "공표시기", "지역범위", "출처", "통계코드"], variable_rows),
        "member-indicators.json": (json.dumps(list(sorted(registry.values(), key=lambda item: item["id"])),
                                                ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for filename, payload in build_exports().items():
        target = OUTPUT / filename
        if args.check:
            if not target.exists() or target.read_bytes() != payload:
                stale.append(filename)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            print(f"Built {filename}: {len(payload):,} bytes")
    if stale:
        raise SystemExit("Stale download files: " + ", ".join(stale) + ". Run python scripts/build_member_downloads.py")
    print("Member downloads are synchronized.")


if __name__ == "__main__":
    main()
