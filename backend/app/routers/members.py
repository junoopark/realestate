"""Public setup metadata and authenticated, allowlisted data downloads."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.member_auth import Member, auth_config, require_member
from app.member_store import member_storage_status

router = APIRouter(prefix="/members", tags=["members"])
DOWNLOAD_ROOT = Path(__file__).resolve().parents[2] / "data" / "member-downloads"
DOWNLOADS = {
    "factor-sample": {
        "id": "factor-sample", "title": "동인별 지표 샘플 데이터", "filename": "factor-sample.csv", "format": "CSV",
        "description": "대시보드에 사용한 지역별 동인 지표 샘플입니다. 전체 원자료가 아닌 학습용 추출본입니다.",
    },
    "variable-dictionary": {
        "id": "variable-dictionary", "title": "지표 변수 설명서", "filename": "variable-dictionary.csv", "format": "CSV",
        "description": "샘플 데이터의 변수명, 동인 분류, 공표시기와 출처를 확인할 수 있습니다.",
    },
}


def _download_path(item):
    root = DOWNLOAD_ROOT.resolve()
    path = (root / item["filename"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path


@router.get("/config")
def member_config():
    return auth_config()


@router.get("/status")
def member_status():
    return {"auth_configured": auth_config()["enabled"], "storage": member_storage_status(),
            "downloads_ready": all(_download_path(item) is not None for item in DOWNLOADS.values())}


@router.get("/me")
def member_me(member: Member = Depends(require_member)):
    return {"id": member.id, "display_name": member.display_name}


@router.get("/downloads")
def downloads_catalog():
    items = []
    for item in DOWNLOADS.values():
        path = _download_path(item)
        items.append({**item, "bytes": path.stat().st_size if path else 0, "available": path is not None})
    return {"items": items}


@router.get("/downloads/{download_id}")
def download_file(download_id: str, member: Member = Depends(require_member)):
    item = DOWNLOADS.get(download_id)
    if item is None:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")
    path = _download_path(item)
    if path is None:
        raise HTTPException(status_code=503, detail="자료를 준비 중입니다.")
    return FileResponse(path, filename=item["filename"], media_type="text/csv; charset=utf-8",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
