"""Provider-agnostic LLM client for the trend-insights agent.

Supported providers (selected via settings.llm_provider):
  - "anthropic"  - Anthropic Claude (default)
  - "openai"     - OpenAI ChatGPT (gpt-4o-mini by default)
  - "ollama"     - Local Ollama

If no valid key/endpoint is found the client falls back to a rule-based mock
so the demo always returns useful output regardless of credentials.

Usage
-----
    client = get_llm_client()
    raw_text = await client.invoke("Your prompt here")
    insights = await client.generate_insights(trend_context)
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger(__name__)

_LLM_LOG_MAX_CHARS = 4000


# ── Data classes ──────────────────────────────────────────────────────


@dataclass
class TrendItem:
    title: str
    summary: str
    source: str
    published_at: str
    level: str  # "material" | "supplier" | "global"
    query: str
    url: str | None = None
    relevance_score: float = 0.7


@dataclass
class TrendContext:
    """Aggregated context passed to the LLM for insight generation."""

    oem_name: str = ""
    suppliers: list[dict] = field(default_factory=list)
    materials: list[dict] = field(default_factory=list)
    global_context: list[dict] = field(default_factory=list)
    trend_items: list[TrendItem] = field(default_factory=list)


@dataclass
class Insight:
    scope: str  # "material" | "supplier" | "global"
    entity_name: str  # material or supplier name, or "Global"
    risk_opportunity: str  # "risk" | "opportunity"
    title: str
    description: str
    predicted_impact: str
    time_horizon: str  # "short-term" | "medium-term" | "long-term"
    severity: str  # "low" | "medium" | "high" | "critical"
    recommended_actions: list[str] = field(default_factory=list)
    confidence: float = 0.7
    source_articles: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scope": self.scope,
            "entity_name": self.entity_name,
            "risk_opportunity": self.risk_opportunity,
            "title": self.title,
            "description": self.description,
            "predicted_impact": self.predicted_impact,
            "time_horizon": self.time_horizon,
            "severity": self.severity,
            "recommended_actions": self.recommended_actions,
            "confidence": self.confidence,
            "source_articles": self.source_articles,
        }


# ── LLM adapter base ──────────────────────────────────────────────────


class BaseLLMAdapter:
    provider: str = "base"
    model: str = "unknown"

    async def _raw_invoke(self, prompt: str) -> str:
        raise NotImplementedError

    async def invoke(self, prompt: str) -> str:
        call_id = uuid.uuid4().hex[:8]
        start = time.perf_counter()
        logger.info(
            "LLM request id=%s provider=%s model=%s prompt_len=%d",
            call_id,
            self.provider,
            self.model,
            len(prompt),
        )
        try:
            response = await self._raw_invoke(prompt)
        except Exception as exc:
            elapsed = int((time.perf_counter() - start) * 1000)
            logger.exception(
                "LLM error id=%s provider=%s model=%s elapsed_ms=%d",
                call_id,
                self.provider,
                self.model,
                elapsed,
            )
            _persist_llm_log(
                call_id,
                self.provider,
                self.model,
                prompt,
                None,
                "error",
                elapsed,
                str(exc),
            )
            raise
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.info(
            "LLM response id=%s provider=%s elapsed_ms=%d response_len=%d",
            call_id,
            self.provider,
            elapsed,
            len(response),
        )
        _persist_llm_log(
            call_id,
            self.provider,
            self.model,
            prompt,
            response,
            "success",
            elapsed,
            None,
        )
        return response

    async def generate_insights(self, ctx: TrendContext) -> list[Insight]:
        """Run three focused LLM calls concurrently — one per scope — and merge results."""
        material_ctx = _ScopedContext("material", ctx)
        supplier_ctx = _ScopedContext("supplier", ctx)
        global_ctx = _ScopedContext("global", ctx)

        import asyncio

        results = await asyncio.gather(
            self._invoke_scope(material_ctx),
            self._invoke_scope(supplier_ctx),
            self._invoke_scope(global_ctx),
            return_exceptions=True,
        )

        insights: list[Insight] = []
        scopes = ("material", "supplier", "global")
        for scope, result in zip(scopes, results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Scope '%s' call failed: %s - using mock for that scope",
                    scope,
                    result,
                )
                insights.extend(_mock_insights_for_scope(scope, ctx))
            else:
                insights.extend(result)

        if not insights:
            insights = _mock_insights(ctx)
        return insights

    async def _invoke_scope(self, scoped: "_ScopedContext") -> list[Insight]:
        prompt = _build_scope_prompt(scoped)
        try:
            raw = await self.invoke(prompt)
            parsed = _parse_insights(raw)
            if parsed:
                return parsed
        except Exception as exc:
            logger.exception("Scope '%s' LLM call failed: %s", scoped.scope, exc)
        return _mock_insights_for_scope(scoped.scope, scoped.ctx)


# ── Anthropic adapter ─────────────────────────────────────────────────


class AnthropicAdapter(BaseLLMAdapter):
    provider = "anthropic"

    def __init__(self):
        from anthropic import AsyncAnthropic

        self.model = settings.anthropic_model or "claude-3-5-sonnet-20241022"
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def _raw_invoke(self, prompt: str) -> str:
        msg = await self._client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text if msg.content else ""


# ── OpenAI adapter ────────────────────────────────────────────────────


class OpenAIAdapter(BaseLLMAdapter):
    provider = "openai"

    def __init__(self):
        from openai import AsyncOpenAI

        self.model = settings.openai_model or "gpt-4o-mini"
        kwargs: dict = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
            logger.info("OpenAI using custom base_url: %s", settings.openai_base_url)
        self._client = AsyncOpenAI(**kwargs)

    async def _raw_invoke(self, prompt: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""


# ── Ollama adapter ────────────────────────────────────────────────────


class OllamaAdapter(BaseLLMAdapter):
    provider = "ollama"

    def __init__(self):
        import httpx as _httpx  # noqa: F401 - just verify it's importable

        self.model = settings.ollama_model or "llama3"
        self._base_url = (settings.ollama_base_url or "http://localhost:11434").rstrip(
            "/"
        )

    async def _raw_invoke(self, prompt: str) -> str:
        import httpx

        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self._base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=120.0,
            )
            if r.status_code != 200:
                raise RuntimeError(f"Ollama error {r.status_code}: {r.text[:200]}")
            return r.json().get("response") or ""


# ── Mock adapter (no credentials) ────────────────────────────────────


class MockAdapter(BaseLLMAdapter):
    provider = "mock"
    model = "mock"

    async def _raw_invoke(self, prompt: str) -> str:
        return ""

    async def generate_insights(self, ctx: TrendContext) -> list[Insight]:
        logger.info(
            "MockAdapter: returning rule-based insights (no LLM key configured)."
        )
        return _mock_insights(ctx)


# ── Factory ───────────────────────────────────────────────────────────

_cached_client: BaseLLMAdapter | None = None


def get_llm_client() -> BaseLLMAdapter:
    global _cached_client
    if _cached_client is not None:
        return _cached_client

    provider = (settings.llm_provider or "anthropic").lower()

    if provider == "openai" and settings.openai_api_key:
        logger.info("LLM client: OpenAI model=%s", settings.openai_model)
        _cached_client = OpenAIAdapter()
    elif provider == "ollama":
        logger.info(
            "LLM client: Ollama model=%s base=%s",
            settings.ollama_model,
            settings.ollama_base_url,
        )
        _cached_client = OllamaAdapter()
    elif settings.anthropic_api_key:
        logger.info("LLM client: Anthropic model=%s", settings.anthropic_model)
        _cached_client = AnthropicAdapter()
    elif settings.openai_api_key:
        logger.info("LLM client: OpenAI (fallback) model=%s", settings.openai_model)
        _cached_client = OpenAIAdapter()
    else:
        logger.warning("No LLM credentials found - using rule-based MockAdapter.")
        _cached_client = MockAdapter()

    return _cached_client


def reset_llm_client() -> None:
    """Force re-initialisation on next call (useful after config change in tests)."""
    global _cached_client
    _cached_client = None


# ── Scoped context (one per parallel call) ────────────────────────────


@dataclass
class _ScopedContext:
    scope: str  # "material" | "supplier" | "global"
    ctx: TrendContext


# ── Per-scope prompt builders ─────────────────────────────────────────


def _fmt_trend_items(items: list[TrendItem], limit: int = 6) -> str:
    if not items:
        return "  (none)"
    return "\n".join(
        f"  [{i + 1}] {it.title} | {it.source} | {it.published_at[:10]}\n"
        f"       {it.summary[:200]}"
        for i, it in enumerate(items[:limit])
    )


def _build_scope_prompt(scoped: _ScopedContext) -> str:
    ctx = scoped.ctx
    scope = scoped.scope

    oem = ctx.oem_name or "Unnamed Manufacturer"
    supplier_names = ", ".join(s.get("name", "") for s in ctx.suppliers[:10]) or "N/A"
    material_names = (
        ", ".join(m.get("material_name", "") for m in ctx.materials[:10]) or "N/A"
    )
    global_rows = (
        "; ".join(g.get("macro_trend", "") for g in ctx.global_context[:5]) or "N/A"
    )

    trend_items = [t for t in ctx.trend_items if t.level == scope]
    news_block = _fmt_trend_items(trend_items)

    if scope == "material":
        entities = material_names
        focus_line = "Focus exclusively on MATERIAL-level risks and opportunities (prices, shortages, substitutes, lead times)."
        count = "3-4"
    elif scope == "supplier":
        entities = supplier_names
        focus_line = "Focus exclusively on SUPPLIER-level risks and opportunities (delivery reliability, geopolitics, capacity, financial health)."
        count = "3-4"
    else:
        entities = global_rows
        focus_line = "Focus exclusively on GLOBAL macro-level risks and opportunities (trade policy, freight, regulation, climate, geopolitics)."
        count = "2-3"

    return f"""You are a predictive supply chain intelligence agent for a manufacturer.

