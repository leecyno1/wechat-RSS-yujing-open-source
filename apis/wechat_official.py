from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response, status as fast_status

from core.config import cfg
from core.db import DB
from core.digest import DigestService
from core.log import logger
from core.models.user import User as DBUser
from core.models.user_bind_code import UserBindCode
from core.models.user_wechat_binding import UserWechatBinding
from core.wechat_official import WeChatCrypto, WeChatOfficialClient, verify_msg_signature, verify_signature


router = APIRouter(prefix="/wechat_official", tags=["WeChat Official"])


def _cfg_str(key: str) -> str:
    return str(cfg.get(key, "") or "").strip()


def _parse_xml(xml_text: str) -> dict[str, str]:
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return {}
    out: dict[str, str] = {}
    for child in list(root):
        out[str(child.tag)] = str(child.text or "")
    return out


def _crypto_or_none() -> WeChatCrypto | None:
    token = _cfg_str("wechat_official.token")
    aes_key = _cfg_str("wechat_official.encoding_aes_key")
    appid = _cfg_str("wechat_official.appid")
    if not token or not aes_key or not appid:
        return None
    try:
        return WeChatCrypto(token=token, encoding_aes_key=aes_key, appid=appid)
    except Exception:
        return None


def _menu_digest_key() -> str:
    return _cfg_str("wechat_official.menu.digest_key") or "DIGEST_TODAY"


def _send_text(openid: str, text: str) -> None:
    try:
        WeChatOfficialClient().send_custom_text(openid, text)
    except Exception:
        return


def _normalize_alnum_upper(raw: str) -> str:
    s = str(raw or "").strip().upper()
    return "".join([c for c in s if c.isalnum()])


def _extract_bind_code(content: str) -> str:
    prefix = str(cfg.get("binding.code_prefix", "LM") or "LM").strip().upper() or "LM"
    raw = _normalize_alnum_upper(content)
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


