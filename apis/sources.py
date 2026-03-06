import json
import time
import uuid
from datetime import datetime
from hashlib import sha1
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func

from apis.base import error_response, success_response
from core.auth import get_current_user
from core.db import DB
from core.models.feed import Feed
from core.models.user_subscription import UserSubscription
from core.source.adapters import build_rsshub_feed_url, fetch_feed, normalize_source_key


router = APIRouter(prefix="/sources", tags=["多源订阅"])


PLATFORM_PRESETS = [
    {
        "platform": "wechat",
        "name": "微信公众号",
        "source_type": "rsshub",
        "rsshub_route_template": "/wechat/mp/:biz",
        "description": "RSSHub 微信公众号路由（填写公众号 __biz）",
    },
    {
        "platform": "zhihu",
        "name": "知乎",
        "source_type": "rsshub",
        "rsshub_route_template": "/zhihu/hotlist",
        "description": "知乎热榜（RSSHub）",
    },
    {
        "platform": "xueqiu",
        "name": "雪球",
        "source_type": "rsshub",
        "rsshub_route_template": "/xueqiu/user/:uid",
        "description": "雪球用户动态（RSSHub，替换 :uid）",
    },
    {
        "platform": "toutiao",
        "name": "头条",
        "source_type": "rsshub",
        "rsshub_route_template": "/toutiao/user/:id",
        "description": "今日头条用户动态（RSSHub，替换 :id）",
    },
    {
        "platform": "baijiahao",
        "name": "百家号",
        "source_type": "rsshub",
        "rsshub_route_template": "/baijiahao/author/:id",
        "description": "百家号作者动态（RSSHub，替换 :id）",
    },
    {
        "platform": "wsj",
        "name": "华尔街日报",
        "source_type": "rss",
        "source_url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
        "description": "WSJ World News RSS",
    },
    {
        "platform": "bbc",
        "name": "BBC",
        "source_type": "rss",
        "source_url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "description": "BBC World News RSS",
    },
]


def _normalize_platform(source_platform: str | None, source_type: str) -> str:
    raw = str(source_platform or "").strip().lower().replace(" ", "_")
    alias = {
        "weixin": "wechat",
        "wx": "wechat",
        "zhihu.com": "zhihu",
        "xq": "xueqiu",
        "toutiao.com": "toutiao",
        "baijia": "baijiahao",
        "wallstreetjournal": "wsj",
    }
    raw = alias.get(raw, raw)
    if not raw:
        return "rsshub" if str(source_type).strip().lower() == "rsshub" else "rss"
    # Keep schema simple and safe.
    return "".join([c for c in raw if c.isalnum() or c in ("_", "-")])[:32] or "rss"


def _uid(current_user: dict) -> str:
    try:
        return str(current_user.get("original_user").id)
    except Exception:
        return str(current_user.get("username") or "")


def _is_admin(current_user: dict) -> bool:
    try:
        return str(current_user.get("role") or "") == "admin" or str(current_user.get("username") or "") == "admin"
    except Exception:
        return False


def _ensure_source_url(source_type: str, source_url: str | None, rsshub_base_url: str | None, rsshub_route: str | None) -> str:
    st = str(source_type or "").strip().lower()
    if st == "rsshub":
        if source_url:
            return str(source_url).strip()
        return build_rsshub_feed_url(str(rsshub_base_url or ""), str(rsshub_route or ""))
    return str(source_url or "").strip()


class AddSourceFeedRequest(BaseModel):
    source_type: Literal["rss", "rsshub"] = Field("rss", description="来源类型")
    source_platform: Optional[str] = Field(None, description="平台标识: zhihu/xueqiu/toutiao/baijiahao/wsj/bbc...")
    source_url: Optional[str] = Field(None, description="RSS/Atom URL，rsshub可直接填完整URL")
    rsshub_base_url: Optional[str] = Field(None, description="RSSHub实例URL（配合 route）")
    rsshub_route: Optional[str] = Field(None, description="RSSHub路由路径")
    name: Optional[str] = Field(None, description="可选：自定义频道名称")
    auto_subscribe: bool = Field(True, description="创建后自动订阅当前用户")


