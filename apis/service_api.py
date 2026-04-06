import json
import re
import hmac
import hashlib
import threading
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status as fast_status
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_

from apis.base import error_response, success_response, format_search_kw
from core.config import cfg
from core.db import DB
from core.digest import DigestService, generate_digest_outbox
from core.insights import InsightsService
from core.models.article import Article, ArticleBase
from core.models.article_insight import ArticleInsight
from core.models.base import DATA_STATUS
from core.models.feed import Feed
from core.models.user import User as DBUser
from core.models.user_bind_code import UserBindCode
from core.models.user_message_outbox import UserMessageOutbox
from core.models.user_subscription import UserSubscription
from core.models.user_wechat_binding import UserWechatBinding
from core.queue import InsightsQueue
from core.wechat_official import WeChatOfficialClient
from core.insights.extract import html_to_text
from core.print import print_warning, print_info


router = APIRouter(prefix="/service", tags=["Service API"])


_RL_LOCK = threading.Lock()
_RL_BUCKET: dict[tuple[str, int], int] = {}


def _parse_api_keys(raw: str) -> set[str]:
    keys: set[str] = set()
    for part in (raw or "").split(","):
        k = (part or "").strip()
        if k:
            keys.add(k)
    return keys


def _api_key_fp(v: str) -> str:
    s = str(v or "")
    if not s:
        return ""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:10]


