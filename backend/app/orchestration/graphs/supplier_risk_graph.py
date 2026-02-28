"""
SupplierRiskGraph
=================
A LangGraph StateGraph that composes the three domain agents — Weather,
News (supplier + global contexts), and Shipment — into a single parallel
analysis unit for one supplier scope.

Graph structure
---------------

    START
      │
      ▼
  [run_agents]          ← asyncio.gather over all 4 agent invocations
      │
      ▼
  [merge_and_score]     ← flatten risk lists; compute weighted unified score
      │
      ▼
     END

No database I/O occurs here. The caller (OemOrchestrationGraph or tests)
is responsible for persisting the output.
"""

import asyncio
import logging
import math
from collections import Counter

from langgraph.graph import StateGraph, END

from app.services.agent_types import OemScope
from app.agents.weather import run_weather_agent_graph
from app.agents.news import run_news_agent_graph
from app.agents.shipment import run_shipment_risk_graph
from app.data.active_conflicts import get_conflict_risks_for_supplier
from app.orchestration.graphs.states import SupplierRiskState

logger = logging.getLogger(__name__)

# ── Scoring constants (mirrors agent_service.py) ──────────────────────────────

SEVERITY_WEIGHT: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1}
DOMAIN_WEIGHTS: dict[str, float] = {"weather": 1.0, "shipping": 1.3, "news": 1.1, "geopolitical": 1.5}
RISK_SCORE_CURVE_K: float = 12.0


# ── Public scoring utilities (re-used by OemOrchestrationGraph) ───────────────

def compute_score_from_dicts(risks: list[dict]) -> tuple[float, dict, dict]:
    """
    Compute ``(overall_score, domain_breakdown, severity_counts)`` from a
    list of risk dicts produced by the domain agents.

    Mirrors ``_compute_risk_score`` in agent_service.py but operates on plain
    dicts instead of SQLAlchemy ORM objects so it can be used both inside the
    graph and after DB queries (via dict conversion).
    """
    severity_counts: dict[str, int] = {}
    breakdown: dict[str, float] = {}
    base_weight = 0.0

    for r in risks:
        sev = (r.get("severity") or "medium").lower()
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        sev_weight = SEVERITY_WEIGHT.get(sev, 2)

        src = r.get("sourceType") or "other"
        domain_weight = DOMAIN_WEIGHTS.get(src, 1.0)

        # Domain-specific pointer boosts from rich sourceData.
        pointer_boost = 1.0
        src_data = r.get("sourceData") or {}

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
            if risk_type in {"war", "armed_conflict"}:
                pointer_boost = 1.5
            elif risk_type in {"factory_shutdown", "bankruptcy_risk", "sanction_risk", "geopolitical_tension"}:
                pointer_boost = 1.3
        elif src == "geopolitical":
            pointer_boost = 1.5  # active conflict exposure is critical

        weight = sev_weight * domain_weight * pointer_boost
        base_weight += weight
        breakdown[src] = breakdown.get(src, 0.0) + weight

    overall = (
        0.0
        if not risks
        else round(100.0 * (1.0 - math.exp(-base_weight / RISK_SCORE_CURVE_K)), 2)
    )
    return overall, breakdown, severity_counts


def score_to_level(score: float) -> str:
    """Map 0–100 score to LOW / MEDIUM / HIGH / CRITICAL band."""
    if score <= 25:
        return "LOW"
    if score <= 50:
        return "MEDIUM"
    if score <= 75:
        return "HIGH"
    return "CRITICAL"


# ── Graph nodes ────────────────────────────────────────────────────────────────

