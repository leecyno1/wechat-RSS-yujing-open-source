import os
from typing import Any

import httpx
from fastmcp import FastMCP


def _resolve_api_base() -> str:
    base = str(os.getenv("WERSS_API_BASE", "http://we-mp-rss:8001/api/v1/wx")).strip()
    return base.rstrip("/")


def _resolve_api_key() -> str:
    direct = str(os.getenv("WERSS_API_KEY", "")).strip()
    if direct:
        return direct
    all_keys = str(os.getenv("SERVICE_API_KEYS", "")).strip()
    if all_keys:
        first = all_keys.split(",")[0].strip()
        if first:
            return first
    raise RuntimeError("Missing API key: set WERSS_API_KEY or SERVICE_API_KEYS")


def _headers() -> dict[str, str]:
    return {
        "X-API-Key": _resolve_api_key(),
    }


def _unwrap(payload: dict[str, Any]) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


mcp = FastMCP("we-mp-rss-mcp")


@mcp.tool(
    name="list_subscribed_articles",
    description="读取用户已订阅源的最新文章（包含 text_preview、summary、key_points）",
)
def list_subscribed_articles(
    user_id: str = "",
    wechat_openid: str = "",
    scope: str = "timeline",
    limit: int = 50,
    offset: int = 0,
    include_content: bool = False,
    include_llm_breakdown: bool = False,
) -> Any:
    if not str(user_id or "").strip() and not str(wechat_openid or "").strip():
        return {
            "ok": False,
            "error": "user_id 和 wechat_openid 至少提供一个",
        }
    base = _resolve_api_base()
    params = {
        "scope": scope,
        "limit": max(1, min(int(limit), 500)),
        "offset": max(0, int(offset)),
        "include_content": bool(include_content),
        "include_llm_breakdown": bool(include_llm_breakdown),
    }
    if str(user_id or "").strip():
        params["user_id"] = str(user_id).strip()
    if str(wechat_openid or "").strip():
        params["wechat_openid"] = str(wechat_openid).strip()

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{base}/service/subscriptions/articles",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        return _unwrap(resp.json())


@mcp.tool(
    name="list_channels",
    description="读取频道/博主列表（多平台）",
)
def list_channels(limit: int = 100, offset: int = 0, kw: str = "") -> Any:
    base = _resolve_api_base()
    params = {
        "limit": max(1, min(int(limit), 1000)),
        "offset": max(0, int(offset)),
        "kw": str(kw or "").strip(),
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            f"{base}/service/channels",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        return _unwrap(resp.json())


@mcp.tool(
    name="get_article_detail",
    description="读取文章详情（可含 summary / key_points / llm_breakdown）",
)
def get_article_detail(
    article_id: str,
    include_content: bool = True,
    include_llm: bool = True,
    schedule_cache: bool = True,
) -> Any:
    aid = str(article_id or "").strip()
    if not aid:
        return {"ok": False, "error": "article_id 不能为空"}
    base = _resolve_api_base()
    params = {
        "include_content": bool(include_content),
        "include_llm": bool(include_llm),
        "schedule_cache": bool(schedule_cache),
    }
    with httpx.Client(timeout=25.0) as client:
        resp = client.get(
            f"{base}/service/articles/{aid}",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        return _unwrap(resp.json())


if __name__ == "__main__":
    host = str(os.getenv("MCP_HOST", "0.0.0.0")).strip() or "0.0.0.0"
    port = int(str(os.getenv("MCP_PORT", "8090")).strip() or "8090")
    path = str(os.getenv("MCP_PATH", "/mcp")).strip() or "/mcp"
    transport = str(os.getenv("MCP_TRANSPORT", "streamable-http")).strip() or "streamable-http"
    mcp.run(
        transport=transport,
        host=host,
        port=port,
        path=path,
        log_level="info",
        show_banner=False,
    )