def _rate_limited(api_key: str) -> tuple[bool, int]:
    """返回 (是否限流, 当前分钟计数)。0 或负值配置表示关闭限流。"""
    try:
        limit = int(cfg.get("service.rate_limit_per_minute", 180) or 180)
    except Exception:
        limit = 180
    if limit <= 0:
        return False, 0
    minute_key = int(datetime.utcnow().timestamp() // 60)
    key = (str(api_key), minute_key)
    with _RL_LOCK:
        # 惰性清理历史分钟桶，避免字典无限增长
        stale = [k for k in _RL_BUCKET.keys() if k[1] < minute_key - 2]
        for k in stale:
            _RL_BUCKET.pop(k, None)
        cur = int(_RL_BUCKET.get(key, 0)) + 1
        _RL_BUCKET[key] = cur
    return cur > limit, cur


def require_service_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> str:
    raw = str(cfg.get("service.api_keys", "") or "")
    keys = _parse_api_keys(raw)
    if not keys:
        raise HTTPException(
            status_code=fast_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_response(code=50301, message="Service API is disabled (set SERVICE_API_KEYS)."),
        )
    ok = False
    if x_api_key:
        for key in keys:
            if hmac.compare_digest(str(x_api_key), str(key)):
                ok = True
                break
    if not ok:
        print_warning(f"[service_api] invalid api key from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(
            status_code=fast_status.HTTP_401_UNAUTHORIZED,
            detail=error_response(code=40111, message="Invalid X-API-Key."),
        )
    limited, count = _rate_limited(str(x_api_key))
    if limited:
        raise HTTPException(
            status_code=fast_status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error_response(code=42901, message="Rate limit exceeded for this API key."),
        )
    if bool(cfg.get("service.audit_log_enable", True)):
        print_info(
            f"[service_api] key={_api_key_fp(str(x_api_key))} ip={request.client.host if request.client else 'unknown'} "
            f"path={request.url.path} method={request.method} minute_count={count}"
        )
    return x_api_key


def _estimate_word_count(text: str) -> int:
    if not text:
        return 0
    t = re.sub(r"\s+", "", text)
    return len(t)


def _mask_openid(v: str) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    if len(s) <= 10:
        return s[:2] + "***"
    return s[:4] + "***" + s[-4:]


def _serialize_feed(feed: Feed) -> dict:
    source_type = str(feed.source_type or "wechat")
    source_platform = str(feed.source_platform or ("wechat" if (feed.faker_id or "").strip() else "rss"))
    return {
        "id": str(feed.id),
        "name": feed.mp_name or "",
        "cover": feed.mp_cover or "",
        "intro": feed.mp_intro or "",
        "source_type": source_type,
        "source_platform": source_platform,
        "source_url": feed.source_url or "",
        "created_at": str(getattr(feed, "created_at", "") or ""),
        "updated_at": str(getattr(feed, "updated_at", "") or ""),
    }


def _serialize_insight(insight: ArticleInsight, *, include_llm: bool) -> dict:
    return {
        "article_id": insight.article_id,
        "summary": insight.summary or "",
        "headings": json.loads(insight.headings_json) if insight.headings_json else [],
        "key_points": json.loads(insight.key_points_json) if getattr(insight, "key_points_json", None) else None,
        "llm_breakdown": json.loads(insight.llm_breakdown_json) if (include_llm and insight.llm_breakdown_json) else None,
        "status": insight.status,
        "error": insight.error or "",
        "llm_provider": insight.llm_provider or "",
        "llm_model": insight.llm_model or "",
        "updated_at": str(getattr(insight, "updated_at", "") or ""),
        "created_at": str(getattr(insight, "created_at", "") or ""),
    }


@router.get("/ping", summary="Service API 健康检查")
async def service_ping(_key: str = Depends(require_service_api_key)):
    return success_response({"ok": True})


@router.get("/channels", summary="频道列表(多平台)")
async def service_list_channels(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    _key: str = Depends(require_service_api_key),
):
    session = DB.get_session()
    q = session.query(Feed).filter(
        or_(
            and_(Feed.faker_id.isnot(None), Feed.faker_id != ""),
            Feed.source_type.in_(["rss", "rsshub"]),
        )
    )
    if kw:
        q = q.filter(Feed.mp_name.ilike(f"%{kw}%"))
    total = q.count()
    rows = q.order_by(Feed.created_at.desc()).limit(limit).offset(offset).all()
    return success_response({"list": [_serialize_feed(f) for f in rows], "total": total, "page": {"limit": limit, "offset": offset, "total": total}})


@router.get("/channels/{channel_id}/articles", summary="频道文章列表(按时间倒序)")
async def service_list_channel_articles(
    channel_id: str,
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str = Query(""),
    include_content: bool = Query(False),
    _key: str = Depends(require_service_api_key),
):
    session = DB.get_session()
    Art = Article if include_content else ArticleBase
    q = session.query(Art, Feed).join(Feed, Feed.id == Art.mp_id).filter(Art.status != DATA_STATUS.DELETED)
    if channel_id not in ("all", "", None):
        q = q.filter(Art.mp_id == channel_id)
    if search:
        q = q.filter(format_search_kw(search))
    total = q.count()
    rows = q.order_by(Art.publish_time.desc()).limit(limit).offset(offset).all()
    items = []
    for art, feed in rows:
        items.append(
            {
                "id": str(art.id),
                "title": art.title or "",
                "description": art.description or "",
                "publish_time": int(art.publish_time or 0),
                "mp_id": art.mp_id or "",
                "mp_name": feed.mp_name or "",
                "source_platform": str(feed.source_platform or ("wechat" if (feed.faker_id or "").strip() else "rss")),
                "pic_url": art.pic_url or "",
                "url": art.url or "",
                "content": art.content if include_content else None,
                "word_count": _estimate_word_count((art.description or "") if not include_content else (art.content or art.description or "")),
            }
        )
    channel = None
    if channel_id not in ("all", "", None):
        f = session.query(Feed).filter(Feed.id == channel_id).first()
        channel = _serialize_feed(f) if f else None
    return success_response({"channel": channel, "list": items, "total": total, "page": {"limit": limit, "offset": offset, "total": total}})


def _parse_key_points_json(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _article_preview_text(article: Article, preview_len: int = 220) -> str:
    desc = str(getattr(article, "description", "") or "").strip()
    if desc:
        return desc[:preview_len]
    content = str(getattr(article, "content", "") or "").strip()
    if content:
        txt = html_to_text(content)
        if txt:
            return txt[:preview_len]
    title = str(getattr(article, "title", "") or "").strip()
    return title[:preview_len]


@router.get("/subscriptions/articles", summary="外部Agent：读取用户已订阅源的最新文章(含预览/摘要/关键信息)")
async def service_list_subscribed_articles(
    user_id: str | None = Query(None, description="站内用户ID（与 wechat_openid 二选一）"),
    wechat_openid: str | None = Query(None, description="公众号 openid（与 user_id 二选一）"),
    scope: Literal["timeline", "per_feed_latest"] = Query("timeline", description="timeline=时间线；per_feed_latest=每个已订阅源最新一篇"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    preview_len: int = Query(220, ge=60, le=1000),
    include_content: bool = Query(False, description="是否返回正文HTML（默认 false）"),
    include_llm_breakdown: bool = Query(False, description="是否返回全文拆解JSON（体积较大）"),
    _key: str = Depends(require_service_api_key),
):
    session = DB.get_session()

    resolved_user_id = str(user_id or "").strip()
    openid = str(wechat_openid or "").strip()
    if not resolved_user_id and not openid:
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40001, message="user_id / wechat_openid 至少提供一个"),
        )

    if not resolved_user_id and openid:
        binding = (
            session.query(UserWechatBinding)
            .filter(UserWechatBinding.wechat_openid == openid)
            .filter(UserWechatBinding.is_active == 1)
            .first()
        )
        if not binding:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="未找到 openid 对应的有效绑定"),
            )
        resolved_user_id = str(binding.user_id)

    feed_ids = [
        str(x[0])
        for x in (
            session.query(UserSubscription.feed_id)
            .filter(UserSubscription.user_id == resolved_user_id)
            .all()
        )
        if str(x[0] or "").strip()
    ]
    if not feed_ids:
        return success_response(
            {
                "user_id": resolved_user_id,
                "wechat_openid": openid or "",
                "subscriptions_total": 0,
                "scope": scope,
                "list": [],
                "total": 0,
                "page": {"limit": limit, "offset": offset, "total": 0},
            }
        )

    if scope == "per_feed_latest":
        latest_sub = (
            session.query(
                Article.mp_id.label("mp_id"),
                func.max(Article.publish_time).label("max_publish_time"),
            )
            .filter(Article.mp_id.in_(feed_ids))
            .filter(Article.status != DATA_STATUS.DELETED)
            .group_by(Article.mp_id)
            .subquery()
        )
        q = (
            session.query(Article, Feed, ArticleInsight)
            .join(Feed, Feed.id == Article.mp_id)
            .outerjoin(ArticleInsight, ArticleInsight.article_id == Article.id)
            .join(
                latest_sub,
                and_(
                    latest_sub.c.mp_id == Article.mp_id,
                    latest_sub.c.max_publish_time == Article.publish_time,
                ),
            )
            .order_by(Article.publish_time.desc())
        )
        total = q.count()
        rows = q.limit(limit).offset(offset).all()
    else:
        q = (
            session.query(Article, Feed, ArticleInsight)
            .join(Feed, Feed.id == Article.mp_id)
            .outerjoin(ArticleInsight, ArticleInsight.article_id == Article.id)
            .filter(Article.mp_id.in_(feed_ids))
            .filter(Article.status != DATA_STATUS.DELETED)
        )
        total = q.count()
        rows = q.order_by(Article.publish_time.desc()).limit(limit).offset(offset).all()

    items = []
    for art, feed, ins in rows:
        key_points = _parse_key_points_json(getattr(ins, "key_points_json", None)) if ins else None
        llm_breakdown = None
        if include_llm_breakdown and ins and getattr(ins, "llm_breakdown_json", None):
            try:
                llm_breakdown = json.loads(ins.llm_breakdown_json)
            except Exception:
                llm_breakdown = None
        items.append(
            {
                "id": str(art.id),
                "title": str(art.title or ""),
                "publish_time": int(art.publish_time or 0),
                "url": str(art.url or ""),
                "pic_url": str(art.pic_url or ""),
                "feed": {
                    "id": str(feed.id),
                    "name": str(feed.mp_name or ""),
                    "source_platform": str(feed.source_platform or ("wechat" if (feed.faker_id or "").strip() else "rss")),
                    "source_type": str(feed.source_type or "wechat"),
                    "cover": str(feed.mp_cover or ""),
                },
                "text_preview": _article_preview_text(art, preview_len=preview_len),
                "summary": str((getattr(ins, "summary", "") if ins else "") or ""),
                "key_points": key_points,
                "llm_breakdown": llm_breakdown,
                "content": str(art.content or "") if include_content else None,
            }
        )

    return success_response(
        {
            "user_id": resolved_user_id,
            "wechat_openid": openid or "",
            "subscriptions_total": len(feed_ids),
            "scope": scope,
            "list": items,
            "total": total,
            "page": {"limit": limit, "offset": offset, "total": total},
        }
    )


