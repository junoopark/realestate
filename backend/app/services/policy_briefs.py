"""Free, extractive policy briefs: select official releases and quote their text.

Collection writes a separate table. GET only merges it with the reviewed seed;
restarting the application cannot replace automatic briefs with the old JSON.
"""

import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ContentSnapshot, PolicyBrief, PolicyDocument
from app.db.session import get_engine
from app.services.content_store import digest
from app.services.policy_text import fetch_document

VERSION = "extractive-v1"
STATE_KEY = "policy-briefs-state"
TOPICS = re.compile(r"주택|부동산|전세|월세|임대차|임차인|재개발|재건축|정비사업|청약|가계대출|가계부채|주담대|토지거래|종합부동산세|양도소득세|(?<![a-z])(?:dsr|ltv|dti)(?![a-z])", re.I)
ACTIONS = re.compile(r"대책|방안|계획|개편|개정|개선|도입|확대|완화|강화|지원|시행|추진|공급|모집|신청|접수|조성|지정|낮춘|높인")
CHANGES = re.compile(r"대책|방안|개편|개정|개선|도입|확대|완화|강화|시행|모집|신청|접수|낮춘|높인")
NOISE = re.compile(r"담당자|담당부서|연락처|전화번호|누리집|다운로드|보도시점|배포일시|사진제공|이전글|다음글")


def compact(value):
    return re.sub(r"\s+", "", value or "").casefold()


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (ValueError, TypeError, AttributeError):
        return None


def selection_reason(title):
    """A reproducible relevance rule, not an estimate of market impact."""
    text = compact(title)
    topic, action = TOPICS.search(text), ACTIONS.search(text)
    if not topic or not action or re.match(r"[\[【(]?(설명|해명|보도설명|사실은|장관동정|차관동정)", text):
        return None
    # Monthly statistics, meetings and inspections are monitoring candidates,
    # unless the title explicitly announces a policy change.
    if re.search(r"동향|통계|잠정|점검|간담회|회의|행사|실적|피해자.*추가결정", text) and not CHANGES.search(text):
        return None
    return f"{topic.group()} 관련 발표이며 '{action.group()}' 내용을 포함합니다."


def excerpts(text, title):
    sentences = []
    for part in re.split(r"\n+|(?<=[.!?。])\s+", text):
        line = re.sub(r"\s+", " ", part).strip(" \t□ㅇ○◇●▪▶-•")
        if not 30 <= len(line) <= 1200 or NOISE.search(line) or compact(line) == compact(title):
            continue
        if not any(compact(line) == compact(old) for old in sentences):
            sentences.append(line)
    scored = []
    for i, sentence in enumerate(sentences):
        value = compact(sentence)
        score = 3 * bool(TOPICS.search(value)) + 2 * bool(ACTIONS.search(value))
        score += bool(re.search(r"대상|시행|신청|접수|\d+(?:년|월|일|원|호|%)", value))
        if score >= 2:
            scored.append((score, i, sentence))
    chosen = sorted(sorted(scored, key=lambda row: (-row[0], row[1]))[:3], key=lambda row: row[1])
    # Ellipses explicitly mark excerpt truncation; no words or dates are inferred.
    return [sentence if len(sentence) <= 360 else sentence[:359].rstrip() + "…" for _, _, sentence in chosen]


def build_brief(document, article, generated_at):
    highlights = excerpts(article["text"], document["title"])
    if not highlights:
        raise ValueError("No substantive policy sentences found")
    published = timestamp(document["published_at"])
    if published is None:
        raise ValueError("Publication date unavailable")
    return {
        "id": "auto-" + document["id"], "title": document["title"], "agency": document["agency"],
        "published_at": published.astimezone(timezone(timedelta(hours=9))).date().isoformat(),
        "category": document["category"], "summary": highlights[0], "highlights": highlights,
        "effective_date": None, "effective_note": "적용 대상·시행일·예외 조건은 발표 원문을 확인하세요.",
        "status": "공식 발표 · 자동 요약", "risk_points": [], "impact_path": None,
        "source_url": document["source_url"], "source_name": document["agency"],
        "excerpt_url": article["url"], "summary_kind": "extractive", "source_kind": article["kind"],
        "review_status": "automatic", "verified_at": None, "generated_at": generated_at,
        "source_checked_at": generated_at, "selection_reason": selection_reason(document["title"]),
    }


