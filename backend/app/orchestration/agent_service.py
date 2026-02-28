import asyncio
import logging
import math
from datetime import datetime, date
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.agent_status import AgentStatusEntity, AgentStatus
from app.models.risk import Risk, RiskStatus
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.mitigation_plan import MitigationPlan
from app.models.supply_chain_risk_score import SupplyChainRiskScore
from app.models.workflow_run import WorkflowRun
from app.models.supplier_risk_analysis import SupplierRiskAnalysis
from app.services.oems import get_oem_by_id, get_all_oems
from app.services.suppliers import (
    get_all as get_suppliers,
    get_by_id as get_supplier_by_id,
    get_risks_by_supplier,
    get_latest_swarm_by_supplier,
)
from app.services.risks import create_risk_from_dict
from app.services.opportunities import create_opportunity_from_dict
from app.services.mitigation_plans import create_plan_from_dict
from app.services.agent_orchestrator import (
    generate_mitigation_plan,
    generate_combined_mitigation_plan,
    generate_opportunity_plan,
)
from app.services.agent_types import OemScope
from app.data.manager import get_data_source_manager
from app.agents.weather import run_weather_agent_graph
from app.agents.news import run_news_agent_graph
from app.agents.shipment import (
    run_shipment_risk_graph,
    shipping_risk_result_to_db_risks,
)
from app.services.websocket_manager import (
    broadcast_agent_status,
    broadcast_suppliers_snapshot,
)
from app.orchestration.graphs.states import (
    OemOrchestrationState,
    RiskAnalysisState,
    SupplierWorkflowContext,
)
from app.orchestration.graphs.oem_orchestration_graph import OEM_ORCHESTRATION_GRAPH
from app.orchestration.graphs.risk_analysis_graph import RISK_ANALYSIS_GRAPH
from app.orchestration.graphs.supplier_risk_graph import (
    compute_score_from_dicts,
    score_to_level,
)

logger = logging.getLogger(__name__)

# Base severity weights for individual risks.
SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}

# Domain weights let us emphasize certain risk sources in aggregation.
DOMAIN_WEIGHTS = {
    "weather": 1.0,
    "shipping": 1.3,
    "news": 1.1,
}

# Controls the curvature of the non-linear escalation function:
# score = 100 * (1 - exp(-base_weight / RISK_SCORE_CURVE_K))
RISK_SCORE_CURVE_K = 12.0

_is_running = False


def _ensure_agent_status(db: Session) -> AgentStatusEntity:
    """
    Ensure there is at least one AgentStatusEntity row.

    This is used primarily for the /agent/status endpoint to bootstrap
    an initial idle status on a fresh database. It always returns the
    most recently created row.
    """
    status = (
        db.query(AgentStatusEntity).order_by(AgentStatusEntity.createdAt.desc()).first()
    )
    if not status:
        status = AgentStatusEntity(
            status=AgentStatus.IDLE.value,
            risksDetected=0,
            opportunitiesIdentified=0,
            plansGenerated=0,
            lastUpdated=datetime.utcnow(),
        )
        db.add(status)
        db.commit()
        db.refresh(status)
    return status


def _get_running_status(db: Session) -> AgentStatusEntity | None:
    """
    Return the most recent agent_status row that represents an active run.

    A row is considered "running" only while it is in one of the
    transitional states: monitoring, analyzing, or processing. Idle and
    completed/error states are treated as non-running so a new trigger
    will create a fresh workflow entry.
    """
    return (
        db.query(AgentStatusEntity)
        .filter(
            AgentStatusEntity.status.in_(
                [
                    AgentStatus.MONITORING.value,
                    AgentStatus.ANALYZING.value,
                    AgentStatus.PROCESSING.value,
                ]
            )
        )
        .order_by(AgentStatusEntity.createdAt.desc())
        .first()
    )


def _create_agent_run_in_db(
    db: Session,
    oem_id: UUID | None,
    workflow_run_id: UUID | None,
    initial_task: str | None,
    supplier_id: UUID | None = None,
) -> AgentStatusEntity:
    """
    Create a new agent_status row representing a single workflow trigger.
    """
    ent = AgentStatusEntity(
        oemId=oem_id,
        workflowRunId=workflow_run_id,
        supplierId=supplier_id,
        status=AgentStatus.MONITORING.value,
        currentTask=initial_task,
        risksDetected=0,
        opportunitiesIdentified=0,
        plansGenerated=0,
        lastProcessedData=None,
        lastDataSource=None,
        errorMessage=None,
        metadata_=None,
        lastUpdated=datetime.utcnow(),
    )
    db.add(ent)
    db.commit()
    db.refresh(ent)
    return ent


