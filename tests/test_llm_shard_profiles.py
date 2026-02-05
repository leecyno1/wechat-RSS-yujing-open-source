import json


def test_parse_and_pick_profile_is_stable_and_spreads():
    from core.insights.service import _parse_shard_profiles, _pick_shard_profile

    raw = json.dumps(
        [
            {"name": "p1", "provider": "a", "api_url": "https://a.example/v1", "api_key": "k1", "model": "m1"},
            {"name": "p2", "provider": "b", "api_url": "https://b.example/v1", "api_key": "k2", "model": "m2"},
            {"name": "p3", "provider": "c", "api_url": "https://c.example/v1", "api_key": "k3", "model": "m3"},
        ],
        ensure_ascii=False,
    )

    profiles = _parse_shard_profiles(raw)
    assert [p["name"] for p in profiles] == ["p1", "p2", "p3"]

    picks = [_pick_shard_profile(f"a{i}", profiles)["name"] for i in range(200)]
    picks2 = [_pick_shard_profile(f"a{i}", profiles)["name"] for i in range(200)]
    assert picks == picks2
    assert set(picks) == {"p1", "p2", "p3"}

