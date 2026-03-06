from __future__ import annotations

import os
import time
from datetime import datetime
from hashlib import sha1
from typing import Any

from core.config import cfg
from core.db import DB
from core.insights import InsightsService
from core.print import print_error, print_info, print_success, print_warning
from core.queue import TaskQueueManager
from core.task import TaskScheduler
from core.wx import WxGather
from core.models.article import Article
from sqlalchemy import func
from core.source.adapters import fetch_feed


_AUTO_UPDATE_SCHEDULER = TaskScheduler()
_AUTO_UPDATE_QUEUE: TaskQueueManager | None = None
_AUTO_UPDATE_SOURCE_QUEUES: dict[str, TaskQueueManager] = {}


def _normalize_article_id(article: dict[str, Any]) -> str | None:
    raw_id = str(article.get("id") or "").strip()
    mp_id = str(article.get("mp_id") or "").strip()
    if not raw_id or not mp_id:
        return None
    return f"{mp_id}-{raw_id}".replace("MP_WXS_", "")


def _update_one_feed(feed) -> None:
    faker_id = str(getattr(feed, "faker_id", "") or "").strip()
    if not faker_id:
        return

    max_page = int(cfg.get("auto_update.max_page", cfg.get("max_page", 1) or 1) or 1)
    max_page = max(1, min(50, max_page))
    # In auto updates we want speed; throttle is handled via WeChat backend limits
    # and queue concurrency rather than per-item sleeps.
    interval = 0

    changed_article_ids: list[str] = []

    def _cb(article: dict[str, Any], check_exist: bool = False) -> bool:
        ok = DB.add_article(article, check_exist=check_exist)
        if ok:
            aid = _normalize_article_id(article)
            if aid:
                changed_article_ids.append(aid)
        return ok

    wx = WxGather().Model()
    wx.fast_mode = True

    # Incremental refresh based on last seen publish_time (with grace window).
    since_ts = None
    try:
        grace = int(cfg.get("gather.incremental_grace_seconds", 3600) or 3600)
        s = DB.get_session()
        last_ts = (
            s.query(func.max(Article.publish_time))
            .filter(Article.mp_id == str(getattr(feed, "id", "") or ""))
            .scalar()
            or 0
        )
        last_ts = int(last_ts or 0)
        if last_ts > 0:
            since_ts = max(0, last_ts - max(0, grace))
    except Exception:
        since_ts = None

    wx.get_Articles(
        faker_id,
        CallBack=_cb,
        Mps_id=str(getattr(feed, "id", "") or ""),
        Mps_title=str(getattr(feed, "mp_name", "") or ""),
        MaxPage=max_page,
        interval=interval,
        since_ts=since_ts,
    )

    if not changed_article_ids:
        return

    # After each update, ensure insights are (re)generated for changed articles.
    service = InsightsService()
    try:
        from core.queue import InsightsQueue
    except Exception:
        InsightsQueue = None

    for aid in changed_article_ids:
        try:
            if InsightsQueue:
                InsightsQueue.add_task(service.ensure_cached, aid)
            else:
                service.ensure_cached(aid)
        except Exception:
            continue


def _source_platform(feed) -> str:
    raw = str(getattr(feed, "source_platform", "") or "").strip().lower()
    if raw:
        return raw
    st = str(getattr(feed, "source_type", "") or "").strip().lower()
    if st in ("rss", "rsshub"):
        return st
    return "wechat"


def _parse_workers_by_platform(raw: str | None) -> dict[str, int]:
    """
    Parse config string such as:
    zhihu:4,xueqiu:2,wsj:1,bbc:1
    """
    out: dict[str, int] = {}
    text = str(raw or "").strip()
    if not text:
        return out
    for part in text.split(","):
        item = str(part or "").strip()
        if not item or ":" not in item:
            continue
        key, val = item.split(":", 1)
        k = str(key or "").strip().lower()
        try:
            workers = int(str(val or "").strip())
        except Exception:
            continue
        if not k:
            continue
        out[k] = max(1, min(32, workers))
    return out


def _source_workers(platform: str) -> int:
    try:
        default_workers = int(cfg.get("auto_update.source_workers", 4) or 4)
    except Exception:
        default_workers = 4
    mapping = _parse_workers_by_platform(cfg.get("auto_update.source_workers_by_platform", ""))
    return max(1, min(32, int(mapping.get(platform, default_workers))))


def _ensure_source_queue(platform: str) -> TaskQueueManager:
    q = _AUTO_UPDATE_SOURCE_QUEUES.get(platform)
    if q is not None:
        return q
    workers = _source_workers(platform)
    q = TaskQueueManager(tag=f"全量更新[{platform}]", workers=workers)
    q.run_task_background()
    _AUTO_UPDATE_SOURCE_QUEUES[platform] = q
    return q