def get_oem_scope(db: Session, oem_id: UUID) -> OemScope | None:
    oem = get_oem_by_id(db, oem_id)
    if not oem:
        return None
    suppliers = get_suppliers(db, oem_id)
    if not suppliers:
        logger.warning(
            "get_oem_scope: OEM %s has no suppliers; skipping workflow scope",
            oem_id,
        )
        return None
    supplier_names: list[str] = []
    locations: list[str] = []
    cities: list[str] = []
    countries: list[str] = []
    regions: list[str] = []
    commodities = set()

    # Seed scope with OEM's own location so weather/news/shipping analysis
    # always considers the OEM side of the network.
    if getattr(oem, "location", None):
        locations.append(oem.location)  # type: ignore[arg-type]
    if getattr(oem, "city", None):
        cities.append(oem.city)  # type: ignore[arg-type]
    # Prefer explicit countryCode when available, fall back to country.
    country_code = getattr(oem, "countryCode", None)
    if country_code:
        countries.append(country_code)  # type: ignore[arg-type]
    elif getattr(oem, "country", None):
        countries.append(oem.country)  # type: ignore[arg-type]
    if getattr(oem, "region", None):
        regions.append(oem.region)  # type: ignore[arg-type]

    for s in suppliers:
        if s.name:
            supplier_names.append(s.name)
        if s.location:
            locations.append(s.location)
        if s.city:
            cities.append(s.city)
        if getattr(s, "countryCode", None):
            countries.append(s.countryCode)
        elif s.country:
            countries.append(s.country)
        if s.region:
            regions.append(s.region)
        if s.commodities:
            for c in (s.commodities or "").replace(";", ",").split(","):
                c = c.strip()
                if c:
                    commodities.add(c)
    # Also fold in OEM-level commodities if present.
    if getattr(oem, "commodities", None):
        for c in (oem.commodities or "").replace(";", ",").split(","):
            c = c.strip()
            if c:
                commodities.add(c)
    return OemScope(
        oemId=str(oem_id),
        oemName=oem.name,
        supplierNames=list(dict.fromkeys(supplier_names)),
        locations=list(dict.fromkeys(locations)),
        cities=list(dict.fromkeys(cities)),
        countries=list(dict.fromkeys(countries)),
        regions=list(dict.fromkeys(regions)),
        commodities=list(commodities),
    )


def get_oem_supplier_scope(db: Session, oem_id: UUID, supplier) -> OemScope:
    """
    Build a scope for a single OEM-supplier pair (one supplier only).
    Used when the workflow runs per supplier so each run has oem_id + supplier_id.
    """
    oem = get_oem_by_id(db, oem_id)
    if not oem:
        raise ValueError(f"OEM {oem_id} not found")
    locations: list[str] = []
    cities: list[str] = []
    countries: list[str] = []
    regions: list[str] = []
    commodities = set()
    if getattr(oem, "location", None):
        locations.append(oem.location)  # type: ignore[arg-type]
    if getattr(oem, "city", None):
        cities.append(oem.city)  # type: ignore[arg-type]
    country_code = getattr(oem, "countryCode", None)
    if country_code:
        countries.append(country_code)  # type: ignore[arg-type]
    elif getattr(oem, "country", None):
        countries.append(oem.country)  # type: ignore[arg-type]
    if getattr(oem, "region", None):
        regions.append(oem.region)  # type: ignore[arg-type]
    if getattr(oem, "commodities", None):
        for c in (oem.commodities or "").replace(";", ",").split(","):
            c = c.strip()
            if c:
                commodities.add(c)
    if supplier.location:
        locations.append(supplier.location)
    if supplier.city:
        cities.append(supplier.city)
    if getattr(supplier, "countryCode", None):
        countries.append(supplier.countryCode)
    elif supplier.country:
        countries.append(supplier.country)
    if supplier.region:
        regions.append(supplier.region)
    if supplier.commodities:
        for c in (supplier.commodities or "").replace(";", ",").split(","):
            c = c.strip()
            if c:
                commodities.add(c)
    return OemScope(
        oemId=str(oem_id),
        oemName=oem.name,
        supplierNames=[supplier.name] if supplier.name else [],
        locations=list(dict.fromkeys(locations)),
        cities=list(dict.fromkeys(cities)),
        countries=list(dict.fromkeys(countries)),
        regions=list(dict.fromkeys(regions)),
        commodities=list(commodities),
        supplierId=str(supplier.id),
        supplierName=supplier.name or "",
    )


def get_oem_supplier_scopes(db: Session, oem_id: UUID) -> list[OemScope]:
    """
    Return one scope per supplier for the given OEM.
    Each scope is an OEM-supplier pair so the workflow can run once per supplier.
    """
    oem = get_oem_by_id(db, oem_id)
    if not oem:
        return []
    suppliers = get_suppliers(db, oem_id)
    if not suppliers:
        logger.warning(
            "get_oem_supplier_scopes: OEM %s has no suppliers; returning empty list",
            oem_id,
        )
        return []
    return [get_oem_supplier_scope(db, oem_id, s) for s in suppliers]


def _build_data_source_params(scope: OemScope) -> dict:
    cities = (
        scope.get("cities") or scope.get("locations")[:10]
        if scope.get("locations")
        else ["New York", "London", "Tokyo", "Mumbai", "Shanghai"]
    )
    if not cities:
        cities = ["New York", "London", "Tokyo", "Mumbai", "Shanghai"]
    commodities = scope.get("commodities") or [
        "steel",
        "copper",
        "oil",
        "grain",
        "semiconductors",
    ]

    # Model logistics explicitly as routes from each supplier city to OEM city.
    # By construction in get_oem_scope, the first city (if present) is the OEM.
    routes: list[dict] = []
    if cities:
        oem_city = cities[0]
        supplier_cities = cities[1:] or [oem_city]
        for c in supplier_cities[:10]:
            if c == oem_city:
                continue
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


