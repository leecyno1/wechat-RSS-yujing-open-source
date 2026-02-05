def test_fillback_does_not_sleep_in_fast_mode(monkeypatch):
    from core.wx.base import WxGather

    slept = []

    # Patch sleep at both common call sites (legacy Wait() and direct time.sleep usage).
    try:
        import core.wait as wait_mod

        monkeypatch.setattr(wait_mod.time, "sleep", lambda s: slept.append(s))
    except Exception:
        pass

    import core.wx.base as base_mod

    monkeypatch.setattr(base_mod.time, "sleep", lambda s: slept.append(s))

    g = WxGather()
    g.fast_mode = True

    def cb(_art):
        return True

    g.FillBack(
        CallBack=cb,
        data={
            "id": "a1",
            "mp_id": "mp1",
            "title": "t",
            "link": "https://example.com",
            "cover": "c",
            "update_time": 1700000000,
        },
        Ext_Data={"mp_title": "x", "mp_id": "mp1"},
    )

    assert slept == []

