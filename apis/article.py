from datetime import datetime
import threading

from fastapi import APIRouter, Depends, HTTPException, status as fast_status, Query
from starlette.concurrency import run_in_threadpool
from core.auth import get_current_user
from core.db import DB
from core.models.base import DATA_STATUS
from core.models.article import Article,ArticleBase
from sqlalchemy import and_, func, or_, desc
from .base import success_response, error_response
from core.config import cfg
from apis.base import format_search_kw
from core.print import print_warning, print_info, print_error, print_success
from core.insights import InsightsService
from driver.wxarticle import WXArticleFetcher
from core.queue import InFlightGate, InsightsQueue, PriorityInsightsQueue, PriorityTaskQueue
from core.models.user_article_state import UserArticleState
from core.models.feed import Feed
from core.source.content_extractor import fetch_source_article_content
from core.article_cleanup import run_article_history_cleanup
router = APIRouter(prefix=f"/articles", tags=["文章管理"])

_ARTICLE_CONTENT_GATE = InFlightGate()
_WECHAT_FETCH_LOCK = threading.Lock()

def _estimate_word_count(text: str) -> int:
    if not text:
        return 0
    return len("".join((text or "").split()))


def _article_metrics_missing(article: Article) -> bool:
    return (
        getattr(article, "read_count", None) is None
        or getattr(article, "like_count", None) is None
        or getattr(article, "share_count", None) is None
        or getattr(article, "recommend_count", None) is None
    )


def _is_admin(current_user: dict) -> bool:
    role = str((current_user or {}).get("role") or "").strip().lower()
    username = str((current_user or {}).get("username") or "").strip().lower()
    return role == "admin" or username == "admin"


