"""17개 시도 경계 GeoJSON 을 Home 지도 히트맵용 SVG 경로로 줄인다.

원본: 통계청 통계지리정보서비스(SGIS) 행정구역 경계 2018 (공공누리 제1유형, 출처 표시)
      https://github.com/southkorea/southkorea-maps 의 kostat/2018/json/skorea-provinces-2018-geo.json
출력: frontend/data/korea_sido.json  { viewBox, source, regions: [{ name, code, d, cx, cy }] }
      name 은 factor_sample.json 의 시도 이름(서울, 경기 …)과 같다.

처리: 경위도를 위도 37도 기준 등장방형으로 펴고, Douglas-Peucker 로 점을 줄이고, 아주 작은 섬은 뺀다.

사용법:
  python scripts/build_korea_map.py <skorea-provinces-2018-geo.json 경로>
"""

import json
import math
import os
import sys

OUT = os.path.join(os.path.dirname(__file__), "..", "frontend", "data", "korea_sido.json")
WIDTH = 460             # SVG 가로 크기 (세로는 비율대로)
TOLERANCE = 0.9         # 단순화 허용 오차 (SVG 좌표 px)
MIN_AREA = 6.0          # 이보다 작은 섬(px²)은 뺀다 (울릉도·제주 본섬처럼 큰 섬은 남는다)

SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주",
    "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기", "강원도": "강원",
    "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전라남도": "전남", "경상북도": "경북",
    "경상남도": "경남", "제주특별자치도": "제주",
}


def simplify(points, tol):
    """Douglas-Peucker (반복형)"""
    if len(points) < 4:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = points[a], points[b]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy) or 1e-9
        best, idx = 0.0, None
        for i in range(a + 1, b):
            x, y = points[i]
            d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm
            if d > best:
                best, idx = d, i
        if idx is not None and best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(points, keep) if k]


def simplify_ring(ring, tol):
    """닫힌 고리는 시작점=끝점이라 그대로 넣으면 기준선 길이가 0 이 된다.
    시작점에서 가장 먼 점으로 두 갈래로 나눠 각각 줄인 뒤 잇는다."""
    if ring[0] == ring[-1]:
        ring = ring[:-1]
    x0, y0 = ring[0]
    far = max(range(len(ring)), key=lambda i: (ring[i][0] - x0) ** 2 + (ring[i][1] - y0) ** 2)
    return simplify(ring[: far + 1], tol) + simplify(ring[far:] + ring[:1], tol)[1:-1]


def area(ring):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))) / 2


def main(path):
    geo = json.load(open(path, encoding="utf-8"))
    polys = []  # (name, code, [ring...])
    for f in geo["features"]:
        g = f["geometry"]
        parts = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        polys.append((SHORT[f["properties"]["name"]], f["properties"]["code"], [p[0] for p in parts]))  # 바깥 고리만

    kx = math.cos(math.radians(37))
    xs = [lon * kx for _, _, rings in polys for r in rings for lon, _ in r]
    ys = [-lat for _, _, rings in polys for r in rings for _, lat in r]
    x0, y0 = min(xs), min(ys)
    scale = WIDTH / (max(xs) - x0)
    height = math.ceil((max(ys) - y0) * scale)

    regions = []
    for name, code, rings in polys:
        d, best = [], None
        for ring in rings:
            pts = [((lon * kx - x0) * scale, (-lat - y0) * scale) for lon, lat in ring]
            a = area(pts)
            if a < MIN_AREA:
                continue
            pts = simplify_ring(pts, TOLERANCE)
            if len(pts) < 4:
                continue
            d.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + "Z")
            if best is None or a > best[0]:
                cx = sum(x for x, _ in pts) / len(pts)
                cy = sum(y for _, y in pts) / len(pts)
                best = (a, cx, cy)
        regions.append(dict(name=name, code=code, d="".join(d), cx=round(best[1], 1), cy=round(best[2], 1)))

    out = dict(
        viewBox=f"0 0 {WIDTH} {height}",
        source="통계청 SGIS 행정구역 경계(2018), 공공누리 제1유형",
        regions=regions,
    )
    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(regions)}개 시도 -> {os.path.normpath(OUT)} ({os.path.getsize(OUT) / 1024:.0f} KB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
