"""설정·경로·환경변수.

모든 경로는 프로젝트 루트(global_housing/) 기준이다. 실행은 루트에서 `python -m src.run ...`.
API 키는 환경변수로만 받는다. --env-file 로 .env 파일 경로를 줄 수 있다(값은 출력하지 않는다).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_env_file(path: str | Path | None) -> list[str]:
    """KEY=VALUE 줄을 읽어 아직 없는 환경변수만 채운다. 읽은 키 이름만 돌려준다(값은 돌려주지 않는다)."""
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f".env 파일이 없습니다: {p}")
    names = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if v and not os.environ.get(k):
            os.environ[k] = v
        names.append(k)
    return names


@dataclass
class Context:
    """한 번의 실행에 필요한 설정과 경로."""

    project: dict
    cities: dict
    series: dict
    offline: bool = False
    only: set[str] = field(default_factory=set)   # 지정하면 이 source_id 만 수집
    root: Path = ROOT

    @property
    def raw(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def cache(self) -> Path:
        """대용량 원본 캐시(커밋하지 않음). 필요한 행만 data/raw 에 부분집합으로 남긴다."""
        return self.root / "data" / "_cache"

    @property
    def manual(self) -> Path:
        return self.root / "data" / "manual_inputs"

    @property
    def interim(self) -> Path:
        return self.root / "data" / "interim"

    @property
    def processed(self) -> Path:
        return self.root / "data" / "processed"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def as_of(self) -> str:
        return str(self.project["project"]["as_of"])

    def series_for(self, source_id: str) -> dict:
        return {k: v for k, v in self.series.items() if v.get("source_id") == source_id}


def load_context(config_path: str | Path = "configs/project.yaml", offline: bool = False, only=None) -> Context:
    cfg_path = Path(config_path)
    if not cfg_path.is_absolute():
        cfg_path = ROOT / cfg_path
    cfg_dir = cfg_path.parent
    project = load_yaml(cfg_path)
    cities = load_yaml(cfg_dir / "cities.yaml")["cities"]
    series_doc = load_yaml(cfg_dir / "series.yaml")
    defaults = series_doc.get("defaults", {})
    series = {}
    for sid, meta in (series_doc.get("series") or {}).items():
        m = {**defaults, **meta, "series_id": sid}
        if m["city_id"] not in cities and m["city_id"] not in ("_national", "_global"):
            raise ValueError(f"series {sid}: 알 수 없는 city_id {m['city_id']}")
        series[sid] = m
    return Context(project=project, cities=cities, series=series, offline=offline, only=set(only or []))
