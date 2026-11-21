from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.app.core.state import AppContainer, get_container
from apps.api.app.schemas.verification import VerificationResultResponse, VerificationRunRequest

router = APIRouter(prefix="/verification", tags=["verification"])


@router.post("/run", response_model=VerificationResultResponse)
async def run_verification(
    request: VerificationRunRequest,
    container: AppContainer = Depends(get_container),
) -> VerificationResultResponse:
    return await container.verifier.verify(request)


@router.get("", response_model=list[VerificationResultResponse])
async def list_verifications(
    plan_id: UUID | None = Query(default=None),
    container: AppContainer = Depends(get_container),
) -> list[VerificationResultResponse]:
    return container.verification_repo.list_verifications(plan_id=plan_id)


@router.get("/{verification_id}", response_model=VerificationResultResponse)
async def get_verification(
    verification_id: UUID,
    container: AppContainer = Depends(get_container),
) -> VerificationResultResponse:
    record = container.verification_repo.get_verification(verification_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Verification {verification_id} not found")
    return record
