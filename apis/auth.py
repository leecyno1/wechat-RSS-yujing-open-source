from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime, timedelta
from core.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    pwd_context,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from .ver import API_VERSION
from .base import success_response, error_response
from driver.base import WX_API
from core.config import set_config, cfg
from pydantic import BaseModel, Field
from driver.token import set_token
from sqlalchemy import and_, or_
router = APIRouter(prefix=f"/auth", tags=["认证"])
from driver.success import Success
from driver.wx_api import get_qr_code #通过API登录
def ApiSuccess(data):
    if data != None:
            print("\n登录结果:")
            print(f"Token: {data['token']}")
            set_config("token",data['token'])
            cfg.reload()
    else:
            print("\n登录失败，请检查上述错误信息")
@router.get("/qr/code", summary="获取登录二维码")
async def get_qrcode(force: bool = False, current_user=Depends(get_current_user)):

    # force param reserved for future (driver handles expiry refresh automatically)
    code_url=WX_API.GetCode(Success)
    return success_response(code_url)


class ManualSession(BaseModel):
    token: str = Field(..., description="微信公众号平台 token")
    cookie: str = Field(..., description="微信公众号平台 Cookie 字符串")
    fingerprint: str | None = Field(None, description="可选 fingerprint")


@router.post("/session", summary="手动设置公众号平台会话(免扫码)")
async def set_manual_session(payload: ManualSession, current_user=Depends(get_current_user)):
    set_token(
        {
            "token": payload.token,
            "cookies_str": payload.cookie,
            "fingerprint": payload.fingerprint or "",
            "expiry": {},
        }
    )
    cfg.reload()
    return success_response({"ok": True})


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    email: str | None = Field(None, max_length=100)


def _split_csv(raw: str | None) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    return [x.strip() for x in text.split(",") if str(x).strip()]


def _platform_filter_expr(FeedModel, platform: str):
    p = str(platform or "").strip().lower()
    if p in ("wechat", "wx", "weixin"):
        return or_(
            FeedModel.source_platform == "wechat",
            and_(FeedModel.faker_id.isnot(None), FeedModel.faker_id != ""),
        )
    if p in ("rss", "rsshub"):
        return FeedModel.source_type == p
    return FeedModel.source_platform == p


def _auto_subscribe_defaults(session, user_id: str) -> int:
    """
    Auto subscribe starter pack for newly registered users.

    Controlled by:
    - auth.default_subscribe_enable
    - auth.default_subscribe_platforms
    - auth.default_subscribe_per_platform
    - auth.default_subscribe_feed_ids
    """
    if not bool(cfg.get("auth.default_subscribe_enable", False)):
        return 0

    from core.models.feed import Feed
    from core.models.user_subscription import UserSubscription

    direct_feed_ids = _split_csv(cfg.get("auth.default_subscribe_feed_ids", ""))
    platforms = _split_csv(
        cfg.get("auth.default_subscribe_platforms", "wechat,zhihu,xueqiu,toutiao,baijiahao,wsj,bbc")
    )
    try:
        per_platform = int(cfg.get("auth.default_subscribe_per_platform", 3) or 3)
    except Exception:
        per_platform = 3
    per_platform = max(1, min(30, per_platform))

    selected_feed_ids: list[str] = []

    if direct_feed_ids:
        rows = session.query(Feed.id).filter(Feed.id.in_(direct_feed_ids)).all()
        selected_feed_ids.extend([str(fid) for (fid,) in rows])

    for p in platforms:
        expr = _platform_filter_expr(Feed, p)
        rows = (
            session.query(Feed.id)
            .filter(expr)
            .order_by(Feed.update_time.desc(), Feed.sync_time.desc(), Feed.created_at.desc())
            .limit(per_platform)
            .all()
        )
        selected_feed_ids.extend([str(fid) for (fid,) in rows])

    # Keep order and deduplicate.
    dedup_ids = list(dict.fromkeys([x for x in selected_feed_ids if x]))
    if not dedup_ids:
        return 0

    existing = set(
        x
        for (x,) in session.query(UserSubscription.feed_id)
        .filter(UserSubscription.user_id == user_id)
        .filter(UserSubscription.feed_id.in_(dedup_ids))
        .all()
    )
    now = datetime.now()
    to_insert = [
        UserSubscription(user_id=user_id, feed_id=fid, created_at=now, updated_at=now)
        for fid in dedup_ids
        if fid not in existing
    ]
    if not to_insert:
        return 0
    session.bulk_save_objects(to_insert)
    session.commit()
    return len(to_insert)


@router.post("/register", summary="用户注册(公域可选开启)")
async def register(payload: RegisterRequest):
    if not bool(cfg.get("auth.allow_register", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response(code=40301, message="当前未开启注册（请在配置中设置 auth.allow_register=true）"),
        )

    session = None
    try:
        import uuid
        from core.models import User as DBUser
        import core.db as db

        session = db.DB.get_session()
        username = payload.username.strip()
        if not username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(code=40001, message="用户名不能为空"),
            )
        exists = session.query(DBUser).filter(DBUser.username == username).first()
        if exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(code=40002, message="用户名已存在"),
            )

        now = datetime.now()
        u = DBUser(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=pwd_context.hash(payload.password),
            email=(payload.email or "").strip(),
            role="user",
            permissions="[]",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(u)
        session.commit()
        default_subscribed = 0
        try:
            default_subscribed = _auto_subscribe_defaults(session, str(u.id))
        except Exception:
            session.rollback()
            default_subscribed = 0

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(data={"sub": u.username}, expires_delta=access_token_expires)
        return success_response(
            {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "default_subscribed": default_subscribed,
            }
        )
    finally:
        try:
            if session is not None:
                session.close()
        except Exception:
            pass
@router.get("/qr/image", summary="获取登录二维码图片")
async def qr_image(current_user=Depends(get_current_user)):
    return success_response(WX_API.GetHasCode())

@router.get("/qr/status",summary="获取扫描状态")
async def qr_status(current_user=Depends(get_current_user)):
    #  from driver.success import  getStatus
     return success_response({
          "login_status":WX_API.HasLogin(),
     })    
@router.get("/qr/over",summary="扫码完成")
async def qr_success(current_user=Depends(get_current_user)):
     return success_response(WX_API.Close())    
@router.post("/login", summary="用户登录")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response(
                code=40101,
                message="用户名或密码错误"
            )
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return success_response({
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    })


@router.post("/token",summary="获取Token")
async def getToken(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail=error_response(
                code=40101,
                message="用户名或密码错误"
            )
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/logout", summary="用户注销")
async def logout(current_user: dict = Depends(get_current_user)):
    return {"code": 0, "message": "注销成功"}

@router.post("/refresh", summary="刷新Token")
async def refresh_token(current_user: dict = Depends(get_current_user)):
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": current_user["username"]}, expires_delta=access_token_expires
    )
    return success_response({
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    })

@router.get("/verify", summary="验证Token有效性")
async def verify_token(current_user: dict = Depends(get_current_user)):
    """验证当前token是否有效"""
    return success_response({
        "is_valid": True,
        "username": current_user["username"],
        "expires_at": current_user.get("exp")
    })
