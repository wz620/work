"""S2：OpenAI 兼容 Chat Completions 客户端适配层。

复用镜像内已装的 `httpx`，不引入新依赖；`base_url` 为空时视为不可用，走本地规则兜底。
"""
from __future__ import annotations

from typing import Any

import httpx

from ..errors import APIError


class ChatClient:
    def __init__(self, base_url: str | None, api_key: str | None, model: str, timeout: float):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or "local-rules"
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.base_url and self.api_key)

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        if not self.available:
            raise APIError(503, "LLM_UNAVAILABLE", "未配置 LLM 服务")
        payload: dict[str, Any] = {"model": self.model, "messages": messages,
                                   "tools": tools, "tool_choice": "auto"}
        headers = {"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(self.base_url + "/chat/completions", json=payload, headers=headers)
        except httpx.HTTPError:
            raise APIError(502, "LLM_UNREACHABLE", "LLM 服务不可达") from None
        if response.status_code >= 400:
            raise APIError(502, "LLM_ERROR", "LLM 返回错误状态", {"status": response.status_code})
        try:
            return response.json()["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise APIError(502, "LLM_BAD_RESPONSE", "LLM 返回结构不可解析") from None
