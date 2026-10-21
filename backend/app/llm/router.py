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
