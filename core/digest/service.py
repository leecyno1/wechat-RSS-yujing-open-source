from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable, Literal, Optional

from sqlalchemy import func

from core.config import cfg
from core.db import DB
from core.models.article import ArticleBase
from core.models.article_insight import ArticleInsight
from core.models.base import DATA_STATUS
from core.models.feed import Feed
from core.models.user_subscription import UserSubscription


DigestSlot = Literal["morning", "afternoon", "evening", "daily"]


@dataclass(frozen=True)
class DigestWindow:
    start_ts: int
    end_ts: int
    label: str


def _int_or_none(v: Any) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _safe_str(v: Any) -> str:
    try:
        return str(v or "")
    except Exception:
        return ""


def _parse_date(value: str | None) -> date:
    if not value:
        return datetime.now().date()
    s = str(value).strip()
    if not s:
        return datetime.now().date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def _window_daily(d: date) -> DigestWindow:
    start_dt = datetime.combine(d, time.min)
    end_dt = start_dt + timedelta(days=1)
    return DigestWindow(start_ts=int(start_dt.timestamp()), end_ts=int(end_dt.timestamp()), label=f"{d.isoformat()} 全日")


def _window_slot(d: date, slot: DigestSlot) -> DigestWindow:
    morning_hour = int(cfg.get("digest.slot_morning_hour", 6) or 6)
    afternoon_hour = int(cfg.get("digest.slot_afternoon_hour", 15) or 15)
    evening_hour = int(cfg.get("digest.slot_evening_hour", 21) or 21)

    def _dt(dd: date, hh: int) -> datetime:
        return datetime.combine(dd, time(hour=max(0, min(23, int(hh or 0))), minute=0, second=0))

    if slot == "daily":
        return _window_daily(d)

    if slot == "morning":
        start_dt = _dt(d - timedelta(days=1), evening_hour)
        end_dt = _dt(d, morning_hour)
        label = f"{d.isoformat()} 早间({evening_hour:02d}:00-{morning_hour:02d}:00)"
    elif slot == "afternoon":
        start_dt = _dt(d, morning_hour)
        end_dt = _dt(d, afternoon_hour)
        label = f"{d.isoformat()} 午间({morning_hour:02d}:00-{afternoon_hour:02d}:00)"
    else:  # evening
        start_dt = _dt(d, afternoon_hour)
        end_dt = _dt(d, evening_hour)
        label = f"{d.isoformat()} 晚间({afternoon_hour:02d}:00-{evening_hour:02d}:00)"

    return DigestWindow(start_ts=int(start_dt.timestamp()), end_ts=int(end_dt.timestamp()), label=label)


def _metric_key(v: int | None) -> int:
    # Put unknown metrics at the bottom.
    return -1 if v is None else int(v)


def _truncate(text: str, max_len: int) -> str:
    if not text:
        return ""
    s = " ".join(str(text).strip().split())
    if max_len <= 0 or len(s) <= max_len:
        return s
    return s[: max(0, max_len - 1)] + "…"


