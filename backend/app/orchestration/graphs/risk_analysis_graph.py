"""
RiskAnalysisGraph
=================
A LangGraph StateGraph that drives the risk analysis pipeline for one OEM,
iterating over every supplier sequentially (safe for a single shared
SQLAlchemy session) and then aggregating an OEM-level risk score.

Runs the News Agent (supplier + global contexts) and the Shipment Weather
Agent per supplier, then persists results and computes scores.

Graph structure
---------------

    START
      |
      v
  [process_next_supplier]  <- news agent (supplier+global) + shipment weather
      |                       -> persist risks/opps -> compute per-supplier score
      |
      +---(more suppliers?)---> [process_next_supplier]   (loop)
      |
      v
  [aggregate_oem_score]    <- query all risks -> compute OEM SupplyChainRiskScore
      |
      v
  [broadcast_complete]     <- mark COMPLETED -> final WebSocket broadcast
      |
      v
     END

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
import json
import logging
import re
import time
import uuid as _uuid
from datetime import datetime
from uuid import UUID

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.models.agent_status import AgentStatusEntity, AgentStatus
from app.models.opportunity import Opportunity
from app.models.risk import Risk, RiskStatus
from app.models.supply_chain_risk_score import SupplyChainRiskScore
from app.models.supplier_risk_analysis import SupplierRiskAnalysis
from app.agents.news import run_news_agent_graph
from app.agents.shipment import run_shipment_risk_graph
from app.agents.weather import run_weather_graph
from app.services.agent_types import OemScope
from app.services.langchain_llm import get_chat_model
from app.services.llm_client import _persist_llm_log
from app.services.opportunities import create_opportunity_from_dict
from app.services.risks import create_risk_from_dict
from app.services.suppliers import (
    get_all as get_suppliers,
    get_risks_by_supplier,
    get_latest_swarm_by_supplier,
)
from app.services.websocket_manager import (
    broadcast_agent_status,
    broadcast_oem_risk_score,
    broadcast_suppliers_snapshot,
)
from app.orchestration.graphs.states import (
    RiskAnalysisState,
    RiskAnalysisSupplierResult,
    SupplierWorkflowContext,
)
from app.orchestration.graphs.supplier_risk_graph import (
    compute_score_from_dicts,
    score_to_level,
)

logger = logging.getLogger(__name__)

# Severity ordering for ranking top risks.
_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_VALID_SEVERITIES = frozenset(_SEV_ORDER)
_VALID_SOURCE_TYPES = frozenset({"news", "weather", "shipping", "traffic", "global_news"})
_VALID_OPP_TYPES = frozenset({
    "cost_saving", "time_saving", "quality_improvement",
    "market_expansion", "supplier_diversification",
})


# -- Risk / opportunity normalisation ----------------------------------------

def _normalize_risk(risk: dict, default_source: str = "unknown") -> dict | None:
    """
    Validate and normalise a risk dict before DB persistence.

    Ensures every risk has the required fields (title, description,
    sourceType) and that severity is a recognised value.  Returns
    ``None`` when the dict is irrecoverably malformed so the caller
    can silently skip it.
    """
    if not isinstance(risk, dict):
        return None

    title = (str(risk.get("title") or "")).strip()
    description = (str(risk.get("description") or "")).strip()
    if not title or not description:
        logger.debug("_normalize_risk: dropping risk with empty title/description")
        return None

    risk["title"] = title
    risk["description"] = description

    # Severity — lowercase + fallback
    raw_sev = (str(risk.get("severity") or "medium")).strip().lower()
    risk["severity"] = raw_sev if raw_sev in _VALID_SEVERITIES else "medium"

    # sourceType — must be a recognised domain for scoring
    raw_src = (str(risk.get("sourceType") or default_source)).strip().lower()
    risk["sourceType"] = raw_src if raw_src in _VALID_SOURCE_TYPES else default_source

    # sourceData — must be a dict (or None)
    if risk.get("sourceData") is not None and not isinstance(risk["sourceData"], dict):
        risk["sourceData"] = None

    # Numeric fields — coerce or clear
    for numeric_key in ("estimatedCost",):
        val = risk.get(numeric_key)
        if val is not None:
            try:
                risk[numeric_key] = float(val)
            except (TypeError, ValueError):
                risk[numeric_key] = None

    # String fields — coerce
    for str_key in ("affectedRegion", "affectedSupplier", "estimatedImpact"):
        val = risk.get(str_key)
        if val is not None:
            risk[str_key] = str(val).strip() or None

    return risk


def _normalize_opportunity(opp: dict, default_source: str = "unknown") -> dict | None:
    """
    Validate and normalise an opportunity dict before DB persistence.

    Returns ``None`` when the dict is irrecoverably malformed.
    """
    if not isinstance(opp, dict):
        return None

    title = (str(opp.get("title") or "")).strip()
    description = (str(opp.get("description") or "")).strip()
    if not title or not description:
        logger.debug("_normalize_opportunity: dropping opp with empty title/description")
        return None

    opp["title"] = title
    opp["description"] = description

    # type — must be a recognised opportunity type
    raw_type = (str(opp.get("type") or "cost_saving")).strip().lower()
    opp["type"] = raw_type if raw_type in _VALID_OPP_TYPES else "cost_saving"

    # sourceType
    raw_src = (str(opp.get("sourceType") or default_source)).strip().lower()
    opp["sourceType"] = raw_src if raw_src in _VALID_SOURCE_TYPES else default_source

    # sourceData — must be a dict (or None)
    if opp.get("sourceData") is not None and not isinstance(opp["sourceData"], dict):
        opp["sourceData"] = None

    # Numeric fields
    for numeric_key in ("estimatedValue",):
        val = opp.get(numeric_key)
        if val is not None:
            try:
                opp[numeric_key] = float(val)
            except (TypeError, ValueError):
                opp[numeric_key] = None

    # String fields
    for str_key in ("affectedRegion", "potentialBenefit"):
        val = opp.get(str_key)
        if val is not None:
            opp[str_key] = str(val).strip() or None

    return opp


# -- LLM risk scoring ---------------------------------------------------------

_RISK_SCORE_PROMPT = ChatPromptTemplate.from_template(
    """You are a supply chain risk analyst. Given the following list of detected
