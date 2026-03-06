from apis.sources import PLATFORM_PRESETS, _normalize_platform


def test_platform_presets_cover_key_platforms():
    keys = {str(x.get("platform") or "").strip() for x in PLATFORM_PRESETS}
    assert "zhihu" in keys
    assert "xueqiu" in keys
    assert "toutiao" in keys
    assert "baijiahao" in keys
    assert "wsj" in keys
    assert "bbc" in keys


def test_normalize_platform_alias():
    assert _normalize_platform("wx", "rsshub") == "wechat"
    assert _normalize_platform("weixin", "rsshub") == "wechat"
    assert _normalize_platform("wallstreetjournal", "rss") == "wsj"


def test_normalize_platform_fallback():
    assert _normalize_platform("", "rsshub") == "rsshub"
    assert _normalize_platform("", "rss") == "rss"
