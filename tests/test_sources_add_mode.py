from apis import sources
from pydantic import ValidationError
import pytest


def test_as_bool_parsing():
    assert sources._as_bool(True) is True
    assert sources._as_bool(False) is False
    assert sources._as_bool("true") is True
    assert sources._as_bool("1") is True
    assert sources._as_bool("yes") is True
    assert sources._as_bool("on") is True
    assert sources._as_bool("false") is False
    assert sources._as_bool("0") is False
    assert sources._as_bool("", default=True) is True


def test_validate_source_on_add_default(monkeypatch):
    monkeypatch.setattr(sources.cfg, "get", lambda *args, **kwargs: "true")
    assert sources._validate_source_on_add_default() is True

    monkeypatch.setattr(sources.cfg, "get", lambda *args, **kwargs: "false")
    assert sources._validate_source_on_add_default() is False


def test_rsshub_preview_request_limit_supports_120():
    """UI may request >100 preview items when browsing platform routes."""
    req = sources.RsshubPreviewRequest.model_validate(
        {
            "route": "/zhihu/hot",
            "limit": 120,
        }
    )
    assert req.limit == 120


def test_rsshub_preview_request_limit_rejects_too_large():
    with pytest.raises(ValidationError):
        sources.RsshubPreviewRequest.model_validate(
            {
                "route": "/zhihu/hot",
                "limit": 800,
            }
        )


def test_fetch_feed_for_source_prefers_internal_rsshub(monkeypatch):
    called = []

    monkeypatch.setattr(sources, "_rsshub_internal_url", lambda: "http://rsshub:1200")

    def _fake_fetch(url: str):
        called.append(url)
        return {"feed_title": "ok", "items": []}

    monkeypatch.setattr(sources, "fetch_feed", _fake_fetch)

    parsed, used_url = sources._fetch_feed_for_source(
        "rsshub", "http://localhost:1201/toutiao/user/token/abc123"
    )

    assert parsed.get("feed_title") == "ok"
    assert used_url == "http://rsshub:1200/toutiao/user/token/abc123"
    assert called == ["http://rsshub:1200/toutiao/user/token/abc123"]


def test_fetch_feed_for_source_fallbacks_to_original_rsshub_url(monkeypatch):
    called = []

    monkeypatch.setattr(sources, "_rsshub_internal_url", lambda: "http://rsshub:1200")

    def _fake_fetch(url: str):
        called.append(url)
        if url.startswith("http://rsshub:1200/"):
            raise RuntimeError("internal failed")
        return {"feed_title": "fallback", "items": []}

    monkeypatch.setattr(sources, "fetch_feed", _fake_fetch)

    parsed, used_url = sources._fetch_feed_for_source(
        "rsshub", "http://localhost:1201/zhihu/hot"
    )

    assert parsed.get("feed_title") == "fallback"
    assert used_url == "http://localhost:1201/zhihu/hot"
    assert called == ["http://rsshub:1200/zhihu/hot", "http://localhost:1201/zhihu/hot"]
