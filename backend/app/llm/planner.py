"""S2：无 LLM 时的确定性兜底规划器（关键词 → 工具调用）。

保证在没有任何 LLM 配置的离线环境下，/assistant/chat 仍可完整演示工具调用链路。
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_ALGORITHM = "itemcf"

HISTORY_WORDS = ("历史", "看过", "浏览", "评分", "喜欢过", "history", "rated", "watched")
RESULT_WORDS = ("结果", "批次", "落库", "batch")
MOVIE_WORDS = ("电影", "影片", "详情", "是什么", "movie")


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict


def _first_number(text: str) -> str | None:
    digits = ""
    for char in text:
        if char.isdigit():
            digits += char
            if len(digits) >= 19:
                break
        elif digits:
            break
    return digits or None


def plan(message: str, algorithm: str | None = None, limit: int | None = None) -> list[ToolCall]:
    text = message.strip().lower()
    calls: list[ToolCall] = []
    if any(word in text for word in HISTORY_WORDS):
        calls.append(ToolCall("get_user_history", {}))
    movie_id = _first_number(text)
    if movie_id and any(word in text for word in MOVIE_WORDS):
        calls.append(ToolCall("get_movie", {"movie_id": movie_id}))
    if any(word in text for word in RESULT_WORDS):
        calls.append(ToolCall("get_recommendation_results", {}))
    if any(word in text for word in ("推荐", "recommend", "感兴趣", "想看")) or not calls:
        arguments: dict = {"algorithm": algorithm or DEFAULT_ALGORITHM}
        if limit is not None:
            arguments["limit"] = limit
        calls.append(ToolCall("get_recommendations", arguments))
    return calls
