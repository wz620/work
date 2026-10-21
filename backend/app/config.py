from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DATASET = "rec-course-v3-train5-1.0.0"
SPLIT = "temporal-v1-cold500-train5-v3"
SCHEMA = "student-eight-v3"
MANIFEST_SHA = "fcfb9a195a56709773696aab02f769c691778af0eb433a1e0778a71c4b289b9e"

# S1 缺省召回来源；与 recommender.student.fusion.DEFAULT_SOURCES 保持一致（此处不反向导入）。
DEFAULT_FUSION_SOURCES = ["popular", "content", "itemcf", "als", "cold_start"]
# S3 缺省实时算法：必须是 Algorithm 枚举内的已实现算法（RRF 是融合层，不是第六种算法）。
DEFAULT_REALTIME_ALGORITHM = "itemcf"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", extra="forbid", hide_input_in_errors=True)
    env: Literal["development", "production"] = "production"
    origin: str
    jwt_secret: SecretStr
    jwt_minutes: int = Field(default=30, ge=1, le=60)
    cookie_secure: bool = True
    db_host: str = "127.0.0.1"
    db_port: int = Field(default=3306, ge=1, le=65535)
    db_name: str
    db_user: str
    db_password: SecretStr
    db_socket: str | None = None
    db_ssl_ca: str | None = None
    manifest_path: Path = ROOT / "data/packages" / DATASET / "manifest.json"

    # ---- S1 多路召回的 RRF 融合（默认开启；API 容器 env 为白名单，离线走默认即自洽）----
    enable_fusion: bool = True
    fusion_k: int = Field(default=60, ge=0, le=1000)
    fusion_sources: list[str] = Field(default_factory=lambda: list(DEFAULT_FUSION_SOURCES))
    fusion_limit: int = Field(default=10, ge=1, le=50)

    # ---- S2 LLM 工具调用（base_url/api_key 为空即降级为本地规则兜底）----
    enable_assistant: bool = True
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str = "local-rules"
    llm_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    assistant_rate_limit_per_minute: int = Field(default=20, ge=1, le=10000)

    # ---- S3 Kafka 实时行为推荐（bootstrap 为空即使用进程内总线）----
    enable_realtime: bool = True
    kafka_bootstrap: str | None = None
    kafka_topic: str = "cinelab.behavior.v1"
    kafka_group: str = "cinelab-rt-recsys"
    realtime_window_events: int = Field(default=20, ge=1, le=1000)
    realtime_algorithm: str = DEFAULT_REALTIME_ALGORITHM
    realtime_cold_start_algorithm: str = "cold_start"
    realtime_limit: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def secure_settings(self) -> "Settings":
        url = urlsplit(self.origin)
        if url.scheme not in {"http", "https"} or not url.hostname or url.path or url.query or url.fragment or url.username is not None:
            raise ValueError("APP_ORIGIN must be one exact HTTP(S) origin without a trailing slash")
        if len(self.jwt_secret.get_secret_value().encode()) < 32:
            raise ValueError("APP_JWT_SECRET requires at least 32 bytes of independently generated secret")
        if not self.db_user or self.db_user.lower() == "root":
            raise ValueError("The API requires an independent non-root application database user")
        if not self.db_password.get_secret_value():
            raise ValueError("The independent application database password cannot be empty")
        if self.env == "production" and (not self.cookie_secure or url.scheme != "https"):
            raise ValueError("Production requires HTTPS and Secure cookies")
        if self.llm_base_url and urlsplit(self.llm_base_url).scheme not in {"http", "https"}:
            raise ValueError("APP_LLM_BASE_URL must be an HTTP(S) base URL")
        # 延迟导入：新增开关的取值必须落在已注册算法枚举内，避免运行期才发现拼写错误。
        from recommender.contracts import Algorithm
        allowed = {algorithm.value for algorithm in Algorithm}
        if not self.fusion_sources or any(name not in allowed for name in self.fusion_sources):
            raise ValueError("APP_FUSION_SOURCES accepts only registered algorithm names")
        if self.realtime_algorithm not in allowed or self.realtime_cold_start_algorithm not in allowed:
            raise ValueError("APP_REALTIME_*_ALGORITHM must be a registered algorithm name")
        return self
