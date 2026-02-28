"""
OemOrchestrationGraph
=====================
A LangGraph StateGraph that drives the full analysis pipeline for one OEM,
iterating over every supplier sequentially (safe for a single shared
SQLAlchemy session) and then aggregating an OEM-level risk score.

Graph structure
---------------

    START
      │
      ▼
  [process_next_supplier]  ← fetch data (parallel) → call SupplierRiskGraph
      │                       → persist risks/opps → update latestRiskScore
      │                       → broadcast partial update
      │
      ├──(more suppliers?)──► [process_next_supplier]   (loop)
      │
      ▼
  [aggregate_oem_score]    ← query all risks → compute OEM SupplyChainRiskScore
      │
      ▼
  [generate_plans]         ← combined + per-risk + opportunity mitigation plans
      │
      ▼
  [broadcast_complete]     ← mark completed → final WebSocket broadcast
      │
      ▼
     END

Runtime dependencies (DB session, workflow IDs) are passed through
``RunnableConfig["configurable"]`` so the graph state remains serialisable.

Expected config shape
---------------------
.. code-block:: python

    config = {
        "configurable": {
            "db": <sqlalchemy Session>,
        }
    }

The per-supplier ``workflow_run_id`` and ``agent_status_id`` are carried
inside each ``SupplierWorkflowContext`` in the state, not the config, so
each supplier can own its own DB records.
"""

import asyncio
import logging
from datetime import datetime
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.models.agent_status import AgentStatusEntity, AgentStatus
from app.models.mitigation_plan import MitigationPlan
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.risk import Risk, RiskStatus
from app.models.supply_chain_risk_score import SupplyChainRiskScore
from app.models.supplier_risk_analysis import SupplierRiskAnalysis
from app.services.agent_orchestrator import (
    generate_combined_mitigation_plan,
    generate_mitigation_plan,
    generate_opportunity_plan,
)
from app.services.agent_types import OemScope
from app.services.mitigation_plans import create_plan_from_dict
from app.services.opportunities import create_opportunity_from_dict
from app.services.risks import create_risk_from_dict
from app.services.suppliers import (
    get_all as get_suppliers,
    get_risks_by_supplier,
    get_latest_swarm_by_supplier,
    _build_swarm_summary_for_supplier,
)
from app.services.websocket_manager import (
    broadcast_agent_status,
    broadcast_suppliers_snapshot,
)
from app.data.manager import get_data_source_manager
from app.orchestration.graphs.states import (
    OemOrchestrationState,
    SupplierRiskResult,
    SupplierRiskState,
    SupplierWorkflowContext,
)
from app.orchestration.graphs.supplier_risk_graph import (
    SUPPLIER_RISK_GRAPH,
    compute_score_from_dicts,
    score_to_level,
)

logger = logging.getLogger(__name__)


# ── Data-fetching helpers ──────────────────────────────────────────────────────

def _build_data_source_params(scope: OemScope) -> dict:
    cities = (
        scope.get("cities")
        or (scope.get("locations") or [])[:10]
        or ["New York", "London", "Tokyo", "Mumbai", "Shanghai"]
    )
    if not cities:
        cities = ["New York", "London", "Tokyo", "Mumbai", "Shanghai"]

    commodities = scope.get("commodities") or [
        "steel", "copper", "oil", "grain", "semiconductors"
    ]

    routes: list[dict] = []
    if cities:
        oem_city = cities[0]
        for c in (cities[1:] or [oem_city])[:10]:
            if c != oem_city:
                routes.append({"origin": c, "destination": oem_city})
    if not routes:
        routes = [{"origin": "New York", "destination": "Los Angeles"}]

    keywords = ["supply chain", "manufacturing", "logistics"] + (
        scope.get("commodities") or []
    )[:3]

    return {
        "cities": cities,
        "commodities": commodities,
        "routes": routes,
        "keywords": keywords,
    }


