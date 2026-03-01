from uuid import UUID
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.supplier import Supplier
from app.models.risk import Risk, RiskSeverity, RiskStatus
from app.models.opportunity import Opportunity
from app.models.supply_chain_risk_score import SupplyChainRiskScore
from app.models.supplier_risk_analysis import SupplierRiskAnalysis
from app.models.swarm_analysis import SwarmAnalysis
from app.models.mitigation_plan import MitigationPlan
from app.models.workflow_run import WorkflowRun


def _parse_csv_line(line: str) -> list[str]:
    result = []
    current = ""
    in_quotes = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "," and not in_quotes:
            result.append(current.strip())
            current = ""
        else:
            current += ch
    result.append(current.strip())
    return result


def _normalize_header(h: str) -> str:
    return h.strip().lower().replace(" ", "_")


def upload_csv(
    db: Session, oem_id: UUID, content: bytes, filename: str = "upload.csv"
) -> dict:
    text = content.decode("utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return {
            "created": 0,
            "errors": [
                "CSV must have a header row and at least one data row.",
            ],
        }

    headers = _parse_csv_line(lines[0])
    header_index: Dict[str, int] = {}
    for i, h in enumerate(headers):
        key = _normalize_header(h)
        if key not in header_index:
            header_index[key] = i

    name_idx = (
        header_index.get("name")
        or header_index.get("supplier_name")
        or header_index.get("supplier")
        or 0
    )
    errors = []
    created = 0

    for row_num in range(1, len(lines)):
        values = _parse_csv_line(lines[row_num])
        if len(values) < 1 or not values[name_idx]:
            continue

        metadata = {}
        name = ""
        location = city = country = region = commodities = None

        for i, header in enumerate(headers):
            key = _normalize_header(header)
            value = values[i] if i < len(values) else ""
            if key in ("name", "supplier_name", "supplier"):
                name = value
            elif key in ("location", "address"):
                location = value or None
            elif key == "city":
                city = value or None
            elif key == "country":
                country = value or None
            elif key == "region":
                region = value or None
            elif key in ("commodities", "commodity"):
                commodities = value or None
            else:
                metadata[header.strip()] = value

        if not name:
            errors.append(f"Row {row_num + 1}: missing name.")
            continue

        try:
            supp = Supplier(
                oemId=oem_id,
                name=name,
                location=location,
                city=city,
                country=country,
                countryCode=country,
                region=region,
                commodities=commodities,
                metadata_=metadata if metadata else None,
            )
            db.add(supp)
            db.commit()
            created += 1
        except Exception as e:
            db.rollback()
            errors.append(f"Row {row_num + 1}: {e}")

    return {"created": created, "errors": errors}


def get_all(db: Session, oem_id: UUID) -> list[Supplier]:
    return (
        db.query(Supplier)
        .filter(Supplier.oemId == oem_id)
        .order_by(Supplier.createdAt.desc())
        .all()
    )


def get_by_id(db: Session, supplier_id: UUID) -> Supplier | None:
    return db.query(Supplier).filter(Supplier.id == supplier_id).first()


def get_one(db: Session, id: UUID, oem_id: UUID) -> Supplier | None:
    return (
        db.query(Supplier).filter(Supplier.id == id, Supplier.oemId == oem_id).first()
    )


def update_one(
    db: Session,
    id: UUID,
    oem_id: UUID,
    data: dict,
) -> Supplier | None:
    supplier = get_one(db, id, oem_id)
    if not supplier:
        return None
    allowed = {"name", "location", "city", "country", "region", "commodities"}
    for key, value in data.items():
        if key in allowed:
            setattr(supplier, key, value)
    db.commit()
    db.refresh(supplier)
    return supplier


def delete_one(db: Session, id: UUID, oem_id: UUID) -> bool:
    supplier = get_one(db, id, oem_id)
    if not supplier:
        return False
    db.delete(supplier)
    db.commit()
    return True