def _fetch_article_content_sync(article_id: str, *, force: bool = False) -> dict:
    session = DB.get_session()
    article = (
        session.query(Article)
        .filter(Article.id == article_id)
        .filter(Article.status != DATA_STATUS.DELETED)
        .first()
    )
    if not article:
        raise ValueError("文章不存在")

    has_content = bool((article.content or "").strip() and (article.content or "").strip() != "DELETED")
    needs_fetch = force or (not has_content) or _article_metrics_missing(article)

    if not needs_fetch:
        ins = InsightsService().get_or_create_basic(article_id)
        return {
            "ok": True,
            "fetched": False,
            "content_len": len((article.content or "") or ""),
            "desc_len": len((article.description or "") or ""),
            "read_count": getattr(article, "read_count", None),
            "like_count": getattr(article, "like_count", None),
            "share_count": getattr(article, "share_count", None),
            "recommend_count": getattr(article, "recommend_count", None),
            "summary_len": len((ins.summary or "") if ins else ""),
        }

    url = (article.url or "").strip()
    if not url:
        raise ValueError("文章缺少原文链接，无法抓取正文")

    # DB-level cache: reuse parsed content from the same URL to avoid repeated parsing after list/page refresh.
    if not force:
        cached = (
            session.query(Article)
            .filter(Article.id != article_id)
            .filter(Article.url == url)
            .filter(Article.status != DATA_STATUS.DELETED)
            .filter(Article.content.isnot(None))
            .filter(Article.content != "")
            .filter(Article.content != "DELETED")
            .order_by(desc(Article.updated_at), desc(Article.publish_time))
            .first()
        )
        if cached:
            changed = False
            if not has_content:
                article.content = (cached.content or "").strip()
                changed = True
            if not (article.description or "").strip() and (cached.description or "").strip():
                article.description = (cached.description or "").strip()
                changed = True
            if not (article.pic_url or "").strip() and (cached.pic_url or "").strip():
                article.pic_url = (cached.pic_url or "").strip()
                changed = True
            for metric_key in ("read_count", "like_count", "share_count", "recommend_count"):
                if getattr(article, metric_key, None) is None and getattr(cached, metric_key, None) is not None:
                    setattr(article, metric_key, getattr(cached, metric_key))
                    changed = True
            if changed:
                article.updated_at = datetime.now()
                session.add(article)
                session.commit()
            ins = InsightsService().get_or_create_basic(article_id)
            return {
                "ok": True,
                "fetched": False,
                "reused": True,
                "content_len": len((article.content or "") or ""),
                "desc_len": len((article.description or "") or ""),
                "read_count": getattr(article, "read_count", None),
                "like_count": getattr(article, "like_count", None),
                "share_count": getattr(article, "share_count", None),
                "recommend_count": getattr(article, "recommend_count", None),
                "summary_len": len((ins.summary or "") if ins else ""),
            }

    feed = session.query(Feed).filter(Feed.id == article.mp_id).first()
    source_type = str(getattr(feed, "source_type", "wechat") or "wechat").strip().lower()

    if source_type in ("rss", "rsshub"):
        info = fetch_source_article_content(
            url,
            title_hint=str(article.title or ""),
            description_hint=str(article.description or ""),
        )
        if not bool(info.get("ok")):
            raise RuntimeError(f"抓取失败：{str(info.get('error') or '无可用正文')}")
    else:
        min_content_chars = max(20, min(5000, int(cfg.get("article.content_min_chars", 120) or 120)))
        wx_err = ""
        try:
            # Playwright 同进程多线程并发抓微信正文稳定性较差，串行化可避免卡死。
            with _WECHAT_FETCH_LOCK:
                info = WXArticleFetcher().get_article_content(url)
        except Exception as e:
            wx_err = str(e)
            info = {}

        wx_content = str((info or {}).get("content") or "").strip()
        wx_len = _estimate_word_count(wx_content)
        # Playwright 抓取失败 / 只抓到标题这类短内容时，退回通用 HTML 提取器，避免正文长期空白。
        if ((not wx_content) or (wx_content != "DELETED" and wx_len < min_content_chars)) and wx_content != "DELETED":
            fallback = fetch_source_article_content(
                url,
                title_hint=str(article.title or ""),
                description_hint=str(article.description or ""),
            )
            if bool(fallback.get("ok")):
                fb_content = str(fallback.get("content_html") or fallback.get("content") or "").strip()
                fb_len = _estimate_word_count(fb_content)
                if fb_content and (fb_len >= max(20, min_content_chars) or fb_len > wx_len):
                    info = {
                        **(info or {}),
                        "content": fb_content,
                        "topic_image": str((info or {}).get("topic_image") or fallback.get("topic_image") or fallback.get("pic_url") or ""),
                        "description": str((info or {}).get("description") or fallback.get("description") or ""),
                    }
            elif wx_err and not info:
                raise RuntimeError(f"抓取失败：{wx_err}")

    if not info:
        raise RuntimeError("抓取失败：未返回有效内容")

    content = (info.get("content") or "").strip()
    topic_image = (info.get("topic_image") or "").strip()
    desc = (info.get("description") or "").strip()
    read_count = info.get("read_count", None)
    like_count = info.get("like_count", None)
    share_count = info.get("share_count", None)
    recommend_count = info.get("recommend_count", None)

    changed = False
    if content and (force or not has_content):
        article.content = content
        changed = True
    if topic_image and not (article.pic_url or "").strip():
        article.pic_url = topic_image
        changed = True
    if desc and not (article.description or "").strip():
        article.description = desc
        changed = True
    if read_count is not None and (getattr(article, "read_count", None) is None or force):
        try:
            article.read_count = int(read_count)
            changed = True
        except Exception:
            pass
    if like_count is not None and (getattr(article, "like_count", None) is None or force):
        try:
            article.like_count = int(like_count)
            changed = True
        except Exception:
            pass
    if share_count is not None and (getattr(article, "share_count", None) is None or force):
        try:
            article.share_count = int(share_count)
            changed = True
        except Exception:
            pass
    if recommend_count is not None and (getattr(article, "recommend_count", None) is None or force):
        try:
            article.recommend_count = int(recommend_count)
            changed = True
        except Exception:
            pass

    if changed:
        article.updated_at = datetime.now()
        session.add(article)
        session.commit()
        session.refresh(article)

    service = InsightsService()
    ins = service.get_or_create_basic(article_id)

    if ins and (ins.summary or "").strip() and not (article.description or "").strip():
        article.description = (ins.summary or "").strip()
        article.updated_at = datetime.now()
        session.add(article)
        session.commit()
        session.refresh(article)

    try:
        PriorityInsightsQueue.add_task(service.ensure_cached, article_id)
    except Exception:
        pass

    return {
        "ok": True,
        "fetched": True,
        "changed": bool(changed),
        "content_len": len((article.content or "") or ""),
        "desc_len": len((article.description or "") or ""),
        "pic_url": article.pic_url or "",
        "read_count": getattr(article, "read_count", None),
        "like_count": getattr(article, "like_count", None),
        "share_count": getattr(article, "share_count", None),
        "recommend_count": getattr(article, "recommend_count", None),
        "summary_len": len((ins.summary or "") if ins else ""),
    }


