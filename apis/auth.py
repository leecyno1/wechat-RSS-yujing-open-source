from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime
import re
import secrets
from core.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    pwd_context,
    get_token_expiry_delta,
    get_token_expires_in_seconds,
)
from .ver import API_VERSION
from .base import success_response, error_response
from driver.base import WX_API
from core.config import set_config, cfg
from pydantic import BaseModel, Field
from driver.token import set_token
from sqlalchemy import and_, or_
from core.mailer import send_mail
from core.models.user_bind_code import UserBindCode
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
    email: str = Field(..., min_length=6, max_length=100)
    verify_code: str = Field(..., min_length=4, max_length=20)


class SendRegisterCodeRequest(BaseModel):
    email: str = Field(..., min_length=6, max_length=100)


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _normalize_email(raw: str | None) -> str:
    return str(raw or "").strip().lower()


def _require_valid_email(raw: str | None) -> str:
    email = _normalize_email(raw)
    if not email or not _EMAIL_RE.match(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40004, message="请输入有效邮箱地址"),
        )
    return email


def _gen_register_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def _send_register_email_code(*, email: str, code: str, ttl_minutes: int) -> None:
    subject = str(cfg.get("auth.register_email_subject", "大圣之怒订阅助手注册验证码") or "大圣之怒订阅助手注册验证码")
    text = (
        f"你的注册验证码是：{code}\n"
        f"有效期：{ttl_minutes} 分钟。\n"
        f"如非本人操作，请忽略此邮件。"
    )
    html = (
        "<div style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'>"
        "<h3 style='margin:0 0 12px;'>大圣之怒订阅助手</h3>"
        f"<p style='margin:0 0 8px;'>你的注册验证码是：</p>"
        f"<div style='font-size:28px;font-weight:700;letter-spacing:3px;margin:8px 0 12px;'>{code}</div>"
        f"<p style='margin:0;color:#6b7280;'>有效期 {ttl_minutes} 分钟。如非本人操作，请忽略此邮件。</p>"
        "</div>"
    )
    send_mail(to_email=email, subject=subject, text_body=text, html_body=html)


def _consume_register_code(session, *, email: str, verify_code: str, now: datetime) -> None:
    rec = (
        session.query(UserBindCode)
        .filter(UserBindCode.user_id == email)
        .filter(UserBindCode.purpose == "email_register")
        .filter(UserBindCode.status == 0)
        .order_by(UserBindCode.created_at.desc())
        .first()
    )
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40005, message="验证码不存在或已失效，请重新获取"),
        )
    if rec.expires_at and rec.expires_at <= now:
        rec.status = 9
        rec.updated_at = now
        session.add(rec)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40006, message="验证码已过期，请重新获取"),
        )
    if str(rec.code or "").strip() != str(verify_code or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40007, message="验证码错误"),
        )
    rec.status = 1
    rec.used_at = now
    rec.updated_at = now
    session.add(rec)
    session.commit()


@router.post("/register/email-code", summary="发送注册邮箱验证码")
async def send_register_email_code(payload: SendRegisterCodeRequest):
    if not bool(cfg.get("auth.allow_register", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response(code=40301, message="当前未开启注册（请在配置中设置 auth.allow_register=true）"),
        )

    session = None
    try:
        from core.models import User as DBUser
        import core.db as db
        from datetime import timedelta

        email = _require_valid_email(payload.email)
        session = db.DB.get_session()
        now = datetime.now()

        exists_user = session.query(DBUser).filter(DBUser.email == email).first()
        if exists_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(code=40008, message="该邮箱已注册"),
            )

        resend_seconds = max(10, min(600, int(cfg.get("auth.register_code_resend_seconds", 60) or 60)))
        latest = (
            session.query(UserBindCode)
            .filter(UserBindCode.user_id == email)
            .filter(UserBindCode.purpose == "email_register")
            .order_by(UserBindCode.created_at.desc())
            .first()
        )
        if latest and latest.status == 0 and latest.created_at:
            try:
                elapsed = int((now - latest.created_at).total_seconds())
            except Exception:
                elapsed = resend_seconds + 1
            if elapsed < resend_seconds:
                wait_seconds = resend_seconds - max(0, elapsed)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=error_response(code=42901, message=f"发送过于频繁，请 {wait_seconds} 秒后重试"),
                )

        # invalidate all pending for this email
        (
            session.query(UserBindCode)
            .filter(UserBindCode.user_id == email)
            .filter(UserBindCode.purpose == "email_register")
            .filter(UserBindCode.status == 0)
            .update({"status": 9, "updated_at": now}, synchronize_session=False)
        )
        session.commit()

        ttl_minutes = max(3, min(30, int(cfg.get("auth.register_code_ttl_minutes", 10) or 10)))
        expires_at = now + timedelta(minutes=ttl_minutes)

        code = ""
        for _ in range(30):
            candidate = _gen_register_code()
            exists = session.query(UserBindCode.id).filter(UserBindCode.code == candidate).first()
            if not exists:
                code = candidate
                break
        if not code:
            raise RuntimeError("验证码生成失败，请稍后重试")

        rec = UserBindCode(
            user_id=email,
            code=code,
            purpose="email_register",
            status=0,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        session.add(rec)
        session.commit()

        try:
            _send_register_email_code(email=email, code=code, ttl_minutes=ttl_minutes)
        except Exception:
            rec.status = 9
            rec.updated_at = datetime.now()
            session.add(rec)
            session.commit()
            raise
        return success_response({"ok": True, "ttl_minutes": ttl_minutes})
    except HTTPException:
        raise
    except Exception as e:
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50004, message=f"发送验证码失败: {str(e)}"),
        )
    finally:
        try:
            if session is not None:
                session.close()
        except Exception:
            pass


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