def get_risks_by_supplier(db: Session, oem_id: Optional[UUID] = None) -> dict:
    """
    Lightweight aggregation used by the existing UI to show simple counts.

    Resolves risks to supplier names via affectedSupplier/affectedSuppliers
    first, then falls back to the supplierId FK for risks where the LLM
    returned a null affectedSupplier (e.g. global-context news risks).

    When oem_id is provided, only risks for that OEM are included so the
    summary matches the OEM's suppliers list (and war/news risks are not
    mixed across OEMs).
    """
    q = (
        db.query(
            Risk.id,
            Risk.title,
            Risk.severity,
            Risk.affectedSupplier,
            Risk.affectedSuppliers,
            Risk.supplierId,
            Risk.createdAt,
        )
        .order_by(Risk.createdAt.desc())
    )
    if oem_id is not None:
        q = q.filter(Risk.oemId == oem_id)
    risks = q.all()

    # Build a supplierId -> supplier name lookup for risks missing affectedSupplier
    supplier_ids_needing_name: set = set()
    for r in risks:
        has_name = bool(
            getattr(r, "affectedSuppliers", None)
            or (r.affectedSupplier and r.affectedSupplier.strip())
        )
        if not has_name and r.supplierId:
            supplier_ids_needing_name.add(r.supplierId)

    supplier_id_to_name: Dict[str, str] = {}
    if supplier_ids_needing_name:
        q_sup = db.query(Supplier.id, Supplier.name).filter(
            Supplier.id.in_(supplier_ids_needing_name)
        )
        if oem_id is not None:
            q_sup = q_sup.filter(Supplier.oemId == oem_id)
        for row in q_sup.all():
            supplier_id_to_name[str(row.id)] = row.name

    out: Dict[str, dict] = {}
    for r in risks:
        # Support multiple suppliers per risk; fall back to single label.
        names: list[str] = []
        if getattr(r, "affectedSuppliers", None):
            names = [
                (str(n).strip()) for n in (r.affectedSuppliers or []) if str(n).strip()
            ]
        elif r.affectedSupplier:
            names = [r.affectedSupplier.strip()]

        # Fallback: resolve via supplierId when name fields are empty
        if not names and r.supplierId:
            resolved = supplier_id_to_name.get(str(r.supplierId))
            if resolved:
                names = [resolved]

        for key in names:
            if not key:
                continue
            if key not in out:
                out[key] = {"count": 0, "bySeverity": {}, "latest": None}
            out[key]["count"] += 1
            sev = str(r.severity.value if hasattr(r.severity, "value") else r.severity)
            out[key]["bySeverity"][sev] = out[key]["bySeverity"].get(sev, 0) + 1
            if out[key]["latest"] is None:
                out[key]["latest"] = {
                    "id": str(r.id),
                    "severity": sev,
                    "title": r.title,
                }
    return out


SEVERITY_WEIGHT: Dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def _compute_agent_score(risks: List[Risk]) -> Tuple[float, Dict[str, int]]:
    """
    Collapse multiple risks for a single agent into a 0-100 score plus per-severity counts.
    """
    if not risks:
        return 0.0, {}
    severity_counts: Dict[str, int] = {}
    weighted_sum = 0
    for r in risks:
        sev_value = (
            getattr(
                r.severity,
                "value",
                r.severity,
            )
            or RiskSeverity.MEDIUM.value
        )
        sev = str(sev_value).lower()
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        weight = SEVERITY_WEIGHT.get(sev, SEVERITY_WEIGHT["medium"])
        weighted_sum += weight
    count = len(risks)
    avg = weighted_sum / count if count else 0
    score = min(100.0, round(avg * 25))
    return score, severity_counts


def _score_to_risk_level(score: float) -> str:
    if score <= 25:
        return "LOW"
    if score <= 50:
        return "MEDIUM"
    if score <= 75:
        return "HIGH"
    return "CRITICAL"