@router.get("/articles/{article_id}", summary="文章详情(含洞察)")
async def service_get_article(
    article_id: str,
    include_content: bool = Query(True),
    include_llm: bool = Query(True),
    schedule_cache: bool = Query(True, description="缺失洞察时是否后台排队补齐"),
    _key: str = Depends(require_service_api_key),
):
    session = DB.get_session()
    art = session.query(Article).filter(Article.id == article_id).first()
    if not art or int(getattr(art, "status", 0) or 0) == int(DATA_STATUS.DELETED):
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="文章不存在"),
        )
    feed = session.query(Feed).filter(Feed.id == art.mp_id).first()
    service = InsightsService()
    insight = service.get_or_create_basic(article_id)
    if insight and schedule_cache:
        try:
            missing_kp = bool(cfg.get("insights.auto_key_points", True)) and not (getattr(insight, "key_points_json", None) or "")
            missing_bd = bool(cfg.get("insights.auto_llm_breakdown", False)) and include_llm and not (getattr(insight, "llm_breakdown_json", None) or "")
            if missing_kp or missing_bd:
                InsightsQueue.add_task(service.ensure_cached, article_id)
        except Exception:
            pass

    out = {
        "id": str(art.id),
        "title": art.title or "",
        "description": art.description or "",
        "publish_time": int(art.publish_time or 0),
        "mp_id": art.mp_id or "",
        "pic_url": art.pic_url or "",
        "url": art.url or "",
        "content": art.content if include_content else None,
        "feed": _serialize_feed(feed) if feed else None,
        "insights": _serialize_insight(insight, include_llm=include_llm) if insight else None,
    }
    return success_response(out)


class WechatBindingUpsertRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=255, description="站内用户ID（users.id）")
    wechat_openid: str = Field(..., min_length=1, max_length=255, description="机器人侧识别ID（openid/uid等）")
    wechat_unionid: str | None = Field(None, max_length=255)
    is_active: bool = Field(True, description="是否启用该绑定")


@router.post("/wechat/bindings", summary="写入/更新 用户<->公众号关注身份 绑定")
async def service_upsert_wechat_binding(payload: WechatBindingUpsertRequest, _key: str = Depends(require_service_api_key)):
    session = DB.get_session()
    user_id = payload.user_id.strip()
    openid = payload.wechat_openid.strip()
    if not user_id or not openid:
        raise HTTPException(status_code=fast_status.HTTP_400_BAD_REQUEST, detail=error_response(code=40001, message="user_id / wechat_openid 不能为空"))

    user = session.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=fast_status.HTTP_404_NOT_FOUND, detail=error_response(code=40401, message="用户不存在"))

    # Prevent one openid binding to multiple users.
    by_openid = session.query(UserWechatBinding).filter(UserWechatBinding.wechat_openid == openid).first()
    if by_openid and str(by_openid.user_id) != user_id:
        raise HTTPException(
            status_code=fast_status.HTTP_409_CONFLICT,
            detail=error_response(code=40901, message="该 wechat_openid 已绑定到其它用户"),
        )

    now = datetime.now()
    binding = session.query(UserWechatBinding).filter(UserWechatBinding.user_id == user_id).first()
    if binding:
        binding.wechat_openid = openid
        binding.wechat_unionid = (payload.wechat_unionid or "").strip() or None
        binding.is_active = 1 if payload.is_active else 0
        binding.updated_at = now
        session.add(binding)
    else:
        binding = UserWechatBinding(
            user_id=user_id,
            wechat_openid=openid,
            wechat_unionid=(payload.wechat_unionid or "").strip() or None,
            is_active=1 if payload.is_active else 0,
            created_at=now,
            updated_at=now,
        )
        session.add(binding)

    session.commit()
    return success_response(
        {
            "user_id": binding.user_id,
            "wechat_openid": binding.wechat_openid,
            "wechat_unionid": binding.wechat_unionid or "",
            "is_active": bool(int(getattr(binding, "is_active", 0) or 0)),
            "updated_at": str(getattr(binding, "updated_at", "") or ""),
            "created_at": str(getattr(binding, "created_at", "") or ""),
        }
    )


class WechatConsumeBindCodeRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=32, description="站内生成的绑定码（用户发给公众号）")
    wechat_openid: str = Field(..., min_length=1, max_length=255, description="机器人侧识别ID（openid/uid等）")
    wechat_unionid: str | None = Field(None, max_length=255)


def _normalize_bind_code(raw: str) -> str:
    s = str(raw or "").strip().upper()
    s = "".join([c for c in s if c.isalnum()])  # remove spaces/dashes
    return s


@router.post("/wechat/bindings/consume_code", summary="机器人：用绑定码完成 user_id <-> openid 绑定")
async def service_consume_bind_code(payload: WechatConsumeBindCodeRequest, _key: str = Depends(require_service_api_key)):
    session = DB.get_session()
    now = datetime.now()

    code = _normalize_bind_code(payload.code)
    openid = payload.wechat_openid.strip()
    if not code or not openid:
        raise HTTPException(status_code=fast_status.HTTP_400_BAD_REQUEST, detail=error_response(code=40001, message="code / wechat_openid 不能为空"))

    rec = session.query(UserBindCode).filter(UserBindCode.code == code).filter(UserBindCode.purpose == "wechat_follow_bind").first()
    if not rec:
        raise HTTPException(status_code=fast_status.HTTP_404_NOT_FOUND, detail=error_response(code=40401, message="绑定码不存在"))

    status_v = int(getattr(rec, "status", 0) or 0)
    exp = getattr(rec, "expires_at", None)
    if status_v == 1:
        # Idempotent: same openid ok; different openid -> conflict.
        used_openid = str(getattr(rec, "used_openid", "") or "")
        if used_openid and used_openid != openid:
            raise HTTPException(status_code=fast_status.HTTP_409_CONFLICT, detail=error_response(code=40902, message="绑定码已被使用"))
        binding = session.query(UserWechatBinding).filter(UserWechatBinding.user_id == rec.user_id).filter(UserWechatBinding.is_active == 1).first()
        return success_response({"ok": True, "user_id": str(rec.user_id), "wechat_openid": openid, "is_bound": bool(binding), "code": code, "already_used": True})

    if exp and exp <= now:
        try:
            rec.status = 9
            rec.updated_at = now
            session.add(rec)
            session.commit()
        except Exception:
            session.rollback()
        raise HTTPException(status_code=fast_status.HTTP_410_GONE, detail=error_response(code=41001, message="绑定码已过期，请重新生成"))

    if status_v == 9:
        raise HTTPException(status_code=fast_status.HTTP_410_GONE, detail=error_response(code=41001, message="绑定码已失效，请重新生成"))

    user_id = str(rec.user_id)
    user = session.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=fast_status.HTTP_404_NOT_FOUND, detail=error_response(code=40402, message="绑定码对应用户不存在"))

    # Prevent one openid binding to multiple users.
    by_openid = session.query(UserWechatBinding).filter(UserWechatBinding.wechat_openid == openid).filter(UserWechatBinding.is_active == 1).first()
    if by_openid and str(by_openid.user_id) != user_id:
        raise HTTPException(status_code=fast_status.HTTP_409_CONFLICT, detail=error_response(code=40901, message="该 wechat_openid 已绑定到其它用户"))

    binding = session.query(UserWechatBinding).filter(UserWechatBinding.user_id == user_id).first()
    if binding:
        binding.wechat_openid = openid
        binding.wechat_unionid = (payload.wechat_unionid or "").strip() or None
        binding.is_active = 1
        binding.updated_at = now
        session.add(binding)
    else:
        binding = UserWechatBinding(
            user_id=user_id,
            wechat_openid=openid,
            wechat_unionid=(payload.wechat_unionid or "").strip() or None,
            is_active=1,
            created_at=now,
            updated_at=now,
        )
        session.add(binding)

    # Mark code used and invalidate other pending codes for this user.
    rec.status = 1
    rec.used_at = now
    rec.used_openid = openid
    rec.updated_at = now
    session.add(rec)

    try:
        others = (
            session.query(UserBindCode)
            .filter(UserBindCode.user_id == user_id)
            .filter(UserBindCode.purpose == "wechat_follow_bind")
            .filter(UserBindCode.status == 0)
            .filter(UserBindCode.id != rec.id)
            .all()
        )
        for c in others:
            c.status = 9
            c.updated_at = now
            session.add(c)
    except Exception:
        pass

    session.commit()
    return success_response({"ok": True, "user_id": user_id, "wechat_openid": openid, "code": code, "is_bound": True, "already_used": False})


