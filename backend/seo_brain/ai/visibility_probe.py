"""A bounded, on-demand web-search sample for the AI visibility pilot.

This samples the OpenAI *API*, not the consumer ChatGPT product. The raw
answer and its URL annotations are retained so a person can assess mentions.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import httpx


class ProbeUnavailable(Exception):
    pass


def probe_openai(question: str, locale: str, market: str, model: str, api_key: str) -> dict:
    payload = {
        "model": model,
        "input": f"Answer this buyer question naturally in {locale} for market {market}. "
                 "Use the web to verify current information and cite sources. "
                 f"Do not favor any brand. Question: {question}",
        "tools": [{"type": "web_search", "search_context_size": "low"}],
        "tool_choice": "required",
        "max_output_tokens": 1800,
        "store": False,
    }
    try:
        response = httpx.post(
            "https://api.openai.com/v1/responses", json=payload,
            headers={"Authorization": f"Bearer {api_key}"}, timeout=55,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        # Do not log the response body or credentials; upstream messages can
        # contain user supplied text or request details.
        raise ProbeUnavailable("OpenAI web search could not complete") from exc

    output = data.get("output") or []
    searched = any(item.get("type") == "web_search_call" and item.get("status") == "completed"
                   for item in output)
    answer_parts: list[str] = []
    citations: list[dict] = []
    offset = 0
    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") != "output_text":
                continue
            part = content.get("text") or ""
            answer_parts.append(part)
            for annotation in content.get("annotations") or []:
                if annotation.get("type") != "url_citation":
                    continue
                url = annotation.get("url") or ""
                if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
                    continue
                citations.append({"url": url, "kind": "inline",
                                  "position": offset + max(0, int(annotation.get("end_index") or 0))})
            offset += len(part) + 1
    answer = "\n".join(answer_parts).strip()
    if not searched or not answer or len(answer) > 30000:
        raise ProbeUnavailable("Web search returned no usable cited answer")
    unique: dict[str, dict] = {}
    for citation in citations:
        unique.setdefault(citation["url"], citation)
    return {"answer_text": answer, "citations": list(unique.values())[:60],
            "model": data.get("model") or model, "status": "complete" if data.get("status") == "completed" else "partial"}
