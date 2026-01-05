from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status as fast_status

from apis.base import error_response
from core.config import cfg
from core.db import DB
from core.log import logger
from core.models.user import User as DBUser
from core.models.user_bind_code import UserBindCode
from core.models.user_wechat_binding import UserWechatBinding


router = APIRouter(prefix="/langbot", tags=["LangBot"])


def _cfg_str(key: str) -> str:
    return str(cfg.get(key, "") or "").strip()


def _require_token(token: str | None) -> None:
    expected = _cfg_str("langbot.webhook_token")
    if not expected:
        raise HTTPException(
            status_code=fast_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_response(code=50321, message="LangBot webhook is disabled (set LANGBOT_WEBHOOK_TOKEN)."),
        )
    if not token or token != expected:
        raise HTTPException(
            status_code=fast_status.HTTP_401_UNAUTHORIZED,
            detail=error_response(code=40121, message="Invalid webhook token."),
        )


def _normalize_bind_code(raw: str) -> str:
    s = str(raw or "").strip().upper()
    return "".join([c for c in s if c.isalnum()])


def _extract_text(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return "".join([_extract_text(x) for x in obj])
    if isinstance(obj, dict):
        if isinstance(obj.get("text"), str):
            return str(obj.get("text") or "")
        if isinstance(obj.get("content"), str):
            return str(obj.get("content") or "")
        for key in ("chain", "messages", "messageChain", "message_chain", "message"):
            if key in obj:
                return _extract_text(obj.get(key))
        if "data" in obj:
            return _extract_text(obj.get("data"))
        return ""
    return ""


def _extract_bind_code(content: str) -> str:
    prefix = str(cfg.get("binding.code_prefix", "LM") or "LM").strip().upper() or "LM"
    raw = _normalize_bind_code(content)
    if not raw or not prefix:
        return ""
    idx = raw.rfind(prefix)
    if idx < 0:
        return ""
    try:
        code_len = int(cfg.get("binding.code_len", 8) or 8)
    except Exception:
        code_len = 8
    code_len = max(len(prefix) + 4, min(32, code_len))
    return raw[idx : idx + code_len]


@router.post("/webhook", summary="LangBot Webhook: consume wechat bind code from messages")
async def langbot_webhook(
    request: Request,
    token: str | None = Query(None, description="Webhook token (LANGBOT_WEBHOOK_TOKEN)"),
):
    _require_token(token)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=fast_status.HTTP_400_BAD_REQUEST, detail=error_response(code=40021, message="Invalid JSON payload."))

    event_type = str((payload or {}).get("event_type") or "")
    if event_type != "bot.person_message":
        return {"ok": True, "skip_pipeline": False, "ignored": True, "event_type": event_type}

    data = (payload or {}).get("data") or {}
    sender = (data or {}).get("sender") or {}
    openid = str((sender or {}).get("id") or "").strip()
    message = (data or {}).get("message")
    text = _extract_text(message).strip()
    code = _extract_bind_code(text)
    if not (openid and code):
        return {"ok": True, "skip_pipeline": False, "handled": False, "reason": "no_bind_code"}

    now = datetime.now()
    session = DB.get_session()
    masked_code = (code[:2] + "***") if len(code) > 2 else "***"
    try:
        rec = (
            session.query(UserBindCode)
            .filter(UserBindCode.code == code)
            .filter(UserBindCode.purpose == "wechat_follow_bind")
            .first()
        )
        if not rec:
            logger.info("LangBot: bind failed (code not found) openid=%s code=%s", openid, masked_code)
            return {"ok": False, "skip_pipeline": True, "handled": True, "error": "code_not_found"}

        status_v = int(getattr(rec, "status", 0) or 0)
        exp = getattr(rec, "expires_at", None)
        if exp and exp <= now:
            try:
                rec.status = 9
                rec.updated_at = now
                session.add(rec)
                session.commit()
            except Exception:
                session.rollback()
            return {"ok": False, "skip_pipeline": True, "handled": True, "error": "code_expired"}

        if status_v == 9:
            return {"ok": False, "skip_pipeline": True, "handled": True, "error": "code_invalid"}

        user_id = str(getattr(rec, "user_id", "") or "")
        user = session.query(DBUser).filter(DBUser.id == user_id).first()
        if not user:
            return {"ok": False, "skip_pipeline": True, "handled": True, "error": "user_not_found"}

        if status_v == 1:
            used_openid = str(getattr(rec, "used_openid", "") or "")
            if used_openid and used_openid != openid:
                return {"ok": False, "skip_pipeline": True, "handled": True, "error": "code_already_used"}
            binding = (
                session.query(UserWechatBinding)
                .filter(UserWechatBinding.user_id == user_id)
                .filter(UserWechatBinding.is_active == 1)
                .first()
            )
            return {
                "ok": True,
                "skip_pipeline": True,
                "handled": True,
                "already_used": True,
                "user_id": user_id,
                "wechat_openid": openid,
                "is_bound": bool(binding),
            }

        # Prevent one openid binding to multiple users.
        by_openid = (
            session.query(UserWechatBinding)
            .filter(UserWechatBinding.wechat_openid == openid)
            .filter(UserWechatBinding.is_active == 1)
            .first()
        )
        if by_openid and str(by_openid.user_id) != user_id:
            return {"ok": False, "skip_pipeline": True, "handled": True, "error": "openid_conflict"}

        binding = session.query(UserWechatBinding).filter(UserWechatBinding.user_id == user_id).first()
        if binding:
            binding.wechat_openid = openid
            binding.is_active = 1
            binding.updated_at = now
            session.add(binding)
        else:
            binding = UserWechatBinding(
                user_id=user_id,
                wechat_openid=openid,
                wechat_unionid=None,
                is_active=1,
                created_at=now,
                updated_at=now,
            )
            session.add(binding)

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
        return {"ok": True, "skip_pipeline": True, "handled": True, "user_id": user_id, "wechat_openid": openid, "already_used": False}
    finally:
        try:
            session.close()
        except Exception:
            pass