async def _run_agents_node(state: SupplierRiskState) -> SupplierRiskState:
    """
    Run all four agent invocations concurrently:

    - Weather agent          (supplier scope)
    - News agent             (supplier context)
    - News agent             (global context)
    - Shipment agent         (supplier scope)

    All four calls are issued simultaneously via ``asyncio.gather`` so the
    total wall-clock time equals the slowest single agent rather than the
    sum of all four.
    """
    scope: OemScope = state["supplier_scope"]
    raw_weather = state.get("raw_weather_data") or {}
    raw_news = state.get("raw_news_data") or {}
    raw_global_news = state.get("raw_global_news_data") or {}

    prefetched_headlines = state.get("prefetched_broad_headlines")

    (
        weather_result,
        news_supplier_result,
        news_global_result,
        shipping_result,
    ) = await asyncio.gather(
        run_weather_agent_graph(raw_weather, scope),
        run_news_agent_graph(raw_news, scope, context="supplier", prefetched_broad_headlines=prefetched_headlines),
        run_news_agent_graph(raw_global_news, scope, context="global", prefetched_broad_headlines=prefetched_headlines),
        run_shipment_risk_graph(scope),
    )

    label = scope.get("supplierName") or scope.get("oemName") or "unknown"

    # ── Weather agent output ───────────────────────────────────────────────────
    w_risks = weather_result.get("risks") or []
    w_opps = weather_result.get("opportunities") or []
    logger.info(
        "SupplierRiskGraph[%s] ── WEATHER agent: risks=%d opportunities=%d",
        label, len(w_risks), len(w_opps),
    )
    for r in w_risks:
        logger.info(
            "  [weather risk] severity=%-8s title=%s | region=%s supplier=%s",
            r.get("severity", "?"),
            r.get("title", ""),
            r.get("affectedRegion") or "—",
            r.get("affectedSupplier") or "—",
        )
    for o in w_opps:
        logger.info(
            "  [weather opp ] type=%-20s title=%s",
            o.get("type", "?"),
            o.get("title", ""),
        )

    # ── News agent (supplier context) output ───────────────────────────────────
    ns_risks = news_supplier_result.get("risks") or []
    ns_opps = news_supplier_result.get("opportunities") or []
    logger.info(
        "SupplierRiskGraph[%s] ── NEWS (supplier) agent: risks=%d opportunities=%d",
        label, len(ns_risks), len(ns_opps),
    )
    for r in ns_risks:
        logger.info(
            "  [news-supplier risk] severity=%-8s type=%-25s title=%s",
            r.get("severity", "?"),
            (r.get("sourceData") or {}).get("risk_type") or r.get("risk_type") or "?",
            r.get("title", ""),
        )
    for o in ns_opps:
        logger.info(
            "  [news-supplier opp ] type=%-20s title=%s",
            o.get("type", "?"),
            o.get("title", ""),
        )

    # ── News agent (global context) output ─────────────────────────────────────
    ng_risks = news_global_result.get("risks") or []
    logger.info(
        "SupplierRiskGraph[%s] ── NEWS (global) agent: risks=%d",
        label, len(ng_risks),
    )
    for r in ng_risks:
        logger.info(
            "  [news-global  risk] severity=%-8s type=%-25s title=%s",
            r.get("severity", "?"),
            (r.get("sourceData") or {}).get("risk_type") or r.get("risk_type") or "?",
            r.get("title", ""),
        )

    # ── Shipment agent output ──────────────────────────────────────────────────
    sh_risks = shipping_result.get("risks") or []
    logger.info(
        "SupplierRiskGraph[%s] ── SHIPMENT agent: risks=%d",
        label, len(sh_risks),
    )
    for r in sh_risks:
        src = (r.get("sourceData") or {})
        metrics = (src.get("riskMetrics") or {})
        delay_lbl = (metrics.get("delay_risk") or {}).get("label", "?")
        stag_lbl = (metrics.get("stagnation_risk") or {}).get("label", "?")
        vel_lbl = (metrics.get("velocity_risk") or {}).get("label", "?")
        logger.info(
            "  [shipment risk] severity=%-8s delay=%-8s stagnation=%-8s velocity=%-8s title=%s",
            r.get("severity", "?"),
            delay_lbl, stag_lbl, vel_lbl,
            r.get("title", ""),
        )

    # ── Geopolitical conflict (active conflict list) ─────────────────────────────
    # When supplier country/region matches a conflict country, inject critical risks
    # so score and swarm topDrivers reflect exposure.
    countries_from_scope = scope.get("countries") or []
    regions_from_scope = scope.get("regions") or []
    geo_risks = get_conflict_risks_for_supplier(
        countries=countries_from_scope,
        regions=regions_from_scope,
        supplier_name=scope.get("supplierName"),
    )
    if geo_risks:
        logger.info(
            "SupplierRiskGraph[%s] ── GEOPOLITICAL (active conflict): risks=%d",
            label, len(geo_risks),
        )
        for r in geo_risks:
            logger.info(
                "  [geopolitical risk] severity=%-8s title=%s | region=%s",
                r.get("severity", "?"),
                r.get("title", ""),
                r.get("affectedRegion") or "—",
            )

    return {
        "weather_risks": weather_result.get("risks") or [],
        "weather_opportunities": weather_result.get("opportunities") or [],
        "news_supplier_risks": news_supplier_result.get("risks") or [],
        "news_supplier_opportunities": news_supplier_result.get("opportunities") or [],
        "news_global_risks": news_global_result.get("risks") or [],
        "shipping_risks": shipping_result.get("risks") or [],
        "geopolitical_risks": geo_risks,
    }