def _build_global_news_params() -> dict:
    return {
        "keywords": [
            "global supply chain",
            "geopolitical risk",
            "trade disruption",
            "raw materials shortage",
            "logistics crisis",
            "shipping capacity",
        ]
    }


async def _fetch_all_data(scope: OemScope) -> dict:
    """
    Fetch weather, supplier news, global news, and shipping data in parallel.
    Returns ``{"weather": dict, "news": dict, "global_news": dict, "shipping": dict}``.
    """
    manager = get_data_source_manager()
    await manager.initialize()

    supplier_params = _build_data_source_params(scope)
    global_params = _build_global_news_params()
    route_params = {"routes": supplier_params["routes"]}

    supplier_data, global_news_data, route_data = await asyncio.gather(
        manager.fetch_by_types(["weather", "news"], supplier_params),
        manager.fetch_by_types(["news"], global_params),
        manager.fetch_by_types(["traffic", "shipping"], route_params),
    )

    return {
        "weather": {"weather": supplier_data.get("weather") or []},
        "news": {"news": supplier_data.get("news") or []},
        "global_news": {"news": global_news_data.get("news") or []},
        "shipping": {"shipping": route_data.get("shipping") or []},
    }


# ── Status / broadcast helpers ─────────────────────────────────────────────────

def _update_status(
    db: Session,
    agent_status_id: UUID,
    status: str,
    task: str | None = None,
) -> None:
    ent = (
        db.query(AgentStatusEntity)
        .filter(AgentStatusEntity.id == agent_status_id)
        .first()
    )
    if not ent:
        return
    ent.status = status
    ent.currentTask = task
    ent.lastUpdated = datetime.utcnow()
    db.commit()


async def _broadcast_status(db: Session, agent_status_id: UUID) -> None:
    ent = (
        db.query(AgentStatusEntity)
        .filter(AgentStatusEntity.id == agent_status_id)
        .first()
    )
    if not ent:
        return
    await broadcast_agent_status(
        {
            "id": str(ent.id),
            "status": ent.status,
            "currentTask": ent.currentTask,
            "lastProcessedData": ent.lastProcessedData,
            "lastDataSource": ent.lastDataSource,
            "errorMessage": ent.errorMessage,
            "risksDetected": ent.risksDetected,
            "opportunitiesIdentified": ent.opportunitiesIdentified,
            "plansGenerated": ent.plansGenerated,
            "lastUpdated": (
                ent.lastUpdated.isoformat() if ent.lastUpdated else None
            ),
            "createdAt": ent.createdAt.isoformat() if ent.createdAt else None,
        }
    )


async def _broadcast_suppliers(db: Session, oem_id: UUID) -> None:
    suppliers = get_suppliers(db, oem_id)
    if not suppliers:
        return
    risk_map = get_risks_by_supplier(db)
    swarm_map = get_latest_swarm_by_supplier(db, oem_id)
    payload = [
        {
            "id": str(s.id),
            "oemId": str(s.oemId) if s.oemId else None,
            "name": s.name,
            "location": s.location,
            "city": s.city,
            "country": s.country,
            "region": s.region,
            "commodities": s.commodities,
            "metadata": s.metadata_,
            "latestRiskScore": (
                float(s.latestRiskScore)
                if getattr(s, "latestRiskScore", None) is not None
                else None
            ),
            "latestRiskLevel": getattr(s, "latestRiskLevel", None),
            "createdAt": s.createdAt.isoformat() if s.createdAt else None,
            "updatedAt": s.updatedAt.isoformat() if s.updatedAt else None,
            "riskSummary": risk_map.get(
                s.name, {"count": 0, "bySeverity": {}, "latest": None}
            ),
            "swarm": swarm_map.get(s.id),
        }
        for s in suppliers
    ]
    await broadcast_suppliers_snapshot(str(oem_id), payload)


# ── Graph nodes ────────────────────────────────────────────────────────────────

