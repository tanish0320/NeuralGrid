from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from apps.api.app.core.state import AppContainer, get_container
from apps.api.app.schemas.verification import AuditEventRecord

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventRecord])
async def list_audit_events(
    entity_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    container: AppContainer = Depends(get_container),
) -> list[AuditEventRecord]:
    return container.verification_repo.list_audit_events(entity_id=entity_id, limit=limit)