def refresh_briefs(fetcher=None, *, now=None, max_fetches=6, max_seconds=60):
    """Bound the work per run; backlog/retries are handled by the next schedule."""
    fetcher = fetcher or fetch_document
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    deadline = time.monotonic() + max_seconds
    result = {"checked_at": stamp, "generated": 0, "unchanged": 0, "excluded": 0,
              "failed": 0, "deferred": 0, "fetched": 0, "status": "ok"}
    with Session(get_engine()) as session:
        rows = session.scalars(select(PolicyDocument).order_by(PolicyDocument.published_at.desc()).limit(150)).all()
        documents = [{k: getattr(row, k) for k in ("id", "source_id", "title", "agency", "published_at", "source_url", "summary", "category", "content_hash")} for row in rows]
        previous = {r.document_id: (r.document_hash, r.algorithm_version, r.last_attempt_at)
                    for r in session.scalars(select(PolicyBrief)).all()}
    def priority(doc):
        prior = previous.get(doc["id"])
        if prior is None or prior[:2] != (doc["content_hash"], VERSION):
            published = timestamp(doc["published_at"])
            return (0, -published.timestamp() if published else 0)
        attempted = timestamp(prior[2])
        return (1, attempted.timestamp() if attempted else 0)
    # New documents go first, then least recently attempted. Permanently
    # unreadable releases must not consume the budget ahead of the whole backlog.
    documents.sort(key=priority)
    for doc in documents:
        published = timestamp(doc["published_at"])
        if published is None or not now - timedelta(days=90) <= published <= now + timedelta(days=1):
            continue
        reason = selection_reason(doc["title"])
        with Session(get_engine()) as session:
            old = session.get(PolicyBrief, doc["id"])
            same = bool(old and old.document_hash == doc["content_hash"] and old.algorithm_version == VERSION)
            attempt = timestamp(old.last_attempt_at) if old else None
            retry_hours = 5 if old and old.status == "error" else 23
            if same and (old.status == "excluded" or (attempt and now - attempt < timedelta(hours=retry_hours))):
                continue
            if not reason:
                row = old or PolicyBrief(document_id=doc["id"])
                row.document_hash, row.algorithm_version = doc["content_hash"], VERSION
                row.content, row.status, row.error, row.last_attempt_at = None, "excluded", None, stamp
                session.add(row)
                session.commit()
                result["excluded"] += 1
                continue
        if result["fetched"] >= max_fetches or time.monotonic() >= deadline:
            result["deferred"] += 1
            continue
        result["fetched"] += 1
        try:
            try:
                article = fetcher(doc)
            except Exception:
                # RSS text is also official, but is explicitly marked as a feed
                # excerpt. Never synthesize a summary from a title alone.
                if len(doc["summary"].strip()) < 120:
                    raise
                article = {"text": doc["summary"], "url": doc["source_url"], "kind": "rss_excerpt"}
            brief = build_brief(doc, article, stamp)
            body_hash = digest({"text": article["text"], "url": article["url"], "kind": article["kind"]})
            with Session(get_engine()) as session:
                row = session.get(PolicyBrief, doc["id"]) or PolicyBrief(document_id=doc["id"])
                same_body = bool(row.content and row.body_hash == body_hash and row.document_hash == doc["content_hash"] and row.algorithm_version == VERSION)
                if same_body:
                    brief["generated_at"] = row.content["generated_at"]
                row.content, row.body_hash = brief, body_hash
                row.document_hash, row.algorithm_version = doc["content_hash"], VERSION
                row.last_attempt_at = row.last_success_at = stamp
                row.status, row.error = "ok", None
                session.add(row)
                session.commit()
                result["unchanged" if same_body else "generated"] += 1
        except Exception:
            with Session(get_engine()) as session:
                row = session.get(PolicyBrief, doc["id"]) or PolicyBrief(document_id=doc["id"])
                # A changed release must not continue to show its obsolete summary.
                if row.document_hash != doc["content_hash"] or row.algorithm_version != VERSION:
                    row.content = None
                row.document_hash, row.algorithm_version = doc["content_hash"], VERSION
                row.status, row.error = "error", "원문에서 핵심 문장을 읽지 못했습니다. 다음 수집에서 다시 확인합니다."
                row.last_attempt_at = stamp
                session.add(row)
                session.commit()
            result["failed"] += 1
    result["status"] = "partial_failure" if result["failed"] else "ok"
    with Session(get_engine()) as session:
        state = session.get(ContentSnapshot, STATE_KEY) or ContentSnapshot(key=STATE_KEY)
        state.content, state.content_hash, state.updated_at = result, digest(result), stamp
        session.add(state)
        session.commit()
    return result


