"""국토부 실거래(V006 아파트 전월세 · V007 아파트 매매) — 일일 호출 한도 안에서 최근 몇 달만 다시 받는다.

원자료(건별)는 DFMBA 가 2026-10 초까지 받아 기본 패널(시도·서울 구 월별 건수)에 넣었다. 여기서는 그 이후분만 맡는다.

  1) 수집(collect): 시군구 256개 x 최근 WINDOW 개월을 우선순위대로 부르되, 하루 호출 수(budget)를 넘지 않는다.
     받은 건수는 rtms_progress 에 (유형, 시군구, 계약월) 단위로 저장한다. 원자료 행은 저장하지 않는다.
  2) 집계(aggregate): 시도 = 그 시도 시군구를 모두 받은 달만 합계, 서울 구 = 그 구 값. 레지스트리의 MOLIT 수집 단위가
     이 집계를 읽어 다른 지표와 똑같이 '바뀐 값만' 저장하고 화면 계열에 이어붙인다(indicator_pipeline._molit_rows).

다시 받는 주기 (계약월이 오늘에서 몇 달 전인가)
  0~1개월 전: 하루마다 — 신고기한 30일 동안 계속 늘어난다
  2~3개월 전: 3일마다 · 4~5개월 전: 7일마다 — 매매 해제는 5개월 안에 98.9% (DFMBA 실측)
세는 규칙 (DFMBA preprocess/prep_rtms_counts.py 와 같다)
  전월세: 응답 행 수 = 전체, 월세액(monthlyRent) > 0 이면 월세(보증부 포함), 0 이면 전세. 취소되면 응답에서 빠진다.
  매매  : 해제 건(cdealType='O')을 빼고 센다.
"""

import os
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import requests
from defusedxml import ElementTree as ET
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RtmsProgress
from app.services.sgg_codes import SGG

KINDS = {
    "apt_rent": {"url": "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent", "label": "아파트 전월세"},
    "apt_trade": {"url": "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev", "label": "아파트 매매"},
}
WINDOW = 6                 # 최근 몇 개월을 다시 받는가 (이번 달 포함)
BUDGET = 1000              # 실행 1회·유형 1개당 호출 상한 (data.go.kr 개발계정 일일 한도에 맞춘 기본값)
PAGE = 1000                # numOfRows
NO_DATA = {"03", "004"}
QUOTA = {"22", "0022"}     # LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS


def interval_days(age: int) -> int:
    return 1 if age <= 1 else (3 if age <= 3 else 7)


class RtmsError(RuntimeError):
    pass