def _build_swarm_summary_for_supplier(risks: List[Risk]) -> Optional[dict]:
    """
    Build a Swarm Controller style summary for a given supplier from existing risks.

    Maps Risk.sourceType -> conceptual agent buckets (WEATHER, SHIPPING, NEWS)
    and then applies the weighted finalization formula from the PRD.
    """
    if not risks:
        return None

    # Partition risks by conceptual agent type based on their sourceType
    weather_risks: List[Risk] = []
    shipping_risks: List[Risk] = []
    news_risks: List[Risk] = []
    other_risks: List[Risk] = []

    for r in risks:
        if r.sourceType == "weather":
            weather_risks.append(r)
        elif r.sourceType in ("traffic", "shipping"):
            shipping_risks.append(r)
        elif r.sourceType in ("news", "global_news"):
            news_risks.append(r)
        else:
            other_risks.append(r)

    weather_score, weather_counts = _compute_agent_score(weather_risks)
    shipping_score, shipping_counts = _compute_agent_score(shipping_risks)
    news_score, news_counts = _compute_agent_score(news_risks)

    final_score = round(
        (weather_score * 0.4) + (shipping_score * 0.3) + (news_score * 0.3)
    )
    final_level = _score_to_risk_level(final_score)

    # Top drivers: take the most recent, highest-severity risk titles
    def _severity_weight(r: Risk) -> int:
        sev_value = (
            getattr(
                r.severity,
                "value",
                r.severity,
            )
            or RiskSeverity.MEDIUM.value
        )
        sev = str(sev_value).lower()
        return SEVERITY_WEIGHT.get(sev, SEVERITY_WEIGHT["medium"])

    sorted_risks = sorted(
        risks,
        key=lambda r: (_severity_weight(r), r.createdAt or 0),
        reverse=True,
    )
    top_drivers = [r.title for r in sorted_risks[:3]]

    # Simple rule-based mitigation suggestions aligned with PRD examples
    mitigation_plan: List[str] = []

    if _score_to_risk_level(weather_score) in ("HIGH", "CRITICAL"):
        mitigation_plan.append(
            "Increase safety stock near affected regions.",
        )
        mitigation_plan.append(
            "Identify alternate regional suppliers to bypass weather hotspots.",
        )

    if _score_to_risk_level(shipping_score) in ("HIGH", "CRITICAL"):
        mitigation_plan.append(
            "Shift part of volume to air freight for critical orders.",
        )
        mitigation_plan.append(
            "Re-route shipments via less congested ports or lanes.",
        )

    if _score_to_risk_level(news_score) in ("HIGH", "CRITICAL"):
        mitigation_plan.append(
            "Hedge commodity prices for exposed materials.",
        )
        mitigation_plan.append(
            "Activate backup or secondary suppliers in stable regions.",
        )

    # Fallback mitigation guidance if nothing specific triggered
    if not mitigation_plan and final_score > 0:
        mitigation_plan.append(
            "Review supplier exposure and validate business continuity plans.",
        )
        mitigation_plan.append(
            "Schedule a risk review with procurement and operations teams.",
        )

    # Agent-level summaries in AgentResult shape
    def _build_agent_result(
        agent_type: str,
        score: float,
        agent_risks: List[Risk],
        counts: Dict[str, int],
    ) -> dict:
        signals = [r.title for r in agent_risks[:5]]
        interpreted = [r.description for r in agent_risks[:5]]
        # Confidence is a simple heuristic: more corroborating risks → higher confidence
        confidence = min(1.0, 0.5 + 0.1 * len(agent_risks)) if agent_risks else 0.0
        return {
            "agentType": agent_type,
            "score": score,
            "riskLevel": _score_to_risk_level(score),
            "signals": signals,
            "interpretedRisks": interpreted,
            "confidence": confidence,
            "metadata": {
                "severityCounts": counts,
                "riskCount": len(agent_risks),
            },
        }

    agents: List[dict] = [
        _build_agent_result("WEATHER", weather_score, weather_risks, weather_counts),
        _build_agent_result(
            "SHIPPING", shipping_score, shipping_risks, shipping_counts
        ),
        _build_agent_result("NEWS", news_score, news_risks, news_counts),
    ]

    return {
        "finalScore": final_score,
        "riskLevel": final_level,
        "topDrivers": top_drivers,
        "mitigationPlan": mitigation_plan,
        "agents": agents,
    }