def identity_url(url):
    parsed = urlsplit(url or "")
    # Display/search parameters do not identify a release.
    query = [(k, v) for k, v in parse_qsl(parsed.query) if k not in ("kw", "src", "curPage") and not k.startswith("utm_")]
    return urlunsplit(("https", parsed.netloc.lower().removeprefix("www."), parsed.path, urlencode(sorted(query)), ""))


def merge_briefs(reviewed):
    """Read-only: reviewed entries take precedence; joint releases appear once."""
    with Session(get_engine()) as session:
        pairs = session.execute(select(PolicyBrief, PolicyDocument).join(PolicyDocument).where(PolicyBrief.content.is_not(None))).all()
        state = session.get(ContentSnapshot, STATE_KEY)
        automation = dict(state.content) if state else {}
        automatic = [{**row.content, "source_stale": row.status == "error"} for row, doc in pairs
                     if row.content and row.document_hash == doc.content_hash]
    policies = [{**p, "review_status": "reviewed", "verified_at": p.get("verified_at") or reviewed.get("verified_at")} for p in reviewed.get("policies", [])]
    urls = {identity_url(p[k]) for p in policies for k in ("source_url", "original_source_url") if p.get(k)}
    titles = {(p["published_at"], re.sub(r"\W", "", compact(p["title"]))) for p in policies}
    added = 0
    for brief in sorted(automatic, key=lambda p: (p["published_at"], len(p["summary"])), reverse=True):
        title_key = (brief["published_at"], re.sub(r"\W", "", compact(brief["title"])))
        url_key = identity_url(brief["source_url"])
        if url_key in urls or title_key in titles or added >= 30:
            continue
        policies.append(brief)
        urls.add(url_key)
        titles.add(title_key)
        added += 1
    policies.sort(key=lambda p: p["published_at"], reverse=True)
    generated = [p["generated_at"] for p in policies if p.get("generated_at")]
    return {**reviewed, "policies": policies, "reviewed_at": reviewed.get("verified_at"),
            "generated_at": max(generated) if generated else None, "last_checked_at": automation.get("checked_at"),
            "automation": {**automation, "enabled": True, "count": added, "method": "공식 원문 문장 추출 · 별도 AI API 사용 없음"},
            "reviewed_coverage_note": reviewed.get("coverage_note"),
            "coverage_note": "공식 발표를 6시간 주기로 수집해 주택·임대차·대출 등의 정책을 자동 선별하고 원문 핵심 문장을 발췌합니다. 자동 요약과 사람이 검토한 자료를 구분하며, 전체 정책을 빠짐없이 수록한 목록은 아닙니다."}
