import re
import time
import threading
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.config import cfg


def _make_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=2,
        backoff_factor=0.25,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(pool_connections=64, pool_maxsize=128, max_retries=retries)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


_HTTP = _make_session()


def _cfg_value(path: str, default: Any) -> Any:
    cur = getattr(cfg, "_config", None) or getattr(cfg, "config", {})
    try:
        for p in str(path or "").split("."):
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur.get(p)
        if cur is None:
            return default
        return cur
    except Exception:
        return default


def _int_cfg(key: str, default: int, min_value: int, max_value: int) -> int:
    try:
        v = int(_cfg_value(key, default) or default)
    except Exception:
        v = int(default)
    return max(min_value, min(max_value, v))


@dataclass
class SourceExtractResult:
    ok: bool
    url: str
    title: str
    description: str
    content_html: str
    text_length: int
    image_url: str
    method: str
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "content": self.content_html,
            "content_html": self.content_html,
            "text_length": self.text_length,
            "topic_image": self.image_url,
            "pic_url": self.image_url,
            "method": self.method,
            "error": self.error,
        }


_CACHE_LOCK = threading.Lock()
_CONTENT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_get(url: str) -> dict[str, Any] | None:
    key = str(url or "").strip()
    if not key:
        return None
    now = time.time()
    ttl_ok = _int_cfg("source.content_cache_ttl_seconds", 21600, 30, 172800)
    ttl_fail = _int_cfg("source.content_cache_fail_ttl_seconds", 90, 0, 3600)
    with _CACHE_LOCK:
        hit = _CONTENT_CACHE.get(key)
        if not hit:
            return None
        ts, value = hit
        age = now - float(ts or 0.0)
        ok = bool((value or {}).get("ok"))
        ttl = ttl_ok if ok else ttl_fail
        if ttl <= 0 or age > ttl:
            _CONTENT_CACHE.pop(key, None)
            return None
        return dict(value)


def _cache_set(url: str, value: dict[str, Any]) -> None:
    key = str(url or "").strip()
    if not key:
        return
    max_items = _int_cfg("source.content_cache_max_items", 3000, 200, 20000)
    now = time.time()
    with _CACHE_LOCK:
        _CONTENT_CACHE[key] = (now, dict(value or {}))
        if len(_CONTENT_CACHE) <= max_items:
            return
        # Drop oldest entries when cache exceeds cap.
        overflow = len(_CONTENT_CACHE) - max_items
        for k, _ in sorted(_CONTENT_CACHE.items(), key=lambda x: x[1][0])[: max(1, overflow)]:
            _CONTENT_CACHE.pop(k, None)


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _meta_content(soup: BeautifulSoup, key: str, value: str) -> str:
    node = soup.find("meta", attrs={key: value})
    return _clean_text(node.get("content")) if isinstance(node, Tag) else ""


def _pick_image(soup: BeautifulSoup, base_url: str) -> str:
    candidates = [
        _meta_content(soup, "property", "og:image"),
        _meta_content(soup, "name", "twitter:image"),
        _meta_content(soup, "itemprop", "image"),
    ]
    for c in candidates:
        if c:
            try:
                return urljoin(base_url, c)
            except Exception:
                return c
    return ""


def _strip_noise(root: Tag) -> None:
    for bad in root.select(
        "script,style,noscript,iframe,svg,nav,header,footer,aside,form,button,"
        ".advert,.ads,.ad,.social,.share,.newsletter,.related,.recommend,.recommendation,"
        "[aria-label*='share' i],[class*='share' i],[id*='share' i]"
    ):
        bad.decompose()


def _text_len(node: Tag) -> int:
    return len(_clean_text(node.get_text(" ", strip=True)))


def _link_density(node: Tag) -> float:
    total = max(1, _text_len(node))
    link_text = 0
    for a in node.find_all("a"):
        link_text += len(_clean_text(a.get_text(" ", strip=True)))
    return float(link_text) / float(total)


def _candidate_score(node: Tag) -> float:
    txt_len = _text_len(node)
    if txt_len < 180:
        return -1.0
    density = _link_density(node)
    p_count = len(node.find_all("p"))
    h_count = len(node.find_all(["h1", "h2", "h3"]))
    return float(txt_len) + float(p_count * 24 + h_count * 10) - float(density * 2400)


def _extract_from_structured_data(soup: BeautifulSoup) -> str:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            # 这里只做轻量兼容，不强依赖 JSON-LD 完整结构
            body_match = re.search(r'"articleBody"\s*:\s*"(.+?)"\s*(,|\})', raw, re.S)
            if not body_match:
                continue
            body = body_match.group(1)
            body = body.replace("\\n", "\n").replace('\\"', '"').replace("\\/", "/")
            lines = [_clean_text(x) for x in body.split("\n")]
            lines = [x for x in lines if len(x) >= 12]
            if not lines:
                continue
            return "".join([f"<p>{line}</p>" for line in lines])
        except Exception:
            continue
    return ""