def _fetch_article_content_task(article_id: str, force: bool = False) -> None:
    try:
        _fetch_article_content_sync(article_id, force=force)
    finally:
        _ARTICLE_CONTENT_GATE.release(article_id)


def _schedule_article_content_fetch(article_id: str, *, force: bool = False) -> bool:
    if not _ARTICLE_CONTENT_GATE.try_acquire(article_id):
        return False
    try:
        PriorityTaskQueue.add_task(_fetch_article_content_task, article_id, force)
        return True
    except Exception:
        _ARTICLE_CONTENT_GATE.release(article_id)
        return False

    
@router.delete("/clean", summary="清理无效文章(MP_ID不存在于Feeds表中的文章)")
async def clean_orphan_articles(
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        from core.models.article import Article
        
        # 找出Articles表中mp_id不在Feeds表中的记录
        subquery = session.query(Feed.id).subquery()
        deleted_count = session.query(Article)\
            .filter(~Article.mp_id.in_(subquery))\
            .delete(synchronize_session=False)
        
        session.commit()
        
        return success_response({
            "message": "清理无效文章成功",
            "deleted_count": deleted_count
        })
    except Exception as e:
        session.rollback()
        print(f"清理无效文章错误: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message="清理无效文章失败"
            )
        )

@router.put("/{article_id:path}/read", summary="改变文章阅读状态")
async def toggle_article_read_status(
    article_id: str,
    is_read: bool = Query(..., description="阅读状态: true为已读, false为未读"),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        user_id = str(current_user.get("original_user").id) if current_user.get("original_user") else str(current_user.get("username") or "")

        # 检查文章是否存在
        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )
        
        now = datetime.now()
        st = (
            session.query(UserArticleState)
            .filter(UserArticleState.user_id == user_id)
            .filter(UserArticleState.article_id == article_id)
            .first()
        )
        if st:
            st.is_read = 1 if is_read else 0
            st.updated_at = now
        else:
            session.add(
                UserArticleState(
                    user_id=user_id,
                    article_id=article_id,
                    is_read=1 if is_read else 0,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()
        
        return success_response({
            "message": f"文章已标记为{'已读' if is_read else '未读'}",
            "is_read": is_read
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message=f"更新文章阅读状态失败: {str(e)}"
            )
        )
    
@router.post("/{article_id:path}/content/fetch", summary="抓取并保存文章正文(用于全文拆解/本地阅读)")
async def fetch_article_content(
    article_id: str,
    force: bool = Query(False, description="即使已有正文也重新抓取"),
    async_mode: bool = Query(False, description="仅排队抓取并立即返回"),
    current_user: dict = Depends(get_current_user),
):
    try:
        session = DB.get_session()
        article = (
            session.query(Article)
            .filter(Article.id == article_id)
            .filter(Article.status != DATA_STATUS.DELETED)
            .first()
        )
        if not article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="文章不存在"),
            )
        if async_mode:
            if not force and (article.content or "").strip() and (article.content or "").strip() != "DELETED" and not _article_metrics_missing(article):
                try:
                    PriorityInsightsQueue.add_task(InsightsService().ensure_cached, article_id)
                except Exception:
                    pass
                return success_response(
                    {
                        "ok": True,
                        "queued": False,
                        "fetched": False,
                        "content_len": len((article.content or "") or ""),
                        "desc_len": len((article.description or "") or ""),
                    }
                )
            queued = _schedule_article_content_fetch(article_id, force=force)
            if queued:
                try:
                    PriorityInsightsQueue.add_task(InsightsService().ensure_cached, article_id)
                except Exception:
                    pass
            return success_response(
                {
                    "ok": True,
                    "queued": queued,
                    "fetched": False,
                    "content_len": len((article.content or "") or ""),
                    "desc_len": len((article.description or "") or ""),
                }
            )

        result = await run_in_threadpool(lambda: _fetch_article_content_sync(article_id, force=force))
        return success_response(result)
    except HTTPException as e:
        raise e
    except ValueError as e:
        message = str(e)
        status_code = fast_status.HTTP_404_NOT_FOUND if "不存在" in message else fast_status.HTTP_400_BAD_REQUEST
        code = 40401 if "不存在" in message else 40001
        raise HTTPException(status_code=status_code, detail=error_response(code=code, message=message))
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"抓取正文失败: {str(e)}"),
        )

