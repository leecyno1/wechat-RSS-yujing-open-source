#!/usr/bin/env python3
"""
Basic sanity tests for insights extraction and LLM client guards.

Run:
  python test_insights.py
"""

from core.insights.extract import extract_headings, extract_summary
from core.llm.siliconflow import SiliconFlowError, siliconflow_chat_json


def test_extract_basic():
    html = "<h1>一级标题</h1><p>第一段内容用于摘要提取。</p><h2>二级A</h2><p>更多</p><h2>二级B</h2>"
    summary = extract_summary("这是digest摘要", html, max_len=200)
    assert summary == "这是digest摘要"
    headings = extract_headings(html, levels=(1, 2))
    assert headings and headings[0]["level"] == 1 and headings[0]["text"] == "一级标题"
    assert any(h["text"] == "二级A" for h in headings)
    assert any(h["text"] == "二级B" for h in headings)


async def test_llm_guardrails():
    try:
        await siliconflow_chat_json(
            model="",
            api_url="",
            api_key="",
            messages=[{"role": "user", "content": "{}"}],
        )
    except SiliconFlowError:
        return
    raise AssertionError("Expected SiliconFlowError for missing config")


def main():
    test_extract_basic()

    import asyncio
    asyncio.run(test_llm_guardrails())
    print("✅ test_insights.py passed")


if __name__ == "__main__":
    main()

