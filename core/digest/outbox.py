from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from core.db import DB
from core.digest.service import DigestService
from core.models.user import User as DBUser
from core.models.user_message_outbox import UserMessageOutbox
from core.models.user_wechat_binding import UserWechatBinding


def generate_digest_outbox(
    *,
    digest_date: str | None = None,
    slot: str = "daily",
    channel: str = "wechat",
    only_bound: bool = True,
) -> dict[str, Any]:
    session = DB.get_session()
    svc = DigestService()

    d = (digest_date or "").strip() or datetime.now().date().isoformat()
    slot_s = (slot or "daily").strip() or "daily"
    channel_s = (channel or "wechat").strip() or "wechat"

    users = session.query(DBUser).filter(DBUser.is_active == True).order_by(DBUser.created_at.asc()).all()  # noqa: E712
    total_users = len(users)

    existing_user_ids = set(
        uid
        for (uid,) in (
            session.query(UserMessageOutbox.user_id)
            .filter(UserMessageOutbox.channel == channel_s)
            .filter(UserMessageOutbox.message_type == "daily_digest")
            .filter(UserMessageOutbox.digest_date == d)
            .filter(UserMessageOutbox.digest_slot == slot_s)
            .all()
        )
    )

    bindings_map: dict[str, UserWechatBinding] = {}
    if only_bound:
        rows = (
            session.query(UserWechatBinding)
            .filter(UserWechatBinding.is_active == 1)
            .filter(UserWechatBinding.user_id.in_([u.id for u in users]))
            .all()
        )
        bindings_map = {str(b.user_id): b for b in rows}

    created = 0
    skipped_exists = 0
    skipped_empty = 0
    skipped_unbound = 0

    now = datetime.now()
    for u in users:
        uid = str(u.id)
        if uid in existing_user_ids:
            skipped_exists += 1
            continue
        if only_bound and uid not in bindings_map:
            skipped_unbound += 1
            continue

        digest = svc.build_user_digest(uid, digest_date=d, slot=slot_s)
        total = int(((digest.get("stats") or {}).get("total")) or 0)
        if total <= 0:
            skipped_empty += 1
            continue

        binding = bindings_map.get(uid) if only_bound else session.query(UserWechatBinding).filter(UserWechatBinding.user_id == uid).filter(UserWechatBinding.is_active == 1).first()
        openid = str(getattr(binding, "wechat_openid", "") or "") if binding else ""

        payload = (digest.get("message") or {}).get("payload") or {}
        payload = dict(payload)
        payload.update({"user_id": uid, "wechat_openid": openid})
        payload_json = json.dumps(payload, ensure_ascii=False)

        msg_text = str(((digest.get("message") or {}).get("text")) or "")
        if not msg_text.strip():
            skipped_empty += 1
            continue

        outbox = UserMessageOutbox(
            id=str(uuid.uuid4()),
            user_id=uid,
            channel=channel_s,
            message_type="daily_digest",
            digest_date=d,
            digest_slot=slot_s,
            start_ts=int(((digest.get("window") or {}).get("start_ts")) or 0),
            end_ts=int(((digest.get("window") or {}).get("end_ts")) or 0),
            title=f"{d} {slot_s} digest",
            message_text=msg_text,
            payload_json=payload_json,
            status=0,
            created_at=now,
            updated_at=now,
        )
        session.add(outbox)
        created += 1

    session.commit()
    return {
        "date": d,
        "slot": slot_s,
        "channel": channel_s,
        "total_users": total_users,
        "created": created,
        "skipped_exists": skipped_exists,
        "skipped_empty": skipped_empty,
        "skipped_unbound": skipped_unbound,
    }

