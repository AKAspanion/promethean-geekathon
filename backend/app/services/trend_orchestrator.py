"""Trend-insights orchestration layer.

Delegates all fetch + LLM work to the LangGraph agent in app.agents.trend.
This module is responsible for:
1. Loading supplier/material data from the database.
2. Calling run_trend_agent_graph() with the loaded context.
3. Persisting the returned insight dicts as TrendInsight database rows.

Exposed functions
-----------------
run_trend_insights_cycle(db, *, oem_name) -> list[TrendInsight]
    Synchronous wrapper (runs asyncio internally) - safe for APScheduler.

run_trend_insights_cycle_async(db, *, oem_name) -> list[TrendInsight]
    Async version - call from FastAPI route handlers.

run_trend_insights_for_supplier_async(db, *, supplier_id, oem_name) -> list[TrendInsight]
    Per-supplier variant triggered by UI click.
"""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy.orm import Session

from app.models.trend_insight import TrendInsight
from app.models.supplier import Supplier
from app.agents.trend import run_trend_agent_graph

logger = logging.getLogger(__name__)

_DEFAULT_OEM_NAME = "Demo Manufacturer"


def _to_str(value: object) -> str | None:
    """Coerce any scalar/dict/list the LLM returns into a plain string for Text columns."""
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        # e.g. {"lead_time": 12, "production_volume": 15}
        # → "lead_time: 12, production_volume: 15"
        return ", ".join(f"{k}: {v}" for k, v in value.items())
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _to_str_list(value: object) -> list[str]:
    """Coerce LLM output to a plain Python list[str] safe for JSONB insertion.

    The LLM may return:
      - A proper Python list[str]               → use as-is
      - A list that contains dicts              → stringify each dict
      - A JSON-encoded string ('[\"a\", \"b\"]') → parse then coerce
      - None / any other type                   → return []
    """
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return [value] if value.strip() else []
        value = parsed
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            # e.g. {"action": "...", "title": "..."} → pick a sensible key
            text = (
                item.get("action")
                or item.get("title")
                or item.get("text")
                or item.get("description")
                or str(item)
            )
            result.append(str(text))
        else:
            result.append(str(item))
    return result


# ── Async core ────────────────────────────────────────────────────────


def _supplier_row_to_dict(row: Supplier) -> dict:
    return {
        "name": row.name or "",
        "region": row.region or row.country or "",
        "country": row.country or "",
        "location": row.location or "",
        "commodities": row.commodities or "",
    }


def _materials_from_supplier(row: Supplier) -> list[dict]:
    if not row.commodities:
        return []
    return [
        {"material_name": c.strip()}
        for c in row.commodities.split(",")
        if c.strip()
    ]


def _load_suppliers_from_db(db: Session) -> tuple[list[dict], list[dict]]:
    """Query the suppliers table and return (suppliers, materials) as plain dicts.

    Materials are derived from the unique commodities listed across all suppliers.
    """
    rows = db.query(Supplier).all()
    suppliers: list[dict] = []
    commodity_set: set[str] = set()

    for row in rows:
        suppliers.append(_supplier_row_to_dict(row))
        if row.commodities:
            for raw in row.commodities.split(","):
                commodity = raw.strip()
                if commodity:
                    commodity_set.add(commodity)

    materials = [{"material_name": c} for c in sorted(commodity_set)]
    return suppliers, materials


