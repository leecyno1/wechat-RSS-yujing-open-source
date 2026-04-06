import json


def test_parse_fallback_profiles_sorted_by_priority():
    from core.insights.service import _parse_fallback_profiles

    raw = json.dumps(
        [
            {
                "name": "p2",
                "provider": "provider-2",
                "api_url": "https://p2.example/v1",
                "api_key": "k2",
                "model": "m2",
                "priority": 2,
            },
            {
                "name": "p1",
                "provider": "provider-1",
                "api_url": "https://p1.example/v1",
                "api_key": "k1",
                "model": "m1",
                "priority": 1,
            },
            {
                "name": "p3",
                "provider": "provider-3",
                "api_url": "https://p3.example/v1",
                "api_key": "k3",
                "model": "m3",
                "priority": 3,
            },
        ],
        ensure_ascii=False,
    )

    profiles = _parse_fallback_profiles(raw)
    assert [x["name"] for x in profiles] == ["p1", "p2", "p3"]
    assert [int(x["priority"]) for x in profiles] == [1, 2, 3]


def test_insights_service_uses_fallback_profiles_in_priority_order(monkeypatch):
    from core.insights import service as service_mod

    cfg_map = {
        "llm.provider": "siliconflow",
        "llm.siliconflow.model": "default-model",
        "llm.siliconflow.api_url": "https://default.example/v1",
        "llm.siliconflow.api_key": "default-key",
        "llm.shard.enable": False,
        "llm.shard.profiles_json": "",
        "llm.shard.profiles": "",
        "llm.shard.models": "",
        "llm.fallback.enable": True,
        "llm.fallback.profiles_json": json.dumps(
            [
                {
                    "name": "secondary",
                    "provider": "provider-b",
                    "api_url": "https://b.example/v1",
                    "api_key": "kb",
                    "model": "model-b",
                    "priority": 2,
                },
                {
                    "name": "primary",
                    "provider": "provider-a",
                    "api_url": "https://a.example/v1",
                    "api_key": "ka",
                    "model": "model-a",
                    "priority": 1,
                },
            ],
            ensure_ascii=False,
        ),
        "llm.fallback.profiles": "",
    }

    monkeypatch.setattr(service_mod.cfg, "get", lambda key, default=None: cfg_map.get(key, default))
    svc = service_mod.InsightsService()
    ordered = svc._llm_profiles_try_order("article-1")
    assert len(ordered) == 2
    assert ordered[0][0] == "provider-a"
    assert ordered[0][3] == "model-a"
    assert ordered[1][0] == "provider-b"
    assert ordered[1][3] == "model-b"
