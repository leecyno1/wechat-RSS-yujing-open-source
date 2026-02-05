import json
from typing import Any

import httpx


class OpenAICompatError(Exception):
    pass


def _chat_completions_url(api_url: str) -> str:
    base = str(api_url or "").strip()
    if not base:
        return ""
    return base.rstrip("/") + "/chat/completions"


async def _chat_content(
    *,
    model: str,
    api_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    timeout: float = 60.0,
) -> str:
    if not api_url:
        raise OpenAICompatError("Missing api_url")
    if not api_key:
        raise OpenAICompatError("Missing api_key")
    if not model:
        raise OpenAICompatError("Missing model")

    url = _chat_completions_url(api_url)
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"model": model, "messages": messages, "temperature": 0.2}

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise OpenAICompatError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        data = resp.json()

    try:
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        raise OpenAICompatError(f"Invalid response shape: {e}")


async def openai_compat_chat_json(
    *,
    model: str,
    api_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    timeout: float = 60.0,
) -> dict[str, Any]:
    content = await _chat_content(
        model=model, api_url=api_url, api_key=api_key, messages=messages, timeout=timeout
    )
    try:
        return json.loads(content)
    except Exception as e:
        raise OpenAICompatError(f"Model did not return valid JSON: {e}; content={content[:500]}")


async def openai_compat_chat_text(
    *,
    model: str,
    api_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    timeout: float = 60.0,
) -> str:
    return await _chat_content(
        model=model, api_url=api_url, api_key=api_key, messages=messages, timeout=timeout
    )

