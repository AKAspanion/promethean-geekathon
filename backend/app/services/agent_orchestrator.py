import json
import logging
import re
import time
import uuid
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import SessionLocal
from app.models.llm_log import LlmLog
from app.models.risk import RiskSeverity
from app.models.opportunity import OpportunityType
from app.services.agent_types import OemScope

logger = logging.getLogger(__name__)

# LLM abstraction: we use Anthropic or Ollama via simple invoke(text) -> str
_invoke_fn: Any = None


def _persist_llm_log(
    call_id: str,
    provider: str,
    model: str,
    prompt: str,
    response: str | None,
    status: str,
    elapsed_ms: int | None,
    error_message: str | None,
) -> None:
    try:
        db = SessionLocal()
        try:
            row = LlmLog(
                callId=call_id,
                provider=provider,
                model=model,
                prompt=prompt,
                response=response,
                status=status,
                elapsedMs=elapsed_ms,
                errorMessage=error_message,
            )
            db.add(row)
            db.commit()
        finally:
            db.close()
    except SQLAlchemyError:
        logger.exception("Failed to persist LLM log to database")


def _wrap_llm_invoke(base_invoke, provider: str, model: str):
    async def _logged_invoke(prompt: str) -> str:
        call_id = uuid.uuid4().hex[:8]
        prompt_value = prompt or ""
        logger.info(
            "LLM request id=%s provider=%s model=%s prompt_len=%d",
            call_id,
            provider,
            model,
            len(prompt_value),
        )
        start = time.perf_counter()
        try:
            response = await base_invoke(prompt)
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.exception(
                "LLM error id=%s provider=%s model=%s elapsed_ms=%d",
                call_id,
                provider,
                model,
                elapsed_ms,
            )
            _persist_llm_log(
                call_id=call_id,
                provider=provider,
                model=model,
                prompt=prompt_value,
                response=None,
                status="error",
                elapsed_ms=elapsed_ms,
                error_message=str(exc),
            )
            raise
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        response_value = response or ""
        logger.info(
            "LLM response id=%s provider=%s model=%s elapsed_ms=%d resp_len=%d",
            call_id,
            provider,
            model,
            elapsed_ms,
            len(response_value),
        )
        _persist_llm_log(
            call_id=call_id,
            provider=provider,
            model=model,
            prompt=prompt_value,
            response=response_value,
            status="success",
            elapsed_ms=elapsed_ms,
            error_message=None,
        )
        return response

    return _logged_invoke


