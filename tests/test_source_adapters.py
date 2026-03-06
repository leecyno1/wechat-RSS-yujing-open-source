import hashlib

from core.source.adapters import build_rsshub_feed_url, normalize_source_key, parse_feed_text


RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example RSS</title>
    <link>https://example.com</link>
    <description>demo</description>
    <item>
      <title>First item</title>
      <link>https://example.com/posts/1</link>
      <guid>post-1</guid>
      <description>Summary 1</description>
      <pubDate>Fri, 06 Mar 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


ATOM_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Atom</title>
  <id>https://atom.example.com/</id>
  <updated>2026-03-06T10:00:00Z</updated>
  <entry>
    <title>Atom item</title>
    <id>tag:example.com,2026:atom-1</id>
    <link href="https://atom.example.com/posts/1" />
    <summary>Atom summary</summary>
    <updated>2026-03-06T09:30:00Z</updated>
  </entry>
</feed>
"""


def test_parse_rss_text():
    parsed = parse_feed_text(RSS_SAMPLE, source_url="https://example.com/rss.xml")
    assert parsed["feed_title"] == "Example RSS"
    assert len(parsed["items"]) == 1
    first = parsed["items"][0]
    assert first["title"] == "First item"
    assert first["link"] == "https://example.com/posts/1"
    assert first["description"] == "Summary 1"
    assert isinstance(first["publish_time"], int)
    assert first["publish_time"] > 0


def test_parse_atom_text():
    parsed = parse_feed_text(ATOM_SAMPLE, source_url="https://atom.example.com/feed")
    assert parsed["feed_title"] == "Example Atom"
    assert len(parsed["items"]) == 1
    first = parsed["items"][0]
    assert first["title"] == "Atom item"
    assert first["link"] == "https://atom.example.com/posts/1"
    assert first["description"] == "Atom summary"
    assert isinstance(first["publish_time"], int)
    assert first["publish_time"] > 0


def test_build_rsshub_feed_url():
    assert (
        build_rsshub_feed_url("https://rsshub.example.com/", "/zhihu/hotlist")
        == "https://rsshub.example.com/zhihu/hotlist"
    )


def test_normalize_source_key_is_stable():
    key = normalize_source_key("rss", "https://example.com/rss.xml")
    expected = hashlib.sha1("rss:https://example.com/rss.xml".encode("utf-8")).hexdigest()
    assert key == expected