=== MANUFACTURER CONTEXT ===
OEM: {oem}
Key Suppliers: {supplier_names}
Key Materials: {material_names}
Known Global Macro Trends: {global_rows}

=== SCOPE: {scope.upper()} ===
Relevant entities: {entities}

=== {scope.upper()}-LEVEL NEWS SIGNALS ===
{news_block}

=== TASK ===
{focus_line}
Generate {count} predictive, actionable insights for scope="{scope}" only.

Return ONLY a JSON array. Each element must have exactly these keys:
  scope            - "{scope}"
  entity_name      - specific material name, supplier name, or "Global"
  risk_opportunity - "risk" | "opportunity"
  title            - headline max 12 words
  description      - 2-3 sentences grounded in the news above
  predicted_impact - quantified impact (%, days, $)
  time_horizon     - "short-term" | "medium-term" | "long-term"
  severity         - "low" | "medium" | "high" | "critical"
  recommended_actions - array of 3-5 specific action strings
  confidence       - float 0.5-0.95
  source_articles  - array of article titles used as evidence

No prose, no markdown fences. JSON array only."""


# ── Response parser ───────────────────────────────────────────────────


def _extract_json_array(text: str) -> list | None:
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _parse_insights(raw: str) -> list[Insight]:
    data = _extract_json_array(raw)
    if not data or not isinstance(data, list):
        logger.warning(
            "Could not parse insights from LLM response; falling back to mock."
        )
        return []
    insights = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            insights.append(
                Insight(
                    scope=item.get("scope", "global"),
                    entity_name=item.get("entity_name", "Unknown"),
                    risk_opportunity=item.get("risk_opportunity", "risk"),
                    title=item.get("title", "Untitled"),
                    description=item.get("description", ""),
                    predicted_impact=item.get("predicted_impact", ""),
                    time_horizon=item.get("time_horizon", "medium-term"),
                    severity=item.get("severity", "medium"),
                    recommended_actions=item.get("recommended_actions") or [],
                    confidence=float(item.get("confidence", 0.7)),
                    source_articles=item.get("source_articles") or [],
                )
            )
        except Exception as exc:
            logger.warning("Skipping malformed insight item: %s", exc)
    return insights


# ── Rule-based mock insights ──────────────────────────────────────────


def _mock_insights_for_scope(scope: str, ctx: TrendContext) -> list[Insight]:
    """Return only the mock insights for a single scope."""
    return [i for i in _mock_insights(ctx) if i.scope == scope]


def _mock_insights(ctx: TrendContext) -> list[Insight]:
    """Generate deterministic insights from Excel data without calling an LLM."""
    insights: list[Insight] = []

    for m in ctx.materials[:3]:
        name = m.get("material_name", "material")
        criticality = m.get("criticality", "medium")
        volatility = m.get("price_volatility", "medium")
        insights.append(
            Insight(
                scope="material",
                entity_name=name.title(),
                risk_opportunity="risk",
                title=f"{name.title()} supply constraint risk",
                description=(
                    f"{name.title()} is classified as {criticality}-criticality with {volatility} "
                    f"price volatility. Current market signals indicate potential supply tightening "
                    f"driven by geopolitical and demand-side pressures."
                ),
                predicted_impact=f"10-20% cost increase and {m.get('avg_lead_time_days', 30)}+ day lead-time extension.",
                time_horizon="short-term",
                severity="high" if criticality in ("critical", "high") else "medium",
                recommended_actions=[
                    f"Increase safety stock for {name} by 30-45 days.",
                    "Qualify at least one alternative supplier within 90 days.",
                    "Issue formal supplier risk questionnaire to current source.",
                    "Review purchase contracts for force-majeure and price-cap clauses.",
                ],
                confidence=0.72,
                source_articles=[
                    t.title for t in ctx.trend_items if name.lower() in t.query.lower()
                ][:3],
            )
        )

    for s in ctx.suppliers[:3]:
        name = s.get("name", "supplier")
        region = s.get("region", "")
        risk = s.get("risk_score", 50)
        insights.append(
            Insight(
                scope="supplier",
                entity_name=name,
                risk_opportunity="risk" if int(risk or 50) > 60 else "opportunity",
                title=f"Supply continuity assessment: {name}",
                description=(
                    f"{name} (region: {region}) carries a risk score of {risk}. "
                    f"Recent news signals point to operational or geopolitical pressures "
                    f"affecting delivery reliability from this supplier."
                ),
                predicted_impact="Delivery delays of 2-4 weeks and potential cost uplift of 5-15%.",
                time_horizon="short-term",
                severity="high" if int(risk or 50) >= 70 else "medium",
                recommended_actions=[
                    f"Schedule business continuity review call with {name}.",
                    "Increase on-hand inventory buffer to 8 weeks.",
                    "Identify and onboard secondary supplier in alternate region.",
                    "Insert escalation clause in next procurement contract renewal.",
                ],
                confidence=0.68,
                source_articles=[
                    t.title for t in ctx.trend_items if t.level == "supplier"
                ][:2],
            )
        )

    global_trends = ctx.global_context or []
    for g in global_trends[:2]:
        trend = g.get("macro_trend", "global risk")
        severity = g.get("severity", "medium")
        insights.append(
            Insight(
                scope="global",
                entity_name="Global",
                risk_opportunity="risk",
                title=f"Global macro risk: {trend[:60]}",
                description=(
                    f"The macro trend '{trend}' poses a systemic risk to the manufacturer's supply chain. "
                    f"Industry data and recent news confirm the trend is active and escalating."
                ),
                predicted_impact="Broad supply chain disruption with 3-6 month recovery horizon.",
                time_horizon=g.get("time_horizon", "medium-term"),
                severity=severity,
                recommended_actions=[
                    "Brief executive leadership on macro risk landscape.",
                    "Activate supply chain war-game scenario for this disruption type.",
                    "Review insurance coverage for supply chain interruption.",
                    "Accelerate supplier-diversification roadmap.",
                ],
                confidence=0.65,
                source_articles=[
                    t.title for t in ctx.trend_items if t.level == "global"
                ][:2],
            )
        )

    return insights


# ── LLM log persistence (fire-and-forget, best effort) ────────────────


def _persist_llm_log(
    call_id: str,
    provider: str,
    model: str,
    prompt: str,
    response: str | None,
    status: str,
    elapsed_ms: int,
    error_message: str | None,
) -> None:
    try:
        from app.database import SessionLocal
        from app.models.llm_log import LlmLog
        from sqlalchemy.exc import SQLAlchemyError

        db = SessionLocal()
        try:
            row = LlmLog(
                callId=call_id,
                provider=provider,
                model=model,
                prompt=prompt[:_LLM_LOG_MAX_CHARS],
                response=(response or "")[:_LLM_LOG_MAX_CHARS] if response else None,
                status=status,
                elapsedMs=elapsed_ms,
                errorMessage=error_message,
            )
            db.add(row)
            db.commit()
        except SQLAlchemyError:
            logger.exception("Failed to persist LLM log")
        finally:
            db.close()
    except Exception:
        pass
