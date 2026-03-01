import json
import logging
import re
import time
import uuid as _uuid
from datetime import datetime, timezone
from typing import TypedDict, Literal
from uuid import UUID

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END, START

from app.database import SessionLocal
from app.services.agent_orchestrator import _extract_json
from app.services.langchain_llm import get_chat_model
from app.services.llm_client import _persist_llm_log
from app.services.agent_types import OemScope
from app.services.oems import get_oem_by_id
from app.services.suppliers import get_by_id as get_supplier_by_id
from app.services.websocket_manager import manager as ws_manager
from app.data.news import NewsDataSource
from app.data.gdelt import GDELTDataSource

logger = logging.getLogger(__name__)


async def _broadcast_progress(
    step: str,
    message: str,
    context: str | None = None,
    details: dict | None = None,
    oem_name: str | None = None,
    supplier_name: str | None = None,
) -> None:
    """Broadcast a news agent progress event over websocket."""
    payload: dict = {
        "type": "news_agent_progress",
        "step": step,
        "message": message,
    }
    if context:
        payload["context"] = context
    if oem_name:
        payload["oemName"] = oem_name
    if supplier_name:
        payload["supplierName"] = supplier_name
    if details:
        payload["details"] = details
    await ws_manager.broadcast(payload)


class NewsItem(TypedDict):
    title: str | None
    description: str | None
    url: str | None
    source: str | None
    publishedAt: str | None
    author: str | None
    content: str | None


class EntityData(TypedDict, total=False):
    """Flat dict holding key attributes of an OEM or Supplier."""
    id: str
    name: str
    location: str | None
    city: str | None
    country: str | None
    countryCode: str | None
    region: str | None
    commodities: str | None


class NewsAgentState(TypedDict, total=False):
    scope: OemScope
    context: Literal["supplier", "global"]
    # OEM and supplier details fetched from DB
    oem_data: EntityData
    supplier_data: EntityData | None
    # Pre-fetched data passed from outside (backward compat)
    news_data: dict[str, list[dict]]
    # Per-source raw fetch results (populated by parallel fetch nodes)
    newsapi_raw: list[dict]
    gdelt_raw: list[dict]
    headlines_raw: list[dict]  # broad top-headlines filtered by supplier pool
    prefetched_broad_headlines: list[dict] | None  # optional; when set, skip fetch_broad_headlines API
    # Merged + normalised
    news_items: list[NewsItem]
    news_risks: list[dict]
    news_opportunities: list[dict]


# ---------------------------------------------------------------------------
# Helper to extract EntityData from a DB model
# ---------------------------------------------------------------------------

def _entity_from_model(obj) -> EntityData:
    """Build an EntityData dict from a SQLAlchemy OEM or Supplier model."""
    return EntityData(
        id=str(obj.id),
        name=getattr(obj, "name", "") or "",
        location=getattr(obj, "location", None),
        city=getattr(obj, "city", None),
        country=getattr(obj, "country", None),
        countryCode=getattr(obj, "countryCode", None),
        region=getattr(obj, "region", None),
        commodities=getattr(obj, "commodities", None),
    )


# ---------------------------------------------------------------------------
# Parse commodities string into a list
# ---------------------------------------------------------------------------