def _extract_main_html(soup: BeautifulSoup) -> tuple[str, str]:
    body = soup.body
    if not isinstance(body, Tag):
        return "", ""

    _strip_noise(body)

    selectors = [
        "article",
        "main article",
        "[itemprop='articleBody']",
        ".article-content",
        ".article-content__content",
        ".article__content",
        ".article__main",
        ".article-body",
        ".article-body__content",
        ".story__content",
        ".story-body",
        ".post-content",
        ".entry-content",
        ".caas-body",
        ".body__inner-container",
        ".story-body__inner",
        ".zn-body__paragraph",
        ".l-container",
        "main",
    ]
    candidates: list[Tag] = []
    for sel in selectors:
        for node in body.select(sel):
            if isinstance(node, Tag):
                candidates.append(node)

    if not candidates:
        for node in body.find_all(["div", "section"], recursive=True):
            if isinstance(node, Tag) and _text_len(node) >= 220:
                candidates.append(node)

    best = None
    best_score = -1.0
    for node in candidates:
        score = _candidate_score(node)
        if score > best_score:
            best_score = score
            best = node

    if not isinstance(best, Tag):
        return "", ""

    output = BeautifulSoup("", "lxml")
    wrap = output.new_tag("div")
    output.append(wrap)
    blocks = best.find_all(["h1", "h2", "h3", "p", "li", "blockquote", "pre"], recursive=True)
    for b in blocks:
        text = _clean_text(b.get_text(" ", strip=True))
        if not text:
            continue
        if b.name == "p" and len(text) < 18:
            continue
        cloned = output.new_tag(b.name)
        cloned.string = text
        wrap.append(cloned)

    html = str(wrap)
    text = _clean_text(wrap.get_text(" ", strip=True))
    if len(text) < 160:
        return "", text
    return html, text


def fetch_source_article_content(url: str, *, title_hint: str = "", description_hint: str = "") -> dict[str, Any]:
    target = str(url or "").strip()
    if not target:
        result = SourceExtractResult(
            ok=False,
            url=target,
            title=_clean_text(title_hint),
            description=_clean_text(description_hint),
            content_html="",
            text_length=0,
            image_url="",
            method="none",
            error="empty url",
        ).to_dict()
        return result

    cached = _cache_get(target)
    if cached is not None:
        return cached

    timeout = _int_cfg("source.content_fetch_timeout", 12, 4, 45)
    headers = {
        "User-Agent": str(cfg.get("user_agent", "we-mp-rss/1.0") or "we-mp-rss/1.0"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }

    started = time.time()
    try:
        resp = _HTTP.get(target, headers=headers, timeout=float(timeout), allow_redirects=True)
        resp.raise_for_status()
        html_raw = str(resp.text or "")
        if not html_raw.strip():
            raise ValueError("empty html response")
    except Exception as e:
        result = SourceExtractResult(
            ok=False,
            url=target,
            title=_clean_text(title_hint),
            description=_clean_text(description_hint),
            content_html="",
            text_length=0,
            image_url="",
            method="http",
            error=f"request failed: {e}",
        ).to_dict()
        _cache_set(target, result)
        return result

    try:
        soup = BeautifulSoup(html_raw, "lxml")
        title = (
            _meta_content(soup, "property", "og:title")
            or _clean_text(soup.title.get_text() if soup.title else "")
            or _clean_text(title_hint)
        )
        desc = (
            _meta_content(soup, "property", "og:description")
            or _meta_content(soup, "name", "description")
            or _clean_text(description_hint)
        )
        image = _pick_image(soup, target)

        html_main, txt_main = _extract_main_html(soup)
        method = "heuristic"
        if not html_main:
            html_main = _extract_from_structured_data(soup)
            if html_main:
                method = "jsonld"
                txt_main = _clean_text(BeautifulSoup(html_main, "lxml").get_text(" ", strip=True))

        if not html_main and desc:
            html_main = f"<p>{desc}</p>"
            txt_main = desc
            method = "meta_description"

        min_len = _int_cfg("source.content_min_text_length", 140, 40, 1200)
        elapsed_ms = int((time.time() - started) * 1000)
        if len(txt_main) < min_len:
            result = SourceExtractResult(
                ok=False,
                url=target,
                title=title,
                description=desc,
                content_html=html_main or "",
                text_length=len(txt_main),
                image_url=image,
                method=method,
                error=f"content too short: {len(txt_main)} chars ({elapsed_ms}ms)",
            ).to_dict()
            _cache_set(target, result)
            return result

        result = SourceExtractResult(
            ok=True,
            url=target,
            title=title,
            description=desc,
            content_html=html_main,
            text_length=len(txt_main),
            image_url=image,
            method=method,
            error="",
        ).to_dict()
        _cache_set(target, result)
        return result
    except Exception as e:
        result = SourceExtractResult(
            ok=False,
            url=target,
            title=_clean_text(title_hint),
            description=_clean_text(description_hint),
            content_html="",
            text_length=0,
            image_url="",
            method="parse",
            error=f"parse failed: {e}",
        ).to_dict()
        _cache_set(target, result)
        return result
