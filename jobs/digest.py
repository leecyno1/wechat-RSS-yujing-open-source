from __future__ import annotations

from core.config import cfg
from core.digest import generate_digest_outbox
from core.print import print_error, print_success, print_warning
from core.queue import TaskQueueManager
from core.task import TaskScheduler


_DIGEST_SCHEDULER = TaskScheduler()
_DIGEST_QUEUE: TaskQueueManager | None = None


def _ensure_queue() -> TaskQueueManager:
    global _DIGEST_QUEUE
    if _DIGEST_QUEUE is None:
        _DIGEST_QUEUE = TaskQueueManager(tag="合集推送")
        _DIGEST_QUEUE.run_task_background()
    return _DIGEST_QUEUE


def _run_generate(slot: str) -> None:
    try:
        channel = str(cfg.get("digest.outbox_channel", "wechat") or "wechat")
        only_bound = bool(cfg.get("digest.only_bound", True))
        res = generate_digest_outbox(slot=slot, channel=channel, only_bound=only_bound)
        print_success(f"合集推送 outbox 已生成: {res}")
    except Exception as e:
        print_error(f"合集推送 outbox 生成失败: {e}")


def _enqueue(slot: str) -> None:
    q = _ensure_queue()
    q.add_task(_run_generate, slot)


def start_digest_outbox() -> None:
    """Generate robot outbox messages on schedule."""
    enabled = bool(cfg.get("digest.enable", False))
    if not enabled:
        print_warning("合集推送 outbox 未启用（设置 DIGEST_ENABLE=True）")
        return

    try:
        _DIGEST_SCHEDULER.clear_all_jobs()
    except Exception:
        pass

    cron_morning = str(cfg.get("digest.cron_morning", "10 6 * * *") or "10 6 * * *")
    cron_afternoon = str(cfg.get("digest.cron_afternoon", "10 15 * * *") or "10 15 * * *")
    cron_evening = str(cfg.get("digest.cron_evening", "10 21 * * *") or "10 21 * * *")

    _DIGEST_SCHEDULER.add_cron_job(lambda: _enqueue("morning"), cron_expr=cron_morning, job_id="digest-outbox-morning", tag="合集推送(早)")
    _DIGEST_SCHEDULER.add_cron_job(lambda: _enqueue("afternoon"), cron_expr=cron_afternoon, job_id="digest-outbox-afternoon", tag="合集推送(午)")
    _DIGEST_SCHEDULER.add_cron_job(lambda: _enqueue("evening"), cron_expr=cron_evening, job_id="digest-outbox-evening", tag="合集推送(晚)")

    _DIGEST_SCHEDULER.start()
    print_success(f"合集推送 outbox 已启用：{cron_morning} / {cron_afternoon} / {cron_evening}")