class RtmsQuotaError(RtmsError):
    """일일 호출 한도 초과 — 받은 데까지 저장하고 멈춘다(다음 실행이 이어받는다)."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ym_shift(ym: str, months: int) -> str:
    y, m = int(ym[:4]), int(ym[4:6])
    i = y * 12 + (m - 1) + months
    return f"{i // 12:04d}{i % 12 + 1:02d}"


def ym_age(ym: str, today: date) -> int:
    return (today.year * 12 + today.month) - (int(ym[:4]) * 12 + int(ym[4:6]))


class RtmsClient:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None, timeout: int = 60,
                 pause: float = 0.1):
        self.key = (api_key or os.getenv("DATA_GO_KR_API_KEY", "")).strip()
        if not self.key:
            raise ValueError("DATA_GO_KR_API_KEY가 설정되지 않았습니다. backend/.env 또는 GitHub Secrets 를 확인하세요.")
        self.http = session or requests.Session()
        self.timeout, self.pause = timeout, pause
        self.calls = 0

    def _hide(self, text) -> str:
        return str(text).replace(self.key, "***")

    def _page(self, url: str, lawd_cd: str, ym: str, page: int):
        params = {"serviceKey": self.key, "LAWD_CD": lawd_cd, "DEAL_YMD": ym, "numOfRows": PAGE, "pageNo": page}
        last = None
        for attempt in range(4):  # 서버가 연결을 끊는 일이 잦다 — 짧게 몇 번만 다시 시도하고 넘어간다
            try:
                if self.calls and self.pause:
                    time.sleep(self.pause)
                self.calls += 1
                res = self.http.get(url, params=params, timeout=self.timeout)
                if res.status_code == 429:
                    raise RtmsQuotaError(f"{lawd_cd} {ym}: HTTP 429")
                res.raise_for_status()
                root = ET.fromstring(res.content)
                break
            except RtmsQuotaError:
                raise
            except (requests.RequestException, ET.ParseError) as exc:
                last = exc
                time.sleep(min(5 * 2 ** attempt, 40))
        else:
            raise RtmsError(f"{lawd_cd} {ym}: {self._hide(last)}")
        code = root.findtext("./header/resultCode")
        if code is None:  # 인증키 오류·한도 초과는 <OpenAPI_ServiceResponse> 꼴로 온다 — 0건으로 착각하지 않게 멈춘다
            reason = (root.findtext(".//returnReasonCode") or "").strip()
            msg = (root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg") or root.tag).strip()
            if reason == "22" or "LIMITED_NUMBER" in msg:
                raise RtmsQuotaError(f"{lawd_cd} {ym}: 일일 호출 한도 초과")
            raise RtmsError(f"{lawd_cd} {ym}: 공공데이터포털 오류 {reason} {msg}")
        code = code.strip()
        if code not in ("000", "00"):
            if code in NO_DATA:
                return [], 0
            if code in QUOTA:
                raise RtmsQuotaError(f"{lawd_cd} {ym}: 일일 호출 한도 초과")
            raise RtmsError(f"{lawd_cd} {ym}: API 오류 {code} {root.findtext('./header/resultMsg') or ''}")
        items = [{c.tag: (c.text or "").strip() for c in item} for item in root.findall("./body/items/item")]
        return items, int(root.findtext("./body/totalCount") or 0)

    def fetch_month(self, kind: str, lawd_cd: str, ym: str) -> tuple[list[dict], int]:
        """(그 시군구·계약월의 거래 건 전체, 쓴 호출 수)."""
        url, out, page, used = KINDS[kind]["url"], [], 1, 0
        while True:
            items, total = self._page(url, lawd_cd, ym, page)
            used += 1
            out.extend(items)
            if not items or page * PAGE >= total:
                return out, used
            page += 1


def count_rows(kind: str, items: list[dict]) -> dict:
    if kind == "apt_rent":
        monthly = 0
        for r in items:
            try:
                monthly += float((r.get("monthlyRent") or "0").replace(",", "") or 0) > 0
            except ValueError:
                pass
        return {"count_all": len(items), "count_monthly": monthly, "count_jeonse": len(items) - monthly, "count_canceled": 0}
    canceled = sum(1 for r in items if (r.get("cdealType") or "").strip() == "O")
    return {"count_all": len(items) - canceled, "count_monthly": 0, "count_jeonse": 0, "count_canceled": canceled}


def plan(session: Session, kind: str, today: date | None = None, window: int = WINDOW, codes=None) -> list[tuple]:
    """다시 받을 (시군구, 계약월) 목록, 급한 순. 한 번도 안 받은 것 → 최근 달 → 오래 묵은 것."""
    today = today or date.today()
    cur = f"{today.year:04d}{today.month:02d}"
    months = [ym_shift(cur, -i) for i in range(window)]
    got = {(r.lawd_cd, r.deal_ym): r.fetched_at for r in session.execute(
        select(RtmsProgress).where(RtmsProgress.kind == kind, RtmsProgress.deal_ym.in_(months))).scalars()}
    due = []
    for ym in months:
        age = ym_age(ym, today)
        for cd in (codes or sorted(SGG)):
            last = got.get((cd, ym))
            if last is None:
                due.append((0, age, "", cd, ym))
                continue
            last_day = datetime.fromisoformat(last).date()
            if (today - last_day).days >= interval_days(age):
                due.append((1, age, last, cd, ym))
    due.sort()
    return [(cd, ym) for *_, cd, ym in due]


def collect(session: Session, kinds=None, budget: int = BUDGET, window: int = WINDOW, client: RtmsClient | None = None,
            today: date | None = None, codes=None, log=print) -> dict:
    """유형마다 budget 호출까지 받는다. 반환: 유형별 조회 수·호출 수·바뀐 시군구-월 수·한도 도달 여부."""
    client = client or RtmsClient()
    summary = {}
    for kind in kinds or list(KINDS):
        todo = plan(session, kind, today, window, codes)
        start_calls, done, changed, errors, stopped = client.calls, 0, 0, 0, ""
        log(f"[{kind}] {KINDS[kind]['label']}: 다시 받을 시군구-월 {len(todo)}개, 호출 상한 {budget}회")
        pending = []
        for cd, ym in todo:
            if client.calls - start_calls >= budget:
                stopped = "budget"
                break
            try:
                items, used = client.fetch_month(kind, cd, ym)
            except RtmsQuotaError as exc:
                stopped = f"quota ({exc})"
                break
            except RtmsError as exc:
                errors += 1
                log(f"  ! {exc}")
                if errors >= 10:
                    stopped = "errors"
                    break
                continue
            pending.append((cd, ym, count_rows(kind, items), used))
            done += 1
            if len(pending) >= 50:
                changed += _save(session, kind, pending)
                pending = []
            if done % 100 == 0:
                log(f"  {done}/{len(todo)} 조회 · 호출 {client.calls - start_calls}회", )
        changed += _save(session, kind, pending)
        summary[kind] = {"due": len(todo), "fetched": done, "calls": client.calls - start_calls, "changed": changed,
                         "errors": errors, "stopped": stopped, "left": len(todo) - done}
        log(f"  → 조회 {done}개 · 호출 {summary[kind]['calls']}회 · 건수 바뀐 시군구-월 {changed}개"
            + (f" · 멈춤: {stopped} (남은 {len(todo) - done}개는 다음 실행이 이어받음)" if stopped else ""))
        if stopped.startswith("quota"):
            break  # 다른 유형도 같은 키라 한도에 걸렸을 수 있다
    return summary


def _save(session: Session, kind: str, rows: list[tuple]) -> int:
    """받은 건수를 저장. 반환: 건수가 처음 생기거나 바뀐 (시군구, 월) 수."""
    if not rows:
        return 0
    now, changed = utc_now(), 0
    for cd, ym, counts, used in rows:
        row = session.get(RtmsProgress, (kind, cd, ym))
        if row is None:
            session.add(RtmsProgress(kind=kind, lawd_cd=cd, deal_ym=ym, calls=used, first_fetched_at=now, fetched_at=now, **counts))
            changed += 1
            continue
        if any(getattr(row, k) != v for k, v in counts.items()):
            changed += 1
            for k, v in counts.items():
                setattr(row, k, v)
        row.calls, row.fetched_at = used, now
    session.commit()
    return changed


def aggregate(session: Session, kind: str, field: str, start_ym: str | None = None, end_ym: str | None = None,
              keep_gu=None) -> dict:
    """{(지역, 'YYYY-MM'): 건수}. 시도는 소속 시군구를 모두 받은 달만, 서울 구는 받은 달."""
    q = select(RtmsProgress.lawd_cd, RtmsProgress.deal_ym, getattr(RtmsProgress, field)).where(RtmsProgress.kind == kind)
    if start_ym:
        q = q.where(RtmsProgress.deal_ym >= start_ym)
    if end_ym:
        q = q.where(RtmsProgress.deal_ym <= end_ym)
    by_month = defaultdict(dict)
    for cd, ym, v in session.execute(q):
        if cd in SGG:
            by_month[ym][cd] = v
    members = defaultdict(list)
    for cd, (sido, _) in SGG.items():
        members[sido].append(cd)
    out = {}
    for ym, vals in by_month.items():
        period = f"{ym[:4]}-{ym[4:]}"
        for sido, cds in members.items():
            if all(cd in vals for cd in cds):
                out[(sido, period)] = float(sum(vals[cd] for cd in cds))
        for cd, v in vals.items():
            sido, name = SGG[cd]
            if sido == "서울" and (keep_gu is None or name in keep_gu):
                out[(name, period)] = float(v)
    return out


def status(session: Session, today: date | None = None, window: int = WINDOW) -> dict:
    """유형·월별로 몇 개 시군구를 받았는지 (수집 모니터용)."""
    today = today or date.today()
    cur = f"{today.year:04d}{today.month:02d}"
    months = [ym_shift(cur, -i) for i in range(window)]
    out = {}
    for kind in KINDS:
        rows = session.execute(select(RtmsProgress.deal_ym, RtmsProgress.fetched_at).where(
            RtmsProgress.kind == kind, RtmsProgress.deal_ym.in_(months))).all()
        per = defaultdict(list)
        for ym, at in rows:
            per[ym].append(at)
        out[kind] = {ym: {"sgg": len(per[ym]), "of": len(SGG), "oldest": min(per[ym]) if per[ym] else None} for ym in months}
    return out
