from logging import info
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.background import BackgroundTasks
from core.auth import get_current_user
from core.db import DB
from core.wx import search_Biz
from driver.wx import Wx
from .base import success_response, error_response
from datetime import datetime
from core.config import cfg
from core.res import save_avatar_locally
import io
import os
from jobs.article import UpdateArticle
from driver.wxarticle import WXArticleFetcher
import base64
from typing import Any, Optional
import json
import threading
import time
from sqlalchemy import func
from core.models.user_subscription import UserSubscription
router = APIRouter(prefix=f"/mps", tags=["公众号管理"])
# import core.db as db
# UPDB=db.Db("数据抓取")
# def UpdateArticle(art:dict):
#             return UPDB.add_article(art)


def _safe_isoformat(dt: Any) -> Optional[str]:
    if dt is None:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)


def _normalize_fakeid(mp_id: Optional[str]) -> Optional[str]:
    """Normalize incoming mp identifier to a usable __biz(base64) string.

    Accepts:
    - numeric fakeid ("2397003540") -> base64("2397003540")
    - __biz base64 ("MjM5NzAwMzU0MA==") -> keep
    """
    if not mp_id:
        return None
    mp_id = str(mp_id).strip()
    if mp_id.isdigit():
        try:
            return base64.b64encode(mp_id.encode("utf-8")).decode("utf-8")
        except Exception:
            return None
    try:
        decoded = base64.b64decode(mp_id).decode("utf-8", errors="ignore").strip()
        if decoded.isdigit():
            return mp_id
    except Exception:
        return None
    return None


def _extract_numeric_id(mp_id: Optional[str]) -> Optional[str]:
    if not mp_id:
        return None
    mp_id = str(mp_id).strip()
    if mp_id.isdigit():
        return mp_id
    try:
        decoded = base64.b64decode(mp_id).decode("utf-8", errors="ignore").strip()
        return decoded if decoded.isdigit() else None
    except Exception:
        return None


def _should_skip_sync(mp, sync_interval: int) -> tuple[bool, int]:
    """Rate-limit by last sync_time (seconds since epoch)."""
    try:
        import time

        now = int(time.time())
        last_sync = int(getattr(mp, "sync_time", 0) or 0)
        if last_sync and now - last_sync < sync_interval:
            return True, now - last_sync
        return False, now - last_sync if last_sync else now
    except Exception:
        return False, 0


def _queue_update_feed(feed_id: str, start_page: int = 0, end_page: int = 1) -> None:
    """Background worker: update one feed and (re)generate insights for changed articles.

    Notes:
    - Article-level insights are already enqueued in DB.add_article when a row changes.
    - This function is designed to run inside TaskQueue worker threads.
    """
    session2 = DB.get_session()
    try:
        from core.models.feed import Feed
        from core.wx import WxGather
        from core.insights import InsightsService

        mp = session2.query(Feed).filter(Feed.id == feed_id).first()
        if not mp:
            return

        biz = _normalize_fakeid(getattr(mp, "faker_id", None))
        if not biz:
            return

        sync_interval = int(cfg.get("sync_interval", 60) or 60)
        should_skip, time_span = _should_skip_sync(mp, sync_interval)
        if should_skip:
            return

        wx = WxGather().Model()
        wx.get_Articles(
            biz,
            Mps_id=mp.id,
            Mps_title=mp.mp_name,
            CallBack=UpdateArticle,
            start_page=max(0, int(start_page or 0)),
            MaxPage=max(1, int(end_page or 1)),
        )

        try:
            if bool(cfg.get("insights.prewarm_on_update", True)):
                days = int(cfg.get("insights.prewarm_days", 3))
                limit = int(cfg.get("insights.prewarm_limit", 120))
                InsightsService().ensure_mp_recent_cached(mp.id, days=days, limit=limit)
        except Exception:
            pass
    except Exception:
        pass


def _load_plaza_data() -> dict:
    path = str(cfg.get("plaza.file", "data/plaza_mps.json") or "data/plaza_mps.json")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("categories"), list):
                return data
    except Exception:
        pass
    return {"version": 1, "categories": []}


_PLAZA_LOCK = threading.Lock()


def _plaza_file_path() -> str:
    return str(cfg.get("plaza.file", "data/plaza_mps.json") or "data/plaza_mps.json")


