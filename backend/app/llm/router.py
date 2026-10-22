"""S2：LLM 工具调用的只读 HTTP 入口。

配置了 LLM 时走 `ChatClient`（OpenAI 兼容）产出工具调用；未配置时走 `planner` 的
确定性关键词兜底（`mode="local_rules"`），保证离线环境仍可完整演示
"消息 → 工具调用 → 只读结果 → 回答"链路。

身份只从会话 JWT 推导，工具入参不接受任何身份字段；审计以单行 JSON 打到 stdout
（可选同时追加易失的 /tmp JSONL），**不建表、不落库**。
"""
from __future__ import annotations

from collections import deque
import json
import logging
from threading import Lock
import time

from fastapi import APIRouter, Request
from pydantic import Field

from ..errors import APIError
from ..schemas import Input
from ..security import ActorDependency
from . import tools
from .client import ChatClient
from .planner import ToolCall, plan

router = APIRouter(tags=["S2 LLM 工具调用"])
log = logging.getLogger("course_api")

# 只读容器仅 /tmp 可写，且随容器销毁；审计主通道仍是 stdout 结构化日志。
AUDIT_PATH = "/tmp/cinelab-assistant-audit.jsonl"
WINDOW_SECONDS = 60
MAX_SUMMARY_ITEMS = 10
SYSTEM_PROMPT = (
    "你是电影推荐助手。只能用提供的只读工具取数回答，不得编造电影或评分数据；"
    "调用者身份由服务端从会话推导，工具参数里没有也不需要身份字段。"
)


class AssistantRequest(Input):
    message: str = Field(min_length=1, max_length=500)
    # algorithm/limit 只在无 LLM 的本地规则兜底生效，LLM 明确不回带调用时用作缺省提示。
    algorithm: str | None = Field(default=None, max_length=32)
    limit: int | None = Field(default=None, ge=1, le=50)


class ToolCallRecord(Input):
    name: str
    arguments: dict
    status: str
    result: dict | None = None
    error: str | None = None


class AssistantResponse(Input):
    mode: str
    tool_calls: list[ToolCallRecord]
    answer: str
    request_id: str


_windows: dict[int, deque[float]] = {}
_window_lock = Lock()


def _rate_limit(account_id: int, per_minute: int) -> None:
    """进程内固定窗口限流：每个账号每分钟最多 per_minute 次。"""
    now = time.monotonic()
    with _window_lock:
        for key in [key for key, events in _windows.items() if not events or events[-1] <= now - WINDOW_SECONDS]:
            del _windows[key]
        events = _windows.setdefault(account_id, deque())
        while events and events[0] <= now - WINDOW_SECONDS:
            events.popleft()
        if len(events) >= per_minute:
            delay = max(1, int(WINDOW_SECONDS - (now - events[0])) + 1)
            raise APIError(429, "ASSISTANT_RATE_LIMITED", "助手调用过于频繁，请稍后再试",
                           headers={"Retry-After": str(delay)})
        events.append(now)