async def _process_next_supplier(
    state: OemOrchestrationState,
    config: RunnableConfig,
) -> OemOrchestrationState:
    """
    Pop one SupplierWorkflowContext from ``remaining_contexts``, run the full
    analysis pipeline for that supplier, and persist results to the DB.

    Steps per supplier
    ------------------
    1. Fetch all data sources in parallel (weather, news, global news, shipping).
    2. Invoke SupplierRiskGraph — runs all 3 domain agents in parallel.
    3. Persist risk and opportunity rows to the DB.
    4. Update ``Supplier.latestRiskScore`` and create a ``SupplierRiskAnalysis`` row.
    5. Broadcast a partial supplier snapshot over WebSocket.
    """
    db: Session = config["configurable"]["db"]
    oem_id = UUID(state["oem_id"])

    remaining = list(state.get("remaining_contexts") or [])
    ctx: SupplierWorkflowContext = remaining.pop(0)
    processed = list(state.get("processed_contexts") or []) + [ctx]

    scope: OemScope = ctx["scope"]
    agent_status_id = UUID(ctx["agent_status_id"])
    workflow_run_id = UUID(ctx["workflow_run_id"])
    supplier_id_uuid = UUID(scope["supplierId"]) if scope.get("supplierId") else None
    label = scope.get("supplierName") or scope.get("oemName") or "unknown"

    logger.info("OemOrchestrationGraph: starting supplier '%s'", label)

    # ── 1. Fetch data ──────────────────────────────────────────────────────────
    _update_status(
        db, agent_status_id,
        AgentStatus.MONITORING.value,
        f"Fetching data for supplier: {label}",
    )
    await _broadcast_status(db, agent_status_id)

    fetched = await _fetch_all_data(scope)

    # ── 2. SupplierRiskGraph (3 agents in parallel) ────────────────────────────
    _update_status(
        db, agent_status_id,
        AgentStatus.ANALYZING.value,
        f"Running domain agents for supplier: {label}",
    )
    await _broadcast_status(db, agent_status_id)

    initial: SupplierRiskState = {
        "supplier_scope": scope,
        "raw_weather_data": fetched["weather"],
        "raw_news_data": fetched["news"],
        "raw_global_news_data": fetched["global_news"],
        "raw_shipping_data": fetched["shipping"],
    }
    final: SupplierRiskState = await SUPPLIER_RISK_GRAPH.ainvoke(initial)  # type: ignore[assignment]

    all_risks: list[dict] = final.get("all_risks") or []
    all_opportunities: list[dict] = final.get("all_opportunities") or []
    unified_score: float = final.get("unified_score") or 0.0
    domain_scores: dict = final.get("domain_scores") or {}
    risk_level: str = final.get("risk_level") or "LOW"

    # ── 3. Persist to DB ───────────────────────────────────────────────────────
    _update_status(
        db, agent_status_id,
        AgentStatus.PROCESSING.value,
        f"Saving results for supplier: {label}",
    )
    await _broadcast_status(db, agent_status_id)

    supplier_name = scope.get("supplierName")
    for r in all_risks:
        r["oemId"] = oem_id
        if supplier_id_uuid is not None:
            r["supplierId"] = supplier_id_uuid
        if supplier_name and not r.get("affectedSupplier"):
            r["affectedSupplier"] = supplier_name
            r["supplierName"] = supplier_name
        create_risk_from_dict(
            db, r,
            agent_status_id=agent_status_id,
            workflow_run_id=workflow_run_id,
        )

    for o in all_opportunities:
        o["oemId"] = oem_id
        if supplier_id_uuid is not None:
            o["supplierId"] = supplier_id_uuid
        create_opportunity_from_dict(
            db, o,
            agent_status_id=agent_status_id,
            workflow_run_id=workflow_run_id,
        )

    # ── 4. Update Supplier.latestRiskScore ────────────────────────────────────
    if supplier_id_uuid:
        _, _, severity_counts = compute_score_from_dicts(all_risks)
        for supplier in get_suppliers(db, oem_id):
            if supplier.id != supplier_id_uuid:
                continue
            supplier.latestRiskScore = unified_score
            supplier.latestRiskLevel = risk_level
            db.commit()

            # Refresh the Risk rows just persisted to get their DB IDs.
            supplier_risk_rows = (
                db.query(Risk)
                .filter(
                    Risk.oemId == oem_id,
                    Risk.supplierId == supplier_id_uuid,
                    Risk.workflowRunId == workflow_run_id,
                    Risk.status == RiskStatus.DETECTED,
                )
                .all()
            )
            sra = SupplierRiskAnalysis(
                oemId=oem_id,
                workflowRunId=workflow_run_id,
                supplierId=supplier_id_uuid,
                riskScore=unified_score,
                risks=[str(r.id) for r in supplier_risk_rows],
                description=(
                    f"Supplier risk score for {label} "
                    f"in workflow run {workflow_run_id}"
                ),
                metadata_={
                    "severityCounts": severity_counts,
                    "domainScores": domain_scores,
                },
            )
            db.add(sra)
            db.commit()

            # ── 4b. Swarm analysis (rule-based from domain agent risks) ────
            from app.models.swarm_analysis import SwarmAnalysis

            fallback = _build_swarm_summary_for_supplier(supplier_risk_rows)
            if fallback:
                db.add(SwarmAnalysis(
                    supplierRiskAnalysisId=sra.id,
                    supplierId=supplier_id_uuid,
                    oemId=oem_id,
                    finalScore=fallback["finalScore"],
                    riskLevel=fallback["riskLevel"],
                    topDrivers=fallback["topDrivers"],
                    mitigationPlan=fallback["mitigationPlan"],
                    agents=fallback["agents"],
                    llmRawResponse=None,
                    metadata_={"scoringMethod": "rule_based"},
                ))
                db.commit()

            break

    # ── 5. Partial WebSocket broadcast ─────────────────────────────────────────
    await _broadcast_suppliers(db, oem_id)

    result: SupplierRiskResult = {
        "supplier_scope": scope,
        "all_risks": all_risks,
        "all_opportunities": all_opportunities,
        "unified_score": unified_score,
        "risk_level": risk_level,
        "domain_scores": domain_scores,
    }

    logger.info(
        "OemOrchestrationGraph: supplier '%s' done — risks=%d score=%.2f level=%s",
        label, len(all_risks), unified_score, risk_level,
    )

    return {
        "remaining_contexts": remaining,
        "processed_contexts": processed,
        "supplier_results": (state.get("supplier_results") or []) + [result],
    }


