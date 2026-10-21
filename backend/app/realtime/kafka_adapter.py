"""S3：实时行为推荐 —— Kafka / 进程内总线的共同入口。

外部服务（Kafka）在本包内一律延迟导入、函数内判断可用性：缺失时抛
`AdapterUnavailable`，由上层降级到 `InProcBus`。真实 Kafka 只替换"事件来源"，
消费到的事件仍走 `worker.RealtimeWorker.consume()` 这同一段逻辑。
"""
from __future__ import annotations

import json


class AdapterUnavailable(RuntimeError):
    """kafka-python 未安装或客户端初始化失败时的降级信号。"""


def _servers(bootstrap: str) -> list[str]:
    return [node.strip() for node in bootstrap.split(",") if node.strip()]


def producer(bootstrap: str):
    try:
        from kafka import KafkaProducer
    except ImportError:
        raise AdapterUnavailable("kafka-python 未安装") from None
    return KafkaProducer(bootstrap_servers=_servers(bootstrap), acks="all", linger_ms=50,
                         value_serializer=lambda value: _encode(value))


def consumer(bootstrap: str, topic: str, group: str):
    try:
        from kafka import KafkaConsumer
    except ImportError:
        raise AdapterUnavailable("kafka-python 未安装") from None
    return KafkaConsumer(topic, bootstrap_servers=_servers(bootstrap), group_id=group,
                         auto_offset_reset="latest", enable_auto_commit=False,
                         value_deserializer=lambda value: _decode(value))


def _encode(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _decode(value: bytes):
    return json.loads(value.decode("utf-8"))
