import json
import re
from datetime import datetime
from typing import Any
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from core.config import cfg
from core.db import DB
from core.models.article import Article
from core.models.article_insight import ArticleInsight
from core.print import print_error, print_info
from core.queue import InFlightGate

from .extract import compute_content_hash, extract_headings, extract_summary, html_to_text


_INSIGHT_WARMUP_GATE = InFlightGate()


def _content_usable(raw: Any, *, min_chars: int) -> bool:
    s = str(raw or "").strip()
    if not s or s == "DELETED":
        return False
    text = re.sub(r"<[^>]+>", " ", s)
    text = re.sub(r"\s+", " ", text).strip()
    return len(text) >= max(20, int(min_chars or 120))


def _run_blocking_with_timeout(fn, *, timeout_seconds: float) -> Any:
    timeout_seconds = max(3.0, min(180.0, float(timeout_seconds or 30.0)))
    pool = ThreadPoolExecutor(max_workers=1)
    fut = pool.submit(fn)
    try:
        return fut.result(timeout=timeout_seconds)
    finally:
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass


def _pick_shard_model(article_id: str, models: list[str]) -> str:
    """Deterministically pick one model for an article (strategy A: shard by article)."""
    models = [str(m).strip() for m in (models or []) if str(m).strip()]
    if not models:
        return ""
    h = hashlib.sha256(str(article_id or "").encode("utf-8")).digest()
    idx = int.from_bytes(h[:4], "big") % len(models)
    return models[idx]


def _parse_shard_profiles(raw: Any) -> list[dict[str, str]]:
    """Parse sharding profiles from JSON string / list.

    A profile is an OpenAI-compatible endpoint config:
    {name, provider?, api_url, api_key, model}
    """
    if raw is None:
        return []
    data: Any = raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            data = json.loads(s)
        except Exception:
            return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, str]] = []

    def _priority(v: Any) -> int:
        try:
            n = int(v)
            if n < 1:
                return 9999
            return n
        except Exception:
            return 9999

    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        api_url = str(item.get("api_url") or "").strip()
        api_key = str(item.get("api_key") or "").strip()
        model = str(item.get("model") or "").strip()
        provider = str(item.get("provider") or "").strip()
        if not (name and api_url and api_key and model):
            continue
        out.append(
            {
                "name": name,
                "provider": provider,
                "api_url": api_url,
                "api_key": api_key,
                "model": model,
                "priority": str(_priority(item.get("priority", 9999))),
            }
        )
    # Deterministic order to keep stable sharding across restarts.
    out.sort(key=lambda x: x.get("name", ""))
    return out


def _pick_shard_profile(article_id: str, profiles: list[dict[str, str]]) -> dict[str, str]:
    profiles = profiles or []
    if not profiles:
        return {}
    h = hashlib.sha256(str(article_id or "").encode("utf-8")).digest()
    idx = int.from_bytes(h[:4], "big") % len(profiles)
    return profiles[idx]


def _parse_fallback_profiles(raw: Any) -> list[dict[str, str]]:
    profiles = _parse_shard_profiles(raw)
    if not profiles:
        return []
    # Fallback uses strict priority order (1 -> 2 -> 3 ...).
    profiles.sort(key=lambda x: (int(str(x.get("priority") or "9999")), str(x.get("name") or "")))
    return profiles


def _safe_priority(v: Any, default: int = 9999) -> int:
    try:
        n = int(v)
        return n if n > 0 else default
    except Exception:
        return default


def _norm_router_mode(v: Any) -> str:
    s = str(v or "").strip().lower()
    if s in ("shard", "hash", "hash_shard"):
        return "shard"
    return "fallback"


def _profiles_to_tuples(profiles: list[dict[str, str]]) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    for prof in profiles or []:
        out.append(
            (
                str(prof.get("provider") or "").strip(),
                str(prof.get("api_url") or "").strip(),
                str(prof.get("api_key") or "").strip(),
                str(prof.get("model") or "").strip(),
            )
        )
    return out


def _sort_profiles_priority(profiles: list[dict[str, str]]) -> list[dict[str, str]]:
    out = list(profiles or [])
    out.sort(key=lambda x: (_safe_priority(x.get("priority"), 9999), str(x.get("name") or "")))
    return out


