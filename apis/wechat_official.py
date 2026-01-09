from __future__ import annotations

import xml.etree.ElementTree as ET
import re
import time
from datetime import datetime
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response, status as fast_status
from sqlalchemy import func, or_

from core.config import cfg
from core.db import DB
from core.digest import DigestService
from core.log import logger
from core.models.article import Article
from core.models.feed import Feed
from core.models.user_subscription import UserSubscription
from core.models.user import User as DBUser
from core.models.user_bind_code import UserBindCode
from core.models.user_wechat_binding import UserWechatBinding
from core.wechat_official import WeChatCrypto, WeChatOfficialClient, verify_msg_signature, verify_signature


router = APIRouter(prefix="/wechat_official", tags=["WeChat Official"])
legacy_router = APIRouter(tags=["WeChat Official"], include_in_schema=False)


def _cfg_str(key: str) -> str:
    v = str(cfg.get(key, "") or "").strip()
    if v:
        return v
    env_map = {
        "wechat_official.appid": "WECHAT_OFFICIAL_APPID",
        "wechat_official.appsecret": "WECHAT_OFFICIAL_APPSECRET",
        "wechat_official.token": "WECHAT_OFFICIAL_TOKEN",
        "wechat_official.encoding_aes_key": "WECHAT_OFFICIAL_ENCODING_AES_KEY",
    }
    env_key = env_map.get(key)
    if not env_key:
        return ""
    return str(os.getenv(env_key, "") or "").strip()


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


def _mask_openid(v: str) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    if len(s) <= 10:
        return s[:2] + "***"
    return s[:4] + "***" + s[-4:]


def _send_text(openid: str, text: str) -> None:
    try:
        WeChatOfficialClient().send_custom_text(openid, text)
    except Exception as e:
        logger.warning("WeChatOfficial: send failed openid=%s err=%s", _mask_openid(openid), str(e))
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


def _consume_bind_code_reply(openid: str, content: str) -> str | None:
    openid_s = str(openid or "").strip()
    if not openid_s:
        return None
    code = _extract_bind_code(content)
    if not code:
        return None
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
            return "【Dr.Lemon订阅助手】绑定码不存在或已过期。\n请回到网站【信息-绑定】重新生成绑定码后再发送。"

        status_v = int(getattr(rec, "status", 0) or 0)
        exp = getattr(rec, "expires_at", None)
        if status_v == 1:
            used_openid = str(getattr(rec, "used_openid", "") or "")
            if used_openid and used_openid != openid_s:
                logger.info("WeChatOfficial: bind failed (code used) openid=%s code=%s", openid_s, masked_code)
                return "【Dr.Lemon订阅助手】该绑定码已被使用。\n请回到网站重新生成绑定码后再发送。"
            binding = (
                session.query(UserWechatBinding)
                .filter(UserWechatBinding.user_id == rec.user_id)
                .filter(UserWechatBinding.is_active == 1)
                .first()
            )
            if binding:
                return "【Dr.Lemon订阅助手】你已绑定成功。\n点击菜单【订阅推送】可获取今日精选+摘要。"
            else:
                return "【Dr.Lemon订阅助手】绑定码已使用，但绑定记录异常。\n请回到网站重新生成绑定码后再发送。"

        if exp and exp <= now:
            try:
                rec.status = 9
                rec.updated_at = now
                session.add(rec)
                session.commit()
            except Exception:
                session.rollback()
            logger.info("WeChatOfficial: bind failed (code expired) openid=%s code=%s", openid_s, masked_code)
            return "【Dr.Lemon订阅助手】绑定码已过期。\n请回到网站【信息-绑定】重新生成绑定码后再发送。"

        if status_v == 9:
            logger.info("WeChatOfficial: bind failed (code invalid) openid=%s code=%s", openid_s, masked_code)
            return "【Dr.Lemon订阅助手】绑定码已失效。\n请回到网站【信息-绑定】重新生成绑定码后再发送。"

        user_id = str(getattr(rec, "user_id", "") or "")
        user = session.query(DBUser).filter(DBUser.id == user_id).first()
        if not user:
            logger.info("WeChatOfficial: bind failed (user missing) openid=%s user_id=%s code=%s", openid_s, user_id, masked_code)
            return "【Dr.Lemon订阅助手】绑定失败：绑定码对应用户不存在。\n请回到网站重新生成绑定码后再发送。"

        # Prevent one openid binding to multiple users.
        by_openid = (
            session.query(UserWechatBinding)
            .filter(UserWechatBinding.wechat_openid == openid_s)
            .filter(UserWechatBinding.is_active == 1)
            .first()
        )
        if by_openid and str(by_openid.user_id) != user_id:
            logger.info("WeChatOfficial: bind failed (openid conflict) openid=%s user_id=%s", openid_s, user_id)
            return "【Dr.Lemon订阅助手】该微信已绑定到其它站内账号。\n如需更换账号，请先在站内解绑或联系管理员。"

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
        return f"【Dr.Lemon订阅助手】绑定成功！\n你已绑定站内账号：{user.username}\n点击菜单【订阅推送】可获取今日精选+摘要。"
    finally:
        try:
            session.close()
        except Exception:
            pass


