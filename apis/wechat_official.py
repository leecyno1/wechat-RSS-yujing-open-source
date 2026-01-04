from __future__ import annotations

import xml.etree.ElementTree as ET

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response, status as fast_status

from core.config import cfg
from core.db import DB
from core.digest import DigestService
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

    return Response(content="success")

