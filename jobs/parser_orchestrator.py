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


def _enqueue_parser_task() -> None:
    try:
        from apis.parser import enqueue_parser_task_system
    except Exception as e:
        print_error(f"解析编排任务启动失败：无法加载 parser API: {e}")
        return

    options = {
        "days": max(0, min(30, int(cfg.get("parser.days", 3) or 3))),
        "limit": max(1, min(5000, int(cfg.get("parser.limit_per_run", 300) or 300))),
        "workers": max(1, min(32, int(cfg.get("parser.workers", 6) or 6))),
        "strategy": str(cfg.get("parser.strategy", "balanced") or "balanced").strip().lower(),
        "source_types": _split_csv(cfg.get("parser.source_types", "wechat,rss,rsshub")),
        "max_per_feed": max(0, min(100, int(cfg.get("parser.max_per_feed", 0) or 0))),
        "round_robin": _as_bool(cfg.get("parser.round_robin", True), True),
        "force_content": _as_bool(cfg.get("parser.force_content", False), False),
        "force_insights": _as_bool(cfg.get("parser.force_insights", False), False),
    }
    ret = enqueue_parser_task_system(options=options, allow_parallel=False)
    if bool(ret.get("deduped")):
        print_info(f"解析编排跳过：已有任务运行中 task_id={ret.get('task_id')}")
    else:
        print_success(f"解析编排任务已入队 task_id={ret.get('task_id')}")


def start_parser_orchestrator() -> None:
    enabled = _as_bool(cfg.get("parser.enable", True), True)
    if not enabled:
        print_warning("解析编排定时任务未启用（设置 PARSER_ENABLE=True）")
        return

    try:
        _SCHEDULER.clear_all_jobs()
    except Exception:
        pass

    run_on_start = _as_bool(cfg.get("parser.run_on_start", True), True)
    cron_expr = str(cfg.get("parser.cron", "*/10 * * * *") or "*/10 * * * *").strip()

    _SCHEDULER.add_cron_job(
        _enqueue_parser_task,
        cron_expr=cron_expr,
        job_id="parser-orchestrator",
        tag="解析编排",
    )
    _SCHEDULER.start()
    print_success(f"解析编排定时任务已启用：{cron_expr}")

    if run_on_start:
        _enqueue_parser_task()
