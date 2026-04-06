import json
import os
import time
import threading
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Optional, Literal, Any
from urllib.parse import urlsplit

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_

from apis.base import error_response, success_response
from core.auth import get_current_user
from core.config import cfg
from core.db import DB
from core.models.article import Article
from core.models.feed import Feed
from core.models.user_subscription import UserSubscription
from core.queue import InFlightGate, TaskQueueManager
from core.source.adapters import build_rsshub_feed_url, fetch_feed, normalize_source_key
from core.source.content_extractor import fetch_source_article_content


router = APIRouter(prefix="/sources", tags=["多源订阅"])


_BUILTIN_PLATFORM_PRESETS = [
    {
        "platform": "wechat",
        "name": "微信公众号",
        "source_type": "rsshub",
        "rsshub_route_template": "/wechat/mp/:biz",
        "description": "RSSHub 微信公众号路由（填写公众号 __biz）",
        "quick_add": False,
    },
    {
        "platform": "zhihu",
        "name": "知乎",
        "source_type": "rsshub",
        "rsshub_route_template": "/zhihu/hot",
        "description": "知乎热榜（RSSHub）",
        "quick_add": False,
    },
    {
        "platform": "xueqiu",
        "name": "雪球",
        "source_type": "rsshub",
        "rsshub_route_template": "/xueqiu/user/:uid",
        "description": "雪球用户动态（RSSHub，替换 :uid）",
        "quick_add": False,
    },
    {
        "platform": "toutiao",
        "name": "头条",
        "source_type": "rsshub",
        "rsshub_route_template": "/toutiao/user/token/:token",
        "description": "今日头条作者主页（RSSHub，替换 :token）",
        "quick_add": False,
    },
    {
        "platform": "baijiahao",
        "name": "百家号",
        "source_type": "rsshub",
        "rsshub_route_template": "/baidu/search/:keyword",
        "description": "百家号内容聚合（百度搜索兜底，替换 :keyword）",
        "quick_add": False,
    },
    {
        "platform": "weibo",
        "name": "微博",
        "source_type": "rsshub",
        "rsshub_route_template": "/weibo/user/:uid",
        "description": "微博用户动态（RSSHub，替换 :uid）",
        "quick_add": False,
    },
    {
        "platform": "wsj",
        "name": "华尔街日报",
        "source_type": "rss",
        "source_url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
        "description": "WSJ World News RSS",
        "quick_add": True,
    },
    {
        "platform": "bbc",
        "name": "BBC",
        "source_type": "rss",
        "source_url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "description": "BBC World News RSS",
        "quick_add": True,
    },
]

# Backward-compatible export used by existing tests/importers.
PLATFORM_PRESETS = _BUILTIN_PLATFORM_PRESETS

_PRESET_TAG_RULES = [
    ("AI", ["ai", "openai", "chatgpt", "deepseek", "agent", "llm", "人工智能", "大模型"]),
    ("科技", ["tech", "technology", "科技", "程序", "开发", "云", "软件", "互联网", "开源"]),
    ("财经", ["finance", "business", "财经", "金融", "投资", "股票", "基金", "宏观"]),
    ("新闻", ["news", "world", "日报", "新闻", "头条", "观察", "媒体"]),
    ("商业", ["company", "商业", "企业", "品牌", "营销", "创业"]),
]

_PRESETS_LOCK = threading.Lock()


def _presets_file_path() -> str:
    return str(cfg.get("sources.presets_file", "core/source/source_presets.json") or "core/source/source_presets.json")


