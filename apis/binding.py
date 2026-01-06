from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status as fast_status
from pydantic import BaseModel, Field

from apis.base import error_response, success_response
from core.auth import get_current_user
from core.config import cfg
from core.db import DB
from core.models.user_bind_code import UserBindCode
from core.models.user_wechat_binding import UserWechatBinding
from core.wechat_official import WeChatOfficialClient


router = APIRouter(prefix="/binding", tags=["绑定"])


def _uid(current_user: dict) -> str:
    try:
        return str(current_user.get("original_user").id)
    except Exception:
        return str(current_user.get("username") or "")


def _mask(v: str) -> str:
    s = str(v or "")
    if not s:
        return ""
    if len(s) <= 10:
        return s[:2] + "***"
    return s[:4] + "***" + s[-4:]


def _expire_stale_codes(session, user_id: str, now: datetime) -> None:
    try:
        stale = (
            session.query(UserBindCode)
            .filter(UserBindCode.user_id == user_id)
            .filter(UserBindCode.purpose == "wechat_follow_bind")
            .filter(UserBindCode.status == 0)
            .filter(UserBindCode.expires_at <= now)
            .all()
        )
        if not stale:
            return
        for c in stale:
            c.status = 9
            c.updated_at = now
            session.add(c)
        session.commit()
    except Exception:
        session.rollback()


def _get_active_code(session, user_id: str, now: datetime) -> UserBindCode | None:
    return (
        session.query(UserBindCode)
        .filter(UserBindCode.user_id == user_id)
        .filter(UserBindCode.purpose == "wechat_follow_bind")
        .filter(UserBindCode.status == 0)
        .filter(UserBindCode.expires_at > now)
        .order_by(UserBindCode.created_at.desc())
        .first()
    )


def _serialize_code(code: UserBindCode | None, now: datetime) -> dict | None:
    if not code:
        return None
    exp = getattr(code, "expires_at", None)
    expires_in = None
    try:
        if exp:
            expires_in = max(0, int((exp - now).total_seconds()))
    except Exception:
        expires_in = None
    return {
        "code": str(code.code),
        "expires_at": exp.isoformat() if exp else None,
        "expires_in": expires_in,
        "status": int(getattr(code, "status", 0) or 0),
    }


@router.get("/wechat", summary="获取公众号绑定状态 + 当前绑定码(如有)")
async def get_wechat_binding(current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    user_id = _uid(current_user)
    now = datetime.now()

    _expire_stale_codes(session, user_id, now)

    binding = session.query(UserWechatBinding).filter(UserWechatBinding.user_id == user_id).filter(UserWechatBinding.is_active == 1).first()
    active_code = _get_active_code(session, user_id, now)

    return success_response(
        {
            "user_id": user_id,
            "is_bound": bool(binding),
            "wechat_openid_masked": _mask(getattr(binding, "wechat_openid", "")) if binding else "",
            "wechat_unionid_masked": _mask(getattr(binding, "wechat_unionid", "")) if binding else "",
            "bind_code": _serialize_code(active_code, now),
        }
    )


class GenerateBindCodeRequest(BaseModel):
    force: bool = Field(False, description="是否强制重新生成(会失效旧码)")


@router.post("/wechat/code", summary="生成/获取 绑定码(用户发给公众号)")
async def create_wechat_bind_code(payload: GenerateBindCodeRequest, current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    user_id = _uid(current_user)
    now = datetime.now()

    _expire_stale_codes(session, user_id, now)

    if payload.force:
        try:
            rows = (
                session.query(UserBindCode)
                .filter(UserBindCode.user_id == user_id)
                .filter(UserBindCode.purpose == "wechat_follow_bind")
                .filter(UserBindCode.status == 0)
                .all()
            )
            for c in rows:
                c.status = 9
                c.updated_at = now
                session.add(c)
            session.commit()
        except Exception:
            session.rollback()

    existing = _get_active_code(session, user_id, now)
    if existing:
        return success_response(_serialize_code(existing, now))

    prefix = str(cfg.get("binding.code_prefix", "LM") or "LM").strip().upper() or "LM"
    code_len = int(cfg.get("binding.code_len", 8) or 8)
    code_len = max(len(prefix) + 4, min(20, code_len))
    suffix_len = max(4, code_len - len(prefix))

    ttl_minutes = int(cfg.get("binding.code_ttl_minutes", 60) or 60)
    ttl_minutes = max(5, min(24 * 60, ttl_minutes))
    expires_at = now + timedelta(minutes=ttl_minutes)

    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

    for _ in range(50):
        code = prefix + "".join(secrets.choice(alphabet) for _ in range(suffix_len))
        exists = session.query(UserBindCode.id).filter(UserBindCode.code == code).first()
        if exists:
            continue
        rec = UserBindCode(
            user_id=user_id,
            code=code,
            purpose="wechat_follow_bind",
            status=0,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        try:
            session.add(rec)
            session.commit()
            return success_response(_serialize_code(rec, now))
        except Exception:
            session.rollback()
            continue

    raise HTTPException(
        status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=error_response(code=50001, message="生成绑定码失败，请稍后重试"),
    )


@router.get("/wechat/qrcode", summary="生成/获取 绑定二维码（扫码关注即绑定）")
async def get_wechat_bind_qrcode(current_user: dict = Depends(get_current_user)):
    """Return WeChat Official Account QR code URL with scene_str=bind_code.

    User scans this QR to follow; the subscribe/scan callback will bind openid automatically.
    """
    session = DB.get_session()
    user_id = _uid(current_user)
    now = datetime.now()

    _expire_stale_codes(session, user_id, now)

    active_code = _get_active_code(session, user_id, now)
    if not active_code:
        # Generate a new active code (same logic as POST /wechat/code, but no request body).
        prefix = str(cfg.get("binding.code_prefix", "LM") or "LM").strip().upper() or "LM"
        code_len = int(cfg.get("binding.code_len", 8) or 8)
        code_len = max(len(prefix) + 4, min(20, code_len))
        suffix_len = max(4, code_len - len(prefix))

        ttl_minutes = int(cfg.get("binding.code_ttl_minutes", 60) or 60)
        ttl_minutes = max(5, min(24 * 60, ttl_minutes))
        expires_at = now + timedelta(minutes=ttl_minutes)

        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        for _ in range(50):
            code = prefix + "".join(secrets.choice(alphabet) for _ in range(suffix_len))
            exists = session.query(UserBindCode.id).filter(UserBindCode.code == code).first()
            if exists:
                continue
            rec = UserBindCode(
                user_id=user_id,
                code=code,
                purpose="wechat_follow_bind",
                status=0,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            try:
                session.add(rec)
                session.commit()
                active_code = rec
                break
            except Exception:
                session.rollback()
                continue

    if not active_code:
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message="生成绑定码失败，请稍后重试"),
        )

    try:
        exp = getattr(active_code, "expires_at", None)
        expires_in = 600
        if exp:
            expires_in = max(60, int((exp - now).total_seconds()))
    except Exception:
        expires_in = 600

    try:
        data = WeChatOfficialClient().create_qrcode_ticket(scene_str=str(active_code.code), expire_seconds=expires_in)
        ticket = str(data.get("ticket") or "").strip()
        if not ticket:
            raise RuntimeError("missing ticket")
        qrcode_url = WeChatOfficialClient().show_qrcode_url(ticket)
        return success_response({"bind_code": _serialize_code(active_code, now), "qrcode_url": qrcode_url, "expires_in": expires_in})
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_response(code=50311, message=f"公众号二维码生成失败：{e}"),
        )
