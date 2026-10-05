"""Small, bounded public-source collector with durable revision history."""

import hashlib
import re
import threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from defusedxml import ElementTree
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PolicyDocument, PolicyDocumentVersion, PolicySourceState
from app.db.session import get_engine
from app.services.content_store import digest, utc_now
from app.services.policy_sources import SOURCES

MAX_RESPONSE_BYTES = 3_000_000
REFRESH_LOCK = threading.Lock()
KEYWORD_GROUPS = {
    "금융·대출": ("주택담보", "주담대", "가계대출", "가계부채", "스트레스 DSR", "DSR", "LTV", "DTI", "부동산 PF", "부동산PF", "프로젝트파이낸싱"),
    "세제": ("취득세", "재산세", "종합부동산세", "양도소득세", "지방세"),
    "임대차": ("전세", "월세", "임대차", "임차인", "임대보증금"),
    "공급·정비": ("주택공급", "주택 공급", "재개발", "재건축", "정비사업", "공공주택", "공공택지", "도시정비", "분양", "청약"),
    "부동산 일반": ("부동산", "주택", "아파트", "주거", "임대주택", "토지거래"),
}


def classify(text):
    folded = text.casefold()
    def matches_word(word):
        if word == "재개발":
            # '인재개발원' is staff training, not urban redevelopment.
            return re.search(r"(?<!인)재개발", folded) is not None
        if word.isascii():
            return re.search(r"(?<![a-z])" + re.escape(word.casefold()) + r"(?![a-z])", folded) is not None
        return word.casefold() in folded
    matches = [(category, [word for word in words if matches_word(word)]) for category, words in KEYWORD_GROUPS.items()]
    active = [(category, words) for category, words in matches if words]
    return (active[0][0], list(dict.fromkeys(word for _, words in active for word in words))) if active else (None, [])


def clean_text(value):
    soup = BeautifulSoup(value or "", "html.parser")
    for node in soup.select("script, style, iframe, noscript"):
        node.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def parse_date(value):
    if not value:
        return None
    value = value.strip().replace("KST", "+0900")
    try:
        parsed = parsedate_to_datetime(value)
    except (ValueError, TypeError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        # Agency feeds publish in Korea Standard Time.
        from datetime import timedelta
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=9)))
    return parsed.isoformat(timespec="seconds")


def canonical_url(value, source):
    url = urlsplit(urljoin(source["url"], value.strip()))
    allowed_host = urlsplit(source["url"]).hostname
    if url.scheme not in ("http", "https") or url.hostname not in (allowed_host, allowed_host.removeprefix("www.")):
        raise ValueError("Unexpected source link")
    # Search parameters are not part of FSC document identity.
    query = "" if source["id"] == "fsc" else urlencode(sorted((k, v) for k, v in parse_qsl(url.query) if not k.startswith("utm_")))
    return urlunsplit(("https", url.netloc.lower(), url.path, query, ""))


def make_item(title, link, date, description, source):
    title, description = clean_text(title), clean_text(description)
    if not title or not link:
        raise ValueError("Missing title or link")
    category, keywords = classify(f"{title} {description}")
    if not keywords:
        return None
    source_url = canonical_url(link, source)
    published_at = parse_date(date)
    return {
        "id": hashlib.sha256(source_url.encode("utf-8")).hexdigest(),
        "source_id": source["id"], "title": title, "agency": source["organization"],
        "published_at": published_at, "source_url": source_url,
        "summary": description[:600], "category": category, "matched_keywords": keywords,
        # Hash the entire normalized feed description, not just the displayed excerpt.
        "content_hash": digest({"title": title, "published_at": published_at, "source_url": source_url, "description": description}),
    }


def parse_rss(body, source):
    root = ElementTree.fromstring(body)
    nodes = root.findall(".//item")
    if not nodes:
        raise ValueError("RSS item structure changed or empty feed")
    result = []
    for node in nodes[:200]:
        item = make_item(node.findtext("title"), node.findtext("link"), node.findtext("pubDate") or node.findtext("{http://purl.org/dc/elements/1.1/}date"), node.findtext("description") or "", source)
        if item:
            result.append(item)
    return result


def parse_fsc_html(body, source):
    soup = BeautifulSoup(body.decode("utf-8"), "html.parser")
    links = soup.select('.subject a[href*="/no010101/"]')
    if not links:
        raise ValueError("FSC list structure changed")
    result = []
    for link in links[:100]:
        row = link.find_parent("li")
        day = row.select_one(".day") if row else None
        if day is None:
            raise ValueError("FSC publication date missing")
        item = make_item(link.get_text(" ", strip=True), link["href"], day.get_text(strip=True), "", source)
        if item:
            result.append(item)
    return result