def _should_continue(state: OemOrchestrationState) -> str:
    """Loop back to process_next_supplier until no contexts remain."""
    if state.get("remaining_contexts"):
        return "process_next_supplier"
    return "aggregate_oem_score"


async def _aggregate_oem_score(
    state: OemOrchestrationState,
    config: RunnableConfig,
) -> OemOrchestrationState:
    """
    Derive the OEM-level risk score by aggregating **per-supplier scores**
    rather than re-pooling every individual risk through the exponential curve
    (which inflates the OEM score far above the individual supplier scores).

    Formula:
        oem_score = 0.6 * mean(supplier_scores) + 0.4 * max(supplier_scores)

    This ensures the OEM score stays proportional to its suppliers while still
    being pulled toward the worst-performing supplier (risk-averse).
    """
    db: Session = config["configurable"]["db"]
    oem_id = UUID(state["oem_id"])

    # Collect all agent_status_ids for this OEM run so we can query
    # every risk created during this graph invocation.
    all_agent_ids = [
        UUID(ctx["agent_status_id"])
        for ctx in (state.get("processed_contexts") or [])
    ]
    all_workflow_ids = [
        UUID(ctx["workflow_run_id"])
        for ctx in (state.get("processed_contexts") or [])
    ]

    if not all_agent_ids:
        return {"oem_risk_score": 0.0, "oem_risk_level": "LOW"}

    all_risks_orm = (
        db.query(Risk)
        .filter(
            Risk.oemId == oem_id,
            Risk.status == RiskStatus.DETECTED,
            Risk.agentStatusId.in_(all_agent_ids),
        )
        .all()
    )

    # Still compute breakdown & severity_counts from pooled risks for
    # informational purposes (stored in the SupplyChainRiskScore row).
    risk_dicts = [
        {
            "severity": getattr(r.severity, "value", r.severity),
            "sourceType": r.sourceType,
            "sourceData": r.sourceData,
        }
        for r in all_risks_orm
    ]
    _, breakdown, severity_counts = compute_score_from_dicts(risk_dicts)

    # ── OEM score = weighted blend of per-supplier scores ─────────────────
    supplier_results = state.get("supplier_results") or []
    supplier_scores = [
        sr.get("unified_score") or 0.0 for sr in supplier_results
    ]

    if supplier_scores:
        avg_score = sum(supplier_scores) / len(supplier_scores)
        max_score = max(supplier_scores)
        # Blend: 60% average + 40% worst-case supplier
        overall = round(0.6 * avg_score + 0.4 * max_score, 2)
    else:
        overall = 0.0

    oem_risk_level = score_to_level(overall)

    # Use the first workflow_run_id as the canonical OEM-level run reference.
    db.add(
        SupplyChainRiskScore(
            oemId=oem_id,
            workflowRunId=all_workflow_ids[0],
            overallScore=overall,
            breakdown=breakdown,
            severityCounts=severity_counts,
            riskIds=(
                ",".join(str(r.id) for r in all_risks_orm) if all_risks_orm else None
            ),
        )
    )
    db.commit()

    logger.info(
        "OemOrchestrationGraph: OEM %s — overall_score=%.2f level=%s "
        "supplier_scores=%s risks=%d",
        state["oem_id"], overall, oem_risk_level,
        [round(s, 2) for s in supplier_scores],
        len(all_risks_orm),
    )

    return {"oem_risk_score": overall, "oem_risk_level": oem_risk_level}


