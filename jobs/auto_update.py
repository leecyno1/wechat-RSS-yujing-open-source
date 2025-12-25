from __future__ import annotations

from typing import Any

from core.config import cfg
from core.db import DB
from core.insights import InsightsService
from core.print import print_error, print_info, print_success, print_warning
from core.queue import TaskQueue, TaskQueueManager
from core.task import TaskScheduler
from core.wx import WxGather


_AUTO_UPDATE_SCHEDULER = TaskScheduler()
_AUTO_UPDATE_QUEUE: TaskQueueManager | None = None


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
    interval = int(cfg.get("interval", 10) or 10)
    interval = max(1, min(60, interval))

    changed_article_ids: list[str] = []

    def _cb(article: dict[str, Any], check_exist: bool = False) -> bool:
        ok = DB.add_article(article, check_exist=check_exist)
        if ok:
            aid = _normalize_article_id(article)
            if aid:
                changed_article_ids.append(aid)
        return ok

    wx = WxGather().Model()
    wx.get_Articles(
        faker_id,
        CallBack=_cb,
        Mps_id=str(getattr(feed, "id", "") or ""),
        Mps_title=str(getattr(feed, "mp_name", "") or ""),
        MaxPage=max_page,
        interval=interval,
    )

    if not changed_article_ids:
        return

    # After each update, ensure insights are (re)generated for changed articles.
    service = InsightsService()
    for aid in changed_article_ids:
        try:
            TaskQueue.add_task(service.ensure_cached, aid)
        except Exception:
            # Fallback to sync best-effort in the worker thread.
            try:
                service.ensure_cached(aid)
            except Exception:
                continue


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

    global _AUTO_UPDATE_QUEUE
    if _AUTO_UPDATE_QUEUE is None:
        _AUTO_UPDATE_QUEUE = TaskQueueManager(tag="全量更新")
        _AUTO_UPDATE_QUEUE.run_task_background()

    print_info(f"全量更新开始：共 {len(feeds)} 个公众号，MaxPage={cfg.get('auto_update.max_page', cfg.get('max_page', 1))}")
    for feed in feeds:
        try:
            _AUTO_UPDATE_QUEUE.add_task(_update_one_feed, feed)
        except Exception as e:
            print_error(f"全量更新入队失败：{getattr(feed, 'mp_name', '')}: {e}")
            continue
    print_success("全量更新任务已全部入队")


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

