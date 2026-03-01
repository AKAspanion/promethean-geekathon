from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_oem
from app.models.oem import Oem
from app.services.suppliers import (
    get_all,
    get_one,
    upload_csv,
    update_one,
    delete_one,
    get_risks_by_supplier,
    get_latest_risk_analysis_by_supplier,
    get_latest_swarm_by_supplier,
    get_supplier_metrics,
    get_supplier_risk_history,
)


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    commodities: Optional[str] = None

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.post("/upload")
def upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    if not file.file:
        raise HTTPException(
            status_code=400, detail='No file uploaded. Use form field name "file".'
        )
    content = file.file.read()
    return upload_csv(db, oem.id, content, file.filename or "upload.csv")


@router.get("")
def list_suppliers(
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    suppliers = get_all(db, oem.id)
    risk_map = get_risks_by_supplier(db, oem.id)
    reasoning_map = get_latest_risk_analysis_by_supplier(db, oem.id)
    swarm_map = get_latest_swarm_by_supplier(db, oem.id)
    return [
        {
            **{
                "id": str(s.id),
                "oemId": str(s.oemId) if s.oemId else None,
                "name": s.name,
                "location": s.location,
                "city": s.city,
                "country": s.country,
                "region": s.region,
                "commodities": s.commodities,
                "metadata": s.metadata_,
                "latestRiskScore": float(s.latestRiskScore)
                if s.latestRiskScore is not None
                else None,
                "latestRiskLevel": s.latestRiskLevel,
                "createdAt": s.createdAt.isoformat() if s.createdAt else None,
                "updatedAt": s.updatedAt.isoformat() if s.updatedAt else None,
            },
            "riskSummary": risk_map.get(
                s.name,
                {"count": 0, "bySeverity": {}, "latest": None},
            ),
            "aiReasoning": reasoning_map.get(s.id),
            "swarm": swarm_map.get(s.id),
        }
        for s in suppliers
    ]


@router.get("/{id}/history")
def supplier_history(
    id: UUID,
    limit: int = 20,
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    """Risk analysis history for a supplier across workflow runs."""
    supplier = get_one(db, id, oem.id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return get_supplier_risk_history(db, id, oem.id, limit=limit)


@router.get("/{id}/metrics")
def supplier_metrics(
    id: UUID,
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    """Full supplier metrics scoped to the latest workflow run."""
    supplier = get_one(db, id, oem.id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    metrics = get_supplier_metrics(db, id, oem.id)
    if not metrics:
        return {
            "supplier": {
                "id": str(supplier.id),
                "name": supplier.name,
            },
            "workflowRun": None,
            "riskAnalysis": None,
            "risks": [],
            "risksSummary": {"total": 0, "bySeverity": {}},
            "opportunities": [],
            "swarmAnalysis": None,
            "supplyChainScore": None,
            "mitigationPlans": [],
        }
    return {
        "supplier": {
            "id": str(supplier.id),
            "name": supplier.name,
            "location": supplier.location,
            "city": supplier.city,
            "country": supplier.country,
            "region": supplier.region,
            "commodities": supplier.commodities,
            "latestRiskScore": float(supplier.latestRiskScore) if supplier.latestRiskScore is not None else None,
            "latestRiskLevel": supplier.latestRiskLevel,
        },
        **metrics,
    }


@router.get("/{id}/analysis-report/{sra_id}")
def supplier_analysis_report(
    id: UUID,
    sra_id: UUID,
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    """Full analysis report for a specific SupplierRiskAnalysis run.

    Returns the risk analysis, swarm analysis, per-agent raw states,
    risks, opportunities, and mitigation plans — everything needed to
    render a detailed historical analysis report.
    """
    from app.models.supplier_risk_analysis import SupplierRiskAnalysis
    from app.models.swarm_analysis import SwarmAnalysis
    from app.models.agent_run_data import AgentRunData
    from app.models.risk import Risk
    from app.models.opportunity import Opportunity
    from app.models.mitigation_plan import MitigationPlan
    from app.models.workflow_run import WorkflowRun
    from app.services.suppliers import (
        _serialize_risk,
        _serialize_opportunity,
        _serialize_mitigation_plan,
    )

    supplier = get_one(db, id, oem.id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    sra = (
        db.query(SupplierRiskAnalysis)
        .filter(
            SupplierRiskAnalysis.id == sra_id,
            SupplierRiskAnalysis.supplierId == id,
            SupplierRiskAnalysis.oemId == oem.id,
        )
        .first()
    )
    if not sra:
        raise HTTPException(status_code=404, detail="Analysis not found")

    wf_run_id = sra.workflowRunId
    wf_run = db.query(WorkflowRun).filter(WorkflowRun.id == wf_run_id).first()

    # Swarm analysis
    swarm = (
        db.query(SwarmAnalysis)
        .filter(SwarmAnalysis.supplierRiskAnalysisId == sra.id)
        .first()
    )

    # Agent run data
    agent_rows = (
        db.query(AgentRunData)
        .filter(
            AgentRunData.supplierId == id,
            AgentRunData.workflowRunId == wf_run_id,
        )
        .all()
    )
    agent_states = {row.agentType: row.finalState for row in agent_rows}

    # Risks
    risks = (
        db.query(Risk)
        .filter(Risk.workflowRunId == wf_run_id, Risk.supplierId == id)
        .order_by(Risk.createdAt.desc())
        .all()
    )

    # Opportunities
    opportunities = (
        db.query(Opportunity)
        .filter(Opportunity.workflowRunId == wf_run_id, Opportunity.supplierId == id)
        .order_by(Opportunity.createdAt.desc())
        .all()
    )

    # Severity counts
    severity_counts = {}
    for r in risks:
        sev = str(getattr(r.severity, "value", r.severity))
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Mitigation plans
    risk_ids = [r.id for r in risks]
    mitigation_plans = []
    if risk_ids:
        mitigation_plans = (
            db.query(MitigationPlan)
            .filter(MitigationPlan.riskId.in_(risk_ids))
            .order_by(MitigationPlan.createdAt.desc())
            .all()
        )

    return {
        "supplier": {
            "id": str(supplier.id),
            "name": supplier.name,
            "location": supplier.location,
            "city": supplier.city,
            "country": supplier.country,
            "region": supplier.region,
            "commodities": supplier.commodities,
        },
        "workflowRun": {
            "id": str(wf_run.id) if wf_run else str(wf_run_id),
            "runDate": wf_run.runDate.isoformat() if wf_run and wf_run.runDate else None,
            "runIndex": wf_run.runIndex if wf_run else None,
            "createdAt": wf_run.createdAt.isoformat() if wf_run and wf_run.createdAt else None,
        },
        "riskAnalysis": {
            "id": str(sra.id),
            "riskScore": float(sra.riskScore) if sra.riskScore is not None else 0,
            "description": sra.description,
            "metadata": sra.metadata_,
            "createdAt": sra.createdAt.isoformat() if sra.createdAt else None,
        },
        "swarmAnalysis": {
            "id": str(swarm.id),
            "finalScore": float(swarm.finalScore) if swarm.finalScore is not None else 0,
            "riskLevel": swarm.riskLevel,
            "topDrivers": swarm.topDrivers or [],
            "mitigationPlan": swarm.mitigationPlan or [],
            "agents": swarm.agents or [],
            "createdAt": swarm.createdAt.isoformat() if swarm.createdAt else None,
        } if swarm else None,
        "agentStates": agent_states,
        "risks": [_serialize_risk(r) for r in risks],
        "risksSummary": {
            "total": len(risks),
            "bySeverity": severity_counts,
        },
        "opportunities": [_serialize_opportunity(o) for o in opportunities],
        "mitigationPlans": [_serialize_mitigation_plan(mp) for mp in mitigation_plans],
    }


@router.get("/{id}")
def get_supplier_by_id(
    id: UUID,
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    supplier = get_one(db, id, oem.id)
    if not supplier:
        return None
    risk_map = get_risks_by_supplier(db, oem.id)
    reasoning_map = get_latest_risk_analysis_by_supplier(db, oem.id)
    swarm_map = get_latest_swarm_by_supplier(db, oem.id)
    return {
        **{
            "id": str(supplier.id),
            "oemId": str(supplier.oemId) if supplier.oemId else None,
            "name": supplier.name,
            "location": supplier.location,
            "city": supplier.city,
            "country": supplier.country,
            "region": supplier.region,
            "commodities": supplier.commodities,
            "metadata": supplier.metadata_,
            "latestRiskScore": float(supplier.latestRiskScore)
            if supplier.latestRiskScore is not None
            else None,
            "latestRiskLevel": supplier.latestRiskLevel,
            "createdAt": supplier.createdAt.isoformat() if supplier.createdAt else None,
            "updatedAt": supplier.updatedAt.isoformat() if supplier.updatedAt else None,
        },
        "riskSummary": risk_map.get(
            supplier.name,
            {"count": 0, "bySeverity": {}, "latest": None},
        ),
        "aiReasoning": reasoning_map.get(supplier.id),
        "swarm": swarm_map.get(supplier.id),
    }


def _format_supplier(supplier, risk_map, swarm_map, reasoning_map=None):
    return {
        **{
            "id": str(supplier.id),
            "oemId": str(supplier.oemId) if supplier.oemId else None,
            "name": supplier.name,
            "location": supplier.location,
            "city": supplier.city,
            "country": supplier.country,
            "region": supplier.region,
            "commodities": supplier.commodities,
            "metadata": supplier.metadata_,
            "latestRiskScore": float(supplier.latestRiskScore)
            if supplier.latestRiskScore is not None
            else None,
            "latestRiskLevel": supplier.latestRiskLevel,
            "createdAt": supplier.createdAt.isoformat() if supplier.createdAt else None,
            "updatedAt": supplier.updatedAt.isoformat() if supplier.updatedAt else None,
        },
        "riskSummary": risk_map.get(
            supplier.name,
            {"count": 0, "bySeverity": {}, "latest": None},
        ),
        "aiReasoning": (reasoning_map or {}).get(supplier.id),
        "swarm": swarm_map.get(supplier.id),
    }


@router.put("/{id}")
def update_supplier(
    id: UUID,
    body: SupplierUpdate,
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    supplier = update_one(db, id, oem.id, data)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    risk_map = get_risks_by_supplier(db, oem.id)
    reasoning_map = get_latest_risk_analysis_by_supplier(db, oem.id)
    swarm_map = get_latest_swarm_by_supplier(db, oem.id)
    return _format_supplier(supplier, risk_map, swarm_map, reasoning_map)


@router.delete("/{id}", status_code=204)
def delete_supplier(
    id: UUID,
    db: Session = Depends(get_db),
    oem: Oem = Depends(get_current_oem),
):
    deleted = delete_one(db, id, oem.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Supplier not found")
