import json
from datetime import datetime
from typing import Any
import time

from core.config import cfg
from core.db import DB
from core.models.article import Article
from core.models.article_insight import ArticleInsight
from core.print import print_error, print_info

from .extract import compute_content_hash, extract_headings, extract_summary, html_to_text


class InsightsService:
    def __init__(self):
        self.provider = cfg.get("llm.provider", "siliconflow")
        self.model = cfg.get("llm.siliconflow.model", "")

    def ensure_cached(self, article_id: str) -> None:
        """Best-effort precompute & cache insights for better UX."""
        import asyncio

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

        session = DB.get_session()
        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            return

        fetched_content = False
        try:
            if bool(cfg.get("insights.auto_fetch_content", False)) and (not (article.content or "").strip()):
                url = (article.url or "").strip()
                if url and "mp.weixin.qq.com" in url:
                    try:
                        from driver.wxarticle import WXArticleFetcher

                        info = WXArticleFetcher().get_article_content(url)
                        content = (info.get("content") or "").strip()
                        changed = False
                        if content:
                            article.content = content
                            changed = True
                        topic_image = (info.get("topic_image") or "").strip()
                        if topic_image and not (article.pic_url or "").strip():
                            article.pic_url = topic_image
                            changed = True
                        if changed:
                            article.updated_at = datetime.now()
                            session.add(article)
                            session.commit()
                            fetched_content = bool(content)
                    except Exception:
                        session.rollback()
        except Exception:
            session.rollback()

        # Always ensure basic exists (summary/headings/content_hash)
        try:
            ins = self.get_or_create_basic(article_id)
            if ins and (ins.summary or "").strip() and not (article.description or "").strip():
                article.description = (ins.summary or "").strip()
                article.updated_at = datetime.now()
                session.add(article)
                session.commit()
        except Exception:
            pass

        # Important: when we just fetched content via Playwright (sync),
        # some environments may have an active asyncio loop that makes `_run_coro`
        # fall back to `create_task()` and never persist results (key points/breakdown).
        # Re-schedule a second pass so LLM steps run after the fetch stage.
        if fetched_content:
            try:
                from core.queue import TaskQueue

                TaskQueue.add_task(self.ensure_cached, article_id)
            except Exception:
                pass
            return

        # Key points: can be generated from digest/summary even without content.
        if bool(cfg.get("insights.auto_key_points", False)):
            try:
                _run_coro(self.generate_key_points(article_id))
            except Exception:
                pass

        # Breakdown: requires content + LLM configured
        if bool(cfg.get("insights.auto_llm_breakdown", False)):
            try:
                _run_coro(self.generate_llm_breakdown(article_id))
            except Exception:
                pass

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
        ids = (
            session.query(Article.id)
            .filter(Article.mp_id == mp_id)
            .filter(Article.status != deleted_status)
            .filter(Article.publish_time.isnot(None))
            .filter(Article.publish_time >= threshold)
            .order_by(Article.publish_time.desc())
            .limit(limit)
            .all()
        )
        try:
            from core.queue import TaskQueue
        except Exception:
            TaskQueue = None

        for (aid,) in ids:
            try:
                if TaskQueue:
                    TaskQueue.add_task(self.ensure_cached, str(aid))
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
            insight.llm_provider = self.provider
            insight.llm_model = self.model

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
        api_key = cfg.get("llm.siliconflow.api_key", "")
        api_url = cfg.get("llm.siliconflow.api_url", "")
        model = cfg.get("llm.siliconflow.model", "")
        if not (api_key and api_url and model):
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

        from core.llm.siliconflow import siliconflow_chat_json

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

        try:
            data = await siliconflow_chat_json(
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
            insight.error = ""
        except Exception as e:
            print_error(f"LLM key points failed: {e}")
            # Persist fallback to keep UX stable.
            data = self._fallback_key_points(insight)
            insight.key_points_json = json.dumps(data, ensure_ascii=False)
            insight.error = str(e)

        insight.updated_at = datetime.now()
        insight.llm_provider = self.provider
        insight.llm_model = model
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

        api_key = cfg.get("llm.siliconflow.api_key", "")
        api_url = cfg.get("llm.siliconflow.api_url", "")
        model = cfg.get("llm.siliconflow.model", "")
        if not (api_key and api_url and model):
            insight.status = 9
            insight.error = "LLM not configured; set SILICONFLOW_API_KEY / SILICONFLOW_API_URL / SILICONFLOW_MODEL."
            insight.updated_at = datetime.now()
            insight.llm_provider = self.provider
            insight.llm_model = model
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

        from core.llm.siliconflow import siliconflow_chat_json

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

        try:
            data = await siliconflow_chat_json(
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
        except Exception as e:
            print_error(f"LLM breakdown failed: {e}")
            insight.status = 9
            insight.error = str(e)

        insight.updated_at = datetime.now()
        insight.llm_provider = self.provider
        insight.llm_model = cfg.get("llm.siliconflow.model", "")
        session.add(insight)
        session.commit()
        session.refresh(insight)
        return insight
