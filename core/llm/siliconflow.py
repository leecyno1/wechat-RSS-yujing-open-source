import json
from typing import Any

import httpx


class SiliconFlowError(Exception):
    pass


async def _siliconflow_chat_content(
    *,
    model: str,
    api_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    timeout: float = 60.0,
) -> str:
    if not api_url:
        raise SiliconFlowError("Missing SiliconFlow api_url (set llm.siliconflow.api_url or SILICONFLOW_API_URL).")
    if not api_key:
        raise SiliconFlowError("Missing SiliconFlow api_key (set llm.siliconflow.api_key or SILICONFLOW_API_KEY).")
    if not model:
        raise SiliconFlowError("Missing model (set llm.siliconflow.model).")

    url = api_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise SiliconFlowError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        data = resp.json()

    try:
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        raise SiliconFlowError(f"Invalid response shape: {e}")


async def siliconflow_chat_json(
    *,
    model: str,
    api_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    timeout: float = 60.0,
) -> dict[str, Any]:
    content = await _siliconflow_chat_content(
        model=model,
        api_url=api_url,
        api_key=api_key,
        messages=messages,
        timeout=timeout,
    )

    try:
        return json.loads(content)
    except Exception as e:
        raise SiliconFlowError(f"Model did not return valid JSON: {e}; content={content[:500]}")


async def siliconflow_chat_text(
    *,
    model: str,
    api_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    timeout: float = 60.0,
) -> str:
    return await _siliconflow_chat_content(
        model=model,
        api_url=api_url,
        api_key=api_key,
        messages=messages,
        timeout=timeout,
    )