def _update_one_source_feed(feed_id: str) -> None:
    """
    Refresh one RSS/RSSHub source feed and enqueue insights for changed articles.
    """
    session = DB.get_session()
    try:
        from core.models.feed import Feed

        feed = session.query(Feed).filter(Feed.id == feed_id).first()
        if not feed:
            return
        source_type = str(getattr(feed, "source_type", "") or "").strip().lower()
        if source_type not in ("rss", "rsshub"):
            return
        source_url = str(getattr(feed, "source_url", "") or "").strip()
        if not source_url:
            return

        now_ts = int(time.time())
        changed_article_ids: list[str] = []
        parsed = fetch_feed(source_url)
        items = parsed.get("items") or []
        now = datetime.now()

        for item in items:
            item_id = str(item.get("id") or "").strip()
            title = str(item.get("title") or "").strip()
            link = str(item.get("link") or "").strip()
            desc = str(item.get("description") or "").strip()
            publish_time = int(item.get("publish_time") or now_ts)
            if not item_id:
                item_id = sha1(f"{feed.id}:{link or title}:{publish_time}".encode("utf-8")).hexdigest()
            payload = {
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
            if DB.add_article(payload):
                aid = f"{feed.id}-{item_id}".replace("MP_WXS_", "")
                changed_article_ids.append(aid)

        feed.sync_time = now_ts
        feed.update_time = now_ts
        if parsed.get("feed_title"):
            feed.mp_name = str(parsed.get("feed_title"))[:255]
        feed.updated_at = now
        session.add(feed)
        session.commit()

        if not changed_article_ids:
            return
        service = InsightsService()
        try:
            from core.queue import InsightsQueue
        except Exception:
            InsightsQueue = None
        for aid in changed_article_ids:
            try:
                if InsightsQueue:
                    InsightsQueue.add_task(service.ensure_cached, aid)
                else:
                    service.ensure_cached(aid)
            except Exception:
                continue
    except Exception as e:
        try:
            session.rollback()
        except Exception:
            pass
        print_error(f"多平台来源更新失败({feed_id}): {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass


def _run_full_update() -> None:
    """Enqueue a full refresh for all subscribed feeds."""
    feeds = []
    try:
        feeds = DB.get_all_mps() or []
    except Exception as e:
        print_error(f"全量更新失败：无法获取公众号列表: {e}")
        return

    if not feeds:
        print_warning("全量更新跳过：当前没有任何订阅公众号")
        return

    wechat_feeds = []
    source_feed_ids_by_platform: dict[str, list[str]] = {}
    for feed in feeds:
        source_type = str(getattr(feed, "source_type", "") or "").strip().lower()
        faker_id = str(getattr(feed, "faker_id", "") or "").strip()
        if source_type in ("rss", "rsshub"):
            source_url = str(getattr(feed, "source_url", "") or "").strip()
            if not source_url:
                continue
            p = _source_platform(feed)
            source_feed_ids_by_platform.setdefault(p, []).append(str(getattr(feed, "id", "") or ""))
            continue
        if faker_id:
            wechat_feeds.append(feed)

    global _AUTO_UPDATE_QUEUE
    if wechat_feeds:
        if _AUTO_UPDATE_QUEUE is None:
            try:
                workers = int(os.getenv("AUTO_UPDATE_WORKERS", "6") or "6")
            except Exception:
                workers = 6
            _AUTO_UPDATE_QUEUE = TaskQueueManager(tag="全量更新", workers=max(1, workers))
            _AUTO_UPDATE_QUEUE.run_task_background()
        print_info(
            f"全量更新开始(公众号)：共 {len(wechat_feeds)} 个，MaxPage={cfg.get('auto_update.max_page', cfg.get('max_page', 1))}"
        )
        for feed in wechat_feeds:
            try:
                _AUTO_UPDATE_QUEUE.add_task(_update_one_feed, feed)
            except Exception as e:
                print_error(f"全量更新入队失败：{getattr(feed, 'mp_name', '')}: {e}")
                continue

    source_total = 0
    for platform, feed_ids in source_feed_ids_by_platform.items():
        if not feed_ids:
            continue
        q = _ensure_source_queue(platform)
        source_total += len(feed_ids)
        print_info(f"全量更新开始({platform})：共 {len(feed_ids)} 个来源，workers={q.workers}")
        for feed_id in feed_ids:
            try:
                q.add_task(_update_one_source_feed, feed_id)
            except Exception as e:
                print_error(f"{platform} 入队失败：{feed_id}: {e}")

    print_success(
        f"全量更新任务已入队：公众号 {len(wechat_feeds)} 个，多平台来源 {source_total} 个"
    )


def start_auto_update() -> None:
    """Schedule auto updates at 06:00 / 15:00 / 21:00 every day."""
    enabled = bool(cfg.get("auto_update.enable", False))
    if not enabled:
        print_warning("自动全量更新未启用（设置 AUTO_UPDATE_ENABLE=True）")
        return

    # Avoid duplicate jobs if start_all_task() is called again.
    try:
        _AUTO_UPDATE_SCHEDULER.clear_all_jobs()
    except Exception:
        pass

    cron_morning = str(cfg.get("auto_update.cron_morning", "0 6 * * *") or "0 6 * * *")
    cron_afternoon = str(cfg.get("auto_update.cron_afternoon", "0 15 * * *") or "0 15 * * *")
    cron_evening = str(cfg.get("auto_update.cron_evening", "0 21 * * *") or "0 21 * * *")

    _AUTO_UPDATE_SCHEDULER.add_cron_job(_run_full_update, cron_expr=cron_morning, job_id="auto-update-morning", tag="自动全量更新(早)")
    _AUTO_UPDATE_SCHEDULER.add_cron_job(_run_full_update, cron_expr=cron_afternoon, job_id="auto-update-afternoon", tag="自动全量更新(午)")
    _AUTO_UPDATE_SCHEDULER.add_cron_job(_run_full_update, cron_expr=cron_evening, job_id="auto-update-evening", tag="自动全量更新(晚)")

    _AUTO_UPDATE_SCHEDULER.start()
    print_success(f"自动全量更新已启用：{cron_morning} / {cron_afternoon} / {cron_evening}")