def get_latest_risk_analysis_by_supplier(
    db: Session, oem_id: UUID
) -> Dict[UUID, str]:
    """
    Return a mapping of supplier_id -> latest SupplierRiskAnalysis.description.
    """
    rows = (
        db.query(SupplierRiskAnalysis.supplierId, SupplierRiskAnalysis.description)
        .filter(
            SupplierRiskAnalysis.oemId == oem_id,
            SupplierRiskAnalysis.supplierId.isnot(None),
            SupplierRiskAnalysis.description.isnot(None),
        )
        .order_by(SupplierRiskAnalysis.createdAt.desc())
        .all()
    )
    result: Dict[UUID, str] = {}
    for row in rows:
        if row.supplierId not in result:
            result[row.supplierId] = row.description
    return result


def get_latest_swarm_by_supplier(
    db: Session, oem_id: UUID
) -> Dict[UUID, dict]:
    """
    Return a mapping of supplier_id -> latest persisted swarm analysis dict.

    Queries the swarm_analysis table, returning the most recent
    SwarmAnalysis per supplier.  Keyed by supplier UUID (not name).
    """
    rows = (
        db.query(SwarmAnalysis)
        .filter(SwarmAnalysis.oemId == oem_id)
        .order_by(SwarmAnalysis.createdAt.desc())
        .all()
    )

    result: Dict[UUID, dict] = {}
    for sa in rows:
        if sa.supplierId in result:
            continue  # already have a newer one
        result[sa.supplierId] = {
            "finalScore": float(sa.finalScore) if sa.finalScore is not None else 0,
            "riskLevel": sa.riskLevel,
            "topDrivers": sa.topDrivers or [],
            "mitigationPlan": sa.mitigationPlan or [],
            "agents": sa.agents or [],
        }

    return result


# ---------------------------------------------------------------------------
# Supplier Metrics — full visibility for a single supplier by workflow run
# ---------------------------------------------------------------------------

def _serialize_risk(r: Risk) -> Dict[str, Any]:
    return {
        "id": str(r.id),
        "title": r.title,
        "description": r.description,
        "severity": getattr(r.severity, "value", r.severity),
        "status": getattr(r.status, "value", r.status),
        "sourceType": r.sourceType,
        "sourceData": r.sourceData,
        "affectedRegion": r.affectedRegion,
        "affectedSupplier": r.affectedSupplier,
        "impactDescription": r.impactDescription,
        "estimatedImpact": r.estimatedImpact,
        "estimatedCost": float(r.estimatedCost) if r.estimatedCost is not None else None,
        "createdAt": r.createdAt.isoformat() if r.createdAt else None,
    }


def _serialize_opportunity(o: Opportunity) -> Dict[str, Any]:
    return {
        "id": str(o.id),
        "title": o.title,
        "description": o.description,
        "type": getattr(o.type, "value", o.type),
        "status": getattr(o.status, "value", o.status),
        "sourceType": o.sourceType,
        "sourceData": o.sourceData,
        "affectedRegion": o.affectedRegion,
        "impactDescription": o.impactDescription,
        "potentialBenefit": o.potentialBenefit,
        "estimatedValue": float(o.estimatedValue) if o.estimatedValue is not None else None,
        "createdAt": o.createdAt.isoformat() if o.createdAt else None,
    }


def _serialize_mitigation_plan(mp: MitigationPlan) -> Dict[str, Any]:
    return {
        "id": str(mp.id),
        "title": mp.title,
        "description": mp.description,
        "actions": mp.actions or [],
        "status": getattr(mp.status, "value", mp.status),
        "assignedTo": mp.assignedTo,
        "dueDate": mp.dueDate.isoformat() if mp.dueDate else None,
        "createdAt": mp.createdAt.isoformat() if mp.createdAt else None,
    }