def _compute_risk_score(risks: list) -> tuple[float, dict, dict]:
    """
    Risk Analysis Agent:

    - Normalize all risks onto a 0-100 scale using severity and domain weights.
    - Apply a non-linear escalation curve so many medium risks escalate faster
      than a simple linear sum.
    - Track per-severity counts and per-sourceType weighted contributions.
    """
    severity_counts: dict[str, int] = {}
    breakdown: dict[str, float] = {}
    base_weight = 0.0
    for r in risks:
        sev = (getattr(r.severity, "value", r.severity) or "medium").lower()
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        sev_weight = SEVERITY_WEIGHT.get(sev, 2)

        src = r.sourceType or "other"
        domain_weight = DOMAIN_WEIGHTS.get(src, 1.0)

        # Risk-pointer aware nudges based on richer sourceData.
        # Shipping: escalate when delay/stagnation metrics are critical.
        pointer_boost = 1.0
        src_data = getattr(r, "sourceData", None) or {}
        if src == "shipping":
            metrics = (src_data or {}).get("riskMetrics") or {}
            delay = (metrics.get("delay_risk") or {}).get("label")
            stagnation = (metrics.get("stagnation_risk") or {}).get("label")
            if delay == "critical" or stagnation == "critical":
                pointer_boost = 1.5
            elif delay == "high" or stagnation == "high":
                pointer_boost = 1.25
        elif src == "weather":
            exposure = ((src_data or {}).get("weatherExposure") or {}).get(
                "weather_exposure_score"
            )
            if isinstance(exposure, (int, float)):
                if exposure >= 80:
                    pointer_boost = 1.4
                elif exposure >= 60:
                    pointer_boost = 1.2
        elif src == "news":
            risk_type = (src_data or {}).get("risk_type")
            if risk_type in {"factory_shutdown", "bankruptcy_risk", "sanction_risk"}:
                pointer_boost = 1.3

        weight = sev_weight * domain_weight * pointer_boost
        base_weight += weight
        breakdown[src] = breakdown.get(src, 0.0) + weight

    # Score 0-100 using a saturating escalation curve. No risks => 0.
    overall = (
        0.0
        if not risks
        else round(
            100.0 * (1.0 - math.exp(-base_weight / RISK_SCORE_CURVE_K)),
            2,
        )
    )
    return overall, breakdown, severity_counts


def _score_to_level(score: float) -> str:
    """
    Map final numeric score to a discrete risk band.
    """
    if score <= 25:
        return "LOW"
    if score <= 50:
        return "MEDIUM"
    if score <= 75:
        return "HIGH"
    return "CRITICAL"


def _update_status(
    db: Session,
    status: str,
    task: str | None = None,
    agent_status_id: UUID | None = None,
) -> None:
    """
    Update the status row for the current run. If an explicit id is
    provided, update that row; otherwise fall back to the latest row.
    """
    q = db.query(AgentStatusEntity)
    if agent_status_id:
        ent = q.filter(AgentStatusEntity.id == agent_status_id).first()
    else:
        ent = q.order_by(AgentStatusEntity.createdAt.desc()).first()
    if not ent:
        return
    ent.status = status
    ent.currentTask = task
    ent.lastUpdated = datetime.utcnow()
    db.commit()


async def _broadcast_current_status(
    db: Session,
    agent_status_id: UUID | None = None,
) -> None:
    """
    Build a lightweight status payload and broadcast it to websocket clients.
    """
    ent = (
        get_status(db)
        if agent_status_id is None
        else db.query(AgentStatusEntity)
        .filter(AgentStatusEntity.id == agent_status_id)
        .first()
    )
    if not ent:
        return
    payload = {
        "id": str(ent.id),
        "status": ent.status,
        "currentTask": ent.currentTask,
        "lastProcessedData": ent.lastProcessedData,
        "lastDataSource": ent.lastDataSource,
        "errorMessage": ent.errorMessage,
        "risksDetected": ent.risksDetected,
        "opportunitiesIdentified": ent.opportunitiesIdentified,
        "plansGenerated": ent.plansGenerated,
        "lastUpdated": ent.lastUpdated.isoformat() if ent.lastUpdated else None,
        "createdAt": ent.createdAt.isoformat() if ent.createdAt else None,
    }
    await broadcast_agent_status(payload)


async def _broadcast_suppliers_for_oem(db: Session, oem_id: UUID) -> None:
    """
    Broadcast the latest per-supplier snapshot for the given OEM.

    This is safe to call multiple times during a run; it always recomputes
    based on the current database state.
    """
    suppliers = get_suppliers(db, oem_id)
    if not suppliers:
        return
    risk_map = get_risks_by_supplier(db)
    swarm_map = get_latest_swarm_by_supplier(db, oem_id)
    suppliers_payload = [
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
                s.name,
                {
                    "count": 0,
                    "bySeverity": {},
                    "latest": None,
                },
            ),
            "swarm": swarm_map.get(s.id),
        }
        for s in suppliers
    ]
    await broadcast_suppliers_snapshot(str(oem_id), suppliers_payload)