@router.get("/wechat/bindings", summary="查看已绑定列表")
async def service_list_wechat_bindings(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    only_active: bool = Query(True),
    _key: str = Depends(require_service_api_key),
):
    session = DB.get_session()
    q = session.query(UserWechatBinding)
    if only_active:
        q = q.filter(UserWechatBinding.is_active == 1)
    total = q.count()
    rows = q.order_by(UserWechatBinding.updated_at.desc()).limit(limit).offset(offset).all()
    items = []
    for b in rows:
        items.append(
            {
                "user_id": str(b.user_id),
                "wechat_openid": str(b.wechat_openid),
                "wechat_unionid": str(getattr(b, "wechat_unionid", "") or ""),
                "is_active": bool(int(getattr(b, "is_active", 0) or 0)),
                "updated_at": str(getattr(b, "updated_at", "") or ""),
                "created_at": str(getattr(b, "created_at", "") or ""),
            }
        )
    return success_response({"list": items, "total": total, "page": {"limit": limit, "offset": offset, "total": total}})


@router.get("/digests/preview", summary="预览某用户的合集/推送消息")
async def service_preview_digest(
    user_id: str = Query(..., min_length=1),
    date: str | None = Query(None, description="YYYY-MM-DD；为空表示今天"),
    slot: str = Query("daily", description="daily|morning|afternoon|evening"),
    _key: str = Depends(require_service_api_key),
):
    svc = DigestService()
    digest = svc.build_user_digest(user_id.strip(), digest_date=date, slot=slot)
    return success_response(digest)


class DigestOutboxGenerateResult(BaseModel):
    date: str
    slot: str
    channel: str
    total_users: int
    created: int
    skipped_exists: int
    skipped_empty: int
    skipped_unbound: int


@router.post("/digests/outbox/generate", summary="生成待推送消息(outbox)供机器人拉取")
async def service_generate_digest_outbox(
    date: str | None = Query(None, description="YYYY-MM-DD；为空表示今天"),
    slot: str = Query("daily", description="daily|morning|afternoon|evening"),
    channel: str = Query("wechat", description="机器人通道标识，如 wechat"),
    only_bound: bool = Query(True, description="只生成已绑定微信身份的用户"),
    _key: str = Depends(require_service_api_key),
):
    res = generate_digest_outbox(digest_date=date, slot=slot, channel=channel, only_bound=only_bound)
    return success_response(DigestOutboxGenerateResult(**res).model_dump())


