import hashlib
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.config import cfg


def _make_feed_session() -> requests.Session:
    # Reuse HTTP connections and retry transient upstream failures.
    s = requests.Session()
    retries = Retry(
        total=2,
        backoff_factor=0.35,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(pool_connections=64, pool_maxsize=128, max_retries=retries)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


_FEED_SESSION = _make_feed_session()


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


def _local(tag: str) -> str:
    return str(tag or "").split("}", 1)[-1]


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return str(node.text or "").strip()


def _find_first(node: ET.Element, names: list[str]) -> ET.Element | None:
    wanted = {n.lower() for n in names}
    for child in list(node):
        if _local(child.tag).lower() in wanted:
            return child
    return None


def _parse_publish_time(value: str) -> int:
    raw = str(value or "").strip()
    if not raw:
        return int(time.time())
    try:
        return int(parsedate_to_datetime(raw).timestamp())
    except Exception:
        pass
    try:
        # Support RFC3339 timestamps such as 2026-03-06T10:00:00Z
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return int(datetime.fromisoformat(raw).timestamp())
    except Exception:
        return int(time.time())


def _stable_item_id(candidate: str) -> str:
    c = str(candidate or "").strip()
    if c:
        return c[:255]
    return hashlib.sha1(str(time.time_ns()).encode("utf-8")).hexdigest()


def normalize_source_key(source_type: str, source_url: str) -> str:
    raw = f"{str(source_type or '').strip().lower()}:{str(source_url or '').strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def build_rsshub_feed_url(base_url: str, route: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    path = str(route or "").strip().lstrip("/")
    if not base:
        raise ValueError("rsshub base url is required")
    if not path:
        raise ValueError("rsshub route is required")
    return f"{base}/{path}"


def parse_feed_text(text: str, *, source_url: str = "") -> dict[str, Any]:
    payload = str(text or "").strip()
    if not payload:
        raise ValueError("empty feed payload")

    root = ET.fromstring(payload)
    tag = _local(root.tag).lower()
    if tag == "feed":
        return _parse_atom(root, source_url=source_url)
    return _parse_rss(root, source_url=source_url)


def _parse_rss(root: ET.Element, *, source_url: str = "") -> dict[str, Any]:
    channel = _find_first(root, ["channel"])
    if channel is None:
        raise ValueError("invalid rss: missing channel")

    feed_title = _text(_find_first(channel, ["title"])) or source_url
    items: list[dict[str, Any]] = []

    for item in [c for c in list(channel) if _local(c.tag).lower() == "item"]:
        title = _text(_find_first(item, ["title"]))
        link = _text(_find_first(item, ["link"]))
        guid = _text(_find_first(item, ["guid"]))
        desc = _text(_find_first(item, ["description", "summary"]))
        pub = _text(_find_first(item, ["pubDate", "published", "updated"]))
        publish_time = _parse_publish_time(pub)
        item_id = _stable_item_id(guid or link or f"{title}:{publish_time}")
        items.append(
            {
                "id": item_id,
                "title": title or link or item_id,
                "link": link,
                "description": desc,
                "publish_time": publish_time,
            }
        )
    return {"feed_title": feed_title, "items": items}


def _parse_atom(root: ET.Element, *, source_url: str = "") -> dict[str, Any]:
    feed_title = _text(_find_first(root, ["title"])) or source_url
    items: list[dict[str, Any]] = []

    entries = [c for c in list(root) if _local(c.tag).lower() == "entry"]
    for entry in entries:
        title = _text(_find_first(entry, ["title"]))
        atom_id = _text(_find_first(entry, ["id"]))
        summary = _text(_find_first(entry, ["summary", "content"]))
        updated = _text(_find_first(entry, ["updated", "published"]))

        link = ""
        for child in list(entry):
            if _local(child.tag).lower() != "link":
                continue
            href = str(child.attrib.get("href") or "").strip()
            rel = str(child.attrib.get("rel") or "").strip().lower()
            if href and (not rel or rel == "alternate"):
                link = href
                break
            if href and not link:
                link = href

        publish_time = _parse_publish_time(updated)
        item_id = _stable_item_id(atom_id or link or f"{title}:{publish_time}")
        items.append(
            {
                "id": item_id,
                "title": title or link or item_id,
                "link": link,
                "description": summary,
                "publish_time": publish_time,
            }
        )
    return {"feed_title": feed_title, "items": items}


def fetch_feed(source_url: str, *, timeout: int = 20) -> dict[str, Any]:
    url = str(source_url or "").strip()
    if not url:
        raise ValueError("source url is required")

    try:
        timeout = int(_cfg_value("source.fetch_timeout", timeout) or timeout)
    except Exception:
        timeout = int(timeout)
    timeout = max(3, min(60, int(timeout)))

    headers = {
        "User-Agent": str(cfg.get("user_agent", "we-mp-rss/1.0") or "we-mp-rss/1.0"),
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    resp = _FEED_SESSION.get(url, headers=headers, timeout=float(timeout))
    resp.raise_for_status()
    return parse_feed_text(resp.text, source_url=url)