def _merge_and_score_node(state: SupplierRiskState) -> SupplierRiskState:
    """
    Merge all domain risk and opportunity lists into unified flat lists,
    then compute the weighted unified score and risk level band.
    """
    all_risks: list[dict] = (
        (state.get("weather_risks") or [])
        + (state.get("news_supplier_risks") or [])
        + (state.get("news_global_risks") or [])
        + (state.get("shipping_risks") or [])
        + (state.get("geopolitical_risks") or [])
    )
    all_opportunities: list[dict] = (
        (state.get("weather_opportunities") or [])
        + (state.get("news_supplier_opportunities") or [])
    )

    unified_score, domain_scores, _ = compute_score_from_dicts(all_risks)
    risk_level = score_to_level(unified_score)

    label = (state.get("supplier_scope") or {}).get("supplierName") or ""
    logger.info(
        "SupplierRiskGraph[%s] ── SCORE: total_risks=%d unified_score=%.2f "
        "level=%s domain_scores=%s",
        label,
        len(all_risks),
        unified_score,
        risk_level,
        {k: round(v, 2) for k, v in domain_scores.items()},
    )
    # Severity breakdown
    sev_counts = Counter(r.get("severity", "unknown") for r in all_risks)
    logger.info(
        "SupplierRiskGraph[%s] ── severity breakdown: %s",
        label,
        dict(sev_counts),
    )

    return {
        "all_risks": all_risks,
        "all_opportunities": all_opportunities,
        "unified_score": unified_score,
        "domain_scores": domain_scores,
        "risk_level": risk_level,
    }


# ── Graph compilation ──────────────────────────────────────────────────────────

_builder = StateGraph(SupplierRiskState)
_builder.add_node("run_agents", _run_agents_node)
_builder.add_node("merge_and_score", _merge_and_score_node)
_builder.set_entry_point("run_agents")
_builder.add_edge("run_agents", "merge_and_score")
_builder.add_edge("merge_and_score", END)

SUPPLIER_RISK_GRAPH = _builder.compile()


# ── Public helper ──────────────────────────────────────────────────────────────

async def run_supplier_risk_graph(
    supplier_scope: OemScope,
    raw_weather_data: dict,
    raw_news_data: dict,
    raw_global_news_data: dict,
    raw_shipping_data: dict,
) -> SupplierRiskState:
    """
    Invoke ``SUPPLIER_RISK_GRAPH`` and return the final state.

    The returned dict contains:
    - ``all_risks``         — merged list of risk dicts (ready for DB persistence)
    - ``all_opportunities`` — merged list of opportunity dicts
    - ``unified_score``     — 0–100 float
    - ``domain_scores``     — per-domain weighted contribution breakdown
    - ``risk_level``        — LOW | MEDIUM | HIGH | CRITICAL
    """
    initial: SupplierRiskState = {
        "supplier_scope": supplier_scope,
        "raw_weather_data": raw_weather_data,
        "raw_news_data": raw_news_data,
        "raw_global_news_data": raw_global_news_data,
        "raw_shipping_data": raw_shipping_data,
    }
    return await SUPPLIER_RISK_GRAPH.ainvoke(initial)  # type: ignore[return-value]
