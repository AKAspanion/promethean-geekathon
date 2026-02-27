from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TrendInsightResponse(BaseModel):
    id: UUID
    scope: str
    entity_name: str | None
    risk_opportunity: str
    title: str
    description: str | None
    predicted_impact: str | None
    time_horizon: str | None
    severity: str | None
    recommended_actions: list[str] | None
    source_articles: list[str] | None
    confidence: float | None
    oem_name: str | None
    llm_provider: str | None
    createdAt: datetime

    model_config = {"from_attributes": True}


class TrendInsightRunResponse(BaseModel):
    message: str
    insights_generated: int
    oem_name: str
    llm_provider: str
    insights: list[TrendInsightResponse]
