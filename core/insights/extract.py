import hashlib
import json
import re
from typing import Any

from bs4 import BeautifulSoup


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return _normalize_space(text)


def extract_summary(description: str, content_html: str, max_len: int = 200) -> str:
    desc = _normalize_space(description)
    if desc:
        return desc[:max_len]
    if not content_html:
        return ""

    soup = BeautifulSoup(content_html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    paragraphs: list[str] = []
    for p in soup.find_all("p"):
        t = _normalize_space(p.get_text(" ", strip=True))
        if len(t) >= 20:
            paragraphs.append(t)
        if len(paragraphs) >= 3:
            break
    if paragraphs:
        return _normalize_space(" ".join(paragraphs))[:max_len]

    return html_to_text(content_html)[:max_len]


def extract_headings(content_html: str, levels: tuple[int, ...] = (1, 2), max_items: int = 20) -> list[dict[str, Any]]:
    if not content_html:
        return []
    soup = BeautifulSoup(content_html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    wanted = {f"h{lvl}": lvl for lvl in levels}
    items: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()

    for el in soup.find_all(list(wanted.keys())):
        lvl = wanted.get(el.name)
        if not lvl:
            continue
        text = _normalize_space(el.get_text(" ", strip=True))
        if not text:
            continue
        key = (lvl, text)
        if key in seen:
            continue
        seen.add(key)
        items.append({"level": lvl, "text": text})
        if len(items) >= max_items:
            break

    return items


def compute_content_hash(description: str, content_html: str) -> str:
    payload = json.dumps(
        {"description": description or "", "content": content_html or ""},
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