risks for a supplier, provide an aggregated risk score from 0 to 100
(decimals allowed). A score of 0 means no risk at all, and 100 means
extremely critical risk requiring immediate action.

Consider the following when scoring:
- Number of risks detected
- Severity distribution (critical, high, medium, low)
- Types of risks (factory shutdown, bankruptcy, sanctions are more severe)
- Geographic concentration of risks
- Potential cascading effects

Supplier: {supplier_name}
OEM: {oem_name}

Detected risks:
{risks_json}

Respond ONLY with a JSON object in this exact format, no other text:
{{"score": <number between 0 and 100>, "reasoning": "<a concise 2-4 sentence summary explaining the key risk drivers, their potential impact on the supply chain, and why this score was assigned>"}}"""
)


def _extract_score_json(text: str) -> dict | None:
    """Extract a JSON object from LLM response text."""
    if not text:
        return None
    cleaned = re.sub(r"```[a-zA-Z]*", "", text)
    cleaned = cleaned.replace("```", "")
    m = re.search(r"\{[\s\S]*\}", cleaned)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


async def _llm_risk_score(
    risks: list[dict],
    supplier_name: str,
    oem_name: str,
) -> tuple[float, str]:
    """
    Call the LLM to produce an aggregated risk score for a supplier.

    Returns ``(score, reasoning)``. Falls back to ``compute_score_from_dicts``
    if the LLM is unavailable or its response cannot be parsed.
    """
    llm = get_chat_model()
    if llm is None or not risks:
        fallback_score, _, _ = compute_score_from_dicts(risks)
        return fallback_score, "LLM unavailable — used algorithmic fallback"

    # Prepare a concise summary for the prompt (top 15 risks by severity).
    sorted_risks = sorted(
        risks,
        key=lambda r: _SEV_ORDER.get((r.get("severity") or "medium").lower(), 99),
    )
    risk_summaries = []
    for r in sorted_risks[:15]:
        risk_summaries.append({
            "title": r.get("title", ""),
            "description": r.get("description", ""),
            "severity": r.get("severity", "medium"),
            "affectedRegion": r.get("affectedRegion", ""),
            "sourceType": r.get("sourceType", ""),
            "risk_type": (r.get("sourceData") or {}).get("risk_type", ""),
        })

    risks_json = json.dumps(risk_summaries, indent=2)
    prompt_text = _RISK_SCORE_PROMPT.format(
        supplier_name=supplier_name,
        oem_name=oem_name,
        risks_json=risks_json,
    )

    provider = getattr(llm, "model_provider", None) or type(llm).__name__
    model_name = getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")
    call_id = _uuid.uuid4().hex[:8]
    start = time.perf_counter()

    try:
        chain = _RISK_SCORE_PROMPT | llm
        msg = await chain.ainvoke({
            "supplier_name": supplier_name,
            "oem_name": oem_name,
            "risks_json": risks_json,
        })

        elapsed = int((time.perf_counter() - start) * 1000)
        content = msg.content
        if isinstance(content, str):
            raw_text = content
        else:
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    parts.append(str(block.get("text") or ""))
                else:
                    parts.append(str(block))
            raw_text = "".join(parts)

        logger.info(
            "[RiskScore] LLM response id=%s provider=%s elapsed_ms=%d len=%d",
            call_id, provider, elapsed, len(raw_text),
        )
        _persist_llm_log(
            call_id, provider, str(model_name),
            str(prompt_text), raw_text, "success", elapsed, None,
        )

        parsed = _extract_score_json(raw_text)
        if parsed and "score" in parsed:
            score = float(parsed["score"])
            score = max(0.0, min(100.0, score))
            reasoning = parsed.get("reasoning", "")
            return round(score, 2), reasoning

        # Could not parse — fall back
        logger.warning(
            "[RiskScore] Could not parse LLM score response, using fallback. raw=%s",
            raw_text[:200],
        )
        fallback_score, _, _ = compute_score_from_dicts(risks)
        return fallback_score, "LLM response unparseable — used algorithmic fallback"

    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.exception("[RiskScore] LLM error: %s", exc)
        _persist_llm_log(
            call_id, provider, str(model_name),
            str(prompt_text), None, "error", elapsed, str(exc),
        )
        fallback_score, _, _ = compute_score_from_dicts(risks)
        return fallback_score, f"LLM error — used algorithmic fallback: {exc}"


# -- LLM OEM risk summary ------------------------------------------------------

_OEM_SUMMARY_PROMPT = ChatPromptTemplate.from_template(
    """You are a supply chain risk analyst. Given the following aggregated risk data