def get_supplier_metrics(
    db: Session, supplier_id: UUID, oem_id: UUID
) -> Optional[Dict[str, Any]]:
    """
    Full metrics for a supplier, scoped to the latest workflow run.

    Flow:
    1. Get the latest SupplierRiskAnalysis for this supplier.
    2. Pick its workflowRunId.
    3. Fetch all risks, opportunities, swarm analysis, supply chain score,
       and mitigation plans produced in that workflow run for this supplier.
    """
    # 1. Latest risk analysis for this supplier
    sra = (
        db.query(SupplierRiskAnalysis)
        .filter(
            SupplierRiskAnalysis.supplierId == supplier_id,
            SupplierRiskAnalysis.oemId == oem_id,
        )
        .order_by(SupplierRiskAnalysis.createdAt.desc())
        .first()
    )
    if not sra:
        return None

    wf_run_id = sra.workflowRunId

    # Workflow run metadata
    wf_run = db.query(WorkflowRun).filter(WorkflowRun.id == wf_run_id).first()

    # 2. All risks for this supplier in this workflow run
    risks = (
        db.query(Risk)
        .filter(
            Risk.workflowRunId == wf_run_id,
            Risk.supplierId == supplier_id,
        )
        .order_by(Risk.createdAt.desc())
        .all()
    )

    # 3. All opportunities for this supplier in this workflow run
    opportunities = (
        db.query(Opportunity)
        .filter(
            Opportunity.workflowRunId == wf_run_id,
            Opportunity.supplierId == supplier_id,
        )
        .order_by(Opportunity.createdAt.desc())
        .all()
    )

    # 4. Swarm analysis for this supplier in this workflow run
    swarm = (
        db.query(SwarmAnalysis)
        .filter(
            SwarmAnalysis.supplierRiskAnalysisId == sra.id,
        )
        .first()
    )

    # 5. Supply chain risk score for this workflow run
    supply_chain_score = (
        db.query(SupplyChainRiskScore)
        .filter(SupplyChainRiskScore.workflowRunId == wf_run_id)
        .order_by(SupplyChainRiskScore.createdAt.desc())
        .first()
    )

    # 6. Mitigation plans for risks in this workflow run
    risk_ids = [r.id for r in risks]
    mitigation_plans: List[MitigationPlan] = []
    if risk_ids:
        mitigation_plans = (
            db.query(MitigationPlan)
            .filter(MitigationPlan.riskId.in_(risk_ids))
            .order_by(MitigationPlan.createdAt.desc())
            .all()
        )

    # Severity counts for quick summary
    severity_counts: Dict[str, int] = {}
    for r in risks:
        sev = str(getattr(r.severity, "value", r.severity))
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
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
        "risks": [_serialize_risk(r) for r in risks],
        "risksSummary": {
            "total": len(risks),
            "bySeverity": severity_counts,
        },
        "opportunities": [_serialize_opportunity(o) for o in opportunities],
        "swarmAnalysis": {
            "id": str(swarm.id),
            "finalScore": float(swarm.finalScore) if swarm.finalScore is not None else 0,
            "riskLevel": swarm.riskLevel,
            "topDrivers": swarm.topDrivers or [],
            "mitigationPlan": swarm.mitigationPlan or [],
            "agents": swarm.agents or [],
            "createdAt": swarm.createdAt.isoformat() if swarm.createdAt else None,
        } if swarm else None,
        "supplyChainScore": {
            "id": str(supply_chain_score.id),
            "overallScore": float(supply_chain_score.overallScore) if supply_chain_score.overallScore is not None else 0,
            "breakdown": supply_chain_score.breakdown,
            "severityCounts": supply_chain_score.severityCounts,
            "summary": supply_chain_score.summary,
            "createdAt": supply_chain_score.createdAt.isoformat() if supply_chain_score.createdAt else None,
        } if supply_chain_score else None,
        "mitigationPlans": [_serialize_mitigation_plan(mp) for mp in mitigation_plans],
    }