def _handle_text_bind(openid: str, content: str) -> None:
    openid_s = str(openid or "").strip()
    if not openid_s:
        return
    code = _extract_bind_code(content)
    if not code:
        return
    masked_code = code[:2] + "***" if len(code) > 2 else "***"
    logger.info("WeChatOfficial: bind attempt openid=%s code=%s", openid_s, masked_code)

    session = DB.get_session()
    now = datetime.now()
    try:
        rec = (
            session.query(UserBindCode)
            .filter(UserBindCode.code == code)
            .filter(UserBindCode.purpose == "wechat_follow_bind")
            .first()
        )
        if not rec:
            logger.info("WeChatOfficial: bind failed (code not found) openid=%s code=%s", openid_s, masked_code)
            _send_text(openid_s, "【Dr.Lemon订阅助手】绑定码不存在或已过期。\n请回到网站【信息-绑定】重新生成绑定码后再发送。")
            return

        status_v = int(getattr(rec, "status", 0) or 0)
        exp = getattr(rec, "expires_at", None)
        if status_v == 1:
            used_openid = str(getattr(rec, "used_openid", "") or "")
            if used_openid and used_openid != openid_s:
                logger.info("WeChatOfficial: bind failed (code used) openid=%s code=%s", openid_s, masked_code)
                _send_text(openid_s, "【Dr.Lemon订阅助手】该绑定码已被使用。\n请回到网站重新生成绑定码后再发送。")
                return
            binding = (
                session.query(UserWechatBinding)
                .filter(UserWechatBinding.user_id == rec.user_id)
                .filter(UserWechatBinding.is_active == 1)
                .first()
            )
            if binding:
                _send_text(openid_s, "【Dr.Lemon订阅助手】你已绑定成功。\n点击菜单【订阅推送】可获取今日精选+摘要。")
            else:
                _send_text(openid_s, "【Dr.Lemon订阅助手】绑定码已使用，但绑定记录异常。\n请回到网站重新生成绑定码后再发送。")
            return

        if exp and exp <= now:
            try:
                rec.status = 9
                rec.updated_at = now
                session.add(rec)
                session.commit()
            except Exception:
                session.rollback()
            logger.info("WeChatOfficial: bind failed (code expired) openid=%s code=%s", openid_s, masked_code)
            _send_text(openid_s, "【Dr.Lemon订阅助手】绑定码已过期。\n请回到网站【信息-绑定】重新生成绑定码后再发送。")
            return

        if status_v == 9:
            logger.info("WeChatOfficial: bind failed (code invalid) openid=%s code=%s", openid_s, masked_code)
            _send_text(openid_s, "【Dr.Lemon订阅助手】绑定码已失效。\n请回到网站【信息-绑定】重新生成绑定码后再发送。")
            return

        user_id = str(getattr(rec, "user_id", "") or "")
        user = session.query(DBUser).filter(DBUser.id == user_id).first()
        if not user:
            logger.info("WeChatOfficial: bind failed (user missing) openid=%s user_id=%s code=%s", openid_s, user_id, masked_code)
            _send_text(openid_s, "【Dr.Lemon订阅助手】绑定失败：绑定码对应用户不存在。\n请回到网站重新生成绑定码后再发送。")
            return

        # Prevent one openid binding to multiple users.
        by_openid = (
            session.query(UserWechatBinding)
            .filter(UserWechatBinding.wechat_openid == openid_s)
            .filter(UserWechatBinding.is_active == 1)
            .first()
        )
        if by_openid and str(by_openid.user_id) != user_id:
            logger.info("WeChatOfficial: bind failed (openid conflict) openid=%s user_id=%s", openid_s, user_id)
            _send_text(openid_s, "【Dr.Lemon订阅助手】该微信已绑定到其它站内账号。\n如需更换账号，请先在站内解绑或联系管理员。")
            return

        binding = session.query(UserWechatBinding).filter(UserWechatBinding.user_id == user_id).first()
        if binding:
            binding.wechat_openid = openid_s
            binding.is_active = 1
            binding.updated_at = now
            session.add(binding)
        else:
            binding = UserWechatBinding(
                user_id=user_id,
                wechat_openid=openid_s,
                wechat_unionid=None,
                is_active=1,
                created_at=now,
                updated_at=now,
            )
            session.add(binding)

        rec.status = 1
        rec.used_at = now
        rec.used_openid = openid_s
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
        logger.info("WeChatOfficial: bind success user_id=%s openid=%s", user_id, openid_s)
        _send_text(openid_s, f"【Dr.Lemon订阅助手】绑定成功！\n你已绑定站内账号：{user.username}\n点击菜单【订阅推送】可获取今日精选+摘要。")
    finally:
        try:
            session.close()
        except Exception:
            pass