for an OEM's entire supply chain, write a concise executive summary (3-5 sentences)
that a supply chain manager can quickly read on a dashboard.

Overall risk score: {overall_score}/100
Risk level: {risk_level}

Severity breakdown:
{severity_counts_json}

Domain breakdown (per-domain weighted contributions):
{breakdown_json}

Top risks (by severity):
{top_risks_json}

Write a plain-text summary (NO JSON, NO markdown) that:
1. States the overall risk posture in one sentence.
2. Highlights the top 2-3 risk drivers and their potential impact.
3. Notes which domain (weather, shipping, news) contributes most to the risk.
4. Ends with a brief recommended focus area.

Keep it under 400 characters. Be specific — reference actual risk titles and regions when available."""
)


async def _generate_oem_summary(
    overall: float,
    risk_level: str,
    breakdown: dict,
    severity_counts: dict,
    risk_rows: list,
) -> str:
    """Generate a concise LLM summary for the OEM-level risk score."""
    llm = get_chat_model()
    if llm is None or not risk_rows:
        return _fallback_oem_summary(overall, risk_level, severity_counts, breakdown)

    top_risks = sorted(
        risk_rows,
        key=lambda r: _SEV_ORDER.get(
            getattr(r.severity, "value", r.severity), 99
        ),
    )[:10]
    top_risks_json = json.dumps(
        [
            {
                "title": getattr(r, "title", ""),
                "severity": getattr(r.severity, "value", r.severity),
                "affectedRegion": getattr(r, "affectedRegion", ""),
                "sourceType": r.sourceType,
            }
            for r in top_risks
        ],
        indent=2,
    )

    invoke_params = {
        "overall_score": round(overall, 1),
        "risk_level": risk_level,
        "severity_counts_json": json.dumps(severity_counts, indent=2),
        "breakdown_json": json.dumps(breakdown, indent=2),
        "top_risks_json": top_risks_json,
    }

    provider = getattr(llm, "model_provider", None) or type(llm).__name__
    model_name = getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")
    call_id = _uuid.uuid4().hex[:8]
    start = time.perf_counter()
    prompt_text = _OEM_SUMMARY_PROMPT.format(**invoke_params)

    try:
        chain = _OEM_SUMMARY_PROMPT | llm
        msg = await chain.ainvoke(invoke_params)

        elapsed = int((time.perf_counter() - start) * 1000)
        content = msg.content
        if isinstance(content, str):
            raw_text = content
        else:
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    parts.append(str(block.get("text") or ""))
                else:
                    parts.append(str(block))
            raw_text = "".join(parts)

        logger.info(
            "[OEMSummary] LLM response id=%s provider=%s elapsed_ms=%d len=%d",
            call_id, provider, elapsed, len(raw_text),
        )
        _persist_llm_log(
            call_id, provider, str(model_name),
            str(prompt_text), raw_text, "success", elapsed, None,
        )

        summary = raw_text.strip()
        if summary:
            return summary

    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.exception("[OEMSummary] LLM error: %s", exc)
        _persist_llm_log(
            call_id, provider, str(model_name),
            str(prompt_text), None, "error", elapsed, str(exc),
        )

    return _fallback_oem_summary(overall, risk_level, severity_counts, breakdown)


def _fallback_oem_summary(
    overall: float,
    risk_level: str,
    severity_counts: dict,
    breakdown: dict,
) -> str:
    """Rule-based fallback summary when LLM is unavailable."""
    critical = severity_counts.get("critical", 0)
    high = severity_counts.get("high", 0)
    medium = severity_counts.get("medium", 0)
    low = severity_counts.get("low", 0)
    total = critical + high + medium + low

    top_domain = max(breakdown, key=lambda k: breakdown.get(k, 0)) if breakdown else "unknown"

    parts = [f"Overall risk is {risk_level} with a score of {overall:.1f}/100."]
    if total:
        parts.append(
            f"{total} risks detected: {critical} critical, {high} high, "
            f"{medium} medium, {low} low."
        )
    if top_domain != "unknown":
        parts.append(f"Primary risk driver: {top_domain} domain.")

    return " ".join(parts)


# -- LLM swarm analysis --------------------------------------------------------

_SWARM_ANALYSIS_PROMPT = ChatPromptTemplate.from_template(
    """You are a supply chain risk analyst performing a multi-agent swarm analysis.