def get_supplier_risk_history(
    db: Session, supplier_id: UUID, oem_id: UUID, limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Return historical risk analysis runs for a supplier, ordered newest-first.

    Each entry contains the SupplierRiskAnalysis data, workflow run info,
    risk/opportunity counts, and swarm summary for that run.
    """
    sra_rows = (
        db.query(SupplierRiskAnalysis)
        .filter(
            SupplierRiskAnalysis.supplierId == supplier_id,
            SupplierRiskAnalysis.oemId == oem_id,
        )
        .order_by(SupplierRiskAnalysis.createdAt.desc())
        .limit(limit)
        .all()
    )
    if not sra_rows:
        return []

    # Collect all workflow run IDs and SRA IDs for batch queries
    wf_ids = [sra.workflowRunId for sra in sra_rows if sra.workflowRunId]
    sra_ids = [sra.id for sra in sra_rows]

    # Batch-load workflow runs
    wf_map: Dict[Any, WorkflowRun] = {}
    if wf_ids:
        for wf in db.query(WorkflowRun).filter(WorkflowRun.id.in_(wf_ids)).all():
            wf_map[wf.id] = wf

    # Batch-load swarm analyses by SRA id
    swarm_map: Dict[Any, SwarmAnalysis] = {}
    if sra_ids:
        for sa in db.query(SwarmAnalysis).filter(SwarmAnalysis.supplierRiskAnalysisId.in_(sra_ids)).all():
            swarm_map[sa.supplierRiskAnalysisId] = sa

    # Batch-load risk counts per workflow run for this supplier
    from sqlalchemy import func as sa_func

    risk_counts: Dict[Any, Dict[str, int]] = {}
    opp_counts: Dict[Any, int] = {}
    if wf_ids:
        risk_rows = (
            db.query(Risk.workflowRunId, Risk.severity, sa_func.count(Risk.id))
            .filter(
                Risk.workflowRunId.in_(wf_ids),
                Risk.supplierId == supplier_id,
            )
            .group_by(Risk.workflowRunId, Risk.severity)
            .all()
        )
        for wf_id, severity, cnt in risk_rows:
            if wf_id not in risk_counts:
                risk_counts[wf_id] = {}
            sev = str(getattr(severity, "value", severity))
            risk_counts[wf_id][sev] = cnt

        opp_rows = (
            db.query(Opportunity.workflowRunId, sa_func.count(Opportunity.id))
            .filter(
                Opportunity.workflowRunId.in_(wf_ids),
                Opportunity.supplierId == supplier_id,
            )
            .group_by(Opportunity.workflowRunId)
            .all()
        )
        for wf_id, cnt in opp_rows:
            opp_counts[wf_id] = cnt

    history = []
    for sra in sra_rows:
        wf = wf_map.get(sra.workflowRunId)
        swarm = swarm_map.get(sra.id)
        sev_counts = risk_counts.get(sra.workflowRunId, {})
        total_risks = sum(sev_counts.values())

        entry: Dict[str, Any] = {
            "id": str(sra.id),
            "workflowRunId": str(sra.workflowRunId) if sra.workflowRunId else None,
            "riskScore": float(sra.riskScore) if sra.riskScore is not None else 0,
            "description": sra.description,
            "createdAt": sra.createdAt.isoformat() if sra.createdAt else None,
            "workflowRun": {
                "runDate": wf.runDate.isoformat() if wf and wf.runDate else None,
                "runIndex": wf.runIndex if wf else None,
            } if wf else None,
            "risksSummary": {
                "total": total_risks,
                "bySeverity": sev_counts,
            },
            "opportunitiesCount": opp_counts.get(sra.workflowRunId, 0),
            "swarmSummary": {
                "finalScore": float(swarm.finalScore) if swarm and swarm.finalScore is not None else None,
                "riskLevel": swarm.riskLevel if swarm else None,
            } if swarm else None,
        }
        history.append(entry)

    return history