def _handle_text_bind(openid: str, content: str) -> None:
    reply = _consume_bind_code_reply(openid, content)
    if reply:
        _send_text(str(openid or "").strip(), reply)


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


def _is_help_query(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return True
    sl = s.lower()
    if sl in ("help", "?", "？", "h", "帮助"):
        return True
    keys = ["绑定", "关注", "怎么用", "如何使用", "使用说明", "注册", "登录", "怎么登录", "如何绑定"]
    return any(k in s for k in keys)


def _is_latest_query(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    keys = ["最新", "今天", "今日", "刚刚", "近期", "最近", "新文章"]
    return any(k in s for k in keys)


def _is_hot_query(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    keys = ["热门", "最热", "爆款", "高赞", "点赞", "推荐", "热榜"]
    return any(k in s for k in keys)


def _clean_query(text: str) -> str:
    s = str(text or "").strip()
    s = re.sub(r"[\\s\\u3000]+", " ", s).strip()
    s = re.sub(r"^(推荐|找|搜索|查找|帮我找)[:：\\s]*", "", s).strip()
    return s


def _format_articles_message(*, title: str, items: list[dict], extra: str = "") -> str:
    lines: list[str] = [str(title or "").strip()]
    for i, it in enumerate(items, start=1):
        t = str(it.get("title") or "").strip()
        u = str(it.get("url") or "").strip()
        mp = str(it.get("mp") or "").strip()
        if mp:
            lines.append(f"{i}. {t}（{mp}）")
        else:
            lines.append(f"{i}. {t}")
        if u:
            lines.append(u)
    if extra:
        lines.append("")
        lines.append(str(extra))
    out = "\n".join([x for x in lines if x is not None]).strip()
    return out[:1800]


def _handle_text_query(openid: str, content: str) -> None:
    openid_s = str(openid or "").strip()
    text = str(content or "").strip()
    if not openid_s or not text:
        return

    qraw = _clean_query(text)

    if _is_help_query(qraw):
        _send_text(
            openid_s,
            "【Dr.Lemon订阅助手】关注与绑定方式：\n"
            "1）登录网站 → 点击右上角【关注柠檬博士】\n"
            "2）扫描弹窗里的【绑定二维码】关注（或已关注直接扫码）→ 自动绑定\n"
            "3）回到网站点【刷新绑定状态】确认\n\n"
            "备用方式：把网站显示的“绑定码”直接发给本公众号，也可完成绑定。\n"
            "绑定后：点击菜单【订阅推送】可获取今日精选+摘要。\n"
            "也可直接发关键词（如“AI”“芯片”“投资”），我会为你推荐相关文章。",
        )
        return

    session = DB.get_session()
    try:
        binding = (
            session.query(UserWechatBinding)
            .filter(UserWechatBinding.wechat_openid == openid_s)
            .filter(UserWechatBinding.is_active == 1)
            .first()
        )
        user_id = str(getattr(binding, "user_id", "") or "") if binding else ""

        feed_ids: list[str] = []
        if user_id:
            rows = session.query(UserSubscription.feed_id).filter(UserSubscription.user_id == user_id).all()
            feed_ids = [str(r[0] or "").strip() for r in rows if r and str(r[0] or "").strip()]

        base_q = (
            session.query(Article, Feed)
            .join(Feed, Feed.id == Article.mp_id)
            .filter(Article.status != 1000)
            .filter(Article.url.isnot(None))
            .filter(Article.url != "")
        )
        if feed_ids:
            base_q = base_q.filter(Article.mp_id.in_(feed_ids))

        limit = 5
        now_ts = int(time.time())
        hot_since = now_ts - 7 * 24 * 3600

        items: list[dict] = []

        if _is_latest_query(qraw):
            rows = base_q.order_by(func.coalesce(Article.publish_time, 0).desc()).limit(limit).all()
            for art, feed in rows:
                items.append({"title": art.title or "", "url": art.url or "", "mp": (feed.mp_name or "") if feed else ""})
            title = "【Dr.Lemon订阅助手】最新文章推荐"
        else:
            kw = qraw
            if _is_hot_query(qraw):
                kw = ""

            q = base_q
            if kw:
                like_kw = f"%{kw}%"
                q = q.filter(or_(Article.title.like(like_kw), Article.description.like(like_kw)))

            if _is_hot_query(qraw):
                q = q.filter(func.coalesce(Article.publish_time, 0) >= hot_since)
                q = q.order_by(
                    func.coalesce(Article.like_count, 0).desc(),
                    func.coalesce(Article.recommend_count, 0).desc(),
                    func.coalesce(Article.read_count, 0).desc(),
                    func.coalesce(Article.publish_time, 0).desc(),
                )
            else:
                q = q.order_by(
                    func.coalesce(Article.like_count, 0).desc(),
                    func.coalesce(Article.publish_time, 0).desc(),
                )

            rows = q.limit(limit).all()
            for art, feed in rows:
                items.append({"title": art.title or "", "url": art.url or "", "mp": (feed.mp_name or "") if feed else ""})

            if items:
                title = f"【Dr.Lemon订阅助手】为你推荐（{qraw}）"
            else:
                q2 = base_q.filter(func.coalesce(Article.publish_time, 0) >= hot_since).order_by(
                    func.coalesce(Article.like_count, 0).desc(),
                    func.coalesce(Article.publish_time, 0).desc(),
                )
                rows2 = q2.limit(limit).all()
                if not rows2:
                    rows2 = base_q.order_by(func.coalesce(Article.publish_time, 0).desc()).limit(limit).all()
                for art, feed in rows2:
                    items.append({"title": art.title or "", "url": art.url or "", "mp": (feed.mp_name or "") if feed else ""})
                title = "【Dr.Lemon订阅助手】没有找到匹配内容，给你一份近期推荐"

        extra = ""
        if not user_id:
            extra = "想要按你的订阅做个性化推荐：请先到网站点击【关注柠檬博士】扫码自动绑定。"
        elif not feed_ids:
            extra = "你还没有订阅任何公众号：先去网站添加订阅后，再发关键词我会更准。"

        _send_text(openid_s, _format_articles_message(title=title, items=items, extra=extra))
    finally:
        try:
            session.close()
        except Exception:
            pass


def _set_binding_active(openid: str, *, is_active: bool) -> bool:
    openid_s = str(openid or "").strip()
    if not openid_s:
        return False
    session = DB.get_session()
    now = datetime.now()
    try:
        binding = session.query(UserWechatBinding).filter(UserWechatBinding.wechat_openid == openid_s).first()
        if not binding:
            return False
        binding.is_active = 1 if is_active else 0
        binding.updated_at = now
        session.add(binding)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
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
        openid = str(msg.get("FromUserName") or "").strip()
        event_key = str(msg.get("EventKey") or "").strip()
        if event == "CLICK":
            if event_key == _menu_digest_key():
                background_tasks.add_task(_handle_click_digest, openid)
        elif event in ("SUBSCRIBE", "SCAN"):
            # Parameterized QRCode: SUBSCRIBE has EventKey "qrscene_xxx", SCAN has "xxx".
            # Use EventKey as content so _extract_bind_code can find the binding code.
            if openid and event_key:
                reply = _consume_bind_code_reply(openid, event_key)
                if reply:
                    background_tasks.add_task(_send_text, openid, reply)
            else:
                # If user re-subscribed but no scene, re-activate existing binding by openid.
                if event == "SUBSCRIBE" and openid:
                    if _set_binding_active(openid, is_active=True):
                        background_tasks.add_task(
                            _send_text,
                            openid,
                            "【Dr.Lemon订阅助手】欢迎回来！\n已恢复你的绑定状态。\n点击菜单【订阅推送】可获取今日精选+摘要。",
                        )
        elif event == "UNSUBSCRIBE":
            if openid:
                _set_binding_active(openid, is_active=False)
    elif msg_type == "text":
        openid = str(msg.get("FromUserName") or "").strip()
        content = str(msg.get("Content") or "").strip()
        if openid and content:
            reply = _consume_bind_code_reply(openid, content)
            if reply:
                background_tasks.add_task(_send_text, openid, reply)
            else:
                background_tasks.add_task(_handle_text_query, openid, content)

    return Response(content="success")


# Compatibility: some deployments already configured WeChat server callback as `/callback/command`.
@legacy_router.get("/callback/command")
async def legacy_wechat_official_verify(
    signature: str | None = Query(None),
    timestamp: str | None = Query(None),
    nonce: str | None = Query(None),
    echostr: str | None = Query(None),
    encrypt_type: str | None = Query(None),
    msg_signature: str | None = Query(None),
):
    return await wechat_official_verify(
        signature=signature,
        timestamp=timestamp,
        nonce=nonce,
        echostr=echostr,
        encrypt_type=encrypt_type,
        msg_signature=msg_signature,
    )


@legacy_router.post("/callback/command")
async def legacy_wechat_official_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    signature: str | None = Query(None),
    timestamp: str | None = Query(None),
    nonce: str | None = Query(None),
    encrypt_type: str | None = Query(None),
    msg_signature: str | None = Query(None),
):
    return await wechat_official_callback(
        request=request,
        background_tasks=background_tasks,
        signature=signature,
        timestamp=timestamp,
        nonce=nonce,
        encrypt_type=encrypt_type,
        msg_signature=msg_signature,
    )