class DigestService:
    def build_user_digest(
        self,
        user_id: str,
        *,
        digest_date: str | None = None,
        slot: DigestSlot = "daily",
        feed_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        d = _parse_date(digest_date)
        window = _window_slot(d, slot)

        top_n = int(cfg.get("digest.top_n", 5) or 5)
        top_n = max(1, min(20, top_n))

        max_summary_items = int(cfg.get("digest.max_summary_items", 20) or 20)
        max_summary_items = max(0, min(200, max_summary_items))

        max_summary_len = int(cfg.get("digest.summary_max_len", 80) or 80)
        max_summary_len = max(20, min(300, max_summary_len))

        session = DB.get_session()

        q = (
            session.query(ArticleBase, Feed, ArticleInsight)
            .join(UserSubscription, UserSubscription.feed_id == ArticleBase.mp_id)
            .join(Feed, Feed.id == ArticleBase.mp_id)
            .outerjoin(ArticleInsight, ArticleInsight.article_id == ArticleBase.id)
            .filter(UserSubscription.user_id == user_id)
            .filter(ArticleBase.status != DATA_STATUS.DELETED)
            .filter(ArticleBase.publish_time.isnot(None))
            .filter(ArticleBase.publish_time >= window.start_ts)
            .filter(ArticleBase.publish_time < window.end_ts)
        )

        if feed_ids:
            ids = [str(x).strip() for x in (feed_ids or []) if str(x).strip()]
            if ids:
                q = q.filter(ArticleBase.mp_id.in_(ids))

        rows = q.order_by(ArticleBase.publish_time.desc()).all()

        items: list[dict[str, Any]] = []
        for art, feed, ins in rows:
            title = _safe_str(getattr(art, "title", ""))
            mp_name = _safe_str(getattr(feed, "mp_name", ""))
            summary = ""
            try:
                summary = _safe_str(getattr(ins, "summary", "")) if ins is not None else ""
            except Exception:
                summary = ""
            if not summary:
                summary = _safe_str(getattr(art, "description", ""))
            items.append(
                {
                    "id": _safe_str(getattr(art, "id", "")),
                    "mp_id": _safe_str(getattr(art, "mp_id", "")),
                    "mp_name": mp_name,
                    "title": title,
                    "url": _safe_str(getattr(art, "url", "")),
                    "publish_time": _int_or_none(getattr(art, "publish_time", None)) or 0,
                    "read_count": _int_or_none(getattr(art, "read_count", None)),
                    "like_count": _int_or_none(getattr(art, "like_count", None)),
                    "share_count": _int_or_none(getattr(art, "share_count", None)),
                    "recommend_count": _int_or_none(getattr(art, "recommend_count", None)),
                    "summary": _truncate(summary, max_summary_len),
                }
            )

        # Top picks by metrics, then time.
        top_sorted = sorted(
            items,
            key=lambda it: (
                _metric_key(it.get("like_count")),
                _metric_key(it.get("read_count")),
                int(it.get("publish_time") or 0),
            ),
            reverse=True,
        )
        top_picks = top_sorted[:top_n]
        top_ids = {it.get("id") for it in top_picks if it.get("id")}

        # Summaries in time order, excluding top picks.
        time_sorted = sorted(items, key=lambda it: int(it.get("publish_time") or 0), reverse=True)
        summaries = [it for it in time_sorted if it.get("id") not in top_ids]
        if max_summary_items >= 0:
            summaries = summaries[:max_summary_items]

        digest_url_base = _safe_str(cfg.get("digest.url_base", "") or "")
        digest_url = ""
        if digest_url_base:
            base = digest_url_base.rstrip("/")
            digest_url = f"{base}/#/digest?date={d.isoformat()}&slot={slot}"

        digest = {
            "id": str(uuid.uuid4()),
            "user_id": _safe_str(user_id),
            "date": d.isoformat(),
            "slot": slot,
            "window": {"start_ts": window.start_ts, "end_ts": window.end_ts, "label": window.label},
            "stats": {"total": len(items), "top_picks": len(top_picks), "summaries": len(summaries)},
            "top_picks": top_picks,
            "summaries": summaries,
            "digest_url": digest_url,
        }

        digest["message"] = self.format_message(digest)
        return digest

    def format_message(self, digest: dict[str, Any]) -> dict[str, Any]:
        date_str = _safe_str(digest.get("date"))
        slot = _safe_str(digest.get("slot"))
        window_label = _safe_str((digest.get("window") or {}).get("label"))
        top_picks = list(digest.get("top_picks") or [])
        summaries = list(digest.get("summaries") or [])
        digest_url = _safe_str(digest.get("digest_url"))

        max_chars = int(cfg.get("digest.max_chars", 1800) or 1800)
        max_chars = max(200, min(8000, max_chars))

        header = f"【大圣之怒订阅助手】{date_str} {slot}精选"
        if window_label:
            header = f"{header}\n{window_label}"

        parts: list[str] = [header]

        if top_picks:
            parts.append("\n【精选 Top】(按点赞/阅读排序)")
            for i, it in enumerate(top_picks, start=1):
                title = _safe_str(it.get("title"))
                mp_name = _safe_str(it.get("mp_name"))
                url = _safe_str(it.get("url"))
                like_cnt = it.get("like_count")
                read_cnt = it.get("read_count")
                like_s = str(like_cnt) if like_cnt is not None else "-"
                read_s = str(read_cnt) if read_cnt is not None else "-"
                line1 = f"{i}. 👍{like_s} 👀{read_s}  {title}"
                line2 = f"   {mp_name}" if mp_name else ""
                line3 = f"   {url}" if url else ""
                block = "\n".join([x for x in (line1, line2, line3) if x])
                parts.append(block)

        if summaries:
            parts.append("\n【更新摘要】")
            for it in summaries:
                mp_name = _safe_str(it.get("mp_name"))
                title = _safe_str(it.get("title"))
                summary = _safe_str(it.get("summary"))
                url = _safe_str(it.get("url"))
                line1 = f"- {mp_name} | {title}" if mp_name else f"- {title}"
                line2 = f"  {summary}" if summary else ""
                line3 = f"  {url}" if url else ""
                block = "\n".join([x for x in (line1, line2, line3) if x])
                parts.append(block)

        if digest_url:
            parts.append(f"\n合集页：{digest_url}")

        text = "\n".join(parts).strip()
        if len(text) > max_chars:
            text = text[: max(0, max_chars - 1)] + "…"

        # Provide a structured payload for robots to consume.
        payload = {
            "date": date_str,
            "slot": slot,
            "window": digest.get("window") or {},
            "stats": digest.get("stats") or {},
            "digest_url": digest_url,
            "text": text,
            "top_picks": top_picks,
        }
        return {"text": text, "payload": payload}