def _parse_commodities(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [c.strip() for c in raw.replace(";", ",").split(",") if c.strip()]


# ---------------------------------------------------------------------------
# Commodity → upstream raw-material mapping
# ---------------------------------------------------------------------------
# Maps finished/processed commodities to their upstream dependencies so that
# geopolitical events affecting raw materials (e.g. oil/petroleum) are
# surfaced for suppliers that depend on derived products (e.g. plastics).

_COMMODITY_UPSTREAM_MAP: dict[str, list[str]] = {
    # Plastics & polymers ← petroleum / oil / natural gas
    "plastic": ["oil", "petroleum", "crude oil", "petrochemical", "resin"],
    "plastics": ["oil", "petroleum", "crude oil", "petrochemical", "resin"],
    "plastic housing": ["oil", "petroleum", "crude oil", "petrochemical", "resin"],
    "plastic housings": ["oil", "petroleum", "crude oil", "petrochemical", "resin"],
    "polymer": ["oil", "petroleum", "crude oil", "petrochemical", "resin"],
    "polycarbonate": ["oil", "petroleum", "petrochemical"],
    "nylon": ["oil", "petroleum", "petrochemical"],
    "polyethylene": ["oil", "petroleum", "petrochemical", "ethylene"],
    "polypropylene": ["oil", "petroleum", "petrochemical"],
    "pvc": ["oil", "petroleum", "petrochemical", "chlorine"],
    "abs": ["oil", "petroleum", "petrochemical"],
    "rubber": ["oil", "petroleum", "natural rubber", "latex"],
    "synthetic rubber": ["oil", "petroleum", "petrochemical"],
    # Connectors & electronics ← copper, rare earths, semiconductors
    "connector": ["copper", "rare earth", "semiconductor"],
    "connectors": ["copper", "rare earth", "semiconductor"],
    "circuit board": ["copper", "rare earth", "semiconductor", "silicon"],
    "pcb": ["copper", "rare earth", "semiconductor", "silicon"],
    "semiconductor": ["silicon", "rare earth", "neon gas"],
    "semiconductors": ["silicon", "rare earth", "neon gas"],
    "wiring harness": ["copper", "rubber", "petroleum"],
    "cable": ["copper", "aluminum", "petroleum"],
    # Metals
    "steel": ["iron ore", "coal", "coking coal"],
    "stainless steel": ["iron ore", "nickel", "chromium"],
    "aluminum": ["bauxite", "alumina"],
    "aluminium": ["bauxite", "alumina"],
    # Battery & EV
    "battery": ["lithium", "cobalt", "nickel", "rare earth"],
    "batteries": ["lithium", "cobalt", "nickel", "rare earth"],
    "ev battery": ["lithium", "cobalt", "nickel", "manganese"],
    # Textiles
    "textile": ["cotton", "polyester", "petroleum"],
    "fabric": ["cotton", "polyester", "petroleum"],
}


def _get_upstream_materials(commodities_str: str | None) -> list[str]:
    """Return upstream raw materials for the given commodities string.

    Matches each parsed commodity against _COMMODITY_UPSTREAM_MAP using
    case-insensitive lookup.  Returns a deduplicated list.
    """
    if not commodities_str:
        return []
    parsed = _parse_commodities(commodities_str)
    seen: set[str] = set()
    result: list[str] = []
    for commodity in parsed:
        key = commodity.lower().strip()
        upstream = _COMMODITY_UPSTREAM_MAP.get(key, [])
        for mat in upstream:
            if mat not in seen:
                seen.add(mat)
                result.append(mat)
    return result


# ---------------------------------------------------------------------------
# Country-code → common-name aliases for semantic headline matching
# ---------------------------------------------------------------------------

_COUNTRY_ALIASES: dict[str, list[str]] = {
    "us": ["united states", "america", "usa", "u.s.", "us"],  # "us" for "US and Israel" etc.
    "uk": ["united kingdom", "britain", "england", "u.k."],
    "gb": ["united kingdom", "britain", "england", "u.k."],
    "cn": ["china", "chinese", "beijing", "shanghai"],
    "tw": ["taiwan", "taiwanese", "taipei"],
    "jp": ["japan", "japanese", "tokyo"],
    "kr": ["south korea", "korean", "seoul"],
    "de": ["germany", "german", "berlin", "munich"],
    "in": ["india", "indian", "delhi", "mumbai", "chennai"],
    "mx": ["mexico", "mexican"],
    "br": ["brazil", "brazilian"],
    "ru": ["russia", "russian", "moscow"],
    "ua": ["ukraine", "ukrainian", "kyiv"],
    "il": ["israel", "israeli", "tel aviv"],
    "sa": ["saudi arabia", "saudi"],
    "ae": ["uae", "emirates", "dubai", "abu dhabi"],
    "sg": ["singapore"],
    "my": ["malaysia", "malaysian", "kuala lumpur"],
    "th": ["thailand", "thai", "bangkok"],
    "vn": ["vietnam", "vietnamese", "hanoi", "ho chi minh"],
    "id": ["indonesia", "indonesian", "jakarta"],
    "ph": ["philippines", "filipino", "manila"],
    "au": ["australia", "australian", "sydney", "melbourne"],
    "ca": ["canada", "canadian", "toronto", "vancouver"],
    "fr": ["france", "french", "paris"],
    "it": ["italy", "italian", "milan"],
    "es": ["spain", "spanish", "madrid", "barcelona"],
    "pl": ["poland", "polish", "warsaw"],
    "tr": ["turkey", "turkish", "istanbul", "ankara"],
    "za": ["south africa"],
    "eg": ["egypt", "egyptian", "cairo", "suez"],
    "cl": ["chile", "chilean", "santiago"],
    "pe": ["peru", "peruvian", "lima"],
    "co": ["colombia", "colombian"],
    "ar": ["argentina", "argentine", "buenos aires"],
    "ng": ["nigeria", "nigerian", "lagos"],
    "ke": ["kenya", "kenyan", "nairobi"],
    "bd": ["bangladesh", "bangladeshi", "dhaka"],
    "pk": ["pakistan", "pakistani", "karachi"],
    "mm": ["myanmar", "burmese"],
    "ye": ["yemen", "yemeni"],
    "ir": ["iran", "iranian", "tehran"],
    "iq": ["iraq", "iraqi", "baghdad"],
    "sy": ["syria", "syrian"],
    "lb": ["lebanon", "lebanese", "beirut"],
}


def _build_supplier_keyword_pool(
    oem_data: EntityData | None, supplier_data: EntityData | None,
) -> list[str]:
    """Build a flat list of lowercase keywords from OEM/supplier data.

    Used for semantic matching of broad top-headlines against the entity pool.
    Returns keywords with len >= 3 to avoid false positives.
    """
    pool: set[str] = set()
    for entity in (oem_data, supplier_data):
        if not entity:
            continue
        name = (entity.get("name") or "").strip()
        if name and len(name) >= 3:
            pool.add(name.lower())
        for field in ("city", "country", "region", "location"):
            val = (entity.get(field) or "").strip()
            if val and len(val) >= 3:
                pool.add(val.lower())
        code = (entity.get("countryCode") or "").strip().lower()
        if code:
            for alias in _COUNTRY_ALIASES.get(code, []):
                pool.add(alias)
            # Also expand country name itself
            country_name = (entity.get("country") or "").strip().lower()
            if country_name and len(country_name) >= 3:
                pool.add(country_name)
        for commodity in _parse_commodities(entity.get("commodities")):
            if len(commodity) >= 3:
                pool.add(commodity.lower())
        # Add upstream raw materials so headlines about feedstock disruptions
        # (e.g. "oil markets", "petroleum prices") match suppliers that depend
        # on derived products (e.g. plastic housings).
        for mat in _get_upstream_materials(entity.get("commodities")):
            if len(mat) >= 3:
                pool.add(mat.lower())
    return list(pool)


def _headline_matches_pool(article: dict, keyword_pool: list[str]) -> bool:
    """Check if headline / description text matches any keyword from the supplier pool.

    Short country codes (e.g. 'us', 'uk') are matched with word boundaries so
    'US and Israel attack Iran' matches a US-based supplier (word 'us') and
    avoids false positives like 'us' in 'focus' or 'manufacturing'.
    """
    text = " ".join([
        article.get("title") or "",
        article.get("description") or "",
    ]).lower()
    if not text.strip():
        return False
    for kw in keyword_pool:
        if len(kw) <= 2:
            # Word-boundary match so "us" matches "US and Israel" not "focus"
            if re.search(r"\b" + re.escape(kw) + r"\b", text):
                return True
        elif kw in text:
            return True
    return False


# ---------------------------------------------------------------------------
# Keyword helpers — driven by oem_data and supplier_data, NOT scope
# ---------------------------------------------------------------------------

def _newsapi_keywords(
    oem_data: EntityData | None, supplier_data: EntityData | None
) -> list[str]:
    base = [
        "supply chain", "manufacturing", "logistics", "shipping",
        "war", "armed conflict", "military conflict", "supply chain war",
    ]
    if oem_data:
        oem_name = oem_data.get("name")
        if oem_name:
            base.append(oem_name)
        for commodity in _parse_commodities(oem_data.get("commodities"))[:3]:
            base.append(f"{commodity} supply chain")
        oem_city = oem_data.get("city")
        if oem_city:
            base.append(f"supply chain {oem_city}")
        oem_country = oem_data.get("countryCode") or oem_data.get("country")
        if oem_country:
            base.append(f"supply chain {oem_country}")
            base.append(f"attack {oem_country}")
            base.append(f"conflict {oem_country}")
    if supplier_data:
        supplier_name = supplier_data.get("name")
        if supplier_name:
            base.append(supplier_name)
        for commodity in _parse_commodities(supplier_data.get("commodities"))[:3]:
            base.append(f"{commodity} supply chain")
        sup_city = supplier_data.get("city")
        if sup_city:
            base.append(f"supply chain {sup_city}")
        sup_country = supplier_data.get("countryCode") or supplier_data.get("country")
        if sup_country:
            base.append(f"supply chain {sup_country}")
            base.append(f"attack {sup_country}")
            base.append(f"conflict {sup_country}")

    # Add upstream raw-material keywords so that events affecting feedstocks
    # (e.g. oil/petroleum for plastics) are captured even when articles don't
    # mention the finished commodity directly.
    for entity in (oem_data, supplier_data):
        if not entity:
            continue
        for mat in _get_upstream_materials(entity.get("commodities"))[:4]:
            base.append(f"{mat} supply chain")
            base.append(f"{mat} shortage")

    return base


def _gdelt_keywords(
    oem_data: EntityData | None, supplier_data: EntityData | None
) -> list[str]:
    # Conflict/war keywords come first so they are prioritised within GDELT's keyword cap
    base = [
        "attack",
        "armed conflict",
        "military conflict",
        "supply chain disruption",
        "trade sanctions",
        "port strike",
        "factory shutdown",
        "natural disaster manufacturing",
    ]
    if oem_data:
        oem_name = oem_data.get("name")
        if oem_name:
            base.append(f"{oem_name} disruption")
        for commodity in _parse_commodities(oem_data.get("commodities"))[:2]:
            base.append(f"{commodity} shortage")
        oem_country = oem_data.get("countryCode") or oem_data.get("country")
        if oem_country:
            base.append(f"attack {oem_country}")
            base.append(f"conflict {oem_country}")
            base.append(f"sanctions {oem_country}")
    if supplier_data:
        supplier_name = supplier_data.get("name")
        if supplier_name:
            base.append(f"{supplier_name} disruption")
        for commodity in _parse_commodities(supplier_data.get("commodities"))[:2]:
            base.append(f"{commodity} shortage")
        sup_country = supplier_data.get("countryCode") or supplier_data.get("country")
        if sup_country:
            base.append(f"attack {sup_country}")
            base.append(f"conflict {sup_country}")
            base.append(f"sanctions {sup_country}")

    # Upstream raw-material disruption keywords
    for entity in (oem_data, supplier_data):
        if not entity:
            continue
        for mat in _get_upstream_materials(entity.get("commodities"))[:4]:
            base.append(f"{mat} shortage")
            base.append(f"{mat} disruption")

    return base


def _entity_names(state: NewsAgentState) -> tuple[str | None, str | None]:
    """Return (oem_name, supplier_name) from state for broadcast payloads."""
    oem = state.get("oem_data")
    sup = state.get("supplier_data")
    return (
        oem.get("name") if oem else None,
        sup.get("name") if sup else None,
    )


# ---------------------------------------------------------------------------
# Parallel fetch nodes
# ---------------------------------------------------------------------------

async def _fetch_newsapi_node(state: NewsAgentState) -> NewsAgentState:
    """Fetch articles from NewsAPI.org. Skips API call when news_data already has news (avoids 429)."""
    context = state.get("context", "supplier")
    oem_data = state.get("oem_data")
    supplier_data = state.get("supplier_data")
    oem_name, supplier_name = _entity_names(state)
    # When orchestrator already fetched news (e.g. manager.fetch_by_types), skip to avoid 429
    pre = (state.get("news_data") or {}).get("news") or []
    if pre:
        logger.info("[NewsAgent:%s] Using pre-fetched news (%d items), skipping NewsAPI call", context, len(pre))
        await _broadcast_progress(
            "fetch_newsapi_skip", "Using pre-fetched news", context,
            {"count": len(pre)}, oem_name=oem_name, supplier_name=supplier_name,
        )
        return {"newsapi_raw": pre}
    keywords = _newsapi_keywords(oem_data, supplier_data)
    logger.info("[NewsAgent:%s] Fetching from NewsAPI with %d keywords", context, len(keywords))
    await _broadcast_progress("fetch_newsapi", "Fetching articles from NewsAPI", context, oem_name=oem_name, supplier_name=supplier_name)
    try:
        source = NewsDataSource()
        await source.initialize({})
        results = await source.fetch_data({"keywords": keywords})
        raw = [r.to_dict() for r in results]
        logger.info("[NewsAgent:%s] NewsAPI returned %d articles", context, len(raw))
        await _broadcast_progress(
            "fetch_newsapi_done", f"NewsAPI returned {len(raw)} articles",
            context, {"count": len(raw)}, oem_name=oem_name, supplier_name=supplier_name,
        )
    except Exception as exc:
        logger.exception("[NewsAgent:%s] NewsAPI fetch error: %s", context, exc)
        await _broadcast_progress("fetch_newsapi_error", f"NewsAPI error: {exc}", context, oem_name=oem_name, supplier_name=supplier_name)
        raw = []
    return {"newsapi_raw": raw}


async def _fetch_gdelt_node(state: NewsAgentState) -> NewsAgentState:
    """Fetch geopolitical event articles from GDELT (no API key required)."""
    context = state.get("context", "supplier")
    oem_data = state.get("oem_data")
    supplier_data = state.get("supplier_data")
    oem_name, supplier_name = _entity_names(state)
    keywords = _gdelt_keywords(oem_data, supplier_data)
    logger.info("[NewsAgent:%s] Fetching from GDELT with %d keywords", context, len(keywords))
    await _broadcast_progress("fetch_gdelt", "Fetching articles from GDELT", context, oem_name=oem_name, supplier_name=supplier_name)
    try:
        source = GDELTDataSource()
        await source.initialize({})
        results = await source.fetch_data({"keywords": keywords})
        raw = [r.to_dict() for r in results]
        logger.info("[NewsAgent:%s] GDELT returned %d articles", context, len(raw))
        await _broadcast_progress(
            "fetch_gdelt_done", f"GDELT returned {len(raw)} articles",
            context, {"count": len(raw)}, oem_name=oem_name, supplier_name=supplier_name,
        )
    except Exception as exc:
        logger.exception("[NewsAgent:%s] GDELT fetch error: %s", context, exc)
        await _broadcast_progress("fetch_gdelt_error", f"GDELT error: {exc}", context, oem_name=oem_name, supplier_name=supplier_name)
        raw = []
    return {"gdelt_raw": raw}


# ---------------------------------------------------------------------------
# Broad headline scan — fetch top headlines and semantic-match against
# the supplier/OEM keyword pool to catch events that keyword search misses
# ---------------------------------------------------------------------------

async def _fetch_top_headlines_node(state: NewsAgentState) -> NewsAgentState:
    """Fetch broad top headlines and filter by semantic match against the supplier pool.

    This catches breaking events that keyword-based NewsAPI queries would miss.
    For example, a headline "Earthquake hits Taiwan" would be picked up because
    "Taiwan" or "taiwanese" is in the supplier keyword pool even though the
    query "TSMC supply chain" was not used.
    """
    context = state.get("context", "supplier")
    oem_data = state.get("oem_data")
    supplier_data = state.get("supplier_data")
    oem_name, supplier_name = _entity_names(state)

    keyword_pool = _build_supplier_keyword_pool(oem_data, supplier_data)
    if not keyword_pool:
        logger.info("[NewsAgent:%s] No supplier keyword pool — skipping broad headline scan", context)
        return {"headlines_raw": []}

    await _broadcast_progress(
        "fetch_headlines",
        "Scanning top headlines for supplier-relevant events",
        context,
        {"pool_size": len(keyword_pool), "pool_sample": keyword_pool[:10]},
        oem_name=oem_name, supplier_name=supplier_name,
    )

    prefetched = state.get("prefetched_broad_headlines")
    try:
        if prefetched is not None:
            # Use headlines fetched once per OEM to avoid 429 (no API call here)
            all_headlines = prefetched
            logger.info("[NewsAgent:%s] Using %d pre-fetched broad headlines", context, len(all_headlines))
        else:
            source = NewsDataSource()
            await source.initialize({})
            all_headlines = await source.fetch_broad_headlines()

        matched: list[dict] = []
        for result in all_headlines:
            raw = result.to_dict() if hasattr(result, "to_dict") else result
            if not isinstance(raw, dict):
                continue
            article = raw.get("data", raw) if isinstance(raw, dict) else raw
            if isinstance(article, dict) and _headline_matches_pool(article, keyword_pool):
                matched.append(raw)

        logger.info(
            "[NewsAgent:%s] Broad headlines: %d total, %d matched supplier pool (pool=%d keywords)",
            context, len(all_headlines), len(matched), len(keyword_pool),
        )
        await _broadcast_progress(
            "fetch_headlines_done",
            f"Found {len(matched)} supplier-relevant headlines from {len(all_headlines)} scanned",
            context,
            {"total_scanned": len(all_headlines), "matched": len(matched)},
            oem_name=oem_name, supplier_name=supplier_name,
        )
    except Exception as exc:
        logger.exception("[NewsAgent:%s] Broad headline scan error: %s", context, exc)
        await _broadcast_progress(
            "fetch_headlines_error", f"Headline scan error: {exc}",
            context, oem_name=oem_name, supplier_name=supplier_name,
        )
        matched = []

    return {"headlines_raw": matched}


# ---------------------------------------------------------------------------
# Merge node — fan-in after parallel fetches
# ---------------------------------------------------------------------------

async def _merge_news_node(state: NewsAgentState) -> NewsAgentState:
    """
    Combine articles from all sources + any pre-fetched news_data.
    Deduplicates by normalised title to avoid redundant LLM tokens.
    """
    context = state.get("context", "supplier")
    oem_name, supplier_name = _entity_names(state)
    combined: list[dict] = []

    # Include legacy pre-fetched data passed from outside the graph
    external = state.get("news_data") or {}
    for item in external.get("news") or []:
        combined.append(item)

    for item in state.get("newsapi_raw") or []:
        combined.append(item)
    for item in state.get("gdelt_raw") or []:
        combined.append(item)
    for item in state.get("headlines_raw") or []:
        combined.append(item)

    # Deduplicate by normalised title
    seen_titles: set[str] = set()
    unique: list[dict] = []
    for item in combined:
        data = item.get("data") if isinstance(item, dict) else item
        if not isinstance(data, dict):
            continue
        title = (data.get("title") or "").strip().lower()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        unique.append(item)

    logger.info(
        "[NewsAgent:%s] Merged %d total -> %d unique articles after dedup",
        context, len(combined), len(unique),
    )
    await _broadcast_progress(
        "merge_done", f"Merged {len(unique)} unique articles (from {len(combined)} total)",
        context, {"total": len(combined), "unique": len(unique)},
        oem_name=oem_name, supplier_name=supplier_name,
    )
    # Store as a news_data dict so _build_news_items_node can consume it normally
    return {"news_data": {"news": unique}}


# ---------------------------------------------------------------------------
# Build news items node
# ---------------------------------------------------------------------------

async def _build_news_items_node(state: NewsAgentState) -> NewsAgentState:
    """Normalize raw news data into NewsItem structures."""
    context = state.get("context", "supplier")
    oem_name, supplier_name = _entity_names(state)
    raw = state.get("news_data") or {}
    items = raw.get("news") or []

    normalized: list[NewsItem] = []
    for item in items:
        data = item.get("data") if isinstance(item, dict) else item
        if not isinstance(data, dict):
            continue
        normalized.append(
            {
                "title": data.get("title"),
                "description": data.get("description"),
                "url": data.get("url"),
                "source": data.get("source"),
                "publishedAt": data.get("publishedAt"),
                "author": data.get("author"),
                "content": data.get("content"),
            }
        )
    logger.info("[NewsAgent:%s] Normalized %d news items for LLM", context, len(normalized))
    await _broadcast_progress(
        "items_ready", f"Prepared {len(normalized)} articles for analysis",
        context, {"count": len(normalized)},
        oem_name=oem_name, supplier_name=supplier_name,
    )
    return {"news_items": normalized}


# ---------------------------------------------------------------------------
# Build OEM/supplier context string for LLM prompts
# ---------------------------------------------------------------------------

def _build_entity_context(
    oem_data: EntityData | None, supplier_data: EntityData | None
) -> str:
    """Build a human-readable context block describing the OEM and supplier."""
    parts: list[str] = []
    if oem_data:
        oem_name = oem_data.get("name") or "Unknown"
        oem_loc_parts = [
            p
            for p in [
                oem_data.get("city"),
                oem_data.get("country"),
                oem_data.get("region"),
            ]
            if p
        ]
        oem_loc = ", ".join(oem_loc_parts) if oem_loc_parts else "Unknown"
        oem_commodities = oem_data.get("commodities") or "N/A"
        oem_upstream = _get_upstream_materials(oem_data.get("commodities"))
        oem_upstream_str = ", ".join(oem_upstream) if oem_upstream else "N/A"
        parts.append(
            f"OEM: {oem_name}\n"
            f"  Location: {oem_loc}\n"
            f"  Commodities: {oem_commodities}\n"
            f"  Upstream raw-material dependencies: {oem_upstream_str}"
        )
    if supplier_data:
        sup_name = supplier_data.get("name") or "Unknown"
        sup_loc_parts = [
            p
            for p in [
                supplier_data.get("city"),
                supplier_data.get("country"),
                supplier_data.get("region"),
            ]
            if p
        ]
        sup_loc = ", ".join(sup_loc_parts) if sup_loc_parts else "Unknown"
        sup_commodities = supplier_data.get("commodities") or "N/A"
        sup_upstream = _get_upstream_materials(supplier_data.get("commodities"))
        upstream_str = ", ".join(sup_upstream) if sup_upstream else "N/A"
        parts.append(
            f"Supplier: {sup_name}\n"
            f"  Location: {sup_loc}\n"
            f"  Commodities: {sup_commodities}\n"
            f"  Upstream raw-material dependencies: {upstream_str}"
        )
    return "\n".join(parts) if parts else "No entity context available."


def _get_llm():
    return get_chat_model()


def _build_supplier_prompt(
    oem_data: EntityData | None, supplier_data: EntityData | None
) -> ChatPromptTemplate:
    entity_context = _build_entity_context(oem_data, supplier_data)
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are a News Agent for a manufacturing supply "
                    "chain. You receive real-time and recent news items "
                    "(sourced from NewsAPI /everything, /top-headlines, "
                    "and broad headline scanning) about suppliers, OEMs, "
                    "and regions. Extract structured supply chain risk "
                    "signals using the following risk types: "
                    "factory_shutdown, labor_strike, "
                    "bankruptcy_risk, sanction_risk, "
                    "port_congestion, natural_disaster, "
                    "geopolitical_tension, war, armed_conflict, "
                    "regulatory_change, "
                    "infrastructure_failure, commodity_shortage, "
                    "cyber_incident.\n\n"
                    "RECENCY RULES:\n"
                    "- Each news item includes a 'publishedAt' timestamp. "
                    "Articles published within the last 24 hours are "
                    "breaking news — do NOT downgrade their severity. "
                    "Recent single-source reports of a war, shutdown, or "
                    "major disruption are sufficient to flag a risk.\n"
                    "- Weight recent articles more heavily than older ones "
                    "when determining severity.\n\n"
                    "GEOGRAPHIC MAPPING RULES:\n"
                    "- Cross-reference every news article with the OEM "
                    "and supplier locations listed in the Entity Context. "
                    "If an event occurs in the same country, region, or "
                    "city where the supplier or OEM operates, escalate "
                    "severity by one level (e.g. medium → high).\n"
                    "- Always populate 'affectedRegion' with the specific "
                    "country or region mentioned in the article.\n"
                    "- If the event affects a key commodity that the OEM "
                    "or supplier depends on (see commodities in Entity "
                    "Context), flag it even if the event is in a "
                    "different region — commodity supply chains are "
                    "global.\n"
                    "- For events like war, natural disasters, or port "
                    "closures: also consider indirect impact on trade "
                    "routes and neighbouring regions that supply "
                    "the OEM/supplier.\n\n"
                    "UPSTREAM COMMODITY DEPENDENCY RULES:\n"
                    "- The Entity Context lists 'Upstream raw-material "
                    "dependencies' for each entity. These are the "
                    "feedstocks and raw materials required to produce "
                    "the entity's commodities (e.g. plastic housings "
                    "depend on oil/petroleum/resin).\n"
                    "- If a news event disrupts an upstream raw material "
                    "(e.g. war in an oil-producing country, petroleum "
                    "price spikes, sanctions on a mineral exporter), "
                    "flag it as a risk for the supplier with risk_type "
                    "'commodity_shortage' even if the article never "
                    "mentions the supplier's finished commodity.\n"
                    "- War or conflict in major oil-producing regions "
                    "(Iran, Iraq, Saudi Arabia, Russia, Venezuela) "
                    "should be flagged as 'high' severity for ANY "
                    "supplier whose commodities depend on petroleum-"
                    "derived materials (plastics, polymers, rubber, "
                    "synthetic textiles). Example: ongoing US–Iran–Israel "
                    "attacks or conflict in the Middle East must be flagged "
                    "as commodity_shortage (high) for suppliers with "
                    "plastic/polymer/connector commodities because Iran "
                    "and the region are major oil producers.\n\n"
                    "CRITICAL SEVERITY RULES FOR WAR AND ARMED CONFLICT:\n"
                    "- If a news item reports active war or armed conflict "
                    "in a region: set severity to 'critical' and "
                    "risk_type to 'war' for the region where the conflict "
                    "is directly occurring. Always populate affectedRegion "
                    "with the specific country or region name.\n"
                    "- BELLIGERENT COUNTRIES: If the article names a "
                    "country as conducting or participating in military "
                    "operations (e.g. 'US and Israel attack Iran'), that "
                    "country is a belligerent. For a supplier whose "
                    "location/country is that belligerent, create a risk "
                    "with severity 'high' and risk_type 'war' or "
                    "'armed_conflict', with affectedRegion set to that "
                    "country. Example: a US-based supplier (e.g. Detroit) "
                    "in a headline 'US and Israel attack Iran' should get "
                    "a high-severity war/armed_conflict risk for the US "
                    "as affectedRegion, in addition to critical for Iran.\n"
                    "- For regions that could be indirectly affected by "
                    "the conflict (e.g. neighbouring countries, key trade "
                    "partners, or regions with significant supply chain "
                    "exposure to the conflict zone): create a separate "
                    "risk entry with severity 'high' and risk_type "
                    "'geopolitical_tension', and populate affectedRegion "
                    "with that region.\n"
                    "- Never downgrade a war/armed conflict event to "
                    "'medium' or 'low' severity.\n\n"
                    "IMPORTANT SCORING: Do NOT inflate severity for indirect or "
                    "speculative risks with no confirmed direct link to the supplier. "
                    "'critical' = confirmed shutdown, strike, sanctions, or imminent "
                    "bankruptcy directly involving this supplier. If news is vague "
                    "or only loosely related, either skip it or rate it 'low'.\n\n"
                    "Also extract positive opportunities (new trade deals, "
                    "capacity expansions, cost reductions, partnerships). "
                    "Not every article is a risk — look for positive "
                    "signals too.\n\n"
                    "IMPORTANT: News articles may be in any language. "
                    "Always return all extracted fields in English.\n\n"
                    "Only set estimatedCost when the article provides a "
                    "concrete figure. Do not guess or fabricate costs.\n\n"
                    "Return ONLY valid JSON."
                ),
            ),
            (
                "user",
                (
                    "Analyze the following news items in the context "
                    "of this OEM and supplier.\n\n"
                    f"=== Entity Context ===\n{entity_context}\n\n"
                    "=== News Items ===\n{news_items_json}\n\n"
                    "Return JSON of shape:\n"
                    "{{\n"
                    '  "risks": [\n'
                    "    {{\n"
                    '      "title": str,\n'
                    '      "description": str,\n'
                    '      "severity": "low" | "medium" | '
                    '"high" | "critical",\n'
                    '      "affectedRegion": str (REQUIRED — the country or region),\n'
                    '      "affectedSupplier": str | null,\n'
                    '      "estimatedImpact": str | null,\n'
                    '      "estimatedCost": number | null,\n'
                    '      "risk_type": str,\n'
                    '      "source": str | null\n'
                    "    }}\n"
                    "  ],\n"
                    '  "opportunities": [\n'
                    "    {{\n"
                    '      "title": str,\n'
                    '      "description": str,\n'
                    '      "type": "cost_saving" | '
                    '"time_saving" | "quality_improvement" | '
                    '"market_expansion" | '
                    '"supplier_diversification",\n'
                    '      "affectedRegion": str | null,\n'
                    '      "potentialBenefit": str | null,\n'
                    '      "estimatedValue": number | null\n'
                    "    }}\n"
                    "  ]\n"
                    "}}\n"
                    "If none, use empty arrays."
                ),
            ),
        ]
    )


