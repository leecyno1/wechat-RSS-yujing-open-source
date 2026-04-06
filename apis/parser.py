from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_

from apis.base import error_response, success_response
from core.auth import get_current_user
from core.config import cfg
from core.db import DB
from core.insights import InsightsService
from core.models.article import Article
from core.models.article_insight import ArticleInsight
from core.models.base import DATA_STATUS
from core.models.feed import Feed
from core.queue import TaskQueueManager

router = APIRouter(prefix="/parser", tags=["解析编排"])

_PARSER_QUEUE: TaskQueueManager | None = None
_PARSER_LOCK = threading.Lock()


def _is_admin(current_user: dict) -> bool:
    try:
        return str(current_user.get("role") or "") == "admin" or str(current_user.get("username") or "") == "admin"
    except Exception:
        return False


def _uid(current_user: dict) -> str:
    try:
        return str(current_user.get("original_user").id)
    except Exception:
        return str(current_user.get("username") or "")


def _parser_tasks_file() -> str:
    return str(cfg.get("parser.tasks_file", "data/parser_tasks.json") or "data/parser_tasks.json")


def _load_tasks() -> list[dict]:
    p = Path(_parser_tasks_file())
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        tasks = raw.get("tasks") if isinstance(raw, dict) else []
        if isinstance(tasks, list):
            return [x for x in tasks if isinstance(x, dict)]
    except Exception:
        pass
    return []


def _save_tasks(tasks: list[dict]) -> None:
    p = Path(_parser_tasks_file())
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tasks": tasks[:200],
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def _upsert_task(task: dict) -> dict:
    with _PARSER_LOCK:
        tasks = _load_tasks()
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
        _save_tasks(tasks)
        for it in tasks:
            if str(it.get("id") or "") == tid:
                return it
        return task


def _get_task(task_id: str) -> dict | None:
    tid = str(task_id or "").strip()
    if not tid:
        return None
    with _PARSER_LOCK:
        for it in _load_tasks():
            if str(it.get("id") or "") == tid:
                return it
    return None


def _update_task(task_id: str, patch: dict) -> dict | None:
    task = _get_task(task_id)
    if not task:
        return None
    task.update(patch or {})
    return _upsert_task(task)


def _find_active_task(task_type: str = "parser_orchestrator") -> dict | None:
    stale_minutes = max(5, min(24 * 60, int(cfg.get("parser.active_task_stale_minutes", 30) or 30)))
    stale_seconds = stale_minutes * 60

    def _parse_ts(v: Any) -> int:
        raw = str(v or "").strip()
        if not raw:
            return 0
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return int(datetime.strptime(raw, fmt).timestamp())
            except Exception:
                continue
        return 0

    now_ts = int(time.time())
    with _PARSER_LOCK:
        tasks = _load_tasks()
        changed = False
        for it in tasks:
            if str(it.get("type") or "") != str(task_type or ""):
                continue
            status = str(it.get("status") or "").lower().strip()
            if status in {"pending", "running"}:
                heartbeat = (
                    _parse_ts(it.get("updated_at"))
                    or _parse_ts(it.get("started_at"))
                    or _parse_ts(it.get("created_at"))
                )
                if heartbeat and (now_ts - heartbeat) > stale_seconds:
                    it["status"] = "failed"
                    it["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    it["error"] = (
                        f"task stale for {int((now_ts - heartbeat) / 60)} minutes; "
                        "auto-marked failed to unblock new runs"
                    )
                    changed = True
                    continue
                return it
        if changed:
            _save_tasks(tasks)
    return None


def _parser_workers() -> int:
    try:
        workers = int(cfg.get("parser.queue_workers", 2) or 2)
    except Exception:
        workers = 2
    return max(1, min(8, workers))


def _ensure_parser_queue() -> TaskQueueManager:
    global _PARSER_QUEUE
    if _PARSER_QUEUE is not None:
        return _PARSER_QUEUE
    q = TaskQueueManager(tag="解析编排", workers=_parser_workers())
    q.run_task_background()
    _PARSER_QUEUE = q
    return q