def _auto_subscribe_defaults(session, user_id: str, force: bool = False) -> int:
    """
    Auto subscribe starter pack for newly registered users.

    Controlled by:
    - auth.default_subscribe_enable
    - auth.default_subscribe_platforms
    - auth.default_subscribe_per_platform
    - auth.default_subscribe_feed_ids
    """
    if (not force) and (not bool(cfg.get("auth.default_subscribe_enable", False))):
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
        email = _require_valid_email(payload.email)
        verify_code = str(payload.verify_code or "").strip()
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

        exists_email = session.query(DBUser).filter(DBUser.email == email).first()
        if exists_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(code=40008, message="该邮箱已注册"),
            )

        now = datetime.now()
        _consume_register_code(session, email=email, verify_code=verify_code, now=now)
        u = DBUser(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=pwd_context.hash(payload.password),
            email=email,
            role="user",
            permissions="[]",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(u)
        session.commit()

        access_token = create_access_token(data={"sub": u.username}, expires_delta=get_token_expiry_delta())
        return success_response(
            {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": get_token_expires_in_seconds(),
                "default_subscribed": 0,
            }
        )
    finally:
        try:
            if session is not None:
                session.close()
        except Exception:
            pass


@router.post("/starter/import", summary="手动导入默认订阅包")
async def import_starter_pack(current_user: dict = Depends(get_current_user)):
    session = None
    try:
        user_id = ""
        try:
            user_id = str(current_user.get("original_user").id)
        except Exception:
            user_id = ""
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(code=40003, message="无法识别当前用户"),
            )

        import core.db as db
        session = db.DB.get_session()
        inserted = _auto_subscribe_defaults(session, user_id, force=True)
        return success_response({"inserted": int(inserted)})
    except HTTPException:
        raise
    except Exception as e:
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50003, message=f"导入默认订阅包失败: {str(e)}"),
        )
    finally:
        if session is not None:
            try:
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
    access_token = create_access_token(data={"sub": user.username}, expires_delta=get_token_expiry_delta())
    return success_response({
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": get_token_expires_in_seconds()
    })


@router.post("/token",summary="获取Token")
async def getToken(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response(
                code=40101,
                message="用户名或密码错误"
            )
        )
    access_token = create_access_token(data={"sub": user.username}, expires_delta=get_token_expiry_delta())
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": get_token_expires_in_seconds()
    }


@router.post("/logout", summary="用户注销")
async def logout(current_user: dict = Depends(get_current_user)):
    return {"code": 0, "message": "注销成功"}

@router.post("/refresh", summary="刷新Token")
async def refresh_token(current_user: dict = Depends(get_current_user)):
    access_token = create_access_token(data={"sub": current_user["username"]}, expires_delta=get_token_expiry_delta())
    return success_response({
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": get_token_expires_in_seconds()
    })

@router.get("/verify", summary="验证Token有效性")
async def verify_token(current_user: dict = Depends(get_current_user)):
    """验证当前token是否有效"""
    return success_response({
        "is_valid": True,
        "username": current_user["username"],
        "expires_at": current_user.get("exp")
    })