You have access to risks detected by three domain agents: WEATHER, SHIPPING, and NEWS.
For each agent, evaluate the risks and produce a structured analysis.

Supplier: {supplier_name}
OEM: {oem_name}
Overall risk score (already computed): {risk_score}
Overall risk level: {risk_level}

=== WEATHER RISKS ===
{weather_risks_json}

=== SHIPPING RISKS ===
{shipping_risks_json}

=== NEWS RISKS ===
{news_risks_json}

Analyze all risks above and produce a JSON object with this EXACT structure:

{{
  "finalScore": <number 0-100, should closely align with the overall risk score {risk_score}>,
  "riskLevel": "<LOW|MEDIUM|HIGH|CRITICAL>",
  "topDrivers": ["<top risk driver 1>", "<top risk driver 2>", "<top risk driver 3>"],
  "mitigationPlan": [
    "<specific, actionable mitigation step tailored to the detected risks>"
  ],
  "agents": [
    {{
      "agentType": "WEATHER",
      "score": <0-100 score based on weather risks>,
      "riskLevel": "<LOW|MEDIUM|HIGH|CRITICAL>",
      "signals": ["<risk title 1>", "<risk title 2>"],
      "interpretedRisks": ["<1-2 sentence interpretation of each key weather risk>"],
      "confidence": <0.0-1.0, higher with more corroborating data>,
      "metadata": {{"severityCounts": {{"low": 0, "medium": 0, "high": 0, "critical": 0}}, "riskCount": <number>}}
    }},
    {{
      "agentType": "SHIPPING",
      "score": <0-100>,
      "riskLevel": "<LOW|MEDIUM|HIGH|CRITICAL>",
      "signals": [],
      "interpretedRisks": [],
      "confidence": <0.0-1.0>,
      "metadata": {{"severityCounts": {{}}, "riskCount": 0}}
    }},
    {{
      "agentType": "NEWS",
      "score": <0-100>,
      "riskLevel": "<LOW|MEDIUM|HIGH|CRITICAL>",
      "signals": [],
      "interpretedRisks": [],
      "confidence": <0.0-1.0>,
      "metadata": {{"severityCounts": {{}}, "riskCount": 0}}
    }}
  ]
}}

Rules:
- topDrivers: Pick the 3 most impactful risk titles across all agents, ordered by severity.
- mitigationPlan: Generate 3-6 specific, actionable mitigation steps tailored to the detected risks. Reference specific risk types, regions, or suppliers. Do NOT use generic boilerplate.
- Per-agent scores: If an agent has zero risks, set score=0, riskLevel=LOW, confidence=0.
- Confidence: More risks with consistent signals = higher confidence. Single risk ~0.5, three+ consistent risks 0.7-0.9.
- The finalScore should closely match the pre-computed score of {risk_score}.