async def _generate_plans(
    state: OemOrchestrationState,
    config: RunnableConfig,
) -> OemOrchestrationState:
    """
    Generate mitigation plans for all suppliers processed in this run:

    - One **combined** plan per supplier (groups all their risks).
    - Individual **per-risk** plans for risks not covered by a combined plan.
    - **Opportunity** plans for identified opportunities.
    """
    db: Session = config["configurable"]["db"]
    oem_id = UUID(state["oem_id"])
    all_agent_ids = [
        UUID(ctx["agent_status_id"])
        for ctx in (state.get("processed_contexts") or [])
    ]

    if not all_agent_ids:
        return {"plans_generated": 0}

    all_risks_orm = (
        db.query(Risk)
        .filter(
            Risk.oemId == oem_id,
            Risk.status == RiskStatus.DETECTED,
            Risk.agentStatusId.in_(all_agent_ids),
        )
        .all()
    )

    # ── Combined plans per supplier ────────────────────────────────────────────
    risks_by_supplier: dict[str, list[Risk]] = {}
    for risk in all_risks_orm:
        names: list[str] = []
        if getattr(risk, "affectedSuppliers", None):
            names = [
                str(n).strip()
                for n in (risk.affectedSuppliers or [])
                if str(n).strip()
            ]
        elif risk.affectedSupplier:
            names = [risk.affectedSupplier.strip()]
        for name in names:
            if name:
                risks_by_supplier.setdefault(name, []).append(risk)

    combined_created = 0
    for supplier_name, risk_list in risks_by_supplier.items():
        plan_data = await generate_combined_mitigation_plan(
            supplier_name,
            [
                {
                    "id": r.id,
                    "title": r.title,
                    "severity": getattr(r.severity, "value", r.severity),
                    "description": r.description,
                    "affectedRegion": r.affectedRegion,
                }
                for r in risk_list
            ],
        )
        create_plan_from_dict(
            db, plan_data,
            risk_id=risk_list[0].id,
            opportunity_id=None,
            agent_status_id=all_agent_ids[0],
        )
        combined_created += 1

    # ── Per-risk plans for uncovered risks ────────────────────────────────────
    covered = {r.id for lst in risks_by_supplier.values() for r in lst}
    per_risk_created = 0
    for risk in all_risks_orm:
        if risk.id in covered:
            continue
        if db.query(MitigationPlan).filter(MitigationPlan.riskId == risk.id).count():
            continue
        aff_label: str | None = None
        if getattr(risk, "affectedSuppliers", None):
            aff_label = (
                ", ".join(
                    str(n).strip()
                    for n in (risk.affectedSuppliers or [])
                    if str(n).strip()
                )
                or None
            )
        if not aff_label:
            aff_label = risk.affectedSupplier

        plan_data = await generate_mitigation_plan(
            {
                "title": risk.title,
                "description": risk.description,
                "severity": getattr(risk.severity, "value", risk.severity),
                "affectedRegion": risk.affectedRegion,
                "affectedSupplier": aff_label,
            }
        )
        if plan_data and plan_data.get("title"):
            create_plan_from_dict(
                db, plan_data,
                risk_id=risk.id,
                opportunity_id=None,
                agent_status_id=all_agent_ids[0],
            )
            per_risk_created += 1

    # ── Opportunity plans ──────────────────────────────────────────────────────
    opportunities = (
        db.query(Opportunity)
        .filter(
            Opportunity.oemId == oem_id,
            Opportunity.status == OpportunityStatus.IDENTIFIED,
            Opportunity.agentStatusId.in_(all_agent_ids),
        )
        .all()
    )
    opp_created = 0
    for opp in opportunities:
        if (
            db.query(MitigationPlan)
            .filter(MitigationPlan.opportunityId == opp.id)
            .count()
        ):
            continue
        plan_data = await generate_opportunity_plan(
            {
                "title": opp.title,
                "description": opp.description,
                "type": getattr(opp.type, "value", opp.type),
                "potentialBenefit": opp.potentialBenefit,
            }
        )
        if plan_data and plan_data.get("title"):
            create_plan_from_dict(
                db, plan_data,
                risk_id=None,
                opportunity_id=opp.id,
                agent_status_id=all_agent_ids[0],
            )
            opp_created += 1

    total = combined_created + per_risk_created + opp_created
    logger.info(
        "OemOrchestrationGraph: plans — combined=%d per_risk=%d opp=%d",
        combined_created, per_risk_created, opp_created,
    )
    return {"plans_generated": total}


