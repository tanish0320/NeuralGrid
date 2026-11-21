from __future__ import annotations

import json
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for NeuralGrid backend and TwinNode controller."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API & Persistence
    neuralgrid_api_host: str = "0.0.0.0"
    neuralgrid_api_port: int = 8000
    neuralgrid_env: str = "demo"
    neuralgrid_db_path: str = "data/neuralgrid.db"
    neuralgrid_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    neuralgrid_default_seed: int = 42
    neuralgrid_tick_interval_seconds: float = 1.5

    # EventSense Controls
    eventsense_enabled: bool = True
    eventsense_enable_gdelt: bool = True
    eventsense_enable_rss: bool = True
    eventsense_enable_crawl4ai: bool = True
    eventsense_max_candidates: int = Field(default=5, ge=1, le=10)
    eventsense_max_crawl_pages: int = Field(default=5, ge=1, le=5)
    eventsense_crawl_timeout_seconds: int = Field(default=30, ge=1, le=120)
    eventsense_crawl_concurrency: int = Field(default=1, ge=1, le=1)
    eventsense_min_domain_delay_seconds: float = Field(default=3.0, ge=0.0, le=60.0)
    eventsense_check_robots: bool = True
    eventsense_user_agent: str = "NeuralGridEventSense/0.1"
    eventsense_max_text_bytes: int = Field(default=200_000, ge=1024, le=1_000_000)
    eventsense_allowed_domains: str = ""
    eventsense_rss_feeds: str = ""
    eventsense_allow_seeded_fallback: bool = True
    demo_event_id: str = "palace-grounds-demo"

    gdelt_enabled: bool = True
    gdelt_timespan: str = "7d"
    gdelt_max_records: int = Field(default=10, ge=1, le=25)
    gdelt_min_interval_seconds: float = Field(default=6.0, ge=0.0, le=60.0)

    # Risk thresholds (rule-based)
    risk_util_moderate: float = 70.0
    risk_util_high: float = 85.0
    risk_util_critical: float = 95.0
    risk_latency_moderate_ms: float = 30.0
    risk_latency_high_ms: float = 45.0
    risk_latency_critical_ms: float = 80.0

    # Planner weights and limits
    w1_overload: float = 0.45
    w2_latency: float = 0.30
    w3_energy: float = 0.15
    w4_churn: float = 0.10
    plan_expiry_seconds: int = 600
    plan_max_actions: int = 8

    # TwinNode Controller & Auth
    twinnode_controller_url: str = "http://127.0.0.1:8000"
    twinnode_agent_host: str = "0.0.0.0"
    twinnode_agent_port: int = 8101
    twinnode_node_id: str = "NODE-TANISH"
    twinnode_node_token: str = "dev-token-tanish"
    twinnode_node_tokens: str = '{"NODE-TANISH":"dev-token-tanish","NODE-JUNAID":"dev-token-junaid"}'
    twinnode_heartbeat_interval_seconds: float = 2.0
    twinnode_heartbeat_timeout_seconds: float = 10.0
    twinnode_task_lease_seconds: float = 30.0
    twinnode_max_retries: int = 2

    @property
    def allowed_domains_set(self) -> set[str]:
        """Return configured allow-listed domains; empty set fails closed."""
        raw = (self.eventsense_allowed_domains or "").strip()
        if not raw:
            return set()
        domains: set[str] = set()
        for part in raw.split(","):
            cleaned = part.strip().lower().rstrip(".")
            if not cleaned or cleaned == "replace-with-approved-domain-list":
                continue
            domains.add(cleaned)
        return domains

    @property
    def rss_feeds_list(self) -> list[str]:
        raw = (self.eventsense_rss_feeds or "").strip()
        if not raw:
            return []
        feeds: list[str] = []
        for part in raw.split(","):
            cleaned = part.strip()
            if not cleaned or cleaned == "replace-with-approved-feed-list":
                continue
            feeds.append(cleaned)
        return feeds

    @property
    def cors_origins_list(self) -> list[str]:
        origins = [item.strip() for item in self.neuralgrid_cors_origins.split(",") if item.strip()]
        return [origin for origin in origins if origin != "*"]

    @property
    def node_tokens_map(self) -> dict[str, str]:
        raw = (self.twinnode_node_tokens or "").strip()
        tokens: dict[str, str] = {}
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                            tokens[k.strip()] = v.strip()
            except json.JSONDecodeError:
                pass
        elif raw:
            for item in raw.split(","):
                if "=" in item:
                    k, v = item.split("=", 1)
                    if k.strip() and v.strip():
                        tokens[k.strip()] = v.strip()
        if self.twinnode_node_id and self.twinnode_node_token and self.twinnode_node_token != "GENERATE_A_RANDOM_LOCAL_TOKEN":
            tokens.setdefault(self.twinnode_node_id, self.twinnode_node_token)
        return tokens


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