def fetch_source(source):
    # One list/feed request per source; no recursive crawling or attachment fetching.
    with requests.get(source["feed_url"], timeout=(5, 20), stream=True, headers={"User-Agent": "DFMBA-RealEstate-ClassProject/1.0 (public policy monitoring)", "Accept": "application/rss+xml, application/xml, text/html"}) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise ValueError("Response exceeded size limit")
            chunks.append(chunk)
        body = b"".join(chunks)
    return parse_rss(body, source) if source["collection_method"] == "RSS" else parse_fsc_html(body, source)


def public_error(exc):
    if isinstance(exc, requests.Timeout):
        return "원문 서버 응답 시간 초과. 이전 수집 자료를 유지합니다."
    if isinstance(exc, requests.HTTPError):
        return f"원문 서버 HTTP {exc.response.status_code}. 이전 수집 자료를 유지합니다."
    if isinstance(exc, requests.RequestException):
        return "원문 서버 연결 실패. 이전 수집 자료를 유지합니다."
    return "원문 구조 변경 또는 저장 오류. 이전 수집 자료를 유지합니다."


def store_items(session, source, items, checked_at):
    created, changed = 0, 0
    for item in {item["id"]: item for item in items}.values():
        row = session.get(PolicyDocument, item["id"])
        if row is None:
            row = PolicyDocument(**item, first_seen_at=checked_at, last_seen_at=checked_at, updated_at=checked_at, revision=1)
            session.add(row)
            session.flush()
            created += 1
        elif row.content_hash != item["content_hash"]:
            for key, value in item.items():
                setattr(row, key, value)
            row.last_seen_at, row.updated_at = checked_at, checked_at
            row.revision += 1
            changed += 1
        else:
            row.last_seen_at = checked_at
            continue
        session.add(PolicyDocumentVersion(document_id=row.id, revision=row.revision, content_hash=row.content_hash, content=item, observed_at=checked_at))
    state = session.get(PolicySourceState, source["id"])
    if state is None:
        state = PolicySourceState(id=source["id"])
        session.add(state)
    state.last_checked_at = state.last_success_at = checked_at
    state.status, state.error, state.item_count = "ok", None, len({item["id"] for item in items})
    return {"created": created, "changed": changed, "matched": state.item_count}


def collect_all(sources=None, fetcher=None):
    sources, fetcher = SOURCES if sources is None else sources, fetch_source if fetcher is None else fetcher
    if not REFRESH_LOCK.acquire(blocking=False):
        return {"status": "busy", "sources": []}
    results = []
    try:
        for source in sources:
            checked_at = utc_now()
            try:
                items = fetcher(source)
                with Session(get_engine()) as session:
                    counts = store_items(session, source, items, checked_at)
                    session.commit()
                results.append({"id": source["id"], "status": "ok", **counts})
            except Exception as exc:
                # One failed source never removes previous documents or another source's success.
                error = public_error(exc)
                with Session(get_engine()) as session:
                    state = session.get(PolicySourceState, source["id"])
                    if state is None:
                        state = PolicySourceState(id=source["id"], item_count=0)
                        session.add(state)
                    state.last_checked_at, state.status, state.error = checked_at, "error", error
                    session.commit()
                results.append({"id": source["id"], "status": "error", "error": error})
    finally:
        REFRESH_LOCK.release()
    return {"status": "ok" if all(row["status"] == "ok" for row in results) else "partial_failure", "checked_at": utc_now(), "sources": results}


def read_monitor(limit=100):
    with Session(get_engine()) as session:
        rows = session.scalars(select(PolicyDocument).order_by(PolicyDocument.published_at.desc().nullslast(), PolicyDocument.updated_at.desc()).limit(limit)).all()
        items = [{key: getattr(row, key) for key in ("id", "source_id", "title", "agency", "published_at", "source_url", "summary", "category", "matched_keywords", "first_seen_at", "last_seen_at", "updated_at", "revision")} | {"revision_count": row.revision, "status": "미검토", "review_status": "unreviewed", "summary_kind": "원문 발췌" if row.summary else "본문 미수집"} for row in rows]
        states = {row.id: row for row in session.scalars(select(PolicySourceState)).all()}
        sources = []
        for source in SOURCES:
            state = states.get(source["id"])
            sources.append({**source, "last_checked_at": state.last_checked_at if state else None, "last_success_at": state.last_success_at if state else None, "status": state.status if state else "never_collected", "error": state.error if state else None, "item_count": state.item_count if state else 0})
    checked = [source["last_checked_at"] for source in sources if source["last_checked_at"]]
    return {"items": items, "sources": sources, "last_checked_at": max(checked) if checked else None}