def _parse_payload_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


@router.get("/digests/outbox/pending", summary="机器人拉取待发送消息")
async def service_list_pending_outbox(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    channel: str = Query("wechat"),
    date: str | None = Query(None),
    slot: str | None = Query(None),
    _key: str = Depends(require_service_api_key),
):
    session = DB.get_session()
    channel_s = (channel or "wechat").strip() or "wechat"

    q = (
        session.query(UserMessageOutbox, UserWechatBinding)
        .outerjoin(UserWechatBinding, and_(UserWechatBinding.user_id == UserMessageOutbox.user_id, UserWechatBinding.is_active == 1))
        .filter(UserMessageOutbox.channel == channel_s)
        .filter(UserMessageOutbox.message_type == "daily_digest")
        .filter(UserMessageOutbox.status == 0)
    )
    if date:
        q = q.filter(UserMessageOutbox.digest_date == str(date).strip())
    if slot:
        q = q.filter(UserMessageOutbox.digest_slot == str(slot).strip())

    total = q.count()
    rows = q.order_by(UserMessageOutbox.created_at.asc()).limit(limit).offset(offset).all()
    items = []
    for ob, b in rows:
        items.append(
            {
                "id": str(ob.id),
                "user_id": str(ob.user_id),
                "wechat_openid": str(getattr(b, "wechat_openid", "") or "") if b else "",
                "channel": str(ob.channel),
                "message_type": str(ob.message_type),
                "digest_date": str(getattr(ob, "digest_date", "") or ""),
                "digest_slot": str(getattr(ob, "digest_slot", "") or ""),
                "message_text": str(ob.message_text or ""),
                "payload": _parse_payload_json(getattr(ob, "payload_json", None)),
                "created_at": str(getattr(ob, "created_at", "") or ""),
            }
        )
    return success_response({"list": items, "total": total, "page": {"limit": limit, "offset": offset, "total": total}})


class OutboxAckRequest(BaseModel):
    status: Literal["sent", "failed"] = Field(..., description="sent|failed")
    error: str | None = Field(None, description="失败原因(可选)")


@router.post("/digests/outbox/{outbox_id}/ack", summary="机器人回传发送结果(ack)")
async def service_ack_outbox(outbox_id: str, payload: OutboxAckRequest, _key: str = Depends(require_service_api_key)):
    session = DB.get_session()
    ob = session.query(UserMessageOutbox).filter(UserMessageOutbox.id == outbox_id).first()
    if not ob:
        raise HTTPException(status_code=fast_status.HTTP_404_NOT_FOUND, detail=error_response(code=40401, message="outbox 不存在"))

    now = datetime.now()
    if payload.status == "sent":
        ob.status = 1
        ob.sent_at = now
        ob.error = None
    else:
        ob.status = 9
        ob.error = (payload.error or "").strip() or "failed"
    ob.updated_at = now
    session.add(ob)
    session.commit()
    return success_response({"ok": True, "id": str(ob.id), "status": int(ob.status or 0)})


@router.post("/wechat_official/menu/setup", summary="设置公众号自定义菜单(订阅推送)")
async def service_setup_wechat_official_menu(
    name: str = Query("订阅推送", min_length=1, max_length=16),
    key: str | None = Query(None, max_length=128, description="菜单 EventKey（为空则用配置 wechat_official.menu.digest_key）"),
    _key: str = Depends(require_service_api_key),
):
    digest_key = (key or str(cfg.get("wechat_official.menu.digest_key", "") or "")).strip() or "DIGEST_TODAY"
    menu = {"button": [{"type": "click", "name": str(name).strip(), "key": digest_key}]}
    try:
        res = WeChatOfficialClient().create_menu(menu)
        return success_response({"ok": True, "menu": menu, "resp": res})
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"menu setup failed: {e}"),
        )