Respond ONLY with the JSON object, no other text."""
)


async def _llm_swarm_analysis(
    risk_dicts: list[dict],
    supplier_name: str,
    oem_name: str,
    risk_score: float,
    risk_level: str,
) -> tuple[dict, str] | None:
    """
    Call the LLM to produce a full swarm analysis breakdown.

    Returns ``(swarm_dict, raw_response)`` or ``None`` if the LLM is
    unavailable or the response cannot be parsed.
    """
    llm = get_chat_model()
    if llm is None:
        return None

    weather_risks = [r for r in risk_dicts if r.get("sourceType") == "weather"]
    shipping_risks = [
        r for r in risk_dicts if r.get("sourceType") in ("traffic", "shipping")
    ]
    news_risks = [
        r for r in risk_dicts if r.get("sourceType") in ("news", "global_news")
    ]

    def _summarize(risks: list[dict], limit: int = 10) -> str:
        if not risks:
            return "(none)"
        summaries = []
        for r in risks[:limit]:
            summaries.append({
                "title": r.get("title", ""),
                "description": r.get("description", ""),
                "severity": r.get("severity", "medium"),
                "affectedRegion": r.get("affectedRegion", ""),
            })
        return json.dumps(summaries, indent=2)

    invoke_params = {
        "supplier_name": supplier_name,
        "oem_name": oem_name,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "weather_risks_json": _summarize(weather_risks),
        "shipping_risks_json": _summarize(shipping_risks),
        "news_risks_json": _summarize(news_risks),
    }

    provider = getattr(llm, "model_provider", None) or type(llm).__name__
    model_name = getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")
    call_id = _uuid.uuid4().hex[:8]
    start = time.perf_counter()

    prompt_text = _SWARM_ANALYSIS_PROMPT.format(**invoke_params)

    try:
        chain = _SWARM_ANALYSIS_PROMPT | llm
        msg = await chain.ainvoke(invoke_params)

        elapsed = int((time.perf_counter() - start) * 1000)
        content = msg.content
        if isinstance(content, str):
            raw_text = content
        else:
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    parts.append(str(block.get("text") or ""))
                else:
                    parts.append(str(block))
            raw_text = "".join(parts)

        logger.info(
            "[SwarmAnalysis] LLM response id=%s provider=%s elapsed_ms=%d len=%d",
            call_id, provider, elapsed, len(raw_text),
        )
        _persist_llm_log(
            call_id, provider, str(model_name),
            str(prompt_text), raw_text, "success", elapsed, None,
        )

        parsed = _extract_score_json(raw_text)
        if parsed and "agents" in parsed and "finalScore" in parsed:
            parsed["finalScore"] = max(0.0, min(100.0, float(parsed["finalScore"])))
            parsed["riskLevel"] = parsed.get("riskLevel", risk_level)
            parsed["topDrivers"] = parsed.get("topDrivers", [])[:5]
            parsed["mitigationPlan"] = parsed.get("mitigationPlan", [])[:8]
            for agent in parsed.get("agents", []):
                agent["score"] = max(0.0, min(100.0, float(agent.get("score", 0))))
                agent["confidence"] = max(
                    0.0, min(1.0, float(agent.get("confidence", 0.5)))
                )
            return parsed, raw_text

        logger.warning(
            "[SwarmAnalysis] Unparseable LLM response, raw=%s", raw_text[:200],
        )
        return None

    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.exception("[SwarmAnalysis] LLM error: %s", exc)
        _persist_llm_log(
            call_id, provider, str(model_name),
            str(prompt_text), None, "error", elapsed, str(exc),
        )
        return None


# -- Status / broadcast helpers ------------------------------------------------

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


async def _broadcast_status(
    db: Session,
    agent_status_id: UUID,
    supplier_name: str | None = None,
    oem_name: str | None = None,
) -> None:
    ent = (
        db.query(AgentStatusEntity)
        .filter(AgentStatusEntity.id == agent_status_id)
        .first()
    )
    if not ent:
        return
    payload: dict = {
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
    if supplier_name:
        payload["supplierName"] = supplier_name
    if oem_name:
        payload["oemName"] = oem_name
    await broadcast_agent_status(payload)


async def _broadcast_suppliers(db: Session, oem_id: UUID) -> None:
    from app.services.suppliers import get_latest_risk_analysis_by_supplier

    suppliers = get_suppliers(db, oem_id)
    if not suppliers:
        return
    risk_map = get_risks_by_supplier(db)
    reasoning_map = get_latest_risk_analysis_by_supplier(db, oem_id)
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
            "aiReasoning": reasoning_map.get(s.id),
            "swarm": swarm_map.get(s.id),
        }
        for s in suppliers
    ]
    await broadcast_suppliers_snapshot(str(oem_id), payload)


# -- Graph nodes ---------------------------------------------------------------

async def _process_next_supplier(
    state: RiskAnalysisState,
    config: RunnableConfig,
) -> RiskAnalysisState:
    """
    Pop one SupplierWorkflowContext, run risk analysis for that supplier,
    persist results, and compute per-supplier risk score.

    Steps per supplier
    ------------------
    1. Run news agent (supplier + global context) and shipment weather
       agent in parallel.
    2. Persist risk and opportunity rows to the DB (linked to supplier).
    3. Query persisted risks, sort by severity, take top 10.
    4. Compute unified score and update Supplier.latestRiskScore.
    5. Create a SupplierRiskAnalysis row.
    6. Update AgentStatusEntity counters.
    7. Broadcast partial supplier snapshot over WebSocket.
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
    supplier_name = scope.get("supplierName") or None
    oem_name = scope.get("oemName") or None
    label = supplier_name or oem_name or "unknown"

    logger.info("RiskAnalysisGraph: starting supplier '%s'", label)

    # -- 1. Run news + shipment weather agents in parallel --------------------
    _update_status(
        db, agent_status_id,
        AgentStatus.ANALYZING.value,
        f"Running risk analysis for supplier: {label}",
    )
    await _broadcast_status(db, agent_status_id, supplier_name=supplier_name, oem_name=oem_name)

    supplier_result, global_result, weather_result, shipping_result = await asyncio.gather(
        run_news_agent_graph({}, scope, context="supplier"),
        run_news_agent_graph({}, scope, context="global"),
        run_weather_graph(scope),
        run_shipment_risk_graph(scope),
    )

    logger.info(
        "RiskAnalysisGraph: supplier '%s' — weather agent returned risks=%d opps=%d",
        label,
        len(weather_result.get("risks") or []),
        len(weather_result.get("opportunities") or []),
    )
    logger.info(
        "RiskAnalysisGraph: supplier '%s' — shipment agent returned risks=%d",
        label,
        len(shipping_result.get("risks") or []),
    )

    raw_risks = (
        (supplier_result.get("risks") or [])
        + (global_result.get("risks") or [])
        + (weather_result.get("risks") or [])
        + (shipping_result.get("risks") or [])
    )
    raw_opps = (
        (supplier_result.get("opportunities") or [])
        + (weather_result.get("opportunities") or [])
    )

    # -- 1b. Normalise all risk / opportunity dicts across sources ----------
    all_risks: list[dict] = []
    for r in raw_risks:
        normed = _normalize_risk(r, default_source="news")
        if normed is not None:
            all_risks.append(normed)

    all_opps: list[dict] = []
    for o in raw_opps:
        normed = _normalize_opportunity(o, default_source="news")
        if normed is not None:
            all_opps.append(normed)

    dropped_risks = len(raw_risks) - len(all_risks)
    dropped_opps = len(raw_opps) - len(all_opps)
    if dropped_risks or dropped_opps:
        logger.warning(
            "RiskAnalysisGraph: supplier '%s' — dropped %d malformed risks, %d malformed opps during normalisation",
            label, dropped_risks, dropped_opps,
        )

    logger.info(
        "RiskAnalysisGraph: supplier '%s' -- risks=%d opportunities=%d (after normalisation)",
        label, len(all_risks), len(all_opps),
    )

    # -- 2. Persist to DB ------------------------------------------------------
    _update_status(
        db, agent_status_id,
        AgentStatus.PROCESSING.value,
        f"Saving results for supplier: {label}",
    )
    await _broadcast_status(db, agent_status_id, supplier_name=supplier_name, oem_name=oem_name)

    for r in all_risks:
        r["oemId"] = oem_id
        if supplier_id_uuid is not None:
            r["supplierId"] = supplier_id_uuid
        # Ensure affectedSupplier is always set when we know the supplier name
        if supplier_name and not r.get("affectedSupplier"):
            r["affectedSupplier"] = supplier_name
            r["supplierName"] = supplier_name
        create_risk_from_dict(
            db, r,
            agent_status_id=agent_status_id,
            workflow_run_id=workflow_run_id,
        )

    for o in all_opps:
        o["oemId"] = oem_id
        if supplier_id_uuid is not None:
            o["supplierId"] = supplier_id_uuid
        create_opportunity_from_dict(
            db, o,
            agent_status_id=agent_status_id,
            workflow_run_id=workflow_run_id,
        )

    # -- 3. Compute top risks for this supplier --------------------------------
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

    supplier_risk_rows.sort(
        key=lambda r: (
            _SEV_ORDER.get(
                getattr(r.severity, "value", r.severity), 99
            ),
            r.createdAt or datetime.min,
        )
    )
    top_risks = supplier_risk_rows[:10]

    # -- 4. Compute unified score via LLM -------------------------------------
    risk_dicts = [
        {
            "title": getattr(r, "title", ""),
            "description": getattr(r, "description", ""),
            "severity": getattr(r.severity, "value", r.severity),
            "affectedRegion": getattr(r, "affectedRegion", ""),
            "sourceType": r.sourceType,
            "sourceData": r.sourceData,
        }
        for r in supplier_risk_rows
    ]

    _update_status(
        db, agent_status_id,
        AgentStatus.ANALYZING.value,
        f"Computing LLM risk score for supplier: {label}",
    )
    await _broadcast_status(db, agent_status_id, supplier_name=supplier_name, oem_name=oem_name)

    unified_score, llm_reasoning = await _llm_risk_score(
        risk_dicts, label, oem_name or "",
    )
    risk_level = score_to_level(unified_score)

    # Also compute algorithmic breakdown for metadata
    algo_risk_dicts = [
        {
            "severity": getattr(r.severity, "value", r.severity),
            "sourceType": r.sourceType,
            "sourceData": r.sourceData,
        }
        for r in supplier_risk_rows
    ]
    _, domain_scores, severity_counts = compute_score_from_dicts(algo_risk_dicts)

    logger.info(
        "RiskAnalysisGraph: supplier '%s' — LLM score=%.2f level=%s reasoning=%s",
        label, unified_score, risk_level, llm_reasoning[:100],
    )

    # -- 5. Update Supplier.latestRiskScore + SupplierRiskAnalysis -------------
    if supplier_id_uuid:
        for supplier in get_suppliers(db, oem_id):
            if supplier.id != supplier_id_uuid:
                continue
            supplier.latestRiskScore = unified_score
            supplier.latestRiskLevel = risk_level
            db.commit()

            sra = SupplierRiskAnalysis(
                oemId=oem_id,
                workflowRunId=workflow_run_id,
                supplierId=supplier_id_uuid,
                riskScore=unified_score,
                risks=[str(r.id) for r in top_risks],
                description=llm_reasoning or (
                    f"Risk score for {label} "
                    f"— top {len(top_risks)} risks"
                ),
                metadata_={
                    "severityCounts": severity_counts,
                    "domainScores": domain_scores,
                    "topRiskIds": [str(r.id) for r in top_risks],
                    "llmReasoning": llm_reasoning,
                    "scoringMethod": "llm",
                },
            )
            db.add(sra)
            db.commit()

            # -- 5b. LLM-based swarm analysis ---------------------------------
            _update_status(
                db, agent_status_id,
                AgentStatus.ANALYZING.value,
                f"Running swarm analysis for supplier: {label}",
            )
            await _broadcast_status(
                db, agent_status_id,
                supplier_name=supplier_name, oem_name=oem_name,
            )

            swarm_result = await _llm_swarm_analysis(
                risk_dicts, label, oem_name or "",
                unified_score, risk_level,
            )

            from app.models.swarm_analysis import SwarmAnalysis

            if swarm_result is not None:
                swarm_data, raw_response = swarm_result
                db.add(SwarmAnalysis(
                    supplierRiskAnalysisId=sra.id,
                    supplierId=supplier_id_uuid,
                    oemId=oem_id,
                    workflowRunId=workflow_run_id,
                    finalScore=swarm_data["finalScore"],
                    riskLevel=swarm_data["riskLevel"],
                    topDrivers=swarm_data["topDrivers"],
                    mitigationPlan=swarm_data["mitigationPlan"],
                    agents=swarm_data["agents"],
                    llmRawResponse=raw_response,
                    metadata_={"scoringMethod": "llm"},
                ))
                db.commit()
            else:
                # Fallback: persist rule-based swarm analysis
                from app.services.suppliers import (
                    _build_swarm_summary_for_supplier,
                )
                fallback = _build_swarm_summary_for_supplier(
                    supplier_risk_rows,
                )
                if fallback:
                    db.add(SwarmAnalysis(
                        supplierRiskAnalysisId=sra.id,
                        supplierId=supplier_id_uuid,
                        oemId=oem_id,
                        workflowRunId=workflow_run_id,
                        finalScore=fallback["finalScore"],
                        riskLevel=fallback["riskLevel"],
                        topDrivers=fallback["topDrivers"],
                        mitigationPlan=fallback["mitigationPlan"],
                        agents=fallback["agents"],
                        llmRawResponse=None,
                        metadata_={"scoringMethod": "rule_based_fallback"},
                    ))
                    db.commit()

            break

    # -- 6. Update AgentStatusEntity counters ----------------------------------
    ent = (
        db.query(AgentStatusEntity)
        .filter(AgentStatusEntity.id == agent_status_id)
        .first()
    )
    if ent:
        ent.risksDetected = len(supplier_risk_rows)
        ent.opportunitiesIdentified = (
            db.query(Opportunity)
            .filter(
                Opportunity.agentStatusId == agent_status_id,
                Opportunity.workflowRunId == workflow_run_id,
            )
            .count()
        )
        ent.lastProcessedData = {
            "timestamp": datetime.utcnow().isoformat(),
            "oemsProcessed": [scope.get("oemName", "")],
            "supplierId": scope.get("supplierId"),
            "supplierName": scope.get("supplierName"),
            "workflowRunId": str(workflow_run_id),
            "graphVersion": "v2",
            "riskScore": unified_score,
            "riskLevel": risk_level,
            "topRiskCount": len(top_risks),
        }
        db.commit()

    # -- 7. Partial WebSocket broadcast ----------------------------------------
    await _broadcast_suppliers(db, oem_id)

    result: RiskAnalysisSupplierResult = {
        "supplier_scope": scope,
        "all_risks": [
            {
                "severity": getattr(r.severity, "value", r.severity),
                "sourceType": r.sourceType,
                "sourceData": r.sourceData,
            }
            for r in supplier_risk_rows
        ],
        "all_opportunities": all_opps,
        "unified_score": unified_score,
        "risk_level": risk_level,
        "domain_scores": domain_scores,
        "top_risk_ids": [str(r.id) for r in top_risks],
    }

    logger.info(
        "RiskAnalysisGraph: supplier '%s' done — "
        "risks=%d score=%.2f level=%s top_risks=%d",
        label, len(supplier_risk_rows), unified_score, risk_level,
        len(top_risks),
    )

    return {
        "remaining_contexts": remaining,
        "processed_contexts": processed,
        "supplier_results": (state.get("supplier_results") or []) + [result],
    }