def _text_has_value(v: Any) -> bool:
    s = str(v or "").strip()
    return bool(s and s != "DELETED")


def _content_usable(raw: Any, *, min_chars: int) -> bool:
    s = str(raw or "").strip()
    if not s or s == "DELETED":
        return False
    # Strip HTML tags to avoid counting markup-only payloads as real正文.
    text = re.sub(r"<[^>]+>", " ", s)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < max(20, int(min_chars or 120)):
        return False
    return True


def _score_item(it: dict, strategy: str) -> tuple:
    publish_time = int(it.get("publish_time") or 0)
    read_count = int(it.get("read_count") or 0)
    like_count = int(it.get("like_count") or 0)
    share_count = int(it.get("share_count") or 0)
    recommend_count = int(it.get("recommend_count") or 0)
    has_content = bool(it.get("has_content"))
    has_summary = bool(it.get("has_summary"))
    has_key_points = bool(it.get("has_key_points"))

    engagement = read_count + like_count * 3 + share_count * 4 + recommend_count * 3
    missing_content = 0 if has_content else 1
    missing_insight = 0 if (has_summary and has_key_points) else 1

    st = str(strategy or "balanced").strip().lower()
    if st == "newest":
        return (publish_time, missing_content, missing_insight, engagement)
    if st == "hot":
        return (engagement, missing_content, missing_insight, publish_time)
    # balanced
    return (missing_content, missing_insight, publish_time, engagement)


def _build_candidates(
    *,
    days: int,
    limit: int,
    strategy: str,
    source_types: list[str],
    max_per_feed: int,
    round_robin: bool,
) -> list[dict]:
    session = DB.get_session()
    try:
        q = (
            session.query(
                Article.id,
                Article.mp_id,
                Article.publish_time,
                Article.content,
                Article.description,
                Article.read_count,
                Article.like_count,
                Article.share_count,
                Article.recommend_count,
                Feed.source_type,
                ArticleInsight.summary,
                ArticleInsight.key_points_json,
            )
            .join(Feed, Feed.id == Article.mp_id)
            .outerjoin(ArticleInsight, ArticleInsight.article_id == Article.id)
            .filter(Article.status != int(DATA_STATUS.DELETED))
        )

        st = [str(x or "").strip().lower() for x in (source_types or []) if str(x or "").strip()]
        if st and "all" not in st:
            cond = []
            for t in st:
                if t == "wechat":
                    from sqlalchemy import or_

                    cond.append(or_(Feed.source_type.is_(None), Feed.source_type == "", Feed.source_type == "wechat"))
                else:
                    cond.append(Feed.source_type == t)
            if cond:
                from sqlalchemy import or_

                q = q.filter(or_(*cond))

        if days > 0:
            threshold = int(time.time()) - int(days) * 86400
            q = q.filter(Article.publish_time >= threshold)

        # 拉大候选池后在内存排序，确保不同平台可混排。
        rows = q.order_by(Article.publish_time.desc()).limit(max(1, min(10000, limit * 4))).all()
        content_min_chars = max(20, min(5000, int(cfg.get("parser.content_min_chars", 120) or 120)))
        items: list[dict] = []
        for row in rows:
            source_type = str(row[9] or "").strip().lower() or "wechat"
            if source_type not in ("wechat", "rss", "rsshub"):
                source_type = "wechat"
            raw_content = row[3] or ""
            item = {
                "article_id": str(row[0] or ""),
                "feed_id": str(row[1] or ""),
                "publish_time": int(row[2] or 0),
                # 短正文/仅标题正文视为缺失，优先进入抓取队列。
                "has_content": _content_usable(raw_content, min_chars=content_min_chars),
                "has_description": _text_has_value(row[4]),
                "read_count": int(row[5] or 0),
                "like_count": int(row[6] or 0),
                "share_count": int(row[7] or 0),
                "recommend_count": int(row[8] or 0),
                "source_type": source_type,
                "has_summary": _text_has_value(row[10]),
                "has_key_points": _text_has_value(row[11]),
            }
            if item["article_id"]:
                items.append(item)
        items.sort(key=lambda x: _score_item(x, strategy), reverse=True)

        # 单来源上限，防止某个站点占满任务。
        cap = max(0, int(max_per_feed or 0))
        if cap > 0:
            capped: list[dict] = []
            feed_counts: dict[str, int] = defaultdict(int)
            for it in items:
                fid = str(it.get("feed_id") or "")
                if feed_counts[fid] >= cap:
                    continue
                feed_counts[fid] += 1
                capped.append(it)
            items = capped

        # 轮询混排：不同来源穿插，提升整体命中率与稳定性。
        if bool(round_robin):
            buckets: dict[str, list[dict]] = defaultdict(list)
            feed_order: list[str] = []
            for it in items:
                fid = str(it.get("feed_id") or "")
                if fid not in buckets:
                    feed_order.append(fid)
                buckets[fid].append(it)
            rr: list[dict] = []
            while True:
                moved = False
                for fid in feed_order:
                    arr = buckets.get(fid) or []
                    if not arr:
                        continue
                    rr.append(arr.pop(0))
                    moved = True
                if not moved:
                    break
            items = rr

        return items[: max(1, min(5000, limit))]
    finally:
        try:
            session.close()
        except Exception:
            pass


