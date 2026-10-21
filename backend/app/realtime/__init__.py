"""S3：Kafka 实时行为推荐（无外部服务时降级为进程内总线）。

事件 schema 见 ``event.py``，消费逻辑见 ``worker.py``，HTTP 入口见 ``router.py``。
本包只读取既有授权（`SELECT`）与 `recommender.contracts.recommend()`，不写数据库。
"""