def _should_continue(state: RiskAnalysisState) -> str:
    """Loop back to process_next_supplier until no contexts remain."""
    if state.get("remaining_contexts"):
        return "process_next_supplier"
    return "aggregate_oem_score"


async def _aggregate_oem_score(
    state: RiskAnalysisState,
    config: RunnableConfig,
) -> RiskAnalysisState:
    """
    Query all detected risks for this OEM across all supplier runs, compute a
    single SupplyChainRiskScore row, and derive the OEM-level risk band.
    """
    db: Session = config["configurable"]["db"]
    oem_id = UUID(state["oem_id"])

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

    risk_dicts = [
        {
            "severity": getattr(r.severity, "value", r.severity),
            "sourceType": r.sourceType,
            "sourceData": r.sourceData,
        }
        for r in all_risks_orm
    ]
    overall, breakdown, severity_counts = compute_score_from_dicts(risk_dicts)
    oem_risk_level = score_to_level(overall)

    # Generate an executive summary for the OEM risk score
    summary = await _generate_oem_summary(
        overall, oem_risk_level, breakdown, severity_counts, all_risks_orm,
    )

    db.add(
        SupplyChainRiskScore(
            oemId=oem_id,
            workflowRunId=all_workflow_ids[0],
            overallScore=overall,
            breakdown=breakdown,
            severityCounts=severity_counts,
            riskIds=(
                ",".join(str(r.id) for r in all_risks_orm)
                if all_risks_orm
                else None
            ),
            summary=summary,
        )
    )
    db.commit()

    logger.info(
        "RiskAnalysisGraph: OEM %s — overall_score=%.2f level=%s risks=%d summary=%s",
        state["oem_id"], overall, oem_risk_level, len(all_risks_orm),
        (summary or "")[:80],
    )

    return {
        "oem_risk_score": overall,
        "oem_risk_level": oem_risk_level,
        "oem_risk_summary": summary,
    }