def _plaza_write(data: dict) -> None:
    path = _plaza_file_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _with_plaza_file_lock(fn):
    """Cross-process lock for plaza file updates (best-effort on non-POSIX)."""
    path = _plaza_file_path()
    lock_path = f"{path}.lock"
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    try:
        import fcntl  # type: ignore

        with open(lock_path, "a", encoding="utf-8") as lockf:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
            try:
                return fn()
            finally:
                try:
                    fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
    except Exception:
        return fn()


def _plaza_upsert_item(item: dict) -> None:
    """Upsert a plaza item into the 'community' category; best-effort persistence."""
    if not isinstance(item, dict):
        return
    name = str(item.get("name") or "").strip()
    if not name:
        return
    feed_id = str(item.get("feed_id") or "").strip()
    mp_id = str(item.get("mp_id") or "").strip()
    name_key = name.lower()

    def _apply():
        data = _load_plaza_data()
        cats = data.get("categories") if isinstance(data, dict) else None
        if not isinstance(cats, list):
            data = {"version": 1, "categories": []}
            cats = data["categories"]

        community = None
        for c in cats:
            if isinstance(c, dict) and str(c.get("id") or "") == "community":
                community = c
                break
        if community is None:
            community = {"id": "community", "name": "用户添加", "items": []}
            cats.insert(0, community)

        items = community.get("items")
        if not isinstance(items, list):
            items = []
            community["items"] = items

        found = None
        for it in items:
            if not isinstance(it, dict):
                continue
            if feed_id and str(it.get("feed_id") or "") == feed_id:
                found = it
                break
            if mp_id and str(it.get("mp_id") or "") == mp_id:
                found = it
                break
            if str(it.get("name") or "").strip().lower() == name_key:
                found = it
                break

        if found is None:
            items.append(item)
        else:
            found.update({k: v for k, v in item.items() if v not in (None, "", [])})

        try:
            items.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
        except Exception:
            pass

        _plaza_write(data)

    with _PLAZA_LOCK:
        _with_plaza_file_lock(_apply)


def _uid(current_user: dict) -> str:
    try:
        return str(current_user.get("original_user").id)
    except Exception:
        return str(current_user.get("username") or "")


def _permissions_list(current_user: dict) -> list[str]:
    raw = current_user.get("permissions", [])
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            v = json.loads(s)
            if isinstance(v, list):
                return [str(x) for x in v]
        except Exception:
            pass
        return [x.strip() for x in s.split(",") if x.strip()]
    return []


def _can_manage_feeds(current_user: dict) -> bool:
    try:
        if str(current_user.get("role") or "") == "admin":
            return True
        if str(current_user.get("username") or "") == "admin":
            return True
        perms = _permissions_list(current_user)
        return "wechat:manage" in perms or "admin" in perms
    except Exception:
        return False


@router.get("/plaza", summary="订阅广场：分类推荐公众号")
async def get_plaza(
    kw: str = Query("", description="可选：关键词过滤"),
    limit: int = Query(500, ge=1, le=2000),
    current_user: dict = Depends(get_current_user),
):
    data = _load_plaza_data()
    q = (kw or "").strip().lower()
    if not q:
        return success_response(data)

    out = {"version": data.get("version", 1), "categories": []}
    for cat in data.get("categories") or []:
        if not isinstance(cat, dict):
            continue
        items = []
        for it in cat.get("items") or []:
            if not isinstance(it, dict):
                continue
            hay = " ".join(
                [
                    str(it.get("name") or ""),
                    str(it.get("kw") or ""),
                    str(it.get("desc") or ""),
                    " ".join([str(x) for x in (it.get("tags") or [])]),
                ]
            ).lower()
            if q in hay:
                items.append(it)
            if len(items) >= limit:
                break
        if items:
            out["categories"].append({"id": cat.get("id"), "name": cat.get("name"), "items": items})
    return success_response(out)


@router.get("/search/{kw}", summary="搜索公众号")
async def search_mp(
    kw: str = "",
    limit: int = 10,
    offset: int = 0,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        result = search_Biz(kw,limit=limit,offset=offset)
        data={
            'list':result.get('list') if result is not None else [],
            'page':{
                'limit':limit,
                'offset':offset
            },
            'total':result.get('total') if result is not None else 0
        }
        return success_response(data)
    except Exception as e:
        print(f"搜索公众号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message=f"搜索公众号失败,请重新扫码授权！",
            )
        )