@router.post("/wechat_official/push/latest", summary="尝试推送最新文章链接给关注用户/绑定用户")
async def service_push_latest_article(
    audience: Literal["bindings", "followers"] = Query("bindings", description="bindings=站内已绑定用户；followers=公众号全部关注用户(openid 列表)"),
    limit: int = Query(1, ge=1, le=200, description="本次最多推送人数（默认 1 用于测试）"),
    dry_run: bool = Query(False, description="仅返回收件人列表（脱敏），不实际发送"),
    openid: str | None = Query(None, description="仅向指定 openid 发送（用于测试）"),
    _key: str = Depends(require_service_api_key),
):
    session = DB.get_session()
    try:
        art = (
            session.query(Article)
            .filter(Article.status != DATA_STATUS.DELETED)
            .filter(Article.url.isnot(None))
            .filter(Article.url != "")
            .order_by(Article.publish_time.desc())
            .first()
        )
        if not art:
            raise HTTPException(status_code=fast_status.HTTP_404_NOT_FOUND, detail=error_response(code=40401, message="没有可推送的文章"))

        article_id = str(getattr(art, "id", "") or "")
        title = str(getattr(art, "title", "") or "").strip()
        url = str(getattr(art, "url", "") or "").strip()
        if not url:
            raise HTTPException(status_code=fast_status.HTTP_404_NOT_FOUND, detail=error_response(code=40402, message="最新文章缺少 url"))

        text = f"【大圣之怒订阅助手】最新文章\n{title}\n{url}".strip()

        recipients: list[str] = []
        if openid and str(openid).strip():
            recipients = [str(openid).strip()]
        elif audience == "bindings":
            rows = session.query(UserWechatBinding).filter(UserWechatBinding.is_active == 1).all()
            for r in rows:
                oid = str(getattr(r, "wechat_openid", "") or "").strip()
                if oid:
                    recipients.append(oid)
        else:
            # followers: fetch openids via WeChat API (may require permissions / IP whitelist).
            try:
                client = WeChatOfficialClient()
                next_openid = ""
                seen: set[str] = set()
                while len(recipients) < limit:
                    data = client.list_followers(next_openid=next_openid)
                    batch = list(((data.get("data") or {}).get("openid")) or [])
                    for oid in batch:
                        s = str(oid or "").strip()
                        if not s or s in seen:
                            continue
                        seen.add(s)
                        recipients.append(s)
                        if len(recipients) >= limit:
                            break
                    next_openid = str(data.get("next_openid") or "").strip()
                    if not batch or not next_openid:
                        break
            except Exception as e:
                raise HTTPException(
                    status_code=fast_status.HTTP_502_BAD_GATEWAY,
                    detail=error_response(code=50201, message=f"wechat api failed: {e}"),
                )

        # de-dup + cap
        uniq: list[str] = []
        seen2: set[str] = set()
        for r in recipients:
            if r in seen2:
                continue
            seen2.add(r)
            uniq.append(r)
            if len(uniq) >= limit:
                break
        recipients = uniq

        if dry_run:
            return success_response(
                {
                    "article": {"id": article_id, "title": title, "url": url},
                    "audience": audience,
                    "limit": limit,
                    "recipients": [_mask_openid(x) for x in recipients],
                    "message_text": text,
                }
            )

        client = WeChatOfficialClient()
        results = []
        sent = 0
        failed = 0
        for r in recipients:
            try:
                client.send_custom_text(r, text)
                sent += 1
                results.append({"openid": _mask_openid(r), "ok": True})
            except Exception as e:
                failed += 1
                results.append({"openid": _mask_openid(r), "ok": False, "error": str(e)[:240]})

        return success_response(
            {
                "article": {"id": article_id, "title": title, "url": url},
                "audience": audience,
                "limit": limit,
                "sent": sent,
                "failed": failed,
                "results": results,
            }
        )
    finally:
        try:
            session.close()
        except Exception:
            pass