def _build_global_prompt(
    oem_data: EntityData | None, supplier_data: EntityData | None
) -> ChatPromptTemplate:
    entity_context = _build_entity_context(oem_data, supplier_data)
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "receive real-time and recent news (sourced from "
                    "NewsAPI /everything, /top-headlines, and broad "
                    "headline scanning) about macro events (geopolitics, "
                    "trade, climate, logistics, war). Extract global "
                    "supply chain risks AND opportunities that could "
                    "affect the given OEM and supplier.\n\n"
                    "RECENCY RULES:\n"
                    "- Each news item includes a 'publishedAt' timestamp. "
                    "Treat articles published within the last 24 hours as "
                    "breaking events — do NOT downgrade their severity. "
                    "A single recent report of war, a major port closure, "
                    "or sanctions is sufficient to raise a risk.\n"
                    "- Weight recent articles more heavily when assigning "
                    "severity.\n\n"
                    "GEOGRAPHIC MAPPING RULES:\n"
                    "- Cross-reference every article against the OEM and "
                    "supplier locations in the Entity Context below.\n"
                    "- If a global event occurs in the same country or "
                    "region as the OEM or supplier, escalate severity.\n"
                    "- Consider trade-route and commodity dependencies: "
                    "Red Sea disruptions affect Asia-Europe routes, "
                    "Taiwan events affect semiconductor supply, etc.\n"
                    "- Always populate 'affectedRegion' with the specific "
                    "country or region from the article.\n\n"
                    "UPSTREAM COMMODITY DEPENDENCY RULES:\n"
                    "- The Entity Context lists 'Upstream raw-material "
                    "dependencies'. If a global event disrupts an "
                    "upstream raw material (e.g. war in an oil-producing "
                    "country, petroleum price spikes), flag it as a risk "
                    "with risk_type 'commodity_shortage' even if the "
                    "article doesn't mention the finished commodity.\n"
                    "- War or conflict in major oil-producing regions "
                    "(Iran, Iraq, Saudi Arabia, Russia, Venezuela) "
                    "should be flagged for suppliers whose commodities "
                    "depend on petroleum-derived materials. Example: "
                    "US–Iran–Israel attacks or Middle East conflict → "
                    "commodity_shortage (high) for plastic/polymer "
                    "suppliers.\n\n"
                    "CRITICAL SEVERITY RULES FOR WAR AND ARMED CONFLICT:\n"
                    "- If a news item reports active war or armed conflict "
                    "in a region: set severity to 'critical' and "
                    "risk_type to 'war' for the region where the conflict "
                    "is directly occurring. Always populate affectedRegion "
                    "with the specific country or region name.\n"
                    "- BELLIGERENT COUNTRIES: If the article names a "
                    "country as conducting military operations (e.g. 'US "
                    "and Israel attack Iran'), for a supplier in that "
                    "country create a risk with severity 'high' and "
                    "risk_type 'war' or 'armed_conflict' with "
                    "affectedRegion set to that country.\n"
                    "- For regions that could be indirectly affected by "
                    "the conflict (e.g. neighbouring countries, key trade "
                    "partners, or regions with significant supply chain "
                    "exposure to the conflict zone): create a separate "
                    "risk entry with severity 'high' and risk_type "
                    "'geopolitical_tension', and populate affectedRegion "
                    "with that region.\n"
                    "- Never downgrade a war/armed conflict event to "
                    "'medium' or 'low' severity.\n\n"
                    "IMPORTANT: Be conservative with severity for distant "
                    "macro events — rate 'high' or 'critical' only when there "
                    "is confirmed, direct impact on this supplier. News "
                    "articles may be in any language; return all extracted "
                    "fields in English. Only set estimatedCost when the "
                    "article provides a concrete figure."
                ),
            ),
            (
                "user",
                (
                    "Analyze the following news items for global supply "
                    "chain risks and opportunities relevant to this OEM "
                    "and supplier.\n\n"
                    f"=== Entity Context ===\n{entity_context}\n\n"
                    "=== News Items ===\n{news_items_json}\n\n"
                    "Return JSON of shape:\n"
                    "{{\n"
                    '  "risks": [\n'
                    "    {{\n"
                    '      "title": str,\n'
                    '      "description": str,\n'
                    '      "severity": "low" | "medium" | '
                    '"high" | "critical",\n'
                    '      "affectedRegion": str (REQUIRED — the country or region),\n'
                    '      "affectedSupplier": str | null,\n'
                    '      "estimatedImpact": str | null,\n'
                    '      "estimatedCost": number | null,\n'
                    '      "risk_type": str,\n'
                    '      "source": str | null\n'
                    "    }}\n"
                    "  ],\n"
                    '  "opportunities": [\n'
                    "    {{\n"
                    '      "title": str,\n'
                    '      "description": str,\n'
                    '      "type": "cost_saving" | '
                    '"time_saving" | "quality_improvement" | '
                    '"market_expansion" | '
                    '"supplier_diversification",\n'
                    '      "affectedRegion": str | null,\n'
                    '      "potentialBenefit": str | null,\n'
                    '      "estimatedValue": number | null\n'
                    "    }}\n"
                    "  ]\n"
                    "}}\n"
                    "If none, use empty arrays."
                ),
            ),
        ]
    )


