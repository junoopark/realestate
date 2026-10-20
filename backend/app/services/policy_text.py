"""Read bounded official article text, with one same-site iframe/PDF fallback.

No paid service, recursive crawler, OCR, or generated prose. Unreadable pages
remain pending; a waiting room, login page, or navigation is never a summary.
"""

import re
import time
from io import BytesIO
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.services.policy_sources import SOURCES

MAX_HTML_BYTES = 3_000_000
MAX_PDF_BYTES = 8_000_000
MAX_TEXT_CHARS = 60_000
USER_AGENT = "KHMI-PolicyBriefs/1.0 (bounded official press-release reader)"
SELECTORS = {
    "fsc": (".board-view-wrap .cont",),
    "mois": ("#desc_pc", ".table_detail_area .desc"),
    "molit": (".bd_view_cont", ".bd_view_content", ".view_cont", ".view_content", "#contentBody", ".board_view_con"),
}


def official_url(url, source):
    parsed = urlsplit(url)
    host = urlsplit(source["url"]).hostname.removeprefix("www.")
    if (parsed.scheme not in ("http", "https") or parsed.username or parsed.password
            or parsed.hostname not in (host, "www." + host) or parsed.port not in (None, 80, 443)):
        raise ValueError("Only this agency's public URLs are allowed")
    return url


def download(url, source, *, pdf=False, getter=None):
    """Validate every redirect before sending another request."""
    getter = getter or requests.get
    deadline = time.monotonic() + 20
    for _ in range(3):
        official_url(url, source)
        with getter(url, timeout=(3, 8), stream=True, allow_redirects=False,
                    headers={"User-Agent": USER_AGENT}) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers.get("Location", ""))
                continue
            response.raise_for_status()
            limit = MAX_PDF_BYTES if pdf else MAX_HTML_BYTES
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                if time.monotonic() > deadline:
                    raise ValueError("Official document download took too long")
                size += len(chunk)
                if size > limit:
                    raise ValueError("Official document exceeds size limit")
                chunks.append(chunk)
            return b"".join(chunks), url
    raise ValueError("Too many document redirects")


def node_text(node):
    # Preserve paragraphs, but do not put line breaks between inline styled words.
    for child in node.select("script, style, iframe, noscript, button, .file, .attachments"):
        child.decompose()
    for br in node.select("br"):
        br.replace_with("\n")
    for block in node.select("p, li, tr, h1, h2, h3, h4"):
        block.append("\n")
    return "\n".join(re.sub(r"\s+", " ", line).strip()
                     for line in node.get_text().splitlines() if line.strip())[:MAX_TEXT_CHARS]


def article_text(body, source):
    soup = BeautifulSoup(body, "html.parser")
    for selector in SELECTORS[source["id"]]:
        node = soup.select_one(selector)
        if node:
            text = node_text(node)
            if len(text) >= 100:
                return text
    return ""


def pdf_text(body):
    if not body.startswith(b"%PDF-"):
        raise ValueError("Attachment is not a PDF")
    reader = PdfReader(BytesIO(body))
    if reader.is_encrypted:
        raise ValueError("Encrypted PDF")
    parts = []
    for page in reader.pages[:12]:
        parts.append(page.extract_text() or "")
        if sum(map(len, parts)) >= MAX_TEXT_CHARS:
            break
    return "\n".join(parts)[:MAX_TEXT_CHARS]


def fetch_document(document):
    source = next(s for s in SOURCES if s["id"] == document["source_id"])
    body, url = download(document["source_url"], source)
    text = article_text(body, source)
    if len(text) >= 100:
        return {"text": text, "url": url, "kind": "official_html"}
    soup = BeautifulSoup(body, "html.parser")
    # Some MOLIT releases embed the public article in an iframe. At most one
    # extra document request, never an off-site viewer or executable javascript.
    for frame in soup.select("iframe[src]"):
        target = urljoin(url, frame["src"])
        try:
            official_url(target, source)
        except ValueError:
            continue
        embedded, target = download(target, source)
        embedded_soup = BeautifulSoup(embedded, "html.parser")
        if embedded_soup.title and re.search(r"waiting|로그인|접속.*대기", embedded_soup.title.get_text(), re.I):
            raise ValueError("Article is unavailable")
        text = article_text(embedded, source) or node_text(embedded_soup.body or embedded_soup)
        if len(text) >= 100:
            return {"text": text, "url": target, "kind": "official_html"}
        raise ValueError("Embedded article has no readable text")
    for link in soup.select("a[href]"):
        if ".pdf" not in (link.get_text(" ", strip=True) + link["href"]).lower():
            continue
        target = urljoin(url, link["href"])
        try:
            official_url(target, source)
        except ValueError:
            continue
        attachment, target = download(target, source, pdf=True)
        text = pdf_text(attachment)
        if len(text) >= 100:
            return {"text": text, "url": target, "kind": "official_pdf"}
        raise ValueError("PDF has no readable text")
    raise ValueError("Official article text unavailable")
