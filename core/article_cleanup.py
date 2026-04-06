from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import and_, func, or_

from core.config import cfg
from core.db import DB
from core.models.article import Article
from core.models.article_favorite import ArticleFavorite
from core.models.article_favorite_meta import ArticleFavoriteMeta
from core.models.article_insight import ArticleInsight
from core.models.article_note import ArticleNote
from core.models.base import DATA_STATUS
from core.models.user_article_state import UserArticleState
from core.print import print_error, print_info, print_success


def _cfg_int(key: str, default: int, min_v: int, max_v: int) -> int:
    try:
        v = int(str(cfg.get(key, default)).strip() or default)
    except Exception:
        v = default
    return max(min_v, min(max_v, v))


def _cfg_float(key: str, default: float, min_v: float, max_v: float) -> float:
    try:
        v = float(str(cfg.get(key, default)).strip() or default)
    except Exception:
        v = default
    return max(min_v, min(max_v, v))


def _chunked(seq: list[str], size: int) -> list[list[str]]:
    n = max(1, int(size or 1))
    return [seq[i : i + n] for i in range(0, len(seq), n)]


def _cleanup_cached_content_files(article_ids: list[str]) -> int:
    try:
        cache_dir = str(cfg.get("cache.dir", "./data/cache") or "./data/cache").strip() or "./data/cache"
        content_dir = (Path(cache_dir) / "content").resolve()
    except Exception:
        return 0
    if not content_dir.exists():
        return 0

    removed = 0
    for aid in article_ids:
        try:
            target = (content_dir / f"{aid}.json").resolve()
            # 防止路径穿越
            if content_dir not in target.parents:
                continue
            if target.exists() and target.is_file():
                target.unlink(missing_ok=True)
                removed += 1
        except Exception:
            continue
    return removed


def run_article_history_cleanup(
    *,
    dry_run: bool = False,
    older_than_days: int | None = None,
    bottom_ratio: float | None = None,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """
    清理历史文章：
    1) 未被任何用户收藏
    2) 发布时间超过 N 天
    3) 在候选集合中按 read_count 排序后位于后 X%
    """
    days = int(older_than_days) if older_than_days is not None else _cfg_int(
        "article.cleanup.older_than_days", 20, 1, 3650
    )
    ratio = float(bottom_ratio) if bottom_ratio is not None else _cfg_float(
        "article.cleanup.bottom_ratio", 0.30, 0.01, 1.0
    )
    delete_batch = int(batch_size) if batch_size is not None else _cfg_int(
        "article.cleanup.delete_batch_size", 500, 50, 5000
    )

    now = datetime.now()
    cutoff_ts = int(now.timestamp()) - (days * 24 * 3600)
    cutoff_dt = datetime.fromtimestamp(cutoff_ts)

    session = DB.get_session()
    try:
        q = (
            session.query(
                Article.id.label("id"),
                func.coalesce(Article.read_count, 0).label("read_count"),
                Article.publish_time.label("publish_time"),
            )
            .outerjoin(ArticleFavorite, ArticleFavorite.article_id == Article.id)
            .filter(Article.status != DATA_STATUS.DELETED)
            .filter(ArticleFavorite.id.is_(None))
            .filter(
                or_(
                    and_(Article.publish_time.isnot(None), Article.publish_time > 0, Article.publish_time <= cutoff_ts),
                    and_(or_(Article.publish_time.is_(None), Article.publish_time <= 0), Article.created_at.isnot(None), Article.created_at <= cutoff_dt),
                )
            )
            .order_by(func.coalesce(Article.read_count, 0).asc(), Article.publish_time.asc())
        )
        rows = q.all()
        candidate_ids = [str(r.id) for r in rows if str(r.id or "").strip()]
        candidate_total = len(candidate_ids)
        quota = int(math.ceil(candidate_total * ratio)) if candidate_total > 0 else 0
        target_ids = candidate_ids[:quota]

        result: dict[str, Any] = {
            "dry_run": bool(dry_run),
            "rule": {
                "older_than_days": int(days),
                "bottom_ratio": float(ratio),
                "cutoff_publish_time": int(cutoff_ts),
            },
            "candidate_total": int(candidate_total),
            "delete_quota": int(quota),
            "selected_total": int(len(target_ids)),
            "selected_sample": target_ids[:20],
            "deleted": {
                "articles": 0,
                "insights": 0,
                "notes": 0,
                "read_states": 0,
                "favorite_meta": 0,
                "cache_files": 0,
            },
        }
        if dry_run or not target_ids:
            return result

        deleted_articles = 0
        deleted_insights = 0
        deleted_notes = 0
        deleted_states = 0
        deleted_meta = 0
        for chunk in _chunked(target_ids, delete_batch):
            deleted_insights += (
                session.query(ArticleInsight).filter(ArticleInsight.article_id.in_(chunk)).delete(synchronize_session=False)
            )
            deleted_notes += (
                session.query(ArticleNote).filter(ArticleNote.article_id.in_(chunk)).delete(synchronize_session=False)
            )
            deleted_states += (
                session.query(UserArticleState).filter(UserArticleState.article_id.in_(chunk)).delete(synchronize_session=False)
            )
            deleted_meta += (
                session.query(ArticleFavoriteMeta)
                .filter(ArticleFavoriteMeta.article_id.in_(chunk))
                .delete(synchronize_session=False)
            )
            deleted_articles += session.query(Article).filter(Article.id.in_(chunk)).delete(synchronize_session=False)

        session.commit()
        cache_removed = _cleanup_cached_content_files(target_ids)

        result["deleted"] = {
            "articles": int(deleted_articles),
            "insights": int(deleted_insights),
            "notes": int(deleted_notes),
            "read_states": int(deleted_states),
            "favorite_meta": int(deleted_meta),
            "cache_files": int(cache_removed),
        }
        return result
    except Exception as e:
        session.rollback()
        print_error(f"历史文章清理失败: {e}")
        raise
    finally:
        try:
            session.close()
        except Exception:
            pass


def run_article_history_cleanup_from_config() -> dict[str, Any]:
    enabled = bool(cfg.get("article.cleanup.enable", True))
    if not enabled:
        print_info("历史文章清理已禁用（article.cleanup.enable=False）")
        return {"enabled": False}

    ret = run_article_history_cleanup(dry_run=False)
    print_success(
        "历史文章清理完成: candidates=%s selected=%s deleted=%s"
        % (
            ret.get("candidate_total", 0),
            ret.get("selected_total", 0),
            (ret.get("deleted") or {}).get("articles", 0),
        )
    )
    return ret