async def _run_analysis_for_oem(
    db: Session,
    scope: OemScope,
    agent_status_id: UUID,
    workflow_run_id: UUID,
) -> None:
    oem_id = UUID(scope["oemId"])
    manager = get_data_source_manager()
    await manager.initialize()

    logger.info(
        "_run_analysis_for_oem: start for OEM %s (%s)",
        scope["oemId"],
        scope["oemName"],
    )

    # 1. Supplier-scoped: weather + news
    _update_status(
        db,
        AgentStatus.MONITORING.value,
        f"Fetching weather & news for OEM: {scope['oemName']}",
        agent_status_id,
    )
    await _broadcast_current_status(db, agent_status_id)
    supplier_params = _build_data_source_params(scope)
    supplier_data = await manager.fetch_by_types(["weather", "news"], supplier_params)
    logger.info(
        "_run_analysis_for_oem: supplier data fetched weather=%d news=%d for OEM %s",
        len(supplier_data.get("weather") or []),
        len(supplier_data.get("news") or []),
        scope["oemName"],
    )
    _update_status(
        db,
        AgentStatus.ANALYZING.value,
        f"Analyzing weather & news for OEM: {scope['oemName']}",
        agent_status_id,
    )
    await _broadcast_current_status(db, agent_status_id)

    weather_only = {"weather": supplier_data.get("weather") or []}
    news_only = {"news": supplier_data.get("news") or []}

    weather_result = await run_weather_agent_graph(weather_only, scope)
    news_result = await run_news_agent_graph(news_only, scope, context="supplier")

    combined_risks = (weather_result.get("risks") or []) + (
        news_result.get("risks") or []
    )
    combined_opps = (weather_result.get("opportunities") or []) + (
        news_result.get("opportunities") or []
    )

    logger.info(
        "_run_analysis_for_oem: supplier analysis results "
        "risks=%d opportunities=%d for OEM %s",
        len(combined_risks),
        len(combined_opps),
        scope["oemName"],
    )
    _update_status(
        db,
        AgentStatus.PROCESSING.value,
        f"Saving supplier results for OEM: {scope['oemName']}",
        agent_status_id,
    )
    await _broadcast_current_status(db, agent_status_id)
    supplier_id_from_scope = (
        UUID(scope["supplierId"]) if scope.get("supplierId") else None
    )
    supplier_name_from_scope = scope.get("supplierName")
    for r in combined_risks:
        r["oemId"] = oem_id
        if supplier_id_from_scope is not None:
            r["supplierId"] = supplier_id_from_scope
        if supplier_name_from_scope and not r.get("affectedSupplier"):
            r["affectedSupplier"] = supplier_name_from_scope
            r["supplierName"] = supplier_name_from_scope
        create_risk_from_dict(
            db,
            r,
            agent_status_id=agent_status_id,
            workflow_run_id=workflow_run_id,
        )
    for o in combined_opps:
        o["oemId"] = oem_id
        if supplier_id_from_scope is not None:
            o["supplierId"] = supplier_id_from_scope
        create_opportunity_from_dict(
            db,
            o,
            agent_status_id=agent_status_id,
            workflow_run_id=workflow_run_id,
        )

    # Broadcast after supplier-scoped risks/opportunities have been stored so
    # the dashboard can show early signals per supplier.
    await _broadcast_suppliers_for_oem(db, oem_id)

    # 2. Global risk
    _update_status(
        db,
        AgentStatus.MONITORING.value,
        "Fetching global news",
        agent_status_id,
    )
    await _broadcast_current_status(db, agent_status_id)
    global_data = await manager.fetch_by_types(["news"], _build_global_news_params())
    global_result = await run_news_agent_graph(global_data, scope, context="global")
    logger.info(
        "_run_analysis_for_oem: global news analysis risks=%d for OEM %s",
        len(global_result.get("risks") or []),
        scope["oemName"],
    )
    for r in global_result["risks"]:
        r["oemId"] = oem_id
        if supplier_id_from_scope is not None:
            r["supplierId"] = supplier_id_from_scope
        if supplier_name_from_scope and not r.get("affectedSupplier"):
            r["affectedSupplier"] = supplier_name_from_scope
            r["supplierName"] = supplier_name_from_scope
        create_risk_from_dict(
            db,
            r,
            agent_status_id=agent_status_id,
            workflow_run_id=workflow_run_id,
        )

    # Broadcast again after global risks have been incorporated.
    await _broadcast_suppliers_for_oem(db, oem_id)

    # 3. Shipping routes
    _update_status(
        db,
        AgentStatus.MONITORING.value,
        f"Fetching shipping for OEM: {scope['oemName']}",
        agent_status_id,
    )
    await _broadcast_current_status(db, agent_status_id)
    route_params = {"routes": supplier_params["routes"]}
    route_data = await manager.fetch_by_types(["traffic", "shipping"], route_params)
    # Run Shipment Agent (LangGraph + LangChain) — it fetches tracking data itself.
    shipping_result = await run_shipment_risk_graph(scope)
    logger.info(
        "_run_analysis_for_oem: shipping analysis score=%s for OEM %s",
        shipping_result.get("shipping_risk_score"),
        scope["oemName"],
    )
    db_risks = shipping_risk_result_to_db_risks(shipping_result, scope)
    for r in db_risks:
        r["oemId"] = oem_id
        if supplier_id_from_scope is not None:
            r["supplierId"] = supplier_id_from_scope
        if supplier_name_from_scope and not r.get("affectedSupplier"):
            r["affectedSupplier"] = supplier_name_from_scope
            r["supplierName"] = supplier_name_from_scope
        create_risk_from_dict(
            db,
            r,
            agent_status_id=agent_status_id,
            workflow_run_id=workflow_run_id,
        )

    # 4. Risk score (OEM-level)
    all_risks = (
        db.query(Risk)
        .filter(
            Risk.oemId == oem_id,
            Risk.status == RiskStatus.DETECTED,
            Risk.agentStatusId == agent_status_id,
        )
        .all()
    )
    overall, breakdown, severity_counts = _compute_risk_score(all_risks)
    score_ent = SupplyChainRiskScore(
        oemId=oem_id,
        workflowRunId=workflow_run_id,
        overallScore=overall,
        breakdown=breakdown,
        severityCounts=severity_counts,
        riskIds=",".join(str(r.id) for r in all_risks) if all_risks else None,
    )
    db.add(score_ent)
    db.commit()
    logger.info(
        "_run_analysis_for_oem: risk score stored overall=%s for OEM %s (risks=%d)",
        overall,
        scope["oemName"],
        len(all_risks),
    )

    # 4b. Per-supplier risk scores (supplier-level)
    suppliers = get_suppliers(db, oem_id)
    for supplier in suppliers:
        supplier_risks = (
            db.query(Risk)
            .filter(
                Risk.oemId == oem_id,
                Risk.status == RiskStatus.DETECTED,
                Risk.supplierId == supplier.id,
                Risk.workflowRunId == workflow_run_id,
            )
            .all()
        )
        if not supplier_risks:
            supplier.latestRiskScore = None
            supplier.latestRiskLevel = None
            continue
        supplier_score, _, severity_counts = _compute_risk_score(supplier_risks)
        supplier.latestRiskScore = supplier_score
        supplier.latestRiskLevel = _score_to_level(float(supplier_score))

        analysis_entry = SupplierRiskAnalysis(
            oemId=oem_id,
            workflowRunId=workflow_run_id,
            supplierId=supplier.id,
            riskScore=supplier_score,
            risks=[str(r.id) for r in supplier_risks],
            description=f"Supplier risk score for {supplier.name} in workflow run {workflow_run_id}",
            metadata_={
                "severityCounts": severity_counts,
            },
        )
        db.add(analysis_entry)
    db.commit()

    # Broadcast after supplier-level risk scores have been updated.
    await _broadcast_suppliers_for_oem(db, oem_id)

    # 5. Mitigation plans by supplier
    risks_by_supplier: dict[str, list[Risk]] = {}
    for risk in all_risks:
        names: list[str] = []
        if getattr(risk, "affectedSuppliers", None):
            names = [
                (str(n).strip())
                for n in (risk.affectedSuppliers or [])
                if str(n).strip()
            ]
        elif risk.affectedSupplier:
            names = [risk.affectedSupplier.strip()]
        for key in names:
            if not key:
                continue
            risks_by_supplier.setdefault(key, []).append(risk)
    combined_plans_created = 0
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
            db,
            plan_data,
            risk_id=risk_list[0].id,
            opportunity_id=None,
            agent_status_id=agent_status_id,
        )
        combined_plans_created += 1
    logger.info(
        "_run_analysis_for_oem: combined mitigation plans created=%d for OEM %s",
        combined_plans_created,
        scope["oemName"],
    )

    # 6. Per-risk plans for risks without supplier or not in combined
    risks_with_plan_supplier = set()
    for risk_list in risks_by_supplier.values():
        for r in risk_list:
            risks_with_plan_supplier.add(r.id)
    needs_plan = (
        db.query(Risk)
        .filter(
            Risk.oemId == oem_id,
            Risk.status == RiskStatus.DETECTED,
            Risk.agentStatusId == agent_status_id,
        )
        .all()
    )
    per_risk_plans_created = 0
    for risk in needs_plan:
        if risk.id in risks_with_plan_supplier:
            continue
        plans = (
            db.query(MitigationPlan).filter(MitigationPlan.riskId == risk.id).count()
        )
        if plans > 0:
            continue
        # For per-risk plans, include all affected suppliers as a
        # comma-separated label for readability in the prompt.
        aff_label = None
        if getattr(risk, "affectedSuppliers", None):
            aff_label = (
                ", ".join(
                    [
                        str(n).strip()
                        for n in (risk.affectedSuppliers or [])
                        if str(n).strip()
                    ]
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
                db,
                plan_data,
                risk_id=risk.id,
                opportunity_id=None,
                agent_status_id=agent_status_id,
            )
            per_risk_plans_created += 1
        elif not plan_data:
            logger.warning(
                "Skipping mitigation plan for risk %s: LLM returned empty plan "
                "(e.g. invalid API key or parse error)",
                risk.id,
            )
    logger.info(
        "_run_analysis_for_oem: per-risk mitigation plans created=%d for OEM %s",
        per_risk_plans_created,
        scope["oemName"],
    )

    # 7. Opportunity plans
    opportunities = (
        db.query(Opportunity)
        .filter(
            Opportunity.oemId == oem_id,
            Opportunity.status == OpportunityStatus.IDENTIFIED,
            Opportunity.agentStatusId == agent_status_id,
        )
        .all()
    )
    opp_plans_created = 0
    for opp in opportunities:
        if (
            db.query(MitigationPlan)
            .filter(MitigationPlan.opportunityId == opp.id)
            .count()
            > 0
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
                db,
                plan_data,
                risk_id=None,
                opportunity_id=opp.id,
                agent_status_id=agent_status_id,
            )
            opp_plans_created += 1
    logger.info(
        "_run_analysis_for_oem: opportunity plans created=%d for OEM %s",
        opp_plans_created,
        scope["oemName"],
    )

    # 8. Final broadcast so dashboard cards reflect the full analysis run.
    await _broadcast_suppliers_for_oem(db, oem_id)


def get_status(db: Session) -> AgentStatusEntity | None:
    """
    Latest agent_status row, representing the most recent workflow run.

    Used by the dashboard to display the current/last run.
    """
    return (
        db.query(AgentStatusEntity).order_by(AgentStatusEntity.createdAt.desc()).first()
    )


def get_latest_risk_score(db: Session, oem_id: UUID) -> SupplyChainRiskScore | None:
    return (
        db.query(SupplyChainRiskScore)
        .filter(SupplyChainRiskScore.oemId == oem_id)
        .order_by(SupplyChainRiskScore.createdAt.desc())
        .first()
    )


def trigger_manual_analysis_sync(db: Session, oem_id: UUID | None) -> None:
    global _is_running
    # First, check for any in-progress run in the database so we don't
    # create duplicate runs across processes.
    running = _get_running_status(db)
    if running:
        logger.warning(
            "Agent run already in progress with id %s and status %s",
            running.id,
            running.status,
        )
        return

    if _is_running:
        logger.warning("Agent is already running (in-process flag)")
        return
    _is_running = True
    try:
        if oem_id:
            logger.info(
                "trigger_manual_analysis_sync: starting manual run for OEM %s",
                oem_id,
            )
            scopes = get_oem_supplier_scopes(db, oem_id)
            if not scopes:
                logger.warning("OEM %s not found or no supplier scopes", oem_id)
                return
            today = date.today()
            existing_count = (
                db.query(WorkflowRun)
                .filter(
                    WorkflowRun.oemId == oem_id,
                    WorkflowRun.runDate == today,
                )
                .count()
            )
            processed_names: list[str] = []
            for i, scope in enumerate(scopes):
                supplier_id_uuid = (
                    UUID(scope["supplierId"]) if scope.get("supplierId") else None
                )
                workflow_run = WorkflowRun(
                    oemId=oem_id,
                    supplierId=supplier_id_uuid,
                    runDate=today,
                    runIndex=existing_count + i + 1,
                )
                db.add(workflow_run)
                db.commit()
                db.refresh(workflow_run)

                task_label = (
                    f"Manual run for OEM: {scope['oemName']} / Supplier: {scope.get('supplierName', '')}"
                    if scope.get("supplierName")
                    else f"Manual run for OEM: {scope['oemName']}"
                )
                run = _create_agent_run_in_db(
                    db,
                    oem_id=oem_id,
                    workflow_run_id=workflow_run.id,
                    initial_task=task_label,
                    supplier_id=supplier_id_uuid,
                )
                asyncio.run(
                    _run_analysis_for_oem(db, scope, run.id, workflow_run.id)
                )
                run.risksDetected = (
                    db.query(Risk)
                    .filter(
                        Risk.agentStatusId == run.id,
                        Risk.workflowRunId == workflow_run.id,
                    )
                    .count()
                )
                run.opportunitiesIdentified = (
                    db.query(Opportunity)
                    .filter(
                        Opportunity.agentStatusId == run.id,
                        Opportunity.workflowRunId == workflow_run.id,
                    )
                    .count()
                )
                run.plansGenerated = (
                    db.query(MitigationPlan)
                    .filter(MitigationPlan.agentStatusId == run.id)
                    .count()
                )
                run.lastProcessedData = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "oemsProcessed": [scope["oemName"]],
                    "supplierId": scope.get("supplierId"),
                    "supplierName": scope.get("supplierName"),
                    "workflowRunId": str(workflow_run.id),
                }
                db.commit()
                _update_status(
                    db,
                    AgentStatus.COMPLETED.value,
                    "Manual analysis completed",
                    agent_status_id=run.id,
                )
                if scope.get("supplierName"):
                    processed_names.append(scope["supplierName"])
        else:
            logger.info("trigger_manual_analysis_sync: starting run for all OEMs")
            oems = get_all_oems(db)
            if not oems:
                _update_status(
                    db,
                    AgentStatus.COMPLETED.value,
                    "No OEMs to process",
                )
                return
            # Create a separate workflow run + status row per OEM-supplier pair.
            processed_oems: list[str] = []
            for oem in oems:
                scopes = get_oem_supplier_scopes(db, oem.id)
                if not scopes:
                    continue
                today = date.today()
                existing_count = (
                    db.query(WorkflowRun)
                    .filter(
                        WorkflowRun.oemId == oem.id,
                        WorkflowRun.runDate == today,
                    )
                    .count()
                )
                for i, scope in enumerate(scopes):
                    supplier_id_uuid = (
                        UUID(scope["supplierId"])
                        if scope.get("supplierId")
                        else None
                    )
                    workflow_run = WorkflowRun(
                        oemId=oem.id,
                        supplierId=supplier_id_uuid,
                        runDate=today,
                        runIndex=existing_count + i + 1,
                    )
                    db.add(workflow_run)
                    db.commit()
                    db.refresh(workflow_run)

                    task_label = (
                        f"Monitoring cycle for OEM: {oem.name} / Supplier: {scope.get('supplierName', '')}"
                        if scope.get("supplierName")
                        else f"Monitoring cycle for OEM: {oem.name}"
                    )
                    run = _create_agent_run_in_db(
                        db,
                        oem_id=oem.id,
                        workflow_run_id=workflow_run.id,
                        initial_task=task_label,
                        supplier_id=supplier_id_uuid,
                    )
                    asyncio.run(
                        _run_analysis_for_oem(
                            db, scope, run.id, workflow_run.id
                        )
                    )
                    run.risksDetected = (
                        db.query(Risk)
                        .filter(
                            Risk.agentStatusId == run.id,
                            Risk.workflowRunId == workflow_run.id,
                        )
                        .count()
                    )
                    run.opportunitiesIdentified = (
                        db.query(Opportunity)
                        .filter(
                            Opportunity.agentStatusId == run.id,
                            Opportunity.workflowRunId == workflow_run.id,
                        )
                        .count()
                    )
                    run.plansGenerated = (
                        db.query(MitigationPlan)
                        .filter(MitigationPlan.agentStatusId == run.id)
                        .count()
                    )
                    run.lastProcessedData = {
                        "timestamp": datetime.utcnow().isoformat(),
                        "oemsProcessed": [scope["oemName"]],
                        "supplierId": scope.get("supplierId"),
                        "supplierName": scope.get("supplierName"),
                        "workflowRunId": str(workflow_run.id),
                    }
                    db.commit()
                    _update_status(
                        db,
                        AgentStatus.COMPLETED.value,
                        "Monitoring cycle completed for OEM",
                        agent_status_id=run.id,
                    )
                processed_oems.append(oem.name)

    except Exception as e:
        logger.exception("Error in analysis: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
        # Attempt to mark the most recent run as errored.
        latest = get_status(db)
        if latest:
            latest.status = AgentStatus.ERROR.value
            latest.errorMessage = f"Error: {e}"
            latest.lastUpdated = datetime.utcnow()
            db.commit()
    finally:
        _is_running = False


def trigger_manual_analysis_v2_sync(db: Session, oem_id: UUID | None) -> None:
    """
    Graph-based risk analysis trigger (v2).

    Creates WorkflowRun + AgentStatus rows per supplier, then delegates
    all analysis logic to ``RISK_ANALYSIS_GRAPH``.

    The graph runs the News Agent (supplier + global contexts) and the
    Shipment Weather Agent for each supplier in parallel, persists results,
    computes per-supplier scores, and aggregates an OEM-level risk score.
    """
    global _is_running
    running = _get_running_status(db)
    if running:
        logger.warning(
            "trigger_manual_analysis_v2_sync: run already in progress id=%s status=%s",
            running.id,
            running.status,
        )
        return
    if _is_running:
        logger.warning("trigger_manual_analysis_v2_sync: in-process flag already set")
        return
    _is_running = True

    try:
        if not oem_id:
            logger.warning("trigger_manual_analysis_v2_sync: oem_id is required")
            return

        oem = get_oem_by_id(db, oem_id)
        if not oem:
            logger.warning("trigger_manual_analysis_v2_sync: OEM %s not found", oem_id)
            return

        scopes = get_oem_supplier_scopes(db, oem.id)
        if not scopes:
            logger.warning(
                "trigger_manual_analysis_v2_sync: OEM %s has no supplier scopes",
                oem.id,
            )
            return

        today = date.today()
        existing_count = (
            db.query(WorkflowRun)
            .filter(
                WorkflowRun.oemId == oem.id,
                WorkflowRun.runDate == today,
            )
            .count()
        )

        # Pre-create one WorkflowRun + AgentStatusEntity per supplier so the
        # existing DB structure and frontend expectations are preserved.
        contexts: list[SupplierWorkflowContext] = []
        for i, scope in enumerate(scopes):
            supplier_id_uuid = (
                UUID(scope["supplierId"]) if scope.get("supplierId") else None
            )
            workflow_run = WorkflowRun(
                oemId=oem.id,
                supplierId=supplier_id_uuid,
                runDate=today,
                runIndex=existing_count + i + 1,
            )
            db.add(workflow_run)
            db.commit()
            db.refresh(workflow_run)

            task_label = (
                f"{oem.name} / {scope.get('supplierName', '')}"
                if scope.get("supplierName")
                else f"{oem.name}"
            )
            run = _create_agent_run_in_db(
                db,
                oem_id=oem.id,
                workflow_run_id=workflow_run.id,
                initial_task=task_label,
                supplier_id=supplier_id_uuid,
            )
            contexts.append(
                SupplierWorkflowContext(
                    scope=scope,
                    workflow_run_id=str(workflow_run.id),
                    agent_status_id=str(run.id),
                )
            )

        logger.info(
            "trigger_manual_analysis_v2_sync: invoking RiskAnalysisGraph "
            "for OEM %s with %d supplier(s)",
            oem.id,
            len(contexts),
        )

        initial_state: RiskAnalysisState = {
            "oem_id": str(oem.id),
            "remaining_contexts": contexts,
            "processed_contexts": [],
            "supplier_results": [],
        }

        asyncio.run(
            RISK_ANALYSIS_GRAPH.ainvoke(
                initial_state,
                config={"configurable": {"db": db}},
            )
        )

    except Exception as e:
        logger.exception("trigger_manual_analysis_v2_sync: error — %s", e)
        try:
            db.rollback()
        except Exception:
            pass
        latest = get_status(db)
        if latest:
            latest.status = AgentStatus.ERROR.value
            latest.errorMessage = f"v2 error: {e}"
            latest.lastUpdated = datetime.utcnow()
            db.commit()
    finally:
        _is_running = False


def trigger_news_analysis_sync(
    db: Session, oem_id: UUID, supplier_id: UUID | None = None
) -> dict:
    """
    Run only the News Agent for a given OEM and persist results.

    Fetches from NewsAPI + GDELT (via the NEWS_GRAPH parallel fetch nodes),
    runs LLM risk/opportunity extraction for both supplier and global context,
    then saves the results to the DB.

    If supplier_id is provided, the scope is narrowed to that single supplier.

    Returns a dict with risksCreated and opportunitiesCreated counts.
    """
    oem = get_oem_by_id(db, oem_id)
    if not oem:
        logger.warning("trigger_news_analysis_sync: OEM %s not found", oem_id)
        return {"risksCreated": 0, "opportunitiesCreated": 0}

    # When a specific supplier is requested, build a supplier-scoped scope.
    if supplier_id:
        supplier = get_supplier_by_id(db, supplier_id)
        if not supplier:
            logger.warning(
                "trigger_news_analysis_sync: Supplier %s not found", supplier_id
            )
            return {"risksCreated": 0, "opportunitiesCreated": 0}
        scope = get_oem_supplier_scope(db, oem_id, supplier)
    else:
        # Build a best-effort scope — works even when no suppliers exist yet.
        scope = get_oem_scope(db, oem_id)
        if not scope:
            # Fall back to a minimal scope using only the OEM's own data.
            scope = OemScope(
                oemId=str(oem_id),
                oemName=oem.name,
                supplierNames=[],
                locations=[getattr(oem, "location", None) or ""],
                cities=[getattr(oem, "city", None) or ""],
                countries=[getattr(oem, "country", None) or ""],
                regions=[getattr(oem, "region", None) or ""],
                commodities=[],
            )

    today = date.today()
    existing_count = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.oemId == oem_id, WorkflowRun.runDate == today)
        .count()
    )
    workflow_run = WorkflowRun(
        oemId=oem_id,
        supplierId=supplier_id,
        runDate=today,
        runIndex=existing_count + 1,
    )
    db.add(workflow_run)
    db.commit()
    db.refresh(workflow_run)

    run = _create_agent_run_in_db(
        db,
        oem_id=oem_id,
        workflow_run_id=workflow_run.id,
        initial_task=f"News-only analysis for OEM: {oem.name}",
        supplier_id=supplier_id,
    )

    risks_created = 0
    opps_created = 0

    async def _run():
        nonlocal risks_created, opps_created

        _update_status(
            db,
            AgentStatus.ANALYZING.value,
            f"Fetching and analysing news for OEM: {oem.name}",
            run.id,
        )
        await _broadcast_current_status(db, run.id)

        # Run supplier-context and global-context passes in parallel.
        # Each graph invocation fetches NewsAPI + GDELT internally, so both
        # fetches and both LLM calls happen concurrently.
        supplier_result, global_result = await asyncio.gather(
            run_news_agent_graph({}, scope, context="supplier"),
            run_news_agent_graph({}, scope, context="global"),
        )

        all_risks = (supplier_result.get("risks") or []) + (
            global_result.get("risks") or []
        )
        all_opps = supplier_result.get("opportunities") or []

        logger.info(
            "trigger_news_analysis_sync: news agent produced risks=%d opps=%d for OEM %s",
            len(all_risks),
            len(all_opps),
            oem.name,
        )

        _update_status(
            db,
            AgentStatus.PROCESSING.value,
            f"Saving news risks for OEM: {oem.name}",
            run.id,
        )
        await _broadcast_current_status(db, run.id)

        for r in all_risks:
            r["oemId"] = oem_id
            create_risk_from_dict(
                db, r, agent_status_id=run.id, workflow_run_id=workflow_run.id
            )
            risks_created += 1

        for o in all_opps:
            o["oemId"] = oem_id
            create_opportunity_from_dict(
                db, o, agent_status_id=run.id, workflow_run_id=workflow_run.id
            )
            opps_created += 1

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.exception("trigger_news_analysis_sync: error — %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        run.status = AgentStatus.ERROR.value
        run.errorMessage = str(exc)
        run.lastUpdated = datetime.utcnow()
        db.commit()
        return {"risksCreated": 0, "opportunitiesCreated": 0}

    run.risksDetected = risks_created
    run.opportunitiesIdentified = opps_created
    run.lastProcessedData = {
        "timestamp": datetime.utcnow().isoformat(),
        "oemsProcessed": [oem.name],
        "workflowRunId": str(workflow_run.id),
        "newsOnly": True,
    }
    db.commit()
    _update_status(
        db,
        AgentStatus.COMPLETED.value,
        "News analysis completed",
        agent_status_id=run.id,
    )
    logger.info(
        "trigger_news_analysis_sync: completed risks=%d opps=%d for OEM %s",
        risks_created,
        opps_created,
        oem.name,
    )
    return {"risksCreated": risks_created, "opportunitiesCreated": opps_created}


def run_scheduled_cycle(db: Session) -> None:
    """Scheduled agent cycle. Disabled; use POST /agent/trigger to run."""
    logger.info("run_scheduled_cycle: disabled; use POST /agent/trigger to run.")
    return