@router.get("", summary="获取公众号列表")
async def get_mps(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    scope: str = Query("mine", description="mine|all; all仅管理员可用"),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        user_id = _uid(current_user)
        query = session.query(Feed).filter(Feed.faker_id.isnot(None)).filter(Feed.faker_id != "")

        if scope != "all" or not _can_manage_feeds(current_user):
            # per-user subscriptions
            has_subs = bool(session.query(func.count(UserSubscription.id)).filter(UserSubscription.user_id == user_id).scalar() or 0)
            if not has_subs and (str(current_user.get("role") or "") == "admin" or str(current_user.get("username") or "") == "admin"):
                # legacy compatibility: admin without subscriptions -> subscribe all
                try:
                    now = datetime.now()
                    all_ids = session.query(Feed.id).filter(Feed.faker_id.isnot(None)).filter(Feed.faker_id != "").all()
                    session.bulk_save_objects([UserSubscription(user_id=user_id, feed_id=fid, created_at=now, updated_at=now) for (fid,) in all_ids])
                    session.commit()
                except Exception:
                    session.rollback()
            query = query.join(UserSubscription, UserSubscription.feed_id == Feed.id).filter(UserSubscription.user_id == user_id)
        if kw:
            query = query.filter(Feed.mp_name.ilike(f"%{kw}%"))
        total = query.count()
        mps = query.order_by(Feed.created_at.desc()).limit(limit).offset(offset).all()
        return success_response({
            "list": [{
                "id": mp.id,
                "mp_name": mp.mp_name,
                "mp_cover": mp.mp_cover,
                "mp_intro": mp.mp_intro,
                "status": mp.status,
                "created_at": _safe_isoformat(mp.created_at)
            } for mp in mps],
            "page": {
                "limit": limit,
                "offset": offset,
                "total": total
            },
            "total": total
        })
    except Exception as e:
        print(f"获取公众号列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="获取公众号列表失败"
            )
        )

@router.get("/update/{mp_id}", summary="更新公众号文章")
async def update_mps(
     mp_id: str,
     start_page: int = 0,
     end_page: int = 1,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        from core.queue import TaskQueue

        if str(mp_id).strip().lower() == "all":
            # One-click refresh: enqueue updates for all feeds the current user subscribed to.
            user_id = _uid(current_user)
            query = (
                session.query(Feed)
                .join(UserSubscription, UserSubscription.feed_id == Feed.id)
                .filter(UserSubscription.user_id == user_id)
                .filter(Feed.faker_id.isnot(None))
                .filter(Feed.faker_id != "")
            )
            feeds = query.all()
            if not feeds:
                return success_response({"queued": 0, "message": "当前用户暂无订阅公众号"})

            queued = 0
            for f in feeds:
                try:
                    TaskQueue.add_task(_queue_update_feed, str(f.id), int(start_page or 0), int(end_page or 1))
                    queued += 1
                except Exception:
                    continue
            return success_response({"queued": queued, "total": len(feeds)})

        # 非管理员仅允许更新自己订阅的公众号，避免公域滥用
        if not _can_manage_feeds(current_user):
            user_id = _uid(current_user)
            ok = (
                session.query(func.count(UserSubscription.id))
                .filter(UserSubscription.user_id == user_id)
                .filter(UserSubscription.feed_id == mp_id)
                .scalar()
            )
            if not ok:
                return error_response(code=40301, message="无权限更新该公众号（未订阅）")
        mp = session.query(Feed).filter(Feed.id == mp_id).first()
        if not mp:
           return error_response(
                    code=40401,
                    message="请选择一个公众号"
                )
        biz = _normalize_fakeid(mp.faker_id)
        if not biz:
            return error_response(
                code=40403,
                message="该订阅缺少可用的fakeid，无法更新文章（请通过“搜索公众号”添加或检查导入数据）",
                data={"faker_id": mp.faker_id},
            )
        if mp.faker_id != biz:
            mp.faker_id = biz
            session.commit()
        import time
        sync_interval=cfg.get("sync_interval",60)
        should_skip, time_span = _should_skip_sync(mp, int(sync_interval or 60))
        if should_skip:
           return error_response(
                    code=40402,
                    message="请不要频繁更新操作",
                    data={"time_span":time_span}
                )
        result=[]    
        def UpArt(mp):
            from core.wx import WxGather
            from core.insights import InsightsService
            wx=WxGather().Model()
            wx.get_Articles(biz,Mps_id=mp.id,Mps_title=mp.mp_name,CallBack=UpdateArticle,start_page=start_page,MaxPage=end_page)
            result=wx.articles
            try:
                if bool(cfg.get("insights.prewarm_on_update", True)):
                    days = int(cfg.get("insights.prewarm_days", 3))
                    limit = int(cfg.get("insights.prewarm_limit", 120))
                    InsightsService().ensure_mp_recent_cached(mp.id, days=days, limit=limit)
            except Exception:
                pass
        import threading
        threading.Thread(target=UpArt,args=(mp,)).start()
        return success_response({
            "time_span":time_span,
            "list":result,
            "total":len(result),
            "mps":mp
        })
    except Exception as e:
        print(f"更新公众号文章: {str(e)}",e)
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message=f"更新公众号文章{str(e)}"
            )
        )