def _process_one(item: dict, *, force_content: bool, force_insights: bool) -> dict:
    aid = str(item.get("article_id") or "").strip()
    st = str(item.get("source_type") or "").strip().lower() or "wechat"
    if not aid:
        return {"article_id": "", "ok": False, "error": "empty article id", "content_refreshed": False, "insights_refreshed": False}

    content_refreshed = False
    insights_refreshed = False

    # 1) 补正文预览（优先）
    need_content = force_content or not bool(item.get("has_content"))
    content_error = ""
    if need_content:
        try:
            if st in ("rss", "rsshub"):
                from apis.sources import _prefetch_source_article_content

                ret = _prefetch_source_article_content(aid, force=force_content)
                if bool(ret.get("ok")):
                    content_refreshed = not bool(ret.get("skipped"))
                else:
                    content_error = str(ret.get("error") or "content prefetch failed")
            else:
                from apis.article import _fetch_article_content_sync

                ret = _fetch_article_content_sync(aid, force=force_content)
                content_refreshed = bool(ret.get("fetched"))
        except Exception as e:
            content_error = str(e)

    # 没抓到正文且也没有描述文本时，跳过模型解析（避免空跑）。
    if content_error and not bool(item.get("has_description")):
        return {
            "article_id": aid,
            "ok": False,
            "error": content_error,
            "content_refreshed": False,
            "insights_refreshed": False,
            "source_type": st,
        }

    # 2) 推动模型解析（关键信息 + 摘要）
    # 默认走队列，避免并发直连 LLM 导致 429；force_insights=true 时同步强制重算。
    service = InsightsService()
    try:
        if force_insights:
            import asyncio

            service.ensure_cached(aid)
            asyncio.run(service.generate_ai_summary(aid, force=True))
            asyncio.run(service.generate_key_points(aid))
            insights_refreshed = True
        else:
            try:
                from core.queue import PriorityInsightsQueue

                PriorityInsightsQueue.add_task(service.ensure_cached, aid)
                insights_refreshed = True
            except Exception:
                service.ensure_cached(aid)
                insights_refreshed = True
    except Exception as e:
        return {
            "article_id": aid,
            "ok": False,
            "error": f"insights failed: {e}",
            "content_refreshed": content_refreshed,
            "insights_refreshed": False,
        }

    return {
        "article_id": aid,
        "ok": True,
        "error": content_error,
        "content_refreshed": content_refreshed,
        "insights_refreshed": insights_refreshed,
        "source_type": st,
    }