@router.delete("/clean_duplicate_articles", summary="清理重复文章")
async def clean_duplicate(
    current_user: dict = Depends(get_current_user)
):
    try:
        from tools.clean import clean_duplicate_articles
        (msg, deleted_count) =clean_duplicate_articles()
        return success_response({
            "message": msg,
            "deleted_count": deleted_count
        })
    except Exception as e:
        print(f"清理重复文章: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message="清理重复文章失败"
            )
        )


@router.post("/cleanup/history", summary="清理历史低价值文章(管理员)")
async def cleanup_history_articles(
    dry_run: bool = Query(False, description="true=仅预览将删除的数据，不实际删除"),
    older_than_days: int = Query(20, ge=1, le=3650, description="仅处理超过该天数的文章"),
    bottom_ratio: float = Query(0.30, ge=0.01, le=1.0, description="按点击量(read_count)排序后的后N%比例"),
    current_user: dict = Depends(get_current_user),
):
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=fast_status.HTTP_403_FORBIDDEN,
            detail=error_response(code=40301, message="仅管理员可执行历史清理"),
        )
    try:
        ret = run_article_history_cleanup(
            dry_run=bool(dry_run),
            older_than_days=int(older_than_days),
            bottom_ratio=float(bottom_ratio),
        )
        return success_response(ret)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"历史清理失败: {str(e)}"),
        )


@router.api_route("", summary="获取文章列表",methods= ["GET", "POST"], operation_id="get_articles_list")
async def get_articles(
    offset: int = Query(0, ge=0),
    limit: int = Query(5, ge=1, le=100),
    with_total: bool = Query(True, description="是否统计total，关闭可显著提升列表查询性能"),
    status: str = Query(None),
    search: str = Query(None),
    mp_id: str = Query(None),
    mp_ids: str = Query(None, description="逗号分隔的多个公众号ID，用于专题/批量过滤"),
    has_content:bool=Query(False),
    unread_only: bool = Query(False, description="仅返回未读文章"),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        user_id = str(current_user.get("original_user").id) if current_user.get("original_user") else str(current_user.get("username") or "")

        article_model = Article if has_content else ArticleBase
        query = (
            session.query(article_model, func.coalesce(UserArticleState.is_read, 0).label("user_is_read"))
            .outerjoin(
                UserArticleState,
                and_(UserArticleState.article_id == article_model.id, UserArticleState.user_id == user_id),
            )
        )
        if has_content:
            query = query.filter(article_model.content.isnot(None)).filter(article_model.content != "").filter(article_model.content != "DELETED")
        if status:
            query = query.filter(article_model.status == status)
        else:
            query = query.filter(article_model.status != DATA_STATUS.DELETED)
        if mp_id:
            query = query.filter(article_model.mp_id == mp_id)
        elif mp_ids:
            try:
                ids = [x.strip() for x in str(mp_ids).split(",") if x.strip()]
            except Exception:
                ids = []
            if ids:
                query = query.filter(article_model.mp_id.in_(ids))
        if unread_only:
            query = query.filter(func.coalesce(UserArticleState.is_read, 0) == 0)
        if search:
            query = query.filter(
               format_search_kw(search)
            )
        
        # 大表 count() 成本较高；前端频道切换场景可关闭 with_total 获得更快响应
        total = query.count() if with_total else -1
        query = query.order_by(article_model.publish_time.desc()).offset(offset).limit(limit)
        # query= query.order_by(Article.id.desc()).offset(offset).limit(limit)
        # 分页查询（按发布时间降序）
        rows = query.all()

        # 调试时可打开打印；默认关闭避免频繁编译 SQL 带来额外开销
        if bool(cfg.get("debug.print_article_sql", False)):
            print_warning(query.statement.compile(compile_kwargs={"literal_binds": True}))
                       
        # 查询公众号名称
        from core.models.feed import Feed
        mp_names = {}
        articles = [a for (a, _is_read) in rows]
        for article in articles:
            if getattr(article, "mp_id", None) and article.mp_id not in mp_names:
                feed = session.query(Feed).filter(Feed.id == article.mp_id).first()
                mp_names[article.mp_id] = feed.mp_name if feed else "未知公众号"
        
        # 合并公众号名称到文章列表
        article_list = []
        for (article, user_is_read) in rows:
            article_dict = article.__dict__.copy()
            article_dict.pop("_sa_instance_state", None)
            article_dict["mp_name"] = mp_names.get(article.mp_id, "未知公众号")
            article_dict["is_read"] = int(user_is_read or 0)
            article_dict["word_count"] = _estimate_word_count(article_dict.get("description") or "")
            article_list.append(article_dict)
        
        from .base import success_response
        return success_response({
            "list": article_list,
            "total": total,
            "counted": bool(with_total)
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message=f"获取文章列表失败: {str(e)}"
            )
        )

@router.get("/{article_id:path}", summary="获取文章详情")
async def get_article_detail(
    article_id: str,
    content: bool = False,
    # current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        article = session.query(Article).filter(Article.id==article_id).filter(Article.status != DATA_STATUS.DELETED).first()
        if not article:
            from .base import error_response
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )
        # Lightweight read-time cache fallback:
        # if this row has no content yet, reuse another row with same URL that already has content.
        has_content = bool((article.content or "").strip() and (article.content or "").strip() != "DELETED")
        if not has_content:
            url = str(article.url or "").strip()
            if url:
                cached = (
                    session.query(Article)
                    .filter(Article.id != article.id)
                    .filter(Article.url == url)
                    .filter(Article.status != DATA_STATUS.DELETED)
                    .filter(Article.content.isnot(None))
                    .filter(Article.content != "")
                    .filter(Article.content != "DELETED")
                    .order_by(desc(Article.updated_at), desc(Article.publish_time))
                    .first()
                )
                if cached:
                    article.content = (cached.content or "").strip()
                    if not (article.description or "").strip() and (cached.description or "").strip():
                        article.description = (cached.description or "").strip()
                    if not (article.pic_url or "").strip() and (cached.pic_url or "").strip():
                        article.pic_url = (cached.pic_url or "").strip()
                    article.updated_at = datetime.now()
                    session.add(article)
                    session.commit()
                    # Ensure response uses persisted values in this request (not stale instance state).
                    session.refresh(article)
        return success_response(article)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message=f"获取文章详情失败: {str(e)}"
            )
        )   

