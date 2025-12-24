import json

from fastapi import APIRouter, Depends, HTTPException, Query, status as fast_status

from apis.base import error_response, success_response
from core.config import cfg
from core.auth import get_current_user
from core.db import DB
from core.insights import InsightsService
from core.models.article_insight import ArticleInsight
from core.queue import TaskQueue


router = APIRouter(prefix="/insights", tags=["洞察"])


def _serialize_insight(insight: ArticleInsight) -> dict:
    return {
        "article_id": insight.article_id,
        "summary": insight.summary or "",
        "headings": json.loads(insight.headings_json) if insight.headings_json else [],
        "key_points": json.loads(insight.key_points_json) if getattr(insight, "key_points_json", None) else None,
        "llm_breakdown": json.loads(insight.llm_breakdown_json) if insight.llm_breakdown_json else None,
        "status": insight.status,
        "error": insight.error or "",
        "llm_provider": insight.llm_provider or "",
        "llm_model": insight.llm_model or "",
        "updated_at": str(getattr(insight, "updated_at", "") or ""),
        "created_at": str(getattr(insight, "created_at", "") or ""),
    }


@router.get("/{article_id}", summary="获取文章洞察(摘要/标题/LLM拆解)")
async def get_article_insights(
    article_id: str,
    include_llm: bool = Query(True, description="是否返回LLM拆解结果"),
    current_user: dict = Depends(get_current_user),
):
    service = InsightsService()
    insight = service.get_or_create_basic(article_id)
    if not insight:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="文章不存在"),
        )
    # If caches missing, schedule background fill (do not block request).
    try:
        auto_kp = bool(cfg.get("insights.auto_key_points", True))
        auto_bd = bool(cfg.get("insights.auto_llm_breakdown", False))
        missing_kp = auto_kp and not (getattr(insight, "key_points_json", None) or "")
        missing_bd = auto_bd and include_llm and not (getattr(insight, "llm_breakdown_json", None) or "")
        if missing_kp or missing_bd:
            TaskQueue.add_task(service.ensure_cached, article_id)
    except Exception:
        pass
    data = _serialize_insight(insight)
    if not include_llm:
        data["llm_breakdown"] = None
    return success_response(data)


@router.post("/{article_id}/basic", summary="生成/刷新基础洞察(摘要/一级二级标题)")
async def refresh_basic_insights(
    article_id: str,
    current_user: dict = Depends(get_current_user),
):
    service = InsightsService()
    insight = service.get_or_create_basic(article_id)
    if not insight:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="文章不存在"),
        )
    return success_response(_serialize_insight(insight))


@router.post("/{article_id}/breakdown", summary="使用LLM生成全文拆解(最多三级)")
async def generate_llm_breakdown(
    article_id: str,
    force: bool = Query(False, description="强制重新生成(忽略缓存)"),
    current_user: dict = Depends(get_current_user),
):
    service = InsightsService()
    insight = await service.generate_llm_breakdown(article_id, force=force)
    if not insight:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="文章不存在"),
        )
    return success_response(_serialize_insight(insight))


@router.post("/{article_id}/key_points", summary="生成/刷新关键信息点(3-8条+高亮)")
async def generate_key_points(
    article_id: str,
    force: bool = Query(False, description="强制重新生成(忽略缓存)"),
    current_user: dict = Depends(get_current_user),
):
    service = InsightsService()
    insight = await service.generate_key_points(article_id, force=force)
    if not insight:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="文章不存在"),
        )
    return success_response(_serialize_insight(insight))


@router.post("/batch/basic", summary="批量生成/刷新基础洞察(最近文章)")
async def batch_refresh_basic(
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    from core.models.article import Article
    articles = (
        session.query(Article.id)
        .order_by(Article.publish_time.desc())
        .limit(limit)
        .all()
    )
    service = InsightsService()
    ok = 0
    for (aid,) in articles:
        try:
            service.get_or_create_basic(aid)
            ok += 1
        except Exception:
            continue
    return success_response({"processed": ok, "limit": limit})


@router.post("/batch/cache", summary="批量预生成并缓存洞察(摘要/关键信息/全文拆解)")
async def batch_cache_insights(
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    from core.models.article import Article
    from core.queue import TaskQueue

    article_ids = (
        session.query(Article.id)
        .order_by(Article.publish_time.desc())
        .limit(limit)
        .all()
    )
    service = InsightsService()
    scheduled = 0
    for (aid,) in article_ids:
        try:
            TaskQueue.add_task(service.ensure_cached, aid)
            scheduled += 1
        except Exception:
            continue
    return success_response({"scheduled": scheduled, "limit": limit})