def _normalize_preset(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    source_type = str(item.get("source_type") or "").strip().lower()
    if source_type not in ("rss", "rsshub"):
        return None
    platform = _normalize_platform(item.get("platform"), source_type)
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    source_url = str(item.get("source_url") or "").strip()
    route = str(item.get("rsshub_route_template") or "").strip()
    if source_type == "rss" and not source_url:
        return None
    if source_type == "rsshub" and not route and not source_url:
        return None
    return {
        "platform": platform,
        "name": name,
        "source_type": source_type,
        "source_url": source_url or None,
        "rsshub_route_template": route or None,
        "description": str(item.get("description") or "").strip(),
        "quick_add": bool(item.get("quick_add", True)),
        "tags": [str(x).strip() for x in (item.get("tags") or []) if str(x).strip()][:3],
        "add_count": int(item.get("add_count") or 0),
        "avatar": str(item.get("avatar") or "").strip(),
        "community": bool(item.get("community", False)),
    }


def _load_external_platform_presets() -> list[dict]:
    p = Path(_presets_file_path())
    if not p.exists():
        return []
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    raw = obj.get("list") if isinstance(obj, dict) else obj
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for it in raw:
        normalized = _normalize_preset(it)
        if normalized:
            out.append(normalized)
    return out


def _list_platform_presets() -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    # Let external/community presets override built-in presets with the same route/url.
    for it in [*_load_external_platform_presets(), *_BUILTIN_PLATFORM_PRESETS]:
        normalized = _normalize_preset(it)
        if not normalized:
            continue
        key = "|".join(
            [
                str(normalized.get("platform") or ""),
                str(normalized.get("name") or ""),
                str(normalized.get("source_type") or ""),
                str(normalized.get("source_url") or ""),
                str(normalized.get("rsshub_route_template") or ""),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(normalized)
    merged.sort(
        key=lambda x: (
            int(x.get("add_count") or 0),
            1 if bool(x.get("community")) else 0,
            str(x.get("name") or "").lower(),
        ),
        reverse=True,
    )
    return merged


def _infer_source_tags(platform: str, name: str, description: str) -> list[str]:
    hay = " ".join([platform or "", name or "", description or ""]).lower()
    tags: list[str] = []
    for label, keywords in _PRESET_TAG_RULES:
        if any(str(kw).lower() in hay for kw in keywords):
            tags.append(label)
    if platform in {"zhihu", "xueqiu", "toutiao", "baijiahao", "weibo"} and "博主" not in tags:
        tags.append("博主")
    if platform in {"wsj", "bbc", "nytimes", "guardian", "cnn", "npr", "cnbc", "portal"} and "门户" not in tags:
        tags.append("门户")
    if not tags:
        tags.append("综合")
    return tags[:3]


def _write_external_platform_presets(items: list[dict]) -> None:
    path = Path(_presets_file_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "list": items,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _upsert_external_platform_preset(item: dict) -> None:
    normalized = _normalize_preset(item)
    if not normalized:
        return
    with _PRESETS_LOCK:
        name = str(normalized.get("name") or "").strip().lower()
        platform = str(normalized.get("platform") or "").strip().lower()
        source_type = str(normalized.get("source_type") or "").strip().lower()
        source_url = str(normalized.get("source_url") or "").strip()
        route = str(normalized.get("rsshub_route_template") or "").strip()
        raw_list = _load_external_platform_presets()
        found = None
        for it in raw_list:
            if (
                str(it.get("platform") or "").strip().lower() == platform
                and str(it.get("source_type") or "").strip().lower() == source_type
                and str(it.get("source_url") or "").strip() == source_url
                and str(it.get("rsshub_route_template") or "").strip() == route
            ):
                found = it
                break
            if str(it.get("name") or "").strip().lower() == name and platform == str(it.get("platform") or "").strip().lower():
                found = it
                break
        if found is None:
            raw_list.append(normalized)
            found = raw_list[-1]
        else:
            found.update({k: v for k, v in normalized.items() if v not in (None, "", [])})
        if not found.get("tags"):
            found["tags"] = _infer_source_tags(platform, str(found.get("name") or ""), str(found.get("description") or ""))
        found["community"] = True
        raw_list.sort(
            key=lambda x: (
                int(x.get("add_count") or 0),
                str(x.get("name") or "").lower(),
            ),
            reverse=True,
        )
        _write_external_platform_presets(raw_list)


def _fallback_rsshub_routes() -> list[dict]:
    """
    当 RSSHub 新版本不再提供 /api/routes 时，回退到项目内置目录，确保前端“路由目录”可用。
    """
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for it in _list_platform_presets():
        if str(it.get("source_type") or "").strip().lower() != "rsshub":
            continue
        path = str(it.get("rsshub_route_template") or "").strip()
        if not path:
            continue
        if not path.startswith("/"):
            path = "/" + path
        if path in seen:
            continue
        seen.add(path)
        title = str(it.get("name") or "").strip() or path
        items.append({"path": path, "title": title, "maintainers": []})

    seed_routes = [
        {"path": "/zhihu/hot", "title": "知乎热榜"},
        {"path": "/zhihu/daily", "title": "知乎日报"},
        {"path": "/v2ex/tab/all", "title": "V2EX 全部"},
        {"path": "/bilibili/ranking/0/3/1", "title": "B 站综合排行"},
        {"path": "/rsshub/routes", "title": "RSSHub 路由更新"},
        {"path": "/wechat/mp/:biz", "title": "微信公众号（填写 __biz）"},
    ]
    for it in seed_routes:
        path = str(it.get("path") or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        items.append({"path": path, "title": str(it.get("title") or path), "maintainers": []})
    return items


def _load_routes_from_rsshub_api(base: str, timeout: int) -> tuple[list[dict], str]:
    try:
        resp = requests.get(f"{base}/api/routes", timeout=timeout)
        if not resp.ok:
            return [], f"HTTP {resp.status_code}"
        data = resp.json() if "json" in str(resp.headers.get("content-type", "")).lower() else {}
        raw_list = data.get("data") if isinstance(data, dict) else data
        if isinstance(raw_list, dict):
            raw_list = list(raw_list.values())
        if not isinstance(raw_list, list):
            return [], "unsupported api schema"
        items: list[dict[str, Any]] = []
        for it in raw_list:
            if not isinstance(it, dict):
                continue
            path = str(it.get("path") or it.get("route") or "").strip()
            title = str(it.get("title") or it.get("name") or "").strip()
            maintainers = it.get("maintainers") or []
            if not path:
                continue
            if not path.startswith("/"):
                path = "/" + path
            items.append(
                {
                    "path": path,
                    "title": title or path,
                    "maintainers": maintainers if isinstance(maintainers, list) else [],
                }
            )
        return items, ""
    except Exception as e:
        return [], str(e)


def _load_rsshub_route_catalog(base: str, timeout: int) -> tuple[list[dict], str, str]:
    api_items, api_error = _load_routes_from_rsshub_api(base, timeout)
    if api_items:
        return api_items, "api", ""
    return _fallback_rsshub_routes(), "fallback_presets", api_error


_SOURCE_REFRESH_QUEUE: TaskQueueManager | None = None
_SOURCE_MAINTENANCE_QUEUE: TaskQueueManager | None = None
_SOURCE_CONTENT_QUEUE: TaskQueueManager | None = None
_MAINTENANCE_LOCK = threading.Lock()
_SOURCE_CONTENT_GATE = InFlightGate()
_BACKFILL_FAIL_LOCK = threading.Lock()


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


def _source_refresh_workers() -> int:
    try:
        workers = int(_cfg_value("sources.refresh_workers", 10) or 10)
    except Exception:
        workers = 10
    return max(1, min(64, workers))


def _ensure_source_refresh_queue() -> TaskQueueManager:
    global _SOURCE_REFRESH_QUEUE
    if _SOURCE_REFRESH_QUEUE is not None:
        return _SOURCE_REFRESH_QUEUE
    q = TaskQueueManager(tag="多源刷新", workers=_source_refresh_workers())
    q.run_task_background()
    _SOURCE_REFRESH_QUEUE = q
    return q


def _source_maintenance_workers() -> int:
    try:
        workers = int(_cfg_value("sources.maintenance_workers", 2) or 2)
    except Exception:
        workers = 2
    return max(1, min(8, workers))


def _source_content_workers() -> int:
    try:
        workers = int(_cfg_value("sources.content_workers", 8) or 8)
    except Exception:
        workers = 8
    return max(1, min(16, workers))


def _ensure_source_content_queue() -> TaskQueueManager:
    global _SOURCE_CONTENT_QUEUE
    if _SOURCE_CONTENT_QUEUE is not None:
        return _SOURCE_CONTENT_QUEUE
    q = TaskQueueManager(tag="正文预抓取", workers=_source_content_workers())
    q.run_task_background()
    _SOURCE_CONTENT_QUEUE = q
    return q


def _ensure_source_maintenance_queue() -> TaskQueueManager:
    global _SOURCE_MAINTENANCE_QUEUE
    if _SOURCE_MAINTENANCE_QUEUE is not None:
        return _SOURCE_MAINTENANCE_QUEUE
    q = TaskQueueManager(tag="来源巡检", workers=_source_maintenance_workers())
    q.run_task_background()
    _SOURCE_MAINTENANCE_QUEUE = q
    return q


def _maintenance_tasks_file() -> str:
    return str(
        _cfg_value("sources.maintenance_tasks_file", "data/source_maintenance_tasks.json")
        or "data/source_maintenance_tasks.json"
    )


def _backfill_fail_state_file() -> str:
    return str(
        _cfg_value("sources.content_backfill_fail_state_file", "data/source_backfill_fail_state.json")
        or "data/source_backfill_fail_state.json"
    )


def _load_backfill_fail_state() -> dict:
    p = Path(_backfill_fail_state_file())
    if not p.exists():
        return {"version": 1, "updated_at": "", "feeds": {}}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        feeds = obj.get("feeds") if isinstance(obj, dict) else {}
        if not isinstance(feeds, dict):
            feeds = {}
        return {"version": 1, "updated_at": str(obj.get("updated_at") or ""), "feeds": feeds}
    except Exception:
        return {"version": 1, "updated_at": "", "feeds": {}}


def _save_backfill_fail_state(state: dict) -> None:
    p = Path(_backfill_fail_state_file())
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "feeds": (state or {}).get("feeds") or {},
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _is_blocked_error(error: str) -> bool:
    e = str(error or "").strip().lower()
    if not e:
        return False
    keys = ["403", "401", "forbidden", "unauthorized", "captcha", "denied", "anti-bot", "access denied"]
    return any(k in e for k in keys)


def _source_prefetch_enabled() -> bool:
    raw = _cfg_value("sources.prefetch_content_on_refresh", True)
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _source_prefetch_per_feed() -> int:
    try:
        value = int(_cfg_value("sources.prefetch_content_per_feed", 2) or 2)
    except Exception:
        value = 2
    return max(0, min(10, value))


def _prefetch_source_article_content(article_id: str, *, force: bool = False) -> dict:
    session = DB.get_session()
    try:
        aid = str(article_id or "").strip()
        if not aid:
            return {"ok": False, "error": "empty article id"}
        article = (
            session.query(Article)
            .filter(Article.id == aid)
            .first()
        )
        if not article:
            return {"ok": False, "error": "article not found"}
        feed = session.query(Feed).filter(Feed.id == article.mp_id).first()
        if not feed:
            return {"ok": False, "error": "feed not found"}
        if str(feed.source_type or "").strip().lower() not in ("rss", "rsshub"):
            return {"ok": False, "error": "not source article"}
        has_content = bool(str(article.content or "").strip() and str(article.content or "").strip() != "DELETED")
        if has_content and not force:
            return {"ok": True, "skipped": True, "reason": "already has content"}
        url = str(article.url or "").strip()
        if not url:
            return {"ok": False, "error": "empty article url"}
        ext = fetch_source_article_content(
            url,
            title_hint=str(article.title or ""),
            description_hint=str(article.description or ""),
        )
        if not bool(ext.get("ok")):
            return {"ok": False, "error": str(ext.get("error") or "extract failed")}

        changed = False
        content_html = str(ext.get("content_html") or ext.get("content") or "").strip()
        description = str(ext.get("description") or "").strip()
        pic_url = str(ext.get("pic_url") or ext.get("topic_image") or "").strip()
        if content_html and (force or not has_content):
            article.content = content_html
            changed = True
        if description and not str(article.description or "").strip():
            article.description = description
            changed = True
        if pic_url and not str(article.pic_url or "").strip():
            article.pic_url = pic_url
            changed = True
        if changed:
            article.updated_at = datetime.now()
            session.add(article)
            session.commit()
        return {
            "ok": True,
            "changed": changed,
            "text_length": int(ext.get("text_length") or 0),
            "method": str(ext.get("method") or ""),
        }
    except Exception as e:
        try:
            session.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)}
    finally:
        try:
            session.close()
        except Exception:
            pass


def _prefetch_source_article_content_task(article_id: str, force: bool = False) -> None:
    try:
        _prefetch_source_article_content(article_id, force=force)
    finally:
        _SOURCE_CONTENT_GATE.release(str(article_id or ""))


def _schedule_source_content_prefetch(article_id: str, *, force: bool = False) -> bool:
    aid = str(article_id or "").strip()
    if not aid:
        return False
    if not _SOURCE_CONTENT_GATE.try_acquire(aid):
        return False
    try:
        _ensure_source_content_queue().add_task(_prefetch_source_article_content_task, aid, force)
        return True
    except Exception:
        _SOURCE_CONTENT_GATE.release(aid)
        return False


def _enqueue_prefetch_for_feed(session, feed_id: str, *, limit: int) -> int:
    if limit <= 0:
        return 0
    rows = (
        session.query(Article.id)
        .filter(Article.mp_id == str(feed_id))
        .filter(or_(Article.content.is_(None), Article.content == "", Article.content == "DELETED"))
        .order_by(Article.publish_time.desc())
        .limit(max(1, min(200, limit * 4)))
        .all()
    )
    queued = 0
    for row in rows:
        aid = str(row[0] if row else "")
        if not aid:
            continue
        if _schedule_source_content_prefetch(aid):
            queued += 1
        if queued >= limit:
            break
    return queued


def _load_maintenance_tasks() -> list[dict]:
    p = Path(_maintenance_tasks_file())
    if not p.exists():
        return []
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        raw = obj.get("tasks") if isinstance(obj, dict) else []
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
    except Exception:
        pass
    return []


def _save_maintenance_tasks(tasks: list[dict]) -> None:
    p = Path(_maintenance_tasks_file())
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tasks": tasks[:200],
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _upsert_maintenance_task(task: dict) -> dict:
    with _MAINTENANCE_LOCK:
        tasks = _load_maintenance_tasks()
        tid = str(task.get("id") or "").strip()
        if not tid:
            raise ValueError("task id is required")
        now_s = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task["updated_at"] = now_s
        found = False
        for i, it in enumerate(tasks):
            if str(it.get("id") or "") == tid:
                tasks[i] = {**it, **task}
                found = True
                break
        if not found:
            if not task.get("created_at"):
                task["created_at"] = now_s
            tasks.insert(0, task)
        _save_maintenance_tasks(tasks)
        for it in tasks:
            if str(it.get("id") or "") == tid:
                return it
        return task


def _get_maintenance_task(task_id: str) -> dict | None:
    tid = str(task_id or "").strip()
    if not tid:
        return None
    with _MAINTENANCE_LOCK:
        tasks = _load_maintenance_tasks()
        for it in tasks:
            if str(it.get("id") or "") == tid:
                return it
    return None


def _update_maintenance_task(task_id: str, patch: dict) -> dict | None:
    task = _get_maintenance_task(task_id)
    if not task:
        return None
    task.update(patch or {})
    return _upsert_maintenance_task(task)


def _find_active_maintenance_task(task_type: str) -> dict | None:
    tt = str(task_type or "").strip()
    if not tt:
        return None
    with _MAINTENANCE_LOCK:
        tasks = _load_maintenance_tasks()
        for it in tasks:
            if str(it.get("type") or "") != tt:
                continue
            status = str(it.get("status") or "").strip().lower()
            if status in {"pending", "running"}:
                return it
    return None


def _normalize_platform(source_platform: str | None, source_type: str) -> str:
    raw = str(source_platform or "").strip().lower().replace(" ", "_")
    alias = {
        "weixin": "wechat",
        "wx": "wechat",
        "zhihu.com": "zhihu",
        "xq": "xueqiu",
        "toutiao.com": "toutiao",
        "baijia": "baijiahao",
        "wallstreetjournal": "wsj",
    }
    raw = alias.get(raw, raw)
    if not raw:
        return "rsshub" if str(source_type).strip().lower() == "rsshub" else "rss"
    # Keep schema simple and safe.
    return "".join([c for c in raw if c.isalnum() or c in ("_", "-")])[:32] or "rss"


def _uid(current_user: dict) -> str:
    try:
        return str(current_user.get("original_user").id)
    except Exception:
        return str(current_user.get("username") or "")


def _is_admin(current_user: dict) -> bool:
    try:
        return str(current_user.get("role") or "") == "admin" or str(current_user.get("username") or "") == "admin"
    except Exception:
        return False


def _rsshub_internal_url() -> str:
    return str(
        cfg.get("rsshub.internal_url", cfg.get("sources.rsshub_base_url", "http://rsshub:1200") or "http://rsshub:1200")
        or "http://rsshub:1200"
    ).strip().rstrip("/")


def _rsshub_public_url() -> str:
    return str(cfg.get("rsshub.public_url", _rsshub_internal_url()) or _rsshub_internal_url()).strip().rstrip("/")


def _rsshub_timeout() -> int:
    try:
        v = int(cfg.get("rsshub.timeout", cfg.get("source.fetch_timeout", 20) or 20) or 20)
    except Exception:
        v = 20
    return max(3, min(60, v))


def _normalize_rsshub_route(route: str | None) -> str:
    raw = str(route or "").strip()
    if not raw:
        raise ValueError("rsshub route 不能为空")
    if raw.startswith("http://") or raw.startswith("https://"):
        u = urlsplit(raw)
        raw = u.path or "/"
        if u.query:
            raw = f"{raw}?{u.query}"
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw


def _guess_platform_from_rsshub_route(route: str) -> str:
    p = str(route or "").split("?", 1)[0].strip("/")
    first = p.split("/", 1)[0].strip().lower() if p else ""
    alias = {
        "wx": "wechat",
        "weixin": "wechat",
        "jinritoutiao": "toutiao",
        "baijia": "baijiahao",
    }
    first = alias.get(first, first)
    if not first:
        return "rsshub"
    if first in {"wechat", "zhihu", "xueqiu", "toutiao", "baijiahao", "weibo", "bilibili", "v2ex", "github", "juejin"}:
        return first
    return "rsshub"


def _resolve_rsshub_base(base_url: str | None, current_user: dict) -> str:
    """
    防止普通用户把服务当作任意 URL 代理（SSRF）。
    - 管理员：允许自定义 base_url；
    - 普通用户：仅允许 internal/public 两个已配置地址。
    """
    candidate = str(base_url or "").strip().rstrip("/")
    if not candidate:
        return _rsshub_internal_url()
    if _is_admin(current_user):
        return candidate
    allowed = {_rsshub_internal_url(), _rsshub_public_url()}
    if candidate not in allowed:
        raise HTTPException(status_code=403, detail=error_response(code=40302, message="不允许使用该 RSSHub 地址"))
    return candidate


def _ensure_source_url(source_type: str, source_url: str | None, rsshub_base_url: str | None, rsshub_route: str | None) -> str:
    st = str(source_type or "").strip().lower()
    if st == "rsshub":
        if source_url:
            return str(source_url).strip()
        base = str(rsshub_base_url or _rsshub_internal_url()).strip()
        return build_rsshub_feed_url(base, str(rsshub_route or ""))
    return str(source_url or "").strip()


def _rsshub_fetch_candidates(source_url: str) -> list[str]:
    raw = str(source_url or "").strip()
    if not raw:
        return []

    candidates: list[str] = []
    try:
        route = _normalize_rsshub_route(raw)
        internal = build_rsshub_feed_url(_rsshub_internal_url(), route)
        if internal:
            candidates.append(internal)
    except Exception:
        pass

    if (raw.startswith("http://") or raw.startswith("https://")) and raw not in candidates:
        candidates.append(raw)

    if not candidates:
        candidates.append(raw)
    return candidates


def _fetch_feed_for_source(source_type: str, source_url: str) -> tuple[dict[str, Any], str]:
    st = str(source_type or "").strip().lower()
    url = str(source_url or "").strip()
    if not url:
        raise ValueError("source url is required")

    if st != "rsshub":
        return fetch_feed(url), url

    last_error: Exception | None = None
    candidates = _rsshub_fetch_candidates(url)
    for candidate in candidates:
        try:
            return fetch_feed(candidate), candidate
        except Exception as e:
            last_error = e
            continue

    if last_error:
        raise last_error
    raise RuntimeError("rsshub feed fetch failed")


class AddSourceFeedRequest(BaseModel):
    source_type: Literal["rss", "rsshub"] = Field("rss", description="来源类型")
    source_platform: Optional[str] = Field(None, description="平台标识: zhihu/xueqiu/toutiao/baijiahao/wsj/bbc...")
    source_url: Optional[str] = Field(None, description="RSS/Atom URL，rsshub可直接填完整URL")
    rsshub_base_url: Optional[str] = Field(None, description="RSSHub实例URL（配合 route）")
    rsshub_route: Optional[str] = Field(None, description="RSSHub路由路径")
    name: Optional[str] = Field(None, description="可选：自定义频道名称")
    auto_subscribe: bool = Field(True, description="创建后自动订阅当前用户")
    validate_on_add: bool = Field(False, description="创建时是否立即校验抓取（默认否，后台异步刷新）")


def _as_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    if not s:
        return default
    return s in {"1", "true", "yes", "on"}


def _validate_source_on_add_default() -> bool:
    return _as_bool(cfg.get("sources.add_validate_on_create", False), False)


class SourceAuditTaskRequest(BaseModel):
    platforms: list[str] = Field(default_factory=list, description="可选平台过滤，如 ['bbc','guardian']")
    limit: int = Field(200, ge=1, le=2000, description="最大巡检来源数")
    sample_per_feed: int = Field(2, ge=1, le=5, description="每个来源抽样文章数")
    min_text_length: int = Field(160, ge=60, le=2000, description="正文最小文本长度阈值")
    remove_failed_sources: bool = Field(False, description="是否自动下线失败来源（删除来源与订阅关系）")
    failure_success_rate: float = Field(0.5, ge=0.0, le=1.0, description="成功率低于该阈值视为失败")
    include_platforms_only: bool = Field(False, description="为 true 时仅巡检 platforms 里的平台")


class SourceContentBackfillTaskRequest(BaseModel):
    platforms: list[str] = Field(default_factory=list, description="可选平台过滤，如 ['bbc','zhihu']")
    feed_ids: list[str] = Field(default_factory=list, description="可选来源ID过滤")
    days: int = Field(3, ge=0, le=30, description="仅回填最近 N 天，0 表示不限制")
    limit: int = Field(800, ge=1, le=5000, description="本次最大处理文章数")
    workers: int = Field(8, ge=1, le=32, description="并行抓取 worker 数")
    missing_only: bool = Field(True, description="仅处理缺少正文的文章")
    force: bool = Field(False, description="强制重抓正文（覆盖已有正文）")
    max_failures_per_feed: int = Field(4, ge=1, le=20, description="单来源失败阈值，达到后本轮跳过该来源")
    blocked_cooldown_hours: int = Field(12, ge=1, le=72, description="命中封禁类错误后的来源冷却小时数")
    skip_cooldown_feeds: bool = Field(True, description="是否跳过处于冷却期的来源")
    enqueue_insights: bool = Field(True, description="正文更新后异步触发关键信息/摘要生成")


def _audit_source_feed(feed: Feed, *, sample_per_feed: int, min_text_length: int, failure_success_rate: float) -> dict:
    source_url = str(feed.source_url or "").strip()
    parsed, _ = _fetch_feed_for_source(str(feed.source_type or ""), source_url)
    items = parsed.get("items") or []
    checks = []
    success = 0
    checked = 0

    for item in items[: sample_per_feed]:
        link = str(item.get("link") or "").strip()
        if not link:
            continue
        checked += 1
        ext = fetch_source_article_content(
            link,
            title_hint=str(item.get("title") or ""),
            description_hint=str(item.get("description") or ""),
        )
        ok = bool(ext.get("ok")) and int(ext.get("text_length") or 0) >= int(min_text_length)
        if ok:
            success += 1
        checks.append(
            {
                "url": link,
                "ok": ok,
                "text_length": int(ext.get("text_length") or 0),
                "method": str(ext.get("method") or ""),
                "error": str(ext.get("error") or ""),
            }
        )

    success_rate = (float(success) / float(checked)) if checked > 0 else 0.0
    keep = checked > 0 and success_rate >= float(failure_success_rate)
    return {
        "feed_id": str(feed.id),
        "name": str(feed.mp_name or ""),
        "platform": str(feed.source_platform or ""),
        "source_type": str(feed.source_type or ""),
        "source_url": source_url,
        "checked": int(checked),
        "success": int(success),
        "success_rate": round(success_rate, 4),
        "keep": bool(keep),
        "checks": checks,
    }


def _run_source_audit_task(task_id: str) -> None:
    task = _get_maintenance_task(task_id)
    if not task:
        return
    options = task.get("options") or {}
    sample_per_feed = int(options.get("sample_per_feed") or 2)
    min_text_length = int(options.get("min_text_length") or 160)
    remove_failed = bool(options.get("remove_failed_sources"))
    failure_success_rate = float(options.get("failure_success_rate") or 0.5)
    limit = int(options.get("limit") or 200)
    include_platforms_only = bool(options.get("include_platforms_only"))
    platforms = [str(x).strip().lower() for x in (options.get("platforms") or []) if str(x).strip()]

    _update_maintenance_task(
        task_id,
        {
            "status": "running",
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "progress": {"total": 0, "done": 0, "ok": 0, "failed": 0, "removed": 0},
            "results": [],
            "error": "",
        },
    )

    session = DB.get_session()
    try:
        q = session.query(Feed).filter(Feed.source_type.in_(["rss", "rsshub"]))
        if platforms:
            if include_platforms_only:
                q = q.filter(Feed.source_platform.in_(platforms))
        feeds = q.limit(limit).all()
        total = len(feeds)
        _update_maintenance_task(task_id, {"progress": {"total": total, "done": 0, "ok": 0, "failed": 0, "removed": 0}})

        done = 0
        ok_count = 0
        fail_count = 0
        removed_count = 0
        results: list[dict] = []

        for feed in feeds:
            done += 1
            try:
                result = _audit_source_feed(
                    feed,
                    sample_per_feed=sample_per_feed,
                    min_text_length=min_text_length,
                    failure_success_rate=failure_success_rate,
                )
            except Exception as e:
                result = {
                    "feed_id": str(feed.id),
                    "name": str(feed.mp_name or ""),
                    "platform": str(feed.source_platform or ""),
                    "source_type": str(feed.source_type or ""),
                    "source_url": str(feed.source_url or ""),
                    "checked": 0,
                    "success": 0,
                    "success_rate": 0.0,
                    "keep": False,
                    "checks": [],
                    "error": str(e),
                }

            removed = False
            if remove_failed and not bool(result.get("keep")):
                try:
                    session.query(UserSubscription).filter(UserSubscription.feed_id == str(feed.id)).delete(synchronize_session=False)
                    session.query(Feed).filter(Feed.id == str(feed.id)).delete(synchronize_session=False)
                    session.commit()
                    removed = True
                except Exception:
                    session.rollback()
                    removed = False

            result["removed"] = bool(removed)
            results.append(result)
            if bool(result.get("keep")):
                ok_count += 1
            else:
                fail_count += 1
            if removed:
                removed_count += 1

            _update_maintenance_task(
                task_id,
                {
                    "progress": {
                        "total": total,
                        "done": done,
                        "ok": ok_count,
                        "failed": fail_count,
                        "removed": removed_count,
                    },
                    "results": results[-300:],
                },
            )

        _update_maintenance_task(
            task_id,
            {
                "status": "completed",
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "progress": {
                    "total": total,
                    "done": done,
                    "ok": ok_count,
                    "failed": fail_count,
                    "removed": removed_count,
                },
                "results": results[-300:],
            },
        )
    except Exception as e:
        _update_maintenance_task(
            task_id,
            {
                "status": "failed",
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(e),
            },
        )
    finally:
        try:
            session.close()
        except Exception:
            pass


def _build_source_content_backfill_task(*, options: dict, created_by: str) -> dict:
    task_id = f"src_backfill_{uuid.uuid4().hex[:16]}"
    return {
        "id": task_id,
        "type": "source_content_backfill",
        "status": "pending",
        "created_by": str(created_by or "system"),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "options": options,
        "progress": {"total": 0, "done": 0, "ok": 0, "failed": 0, "skipped": 0},
        "results": [],
        "error": "",
    }


def _run_source_content_backfill_task(task_id: str) -> None:
    task = _get_maintenance_task(task_id)
    if not task:
        return
    options = task.get("options") or {}
    platforms = [str(x).strip().lower() for x in (options.get("platforms") or []) if str(x).strip()]
    feed_ids = [str(x).strip() for x in (options.get("feed_ids") or []) if str(x).strip()]
    days = int(options.get("days") or 0)
    limit = int(options.get("limit") or 800)
    workers = int(options.get("workers") or 8)
    missing_only = bool(options.get("missing_only", True))
    force = bool(options.get("force", False))
    max_failures_per_feed = int(options.get("max_failures_per_feed") or 4)
    blocked_cooldown_hours = int(options.get("blocked_cooldown_hours") or 12)
    skip_cooldown_feeds = bool(options.get("skip_cooldown_feeds", True))
    enqueue_insights = bool(options.get("enqueue_insights", True))

    _update_maintenance_task(
        task_id,
        {
            "status": "running",
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "progress": {"total": 0, "done": 0, "ok": 0, "failed": 0, "skipped": 0},
            "results": [],
            "error": "",
        },
    )

    session = DB.get_session()
    try:
        q = (
            session.query(Article.id, Article.mp_id, Feed.source_platform)
            .join(Feed, Feed.id == Article.mp_id)
            .filter(Feed.source_type.in_(["rss", "rsshub"]))
        )
        if platforms:
            q = q.filter(Feed.source_platform.in_(platforms))
        if feed_ids:
            q = q.filter(Article.mp_id.in_(feed_ids))
        if days > 0:
            q = q.filter(Article.publish_time >= int(time.time()) - int(days) * 86400)
        if missing_only and not force:
            q = q.filter(or_(Article.content.is_(None), Article.content == "", Article.content == "DELETED"))

        rows = q.order_by(Article.publish_time.desc()).limit(max(1, min(5000, limit))).all()
        raw_jobs: list[dict] = []
        for row in rows:
            aid = str(row[0] if row else "").strip()
            if not aid:
                continue
            raw_jobs.append(
                {
                    "article_id": aid,
                    "feed_id": str(row[1] if row else "").strip(),
                    "platform": str(row[2] if row else "").strip().lower() or "unknown",
                }
            )

        # 平台分桶后轮询出队，避免单个平台大列表阻塞其它平台。
        buckets: dict[str, list[dict]] = defaultdict(list)
        for job in raw_jobs:
            buckets[str(job.get("platform") or "unknown")].append(job)
        jobs: list[dict] = []
        while True:
            progressed = False
            for p in sorted(list(buckets.keys())):
                arr = buckets.get(p) or []
                if not arr:
                    continue
                jobs.append(arr.pop(0))
                progressed = True
            if not progressed:
                break

        total = len(jobs)
        _update_maintenance_task(task_id, {"progress": {"total": total, "done": 0, "ok": 0, "failed": 0, "skipped": 0}})

        done = 0
        ok_count = 0
        fail_count = 0
        skipped_count = 0
        results: list[dict] = []
        feed_failures: dict[str, int] = defaultdict(int)
        blocked_feeds_this_run: set[str] = set()

        service = None
        InsightsQueue = None
        if enqueue_insights:
            try:
                from core.insights import InsightsService
                from core.queue import InsightsQueue as _InsightsQueue

                service = InsightsService()
                InsightsQueue = _InsightsQueue
            except Exception:
                service = None
                InsightsQueue = None

        now_ts = int(time.time())
        with _BACKFILL_FAIL_LOCK:
            fail_state = _load_backfill_fail_state()
            fail_feeds = (fail_state.get("feeds") or {}) if isinstance(fail_state, dict) else {}

        def _record_skip(job: dict, reason: str) -> None:
            nonlocal done, skipped_count
            done += 1
            skipped_count += 1
            results.append(
                {
                    "article_id": str(job.get("article_id") or ""),
                    "ok": True,
                    "skipped": True,
                    "error": "",
                    "method": "",
                    "reason": reason,
                }
            )

        # 预过滤冷却中的来源
        filtered_jobs: list[dict] = []
        for job in jobs:
            fid = str(job.get("feed_id") or "")
            if skip_cooldown_feeds and fid:
                fstate = fail_feeds.get(fid) if isinstance(fail_feeds, dict) else None
                cooldown_until = int((fstate or {}).get("cooldown_until") or 0)
                if cooldown_until > now_ts:
                    _record_skip(job, "feed_cooldown")
                    continue
            filtered_jobs.append(job)

        inflight: dict[Any, dict] = {}
        idx = 0
        run_workers = max(1, min(32, workers))
        submit_window = max(run_workers * 2, 4)
        with ThreadPoolExecutor(max_workers=run_workers) as ex:
            while idx < len(filtered_jobs) or inflight:
                while idx < len(filtered_jobs) and len(inflight) < submit_window:
                    job = filtered_jobs[idx]
                    idx += 1
                    fid = str(job.get("feed_id") or "")
                    if fid and (fid in blocked_feeds_this_run or feed_failures.get(fid, 0) >= max_failures_per_feed):
                        blocked_feeds_this_run.add(fid)
                        _record_skip(job, "feed_failed_too_many")
                        continue
                    fut = ex.submit(_prefetch_source_article_content, str(job.get("article_id") or ""), force=force)
                    inflight[fut] = job

                if not inflight:
                    continue

                for fut in as_completed(list(inflight.keys())):
                    job = inflight.pop(fut, None) or {}
                    aid = str(job.get("article_id") or "")
                    fid = str(job.get("feed_id") or "")
                    done += 1
                    try:
                        ret = fut.result()
                    except Exception as e:
                        ret = {"ok": False, "error": str(e), "method": ""}
                    ok = bool(ret.get("ok"))
                    skipped = bool(ret.get("skipped"))
                    err = str(ret.get("error") or "")
                    method = str(ret.get("method") or "")

                    if ok and not skipped:
                        ok_count += 1
                        if service is not None:
                            try:
                                if InsightsQueue is not None:
                                    InsightsQueue.add_task(service.ensure_cached, aid)
                                else:
                                    service.ensure_cached(aid)
                            except Exception:
                                pass
                    elif ok and skipped:
                        skipped_count += 1
                    else:
                        fail_count += 1
                        if fid:
                            feed_failures[fid] += 1
                            if _is_blocked_error(err) and feed_failures[fid] >= max_failures_per_feed:
                                blocked_feeds_this_run.add(fid)
                                # 进入跨轮次冷却期，避免每轮都反复打 403。
                                fail_feeds[fid] = {
                                    "cooldown_until": int(time.time()) + int(blocked_cooldown_hours) * 3600,
                                    "last_error": err[:300],
                                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                }

                    results.append(
                        {
                            "article_id": aid,
                            "ok": ok,
                            "skipped": skipped,
                            "error": err,
                            "method": method,
                            "feed_id": fid,
                            "platform": str(job.get("platform") or ""),
                        }
                    )
                    break

                if done == 1 or done % 10 == 0 or done >= total:
                    _update_maintenance_task(
                        task_id,
                        {
                            "progress": {
                                "total": total,
                                "done": done,
                                "ok": ok_count,
                                "failed": fail_count,
                                "skipped": skipped_count,
                            },
                            "results": results[-300:],
                        },
                    )

        with _BACKFILL_FAIL_LOCK:
            _save_backfill_fail_state({"feeds": fail_feeds})

        _update_maintenance_task(
            task_id,
            {
                "status": "completed",
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "progress": {
                    "total": total,
                    "done": done,
                    "ok": ok_count,
                    "failed": fail_count,
                    "skipped": skipped_count,
                },
                "results": results[-300:],
            },
        )
    except Exception as e:
        _update_maintenance_task(
            task_id,
            {
                "status": "failed",
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(e),
            },
        )
    finally:
        try:
            session.close()
        except Exception:
            pass


def enqueue_source_content_backfill_system_task(*, options: dict | None = None, allow_parallel: bool = False) -> dict:
    active = _find_active_maintenance_task("source_content_backfill")
    if active and not allow_parallel:
        return {"task_id": str(active.get("id") or ""), "status": str(active.get("status") or "running"), "deduped": True}

    opts = options or {}
    task = _build_source_content_backfill_task(options=opts, created_by="system")
    _upsert_maintenance_task(task)
    queue = _ensure_source_maintenance_queue()
    queue.add_task(_run_source_content_backfill_task, str(task.get("id") or ""))
    return {"task_id": str(task.get("id") or ""), "status": "pending", "deduped": False}


def _add_source_feed_impl(payload: AddSourceFeedRequest, current_user: dict):
    session = DB.get_session()
    now = datetime.now()
    try:
        source_platform = _normalize_platform(payload.source_platform, payload.source_type)
        source_url = _ensure_source_url(
            source_type=payload.source_type,
            source_url=payload.source_url,
            rsshub_base_url=payload.rsshub_base_url,
            rsshub_route=payload.rsshub_route,
        )
        if not source_url:
            raise HTTPException(status_code=400, detail=error_response(code=40001, message="source_url 不能为空"))

        parsed: dict[str, Any] = {}
        validation_warning = ""
        should_validate = bool(payload.validate_on_add) or _validate_source_on_add_default()
        if should_validate:
            try:
                parsed, _ = _fetch_feed_for_source(payload.source_type, source_url)
            except Exception as e:
                # Strict validation mode keeps old behavior.
                raise RuntimeError(f"源地址校验失败: {str(e)}")

        source_key = normalize_source_key(payload.source_type, source_url)

        feed = session.query(Feed).filter(Feed.source_key == source_key).first()
        created = False
        if not feed:
            feed_id = f"SRC_{source_key[:16].upper()}"
            while session.query(func.count(Feed.id)).filter(Feed.id == feed_id).scalar():
                feed_id = f"SRC_{uuid.uuid4().hex[:16].upper()}"

            feed = Feed(
                id=feed_id,
                mp_name=(payload.name or parsed.get("feed_title") or source_url)[:255],
                mp_intro="",
                mp_cover="",
                status=1,
                sync_time=0,
                update_time=0,
                created_at=now,
                updated_at=now,
                faker_id="",
                source_type=payload.source_type,
                source_platform=source_platform,
                source_url=source_url,
                source_key=source_key,
                source_config=json.dumps(
                    {
                        "rsshub_base_url": (payload.rsshub_base_url or "").strip(),
                        "rsshub_route": (payload.rsshub_route or "").strip(),
                    },
                    ensure_ascii=False,
                ),
            )
            session.add(feed)
            session.commit()
            created = True
        else:
            feed.source_type = payload.source_type
            feed.source_platform = source_platform
            feed.source_url = source_url
            if payload.name:
                feed.mp_name = payload.name[:255]
            elif parsed.get("feed_title"):
                feed.mp_name = str(parsed.get("feed_title"))[:255]
            feed.updated_at = now
            session.add(feed)
            session.commit()

        if payload.auto_subscribe:
            user_id = _uid(current_user)
            exists = (
                session.query(func.count(UserSubscription.id))
                .filter(UserSubscription.user_id == user_id)
                .filter(UserSubscription.feed_id == feed.id)
                .scalar()
            )
            if not exists:
                session.add(UserSubscription(user_id=user_id, feed_id=feed.id, created_at=now, updated_at=now))
                session.commit()
        sub_count = (
            session.query(func.count(UserSubscription.id))
            .filter(UserSubscription.feed_id == feed.id)
            .scalar()
        ) or 0

        try:
            _upsert_external_platform_preset(
                {
                    "platform": source_platform,
                    "name": feed.mp_name,
                    "source_type": feed.source_type,
                    "source_url": feed.source_url,
                    "rsshub_route_template": str(payload.rsshub_route or "").strip() or None,
                    "description": str(feed.mp_intro or payload.name or "").strip(),
                    "quick_add": True,
                    "tags": _infer_source_tags(source_platform, str(feed.mp_name or ""), str(feed.mp_intro or payload.name or "")),
                    "add_count": int(sub_count or 0),
                    "community": True,
                }
            )
        except Exception:
            pass

        # Non-blocking mode: enqueue a background refresh so users can subscribe first and fetch later.
        queued_refresh = False
        if not should_validate:
            try:
                _ensure_source_refresh_queue().add_task(_refresh_source_feed_internal, str(feed.id))
                queued_refresh = True
            except Exception as e:
                validation_warning = f"已添加订阅，但后台刷新入队失败: {str(e)}"

        return {
            "created": created,
            "feed": {
                "id": feed.id,
                "name": feed.mp_name,
                "source_type": feed.source_type,
                "source_platform": feed.source_platform or "",
                "source_url": feed.source_url,
                "items_preview": int(len(parsed.get("items") or [])),
            },
            "queued_refresh": queued_refresh,
            "validated_on_add": should_validate,
            "warning": validation_warning or None,
        }
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=error_response(code=50001, message=f"新增来源失败: {str(e)}"))
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.post("/feeds", summary="新增多源订阅(RSS/Atom/RSSHub)")
async def add_source_feed(payload: AddSourceFeedRequest, current_user: dict = Depends(get_current_user)):
    data = _add_source_feed_impl(payload, current_user)
    return success_response(data)


class RsshubPreviewRequest(BaseModel):
    route: str = Field(..., description="RSSHub 路由，例如 /zhihu/hot")
    source_platform: Optional[str] = Field(None, description="可选：平台标识")
    base_url: Optional[str] = Field(None, description="可选：RSSHub 基地址；普通用户仅允许系统配置值")
    limit: int = Field(20, ge=1, le=500, description="预览条数")


class RsshubSubscribeRequest(BaseModel):
    route: str = Field(..., description="RSSHub 路由，例如 /zhihu/hot")
    source_platform: Optional[str] = Field(None, description="可选：平台标识")
    base_url: Optional[str] = Field(None, description="可选：RSSHub 基地址；普通用户仅允许系统配置值")
    name: Optional[str] = Field(None, description="可选：自定义订阅名")
    auto_subscribe: bool = Field(True, description="创建后自动订阅当前用户")


@router.get("/rsshub/status", summary="RSSHub 子服务状态")
async def get_rsshub_status(current_user: dict = Depends(get_current_user)):
    internal = _resolve_rsshub_base(None, current_user)
    public = _rsshub_public_url()
    timeout = _rsshub_timeout()
    started = time.time()
    status_code = 0
    ok = False
    err = ""
    routes_total = 0
    routes_source = ""
    routes_error = ""
    try:
        resp = requests.get(f"{internal}/healthz", timeout=timeout)
        status_code = int(resp.status_code or 0)
        if resp.ok:
            ok = True
        else:
            # 某些 RSSHub 版本不暴露 /healthz，回退到根路径检测
            resp2 = requests.get(f"{internal}/", timeout=timeout)
            status_code = int(resp2.status_code or 0)
            ok = resp2.ok
    except Exception as e:
        err = str(e)

    if ok:
        routes, routes_source, routes_error = _load_rsshub_route_catalog(internal, timeout)
        routes_total = len(routes)

    return success_response(
        {
            "ok": bool(ok),
            "status_code": status_code,
            "latency_ms": int((time.time() - started) * 1000),
            "internal_url": internal,
            "public_url": public,
            "routes_total": int(routes_total),
            "routes_source": routes_source,
            "routes_error": routes_error,
            "error": err,
        }
    )


@router.get("/rsshub/routes", summary="RSSHub 路由目录")
async def list_rsshub_routes(
    kw: str = Query("", description="关键词过滤（标题/路由）"),
    limit: int = Query(120, ge=1, le=500),
    offset: int = Query(0, ge=0),
    base_url: str = Query("", description="可选：RSSHub 基地址（普通用户仅允许系统配置值）"),
    current_user: dict = Depends(get_current_user),
):
    base = _resolve_rsshub_base(base_url or None, current_user)
    timeout = _rsshub_timeout()
    try:
        raw_list, source, source_error = _load_rsshub_route_catalog(base, timeout)
        q = str(kw or "").strip().lower()
        items = []
        for it in raw_list:
            if not isinstance(it, dict):
                continue
            path = str(it.get("path") or it.get("route") or "").strip()
            title = str(it.get("title") or it.get("name") or "").strip()
            maintainers = it.get("maintainers") or []
            if q:
                hit = q in path.lower() or q in title.lower()
                if not hit:
                    continue
            if not path:
                continue
            if not path.startswith("/"):
                path = "/" + path
            items.append(
                {
                    "path": path,
                    "title": title or path,
                    "maintainers": maintainers if isinstance(maintainers, list) else [],
                }
            )
        total = len(items)
        page = items[offset : offset + limit]
        return success_response(
            {
                "list": page,
                "total": total,
                "page": {"limit": limit, "offset": offset, "total": total},
                "source": source,
                "source_error": source_error,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=error_response(code=50022, message=f"读取 RSSHub 路由失败: {str(e)}"))


@router.post("/rsshub/preview", summary="预览 RSSHub 路由内容")
async def preview_rsshub_route(payload: RsshubPreviewRequest, current_user: dict = Depends(get_current_user)):
    try:
        route = _normalize_rsshub_route(payload.route)
        base = _resolve_rsshub_base(payload.base_url, current_user)
        source_url = build_rsshub_feed_url(base, route)
        parsed = fetch_feed(source_url)
        items = list(parsed.get("items") or [])
        preview = []
        for x in items[: payload.limit]:
            preview.append(
                {
                    "id": str(x.get("id") or ""),
                    "title": str(x.get("title") or ""),
                    "link": str(x.get("link") or ""),
                    "description": str(x.get("description") or ""),
                    "publish_time": int(x.get("publish_time") or 0),
                }
            )
        return success_response(
            {
                "route": route,
                "base_url": base,
                "source_url": source_url,
                "feed_title": str(parsed.get("feed_title") or ""),
                "source_platform": _normalize_platform(payload.source_platform, "rsshub")
                if payload.source_platform
                else _guess_platform_from_rsshub_route(route),
                "total_items": int(len(items)),
                "items": preview,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=error_response(code=50023, message=f"RSSHub 路由预览失败: {str(e)}"))


@router.post("/rsshub/subscribe", summary="按 RSSHub 路由一键订阅")
async def subscribe_rsshub_route(payload: RsshubSubscribeRequest, current_user: dict = Depends(get_current_user)):
    try:
        route = _normalize_rsshub_route(payload.route)
        base = _resolve_rsshub_base(payload.base_url, current_user)
        source_platform = payload.source_platform or _guess_platform_from_rsshub_route(route)
        req = AddSourceFeedRequest(
            source_type="rsshub",
            source_platform=source_platform,
            source_url=None,
            rsshub_base_url=base,
            rsshub_route=route,
            name=payload.name,
            auto_subscribe=payload.auto_subscribe,
        )
        data = _add_source_feed_impl(req, current_user)
        data["route"] = route
        data["base_url"] = base
        return success_response(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=error_response(code=50024, message=f"RSSHub 路由订阅失败: {str(e)}"))


@router.get("/rsshub/raw", summary="原样转发 RSSHub 路由内容(XML/JSON)")
async def proxy_rsshub_raw(
    route: str = Query(..., description="RSSHub 路由，支持 /path 或完整 URL"),
    base_url: str = Query("", description="可选：RSSHub 基地址（普通用户仅允许系统配置值）"),
    current_user: dict = Depends(get_current_user),
):
    try:
        base = _resolve_rsshub_base(base_url or None, current_user)
        normalized_route = _normalize_rsshub_route(route)
        source_url = build_rsshub_feed_url(base, normalized_route)
        resp = requests.get(source_url, timeout=_rsshub_timeout())
        ctype = str(resp.headers.get("content-type") or "application/xml")
        return Response(content=resp.text, status_code=resp.status_code, media_type=ctype.split(";")[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=error_response(code=50025, message=f"RSSHub 原始内容代理失败: {str(e)}"))


@router.get("/feeds", summary="获取当前用户可见的多源订阅")
async def list_source_feeds(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    source_platform: str = Query("", description="可选平台过滤"),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    try:
        base_q = session.query(Feed).filter(Feed.source_type.in_(["rss", "rsshub"]))
        if source_platform:
            base_q = base_q.filter(Feed.source_platform == str(source_platform).strip().lower())
        if not _is_admin(current_user):
            user_id = _uid(current_user)
            base_q = (
                base_q.join(UserSubscription, UserSubscription.feed_id == Feed.id)
                .filter(UserSubscription.user_id == user_id)
            )
        total = base_q.count()
        rows = base_q.order_by(Feed.updated_at.desc()).limit(limit).offset(offset).all()
        return success_response(
            {
                "list": [
                    {
                        "id": x.id,
                        "name": x.mp_name,
                        "source_type": x.source_type,
                        "source_platform": x.source_platform or "",
                        "source_url": x.source_url,
                        "updated_at": x.updated_at.isoformat() if x.updated_at else None,
                    }
                    for x in rows
                ],
                "total": total,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=error_response(code=50002, message=f"获取来源列表失败: {str(e)}"))


def _refresh_feed_items(feed: Feed, parsed: dict, now: datetime, now_ts: int) -> tuple[int, int]:
    items = parsed.get("items") or []
    changed = 0

    for item in items:
        item_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or "").strip()
        desc = str(item.get("description") or "").strip()
        publish_time = int(item.get("publish_time") or now_ts)
        if not item_id:
            item_id = sha1(f"{feed.id}:{link or title}:{publish_time}".encode("utf-8")).hexdigest()
        ok = DB.add_article(
            {
                "id": item_id,
                "mp_id": feed.id,
                "title": title or link or item_id,
                "pic_url": "",
                "url": link,
                "description": desc,
                "publish_time": publish_time,
                "status": 1,
                "created_at": now,
                "updated_at": now,
            }
        )
        if ok:
            changed += 1

    feed.sync_time = now_ts
    feed.update_time = now_ts
    if parsed.get("feed_title"):
        feed.mp_name = str(parsed.get("feed_title"))[:255]
    feed.updated_at = now
    return len(items), changed


def _refresh_source_feed_internal(feed_id: str) -> dict:
    session = DB.get_session()
    now_ts = int(time.time())
    now = datetime.now()
    try:
        feed = session.query(Feed).filter(Feed.id == feed_id).first()
        if not feed:
            return {"ok": False, "code": 40401, "feed_id": feed_id, "error": "来源不存在"}
        if str(feed.source_type or "").strip().lower() not in ("rss", "rsshub"):
            return {"ok": False, "code": 40003, "feed_id": feed.id, "error": "仅支持刷新 rss/rsshub 来源"}

        parsed, _ = _fetch_feed_for_source(str(feed.source_type or ""), str(feed.source_url or ""))
        total_items, changed = _refresh_feed_items(feed, parsed, now=now, now_ts=now_ts)
        session.add(feed)
        session.commit()
        prefetch_limit = _source_prefetch_per_feed() if _source_prefetch_enabled() else 0
        prefetch_queued = _enqueue_prefetch_for_feed(session, str(feed.id), limit=prefetch_limit) if prefetch_limit > 0 else 0
        return {
            "ok": True,
            "feed_id": feed.id,
            "name": feed.mp_name or "",
            "total_items": int(total_items),
            "changed": int(changed),
            "prefetch_queued": int(prefetch_queued),
        }
    except Exception as e:
        session.rollback()
        return {"ok": False, "code": 50003, "feed_id": feed_id, "error": str(e)}
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.delete("/feeds/{feed_id}", summary="取消订阅/删除多源订阅")
async def delete_source_feed(
    feed_id: str,
    hard: bool = Query(False, description="true=管理员硬删除；false=仅取消当前用户订阅"),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    try:
        feed = session.query(Feed).filter(Feed.id == feed_id).first()
        if not feed:
            raise HTTPException(status_code=404, detail=error_response(code=40401, message="来源不存在"))
        if str(feed.source_type or "").strip().lower() not in ("rss", "rsshub"):
            raise HTTPException(status_code=400, detail=error_response(code=40003, message="仅支持删除 rss/rsshub 来源"))

        user_id = _uid(current_user)
        is_admin = _is_admin(current_user)

        removed_subscription = 0
        deleted_feed = False

        if hard and not is_admin:
            raise HTTPException(status_code=403, detail=error_response(code=40301, message="仅管理员可执行硬删除"))

        if hard and is_admin:
            removed_subscription = (
                session.query(UserSubscription).filter(UserSubscription.feed_id == feed.id).delete(synchronize_session=False)
            )
            session.delete(feed)
            deleted_feed = True
            session.commit()
            return success_response(
                {
                    "feed_id": feed_id,
                    "removed_subscription": int(removed_subscription or 0),
                    "deleted_feed": deleted_feed,
                }
            )

        removed_subscription = (
            session.query(UserSubscription)
            .filter(UserSubscription.feed_id == feed.id)
            .filter(UserSubscription.user_id == user_id)
            .delete(synchronize_session=False)
        )
        if not removed_subscription:
            raise HTTPException(status_code=403, detail=error_response(code=40301, message="当前用户未订阅该来源"))

        remain = session.query(func.count(UserSubscription.id)).filter(UserSubscription.feed_id == feed.id).scalar() or 0
        if int(remain) <= 0:
            session.delete(feed)
            deleted_feed = True
        session.commit()
        return success_response(
            {
                "feed_id": feed_id,
                "removed_subscription": int(removed_subscription or 0),
                "deleted_feed": deleted_feed,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=error_response(code=50005, message=f"删除来源失败: {str(e)}"))
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.post("/feeds/{feed_id}/refresh", summary="刷新多源订阅文章")
async def refresh_source_feed(
    feed_id: str,
    async_mode: bool = Query(False, description="true=仅入队异步刷新并立即返回，false=同步刷新"),
    min_interval_seconds: int = Query(0, ge=0, le=86400, description="最小刷新间隔秒；命中后直接返回跳过"),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    try:
        feed = session.query(Feed).filter(Feed.id == feed_id).first()
        if not feed:
            raise HTTPException(status_code=404, detail=error_response(code=40401, message="来源不存在"))
        if str(feed.source_type or "").strip() not in ("rss", "rsshub"):
            raise HTTPException(status_code=400, detail=error_response(code=40003, message="仅支持刷新 rss/rsshub 来源"))

        if not _is_admin(current_user):
            user_id = _uid(current_user)
            ok = (
                session.query(func.count(UserSubscription.id))
                .filter(UserSubscription.user_id == user_id)
                .filter(UserSubscription.feed_id == feed.id)
                .scalar()
            )
            if not ok:
                raise HTTPException(status_code=403, detail=error_response(code=40301, message="无权限刷新该来源"))

        now_ts = int(time.time())
        last_sync = int(getattr(feed, "sync_time", 0) or 0)
        if min_interval_seconds > 0 and last_sync > 0:
            age = max(0, now_ts - last_sync)
            if age < int(min_interval_seconds):
                return success_response(
                    {
                        "feed_id": feed_id,
                        "queued": False,
                        "skipped": True,
                        "reason": "recently_synced",
                        "age_seconds": int(age),
                        "min_interval_seconds": int(min_interval_seconds),
                    }
                )

        if async_mode:
            queue = _ensure_source_refresh_queue()
            queue.add_task(_refresh_source_feed_internal, feed_id)
            return success_response(
                {
                    "feed_id": feed_id,
                    "queued": True,
                    "workers": int(queue.workers),
                    "skipped": False,
                    "min_interval_seconds": int(min_interval_seconds),
                }
            )

        result = _refresh_source_feed_internal(feed_id)
        if not result.get("ok"):
            code = int(result.get("code") or 50003)
            status_code = 500
            if code == 40401:
                status_code = 404
            elif code in (40001, 40003):
                status_code = 400
            elif code == 40301:
                status_code = 403
            raise HTTPException(status_code=status_code, detail=error_response(code=code, message=str(result.get("error") or "刷新失败")))
        return success_response(
            {
                "feed_id": result.get("feed_id"),
                "total_items": int(result.get("total_items") or 0),
                "changed": int(result.get("changed") or 0),
                "prefetch_queued": int(result.get("prefetch_queued") or 0),
                "queued": False,
                "skipped": False,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=error_response(code=50003, message=f"刷新来源失败: {str(e)}"))
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.get("/platform_presets", summary="获取多平台预置模板")
async def list_platform_presets():
    return success_response({"list": _list_platform_presets()})


@router.post("/refresh_all", summary="刷新当前用户全部多源订阅")
async def refresh_all_source_feeds(
    limit: int = Query(300, ge=1, le=1000),
    async_mode: bool = Query(True, description="true=异步入队(推荐)，false=同步并发执行"),
    workers: int = Query(0, ge=0, le=64, description="同步模式并发数；0表示自动"),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    try:
        q = session.query(Feed).filter(Feed.source_type.in_(["rss", "rsshub"]))
        if not _is_admin(current_user):
            user_id = _uid(current_user)
            q = q.join(UserSubscription, UserSubscription.feed_id == Feed.id).filter(UserSubscription.user_id == user_id)
        feeds = q.order_by(Feed.updated_at.asc()).limit(limit).all()
        feed_ids = [str(f.id) for f in feeds if str(f.id or "").strip()]
        total_feeds = len(feed_ids)

        if async_mode:
            queue = _ensure_source_refresh_queue()
            queued = 0
            for feed_id in feed_ids:
                try:
                    queue.add_task(_refresh_source_feed_internal, feed_id)
                    queued += 1
                except Exception:
                    continue
            return success_response(
                {
                    "mode": "async",
                    "total_feeds": total_feeds,
                    "queued": queued,
                    "workers": queue.workers,
                    "refreshed": 0,
                    "failed": 0,
                    "total_items": 0,
                    "changed_items": 0,
                    "failures": [],
                }
            )

        refreshed = 0
        total_items = 0
        changed_items = 0
        prefetch_queued = 0
        failures: list[dict] = []
        run_workers = max(1, min(64, int(workers or _source_refresh_workers())))

        with ThreadPoolExecutor(max_workers=run_workers) as ex:
            futures = [ex.submit(_refresh_source_feed_internal, feed_id) for feed_id in feed_ids]
            for fut in as_completed(futures):
                result = fut.result()
                if result.get("ok"):
                    refreshed += 1
                    total_items += int(result.get("total_items") or 0)
                    changed_items += int(result.get("changed") or 0)
                    prefetch_queued += int(result.get("prefetch_queued") or 0)
                else:
                    failures.append(
                        {
                            "feed_id": result.get("feed_id") or "",
                            "name": result.get("name") or "",
                            "error": result.get("error") or "unknown error",
                        }
                    )

        return success_response(
            {
                "mode": "sync",
                "total_feeds": total_feeds,
                "refreshed": refreshed,
                "failed": len(failures),
                "total_items": total_items,
                "changed_items": changed_items,
                "prefetch_queued": prefetch_queued,
                "failures": failures[:20],
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=error_response(code=50004, message=f"刷新全部来源失败: {str(e)}"))
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.post("/maintenance/audit", summary="创建订阅源正文可读性巡检任务（管理员）")
async def create_source_audit_task(payload: SourceAuditTaskRequest, current_user: dict = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail=error_response(code=40301, message="仅管理员可执行订阅源巡检"))

    task_id = f"src_audit_{uuid.uuid4().hex[:16]}"
    task = {
        "id": task_id,
        "type": "source_audit",
        "status": "pending",
        "created_by": _uid(current_user),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "options": {
            "platforms": [str(x).strip().lower() for x in (payload.platforms or []) if str(x).strip()],
            "limit": int(payload.limit),
            "sample_per_feed": int(payload.sample_per_feed),
            "min_text_length": int(payload.min_text_length),
            "remove_failed_sources": bool(payload.remove_failed_sources),
            "failure_success_rate": float(payload.failure_success_rate),
            "include_platforms_only": bool(payload.include_platforms_only),
        },
        "progress": {"total": 0, "done": 0, "ok": 0, "failed": 0, "removed": 0},
        "results": [],
        "error": "",
    }
    _upsert_maintenance_task(task)

    try:
        queue = _ensure_source_maintenance_queue()
        queue.add_task(_run_source_audit_task, task_id)
    except Exception as e:
        _update_maintenance_task(task_id, {"status": "failed", "error": str(e)})
        raise HTTPException(status_code=500, detail=error_response(code=50006, message=f"巡检任务入队失败: {e}"))

    return success_response({"task_id": task_id, "status": "pending"})


@router.post("/maintenance/content_backfill", summary="创建来源文章正文回填任务（管理员）")
async def create_source_content_backfill_task(
    payload: SourceContentBackfillTaskRequest,
    current_user: dict = Depends(get_current_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail=error_response(code=40301, message="仅管理员可执行正文回填"))

    active = _find_active_maintenance_task("source_content_backfill")
    if active:
        return success_response(
            {
                "task_id": str(active.get("id") or ""),
                "status": str(active.get("status") or "running"),
                "deduped": True,
                "message": "已有正文回填任务正在执行，已复用现有任务",
            }
        )

    options = {
        "platforms": [str(x).strip().lower() for x in (payload.platforms or []) if str(x).strip()],
        "feed_ids": [str(x).strip() for x in (payload.feed_ids or []) if str(x).strip()],
        "days": int(payload.days),
        "limit": int(payload.limit),
        "workers": int(payload.workers),
        "missing_only": bool(payload.missing_only),
        "force": bool(payload.force),
        "max_failures_per_feed": int(payload.max_failures_per_feed),
        "blocked_cooldown_hours": int(payload.blocked_cooldown_hours),
        "skip_cooldown_feeds": bool(payload.skip_cooldown_feeds),
        "enqueue_insights": bool(payload.enqueue_insights),
    }
    task = _build_source_content_backfill_task(options=options, created_by=_uid(current_user))
    _upsert_maintenance_task(task)
    try:
        queue = _ensure_source_maintenance_queue()
        queue.add_task(_run_source_content_backfill_task, str(task.get("id") or ""))
    except Exception as e:
        _update_maintenance_task(str(task.get("id") or ""), {"status": "failed", "error": str(e)})
        raise HTTPException(status_code=500, detail=error_response(code=50007, message=f"正文回填任务入队失败: {e}"))
    return success_response({"task_id": str(task.get("id") or ""), "status": "pending", "deduped": False})


@router.get("/maintenance/tasks", summary="查看订阅源巡检任务列表（管理员）")
async def list_source_maintenance_tasks(current_user: dict = Depends(get_current_user), limit: int = Query(20, ge=1, le=200)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail=error_response(code=40301, message="仅管理员可查看巡检任务"))
    tasks = _load_maintenance_tasks()
    return success_response({"list": tasks[:limit], "total": len(tasks)})


@router.get("/maintenance/tasks/{task_id}", summary="查看订阅源巡检任务详情（管理员）")
async def get_source_maintenance_task(task_id: str, current_user: dict = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail=error_response(code=40301, message="仅管理员可查看巡检任务"))
    task = _get_maintenance_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=error_response(code=40401, message="任务不存在"))
    return success_response(task)
