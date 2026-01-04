import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status as fast_status

from apis.base import error_response, success_response
from core.auth import get_current_user
from core.db import DB
from core.digest import DigestService
from core.models.tags import Tags


router = APIRouter(prefix="/digest", tags=["合集/推送"])


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


def _topic_feed_ids(session, topic: Tags) -> list[str]:
    raw = (getattr(topic, "mps_id", None) or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    ids: list[str] = []
    if isinstance(data, list):
        for it in data:
            if isinstance(it, dict) and it.get("id"):
                ids.append(str(it.get("id")).strip())
            elif isinstance(it, str):
                ids.append(it.strip())
    return [x for x in ids if x]


@router.get("/daily", summary="站内每日合集(按用户订阅聚合)")
async def digest_daily(
    date: str | None = Query(None, description="YYYY-MM-DD；为空表示今天"),
    slot: str = Query("daily", description="daily|morning|afternoon|evening"),
    topic_id: str | None = Query(None, description="可选：仅看某个专题(标签)内的公众号"),
    current_user: dict = Depends(get_current_user),
):
    user_id = _uid(current_user)
    session = DB.get_session()

    feed_ids = None
    if topic_id:
        q = session.query(Tags).filter(Tags.id == topic_id)
        if not _is_admin(current_user):
            q = q.filter(Tags.user_id == user_id)
        topic = q.first()
        if not topic:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="专题不存在"),
            )
        feed_ids = _topic_feed_ids(session, topic)

    try:
        svc = DigestService()
        digest = svc.build_user_digest(user_id, digest_date=date, slot=slot, feed_ids=feed_ids)
        return success_response(digest)
    except ValueError as e:
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40001, message=str(e)),
        )
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"生成合集失败: {str(e)}"),
        )

