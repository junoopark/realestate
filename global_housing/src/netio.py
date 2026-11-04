"""원자료 내려받기·캐시·출처 기록(manifest).

- 받은 파일은 data/raw/<source_id>/ 에 그대로 저장한다(원자료는 고치지 않는다).
- 큰 원본(수십 MB)은 data/_cache/ 에 두고, 분석에 쓰는 행만 고치지 않은 채 data/raw 에 부분집합으로 남긴다.
  이때 manifest 에 원본 URL·크기·sha256 과 거른 조건을 함께 적는다.
- 인증키는 manifest·로그에 남기지 않는다(파라미터 값을 *** 로 가린다).
- 네트워크 실패(NetworkError)와 '자료 없음'(DataUnavailable)을 구분한다.
- offline 이면 내려받지 않고 이미 있는 파일만 쓴다. 없으면 RawMissing.
"""

from __future__ import annotations

import csv
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

MANIFEST_FIELDS = ["source_id", "file", "url", "params", "retrieved_at", "bytes", "sha256", "http_status", "note"]


class FetchError(RuntimeError):
    pass


class NetworkError(FetchError):
    """연결·시간초과·5xx — 자료가 없다는 뜻이 아니다."""


class DataUnavailable(FetchError):
    """서버가 응답했지만 자료가 없음(404, 빈 응답, 접근 제한 등)."""


class RawMissing(FetchError):
    """offline 실행인데 원자료 파일이 없다."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.rows: dict[tuple[str, str], dict] = {}
        if path.exists():
            with open(path, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    self.rows[(r["source_id"], r["file"])] = r

    def record(self, **row):
        row = {k: row.get(k, "") for k in MANIFEST_FIELDS}
        self.rows[(row["source_id"], row["file"])] = row

    def get(self, source_id: str, file: str) -> dict | None:
        return self.rows.get((source_id, file))

    def save(self, merge: bool = True):
        """디스크의 기록과 합쳐 저장한다(동시에 돌린 다른 수집이 남긴 행을 지우지 않게)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if merge and self.path.exists():
            with open(self.path, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    self.rows.setdefault((r["source_id"], r["file"]), r)
        with open(self.path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
            w.writeheader()
            for key in sorted(self.rows):
                w.writerow(self.rows[key])


class Fetcher:
    def __init__(self, ctx, manifest: Manifest | None = None):
        self.ctx = ctx
        http = ctx.project.get("http", {})
        self.ua = http.get("user_agent", "global-housing-comparison/0.1")
        self.timeout = http.get("timeout", 90)
        self.retries = http.get("retries", 3)
        self.pause = http.get("pause_seconds", 0.3)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = self.ua
        self.manifest = manifest or Manifest(ctx.raw / "_manifest.csv")
        self.calls = 0

    # ── 내부 ─────────────────────────────────────────────────────────
    @staticmethod
    def _mask(params: dict | None, secret: tuple[str, ...]) -> str:
        if not params:
            return ""
        return "&".join(f"{k}={'***' if k in secret else v}" for k, v in params.items())

    def get(self, url: str, params: dict | None = None, secret: tuple[str, ...] = (), stream=False) -> requests.Response:
        """재시도가 있는 GET. 4xx 는 DataUnavailable, 연결 실패·5xx 는 NetworkError."""
        last = None
        for attempt in range(self.retries + 1):
            if self.calls and self.pause:
                time.sleep(self.pause)
            self.calls += 1
            try:
                res = self.session.get(url, params=params, timeout=self.timeout, stream=stream)
            except requests.RequestException as exc:
                last = f"{type(exc).__name__}"
                time.sleep(min(2 ** attempt * 2, 30))
                continue
            if res.status_code >= 500 or res.status_code == 429:
                last = f"HTTP {res.status_code}"
                time.sleep(min(2 ** attempt * 3, 40))
                continue
            if res.status_code >= 400:
                raise DataUnavailable(f"HTTP {res.status_code}: {url}")
            return res
        raise NetworkError(f"{last}: {url} ({self._mask(params, secret)})")

    # ── 공개 ─────────────────────────────────────────────────────────
    def raw_path(self, source_id: str, filename: str) -> Path:
        return self.ctx.raw / source_id / filename

    def download(self, source_id: str, url: str, filename: str, params: dict | None = None,
                 secret: tuple[str, ...] = (), to_cache: bool = False, note: str = "",
                 force: bool = False, max_age_days: float | None = None) -> Path:
        """URL 을 파일로 저장하고 경로를 돌려준다. 이미 있으면(같은 실행 안에서) 다시 받지 않는다.

        max_age_days: 지정하면 그보다 오래된 파일만 다시 받는다. None 이면 online 실행마다 새로 받는다.
        """
        base = self.ctx.cache if to_cache else self.ctx.raw
        path = base / source_id / filename
        if self.ctx.offline:
            if path.exists():
                return path
            raise RawMissing(f"offline: 원자료 없음 {path.relative_to(self.ctx.root)}")
        if path.exists() and not force and max_age_days is not None:
            age = (time.time() - path.stat().st_mtime) / 86400
            if age < max_age_days:
                return path
        path.parent.mkdir(parents=True, exist_ok=True)
        res = self.get(url, params=params, secret=secret, stream=True)
        tmp = path.with_suffix(path.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in res.iter_content(1 << 16):
                f.write(chunk)
        if tmp.stat().st_size == 0:
            tmp.unlink()
            raise DataUnavailable(f"빈 응답: {url}")
        tmp.replace(path)
        if not to_cache:
            self.manifest.record(source_id=source_id, file=filename, url=url, params=self._mask(params, secret),
                                 retrieved_at=utc_now(), bytes=path.stat().st_size, sha256=sha256(path),
                                 http_status=res.status_code, note=note)
        return path

    def write_subset(self, source_id: str, filename: str, df, origin_url: str, origin_path: Path, rule: str):
        """큰 원본에서 거른 행을 data/raw 에 저장하고 manifest 에 원본 정보와 거른 조건을 적는다."""
        path = self.raw_path(source_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8")
        self.manifest.record(source_id=source_id, file=filename, url=origin_url, params="",
                             retrieved_at=utc_now(), bytes=path.stat().st_size, sha256=sha256(path), http_status=200,
                             note=f"부분집합: {rule} | 원본 {origin_path.name} {origin_path.stat().st_size} bytes "
                                  f"sha256={sha256(origin_path)[:16]}")
        return path

    def save_json(self, source_id: str, filename: str, obj, url: str, params: dict | None = None,
                  secret: tuple[str, ...] = (), note: str = "") -> Path:
        """API 응답(JSON 객체)을 그대로 저장한다."""
        import json

        path = self.raw_path(source_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        self.manifest.record(source_id=source_id, file=filename, url=url, params=self._mask(params, secret),
                             retrieved_at=utc_now(), bytes=path.stat().st_size, sha256=sha256(path), http_status=200,
                             note=note)
        return path
