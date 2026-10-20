from datetime import datetime, timedelta, timezone

import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.db.models import PolicyBrief
from app.db.session import get_engine
from app.services import policy_briefs as briefs, policy_collector as collector, policy_text
from app.services.content_store import initialize_storage, read_seed
from app.services.policy_sources import SOURCES

NOW = datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc)
BODY = (
    "국토교통부는 청년 주택 공급을 확대하고 신청 대상과 지원 조건을 공개한다고 밝혔다.\n"
    "신청 대상은 해당 지역에 거주하는 무주택 청년이며 세부 조건과 접수 일정은 별도 공고를 통해 안내한다.\n"
    "공공주택 공급계획의 구체적인 규모는 관계기관 협의를 거쳐 확정할 예정이다."
)


def document(number=1, title="청년 주택 공급 확대 계획", description=""):
    return collector.make_item(title, f"https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?id={95000000 + number}",
                               "2026-10-16T09:00:00+09:00", description, SOURCES[0])


def store(*docs):
    with Session(get_engine()) as session:
        collector.store_items(session, SOURCES[0], docs, NOW.isoformat())
        session.commit()


def article(doc, text=BODY):
    return {"text": text, "url": doc["source_url"], "kind": "official_html"}


def unavailable(_):
    raise requests.Timeout("never expose a private URL or credential")


@pytest.mark.parametrize("title", [
    "자동차세 체납 차량 합동단속 실시", "지방세입 체납관리단 주거 지원 연계",  # broad RSS hits
    "2026년 9월 가계대출 동향(잠정) 및 가계부채 점검회의 개최", "정비사업 조합 특별현장점검 실시",
    "[설명] 전세계약 보증금 의혹에 대한 설명", "9월중 전세사기피해자 623건 추가 결정",
    "[장관동정] 장관, 공공에 이어 민간까지 주택공급 현장 직접 챙긴다",
])
def test_selection_keeps_nonpolicy_updates_in_monitor(title):
    # A generic mention of welfare/housing is not enough; the title must contain
    # a direct housing/finance topic and a policy action.
    assert briefs.selection_reason(title) is None


@pytest.mark.parametrize("title", ["청년주택드림 청약통장 가입 대상 확대", "주택담보대출 규제 완화 방안", "전세사기 피해자 지원 대책 개정"])
def test_selection_accepts_direct_policy_changes(title):
    assert briefs.selection_reason(title)


def test_excerpts_preserve_source_and_do_not_invent_effective_dates():
    result = briefs.build_brief(document(), article(document()), NOW.isoformat())
    assert result["highlights"] and all(s in BODY for s in result["highlights"])
    assert result["verified_at"] is None
    assert result["effective_date"] is None
    assert result["risk_points"] == [] and result["impact_path"] is None
    assert result["review_status"] == "automatic"


def test_persist_repeat_restart_and_update(local_database):
    doc = document()
    store(doc)
    assert briefs.refresh_briefs(article, now=NOW)["generated"] == 1
    first = briefs.merge_briefs(read_seed("policies"))
    assert first["automation"]["count"] == 1
    auto = next(p for p in first["policies"] if p["review_status"] == "automatic")
    assert first["verified_at"] == "2026-10-05"
    initialize_storage()  # reviewed seed sync must not erase the automatic table
    again = briefs.merge_briefs(read_seed("policies"))
    assert any(p["id"] == auto["id"] for p in again["policies"])
    assert briefs.refresh_briefs(lambda _: pytest.fail("fresh content must not be fetched"), now=NOW + timedelta(hours=1))["fetched"] == 0
    assert briefs.refresh_briefs(article, now=NOW + timedelta(days=1))["unchanged"] == 1
    same = next(p for p in briefs.merge_briefs(read_seed("policies"))["policies"] if p["review_status"] == "automatic")
    assert same["generated_at"] == auto["generated_at"]
    assert same["source_checked_at"] != auto["source_checked_at"]
    changed = lambda d: article(d, BODY.replace("청년", "청년과 신혼부부"))
    assert briefs.refresh_briefs(changed, now=NOW + timedelta(days=2))["generated"] == 1
    with Session(get_engine()) as session:
        assert len(session.scalars(select(PolicyBrief)).all()) == 1


