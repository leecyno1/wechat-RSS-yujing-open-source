# Refresh Performance + Admin Config + LLM Sharding (A) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make manual/auto refresh finish fast (10 accounts <= 60s; 300 accounts <= 15min) by adding concurrent background workers, removing per-item sleeps, and switching to incremental updates; add an admin-only config page that persists model/provider parameters; shard LLM work across multiple models by article (strategy A) to improve throughput.

**Architecture:** Keep an in-process worker pool for now (no Redis). Split work into two queues: `refresh` (feed fetch + upsert) and `insights` (summary/keypoints/breakdown). Refresh enqueues quickly and finishes fast; insights are best-effort and never block refresh. LLM sharding picks a model per-article deterministically to spread load across configured models.

**Tech Stack:** FastAPI + SQLAlchemy + in-process background workers (thread pool), Vue3 UI, YAML config + sqlite volume.

---

### Task 1: Make TaskQueue concurrent + add InsightsQueue

**Files:**
- Modify: `core/queue/queue.py`
- Modify: `core/queue/__init__.py`
- Modify call sites (insights): `apis/article.py`, `apis/insights.py`, `apis/channels.py`, `apis/public.py`, `apis/service_api.py`, `core/db.py`, `core/insights/service.py`

**Step 1: Write a minimal queue test (fails first)**
- Create: `tests/test_queue_workers.py`
- Assert N workers can run tasks concurrently (wall clock shorter than sequential).

**Step 2: Implement worker pool**
- Refactor `TaskQueueManager` to support `workers=N` and start N daemon threads.
- Add `InsightsQueue = TaskQueueManager(tag="洞察队列", workers=<cfg>)`.
- Ensure `get_queue_info()` includes `workers`, `pending_tasks`, `running`.

**Step 3: Move insight tasks to InsightsQueue**
- Replace `TaskQueue.add_task(InsightsService().ensure_cached, ...)` with `InsightsQueue.add_task(...)` where appropriate.

**Step 4: Run tests**
- Run: `pytest -q`
- Expected: PASS.

---

### Task 2: Remove “per article” sleeps + support fast refresh mode

**Files:**
- Modify: `core/wx/base.py`
- Modify: `core/wx/model/app.py`
- Modify: `core/wx/model/web.py`
- Modify: `core/wx/model/api.py`

**Steps:**
- Add `fast_mode` flag on gather instances; when enabled:
  - page-level `sleep(randint(...))` becomes 0.
  - `FillBack()` no longer sleeps 1-5 seconds per article.
  - `Item_Over()` wait becomes 0.
- Keep a small configurable jitter for non-fast mode to avoid frequency control.

**Test (lightweight):**
- Add a unit test that `FillBack()` does not sleep when `fast_mode=True` (monkeypatch `time.sleep`).

---

### Task 3: Make refresh incremental + stop early on old articles

**Files:**
- Modify: `apis/mps.py` (`_queue_update_feed`, `/update/all`)
- Modify: `jobs/auto_update.py`

**Steps:**
- Compute `since_ts` from DB: `max(publish_time)` per feed minus a grace window (default 3600s).
- Pass `since_ts` into `wx.get_Articles(...)` so the crawler breaks when it hits older content.
- Write `mp.sync_time` at the start of `_queue_update_feed` to prevent duplicate concurrent refresh.

**Test (unit):**
- Add helper function that computes `since_ts` and test it with empty/non-empty histories.

---

### Task 4: Admin-only config page that actually persists & applies

**Problem today:** `apis/config_management.py` lists YAML but update writes DB table, so edits don’t take effect.

**Files:**
- Modify: `core/config.py` (reload + override merge + set_path)
- Modify: `apis/config_management.py` (admin-only + write overrides)
- Modify (UI hide): `web_ui/src/router/index.ts` and/or `web_ui/src/views/InfoLayout.vue` (only show Config entry for admin)

**Steps:**
- Add `data/config.override.yaml` support (loaded after base config; persisted via docker volume).
- Add `cfg.set_path("llm.siliconflow.model", "...")` that writes to override file.
- Lock down all config endpoints to `role=admin`.

**Manual test:**
- Edit `llm.siliconflow.model` via UI; verify `GET /api/v1/wx/configs` returns new value and insights use it.

---

### Task 5: LLM sharding strategy A (per-article model selection)

**Files:**
- Modify: `core/insights/service.py`
- Modify: `config.example.yaml` (document `LLM_SHARD_MODELS`, `LLM_SHARD_ENABLE`)

**Steps:**
- Add config:
  - `llm.shard.enable` (default True)
  - `llm.shard.models` (comma-separated; default empty -> use single `llm.siliconflow.model`)
- Deterministically choose model by `hash(article_id) % len(models)` when enabled.
- Persist chosen model in `ArticleInsight.llm_model` per row.

**Test:**
- Given 3 models, 100 synthetic article ids distribute across models and are stable.

---

### Task 6: Verification + Docker smoke

**Steps:**
- Run backend quick checks: `python -m compileall apis core web.py`
- Build & run local compose: `docker compose -f compose/docker-compose-local.yaml up -d --build`
- Trigger refresh: `curl -H "Authorization: Bearer <token>" "http://localhost:8001/api/v1/wx/mps/update/all?start_page=0&end_page=1"`
- Watch queue stats: `GET /api/v1/wx/sys_info` (queue pending decreases quickly).