def _run_parser_task(task_id: str) -> None:
    task = _get_task(task_id)
    if not task:
        return
    options = task.get("options") or {}
    days = int(options.get("days") or 3)
    limit = int(options.get("limit") or 300)
    workers = int(options.get("workers") or 6)
    strategy = str(options.get("strategy") or "balanced").strip().lower()
    source_types = [str(x).strip().lower() for x in (options.get("source_types") or []) if str(x).strip()]
    max_per_feed = int(options.get("max_per_feed") or 0)
    round_robin = bool(options.get("round_robin", True))
    force_content = bool(options.get("force_content", False))
    force_insights = bool(options.get("force_insights", False))

    _update_task(
        task_id,
        {
            "status": "running",
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": "",
            "progress": {
                "total": 0,
                "done": 0,
                "ok": 0,
                "failed": 0,
                "content_refreshed": 0,
                "insights_refreshed": 0,
            },
            "results": [],
        },
    )

    try:
        items = _build_candidates(
            days=days,
            limit=limit,
            strategy=strategy,
            source_types=source_types,
            max_per_feed=max_per_feed,
            round_robin=round_robin,
        )
        total = len(items)
        _update_task(
            task_id,
            {
                "progress": {
                    "total": total,
                    "done": 0,
                    "ok": 0,
                    "failed": 0,
                    "content_refreshed": 0,
                    "insights_refreshed": 0,
                }
            },
        )

        done = 0
        ok_count = 0
        fail_count = 0
        content_count = 0
        insights_count = 0
        results: list[dict] = []
        run_workers = max(1, min(32, workers))

        with ThreadPoolExecutor(max_workers=run_workers) as ex:
            futures = [
                ex.submit(
                    _process_one,
                    it,
                    force_content=force_content,
                    force_insights=force_insights,
                )
                for it in items
            ]
            for fut in as_completed(futures):
                done += 1
                try:
                    ret = fut.result()
                except Exception as e:
                    ret = {
                        "article_id": "",
                        "ok": False,
                        "error": str(e),
                        "content_refreshed": False,
                        "insights_refreshed": False,
                    }
                if bool(ret.get("ok")):
                    ok_count += 1
                else:
                    fail_count += 1
                if bool(ret.get("content_refreshed")):
                    content_count += 1
                if bool(ret.get("insights_refreshed")):
                    insights_count += 1
                results.append(ret)

                if done == 1 or done <= 20 or done % 5 == 0 or done >= total:
                    _update_task(
                        task_id,
                        {
                            "progress": {
                                "total": total,
                                "done": done,
                                "ok": ok_count,
                                "failed": fail_count,
                                "content_refreshed": content_count,
                                "insights_refreshed": insights_count,
                            },
                            "results": results[-500:],
                        },
                    )

        _update_task(
            task_id,
            {
                "status": "completed",
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "progress": {
                    "total": total,
                    "done": done,
                    "ok": ok_count,
                    "failed": fail_count,
                    "content_refreshed": content_count,
                    "insights_refreshed": insights_count,
                },
                "results": results[-500:],
            },
        )
    except Exception as e:
        _update_task(
            task_id,
            {
                "status": "failed",
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(e),
            },
        )


def enqueue_parser_task_system(*, options: dict | None = None, allow_parallel: bool = False) -> dict:
    active = _find_active_task("parser_orchestrator")
    if active and not allow_parallel:
        return {"task_id": str(active.get("id") or ""), "status": str(active.get("status") or "running"), "deduped": True}

    opts = options or {}
    task_id = f"parser_{uuid.uuid4().hex[:16]}"
    task = {
        "id": task_id,
        "type": "parser_orchestrator",
        "status": "pending",
        "created_by": "system",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "options": opts,
        "progress": {"total": 0, "done": 0, "ok": 0, "failed": 0, "content_refreshed": 0, "insights_refreshed": 0},
        "results": [],
        "error": "",
    }
    _upsert_task(task)
    queue = _ensure_parser_queue()
    queue.add_task(_run_parser_task, task_id)
    return {"task_id": task_id, "status": "pending", "deduped": False}