def test_failed_changed_release_is_not_published_with_old_summary(local_database):
    store(document())
    briefs.refresh_briefs(article, now=NOW)
    # Same release fails to load: keep the previous summary with a stale marker.
    result = briefs.refresh_briefs(unavailable, now=NOW + timedelta(days=1))
    assert result["failed"] == 1
    auto = next(p for p in briefs.merge_briefs(read_seed("policies"))["policies"] if p["review_status"] == "automatic")
    assert auto["source_stale"] is True
    assert "private" not in str(result)
    # A changed source must not keep advertising its previous claims.
    store(document(title="청년 주택 공급 확대 계획 개정"))
    briefs.refresh_briefs(unavailable, now=NOW + timedelta(days=1, hours=1))
    assert briefs.merge_briefs(read_seed("policies"))["automation"]["count"] == 0


def test_missing_body_never_becomes_title_only_summary_and_retries(local_database):
    store(document())
    assert briefs.refresh_briefs(unavailable, now=NOW)["failed"] == 1
    assert briefs.merge_briefs(read_seed("policies"))["automation"]["count"] == 0
    assert briefs.refresh_briefs(article, now=NOW + timedelta(hours=6))["generated"] == 1


def test_rss_fallback_is_explicit(local_database):
    store(document(description=BODY))
    assert briefs.refresh_briefs(unavailable, now=NOW)["generated"] == 1
    auto = next(p for p in briefs.merge_briefs(read_seed("policies"))["policies"] if p["review_status"] == "automatic")
    assert auto["source_kind"] == "rss_excerpt"


def test_budget_and_backlog(local_database):
    store(*(document(n, title=f"청년 주택 공급 확대 계획 {n}차") for n in range(5)))
    first = briefs.refresh_briefs(article, now=NOW, max_fetches=2)
    assert first["generated"] == first["fetched"] == 2
    assert first["deferred"] == 3
    second = briefs.refresh_briefs(article, now=NOW + timedelta(hours=6), max_fetches=2)
    assert second["generated"] == 2 and second["deferred"] == 1


def test_failed_recent_documents_do_not_starve_backlog(local_database):
    store(*(document(n, title=f"청년 주택 공급 확대 계획 {n}차") for n in range(5)))
    first = briefs.refresh_briefs(unavailable, now=NOW, max_fetches=2)
    assert first["failed"] == 2
    with Session(get_engine()) as session:
        failed_ids = {row.document_id for row in session.scalars(select(PolicyBrief)).all()}
    def fetch(doc):
        assert doc["id"] not in failed_ids
        return article(doc)
    result = briefs.refresh_briefs(fetch, now=NOW + timedelta(hours=6), max_fetches=2)
    assert result["generated"] == 2


def test_reviewed_and_joint_release_dedup(local_database):
    a, b = document(1), document(2)
    store(a, b)
    briefs.refresh_briefs(article, now=NOW)
    assert briefs.merge_briefs(read_seed("policies"))["automation"]["count"] == 1
    reviewed = {"verified_at": "2026-10-18", "sources": [], "policies": [{
        "id": "reviewed-1", "published_at": "2026-10-16", "title": a["title"], "source_url": a["source_url"] + "&src=text", "summary": "검토 요약",
    }]}
    result = briefs.merge_briefs(reviewed)
    assert len(result["policies"]) == 1
    assert result["policies"][0]["review_status"] == "reviewed"


