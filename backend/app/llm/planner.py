"""S2：无 LLM 时的确定性兜底规划器（关键词 → 工具调用）。

保证在没有任何 LLM 配置的离线环境下，/assistant/chat 仍可完整演示工具调用链路。
核心改进：识别意图关键词、轮换算法、感知用户的「换些/换一批」请求。
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

# 轮换序列：itemcf → content → als → popular → cold_start → itemcf …
_ALGO_CYCLE = itertools.cycle(["itemcf", "content", "als", "popular", "cold_start"])

# 中文 genre → 英文 genres（DB 里存的是英文 pipe 分隔，如 "Comedy|Romance"）
# 一个中文词可能对应多个英文 genre（如 科幻 → Sci-Fi + Fantasy）
_GENRE_CN_TO_EN: dict[str, list[str]] = {
    "科幻":     ["Sci-Fi"],
    "喜剧":     ["Comedy"],
    "动画":     ["Animation"],
    "恐怖":     ["Horror"],
    "动作":     ["Action"],
    "爱情":     ["Romance"],
    "剧情":     ["Drama"],
    "冒险":     ["Adventure"],
    "犯罪":     ["Crime"],
    "悬疑":     ["Mystery"],
    "惊悚":     ["Thriller"],
    "奇幻":     ["Fantasy"],
    "战争":     ["War"],
    "西部":     ["Western"],
    "纪录片":   ["Documentary"],
    "家庭":     ["Children"],
    "音乐":     ["Musical"],
    "综艺":     ["Musical"],
}

# genre 关键词 → 同时用作过滤 q（命中后会真实查询 DB genres 字段）
_GENRE_FILTERS = list(_GENRE_CN_TO_EN.keys()) + [
    "music", "musical", "animation", "comedy", "scifi", "horror",
    "action", "romance", "drama", "adventure", "crime", "thriller",
    "fantasy", "war", "western", "documentary", "family",
]

# 意图 → 算法映射（用户说的不是算法名，而是"给我科幻的"→ 用 content 最合适）
_GENRE_ALGO = {
    # genre hints → content（唯一用 genres 的算法）
    **{g: "content" for g in _GENRE_FILTERS},
    # 算法直称
    "itemcf": "itemcf", "协同": "itemcf", "协同过滤": "itemcf",
    "content": "content", "内容": "content",
    "als": "als", "矩阵分解": "als",
    "popular": "popular", "热门": "popular",
    "cold": "cold_start", "冷启动": "cold_start",
}

HISTORY_WORDS = ("历史", "看过", "浏览", "评分", "喜欢过", "history", "rated", "watched")
RESULT_WORDS = ("结果", "批次", "落库", "batch")
MOVIE_WORDS = ("电影", "影片", "详情", "是什么", "movie")
CYCLE_WORDS = ("换些", "换一批", "换点", "不同的", "再来", "其他", "重新", "换个", "再推荐")


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


def _detect_algorithm(text: str, prefer_diversity: bool) -> tuple[str, str | None]:
    """从自然语言推断 (推荐算法, genre过滤词)。prefer_diversity=True 时轮换算法。"""
    low = text.lower()
    for keyword, algo in _GENRE_ALGO.items():
        if keyword.lower() in low:
            # 命中 genre 关键词 → 翻译 DB 真实值（中文→英文 genres）
            if keyword in _GENRE_CN_TO_EN:
                # 中文：返回第一个英文 genre（SQL LIKE 单个值）
                q = _GENRE_CN_TO_EN[keyword][0]
            elif keyword in _GENRE_FILTERS:
                q = keyword  # 英文关键词直接用
            else:
                q = None
            return algo, q
    if prefer_diversity:
        return next(_ALGO_CYCLE), None
    return next(_ALGO_CYCLE), None  # 默认也轮换


def _detect_title_keyword(text: str) -> str | None:
    """从消息里提取可能的标题关键词（紧跟「电影 / 影片 / 片」后的非数字片段）。"""
    import re
    m = re.search(r"(?:电影|影片|片|推荐)\s*([\u4e00-\u9fa5A-Za-z·\-]{1,10})", text)
    if m:
        cand = m.group(1)
        if cand and cand not in {"推荐", "一些", "几部", "部"}:
            return cand
    return None


def _detect_limit(text: str) -> int | None:
    """从消息里提取数字作为 limit，比如「推荐 5 部」→ 5。"""
    m = re.search(r"(\d+)\s*(部|个|片|部电影)", text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 50:
            return n
    return None


def plan(message: str, algorithm: str | None = None, limit: int | None = None) -> list[ToolCall]:
    text = message.strip()
    calls: list[ToolCall] = []
    low = text.lower()

    # 1. 查询历史 / 评分
    if any(word in low for word in HISTORY_WORDS):
        calls.append(ToolCall("get_user_history", {}))

    # 2. 查询单部电影详情（必须有明确的「看/查/是什么/介绍」意图，不能只是推荐数字）
    movie_id = _first_number(text)
    if movie_id and any(word in low for word in ("是什么", "详情", "介绍", "叫什么", "哪部电影是", "这部电影", "查一下", "查看", "看看", "看下", "查一下这部")):
        calls.append(ToolCall("get_movie", {"movie_id": movie_id}))

    # 3. 查询已落库推荐结果
    if any(word in low for word in RESULT_WORDS):
        calls.append(ToolCall("get_recommendation_results", {}))

    # 4. 推荐（默认路径：没匹配到其他任何意图时也触发）
    wants_recommend = (not calls) or any(word in low for word in ("推荐", "recommend", "感兴趣", "想看", "推荐一些", "给我"))
    if wants_recommend:
        prefer_diversity = any(word in low for word in CYCLE_WORDS)
        picked_algo, picked_q = (algorithm or None, None) if algorithm else _detect_algorithm(text, prefer_diversity)
        args: dict = {"algorithm": picked_algo}
        resolved_limit = limit or _detect_limit(text)
        if resolved_limit:
            args["limit"] = resolved_limit
        # q 过滤：优先用 genre 关键词，否则尝试提取标题关键词
        if picked_q:
            args["q"] = picked_q
        else:
            title_q = _detect_title_keyword(text)
            if title_q:
                args["q"] = title_q
        calls.append(ToolCall("get_recommendations", args))

    return calls
