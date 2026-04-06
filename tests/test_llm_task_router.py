import json


def _mk_cfg_get(overrides: dict):
    base = {
        "llm.provider": "siliconflow",
        "llm.siliconflow.model": "default-model",
        "llm.siliconflow.api_url": "https://default.example/v1",
        "llm.siliconflow.api_key": "default-key",
        "llm.shard.enable": False,
        "llm.shard.profiles_json": "",
        "llm.shard.profiles": "",
        "llm.shard.models": "",
        "llm.fallback.enable": False,
        "llm.fallback.profiles_json": "",
        "llm.fallback.profiles": "",
        "llm.router.enable": False,
        "llm.router.shard.include_fallback": True,
        "llm.router.summary.mode": "fallback",
        "llm.router.key_points.mode": "fallback",
        "llm.router.breakdown.mode": "fallback",
        "llm.router.summary.profiles_json": "",
        "llm.router.key_points.profiles_json": "",
        "llm.router.breakdown.profiles_json": "",
        "llm.router.big_profiles_json": "",
        "llm.router.small_profiles_json": "",
    }
    base.update(overrides or {})
    return lambda key, default=None: base.get(key, default)


def test_task_router_big_for_summary_small_for_key_points(monkeypatch):
    from core.insights import service as service_mod

    summary_profiles = [
        {
            "name": "big-main",
            "provider": "openrouter",
            "api_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-big",
            "model": "anthropic/claude-3.5-sonnet",
            "priority": 1,
        }
    ]
    key_point_profiles = [
        {
            "name": "small-main",
            "provider": "openrouter",
            "api_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-small",
            "model": "qwen/qwen2.5-7b-instruct",
            "priority": 1,
        }
    ]

    monkeypatch.setattr(
        service_mod.cfg,
        "get",
        _mk_cfg_get(
            {
                "llm.router.enable": True,
                "llm.router.summary.mode": "fallback",
                "llm.router.key_points.mode": "fallback",
                "llm.router.summary.profiles_json": json.dumps(summary_profiles, ensure_ascii=False),
                "llm.router.key_points.profiles_json": json.dumps(key_point_profiles, ensure_ascii=False),
            }
        ),
    )

    svc = service_mod.InsightsService()
    s_order = svc._llm_profiles_try_order_for_task("A-001", "summary")
    k_order = svc._llm_profiles_try_order_for_task("A-001", "key_points")
    assert s_order and s_order[0][3] == "anthropic/claude-3.5-sonnet"
    assert k_order and k_order[0][3] == "qwen/qwen2.5-7b-instruct"


def test_task_router_shard_mode_picks_single_profile_and_keeps_fallback(monkeypatch):
    from core.insights import service as service_mod

    profiles = [
        {
            "name": "p-a",
            "provider": "provider-a",
            "api_url": "https://a.example/v1",
            "api_key": "ka",
            "model": "model-a",
            "priority": 2,
        },
        {
            "name": "p-b",
            "provider": "provider-b",
            "api_url": "https://b.example/v1",
            "api_key": "kb",
            "model": "model-b",
            "priority": 1,
        },
    ]

    monkeypatch.setattr(
        service_mod.cfg,
        "get",
        _mk_cfg_get(
            {
                "llm.router.enable": True,
                "llm.router.shard.include_fallback": True,
                "llm.router.summary.mode": "shard",
                "llm.router.summary.profiles_json": json.dumps(profiles, ensure_ascii=False),
            }
        ),
    )

    svc = service_mod.InsightsService()
    ordered = svc._llm_profiles_try_order_for_task("article-1001", "summary")
    assert len(ordered) == 2
    assert ordered[0][3] in {"model-a", "model-b"}
    assert ordered[1][3] in {"model-a", "model-b"}
    assert ordered[0][3] != ordered[1][3]