def test_collection_runs_both_stages_and_get_is_read_only(local_database, monkeypatch):
    from app.main import app
    # Fixed clock prevents the test depending on real publication dates.
    refresh = briefs.refresh_briefs
    monkeypatch.setattr(briefs, "refresh_briefs", lambda **kw: refresh(now=NOW, **kw))
    result = collector.collect_all([SOURCES[0]], lambda _: [document()], brief_fetcher=article)
    assert result["status"] == "ok" and result["briefs"]["generated"] == 1
    monkeypatch.setattr(briefs, "fetch_document", lambda _: pytest.fail("GET must not fetch documents"))
    statements = []
    def record(conn, cursor, statement, parameters, context, many):
        statements.append(statement.lstrip().upper())
    with TestClient(app) as client:
        engine = get_engine()
        event.listen(engine, "before_cursor_execute", record)
        try:
            response = client.get("/policies")
        finally:
            event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 200
    assert response.json()["automation"]["count"] == 1
    assert response.json()["sync"]["mode"] == "reviewed_and_automatic"
    assert not any(s.startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER")) for s in statements)


def test_html_extraction_ignores_navigation_and_preserves_paragraphs():
    body = ('<html><nav>가짜 주택 지원 정책</nav><div class="board-view-wrap"><div class="cont">'
            + ''.join(f'<p>{s}</p>' for s in BODY.splitlines()) + '<script>secret()</script></div></div></html>').encode()
    text = policy_text.article_text(body, SOURCES[2])
    assert "가짜" not in text and "secret" not in text
    assert text == BODY
    assert policy_text.article_text(b'<html><title>Waitingroom</title><p>Waiting</p></html>', SOURCES[0]) == ""


@pytest.mark.parametrize("url", ["https://evil.example/doc", "https://www.fsc.go.kr.evil.example/doc", "http://127.0.0.1/", "https://user:password@www.fsc.go.kr/doc", "https://www.fsc.go.kr:9000/doc"])
def test_document_reader_rejects_unapproved_targets(url):
    with pytest.raises(ValueError):
        policy_text.official_url(url, SOURCES[2])


def test_redirect_checked_before_following_and_large_responses_rejected():
    class Response:
        status_code = 302
        headers = {"Location": "http://127.0.0.1/private"}
        def __enter__(self): return self
        def __exit__(self, *args): pass
    calls = []
    def getter(url, **kwargs):
        calls.append(url)
        assert kwargs["allow_redirects"] is False
        return Response()
    with pytest.raises(ValueError):
        policy_text.download("https://www.fsc.go.kr/no010101/1", SOURCES[2], getter=getter)
    assert len(calls) == 1
    class Large(Response):
        status_code = 200
        def raise_for_status(self): pass
        def iter_content(self, size): yield b"x" * (policy_text.MAX_HTML_BYTES + 1)
    with pytest.raises(ValueError, match="size"):
        policy_text.download("https://www.fsc.go.kr/no010101/1", SOURCES[2], getter=lambda *a, **k: Large())


def test_pdf_attachment_reader_uses_official_text(monkeypatch):
    from io import BytesIO
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    text = "Official housing policy document for extraction testing. Applications and eligibility conditions are stated in this document."
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 30 750 Td ({text}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    calls = []
    def download(url, source, *, pdf=False):
        calls.append((url, pdf))
        if pdf:
            return output.getvalue(), url
        return b'<html><a href="/comm/getFile?fileNo=2">release.pdf</a></html>', url
    monkeypatch.setattr(policy_text, "download", download)
    result = policy_text.fetch_document({"source_id": "fsc", "source_url": "https://www.fsc.go.kr/no010101/1"})
    assert result["kind"] == "official_pdf" and text in result["text"]
    assert calls == [("https://www.fsc.go.kr/no010101/1", False), ("https://www.fsc.go.kr/comm/getFile?fileNo=2", True)]
    with pytest.raises(ValueError, match="not a PDF"):
        policy_text.pdf_text(b"<html>Login</html>")