async def run_trend_insights_cycle_async(
    db: Session,
    *,
    oem_name: str | None = None,
) -> list[TrendInsight]:
    oem_name = oem_name or _DEFAULT_OEM_NAME

    logger.info("Trend insights cycle starting - oem=%s", oem_name)

    # 1. Load suppliers and derive materials from the database
    suppliers, materials = _load_suppliers_from_db(db)

    if not suppliers and not materials:
        logger.warning("No supplier data found in database - aborting trend cycle.")
        return []

    # 2. Run the LangGraph trend agent (fetch + merge + LLM in one graph)
    logger.info("Running TrendGraph for oem=%s", oem_name)
    raw_insights = await run_trend_agent_graph(
        suppliers=suppliers,
        materials=materials,
        oem_name=oem_name,
    )
    logger.info("TrendGraph returned %d insights", len(raw_insights))

    # 3. Persist
    saved: list[TrendInsight] = []
    for ins in raw_insights:
        row = TrendInsight(
            scope=ins.get("scope", "global"),
            entity_name=ins.get("entity_name"),
            risk_opportunity=ins.get("risk_opportunity", "risk"),
            title=ins.get("title", "Untitled"),
            description=ins.get("description"),
            predicted_impact=_to_str(ins.get("predicted_impact")),
            time_horizon=ins.get("time_horizon"),
            severity=ins.get("severity"),
            recommended_actions=_to_str_list(ins.get("recommended_actions")),
            source_articles=_to_str_list(ins.get("source_articles")),
            confidence=float(ins.get("confidence") or 0.7),
            oem_name=oem_name,
            llm_provider="langgraph",
        )
        db.add(row)
        saved.append(row)

    db.commit()
    for row in saved:
        db.refresh(row)

    logger.info("Trend insights cycle complete - saved %d insights.", len(saved))
    return saved


async def run_trend_insights_for_supplier_async(
    db: Session,
    *,
    supplier_id: str,
    oem_name: str | None = None,
) -> list[TrendInsight]:
    """Run the trend-insights cycle scoped to a single supplier row."""
    from uuid import UUID

    oem_name = oem_name or _DEFAULT_OEM_NAME

    row = db.query(Supplier).filter(Supplier.id == UUID(supplier_id)).first()
    if not row:
        logger.warning("Supplier %s not found - aborting trend cycle.", supplier_id)
        return []

    suppliers = [_supplier_row_to_dict(row)]
    materials = _materials_from_supplier(row)

    logger.info(
        "Trend insights cycle starting - supplier=%s oem=%s",
        row.name,
        oem_name,
    )

    # Run the LangGraph trend agent scoped to this supplier
    logger.info("Running TrendGraph for supplier=%s oem=%s", row.name, oem_name)
    raw_insights = await run_trend_agent_graph(
        suppliers=suppliers,
        materials=materials,
        oem_name=oem_name,
    )
    logger.info("TrendGraph returned %d insights", len(raw_insights))

    saved: list[TrendInsight] = []
    for ins in raw_insights:
        db_row = TrendInsight(
            scope=ins.get("scope", "global"),
            entity_name=ins.get("entity_name"),
            risk_opportunity=ins.get("risk_opportunity", "risk"),
            title=ins.get("title", "Untitled"),
            description=ins.get("description"),
            predicted_impact=_to_str(ins.get("predicted_impact")),
            time_horizon=ins.get("time_horizon"),
            severity=ins.get("severity"),
            recommended_actions=_to_str_list(ins.get("recommended_actions")),
            source_articles=_to_str_list(ins.get("source_articles")),
            confidence=float(ins.get("confidence") or 0.7),
            oem_name=oem_name,
            llm_provider="langgraph",
        )
        db.add(db_row)
        saved.append(db_row)

    db.commit()
    for db_row in saved:
        db.refresh(db_row)

    logger.info(
        "Trend insights cycle complete for supplier %s - saved %d insights.",
        row.name,
        len(saved),
    )
    return saved


# ── Sync wrapper (for APScheduler) ───────────────────────────────────


def run_trend_insights_cycle(
    db: Session,
    *,
    oem_name: str | None = None,
) -> list[TrendInsight]:
    """Synchronous entry point safe to call from APScheduler background threads."""
    try:
        return asyncio.run(
            run_trend_insights_cycle_async(db, oem_name=oem_name)
        )
    except Exception as exc:
        logger.exception("Trend insights cycle failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return []