# ---------------------------------------------------------------------------
# LLM risk extraction node
# ---------------------------------------------------------------------------

async def _news_risk_llm_node(state: NewsAgentState) -> NewsAgentState:
    """
    Convert NewsItem list into risks and opportunities using LangChain.
    Builds prompts using oem_data and supplier_data from state.
    Returns empty lists when LLM is not configured.
    """
    items = state.get("news_items") or []
    if not items:
        return {"news_risks": [], "news_opportunities": []}

    llm = _get_llm()
    if not llm:
        return {"news_risks": [], "news_opportunities": []}

    context = state.get("context", "supplier") or "supplier"
    oem_data = state.get("oem_data")
    supplier_data = state.get("supplier_data")
    oem_name, supplier_name = _entity_names(state)

    if context == "supplier":
        prompt = _build_supplier_prompt(oem_data, supplier_data)
    else:
        prompt = _build_global_prompt(oem_data, supplier_data)

    chain = prompt | llm

    # Derive provider/model for logging
    provider = getattr(llm, "model_provider", None) or type(llm).__name__
    model_name = getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")
    call_id = _uuid.uuid4().hex[:8]

    # Sort most-recent articles first so the LLM sees breaking news at the top
    items_sorted = sorted(
        items,
        key=lambda x: x.get("publishedAt") or "",
        reverse=True,
    )

    items_json = json.dumps(items_sorted, indent=2)
    prompt_text = prompt.format(news_items_json=items_json)
    start = time.perf_counter()

    try:
        logger.info(
            "[NewsAgent:%s] LLM request id=%s provider=%s model=%s prompt_len=%d",
            context, call_id, provider, model_name, len(prompt_text),
        )
        await _broadcast_progress(
            "llm_start", f"Running {context} risk extraction",
            context, {"call_id": call_id, "provider": provider, "model": str(model_name)},
            oem_name=oem_name, supplier_name=supplier_name,
        )
        msg = await chain.ainvoke({"news_items_json": items_json})
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
            "[NewsAgent:%s] LLM response id=%s provider=%s elapsed_ms=%d response_len=%d",
            context, call_id, provider, elapsed, len(raw_text),
        )
        _persist_llm_log(
            call_id, provider, str(model_name),
            prompt_text, raw_text, "success", elapsed, None,
        )

        parsed = _extract_json(raw_text) or {}
        raw_risks = parsed.get("risks") or []
        raw_opps = parsed.get("opportunities") or []

        risks: list[dict] = []
        opps: list[dict] = []

        for r in raw_risks:
            if not isinstance(r, dict):
                continue
            title = (str(r.get("title") or "")).strip()
            desc = (str(r.get("description") or "")).strip()
            if not title or not desc:
                continue
            risks.append(r)

        for o in raw_opps:
            if not isinstance(o, dict):
                continue
            title = (str(o.get("title") or "")).strip()
            desc = (str(o.get("description") or "")).strip()
            if not title or not desc:
                continue
            opps.append(o)

        logger.info(
            "[NewsAgent:%s] LLM extraction complete: risks=%d opportunities=%d elapsed_ms=%d",
            context, len(risks), len(opps), elapsed,
        )
        await _broadcast_progress(
            "llm_done", f"Extracted {len(risks)} risks and {len(opps)} opportunities",
            context, {"risks": len(risks), "opportunities": len(opps), "elapsed_ms": elapsed},
            oem_name=oem_name, supplier_name=supplier_name,
        )
        return {"news_risks": risks, "news_opportunities": opps}
    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.exception("[NewsAgent:%s] LLM error: %s", context, exc)
        _persist_llm_log(
            call_id, provider, str(model_name),
            prompt_text, None, "error", elapsed, str(exc),
        )
        await _broadcast_progress("llm_error", f"LLM error: {exc}", context, oem_name=oem_name, supplier_name=supplier_name)
        return {"news_risks": [], "news_opportunities": []}


