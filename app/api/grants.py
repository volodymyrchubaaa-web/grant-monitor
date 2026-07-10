from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Grant
from app.pipeline.run import run_pipeline
from app.schemas import GrantOut, RefreshResult

router = APIRouter(prefix="/api")


@router.get("/grants", response_model=list[GrantOut])
def list_grants(
    sector: str | None = None,
    needs_partner_org: bool | None = None,
    is_oms_eligible: bool | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> list[Grant]:
    query = db.query(Grant)
    if sector:
        query = query.filter(Grant.sector == sector)
    if needs_partner_org is not None:
        query = query.filter(Grant.needs_partner_org == needs_partner_org)
    if is_oms_eligible is not None:
        query = query.filter(Grant.is_oms_eligible == is_oms_eligible)
    if status:
        query = query.filter(Grant.status == status)
    return query.order_by(Grant.deadline.is_(None), Grant.deadline.asc()).all()


@router.get("/grants/{grant_id}", response_model=GrantOut)
def get_grant(grant_id: int, db: Session = Depends(get_db)) -> Grant:
    grant = db.get(Grant, grant_id)
    if grant is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Grant not found")
    return grant


@router.post("/refresh", response_model=RefreshResult)
def refresh(db: Session = Depends(get_db)) -> dict[str, int]:
    return run_pipeline(db)
