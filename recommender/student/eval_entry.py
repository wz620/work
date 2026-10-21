"""评价入口：把评价清单 Provider 赋给同一个 PROVIDERS 入口，供 `--mode evaluation` 自检。

不要被业务 API 导入；业务注册在 recommender/contracts.py 中完成。
用法：python -m recommender.check selfcheck --module recommender.student.eval_entry \
        --algorithm itemcf --mode evaluation --subject-id 14
"""
from pathlib import Path

from ..contracts import Algorithm, PROVIDERS
from .als import ALSProvider
from .cold_start import ColdStartProvider
from .content import ContentProvider
from .itemcf import ItemCFProvider
from .popular import PopularProvider

ROOT = Path(__file__).resolve().parents[2]
EVAL_MODELS = ROOT / "models" / "evaluation"
TRAIN = "evaluation/train.csv"

PROVIDERS[Algorithm.popular] = PopularProvider(EVAL_MODELS / "popular-v1" / "manifest.json", "popular-v1", TRAIN)
PROVIDERS[Algorithm.content] = ContentProvider(EVAL_MODELS / "content-v1" / "manifest.json", "content-v1", TRAIN)
PROVIDERS[Algorithm.itemcf] = ItemCFProvider(EVAL_MODELS / "itemcf-v1" / "manifest.json", "itemcf-v1", TRAIN)
PROVIDERS[Algorithm.als] = ALSProvider(EVAL_MODELS / "als-v1" / "manifest.json", "als-v1", TRAIN)
PROVIDERS[Algorithm.cold_start] = ColdStartProvider(
    EVAL_MODELS / "cold_start-v1" / "manifest.json", "cold_start-v1", "evaluation/cold-k5-support.csv")