class InsightsService:
    def __init__(self):
        self.provider = cfg.get("llm.provider", "siliconflow")
        self.model = cfg.get("llm.siliconflow.model", "")

        shard_enable = bool(cfg.get("llm.shard.enable", False))

        # Optional sharding (strategy A): spread articles across multiple OpenAI-compatible profiles.
        # This maximizes parallelism by using multiple providers / keys.
        profiles_raw = cfg.get("llm.shard.profiles_json", "") or cfg.get("llm.shard.profiles", "")
        self._shard_profiles = _parse_shard_profiles(profiles_raw)
        self._shard_enable = shard_enable and bool(self._shard_profiles)

        # Optional priority fallback chain (strategy B): try provider #1 -> #2 -> #3.
        # Used for high-availability and cross-provider failover.
        fallback_enable = bool(cfg.get("llm.fallback.enable", False))
        fallback_raw = cfg.get("llm.fallback.profiles_json", "") or cfg.get("llm.fallback.profiles", "")
        self._fallback_profiles = _parse_fallback_profiles(fallback_raw)
        self._fallback_enable = fallback_enable and bool(self._fallback_profiles)

        # 0913-style task router: split big/small model routes by task.
        # - summary  => big model route
        # - key_points => small model route
        # - breakdown => optional custom route (defaults to summary route when omitted)
        self._router_enable = bool(cfg.get("llm.router.enable", False))
        self._router_modes = {
            "summary": _norm_router_mode(cfg.get("llm.router.summary.mode", "fallback")),
            "key_points": _norm_router_mode(cfg.get("llm.router.key_points.mode", "fallback")),
            "breakdown": _norm_router_mode(cfg.get("llm.router.breakdown.mode", "fallback")),
        }
        self._router_shard_include_fallback = bool(cfg.get("llm.router.shard.include_fallback", True))

        # Aliases:
        # - llm.router.big_profiles_json -> summary route
        # - llm.router.small_profiles_json -> key_points route
        summary_raw = (
            cfg.get("llm.router.summary.profiles_json", "")
            or cfg.get("llm.router.big_profiles_json", "")
            or cfg.get("llm.router.summary.profiles", "")
        )
        key_points_raw = (
            cfg.get("llm.router.key_points.profiles_json", "")
            or cfg.get("llm.router.small_profiles_json", "")
            or cfg.get("llm.router.key_points.profiles", "")
        )
        breakdown_raw = (
            cfg.get("llm.router.breakdown.profiles_json", "")
            or cfg.get("llm.router.breakdown.profiles", "")
            or summary_raw
        )
        self._router_profiles = {
            "summary": _parse_shard_profiles(summary_raw),
            "key_points": _parse_shard_profiles(key_points_raw),
            "breakdown": _parse_shard_profiles(breakdown_raw),
        }

        # Back-compat: older config supports sharding across models under a single provider.
        shard_models_raw = str(cfg.get("llm.shard.models", "") or "")
        self._shard_models = [m.strip() for m in shard_models_raw.split(",") if m.strip()]

    def _model_for_article(self, article_id: str) -> str:
        if self._shard_enable:
            prof = _pick_shard_profile(article_id, self._shard_profiles)
            return (prof.get("model") or "").strip() or self.model
        if not self._shard_models:
            return self.model
        picked = _pick_shard_model(article_id, self._shard_models)
        return picked or self.model

    def _profile_for_article(self, article_id: str) -> dict[str, str]:
        if not self._shard_enable:
            return {}
        return _pick_shard_profile(article_id, self._shard_profiles)

    def _llm_profile_params(self, article_id: str) -> tuple[str, str, str, str]:
        """Return (provider, api_url, api_key, model) for this article."""
        if self._fallback_enable:
            prof = self._fallback_profiles[0] if self._fallback_profiles else {}
            return (
                str(prof.get("provider") or "").strip(),
                str(prof.get("api_url") or "").strip(),
                str(prof.get("api_key") or "").strip(),
                str(prof.get("model") or "").strip(),
            )
        if self._shard_enable:
            prof = self._profile_for_article(article_id)
            return (
                str(prof.get("provider") or "").strip(),
                str(prof.get("api_url") or "").strip(),
                str(prof.get("api_key") or "").strip(),
                str(prof.get("model") or "").strip(),
            )
        # Default (single provider)
        return (
            str(self.provider or "").strip(),
            str(cfg.get("llm.siliconflow.api_url", "") or "").strip(),
            str(cfg.get("llm.siliconflow.api_key", "") or "").strip(),
            str(cfg.get("llm.siliconflow.model", "") or "").strip(),
        )

    def _llm_profiles_try_order(self, article_id: str) -> list[tuple[str, str, str, str]]:
        """Return ordered LLM profiles for retry/fallback.

        Tuple schema: (provider, api_url, api_key, model).
        """
        if self._fallback_enable:
            ordered: list[tuple[str, str, str, str]] = []
            for prof in self._fallback_profiles:
                ordered.append(
                    (
                        str(prof.get("provider") or "").strip(),
                        str(prof.get("api_url") or "").strip(),
                        str(prof.get("api_key") or "").strip(),
                        str(prof.get("model") or "").strip(),
                    )
                )
            return ordered
        return [self._llm_profile_params(article_id)]

    def _llm_profiles_try_order_for_task(self, article_id: str, task: str) -> list[tuple[str, str, str, str]]:
        task_key = str(task or "").strip().lower() or "summary"
        if not self._router_enable:
            return self._llm_profiles_try_order(article_id)

        profiles = list(self._router_profiles.get(task_key) or [])
        if not profiles:
            return self._llm_profiles_try_order(article_id)

        mode = self._router_modes.get(task_key, "fallback")
        if mode == "shard":
            picked = _pick_shard_profile(article_id, profiles)
            if not picked:
                return self._llm_profiles_try_order(article_id)
            ordered_profiles: list[dict[str, str]] = [picked]
            if self._router_shard_include_fallback:
                picked_name = str(picked.get("name") or "")
                for prof in _sort_profiles_priority(profiles):
                    name = str(prof.get("name") or "")
                    if name and name == picked_name:
                        continue
                    ordered_profiles.append(prof)
            return _profiles_to_tuples(ordered_profiles)

        # default: fallback
        return _profiles_to_tuples(_sort_profiles_priority(profiles))

    def _llm_profile_params_for_task(self, article_id: str, task: str) -> tuple[str, str, str, str]:
        ordered = self._llm_profiles_try_order_for_task(article_id, task)
        if ordered:
            return ordered[0]
        return self._llm_profile_params(article_id)

    def ensure_cached(self, article_id: str) -> None:
        """Best-effort precompute & cache insights for better UX."""
        import asyncio

        article_id = str(article_id or "").strip()
        if not article_id:
            return
        if not _INSIGHT_WARMUP_GATE.try_acquire(article_id):
            return

        def _run_coro(coro):
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(coro)
                    return None
            except RuntimeError:
                pass

            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

        try:
            session = DB.get_session()
            article = session.query(Article).filter(Article.id == article_id).first()
            if not article:
                return

            fetched_content = False
            try:
                if bool(cfg.get("insights.auto_fetch_content", False)) and (not (article.content or "").strip()):
                    try:
                        from apis.article import _fetch_article_content_sync

                        timeout_s = float(cfg.get("insights.auto_fetch_content_timeout_seconds", 40) or 40)
                        ret = _run_blocking_with_timeout(
                            lambda: _fetch_article_content_sync(article_id, force=False),
                            timeout_seconds=timeout_s,
                        )
                        if isinstance(ret, dict):
                            fetched_content = bool(ret.get("fetched")) and int(ret.get("content_len") or 0) > 0
                        # Refresh local row to avoid stale view.
                        if fetched_content:
                            try:
                                session.expire(article)
                                article = session.query(Article).filter(Article.id == article_id).first() or article
                            except Exception:
                                pass
                    except FuturesTimeoutError:
                        session.rollback()
                    except Exception:
                        session.rollback()
            except Exception:
                session.rollback()

            try:
                ins = self.get_or_create_basic(article_id)
                if ins and (ins.summary or "").strip() and not (article.description or "").strip():
                    article.description = (ins.summary or "").strip()
                    article.updated_at = datetime.now()
                    session.add(article)
                    session.commit()
            except Exception:
                pass

            if fetched_content:
                try:
                    from core.queue import InsightsQueue

                    InsightsQueue.add_task(self.ensure_cached, article_id)
                except Exception:
                    pass
                return

            auto_summary = bool(cfg.get("insights.auto_ai_summary", True))
            auto_key_points = bool(cfg.get("insights.auto_key_points", True))
            auto_breakdown = bool(cfg.get("insights.auto_llm_breakdown", False))
            if not (auto_summary or auto_key_points or auto_breakdown):
                return

            async def _run_all() -> None:
                import asyncio

                tasks: list[Any] = []
                if auto_summary:
                    tasks.append(self.generate_ai_summary(article_id, force=False))
                if auto_key_points:
                    tasks.append(self.generate_key_points(article_id))
                if auto_breakdown:
                    tasks.append(self.generate_llm_breakdown(article_id))
                if not tasks:
                    return
                await asyncio.gather(*tasks, return_exceptions=True)

            try:
                _run_coro(_run_all())
            except Exception:
                pass
        finally:
            _INSIGHT_WARMUP_GATE.release(article_id)

    def ensure_mp_recent_cached(self, mp_id: str, *, days: int = 3, limit: int = 120) -> None:
        """Schedule caching for recent articles of a feed (non-blocking)."""
        try:
            mp_id = str(mp_id or "").strip()
            if not mp_id:
                return
            days = int(days or 0)
            if days <= 0:
                return
            limit = int(limit or 0)
            if limit <= 0:
                return
        except Exception:
            return

        threshold = int(time.time()) - days * 86400
        session = DB.get_session()
        try:
            from core.models.base import DATA_STATUS
            deleted_status = int(DATA_STATUS.DELETED)
        except Exception:
            deleted_status = 1000
        rows = (
            session.query(Article.id, Article.content)
            .filter(Article.mp_id == mp_id)
            .filter(Article.status != deleted_status)
            .filter(Article.publish_time.isnot(None))
            .filter(Article.publish_time >= threshold)
            .order_by(Article.publish_time.desc())
            .limit(limit)
            .all()
        )
        try:
            from core.queue import InsightsQueue
        except Exception:
            InsightsQueue = None
        try:
            from apis.article import _schedule_article_content_fetch
        except Exception:
            _schedule_article_content_fetch = None

        prefetch_content = bool(cfg.get("insights.prewarm_prefetch_content", True))
        content_min_chars = max(20, min(5000, int(cfg.get("article.content_min_chars", 120) or 120)))

        for (aid, content) in rows:
            try:
                if prefetch_content and _schedule_article_content_fetch and not _content_usable(content, min_chars=content_min_chars):
                    try:
                        _schedule_article_content_fetch(str(aid), force=False)
                    except Exception:
                        pass
                if InsightsQueue:
                    InsightsQueue.add_task(self.ensure_cached, str(aid))
                else:
                    self.ensure_cached(str(aid))
            except Exception:
                continue

    def _try_hydrate_from_public_page(self, article: Article) -> bool:
        """Backfill digest/cover from the public article page (no WeChat backend auth).

        This is used when we only have url + title, but missing `description`/`pic_url`.
        """
        try:
            url = (article.url or "").strip()
            if not url or "mp.weixin.qq.com" not in url:
                return False
            # Only hydrate when digest missing (cover may already exist)
            if (article.description or "").strip():
                return False

            import requests
            from bs4 import BeautifulSoup

            headers = {
                "User-Agent": cfg.get("user_agent", ""),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Connection": "keep-alive",
            }
            resp = requests.get(url, headers=headers, timeout=float(cfg.get("llm.timeout", 20)))
            if resp.status_code != 200 or not resp.text:
                return False

            soup = BeautifulSoup(resp.text, "lxml")
            desc = ""
            for key in ("og:description", "twitter:description"):
                meta = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
                if meta and meta.get("content"):
                    desc = (meta.get("content") or "").strip()
                    if desc:
                        break

            image = ""
            for key in ("twitter:image", "og:image"):
                meta = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
                if meta and meta.get("content"):
                    image = (meta.get("content") or "").strip()
                    if image:
                        break

            changed = False
            if desc and not (article.description or "").strip():
                article.description = desc
                changed = True
            if image and not (article.pic_url or "").strip():
                article.pic_url = image
                changed = True
            return changed
        except Exception:
            return False

    def _fallback_key_points(self, insight: ArticleInsight) -> dict[str, Any]:
        """No-LLM fallback: derive key points from headings (or summary)."""
        headings: list[dict[str, Any]] = []
        try:
            headings = json.loads(insight.headings_json) if insight.headings_json else []
        except Exception:
            headings = []

        points: list[str] = []
        for h in headings:
            text = (h or {}).get("text") or ""
            if text:
                points.append(text)
            if len(points) >= 8:
                break

        highlight = ""
        if insight.summary:
            highlight = (insight.summary or "").strip()[:80]

        if not points and insight.summary:
            import re

            segs = re.split(r"[。！？!?\n]+", insight.summary or "")
            for s in segs:
                s = (s or "").strip()
                if not s:
                    continue
                points.append(s)
                if len(points) >= 5:
                    break

        if not highlight and points:
            highlight = points[0][:80]

        if highlight and not points:
            points = [highlight]

        return {"highlight": highlight, "points": points}

    def get_or_create_basic(self, article_id: str) -> ArticleInsight | None:
        session = DB.get_session()
        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            return None

        # If missing digest/cover, try to hydrate from public page once.
        try:
            if self._try_hydrate_from_public_page(article):
                article.updated_at = datetime.now()
                session.add(article)
                session.commit()
                session.refresh(article)
        except Exception:
            pass

        content_hash = compute_content_hash(article.description, article.content)
        insight = session.query(ArticleInsight).filter(ArticleInsight.article_id == article_id).first()

        should_refresh = False
        if insight is None:
            insight = ArticleInsight(article_id=article_id)
            should_refresh = True
        elif insight.content_hash != content_hash:
            should_refresh = True
        elif not (getattr(insight, "summary", "") or "").strip() and (article.title or "").strip():
            # Backfill legacy rows where summary was never generated.
            should_refresh = True

        if should_refresh:
            max_len = int(cfg.get("insights.summary_max_len", 200))
            summary = extract_summary(article.description, article.content, max_len=max_len)
            if not (summary or "").strip():
                summary = (article.title or "").strip()[:max_len]
            headings = extract_headings(article.content, levels=(1, 2), max_items=int(cfg.get("insights.headings_max_items", 20)))
            now = datetime.now()
            if summary and not (article.description or "").strip():
                article.description = summary
                article.updated_at = now
                session.add(article)
                # keep content_hash consistent with persisted fields
                content_hash = compute_content_hash(article.description, article.content)
            if getattr(insight, "created_at", None) is None:
                insight.created_at = now
            insight.updated_at = now
            insight.summary = summary
            insight.headings_json = json.dumps(headings, ensure_ascii=False)
            insight.content_hash = content_hash
            insight.status = 1
            insight.error = ""
            provider, _, _, model = self._llm_profile_params_for_task(article_id, "summary")
            insight.llm_provider = provider or self.provider
            insight.llm_model = model or self.model

            session.add(insight)
            session.commit()
            session.refresh(insight)

        # Late backfill: ensure list preview has content even when digest is missing.
        try:
            if insight and (insight.summary or "").strip() and not (article.description or "").strip():
                article.description = (insight.summary or "").strip()
                article.updated_at = datetime.now()
                session.add(article)
                session.commit()
        except Exception:
            session.rollback()

        return insight

    async def generate_key_points(self, article_id: str, *, force: bool = False) -> ArticleInsight | None:
        session = DB.get_session()
        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            return None

        insight = self.get_or_create_basic(article_id)
        if insight is None:
            return None

        # Cache hit: avoid re-running when content unchanged.
        if not force and getattr(insight, "key_points_json", None) and (insight.content_hash == compute_content_hash(article.description, article.content)):
            return insight

        # If LLM not configured, still persist a deterministic fallback so UI has data.
        profiles = [x for x in self._llm_profiles_try_order_for_task(article_id, "key_points") if x[1] and x[2] and x[3]]
        if not profiles:
            data = self._fallback_key_points(insight)
            insight.key_points_json = json.dumps(data, ensure_ascii=False)
            insight.updated_at = datetime.now()
            session.add(insight)
            session.commit()
            session.refresh(insight)
            return insight

        # Prefer full content; fall back to digest.
        # If both are missing, avoid hallucinating: store a deterministic, title-only fallback.
        content_text = html_to_text(article.content) or (article.description or "")
        if not (content_text or "").strip():
            title = (article.title or "").strip()
            highlight = title[:80]
            points: list[str] = []
            if highlight:
                points.append(highlight)
            points.append("未获取摘要/正文，建议先回填摘要或抓取正文后再生成")
            insight.key_points_json = json.dumps({"highlight": highlight, "points": points}, ensure_ascii=False)
            insight.updated_at = datetime.now()
            session.add(insight)
            session.commit()
            session.refresh(insight)
            return insight
        max_chars = int(cfg.get("llm.max_chars", 24000))
        clipped = content_text[:max_chars]
        if len(content_text) > max_chars:
            print_info(f"LLM input truncated: {len(content_text)} -> {len(clipped)} chars")

        from core.llm.openai_compat import openai_compat_chat_json

        system = (
            "你是一个信息提炼助手。只输出严格的 JSON，不要输出任何额外文字。"
            "JSON schema: {highlight:string, points:string[]}"
        )
        user = {
            "title": article.title or "",
            "summary_hint": insight.summary or "",
            "task": "提取 3-8 条关键信息点(points)，并给出一句最重要的高亮(highlight)。中文简洁。",
            "content": clipped,
        }

        used_provider = ""
        used_model = ""
        errs: list[str] = []
        ok = False
        for provider, api_url, api_key, model in profiles:
            try:
                data = await openai_compat_chat_json(
                    model=model,
                    api_url=api_url,
                    api_key=api_key,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                    ],
                    timeout=float(cfg.get("llm.timeout", 60)),
                )
                if not isinstance(data, dict):
                    raise ValueError("Invalid LLM response: not a JSON object")
                highlight = (data.get("highlight") or "").strip()
                points = data.get("points") if isinstance(data.get("points"), list) else []
                points = [str(x).strip() for x in points if str(x).strip()]
                if not highlight or not points:
                    fallback = self._fallback_key_points(insight)
                    highlight = highlight or fallback.get("highlight", "")
                    points = points or fallback.get("points", [])
                insight.key_points_json = json.dumps({"highlight": highlight, "points": points}, ensure_ascii=False)
                used_provider = provider
                used_model = model
                insight.error = ""
                ok = True
                break
            except Exception as e:
                errs.append(f"{provider or 'unknown'}:{model or 'unknown'} -> {str(e)}")
                continue

        if not ok:
            print_error(f"LLM key points failed: {' | '.join(errs)}")
            data = self._fallback_key_points(insight)
            insight.key_points_json = json.dumps(data, ensure_ascii=False)
            insight.error = " | ".join(errs)[:3000]

        insight.updated_at = datetime.now()
        insight.llm_provider = used_provider or self.provider
        insight.llm_model = used_model or self.model
        session.add(insight)
        session.commit()
        session.refresh(insight)
        return insight

    async def generate_ai_summary(self, article_id: str, *, force: bool = False) -> ArticleInsight | None:
        session = DB.get_session()
        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            return None

        insight = self.get_or_create_basic(article_id)
        if insight is None:
            return None

        if not force and (insight.summary or "").strip():
            # Heuristic: if current summary differs from deterministic local-extract result,
            # treat it as an already-generated summary and skip rerun.
            # This avoids repeated LLM calls while still upgrading local fallback summaries.
            existing = str(insight.summary or "").strip()
            max_len = int(cfg.get("insights.summary_max_len", 200))
            local_summary = extract_summary(article.description, article.content, max_len=max_len)
            title_summary = (article.title or "").strip()[:max_len]
            if existing and existing not in {str(local_summary or "").strip(), str(title_summary or "").strip()}:
                return insight

        content_text = html_to_text(article.content) or (article.description or "")
        if not (content_text or "").strip():
            insight.summary = (article.title or "").strip()[:200]
            insight.updated_at = datetime.now()
            session.add(insight)
            session.commit()
            session.refresh(insight)
            return insight

        profiles = [x for x in self._llm_profiles_try_order_for_task(article_id, "summary") if x[1] and x[2] and x[3]]
        if not profiles:
            max_len = int(cfg.get("insights.summary_max_len", 200))
            insight.summary = extract_summary(article.description, article.content, max_len=max_len)
            insight.updated_at = datetime.now()
            session.add(insight)
            session.commit()
            session.refresh(insight)
            return insight

        from core.llm.openai_compat import openai_compat_chat_text

        max_chars = int(cfg.get("llm.max_chars", 24000))
        clipped = content_text[:max_chars]
        system = "你是新闻编辑。输出一段中文摘要（120-220字），突出核心事实、结论与影响。不要使用标题、不要分点。"
        user = f"标题：{article.title or ''}\n内容：\n{clipped}"

        used_provider = ""
        used_model = ""
        errs: list[str] = []
        for provider, api_url, api_key, model in profiles:
            try:
                text = await openai_compat_chat_text(
                    model=model,
                    api_url=api_url,
                    api_key=api_key,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    timeout=float(cfg.get("llm.timeout", 60)),
                )
                summary = str(text or "").strip()
                if not summary:
                    raise ValueError("Empty summary")
                insight.summary = summary[:500]
                used_provider = provider
                used_model = model
                insight.error = ""
                break
            except Exception as e:
                errs.append(f"{provider or 'unknown'}:{model or 'unknown'} -> {str(e)}")
                continue

        if not (insight.summary or "").strip():
            max_len = int(cfg.get("insights.summary_max_len", 200))
            insight.summary = extract_summary(article.description, article.content, max_len=max_len)
            insight.error = " | ".join(errs)[:3000]

        if (insight.summary or "").strip() and not (article.description or "").strip():
            article.description = (insight.summary or "").strip()
            article.updated_at = datetime.now()
            session.add(article)

        insight.updated_at = datetime.now()
        insight.llm_provider = used_provider or self.provider
        insight.llm_model = used_model or self.model
        session.add(insight)
        session.commit()
        session.refresh(insight)
        return insight

    async def generate_llm_breakdown(self, article_id: str, *, force: bool = False) -> ArticleInsight | None:
        session = DB.get_session()
        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            return None

        insight = self.get_or_create_basic(article_id)
        if insight is None:
            return None

        # Cache hit: avoid re-running when content unchanged.
        if (
            not force
            and getattr(insight, "llm_breakdown_json", None)
            and (insight.content_hash == compute_content_hash(article.description, article.content))
        ):
            return insight

        profiles = [x for x in self._llm_profiles_try_order_for_task(article_id, "breakdown") if x[1] and x[2] and x[3]]
        if not profiles:
            insight.status = 9
            insight.error = "LLM not configured; set llm.shard.profiles_json (recommended) or llm.siliconflow.api_key/api_url/model."
            insight.updated_at = datetime.now()
            insight.llm_provider = self.provider
            insight.llm_model = self.model
            session.add(insight)
            session.commit()
            return insight

        content_text = html_to_text(article.content)
        if not content_text:
            insight.status = 9
            insight.error = "Article content is empty; cannot run LLM breakdown."
            insight.updated_at = datetime.now()
            session.add(insight)
            session.commit()
            return insight

        from core.llm.openai_compat import openai_compat_chat_json

        max_chars = int(cfg.get("llm.max_chars", 24000))
        clipped = content_text[:max_chars]
        if len(content_text) > max_chars:
            print_info(f"LLM input truncated: {len(content_text)} -> {len(clipped)} chars")

        system = (
            "你是一个文章结构化拆解助手。只输出严格的 JSON，不要输出任何额外文字。"
            "JSON 必须符合 schema: {title:string, outline:[{level:1|2|3, heading:string, bullets:string[], children:[]}]}"
        )
        user = {
            "title": article.title or "",
            "summary_hint": insight.summary or "",
            "task": "将全文按标题层级拆解为最多三级大纲。每个节点给出 1-3 条要点 bullets。保持中文简洁。",
            "content": clipped,
        }

        used_provider = ""
        used_model = ""
        errs: list[str] = []
        for provider, api_url, api_key, model in profiles:
            try:
                data = await openai_compat_chat_json(
                    model=model,
                    api_url=api_url,
                    api_key=api_key,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                    ],
                    timeout=float(cfg.get("llm.timeout", 60)),
                )
                insight.llm_breakdown_json = json.dumps(data, ensure_ascii=False)
                insight.status = 2
                insight.error = ""
                used_provider = provider
                used_model = model
                break
            except Exception as e:
                errs.append(f"{provider or 'unknown'}:{model or 'unknown'} -> {str(e)}")
                continue

        if insight.status != 2:
            print_error(f"LLM breakdown failed: {' | '.join(errs)}")
            insight.status = 9
            insight.error = " | ".join(errs)[:3000]

        insight.updated_at = datetime.now()
        insight.llm_provider = used_provider or self.provider
        insight.llm_model = used_model or self.model
        session.add(insight)
        session.commit()
        session.refresh(insight)
        return insight
