"""S2：只读工具集 —— OpenAI function schema 与处理器。

四个工具全部只读，身份只从 JWT 推导（不接受调用方传入的身份）；不写数据库。
`execute()` 对参数做白名单与类型校验，非法参数抛 422。
"""
from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import text

from recommender.business import read_history
from recommender.contracts import Algorithm, RecommendationRequest
from ..catalog import public_row
from ..config import DATASET, SPLIT
from ..errors import APIError
from ..experiments import invoke

MAX_ITEMS = 20

TOOLS: list[dict] = [
    {"type": "function", "function": {
        "name": "get_recommendations",
        "description": "按指定推荐算法为当前登录用户生成推荐电影清单，可按关键词（类型或标题）过滤。",
        "parameters": {"type": "object", "properties": {
            "algorithm": {"type": "string", "enum": [a.value for a in Algorithm],
                          "description": "推荐算法名"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "description": "返回条数"},
            "q": {"type": "string", "maxLength": 100,
                  "description": "可选关键词：类型（科幻/喜剧/动画…）或标题，会从真实电影库过滤"}},
            "required": ["algorithm"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "get_movie",
        "description": "查询单部电影的元数据，或按标题关键词搜索电影。",
        "parameters": {"type": "object", "properties": {
            "movie_id": {"type": "string", "description": "电影的 movie_id（数字字符串）"},
            "q": {"type": "string", "maxLength": 100, "description": "标题关键词"}},
            "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "get_user_history",
        "description": "读取当前登录用户自己的评分历史。",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "get_recommendation_results",
        "description": "查询已落库的推荐结果（按批次或主体）。当前业务库该表可能为空。",
        "parameters": {"type": "object", "properties": {
            "batch_id": {"type": "string", "description": "批次ID"},
            "subject_key": {"type": "string", "description": "主体键，如 app:12"}},
            "additionalProperties": False}}},
]

_ALLOWED = {tool["function"]["name"]: set(tool["function"]["parameters"]["properties"]) for tool in TOOLS}


def _require_algorithm(value: Any) -> Algorithm:
    if not isinstance(value, str):
        raise APIError(422, "TOOL_ARGUMENT_INVALID", "algorithm 必须是字符串")
    try:
        return Algorithm(value)
    except ValueError:
        raise APIError(422, "TOOL_ARGUMENT_INVALID", "未知的推荐算法", {"allowed": [a.value for a in Algorithm]}) from None


def _limit(value: Any) -> int:
    if value is None:
        return 10
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 50:
        raise APIError(422, "TOOL_ARGUMENT_INVALID", "limit 必须是 1..50 的整数")
    return value


def _check_arguments(name: str, arguments: dict) -> None:
    if not isinstance(arguments, dict):
        raise APIError(422, "TOOL_ARGUMENT_INVALID", "工具参数必须是对象")
    unknown = sorted(set(arguments) - _ALLOWED[name])
    if unknown:
        raise APIError(422, "TOOL_ARGUMENT_INVALID", "工具参数包含未知字段", {"unknown": unknown})


def _get_recommendations(arguments: dict, request, actor) -> dict:
    algorithm = _require_algorithm(arguments.get("algorithm"))
    limit = _limit(arguments.get("limit"))
    keyword = arguments.get("q")
    if keyword is not None and (not isinstance(keyword, str) or not keyword.strip()):
        raise APIError(422, "TOOL_ARGUMENT_INVALID", "q 必须是非空字符串")

    # ============ 有关键词 q → 直接查真实 DB（genre 过滤 or 标题搜索） ============
    if keyword:
        escaped = keyword.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_")
        with request.app.state.db.connection() as conn:
            rows = conn.execute(text(
                "SELECT movie_id, movielens_title, title_zh, genres "
                "FROM movies "
                "WHERE LOWER(genres) LIKE LOWER(:term) ESCAPE '!' "
                "   OR LOWER(movielens_title) LIKE LOWER(:term) ESCAPE '!' "
                "   OR LOWER(COALESCE(title_zh,'')) LIKE LOWER(:term) ESCAPE '!' "
                "ORDER BY movie_id DESC LIMIT :limit"),
                {"term": "%" + escaped + "%", "limit": limit}).mappings().all()
        items = []
        for rank, row in enumerate(rows, 1):
            items.append({
                "movie_id": str(row["movie_id"]),
                "rank": rank,
                "score": float(row["movie_id"]),  # 无 popularity 列，用 movie_id 作为确定性排序依据
                "title_zh": row.get("title_zh") or row["movielens_title"],
                "genres": row.get("genres"),
            })
        return {
            "algorithm": "keyword_search",  # 不走个性化算法
            "model_version": "db-direct",
            "items": items,
            "q": keyword,
            "note": f"按关键词「{keyword}」从真实电影库 genres/标题匹配，共 {len(items)} 条",
        }

    # ============ 无关键词 → 走真实个性化算法 ============
    result = invoke(algorithm, "app", actor.account_id, limit)
    return {
        "algorithm": result.algorithm.value,
        "model_version": result.model_version,
        "items": [{"movie_id": item.movie_id, "rank": item.rank, "score": item.score} for item in result.items],
        "q": None,
    }


def _get_movie(arguments: dict, request, actor) -> dict:
    movie_id = arguments.get("movie_id")
    keyword = arguments.get("q")
    if (movie_id is None) == (keyword is None):
        raise APIError(422, "TOOL_ARGUMENT_INVALID", "必须且只能提供 movie_id 或 q 之一")
    with request.app.state.db.connection() as conn:
        if movie_id is not None:
            if not isinstance(movie_id, str) or not movie_id.isdigit() or movie_id.startswith("0"):
                raise APIError(422, "TOOL_ARGUMENT_INVALID", "movie_id 必须是正整数数字字符串")
            row = conn.execute(text("SELECT * FROM movies WHERE movie_id=:id"), {"id": int(movie_id)}).mappings().first()
            if row is None:
                raise APIError(404, "MOVIE_NOT_FOUND", "电影不存在")
            return {"movie": public_row(row)}
        if not isinstance(keyword, str) or not keyword.strip():
            raise APIError(422, "TOOL_ARGUMENT_INVALID", "q 必须是非空字符串")
        escaped = keyword.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_")
        rows = conn.execute(text("SELECT movie_id,movielens_title,title_zh,genres,release_year "
            "FROM movies WHERE LOWER(movielens_title) LIKE LOWER(:term) ESCAPE '!' "
            "OR LOWER(COALESCE(title_zh,'')) LIKE LOWER(:term) ESCAPE '!' ORDER BY movie_id LIMIT :limit"),
            {"term": "%" + escaped + "%", "limit": MAX_ITEMS}).mappings().all()
    return {"items": [public_row(row) for row in rows]}


def _get_user_history(arguments: dict, request, actor) -> dict:
    history = read_history(RecommendationRequest("app", actor.account_id, 10, "business", DATASET, SPLIT))
    ratings = [{"movie_id": fb.movie_id, "rating": fb.rating} for fb in history.ratings[:MAX_ITEMS]]
    return {"subject_key": history.subject_key, "rating_count": len(history.ratings),
            "favorites": list(history.favorite_movie_ids[:MAX_ITEMS]), "ratings": ratings}


def _get_recommendation_results(arguments: dict, request, actor) -> dict:
    subject_key = arguments.get("subject_key") or ("app:" + str(actor.account_id))
    batch_id = arguments.get("batch_id")
    clauses, values = ["subject_key=:subject"], {"subject": subject_key, "limit": MAX_ITEMS}
    if batch_id is not None:
        if not isinstance(batch_id, str):
            raise APIError(422, "TOOL_ARGUMENT_INVALID", "batch_id 必须是字符串")
        clauses.append("batch_id=:batch")
        values["batch"] = batch_id
    with request.app.state.db.connection() as conn:
        rows = conn.execute(text("SELECT batch_id,algorithm,model_version,movie_id,rank_pos,score,fusion_rank "
            "FROM recommendation_results WHERE " + " AND ".join(clauses) +
            " ORDER BY rank_pos LIMIT :limit"), values).mappings().all()
    return {"subject_key": subject_key, "items": [public_row(row) for row in rows]}


HANDLERS: dict[str, Callable[[dict, Any, Any], dict]] = {
    "get_recommendations": _get_recommendations,
    "get_movie": _get_movie,
    "get_user_history": _get_user_history,
    "get_recommendation_results": _get_recommendation_results,
}


def check_call(name: str, arguments: dict) -> None:
    """预校验工具名与参数字段（不执行），供 LLM 返回的调用在执行业务前短路。"""
    if name not in HANDLERS:
        raise APIError(422, "TOOL_ARGUMENT_INVALID", "未知工具名", {"allowed": sorted(HANDLERS)})
    _check_arguments(name, arguments)


def execute(name: str, arguments: dict, request, actor) -> dict:
    check_call(name, arguments)
    return HANDLERS[name](arguments, request, actor)
