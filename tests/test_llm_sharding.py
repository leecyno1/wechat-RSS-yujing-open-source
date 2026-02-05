def test_llm_sharding_is_stable_and_spreads():
    from core.insights.service import _pick_shard_model

    models = ["m1", "m2", "m3"]
    picks = [_pick_shard_model(f"a{i}", models) for i in range(200)]

    # Stable: calling twice yields same results.
    picks2 = [_pick_shard_model(f"a{i}", models) for i in range(200)]
    assert picks == picks2

    # Spread: all models should appear at least once.
    assert set(picks) == set(models)