@router.get("/{mp_id}", summary="获取公众号详情")
async def get_mp(
    mp_id: str,
    # current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        mp = session.query(Feed).filter(Feed.id == mp_id).first()
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40401,
                    message="公众号不存在"
                )
            )
        return success_response(mp)
    except Exception as e:
        print(f"获取公众号详情错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="获取公众号详情失败"
            )
        )
@router.post("/by_article", summary="通过文章链接获取公众号详情")
async def get_mp_by_article(
    url: str=Query(..., min_length=1),
    current_user: dict = Depends(get_current_user)
):
    try:
        info =await WXArticleFetcher().async_get_article_content(url)
        
        if not info:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40401,
                    message="公众号不存在"
                )
            )
        return success_response(info)
    except Exception as e:
        print(f"获取公众号详情错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="请输入正确的公众号文章链接"
            )
        )

@router.post("", summary="添加公众号")
async def add_mp(
    mp_name: str = Body(..., min_length=1, max_length=255),
    mp_cover: str = Body(None, max_length=255),
    mp_id: str = Body(..., min_length=1, max_length=255),
    avatar: str = Body(None, max_length=500),
    mp_intro: str = Body(None, max_length=255),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        import time
        now = datetime.now()
        user_id = _uid(current_user)
        
        biz = _normalize_fakeid(mp_id)
        numeric_id = _extract_numeric_id(mp_id)
        if not biz or not numeric_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    code=40001,
                    message="mp_id必须为fakeid数字或文章链接中的__biz(base64)",
                ),
            )
        saved_avatar = save_avatar_locally(avatar) if avatar else None
        local_avatar_path = saved_avatar or mp_cover or ""
        
        # 检查公众号是否已存在
        feed_id = f"MP_WXS_{numeric_id}"
        existing_feed = session.query(Feed).filter((Feed.id == feed_id) | (Feed.faker_id == biz)).first()
        
        if existing_feed:
            # 更新现有记录
            existing_feed.mp_name = mp_name
            existing_feed.mp_cover = local_avatar_path
            existing_feed.mp_intro = mp_intro
            existing_feed.updated_at = now
            if not existing_feed.created_at:
                existing_feed.created_at = now
            existing_feed.faker_id = biz
        else:
            # 创建新的Feed记录
            new_feed = Feed(
                id=feed_id,
                mp_name=mp_name,
                mp_cover= local_avatar_path,
                mp_intro=mp_intro,
                status=1,  # 默认启用状态
                created_at=now,
                updated_at=now,
                faker_id=biz,
                update_time=0,
                sync_time=0,
            )
            session.add(new_feed)
           
        session.commit()
        
        feed = existing_feed if existing_feed else new_feed

        # Ensure current user is subscribed to this feed (方案1)
        try:
            sub = (
                session.query(UserSubscription)
                .filter(UserSubscription.user_id == user_id)
                .filter(UserSubscription.feed_id == feed.id)
                .first()
            )
            if not sub:
                session.add(UserSubscription(user_id=user_id, feed_id=feed.id, created_at=now, updated_at=now))
                session.commit()
        except Exception:
            session.rollback()
        # Persist into plaza (community) so "订阅广场" can grow over time.
        try:
            _plaza_upsert_item(
                {
                    "name": feed.mp_name or mp_name,
                    "kw": feed.mp_name or mp_name,
                    "desc": feed.mp_intro or mp_intro or "",
                    "tags": ["用户添加"],
                    "mp_id": feed.faker_id or biz,
                    "feed_id": feed.id,
                    "cover": feed.mp_cover or local_avatar_path or "",
                    "updated_at": now.isoformat(),
                }
            )
        except Exception:
            pass
         #在这里实现第一次添加获取公众号文章
        if not existing_feed:
            from core.queue import TaskQueue
            from core.wx import WxGather
            from core.insights import InsightsService

            def _prewarm_new_feed(feed_id: str, days: int, max_pages: int, limit: int):
                session2 = DB.get_session()
                f = session2.query(Feed).filter(Feed.id == feed_id).first()
                if not f:
                    return
                fakeid = _normalize_fakeid(f.faker_id) or _normalize_fakeid(biz)
                if not fakeid:
                    return
                try:
                    wx = WxGather().Model()
                    wx.get_Articles(
                        faker_id=fakeid,
                        Mps_id=f.id,
                        Mps_title=f.mp_name or "",
                        CallBack=UpdateArticle,
                        start_page=0,
                        MaxPage=max_pages,
                        interval=int(cfg.get("sync_interval", 10)) if int(cfg.get("sync_interval", 10)) < 10 else 2,
                        Gather_Content=False,
                        since_days=days,
                    )
                except Exception:
                    pass
                try:
                    InsightsService().ensure_mp_recent_cached(f.id, days=days, limit=limit)
                except Exception:
                    pass

            if bool(cfg.get("insights.prewarm_on_add", True)):
                days = int(cfg.get("insights.prewarm_days", 3))
                max_pages = int(cfg.get("insights.prewarm_max_pages", 30))
                limit = int(cfg.get("insights.prewarm_limit", 120))
                TaskQueue.add_task(_prewarm_new_feed, feed.id, days, max_pages, limit)
            else:
                Max_page=int(cfg.get("max_page","2"))
                TaskQueue.add_task(WxGather().Model().get_Articles,faker_id=feed.faker_id,Mps_id=feed.id,CallBack=UpdateArticle,MaxPage=Max_page,Mps_title=mp_name)
            
        return success_response({
            "id": feed.id,
            "mp_name": feed.mp_name,
            "mp_cover": feed.mp_cover,
            "mp_intro": feed.mp_intro,
            "status": feed.status,
            "faker_id": feed.faker_id,
            "created_at": _safe_isoformat(feed.created_at)
        })
    except Exception as e:
        session.rollback()
        print(f"添加公众号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="添加公众号失败"
            )
        )


