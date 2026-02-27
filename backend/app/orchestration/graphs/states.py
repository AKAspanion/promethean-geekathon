from typing import TypedDict

from app.services.agent_types import OemScope


class SupplierRiskState(TypedDict, total=False):
    """
    State for SupplierRiskGraph.

    Pure analysis state — no DB references. Accepts raw fetched data from
    each data source and produces merged risk lists + a unified score.
    """

    supplier_scope: OemScope

    # Raw data injected before graph invocation (keyed the same way the
    # agent runner functions expect them).
    raw_weather_data: dict   # {"weather": [...]}
    raw_news_data: dict      # {"news": [...]}  — supplier context
    raw_global_news_data: dict  # {"news": [...]}  — global context
    raw_shipping_data: dict  # {"shipping": [...]}

    # Per-domain agent outputs (populated by run_agents node)
    weather_risks: list[dict]
    weather_opportunities: list[dict]
    news_supplier_risks: list[dict]
    news_supplier_opportunities: list[dict]
    news_global_risks: list[dict]
    shipping_risks: list[dict]

    # Merged outputs (populated by merge_and_score node)
    all_risks: list[dict]
    all_opportunities: list[dict]

    # Scoring (populated by merge_and_score node)
    domain_scores: dict   # {"weather": float, "news": float, "shipping": float}
    unified_score: float  # 0–100
    risk_level: str       # LOW | MEDIUM | HIGH | CRITICAL


class SupplierRiskResult(TypedDict):
    """
    Serialisable result produced by SupplierRiskGraph for one supplier.
    Accumulated in OemOrchestrationState.supplier_results.
    """

    supplier_scope: OemScope
    all_risks: list[dict]
    all_opportunities: list[dict]
    domain_scores: dict
    unified_score: float
    risk_level: str


class SupplierWorkflowContext(TypedDict):
    """
    Bundles everything the OemOrchestrationGraph needs for one supplier run:
    the scope plus the pre-created DB record IDs so the graph can update
    them without touching the outer trigger loop.
    """

    scope: OemScope
    workflow_run_id: str
    agent_status_id: str


class OemOrchestrationState(TypedDict, total=False):
    """
    State for OemOrchestrationGraph.

    Processes every supplier for one OEM sequentially (safe for a single
    shared SQLAlchemy session) then aggregates an OEM-level risk score,
    generates mitigation plans, and broadcasts the final snapshot.
    """

    oem_id: str

    # Supplier contexts are consumed one at a time via a conditional loop.
    remaining_contexts: list[SupplierWorkflowContext]
    processed_contexts: list[SupplierWorkflowContext]

    # Accumulated per-supplier results (appended in process_next_supplier).
    supplier_results: list[SupplierRiskResult]

    # Set by aggregate_oem_score.
    oem_risk_score: float
    oem_risk_level: str

    # Set by generate_plans.
    plans_generated: int
