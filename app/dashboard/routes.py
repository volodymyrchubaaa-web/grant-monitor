from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Grant
from app.pipeline.run import run_pipeline

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/")
def dashboard(
    request: Request,
    sector: str = "",
    is_oms_eligible: str = "",
    status: str = "",
    db: Session = Depends(get_db),
):
    query = db.query(Grant)
    if sector:
        query = query.filter(Grant.sector == sector)
    if is_oms_eligible in ("true", "false"):
        query = query.filter(Grant.is_oms_eligible == (is_oms_eligible == "true"))
    if status:
        query = query.filter(Grant.status == status)

    grants = query.order_by(Grant.deadline.is_(None), Grant.deadline.asc()).all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "grants": grants,
            "sectors": settings.strategic_sectors,
            "filters": {"sector": sector, "is_oms_eligible": is_oms_eligible, "status": status},
        },
    )


@router.post("/refresh")
def refresh(db: Session = Depends(get_db)):
    run_pipeline(db)
    return RedirectResponse(url="/", status_code=303)