def _audit(record: dict) -> None:
    line = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    log.info("%s", line)
    try:
        with open(AUDIT_PATH, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        # 审计落盘是可选的易失通道，失败不影响请求。
        pass


def _client(settings) -> ChatClient:
    secret = settings.llm_api_key
    return ChatClient(settings.llm_base_url, secret.get_secret_value() if secret else None,
                      settings.llm_model, settings.llm_timeout_seconds)


def _plan_from_llm(client: ChatClient, message: str) -> tuple[list[ToolCall], str | None]:
    """调用 LLM 并把返回的 tool_calls 规整为 ToolCall；无工具调用时保留其文本回答。"""
    reply = client.complete([{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": message}], tools.TOOLS)
    calls: list[ToolCall] = []
    for raw in reply.get("tool_calls") or ():
        function = raw.get("function") if isinstance(raw, dict) else None
        if not isinstance(function, dict):
            raise APIError(422, "TOOL_ARGUMENT_INVALID", "LLM 返回的工具调用结构不合法")
        name, raw_arguments = function.get("name"), function.get("arguments")
        if not isinstance(name, str) or not isinstance(raw_arguments, (str, dict)):
            raise APIError(422, "TOOL_ARGUMENT_INVALID", "LLM 返回的工具调用结构不合法")
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
        except ValueError:
            raise APIError(422, "TOOL_ARGUMENT_INVALID", "LLM 返回的工具参数不是合法 JSON") from None
        if not isinstance(arguments, dict):
            raise APIError(422, "TOOL_ARGUMENT_INVALID", "工具参数必须是对象")
        calls.append(ToolCall(name, arguments))
    answer = reply.get("content")
    return calls, answer if isinstance(answer, str) and answer.strip() else None


def _run(call: ToolCall, request: Request, actor) -> ToolCallRecord:
    tools.check_call(call.name, call.arguments)
    try:
        result = tools.execute(call.name, call.arguments, request, actor)
    except APIError as exc:
        return ToolCallRecord(name=call.name, arguments=call.arguments, status="error", error=exc.code)
    return ToolCallRecord(name=call.name, arguments=call.arguments, status="ok", result=result)


def _summarize(records: list[ToolCallRecord]) -> str:
    parts: list[str] = []
    for record in records:
        if record.status != "ok":
            parts.append(f"调用 {record.name} 失败（{record.error}）")
            continue
        result = record.result or {}
        if record.name == "get_recommendations":
            items = result.get("items") or []
            ids = "、".join(str(item.get("movie_id")) for item in items[:MAX_SUMMARY_ITEMS])
            parts.append(f"按 {result.get('algorithm')}（模型 {result.get('model_version')}）生成 {len(items)} 条推荐：{ids}")
        elif record.name == "get_movie":
            if "movie" in result:
                movie = result["movie"]
                parts.append(f"电影 {movie.get('movie_id')}：{movie.get('title_zh') or movie.get('movielens_title')}")
            else:
                items = result.get("items") or []
                parts.append("标题匹配 {} 部电影：{}".format(
                    len(items), "、".join(str(item.get("movielens_title")) for item in items[:MAX_SUMMARY_ITEMS])))
        elif record.name == "get_user_history":
            parts.append(f"你的评分历史共 {result.get('rating_count')} 条，收藏 {len(result.get('favorites') or [])} 部")
        else:
            items = result.get("items") or []
            parts.append(f"已落库推荐结果 {len(items)} 条（主体 {result.get('subject_key')}）")
    return "；".join(parts) if parts else "未执行任何工具调用。"


@router.post("/assistant/chat", response_model=AssistantResponse)
def assistant_chat(payload: AssistantRequest, request: Request, actor: ActorDependency):
    settings = request.app.state.settings
    if not settings.enable_assistant:
        raise APIError(503, "ASSISTANT_DISABLED", "LLM 工具调用未启用")
    _rate_limit(actor.account_id, settings.assistant_rate_limit_per_minute)
    client = _client(settings)
    llm_answer = None
    if client.available:
        mode = "llm"
        calls, llm_answer = _plan_from_llm(client, payload.message)
    else:
        mode = "local_rules"
        calls = plan(payload.message, payload.algorithm, payload.limit)
    records = [_run(call, request, actor) for call in calls]
    subject_key = "app:" + str(actor.account_id)
    for record in records:
        _audit({"kind": "assistant_tool_call", "request_id": request.state.request_id, "mode": mode,
                "subject_key": subject_key, "name": record.name, "arguments": record.arguments,
                "status": record.status, "error": record.error})
    return AssistantResponse(mode=mode, tool_calls=records,
                             answer=llm_answer or _summarize(records),
                             request_id=request.state.request_id)


# ================ 推荐解释（扩展任务：实验 4+5） =================

def _local_explain(evidence: dict) -> str:
    """LLM 不可用时的确定性兜底解释：把 evidence 翻译成普通话。"""
    algo = evidence.get("algorithm", "?")
    movie = evidence.get("movie_id", "?")

    if not evidence.get("found"):
        return f"暂无法为电影 #{movie} 生成推荐依据（{evidence.get('reason', '证据不足')}）。"

    if algo == "content":
        genres = evidence.get("target_genres", [])
        contrib = evidence.get("contributing_genres", [])
        user_high = evidence.get("user_history_genres_sample", [])
        lines = [f"这部电影 #{movie} 的推荐依据来自 Content 内容匹配算法。"]
        if contrib:
            g_str = "、".join(f"{c['genre']}（权重 {c['profile_weight']:+.2f}）" for c in contrib)
            lines.append(f"你历史评分构建的兴趣画像里，这些类型分量与它匹配：{g_str}。")
        if genres:
            lines.append(f"它本身属于：{'、'.join(genres)}。")
        if user_high:
            sample = "、".join(f"#{u['movie_id']}（{u['rating']}分，{'/'.join(u['genres'])}）" for u in user_high[:3])
            lines.append(f"这与你之前高分评价过的 {sample} 等电影类型偏好一致。")
        return "".join(lines)

    if algo == "itemcf":
        contrib = evidence.get("top_contributions", [])
        lines = [f"这部电影 #{movie} 的推荐依据来自 ItemCF 物品协同过滤算法。"]
        if contrib:
            pairs = "、".join(
                f"#{c['seed_movie_id']}（评分 {c['rating']}，协同相似度 {c['similarity']:.3f}，贡献 {c['contribution']:+.3f}）"
                for c in contrib[:3]
            )
            lines.append(f"它与你评分过的 {pairs} 存在较高的协同相似度，这些共同评分模式让 ItemCF 给它打了高分。")
        return "".join(lines)

    return f"算法 {algo} 的推荐解释暂未实现。"


def _llm_explain(client: ChatClient, evidence: dict, movie_title: str) -> str:
    """调用 ChatClient 生成基于证据的中文解释。不允许编造任何数据。"""
    system = (
        "你是电影推荐解释助手。只能根据用户提供的 JSON 证据，用普通话解释为什么这部电影被推荐。"
        "绝对不能编造任何证据里没有的电影ID、评分、类型、相似度或算法行为。"
        "如果证据不足就如实说明。"
    )
    user_msg = (
        f"候选电影: {movie_title} (movie_id={evidence.get('movie_id')})\n"
        f"算法: {evidence.get('algorithm')}\n"
        f"计算依据（JSON）: {json.dumps(evidence, ensure_ascii=False)}\n"
        "请用 2-3 句中文解释为什么它被推荐，必须严格引用上面的依据。"
    )
    reply = client.complete([
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ], [])  # 解释不需要 tools
    content = reply.get("content", "")
    return content.strip() if isinstance(content, str) and content.strip() else "(LLM 返回为空)"


class ExplainRequest(Input):
    algorithm: str = Field(min_length=3, max_length=32)
    movie_id: str = Field(min_length=1, max_length=32)
    source: str = Field(default="ml", max_length=8)  # "ml" (历史用户) 或 "app" (当前登录)
    subject_id: str = Field(min_length=1, max_length=32)  # ml_user_id 字符串 或 account_id 数字字符串
    limit: int = Field(default=10, ge=1, le=50)


@router.post("/assistant/explain-recommendation")
def explain_recommendation(payload: ExplainRequest, request: Request):
    """
    给指定电影生成推荐依据 + AI 解释。

    流程：
      1. 找到该算法的 Provider，拿到 model_manifest_path
      2. 构建 RecommendationRequest，调 provider.rated() 拿用户历史评分
      3. 调算法 explain 函数收集真实依据
      4. ChatClient 可用 → 调 LLM 生成中文解释；不可用 → 本地模板兜底
    绝不破坏原有推荐 API。
    支持 source="ml"（历史匿名用户，不需要登录）和 source="app"（当前登录账号）。
    """
    from recommender.contracts import Algorithm, PROVIDERS, RecommendationRequest

    try:
        algo = Algorithm(payload.algorithm)
    except ValueError:
        raise APIError(422, "INVALID_ALGORITHM", f"不支持的算法: {payload.algorithm}")

    provider = PROVIDERS.get(algo)
    if provider is None:
        raise APIError(501, "ALGORITHM_NOT_IMPLEMENTED", f"算法 {payload.algorithm} 未实现")

    # 构建 request → 拿用户评分历史
    from ..config import DATASET, SPLIT
    subject_uid = int(payload.subject_id)
    rec_request = RecommendationRequest(payload.source, subject_uid, payload.limit, "business", DATASET, SPLIT)
    rated = provider.rated(rec_request)

    # 收集依据
    evidence = {"found": False, "algorithm": payload.algorithm, "movie_id": payload.movie_id}
    manifest = str(provider.model_manifest_path)

    if algo == Algorithm.content:
        from recommender.student.content_explain import explain as content_explain
        evidence = content_explain(manifest, payload.movie_id, rated, tuple())
    elif algo == Algorithm.itemcf:
        from recommender.student.itemcf_explain import explain as itemcf_explain
        from recommender.student.common import catalog_ids
        evidence = itemcf_explain(manifest, payload.movie_id, rated, catalog_ids())
    else:
        evidence["reason"] = f"算法 {payload.algorithm} 的解释逻辑暂未实现（Content/ItemCF 可用）"

    # 生成解释
    settings = request.app.state.settings
    movie_title = payload.movie_id  # 没查电影标题，用 id 占位
    explanation_mode = "local_rules"
    explanation = _local_explain(evidence)
    try:
        client = _client(settings)
        if client.available and evidence.get("found"):
            explanation = _llm_explain(client, evidence, movie_title)
            explanation_mode = "llm"
    except Exception as exc:
        log.warning("LLM explain 失败，降级到本地规则: %s", exc)

    # 审计
    _audit({"kind": "explain_recommendation", "request_id": request.state.request_id,
            "subject_key": f"{payload.source}:{payload.subject_id}",
            "algorithm": payload.algorithm, "movie_id": payload.movie_id,
            "evidence_found": evidence.get("found", False), "mode": explanation_mode})

    return {
        "algorithm": payload.algorithm,
        "movie_id": payload.movie_id,
        "subject": f"{payload.source}:{payload.subject_id}",
        "evidence": evidence,
        "explanation": explanation,
        "explanation_mode": explanation_mode,
    }