@router.delete("/{article_id:path}", summary="删除文章")
async def delete_article(
    article_id: str,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.article import Article
        
        # 检查文章是否存在
        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )
        # 逻辑删除文章（更新状态为deleted）
        article.status = DATA_STATUS.DELETED
        if cfg.get("article.true_delete", False):
            session.delete(article)
        session.commit()
        
        return success_response(None, message="文章已标记为删除")
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message=f"删除文章失败: {str(e)}"
            )
        )

@router.get("/{article_id:path}/next", summary="获取下一篇文章")
async def get_next_article(
    article_id: str,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        # 获取当前文章的发布时间
        current_article = session.query(Article).filter(Article.id == article_id).first()
        if not current_article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="当前文章不存在"
                )
            )
        
        # 查询发布时间更晚的第一篇文章
        next_article = session.query(Article)\
            .filter(Article.publish_time > current_article.publish_time)\
            .filter(Article.status != DATA_STATUS.DELETED)\
            .filter(Article.mp_id == current_article.mp_id)\
            .order_by(Article.publish_time.asc())\
            .first()
        
        if not next_article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40402,
                    message="没有下一篇文章"
                )
            )
        
        return success_response(next_article)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message=f"获取下一篇文章失败: {str(e)}"
            )
        )

@router.get("/{article_id:path}/prev", summary="获取上一篇文章")
async def get_prev_article(
    article_id: str,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        # 获取当前文章的发布时间
        current_article = session.query(Article).filter(Article.id == article_id).first()
        if not current_article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="当前文章不存在"
                )
            )
        
        # 查询发布时间更早的第一篇文章
        prev_article = session.query(Article)\
            .filter(Article.publish_time < current_article.publish_time)\
            .filter(Article.status != DATA_STATUS.DELETED)\
            .filter(Article.mp_id == current_article.mp_id)\
            .order_by(Article.publish_time.desc())\
            .first()
        
        if not prev_article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40403,
                    message="没有上一篇文章"
                )
            )
        
        return success_response(prev_article)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message=f"获取上一篇文章失败: {str(e)}"
            )
        )
