from __future__ import annotations

from typing import Any, Dict, Optional

from openai import OpenAI

from app.core.config import get_settings


_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        s = get_settings()
        if not s.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is missing in environment/.env")
        _client = OpenAI(api_key=s.OPENAI_API_KEY)
    return _client


def chat_json(system: str, user: str, *, model: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns a JSON object by using OpenAI structured output via response_format.
    """
    s = get_settings()
    client = get_openai_client()
    m = model or s.OPENAI_MODEL

    resp = client.chat.completions.create(
        model=m,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    content = resp.choices[0].message.content or "{}"
    import json
    return json.loads(content)