# ---------------------------------------------------------------------------
# Graph definition — parallel fetch → merge → build → LLM
# ---------------------------------------------------------------------------

_builder = StateGraph(NewsAgentState)

# Parallel fetch nodes (fan-out from START)
_builder.add_node("fetch_newsapi", _fetch_newsapi_node)
_builder.add_node("fetch_gdelt", _fetch_gdelt_node)
_builder.add_node("fetch_top_headlines", _fetch_top_headlines_node)

# Fan-in merge then existing pipeline
_builder.add_node("merge_news", _merge_news_node)
_builder.add_node("build_items", _build_news_items_node)
_builder.add_node("news_risk_llm", _news_risk_llm_node)

# Fan-out: START → all three fetch nodes in parallel
_builder.add_edge(START, "fetch_newsapi")
_builder.add_edge(START, "fetch_gdelt")
_builder.add_edge(START, "fetch_top_headlines")

# Fan-in: all fetch nodes → merge
_builder.add_edge("fetch_newsapi", "merge_news")
_builder.add_edge("fetch_gdelt", "merge_news")
_builder.add_edge("fetch_top_headlines", "merge_news")

# Linear pipeline after merge
_builder.add_edge("merge_news", "build_items")
_builder.add_edge("build_items", "news_risk_llm")
_builder.add_edge("news_risk_llm", END)

