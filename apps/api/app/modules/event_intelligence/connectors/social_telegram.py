from __future__ import annotations

import logging
import os
import httpx
from apps.api.app.core.database import utc_now
from apps.api.app.modules.event_intelligence.connectors.base import EventSourceConnector, RawSourceItem
from apps.api.app.schemas.events import SourceHealthResult

logger = logging.getLogger("neuralgrid.eventsense.connector.telegram")


class TelegramConnector(EventSourceConnector):
    """Telegram Bot API / Public Channel Announcement Connector."""

    source_id = "src_telegram_events"
    platform = "TELEGRAM"
    display_name = "Telegram Public Bengaluru Event Announcements"
    base_url = "https://api.telegram.org"
    access_method = "API_TOKEN"
    default_reliability = 0.82

    def _get_token(self) -> str | None:
        token = getattr(self.settings, "telegram_bot_token", None) if self.settings else None
        return token or os.getenv("TELEGRAM_BOT_TOKEN")

    async def fetch(
        self, city: str, query_terms: list[str], max_records: int
    ) -> list[RawSourceItem]:
        token = self._get_token()
        if not token:
            logger.info("Telegram Bot API: No bot token configured; operating in awaiting-credentials state.")
            return []
        return []

    async def check_health(self) -> SourceHealthResult:
        token = self._get_token()
        if not token:
            return SourceHealthResult(
                source_id=self.source_id,
                connector_type=self.__class__.__name__,
                health_status="AWAITING_CREDENTIALS",
                message="Telegram Bot API token not configured in TELEGRAM_BOT_TOKEN environment variable.",
                last_check_at=utc_now(),
            )

        return SourceHealthResult(
            source_id=self.source_id,
            connector_type=self.__class__.__name__,
            health_status="HEALTHY",
            message="Telegram Bot API token configured.",
            last_check_at=utc_now(),
        )
