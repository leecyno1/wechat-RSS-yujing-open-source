from __future__ import annotations

from core.config import cfg
from core.print import print_error, print_info, print_success, print_warning
from core.task import TaskScheduler


_SCHEDULER = TaskScheduler()


def _as_bool(v, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    if not s:
        return default
    return s in {"1", "true", "yes", "on"}


def _split_csv(v: str | None) -> list[str]:
    raw = str(v or "").strip()
    if not raw:
        return []
    return [str(x).strip().lower() for x in raw.split(",") if str(x).strip()]


def _enqueue_content_backfill() -> None:
    try:
        from apis.sources import enqueue_source_content_backfill_system_task
    except Exception as e:
        print_error(f"正文回填任务启动失败：无法加载 sources API: {e}")
        return

    options = {
        "platforms": _split_csv(cfg.get("sources.content_backfill_platforms", "")),
        "feed_ids": _split_csv(cfg.get("sources.content_backfill_feed_ids", "")),
        "days": max(0, min(30, int(cfg.get("sources.content_backfill_days", 3) or 3))),
        "limit": max(1, min(5000, int(cfg.get("sources.content_backfill_limit_per_run", 800) or 800))),
        "workers": max(1, min(32, int(cfg.get("sources.content_backfill_workers", 8) or 8))),
        "missing_only": _as_bool(cfg.get("sources.content_backfill_missing_only", True), True),
        "force": _as_bool(cfg.get("sources.content_backfill_force", False), False),
        "max_failures_per_feed": max(1, min(20, int(cfg.get("sources.content_backfill_max_failures_per_feed", 4) or 4))),
        "blocked_cooldown_hours": max(1, min(72, int(cfg.get("sources.content_backfill_blocked_cooldown_hours", 12) or 12))),
        "skip_cooldown_feeds": _as_bool(cfg.get("sources.content_backfill_skip_cooldown_feeds", True), True),
        "enqueue_insights": _as_bool(cfg.get("sources.content_backfill_enqueue_insights", True), True),
    }
    ret = enqueue_source_content_backfill_system_task(options=options, allow_parallel=False)
    if bool(ret.get("deduped")):
        print_info(f"正文回填跳过：已有任务运行中 task_id={ret.get('task_id')}")
    else:
        print_success(f"正文回填任务已入队 task_id={ret.get('task_id')}")


def start_source_content_backfill() -> None:
    enabled = _as_bool(cfg.get("sources.content_backfill_enable", True), True)
    if not enabled:
        print_warning("正文回填定时任务未启用（设置 SOURCES_CONTENT_BACKFILL_ENABLE=True）")
        return

    try:
        _SCHEDULER.clear_all_jobs()
    except Exception:
        pass

    run_on_start = _as_bool(cfg.get("sources.content_backfill_run_on_start", True), True)
    cron_expr = str(cfg.get("sources.content_backfill_cron", "*/20 * * * *") or "*/20 * * * *").strip()

    _SCHEDULER.add_cron_job(
        _enqueue_content_backfill,
        cron_expr=cron_expr,
        job_id="sources-content-backfill",
        tag="正文回填",
    )
    _SCHEDULER.start()
    print_success(f"正文回填定时任务已启用：{cron_expr}")

    if run_on_start:
        _enqueue_content_backfill()