@router.post("/plaza/sync", summary="将已订阅公众号批量写入订阅广场(用户添加)")
async def sync_plaza_from_feeds(
    limit: int = Query(2000, ge=1, le=10000),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    from core.models.feed import Feed

    feeds = session.query(Feed).order_by(Feed.created_at.desc()).limit(limit).all()
    ok = 0
    now = datetime.now().isoformat()
    for f in feeds:
        try:
            _plaza_upsert_item(
                {
                    "name": f.mp_name or "",
                    "kw": f.mp_name or "",
                    "desc": f.mp_intro or "",
                    "tags": ["用户添加"],
                    "mp_id": f.faker_id or "",
                    "feed_id": f.id or "",
                    "cover": f.mp_cover or "",
                    "updated_at": now,
                }
            )
            ok += 1
        except Exception:
            continue
    return success_response({"synced": ok, "limit": limit})


@router.delete("/{mp_id}", summary="删除订阅号(管理员=删除公众号；普通用户=取消订阅)")
async def delete_mp(
    mp_id: str,
    hard: bool = Query(False, description="仅管理员：true=删除公众号本身；false=仅取消订阅"),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        user_id = _uid(current_user)

        if _can_manage_feeds(current_user) and hard:
            mp = session.query(Feed).filter(Feed.id == mp_id).first()
            if not mp:
                raise HTTPException(
                    status_code=status.HTTP_201_CREATED,
                    detail=error_response(code=40401, message="订阅号不存在"),
                )
            session.query(UserSubscription).filter(UserSubscription.feed_id == mp_id).delete(synchronize_session=False)
            session.delete(mp)
            session.commit()
            return success_response({"message": "订阅号删除成功", "id": mp_id})

        # default: unsubscribe only
        deleted = (
            session.query(UserSubscription)
            .filter(UserSubscription.user_id == user_id)
            .filter(UserSubscription.feed_id == mp_id)
            .delete(synchronize_session=False)
        )
        session.commit()
        return success_response({"message": "已取消订阅", "id": mp_id, "deleted": int(deleted or 0)})
    except Exception as e:
        session.rollback()
        print(f"删除订阅号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="删除订阅号失败"
            )
        )