def _handle_click_digest(openid: str) -> None:
    openid_s = str(openid or "").strip()
    if not openid_s:
        return

    session = DB.get_session()
    try:
        binding = (
            session.query(UserWechatBinding)
            .filter(UserWechatBinding.wechat_openid == openid_s)
            .filter(UserWechatBinding.is_active == 1)
            .first()
        )
        if not binding:
            _send_text(
                openid_s,
                "【Dr.Lemon订阅助手】\n你还未绑定站内账号。\n\n请先登录网站，在【信息-绑定】生成绑定码，然后把绑定码发给本公众号完成绑定。",
            )
            return

        user_id = str(getattr(binding, "user_id", "") or "")
        if not user_id:
            _send_text(openid_s, "【Dr.Lemon订阅助手】绑定信息异常，请重新绑定。")
            return

        svc = DigestService()
        digest = svc.build_user_digest(user_id, slot="daily")
        total = int(((digest.get("stats") or {}).get("total")) or 0)
        if total <= 0:
            _send_text(openid_s, "【Dr.Lemon订阅助手】今天暂无更新文章。")
            return

        text = str(((digest.get("message") or {}).get("text")) or "").strip()
        if not text:
            _send_text(openid_s, "【Dr.Lemon订阅助手】生成推送内容失败，请稍后再试。")
            return

        _send_text(openid_s, text)
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.get("/callback", summary="公众号回调校验")
async def wechat_official_verify(
    signature: str | None = Query(None),
    timestamp: str | None = Query(None),
    nonce: str | None = Query(None),
    echostr: str | None = Query(None),
    encrypt_type: str | None = Query(None),
    msg_signature: str | None = Query(None),
):
    token = _cfg_str("wechat_official.token")
    if not token:
        raise HTTPException(status_code=fast_status.HTTP_503_SERVICE_UNAVAILABLE, detail="wechat_official.token is not set")

    ts = str(timestamp or "")
    nn = str(nonce or "")
    echo = str(echostr or "")

    if str(encrypt_type or "").lower() == "aes":
        crypto = _crypto_or_none()
        if not crypto:
            raise HTTPException(
                status_code=fast_status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="wechat_official.appid/encoding_aes_key not set (required for aes mode)",
            )
        if not verify_msg_signature(token=token, msg_signature=str(msg_signature or ""), timestamp=ts, nonce=nn, encrypted=echo):
            raise HTTPException(status_code=fast_status.HTTP_403_FORBIDDEN, detail="invalid msg_signature")
        plain = crypto.decrypt(echo)
        return Response(content=plain)

    if not verify_signature(token=token, signature=str(signature or ""), timestamp=ts, nonce=nn):
        raise HTTPException(status_code=fast_status.HTTP_403_FORBIDDEN, detail="invalid signature")
    return Response(content=echo)


@router.post("/callback", summary="公众号事件回调(菜单点击等)")
async def wechat_official_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    signature: str | None = Query(None),
    timestamp: str | None = Query(None),
    nonce: str | None = Query(None),
    encrypt_type: str | None = Query(None),
    msg_signature: str | None = Query(None),
):
    token = _cfg_str("wechat_official.token")
    if not token:
        raise HTTPException(status_code=fast_status.HTTP_503_SERVICE_UNAVAILABLE, detail="wechat_official.token is not set")

    ts = str(timestamp or "")
    nn = str(nonce or "")

    body = (await request.body()) or b""
    body_text = body.decode("utf-8", errors="ignore")

    msg: dict[str, str] = {}

    is_aes = str(encrypt_type or "").lower() == "aes" or "<Encrypt>" in body_text
    if is_aes:
        crypto = _crypto_or_none()
        if not crypto:
            raise HTTPException(
                status_code=fast_status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="wechat_official.appid/encoding_aes_key not set (required for aes mode)",
            )
        outer = _parse_xml(body_text)
        enc = str(outer.get("Encrypt") or "")
        if not enc:
            raise HTTPException(status_code=fast_status.HTTP_400_BAD_REQUEST, detail="missing Encrypt")
        if not verify_msg_signature(token=token, msg_signature=str(msg_signature or ""), timestamp=ts, nonce=nn, encrypted=enc):
            raise HTTPException(status_code=fast_status.HTTP_403_FORBIDDEN, detail="invalid msg_signature")
        plain_xml = crypto.decrypt(enc)
        msg = _parse_xml(plain_xml)
    else:
        if not verify_signature(token=token, signature=str(signature or ""), timestamp=ts, nonce=nn):
            raise HTTPException(status_code=fast_status.HTTP_403_FORBIDDEN, detail="invalid signature")
        msg = _parse_xml(body_text)

    msg_type = str(msg.get("MsgType") or "").strip().lower()
    if msg_type == "event":
        event = str(msg.get("Event") or "").strip().upper()
        if event == "CLICK":
            event_key = str(msg.get("EventKey") or "").strip()
            if event_key == _menu_digest_key():
                openid = str(msg.get("FromUserName") or "").strip()
                background_tasks.add_task(_handle_click_digest, openid)
    elif msg_type == "text":
        openid = str(msg.get("FromUserName") or "").strip()
        content = str(msg.get("Content") or "").strip()
        if openid and content:
            background_tasks.add_task(_handle_text_bind, openid, content)

    return Response(content="success")
