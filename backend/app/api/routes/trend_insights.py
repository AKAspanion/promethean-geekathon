"""API routes for the trend-insights agent.

POST /trend-insights/run
    Manually trigger the agent for a given OEM.
    Accepts optional body: { oemName, excelPath, scope }
    Returns the generated TrendInsightResponse list.

GET  /trend-insights
    Query persisted insights, with filters:
      scope       - material | supplier | global
      entity_name - partial match (case-insensitive)
      severity    - low | medium | high | critical
      limit       - default 50, max 200
      offset      - default 0
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_oem
from app.database import get_db
from app.models.oem import Oem
from app.models.trend_insight import TrendInsight
from app.schemas.trend_insight import (
    TrendInsightResponse,
    TrendInsightRunResponse,
)
from app.services.trend_orchestrator import run_trend_insights_cycle_async
from app.services.llm_client import get_llm_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trend-insights", tags=["trend-insights"])


# ── Manual trigger ────────────────────────────────────────────────────


@router.post("/run", response_model=TrendInsightRunResponse)
async def run_trend_insights(
    oem: Oem = Depends(get_current_oem),
    db: Session = Depends(get_db),
    oem_name: str | None = Body(None, embed=True),
    excel_path: str | None = Body(None, embed=True),
):
    """Run the trend-insights agent for the authenticated OEM.

    - **oem_name**: Override OEM display name (default: OEM from JWT).
    - **excel_path**: Override Excel path (default: data/mock_suppliers_demo.xlsx).
    """
    effective_oem_name = oem_name or oem.name
    client = get_llm_client()

    try:
        saved = await run_trend_insights_cycle_async(
            db,
            oem_name=effective_oem_name,
            excel_path=excel_path,
        )
    except Exception as exc:
        logger.exception("Trend insights run failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Agent run failed: {exc}")

    return TrendInsightRunResponse(
        message="Trend insights generated successfully.",
        insights_generated=len(saved),
        oem_name=effective_oem_name,
        excel_path=excel_path or "data/mock_suppliers_demo.xlsx",
        llm_provider=client.provider,
        insights=[_row_to_schema(r) for r in saved],
    )


# ── Query insights ────────────────────────────────────────────────────


@router.get("", response_model=list[TrendInsightResponse])
def list_trend_insights(
    scope: str | None = Query(
        None, description="Filter by scope: material | supplier | global"
    ),
    entity_name: str | None = Query(
        None, description="Partial match on entity name (case-insensitive)"
    ),
    severity: str | None = Query(
        None, description="Filter by severity: low | medium | high | critical"
    ),
    risk_opportunity: str | None = Query(
        None, description="Filter by type: risk | opportunity"
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: Oem = Depends(get_current_oem),
):
    """Return persisted trend insights with optional filters."""
    q = db.query(TrendInsight).order_by(TrendInsight.createdAt.desc())

    if scope:
        q = q.filter(TrendInsight.scope == scope)
    if severity:
        q = q.filter(TrendInsight.severity == severity)
    if risk_opportunity:
        q = q.filter(TrendInsight.risk_opportunity == risk_opportunity)
    if entity_name:
        q = q.filter(TrendInsight.entity_name.ilike(f"%{entity_name}%"))

    rows = q.offset(offset).limit(limit).all()
    return [_row_to_schema(r) for r in rows]


@router.get("/{insight_id}", response_model=TrendInsightResponse)
def get_trend_insight(
    insight_id: str,
    db: Session = Depends(get_db),
    _: Oem = Depends(get_current_oem),
):
    """Return a single trend insight by ID."""
    row = db.query(TrendInsight).filter(TrendInsight.id == insight_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Trend insight not found")
    return _row_to_schema(row)


# ── Helper ────────────────────────────────────────────────────────────


def _row_to_schema(row: TrendInsight) -> TrendInsightResponse:
    return TrendInsightResponse(
        id=row.id,
        scope=row.scope,
        entity_name=row.entity_name,
        risk_opportunity=row.risk_opportunity,
        title=row.title,
        description=row.description,
        predicted_impact=row.predicted_impact,
        time_horizon=row.time_horizon,
        severity=row.severity,
        recommended_actions=row.recommended_actions or [],
        source_articles=row.source_articles or [],
        confidence=row.confidence,
        oem_name=row.oem_name,
        excel_path=row.excel_path,
        llm_provider=row.llm_provider,
        createdAt=row.createdAt,
    )
