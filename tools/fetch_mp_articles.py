#!/usr/bin/env python3
"""
Batch fetch WeChat MP list and per-MP article list from we-mp-rss APIs.

Usage:
  python tools/fetch_mp_articles.py \
    --base-url http://localhost:8001 \
    --username admin \
    --password '***' \
    --output /tmp/mp_articles.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

import requests


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def join_api_base(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("base_url is required")
    if base.endswith("/api/v1/wx"):
        return base
    return f"{base}/api/v1/wx"


def parse_resp(resp: requests.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {json.dumps(data, ensure_ascii=False)}")
    if isinstance(data, dict) and data.get("code", 0) != 0:
        raise RuntimeError(f"API error: {json.dumps(data, ensure_ascii=False)}")
    return data


def login(session: requests.Session, api_base: str, username: str, password: str, timeout: int) -> str:
    url = f"{api_base}/auth/login"
    payload = {"username": username, "password": password}
    resp = session.post(url, data=payload, timeout=timeout)
    data = parse_resp(resp)
    token = str(((data.get("data") or {}).get("access_token")) or "").strip()
    if not token:
        raise RuntimeError("login ok but missing access_token")
    return token


def fetch_mps(
    session: requests.Session,
    api_base: str,
    headers: dict[str, str],
    timeout: int,
    page_limit: int,
    max_mps: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        if max_mps > 0 and len(items) >= max_mps:
            return items[:max_mps]
        req_limit = min(page_limit, (max_mps - len(items)) if max_mps > 0 else page_limit)
        url = f"{api_base}/mps"
        resp = session.get(
            url,
            headers=headers,
            params={"offset": offset, "limit": req_limit, "kw": ""},
            timeout=timeout,
        )
        data = parse_resp(resp).get("data") or {}
        page_items = list(data.get("list") or [])
        if not page_items:
            break
        items.extend(page_items)
        total = int(data.get("total") or ((data.get("page") or {}).get("total") or 0))
        offset += len(page_items)
        if total and offset >= total:
            break
    return items[:max_mps] if max_mps > 0 else items


def fetch_articles_for_mp(
    session: requests.Session,
    api_base: str,
    headers: dict[str, str],
    timeout: int,
    mp_id: str,
    article_limit: int,
    article_pages: int,
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    total = 0
    for page in range(max(1, article_pages)):
        offset = page * article_limit
        url = f"{api_base}/articles"
        resp = session.get(
            url,
            headers=headers,
            params={
                "mp_id": mp_id,
                "offset": offset,
                "limit": article_limit,
            },
            timeout=timeout,
        )
        data = parse_resp(resp).get("data") or {}
        page_items = list(data.get("list") or [])
        total = int(data.get("total") or total or 0)
        items.extend(page_items)
        if len(page_items) < article_limit:
            break
    return items, total


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fetch MP list and article lists from we-mp-rss API.")
    p.add_argument("--base-url", default="http://localhost:8001", help="Server base URL, e.g. http://localhost:8001")
    p.add_argument("--username", required=True, help="Login username")
    p.add_argument("--password", required=True, help="Login password")
    p.add_argument("--output", default="", help="Output JSON file path. Empty means stdout.")
    p.add_argument("--mp-page-limit", type=int, default=1000, help="Per-request limit when listing MPs (max 1000).")
    p.add_argument("--max-mps", type=int, default=0, help="Max MP count to fetch. 0 means no cap.")
    p.add_argument("--article-limit", type=int, default=100, help="Per-page article limit for each MP.")
    p.add_argument("--article-pages", type=int, default=1, help="How many pages to fetch per MP.")
    p.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds.")
    return p


def main() -> int:
    args = build_parser().parse_args()
    api_base = join_api_base(args.base_url)
    session = requests.Session()

    try:
        token = login(session, api_base, args.username, args.password, args.timeout)
    except Exception as e:
        print(f"[ERROR] login failed: {e}", file=sys.stderr)
        return 2

    headers = {"Authorization": f"Bearer {token}"}

    try:
        mps = fetch_mps(
            session,
            api_base,
            headers,
            timeout=args.timeout,
            page_limit=max(1, min(1000, int(args.mp_page_limit))),
            max_mps=max(0, int(args.max_mps)),
        )
    except Exception as e:
        print(f"[ERROR] fetch mps failed: {e}", file=sys.stderr)
        return 3

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for idx, mp in enumerate(mps, start=1):
        mp_id = str(mp.get("id") or "").strip()
        mp_name = str(mp.get("mp_name") or mp.get("name") or "").strip()
        if not mp_id:
            continue
        try:
            articles, article_total = fetch_articles_for_mp(
                session,
                api_base,
                headers,
                timeout=args.timeout,
                mp_id=mp_id,
                article_limit=max(1, min(1000, int(args.article_limit))),
                article_pages=max(1, int(args.article_pages)),
            )
            results.append(
                {
                    "mp_id": mp_id,
                    "mp_name": mp_name,
                    "article_total": article_total,
                    "articles_fetched": len(articles),
                    "articles": articles,
                }
            )
            print(f"[{idx}/{len(mps)}] {mp_name or mp_id}: {len(articles)}", file=sys.stderr)
        except Exception as e:
            errors.append({"mp_id": mp_id, "mp_name": mp_name, "error": str(e)})
            print(f"[{idx}/{len(mps)}] {mp_name or mp_id}: ERROR {e}", file=sys.stderr)

    payload = {
        "generated_at": utc_now_iso(),
        "api_base": api_base,
        "mps_fetched": len(mps),
        "channels": results,
        "errors": errors,
    }

    out = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"[DONE] wrote {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