async def _broadcast_complete(
    state: OemOrchestrationState,
    config: RunnableConfig,
) -> OemOrchestrationState:
    """Mark every supplier's AgentStatus as COMPLETED and broadcast the final snapshot."""
    db: Session = config["configurable"]["db"]
    oem_id = UUID(state["oem_id"])

    for ctx in state.get("processed_contexts") or []:
        _update_status(
            db,
            UUID(ctx["agent_status_id"]),
            AgentStatus.COMPLETED.value,
            "Analysis completed",
        )

    await _broadcast_suppliers(db, oem_id)
    return {}


# ── Graph compilation ──────────────────────────────────────────────────────────

_oem_builder = StateGraph(OemOrchestrationState)
_oem_builder.add_node("process_next_supplier", _process_next_supplier)
_oem_builder.add_node("aggregate_oem_score", _aggregate_oem_score)
_oem_builder.add_node("generate_plans", _generate_plans)
_oem_builder.add_node("broadcast_complete", _broadcast_complete)

_oem_builder.set_entry_point("process_next_supplier")
_oem_builder.add_conditional_edges(
    "process_next_supplier",
    _should_continue,
    {
        "process_next_supplier": "process_next_supplier",
        "aggregate_oem_score": "aggregate_oem_score",
    },
)
_oem_builder.add_edge("aggregate_oem_score", "generate_plans")
_oem_builder.add_edge("generate_plans", "broadcast_complete")
_oem_builder.add_edge("broadcast_complete", END)

OEM_ORCHESTRATION_GRAPH = _oem_builder.compile()
