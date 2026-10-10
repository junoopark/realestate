"""Member CSV fidelity and spreadsheet-formula safety checks."""
import csv
import importlib.util
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("member_exports", ROOT / "scripts/build_member_downloads.py")
exports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exports)


def test_csv_is_current_and_preserves_numeric_observations():
    generated = exports.build_exports()
    for name, payload in generated.items():
        if name.endswith(".csv"):
            assert payload.startswith(b"\xef\xbb\xbf")
        assert (exports.OUTPUT / name).read_bytes() == payload
    rows = list(csv.DictReader(io.StringIO(generated["member-downloads/factor-sample.csv"].decode("utf-8-sig"))))
    sample = json.loads((ROOT / "frontend/data/factor_sample.json").read_text(encoding="utf-8"))
    first = sample["metrics"][0]
    region = next(iter(first["series"]))
    assert rows[0]["변수ID"] == first["var"]
    assert rows[0]["지역"] == region
    assert float(rows[0]["값"]) == first["series"][region][0]
    assert len(rows) == sum(len(values) for metric in sample["metrics"] for values in metric["series"].values())


def test_csv_text_cannot_execute_formulas_but_negative_numbers_stay_numeric():
    payload = exports.csv_bytes(["text", "number"], [
        ['=HYPERLINK("https://example.invalid")', -3.25],
        ["  +SUM(1,2)", None], ["@SUM(1,2)", 0], ["\t=1+1", 1],
    ])
    rows = list(csv.reader(io.StringIO(payload.decode("utf-8-sig"))))[1:]
    assert all(row[0].startswith("'") for row in rows)
    assert rows[0][1] == "-3.25"
    assert rows[1][1] == ""