class ParserRunRequest(BaseModel):
    days: int = Field(3, ge=0, le=30, description="最近 N 天文章，0 表示不限制")
    limit: int = Field(300, ge=1, le=5000, description="本次最大处理文章数")
    workers: int = Field(6, ge=1, le=32, description="并行 worker 数")
    strategy: Literal["balanced", "newest", "hot"] = Field("balanced", description="排序策略")
    source_types: list[str] = Field(default_factory=lambda: ["wechat", "rss", "rsshub"], description="来源类型过滤")
    max_per_feed: int = Field(0, ge=0, le=100, description="每个来源最多选取条数，0 表示不限制")
    round_robin: bool = Field(True, description="是否按来源轮询混排")
    force_content: bool = Field(False, description="是否强制重抓正文")
    force_insights: bool = Field(False, description="是否强制重算摘要和关键信息")


@router.post("/run", summary="创建解析编排任务（管理员）")
async def create_parser_task(payload: ParserRunRequest, current_user: dict = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail=error_response(code=40301, message="仅管理员可执行解析编排"))

    active = _find_active_task("parser_orchestrator")
    if active:
        return success_response(
            {
                "task_id": str(active.get("id") or ""),
                "status": str(active.get("status") or "running"),
                "deduped": True,
                "message": "已有解析编排任务正在执行，已复用",
            }
        )

    options = {
        "days": int(payload.days),
        "limit": int(payload.limit),
        "workers": int(payload.workers),
        "strategy": str(payload.strategy),
        "source_types": [str(x).strip().lower() for x in (payload.source_types or []) if str(x).strip()],
        "max_per_feed": int(payload.max_per_feed),
        "round_robin": bool(payload.round_robin),
        "force_content": bool(payload.force_content),
        "force_insights": bool(payload.force_insights),
    }
    task_id = f"parser_{uuid.uuid4().hex[:16]}"
    task = {
        "id": task_id,
        "type": "parser_orchestrator",
        "status": "pending",
        "created_by": _uid(current_user),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "options": options,
        "progress": {"total": 0, "done": 0, "ok": 0, "failed": 0, "content_refreshed": 0, "insights_refreshed": 0},
        "results": [],
        "error": "",
    }
    _upsert_task(task)
    try:
        _ensure_parser_queue().add_task(_run_parser_task, task_id)
    except Exception as e:
        _update_task(task_id, {"status": "failed", "error": str(e)})
        raise HTTPException(status_code=500, detail=error_response(code=50081, message=f"解析任务入队失败: {e}"))
    return success_response({"task_id": task_id, "status": "pending", "deduped": False})


@router.get("/tasks", summary="查看解析编排任务列表（管理员）")
async def list_parser_tasks(current_user: dict = Depends(get_current_user), limit: int = Query(20, ge=1, le=200)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail=error_response(code=40301, message="仅管理员可查看解析任务"))
    tasks = _load_tasks()
    return success_response({"list": tasks[:limit], "total": len(tasks)})


@router.get("/tasks/{task_id}", summary="查看解析编排任务详情（管理员）")
async def get_parser_task(task_id: str, current_user: dict = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail=error_response(code=40301, message="仅管理员可查看解析任务"))
    task = _get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=error_response(code=40401, message="任务不存在"))
    return success_response(task)


@router.get("/queue", summary="解析编排队列状态（管理员）")
async def parser_queue_status(current_user: dict = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail=error_response(code=40301, message="仅管理员可查看解析队列"))
    q = _ensure_parser_queue()
    return success_response(q.get_queue_info())
