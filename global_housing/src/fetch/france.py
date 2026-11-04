"""프랑스(파리).

fr_insee   INSEE BDM SDMX(키 불필요): Notaires-INSEE 기존주택 가격지수(파리 아파트, 프랑스 전체), 임대료 지수(파리 광역권)
fr_dvf     DVF(Demandes de valeurs foncières, geo-dvf) 파리(75) 거래 건별 — 아파트 ㎡ 단가
fr_loyers  Carte des loyers(생태전환부·ANIL, 광고 임대료 모형 추정) 코뮌별 아파트 ㎡당 월 임대료
"""

from __future__ import annotations

import gzip
import io

import pandas as pd

from ..netio import DataUnavailable

BDM = "https://bdm.insee.fr/series/sdmx/data/SERIES_BDM/{ids}"
INSEE_SERIES = {
    "010567012": "Indice des prix des logements anciens - Paris - Appartements - base 2015 - brute (trimestriel)",
    "010567059": "Indice des prix des logements anciens - France métropolitaine - Ensemble - base 2015 - CVS (trimestriel)",
    "010600352": "Indice des loyers - Secteur libre - Agglomération parisienne - base janvier 2019 (trimestriel)",
}
DVF = "https://files.data.gouv.fr/geo-dvf/latest/csv/{y}/departements/75.csv.gz"
DVF_YEARS = (2024, 2025)
# data.gouv.fr "Carte des loyers - indicateurs de loyers d'annonce par commune" — 아파트 전체 (연도별 리소스)
LOYERS_API = "https://www.data.gouv.fr/api/1/datasets/carte-des-loyers-indicateurs-de-loyers-dannonce-par-commune-en-2025/"


def fetch_insee(ctx, f, log):
    ids = "+".join(INSEE_SERIES)
    f.download("fr_insee", BDM.format(ids=ids), "insee_bdm_paris_series.xml",
               note="; ".join(f"{k}: {v}" for k, v in INSEE_SERIES.items()))
    log(f"  fr_insee {ids}")


def fetch_dvf(ctx, f, log):
    for y in DVF_YEARS:
        url = DVF.format(y=y)
        try:
            path = f.download("fr_dvf", url, f"dvf_75_{y}.csv.gz", to_cache=True)
        except DataUnavailable as exc:
            log(f"  ! fr_dvf {y}: {exc}")
            continue
        df = pd.read_csv(path, dtype=str, low_memory=False)
        # 아파트가 하나라도 들어간 매매(mutation)의 모든 행 — 주차장(Dépendance) 등이 함께 거래됐는지 정제 단계에서 판단
        ids = set(df.loc[(df["nature_mutation"] == "Vente") & (df["type_local"] == "Appartement"), "id_mutation"])
        sub = df[df["id_mutation"].isin(ids)]
        f.write_subset("fr_dvf", f"dvf_75_{y}_ventes_appartements.csv.gz", sub, url, path,
                       "nature_mutation=Vente 이고 Appartement 가 포함된 id_mutation 의 모든 행 (모든 열 유지)")
        log(f"  fr_dvf {y}: {len(sub)}행 (원본 {len(df)})")


def fetch_loyers(ctx, f, log):
    found = 0
    for year in (2025, 2024, 2023):
        api = f"https://www.data.gouv.fr/api/1/datasets/carte-des-loyers-indicateurs-de-loyers-dannonce-par-commune-en-{year}/"
        try:
            meta = f.get(api).json()
        except DataUnavailable:
            continue
        for res in meta.get("resources", []):
            title = (res.get("title") or "").lower()
            if res.get("format", "").lower() == "csv" and "appartement" in title and "pieces" not in title.replace("è", "e") \
                    and "t1" not in title and "t3" not in title:
                path = f.download("fr_loyers", res["url"], f"loyers_appartements_{year}.csv", to_cache=True)
                raw = path.read_bytes()
                text = None
                for enc in ("utf-8", "latin-1"):
                    try:
                        text = raw.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                sep = ";" if text.count(";") > text.count(",") else ","
                df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str)
                code_col = next(c for c in df.columns if "INSEE" in c.upper() or c.upper() == "INSEE_C")
                sub = df[df[code_col].fillna("").str.startswith("751") | (df[code_col] == "75056")]
                f.write_subset("fr_loyers", f"loyers_appartements_{year}_paris.csv", sub, res["url"], path,
                               f"{code_col} = 75056 또는 751xx (파리) — {res.get('title')}")
                log(f"  fr_loyers {year}: {len(sub)}행 ({res.get('title')})")
                found += 1
                break
    if not found:
        raise DataUnavailable("Carte des loyers 아파트 CSV 를 찾지 못함")


def fetch(ctx, f, log, source_id):
    {"fr_insee": fetch_insee, "fr_dvf": fetch_dvf, "fr_loyers": fetch_loyers}[source_id](ctx, f, log)
