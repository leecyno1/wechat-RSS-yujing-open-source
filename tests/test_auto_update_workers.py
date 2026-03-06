from jobs.auto_update import _parse_workers_by_platform


def test_parse_workers_by_platform_basic():
    parsed = _parse_workers_by_platform("zhihu:4,xueqiu:3,wsj:1")
    assert parsed["zhihu"] == 4
    assert parsed["xueqiu"] == 3
    assert parsed["wsj"] == 1


def test_parse_workers_by_platform_invalid_items():
    parsed = _parse_workers_by_platform("bad,foo:bar,ok:2,too_big:999")
    assert "bad" not in parsed
    assert "foo" not in parsed
    assert parsed["ok"] == 2
    assert parsed["too_big"] == 32
