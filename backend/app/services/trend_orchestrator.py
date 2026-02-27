"""Trend-insights orchestration layer.

Workflow for a single run
--------------------------
1. Load suppliers / materials / global context from Excel.
2. Build per-level search queries from the Excel rows.
3. Fetch news/trend signals via TrendDataSource (NewsAPI or mock).
4. Construct a TrendContext with static + dynamic data.
5. Call the multi-provider LLM client to produce structured Insight objects.
6. Persist each Insight as a TrendInsight database row.
7. Return the list of saved rows.

Exposed functions
-----------------
run_trend_insights_cycle(db, *, oem_name, excel_path) -> list[TrendInsight]
    Synchronous wrapper (runs asyncio internally) - safe for APScheduler.

run_trend_insights_cycle_async(db, *, oem_name, excel_path) -> list[TrendInsight]
    Async version - call from FastAPI route handlers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.config import settings
from app.models.trend_insight import TrendInsight
from app.data.excel import load_all_from_excel, DEFAULT_EXCEL_PATH
from app.data.trends import TrendDataSource
from app.services.llm_client import TrendContext, TrendItem, get_llm_client, Insight

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_DEFAULT_OEM_NAME = "Demo Manufacturer"


# ── Query builders ────────────────────────────────────────────────────


def _material_queries(materials: list[dict]) -> list[str]:
    queries = []
    for m in materials[:8]:
        name = (m.get("material_name") or "").strip()
        if name:
            queries.append(f"{name} supply chain price trends 2025")
            queries.append(f"{name} shortage disruption")
    return list(dict.fromkeys(queries))[:12]


def _supplier_queries(suppliers: list[dict]) -> list[str]:
    queries = []
    for s in suppliers[:8]:
        name = (s.get("name") or "").strip()
        region = (s.get("region") or s.get("country") or "").strip()
        if name:
            queries.append(f"{name} supply chain disruption")
        if region:
            queries.append(f"{region} manufacturing logistics risk")
    return list(dict.fromkeys(queries))[:12]


def _global_queries(global_ctx: list[dict]) -> list[str]:
    base = [
        "global supply chain disruption 2025",
        "trade tariff geopolitical risk manufacturing",
        "shipping freight rates Red Sea 2025",
    ]
    for g in global_ctx[:5]:
        trend = (g.get("macro_trend") or "").strip()
        if trend:
            base.append(trend[:80])
    return list(dict.fromkeys(base))[:10]


# ── Trend item normaliser (DataSourceResult → TrendItem) ──────────────


def _to_trend_item(result_dict: dict) -> TrendItem | None:
    data = result_dict.get("data") or {}
    if not data:
        return None
    return TrendItem(
        title=data.get("title") or "",
        summary=data.get("summary") or data.get("description") or "",
        source=data.get("source") or "Unknown",
        published_at=data.get("published_at") or result_dict.get("timestamp") or "",
        level=data.get("level") or "global",
        query=data.get("query") or "",
        url=data.get("url"),
        relevance_score=float(data.get("relevance_score") or 0.7),
    )


# ── Async core ────────────────────────────────────────────────────────


async def run_trend_insights_cycle_async(
    db: Session,
    *,
    oem_name: str | None = None,
    excel_path: str | None = None,
) -> list[TrendInsight]:
    oem_name = oem_name or _DEFAULT_OEM_NAME
    excel_path = excel_path or settings.trend_agent_excel_path or DEFAULT_EXCEL_PATH

    logger.info("Trend insights cycle starting - oem=%s excel=%s", oem_name, excel_path)

    # 1. Load Excel data
    excel_data = load_all_from_excel(excel_path)
    suppliers = excel_data["suppliers"]
    materials = excel_data["materials"]
    global_ctx = excel_data["global"]

    if not suppliers and not materials:
        logger.warning("No data loaded from Excel - aborting trend cycle.")
        return []

    # 2. Build queries
    mat_queries = _material_queries(materials)
    sup_queries = _supplier_queries(suppliers)
    glb_queries = _global_queries(global_ctx)

    logger.info(
        "Querying trends: %d material, %d supplier, %d global queries",
        len(mat_queries),
        len(sup_queries),
        len(glb_queries),
    )

    # 3. Fetch trend data
    trend_source = TrendDataSource()
    await trend_source.initialize({})
    raw_results = await trend_source.fetch_data(
        {
            "material_queries": mat_queries,
            "supplier_queries": sup_queries,
            "global_queries": glb_queries,
        }
    )

    trend_items: list[TrendItem] = []
    for result in raw_results:
        item = _to_trend_item(
            result.to_dict() if hasattr(result, "to_dict") else result
        )
        if item and item.title:
            trend_items.append(item)

    logger.info("Fetched %d trend items", len(trend_items))

    # 4. Build TrendContext
    ctx = TrendContext(
        oem_name=oem_name,
        excel_path=excel_path,
        suppliers=suppliers,
        materials=materials,
        global_context=global_ctx,
        trend_items=trend_items,
    )

    # 5. Call LLM
    client = get_llm_client()
    logger.info("Generating insights via provider: %s", client.provider)
    insights: list[Insight] = await client.generate_insights(ctx)

    if not insights:
        logger.warning("LLM returned no insights; using mock insights.")
        from app.services.llm_client import _mock_insights

        insights = _mock_insights(ctx)

    logger.info("Received %d insights from LLM", len(insights))

    # 6. Persist
    saved: list[TrendInsight] = []
    for ins in insights:
        row = TrendInsight(
            scope=ins.scope,
            entity_name=ins.entity_name,
            risk_opportunity=ins.risk_opportunity,
            title=ins.title,
            description=ins.description,
            predicted_impact=ins.predicted_impact,
            time_horizon=ins.time_horizon,
            severity=ins.severity,
            recommended_actions=ins.recommended_actions,
            source_articles=ins.source_articles,
            confidence=ins.confidence,
            oem_name=oem_name,
            excel_path=excel_path,
            llm_provider=client.provider,
        )
        db.add(row)
        saved.append(row)

    db.commit()
    for row in saved:
        db.refresh(row)

    logger.info("Trend insights cycle complete - saved %d insights.", len(saved))
    return saved


# ── Sync wrapper (for APScheduler) ───────────────────────────────────


def run_trend_insights_cycle(
    db: Session,
    *,
    oem_name: str | None = None,
    excel_path: str | None = None,
) -> list[TrendInsight]:
    """Synchronous entry point safe to call from APScheduler background threads."""
    try:
        return asyncio.run(
            run_trend_insights_cycle_async(db, oem_name=oem_name, excel_path=excel_path)
        )
    except Exception as exc:
        logger.exception("Trend insights cycle failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return []