async def _broadcast_complete(
    state: RiskAnalysisState,
    config: RunnableConfig,
) -> RiskAnalysisState:
    """Mark every supplier's AgentStatus as COMPLETED and broadcast the final snapshot."""
    db: Session = config["configurable"]["db"]
    oem_id = UUID(state["oem_id"])

    # Batch-update all supplier statuses to COMPLETED in DB (no per-supplier broadcast)
    for ctx in state.get("processed_contexts") or []:
        _update_status(
            db,
            UUID(ctx["agent_status_id"]),
            AgentStatus.COMPLETED.value,
            "Risk analysis completed",
        )

    # Single broadcast: final suppliers snapshot
    await _broadcast_suppliers(db, oem_id)

    # Single broadcast: OEM-level risk score with summary
    latest = (
        db.query(SupplyChainRiskScore)
        .filter(SupplyChainRiskScore.oemId == oem_id)
        .order_by(SupplyChainRiskScore.createdAt.desc())
        .first()
    )
    if latest:
        await broadcast_oem_risk_score(
            str(oem_id),
            {
                "id": str(latest.id),
                "oemId": str(latest.oemId),
                "overallScore": float(latest.overallScore),
                "breakdown": latest.breakdown,
                "severityCounts": latest.severityCounts,
                "summary": latest.summary,
                "createdAt": latest.createdAt.isoformat() if latest.createdAt else None,
            },
        )

    # Single broadcast: final completed agent status (use the last supplier's context)
    contexts = state.get("processed_contexts") or []
    if contexts:
        last_ctx = contexts[-1]
        scope: OemScope = last_ctx["scope"]
        await _broadcast_status(
            db, UUID(last_ctx["agent_status_id"]),
            supplier_name=scope.get("supplierName"),
            oem_name=scope.get("oemName"),
        )

    return {}


# -- Graph compilation ---------------------------------------------------------

_builder = StateGraph(RiskAnalysisState)
_builder.add_node("process_next_supplier", _process_next_supplier)
_builder.add_node("aggregate_oem_score", _aggregate_oem_score)
_builder.add_node("broadcast_complete", _broadcast_complete)

_builder.set_entry_point("process_next_supplier")
_builder.add_conditional_edges(
    "process_next_supplier",
    _should_continue,
    {
        "process_next_supplier": "process_next_supplier",
        "aggregate_oem_score": "aggregate_oem_score",
    },
)
_builder.add_edge("aggregate_oem_score", "broadcast_complete")
_builder.add_edge("broadcast_complete", END)

RISK_ANALYSIS_GRAPH = _builder.compile()
