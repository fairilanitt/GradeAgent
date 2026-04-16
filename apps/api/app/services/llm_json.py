from __future__ import annotations

import json
from typing import Any


def flatten_llm_content(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = [flatten_llm_content(item) for item in content]
        return "\n".join(part for part in parts if part.strip())

    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("content"), str):
            return content["content"]
        return json.dumps(content, ensure_ascii=False)

    return str(content)


def extract_json_object(text: str) -> str:
    from app.services.llm_provider import ProviderConfigurationError

    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            stripped = "\n".join(lines[1:-1]).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ProviderConfigurationError("Model response did not contain a JSON object.")
    return stripped[start : end + 1]