def _get_llm_invoke():
    global _invoke_fn
    if _invoke_fn is not None:
        return _invoke_fn
    provider = (settings.llm_provider or "anthropic").lower()
    if provider == "ollama":
        import httpx

        base_url = settings.ollama_base_url or "http://localhost:11434"
        model = settings.ollama_model or "llama3"

        async def _ollama_invoke(prompt: str) -> str:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{base_url.rstrip('/')}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                    timeout=120.0,
                )
                if r.status_code != 200:
                    raise RuntimeError(f"Ollama error: {r.text}")
                return r.json().get("response") or ""

        _invoke_fn = _wrap_llm_invoke(_ollama_invoke, "ollama", model)
        logger.info(
            "LLM provider initialized: Ollama model=%s baseUrl=%s", model, base_url
        )
    elif provider == "openai":
        if settings.openai_api_key:
            from openai import AsyncOpenAI  # type: ignore[import-untyped]

            kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
            if settings.openai_base_url:
                kwargs["base_url"] = settings.openai_base_url
            client = AsyncOpenAI(**kwargs)
            model = settings.openai_model or "gpt-4o-mini"

            async def _openai_invoke(prompt: str) -> str:
                resp = await client.chat.completions.create(
                    model=model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
                choice = resp.choices[0] if resp.choices else None
                if choice and choice.message and choice.message.content:
                    return choice.message.content
                return ""

            _invoke_fn = _wrap_llm_invoke(_openai_invoke, "openai", model)
            base_msg = (
                f" base_url={settings.openai_base_url}" if settings.openai_base_url
                else ""
            )
            logger.info(
                "LLM provider initialized: OpenAI model=%s%s", model, base_msg
            )
        else:
            logger.error(
                "OPENAI_API_KEY not set and provider is openai; "
                "no LLM will be used."
            )
            _invoke_fn = None
    else:
        if settings.anthropic_api_key:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            model = settings.anthropic_model or "claude-3-5-sonnet-20241022"

            async def _anthropic_invoke(prompt: str) -> str:
                msg = await client.messages.create(
                    model=model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text if msg.content else ""

            _invoke_fn = _wrap_llm_invoke(_anthropic_invoke, "anthropic", model)
            logger.info("LLM provider initialized: Anthropic model=%s", model)
        else:
            logger.error(
                "ANTHROPIC_API_KEY not set and provider is anthropic; no LLM will be used."
            )
            _invoke_fn = None
    return _invoke_fn


def _extract_json(text: str) -> dict | None:
    """
    Best-effort extraction of a JSON object from an LLM response.

    Handles cases where the model wraps JSON in markdown fences or
    adds explanatory prose before/after the JSON block.
    """
    if not text:
        return None

    # Strip markdown-style code fences to reduce noise.
    cleaned = re.sub(r"```[a-zA-Z]*", "", text)
    cleaned = cleaned.replace("```", "")

    m = re.search(r"\{[\s\S]*\}", cleaned)
    if m:
        snippet = m.group(0)
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            pass
    return None


def _normalize_analysis(parsed: dict | None) -> dict:
    """
    Normalize raw parsed analysis into a safe structure:
    - Always returns dict with 'risks' and 'opportunities' lists.
    - Drops entries without at least a title and description.
    - Normalizes severity and type fields to known enum values.
    """
    risks: list[dict] = []
    opportunities: list[dict] = []
    dropped_risks = 0
    dropped_opps = 0

    if isinstance(parsed, dict):
        raw_risks = parsed.get("risks") or []
        raw_opps = parsed.get("opportunities") or []

        if isinstance(raw_risks, list):
            for item in raw_risks:
                if not isinstance(item, dict):
                    dropped_risks += 1
                    continue
                title = (item.get("title") or "").strip()
                desc = (item.get("description") or "").strip()
                if not title or not desc:
                    dropped_risks += 1
                    continue
                sev = item.get("severity") or RiskSeverity.MEDIUM.value
                if isinstance(sev, RiskSeverity):
                    item["severity"] = sev.value
                elif isinstance(sev, str):
                    try:
                        item["severity"] = RiskSeverity(sev.lower()).value
                    except ValueError:
                        item["severity"] = RiskSeverity.MEDIUM.value
                else:
                    item["severity"] = RiskSeverity.MEDIUM.value
                risks.append(item)

        if isinstance(raw_opps, list):
            for item in raw_opps:
                if not isinstance(item, dict):
                    dropped_opps += 1
                    continue
                title = (item.get("title") or "").strip()
                desc = (item.get("description") or "").strip()
                if not title or not desc:
                    dropped_opps += 1
                    continue
                t = item.get("type") or OpportunityType.COST_SAVING.value
                if isinstance(t, OpportunityType):
                    item["type"] = t.value
                elif isinstance(t, str):
                    try:
                        item["type"] = OpportunityType(t.lower()).value
                    except ValueError:
                        item["type"] = OpportunityType.COST_SAVING.value
                else:
                    item["type"] = OpportunityType.COST_SAVING.value
                opportunities.append(item)

    if dropped_risks or dropped_opps:
        logger.info(
            "normalize_analysis: dropped malformed items (risks=%d, opportunities=%d)",
            dropped_risks,
            dropped_opps,
        )
    logger.info(
        "normalize_analysis: %d risks, %d opportunities after cleaning",
        len(risks),
        len(opportunities),
    )
    return {"risks": risks, "opportunities": opportunities}


async def analyze_data(
    all_data: dict[str, list[dict]], scope: OemScope | None = None
) -> dict[str, list]:
    risks = []
    opportunities = []
    invoke = _get_llm_invoke()
    logger.info(
        "analyze_data: starting for %d source types (scope_oem=%s)",
        len(all_data),
        getattr(scope, "get", lambda *_: None)("oemName") if scope else None,
    )
    for source_type, data_array in all_data.items():
        logger.info(
            "analyze_data: source=%s items=%d",
            source_type,
            len(data_array),
        )
        if not data_array:
            continue

        # Combine all raw items for this source type into a single payload so we
        # only need ONE LLM call per (OEM, source_type) instead of per item.
        combined_items: list[dict] = []
        for data_item in data_array:
            payload = (
                data_item.get("data") if isinstance(data_item, dict) else data_item
            )
            if not payload:
                payload = data_item
            combined_items.append(payload)

        combined_payload: dict[str, Any] = {
            "items": combined_items,
            "itemCount": len(combined_items),
        }

        analysis = await _analyze_data_item(
            source_type,
            combined_payload,
            scope,
            invoke,
        )

        # Store the original fetched data as sourceData, annotated as combined.
        source_meta = {
            "combined": True,
            "itemCount": len(data_array),
            "items": data_array,
        }

        if analysis.get("risks"):
            for r in analysis["risks"]:
                r["sourceType"] = source_type
                r["sourceData"] = source_meta
                risks.append(r)
        if analysis.get("opportunities"):
            for o in analysis["opportunities"]:
                o["sourceType"] = source_type
                o["sourceData"] = source_meta
                opportunities.append(o)
    logger.info(
        "analyze_data: completed with %d risks, %d opportunities",
        len(risks),
        len(opportunities),
    )
    return {"risks": risks, "opportunities": opportunities}


async def analyze_global_risk(news_data: dict[str, list]) -> dict[str, list]:
    risks = []
    invoke = _get_llm_invoke()
    combined_items: list[dict] = []
    raw_items: list = []
    for source_type, data_array in news_data.items():
        for data_item in data_array:
            payload = (
                data_item.get("data") if isinstance(data_item, dict) else data_item
            )
            if not payload:
                payload = data_item
            combined_items.append(payload)
            raw_items.append(data_item)
    if not combined_items:
        logger.info("analyze_global_risk: no items; skipping")
        return {"risks": risks}
    logger.info(
        "analyze_global_risk: batch analyzing %d items (1 LLM call)",
        len(combined_items),
    )
    combined_payload: dict[str, Any] = {
        "items": combined_items,
        "itemCount": len(combined_items),
    }
    analysis = await _analyze_item_risks_only(
        "global_news", combined_payload, "global_risk", invoke
    )
    source_meta = {
        "combined": True,
        "itemCount": len(raw_items),
        "items": raw_items,
    }
    for r in analysis.get("risks") or []:
        r["sourceType"] = "global_news"
        r["sourceData"] = source_meta
        risks.append(r)
    logger.info("analyze_global_risk: completed with %d risks", len(risks))
    return {"risks": risks}


async def analyze_shipping_disruptions(route_data: dict[str, list]) -> dict[str, list]:
    risks = []
    invoke = _get_llm_invoke()
    combined_items: list[dict] = []
    raw_items: list = []
    for source_type, data_array in route_data.items():
        for data_item in data_array:
            payload = (
                data_item.get("data") if isinstance(data_item, dict) else data_item
            )
            if not payload:
                payload = data_item
            combined_items.append(payload)
            raw_items.append(data_item)
    if not combined_items:
        logger.info("analyze_shipping_disruptions: no items; skipping")
        return {"risks": risks}
    logger.info(
        "analyze_shipping_disruptions: batch analyzing %d items (1 LLM call)",
        len(combined_items),
    )
    combined_payload: dict[str, Any] = {
        "items": combined_items,
        "itemCount": len(combined_items),
    }
    analysis = await _analyze_item_risks_only(
        "shipping", combined_payload, "shipping_routes", invoke
    )
    source_meta = {
        "combined": True,
        "itemCount": len(raw_items),
        "items": raw_items,
    }
    for r in analysis.get("risks") or []:
        r["sourceType"] = "shipping"
        r["sourceData"] = source_meta
        risks.append(r)
    logger.info(
        "analyze_shipping_disruptions: completed with %d risks",
        len(risks),
    )
    return {"risks": risks}


async def _analyze_data_item(
    source_type: str, data_item: dict, scope: OemScope | None, invoke
) -> dict:
    if not invoke:
        logger.warning(
            "_analyze_data_item: no LLM invoke configured; returning empty analysis "
            "for source=%s",
            source_type,
        )
        return {"risks": [], "opportunities": []}
    try:
        prompt = _build_analysis_prompt(source_type, data_item, scope)
        content = await invoke(prompt)
        parsed = _extract_json(content)
        normalized = _normalize_analysis(parsed)
        if normalized["risks"] or normalized["opportunities"]:
            logger.info(
                "_analyze_data_item: source=%s produced %d risks, %d opps",
                source_type,
                len(normalized["risks"]),
                len(normalized["opportunities"]),
            )
            return normalized
        logger.info(
            "_analyze_data_item: source=%s produced no valid items; returning empty",
            source_type,
        )
    except Exception as e:
        logger.exception("analyzeDataItem error: %s", e)
    return {"risks": [], "opportunities": []}


def _build_analysis_prompt(
    source_type: str, data_item: dict, scope: OemScope | None
) -> str:
    scope_ctx = ""
    if scope:
        scope_ctx = f"""
You are analyzing data for OEM: "{scope["oemName"]}".
Relevant suppliers: {", ".join(scope.get("supplierNames") or ["None"])}.
Relevant locations: {", ".join((scope.get("cities") or []) + (scope.get("regions") or []) + (scope.get("countries") or [])) or "None"}.
Relevant commodities: {", ".join(scope.get("commodities") or ["None"])}.
Only report risks and opportunities relevant to this OEM's supply chain.
"""
    return f"""You are a supply chain risk intelligence agent. Analyze the following {source_type} data and identify:
1. Potential risks (severity: low, medium, high, critical)
2. Potential opportunities for optimization or cost savings
{scope_ctx}

Data:
{json.dumps(data_item, indent=2)}

Return ONLY a valid JSON object:
{{
  "risks": [
    {{ "title": "...", "description": "...", "severity": "low|medium|high|critical", "affectedRegion": "...", "affectedSupplier": "Single supplier name or array of supplier names", "estimatedImpact": "...", "estimatedCost": 0 }}
  ],
  "opportunities": [
    {{ "title": "...", "description": "...", "type": "cost_saving|time_saving|quality_improvement|market_expansion|supplier_diversification", "affectedRegion": "...", "potentialBenefit": "...", "estimatedValue": 0 }}
  ]
}}
If none found, return empty arrays. Be specific and actionable."""


async def _analyze_item_risks_only(
    source_type: str, data_item: dict, context: str, invoke
) -> dict:
    if not invoke:
        logger.warning(
            "_analyze_item_risks_only: no LLM invoke configured; returning empty "
            "for context=%s source=%s",
            context,
            source_type,
        )
        return {"risks": []}
    try:
        if context == "global_risk":
            prompt = _build_global_risk_prompt(data_item)
        else:
            prompt = _build_shipping_disruption_prompt(data_item)
        content = await invoke(prompt)
        parsed = _extract_json(content)
        normalized = _normalize_analysis(parsed)
        if normalized["risks"]:
            logger.info(
                "_analyze_item_risks_only: context=%s source=%s risks=%d",
                context,
                source_type,
                len(normalized["risks"]),
            )
            return {"risks": normalized["risks"]}
        logger.info(
            "_analyze_item_risks_only: context=%s source=%s no valid risks; returning empty",
            context,
            source_type,
        )
    except Exception as e:
        logger.exception("analyzeItemRisksOnly error: %s", e)
    return {"risks": []}


def _build_global_risk_prompt(data_item: dict) -> str:
    batch_note = ""
    if isinstance(data_item, dict) and "items" in data_item:
        batch_note = (
            'The data below contains multiple news items (an "items" array). '
            "Assess all of them and return risks for any that indicate "
            "material global supply chain risk.\n\n"
        )
    return f"""You are a global supply chain risk analyst. Assess the following for GLOBAL supply chain risk (geopolitical, trade, raw materials, pandemics, climate, logistics).

{batch_note}Data:
{json.dumps(data_item, indent=2)}

Return ONLY a valid JSON object:
{{ "risks": [ {{ "title": "...", "description": "...", "severity": "low|medium|high|critical", "affectedRegion": "...", "affectedSupplier": null, "estimatedImpact": "...", "estimatedCost": 0 }} ] }}
If no material risks, return {{ "risks": [] }}. Be concise."""


def _build_shipping_disruption_prompt(data_item: dict) -> str:
    batch_note = ""
    if isinstance(data_item, dict) and "items" in data_item:
        batch_note = (
            "The data below contains multiple route/transport items. "
            "Assess all of them and return risks for any that indicate "
            "disruption or delay.\n\n"
        )
    return f"""You are a shipping and logistics risk analyst. Analyze the following route/transport data for supply chain disruption risks.

{batch_note}Data:
{json.dumps(data_item, indent=2)}

Return ONLY a valid JSON object:
{{ "risks": [ {{ "title": "...", "description": "...", "severity": "low|medium|high|critical", "affectedRegion": "...", "affectedSupplier": null, "estimatedImpact": "...", "estimatedCost": 0 }} ] }}
If no risks, return {{ "risks": [] }}. Be specific to shipping and logistics."""


async def generate_mitigation_plan(risk: dict) -> dict:
    invoke = _get_llm_invoke()
    if not invoke:
        logger.warning(
            "generate_mitigation_plan: no LLM invoke configured; returning empty plan "
            "for risk=%s",
            risk.get("title"),
        )
        return {}
    try:
        prompt = f"""Generate a detailed mitigation plan for this supply chain risk:
Title: {risk.get("title")}
Description: {risk.get("description")}
Severity: {risk.get("severity")}
Affected Region: {risk.get("affectedRegion") or "N/A"}
Affected Supplier: {risk.get("affectedSupplier") or "N/A"}

Return ONLY a valid JSON object:
{{ "title": "...", "description": "...", "actions": ["Action 1", "Action 2"], "metadata": {{}}, "assignedTo": "...", "dueDate": "YYYY-MM-DD" }}"""
        content = await invoke(prompt)
        parsed = _extract_json(content)
        if parsed:
            return parsed
    except Exception as e:
        logger.exception("generateMitigationPlan error: %s", e)
    return {}


async def generate_combined_mitigation_plan(
    supplier_name: str, risks: list[dict]
) -> dict:
    invoke = _get_llm_invoke()
    if not invoke:
        logger.warning(
            "generate_combined_mitigation_plan: no LLM invoke configured; "
            "returning empty plan for supplier=%s",
            supplier_name,
        )
        return {}
    try:
        risk_summaries = "\n".join(
            f"- {r.get('title')} ({r.get('severity')}): {r.get('description', '')} Region: {r.get('affectedRegion', 'N/A')}"
            for r in risks
        )
        prompt = f"""You are a supply chain risk manager. Create ONE combined mitigation plan for SUPPLIER addressing ALL listed risks.

Supplier: {supplier_name}

Risks affecting this supplier:
{risk_summaries}

Return ONLY a valid JSON object:
{{ "title": "Combined Mitigation Plan: [Supplier Name]", "description": "...", "actions": ["Action 1", "Action 2"], "metadata": {{ "supplierName": "{supplier_name}", "riskCount": {len(risks)} }}, "assignedTo": "Supply Chain / Procurement Team", "dueDate": "YYYY-MM-DD" }}
Prioritize highest-severity risks first. Be specific and actionable."""
        content = await invoke(prompt)
        parsed = _extract_json(content)
        if parsed:
            parsed.setdefault("metadata", {})
            parsed["metadata"]["combinedForSupplier"] = supplier_name
            parsed["metadata"]["riskIds"] = [
                str(r.get("id")) for r in risks if r.get("id")
            ]
            return parsed
    except Exception as e:
        logger.exception("generateCombinedMitigationPlan error: %s", e)
    return {}


async def generate_opportunity_plan(opportunity: dict) -> dict:
    invoke = _get_llm_invoke()
    if not invoke:
        logger.warning(
            "generate_opportunity_plan: no LLM invoke configured; returning empty "
            "plan for opportunity=%s",
            opportunity.get("title"),
        )
        return {}
    try:
        prompt = f"""Generate an action plan to capitalize on this supply chain opportunity:
Title: {opportunity.get("title")}
Description: {opportunity.get("description")}
Type: {opportunity.get("type")}
Potential Benefit: {opportunity.get("potentialBenefit") or "N/A"}

Return ONLY a valid JSON object:
{{ "title": "...", "description": "...", "actions": ["Action 1", "Action 2"], "metadata": {{}}, "assignedTo": "...", "dueDate": "YYYY-MM-DD" }}"""
        content = await invoke(prompt)
        parsed = _extract_json(content)
        if parsed:
            return parsed
    except Exception as e:
        logger.exception("generateOpportunityPlan error: %s", e)
    return {}