@router.post("/feeds", summary="新增多源订阅(RSS/Atom/RSSHub)")
async def add_source_feed(payload: AddSourceFeedRequest, current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    now = datetime.now()
    try:
        source_platform = _normalize_platform(payload.source_platform, payload.source_type)
        source_url = _ensure_source_url(
            source_type=payload.source_type,
            source_url=payload.source_url,
            rsshub_base_url=payload.rsshub_base_url,
            rsshub_route=payload.rsshub_route,
        )
        if not source_url:
            return error_response(code=40001, message="source_url 不能为空")

        parsed = fetch_feed(source_url)
        source_key = normalize_source_key(payload.source_type, source_url)

        feed = session.query(Feed).filter(Feed.source_key == source_key).first()
        created = False
        if not feed:
            feed_id = f"SRC_{source_key[:16].upper()}"
            while session.query(func.count(Feed.id)).filter(Feed.id == feed_id).scalar():
                feed_id = f"SRC_{uuid.uuid4().hex[:16].upper()}"

            feed = Feed(
                id=feed_id,
                mp_name=(payload.name or parsed.get("feed_title") or source_url)[:255],
                mp_intro="",
                mp_cover="",
                status=1,
                sync_time=0,
                update_time=0,
                created_at=now,
                updated_at=now,
                faker_id="",
                source_type=payload.source_type,
                source_platform=source_platform,
                source_url=source_url,
                source_key=source_key,
                source_config=json.dumps(
                    {
                        "rsshub_base_url": (payload.rsshub_base_url or "").strip(),
                        "rsshub_route": (payload.rsshub_route or "").strip(),
                    },
                    ensure_ascii=False,
                ),
            )
            session.add(feed)
            session.commit()
            created = True
        else:
            feed.source_type = payload.source_type
            feed.source_platform = source_platform
            feed.source_url = source_url
            if payload.name:
                feed.mp_name = payload.name[:255]
            feed.updated_at = now
            session.add(feed)
            session.commit()

        if payload.auto_subscribe:
            user_id = _uid(current_user)
            exists = (
                session.query(func.count(UserSubscription.id))
                .filter(UserSubscription.user_id == user_id)
                .filter(UserSubscription.feed_id == feed.id)
                .scalar()
            )
            if not exists:
                session.add(UserSubscription(user_id=user_id, feed_id=feed.id, created_at=now, updated_at=now))
                session.commit()

        return success_response(
            {
                "created": created,
                "feed": {
                    "id": feed.id,
                    "name": feed.mp_name,
                    "source_type": feed.source_type,
                    "source_platform": feed.source_platform or "",
                    "source_url": feed.source_url,
                    "items_preview": int(len(parsed.get("items") or [])),
                },
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        return error_response(code=50001, message=f"新增来源失败: {str(e)}")


@router.get("/feeds", summary="获取当前用户可见的多源订阅")
async def list_source_feeds(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    source_platform: str = Query("", description="可选平台过滤"),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    try:
        base_q = session.query(Feed).filter(Feed.source_type.in_(["rss", "rsshub"]))
        if source_platform:
            base_q = base_q.filter(Feed.source_platform == str(source_platform).strip().lower())
        if not _is_admin(current_user):
            user_id = _uid(current_user)
            base_q = (
                base_q.join(UserSubscription, UserSubscription.feed_id == Feed.id)
                .filter(UserSubscription.user_id == user_id)
            )
        total = base_q.count()
        rows = base_q.order_by(Feed.updated_at.desc()).limit(limit).offset(offset).all()
        return success_response(
            {
                "list": [
                    {
                        "id": x.id,
                        "name": x.mp_name,
                        "source_type": x.source_type,
                        "source_platform": x.source_platform or "",
                        "source_url": x.source_url,
                        "updated_at": x.updated_at.isoformat() if x.updated_at else None,
                    }
                    for x in rows
                ],
                "total": total,
            }
        )
    except Exception as e:
        return error_response(code=50002, message=f"获取来源列表失败: {str(e)}")


def _refresh_feed_items(feed: Feed, parsed: dict, now: datetime, now_ts: int) -> tuple[int, int]:
    items = parsed.get("items") or []
    changed = 0

    for item in items:
        item_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or "").strip()
        desc = str(item.get("description") or "").strip()
        publish_time = int(item.get("publish_time") or now_ts)
        if not item_id:
            item_id = sha1(f"{feed.id}:{link or title}:{publish_time}".encode("utf-8")).hexdigest()
        ok = DB.add_article(
            {
                "id": item_id,
                "mp_id": feed.id,
                "title": title or link or item_id,
                "pic_url": "",
                "url": link,
                "description": desc,
                "publish_time": publish_time,
                "status": 1,
                "created_at": now,
                "updated_at": now,
            }
        )
        if ok:
            changed += 1

    feed.sync_time = now_ts
    feed.update_time = now_ts
    if parsed.get("feed_title"):
        feed.mp_name = str(parsed.get("feed_title"))[:255]
    feed.updated_at = now
    return len(items), changed


@router.post("/feeds/{feed_id}/refresh", summary="刷新多源订阅文章")
async def refresh_source_feed(feed_id: str, current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    now_ts = int(time.time())
    now = datetime.now()
    try:
        feed = session.query(Feed).filter(Feed.id == feed_id).first()
        if not feed:
            return error_response(code=40401, message="来源不存在")
        if str(feed.source_type or "").strip() not in ("rss", "rsshub"):
            return error_response(code=40003, message="仅支持刷新 rss/rsshub 来源")

        if not _is_admin(current_user):
            user_id = _uid(current_user)
            ok = (
                session.query(func.count(UserSubscription.id))
                .filter(UserSubscription.user_id == user_id)
                .filter(UserSubscription.feed_id == feed.id)
                .scalar()
            )
            if not ok:
                return error_response(code=40301, message="无权限刷新该来源")

        parsed = fetch_feed(str(feed.source_url or ""))
        total_items, changed = _refresh_feed_items(feed, parsed, now=now, now_ts=now_ts)
        session.add(feed)
        session.commit()

        return success_response({"feed_id": feed.id, "total_items": total_items, "changed": changed})
    except Exception as e:
        session.rollback()
        return error_response(code=50003, message=f"刷新来源失败: {str(e)}")


@router.get("/platform_presets", summary="获取多平台预置模板")
async def list_platform_presets():
    return success_response({"list": PLATFORM_PRESETS})


@router.post("/refresh_all", summary="刷新当前用户全部多源订阅")
async def refresh_all_source_feeds(
    limit: int = Query(300, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    now = datetime.now()
    now_ts = int(time.time())
    try:
        q = session.query(Feed).filter(Feed.source_type.in_(["rss", "rsshub"]))
        if not _is_admin(current_user):
            user_id = _uid(current_user)
            q = q.join(UserSubscription, UserSubscription.feed_id == Feed.id).filter(UserSubscription.user_id == user_id)
        feeds = q.order_by(Feed.updated_at.asc()).limit(limit).all()

        total_feeds = len(feeds)
        refreshed = 0
        total_items = 0
        changed_items = 0
        failures: list[dict] = []

        for feed in feeds:
            try:
                parsed = fetch_feed(str(feed.source_url or ""))
                c_total, c_changed = _refresh_feed_items(feed, parsed, now=now, now_ts=now_ts)
                session.add(feed)
                session.commit()
                refreshed += 1
                total_items += c_total
                changed_items += c_changed
            except Exception as e:
                session.rollback()
                failures.append({"feed_id": feed.id, "name": feed.mp_name or "", "error": str(e)})

        return success_response(
            {
                "total_feeds": total_feeds,
                "refreshed": refreshed,
                "failed": len(failures),
                "total_items": total_items,
                "changed_items": changed_items,
                "failures": failures[:20],
            }
        )
    except Exception as e:
        session.rollback()
        return error_response(code=50004, message=f"刷新全部来源失败: {str(e)}")
