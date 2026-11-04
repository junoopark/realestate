"""도쿄 정제 — 국토교통성 부동산가격지수 Excel (월, 열 위치 기반)."""

from __future__ import annotations

import pandas as pd

from ..netio import RawMissing


def clean(ctx, metas, source_id):
    p = ctx.raw / "jp_mlit" / "mlit_rppi_residential_latest.xlsx"
    if not p.exists():
        raise RawMissing("jp_mlit xlsx")
    out = {}
    for sid, m in metas.items():
        q = m["parse"]
        df = pd.read_excel(p, sheet_name=q["sheet"], header=None)
        dates = pd.to_datetime(df[0], errors="coerce")
        vals = pd.to_numeric(df[int(q["col"])], errors="coerce")
        ok = dates.notna() & vals.notna()
        out[sid] = pd.DataFrame({"period": dates[ok].dt.strftime("%Y-%m"), "value": vals[ok]}).drop_duplicates("period")
    return out
