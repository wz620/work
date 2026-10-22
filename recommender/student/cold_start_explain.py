"""Cold Start 推荐算法的依据收集。

课程设计里 Cold Start v1 用的 item_features.json 和 Content v1 **完全相同**
（MD5 一致），公式也完全一样：profile += (rating - 2.5) * vec。所以 Cold Start
的推荐依据和 Content 相同——两者在这个模型版本里是同一个算法参数。

这里直接复用 content_explain 的实现，只标注 algorithm="cold_start"。
"""
from __future__ import annotations

from recommender.student.content_explain import explain as _content_explain


def explain(manifest: str, movie_id: str, rated: dict, catalog_ids: tuple[str, ...]) -> dict:
    """复用 content_explain，只把 algorithm 改名。"""
    evidence = _content_explain(manifest, movie_id, rated, catalog_ids)
    evidence["algorithm"] = "cold_start"
    evidence["note"] = (
        "课程设计：cold_start-v1 与 content-v1 使用完全相同的 item_features.json "
        "（MD5 一致）和加权求和公式，因此两者依据相同。"
    )
    return evidence
