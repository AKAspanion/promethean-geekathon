from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.api.deps import get_current_oem
from app.models.oem import Oem
from app.orchestration.agent_service import (
    get_status,
    get_latest_risk_score,
    trigger_manual_analysis_sync,
    trigger_manual_analysis_v2_sync,
    trigger_news_analysis_sync,
    _ensure_agent_status,
)

router = APIRouter(prefix="/agent", tags=["agent"])


class TriggerBody(BaseModel):
    oemId: UUID | None = None
    supplierId: UUID | None = None


@router.get("/status")
def agent_status(
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
    oemId: UUID | None = Query(None),
):
    status = get_status(db)
    if not status:
        _ensure_agent_status(db)
        status = get_status(db)
    oid = oemId or oem.id
    risk_score_ent = get_latest_risk_score(db, oid)
    risk_score = (
        float(risk_score_ent.overallScore)
        if risk_score_ent and risk_score_ent.overallScore is not None
        else None
    )
    if not status:
        return {
            "status": "idle",
            "currentTask": None,
            "riskScore": risk_score,
        }
    return {
        "id": str(status.id),
        "status": status.status,
        "currentTask": status.currentTask,
        "lastProcessedData": status.lastProcessedData,
        "lastDataSource": status.lastDataSource,
        "errorMessage": status.errorMessage,
        "risksDetected": status.risksDetected,
        "opportunitiesIdentified": status.opportunitiesIdentified,
        "plansGenerated": status.plansGenerated,
        "riskScore": risk_score,
        "lastUpdated": status.lastUpdated.isoformat() if status.lastUpdated else None,
        "createdAt": status.createdAt.isoformat() if status.createdAt else None,
    }


@router.get("/risk-score")
def risk_score(
    oem: Oem = Depends(get_current_oem),
    oemId: UUID | None = Query(None),
    db: Session = Depends(get_db),
):
    """Latest risk score for the OEM (0-100). Computed after each analysis run."""
    oid = oemId or oem.id
    score = get_latest_risk_score(db, oid)
    if not score:
        return {
            "message": "No risk score computed yet for this OEM.",
            "overallScore": None,
        }
    return {
        "id": str(score.id),
        "oemId": str(score.oemId),
        "overallScore": float(score.overallScore),
        "breakdown": score.breakdown,
        "severityCounts": score.severityCounts,
        "riskIds": score.riskIds.split(",") if score.riskIds else [],
        "createdAt": score.createdAt.isoformat() if score.createdAt else None,
    }


@router.post("/trigger")
def trigger_analysis(
    body: TriggerBody | None = None,
    oem: Oem = Depends(get_current_oem),
    db: Session = Depends(get_db),
):
    oem_id = (body.oemId if body else None) or oem.id
    trigger_manual_analysis_sync(db, oem_id)
    return {"message": "Analysis triggered successfully", "oemId": str(oem_id)}


@router.post("/trigger/news")
def trigger_news_analysis(
    body: TriggerBody | None = None,
    oem: Oem = Depends(get_current_oem),
    db: Session = Depends(get_db),
):
    """
    Run only the News Agent for the current OEM.

    Fetches supply-chain news from NewsAPI + GDELT, runs LLM risk extraction
    for both supplier-scoped and global contexts, and persists the results.
    Much faster than the full /agent/trigger pipeline (no weather or shipping).
    """
    oem_id = (body.oemId if body else None) or oem.id
    supplier_id = body.supplierId if body else None
    result = trigger_news_analysis_sync(db, oem_id, supplier_id=supplier_id)
    return {
        "message": "News analysis completed successfully",
        "oemId": str(oem_id),
        "risksCreated": result["risksCreated"],
        "opportunitiesCreated": result["opportunitiesCreated"],
    }


@router.post("/trigger/v2")
def trigger_analysis_v2(
    body: TriggerBody | None = None,
    oem: Oem = Depends(get_current_oem),
    db: Session = Depends(get_db),
):
    """
    Graph-based analysis (v2).

    Runs Weather, News, and Shipment agents in parallel inside a
    SupplierRiskGraph, then aggregates a unified risk score per supplier
    and an OEM-level score via the OemOrchestrationGraph.

    The original /agent/trigger endpoint is unchanged.
    """
    oem_id = (body.oemId if body else None) or oem.id
    trigger_manual_analysis_v2_sync(db, oem_id)
    return {
        "message": "Graph-based analysis (v2) triggered successfully",
        "oemId": str(oem_id),
    }
