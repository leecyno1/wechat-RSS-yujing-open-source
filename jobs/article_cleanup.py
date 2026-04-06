from __future__ import annotations

from core.article_cleanup import run_article_history_cleanup_from_config
from core.config import cfg
from core.print import print_error, print_info, print_success, print_warning
from core.queue import TaskQueueManager
from core.task import TaskScheduler


_SCHEDULER = TaskScheduler()
_QUEUE: TaskQueueManager | None = None


def _cleanup_workers() -> int:
    try:
        v = int(cfg.get("article.cleanup.workers", 1) or 1)
    except Exception:
        v = 1
    return max(1, min(8, v))


def _ensure_queue() -> TaskQueueManager:
    global _QUEUE
    if _QUEUE is not None:
        return _QUEUE
    _QUEUE = TaskQueueManager(tag="历史文章清理", workers=_cleanup_workers())
    _QUEUE.run_task_background()
    return _QUEUE


def _run_cleanup_task() -> None:
    try:
        ret = run_article_history_cleanup_from_config()
        if ret.get("enabled", True):
            print_success(
                "历史文章清理任务完成: candidates=%s selected=%s deleted=%s"
                % (
                    ret.get("candidate_total", 0),
                    ret.get("selected_total", 0),
                    (ret.get("deleted") or {}).get("articles", 0),
                )
            )
    except Exception as e:
        print_error(f"历史文章清理任务失败: {e}")


def _enqueue_cleanup() -> None:
    q = _ensure_queue()
    q.add_task(_run_cleanup_task)


def start_article_cleanup() -> None:
    enabled = bool(cfg.get("article.cleanup.enable", True))
    if not enabled:
        print_warning("历史文章清理定时任务未启用（设置 ARTICLE_CLEANUP_ENABLE=False）")
        return

    cron_expr = str(cfg.get("article.cleanup.cron", "30 4 * * *") or "30 4 * * *")
    run_on_start = bool(cfg.get("article.cleanup.run_on_start", False))

    try:
        _SCHEDULER.clear_all_jobs()
    except Exception:
        pass

    _SCHEDULER.add_cron_job(
        _enqueue_cleanup,
        cron_expr=cron_expr,
        job_id="article-history-cleanup",
        tag="历史文章清理",
    )
    _SCHEDULER.start()
    print_success(f"历史文章清理定时任务已启用：{cron_expr}")

    if run_on_start:
        try:
            print_info("历史文章清理启动后立即执行一次")
            _enqueue_cleanup()
        except Exception as e:
            print_error(f"历史文章清理启动执行失败: {e}")