NEWS_GRAPH = _builder.compile()


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def _resolve_entity_data(
    scope: OemScope,
) -> tuple[EntityData | None, EntityData | None]:
    """Fetch OEM and supplier details from the DB using IDs in scope."""
    db = SessionLocal()
    try:
        oem_data: EntityData | None = None
        supplier_data: EntityData | None = None

        oem_id_str = scope.get("oemId")
        if oem_id_str:
            oem = get_oem_by_id(db, UUID(oem_id_str))
            if oem:
                oem_data = _entity_from_model(oem)

        supplier_id_str = scope.get("supplierId")
        if supplier_id_str:
            supplier = get_supplier_by_id(db, UUID(supplier_id_str))
            if supplier:
                supplier_data = _entity_from_model(supplier)

        return oem_data, supplier_data
    finally:
        db.close()


async def run_news_agent_graph(
    news_data: dict[str, list[dict]],
    scope: OemScope,
    context: Literal["supplier", "global"],
    prefetched_broad_headlines: list[dict] | None = None,
) -> dict[str, list[dict]]:
    """
    Orchestrate the News Agent using LangGraph and LangChain.

    Fetches from NewsAPI and GDELT in parallel, merges and deduplicates the
    articles, then runs LLM risk/opportunity extraction.

    When prefetched_broad_headlines is provided (e.g. once per OEM), the graph
    skips the broad-headline API call to avoid 429 rate limits.

    OEM and supplier details are fetched from the database using ``oemId``
    and ``supplierId`` from the scope.
    """
    oem_data, supplier_data = _resolve_entity_data(scope)

    oem_label = (oem_data or {}).get("name") or scope.get("oemName") or "unknown"
    sup_label = (supplier_data or {}).get("name") if supplier_data else None
    entity_label = f"{oem_label}/{sup_label}" if sup_label else oem_label

    logger.info("[NewsAgent:%s] Starting news graph for %s", context, entity_label)
    await _broadcast_progress(
        "started", f"Starting {context} news analysis for {entity_label}",
        context, {"oem": oem_label, "supplier": sup_label},
        oem_name=oem_label, supplier_name=sup_label,
    )

    initial_state: NewsAgentState = {
        "scope": scope,
        "news_data": news_data,
        "context": context,
        "oem_data": oem_data,
        "supplier_data": supplier_data,
        "prefetched_broad_headlines": prefetched_broad_headlines,
    }

    final_state = await NEWS_GRAPH.ainvoke(initial_state)

    risks = final_state.get("news_risks") or []
    opps = final_state.get("news_opportunities") or []

    risks_for_db: list[dict] = []
    opps_for_db: list[dict] = []

    for r in risks:
        db_risk = {
            "title": r["title"],
            "description": r["description"],
            "severity": r.get("severity"),
            "affectedRegion": r.get("affectedRegion"),
            "affectedSupplier": r.get("affectedSupplier"),
            "estimatedImpact": r.get("estimatedImpact"),
            "estimatedCost": r.get("estimatedCost"),
            "sourceType": "news",
            "sourceData": {
                "risk_type": r.get("risk_type"),
                "source": r.get("source"),
                "context": context,
            },
        }
        risks_for_db.append(db_risk)

    for o in opps:
        db_opp = {
            "title": o["title"],
            "description": o["description"],
            "type": o.get("type"),
            "affectedRegion": o.get("affectedRegion"),
            "potentialBenefit": o.get("potentialBenefit"),
            "estimatedValue": o.get("estimatedValue"),
            "sourceType": "news",
            "sourceData": {"context": context},
        }
        opps_for_db.append(db_opp)

    logger.info(
        "[NewsAgent:%s] Completed: risks=%d opportunities=%d for %s",
        context, len(risks_for_db), len(opps_for_db), entity_label,
    )
    await _broadcast_progress(
        "context_done",
        f"Completed {context} analysis: {len(risks_for_db)} risks, {len(opps_for_db)} opportunities",
        context,
        {"risks": len(risks_for_db), "opportunities": len(opps_for_db)},
        oem_name=oem_label, supplier_name=sup_label,
    )

    return {
        "risks": risks_for_db,
        "opportunities": opps_for_db,
        "newsapi_raw": final_state.get("newsapi_raw") or [],
        "gdelt_raw": final_state.get("gdelt_raw") or [],
        "news_items": [dict(item) for item in (final_state.get("news_items") or [])],
    }
