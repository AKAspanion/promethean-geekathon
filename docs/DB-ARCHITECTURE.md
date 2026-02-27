# Database Architecture

PostgreSQL schema and entity relationships for the **Predictive Supply Chain Agent** backend. All persistence is done via SQLAlchemy 2 (declarative models) in `backend/app/models/`.

---

## Technology

- **RDBMS**: PostgreSQL 14+
- **ORM**: SQLAlchemy 2 (sync engine, `SessionLocal`, `get_db` in FastAPI)
- **Connection**: From `app.config.settings` (`DATABASE_URL` or `DB_*`). Tables created on app startup via `Base.metadata.create_all(bind=engine)`.

---

## Entity relationship overview

- **OEM** is the tenant: one OEM has many **Suppliers**, **WorkflowRuns**, **AgentStatusEntity** rows, and **SupplyChainRiskScore**.
- **WorkflowRun** represents one full agent run for an OEM (optionally per supplier); **AgentStatusEntity** tracks live status for that run; **Risk**, **Opportunity**, **MitigationPlan**, **SupplierRiskAnalysis**, **SupplyChainRiskScore** are produced by the run.
- **Risk** and **Opportunity** can link to **Supplier** and **WorkflowRun**; **MitigationPlan** links to **Risk** or **Opportunity**.
- **ShippingSupplier** / **Shipment** / **ShippingRiskAssessment** form a separate shipping-intelligence subdomain (integer PKs).
- **TrendInsight**, **LlmLog**, **ExternalApiLog** are supporting/audit tables.

---

## Core domain (OEM-scoped)

### `oems`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| name | String | |
| email | String UNIQUE | Login identifier |
| location, city, country, countryCode, region | String (nullable) | |
| commodities | String (nullable) | Comma-separated |
| metadata | JSONB (nullable) | |
| createdAt, updatedAt | Timestamptz | |

### `suppliers`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| oemId | UUID FK → oems.id CASCADE | |
| name, location, city, country, countryCode, region, commodities | String (nullable) | |
| metadata | JSONB (nullable) | |
| latestRiskScore | Numeric(5,2) (nullable) | Latest supplier risk score |
| latestRiskLevel | String (nullable) | |
| createdAt, updatedAt | Timestamptz | |

**Relations**: `oem` → Oem; `risks` → Risk (cascade delete-orphan).

### `workflow_runs`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| oemId | UUID FK → oems.id CASCADE | |
| supplierId | UUID FK → suppliers.id SET NULL (nullable) | Optional per-supplier run |
| runDate | Date | Calendar date (UTC) |
| runIndex | Integer | Monotonic run index per OEM |
| metadata | JSONB (nullable) | |
| createdAt | Timestamptz | |

**Relations**: `oem` → Oem; `supplier` → Supplier.

### `agent_status`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| oemId | UUID FK → oems.id CASCADE (nullable) | |
| workflowRunId | UUID FK → workflow_runs.id SET NULL (nullable) | |
| supplierId | UUID FK → suppliers.id SET NULL (nullable) | |
| status | String | idle \| monitoring \| analyzing \| processing \| completed \| error |
| currentTask | Text (nullable) | |
| lastProcessedData | JSONB (nullable) | |
| lastDataSource | String (nullable) | |
| errorMessage | String (nullable) | |
| risksDetected, opportunitiesIdentified, plansGenerated | Integer | Counts |
| metadata | JSONB (nullable) | |
| lastUpdated, createdAt | Timestamptz | |

Tracks live and historical agent state per run/OEM/supplier.

### `risks`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| oemId | UUID (nullable) | Denormalized |
| workflowRunId | UUID FK → workflow_runs.id SET NULL (nullable) | |
| supplierId | UUID FK → suppliers.id SET NULL (nullable) | |
| agentStatusId | UUID FK → agent_status.id SET NULL (nullable) | |
| title | String | |
| description | Text | |
| severity | Enum | low \| medium \| high \| critical |
| status | Enum | detected \| analyzing \| mitigating \| resolved \| false_positive |
| sourceType | String | |
| sourceData | JSONB (nullable) | |
| affectedRegion, affectedSupplier | String (nullable) | |
| affectedSuppliers | JSONB (nullable) | List of names |
| impactDescription | Text (nullable) | |
| estimatedImpact, estimatedCost | String / Numeric (nullable) | |
| metadata | JSONB (nullable) | |
| createdAt, updatedAt | Timestamptz | |

**Relations**: `supplier` → Supplier; `mitigation_plans` → MitigationPlan (cascade delete-orphan).

### `opportunities`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| oemId | UUID (nullable) | |
| workflowRunId | UUID FK → workflow_runs.id SET NULL (nullable) | |
| supplierId | UUID FK → suppliers.id SET NULL (nullable) | |
| agentStatusId | UUID FK → agent_status.id SET NULL (nullable) | |
| title | String | |
| description | Text | |
| type | Enum | cost_saving \| time_saving \| quality_improvement \| market_expansion \| supplier_diversification |
| status | Enum | identified \| evaluating \| implementing \| realized \| expired |
| sourceType | String | |
| sourceData | JSONB (nullable) | |
| affectedRegion, affectedSuppliers | String / JSONB (nullable) | |
| impactDescription | Text (nullable) | |
| potentialBenefit, estimatedValue | String / Numeric (nullable) | |
| metadata | JSONB (nullable) | |
| createdAt, updatedAt | Timestamptz | |

**Relations**: `mitigation_plans` → MitigationPlan (cascade delete-orphan).

### `mitigation_plans`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| title | String | |
| description | Text | |
| actions | ARRAY(Text) | Coerced from LLM list-of-dicts to list of strings |
| status | Enum | draft \| approved \| in_progress \| completed \| cancelled |
| riskId | UUID FK → risks.id (nullable) | |
| opportunityId | UUID FK → opportunities.id (nullable) | |
| agentStatusId | UUID FK → agent_status.id SET NULL (nullable) | |
| metadata | JSONB (nullable) | |
| assignedTo, dueDate | String / Date (nullable) | |
| createdAt, updatedAt | Timestamptz | |

**Relations**: `risk` → Risk; `opportunity` → Opportunity. Each plan is tied to either a risk or an opportunity.

### `supply_chain_risk_scores`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| oem_id | UUID | OEM reference |
| workflowRunId | UUID FK → workflow_runs.id SET NULL (nullable) | |
| overall_score | Numeric(5,2) | |
| breakdown | JSONB (nullable) | |
| severityCounts | JSONB (nullable) | |
| riskIds | String (nullable) | Comma-separated IDs |
| createdAt | Timestamptz | |

One overall risk score per run (and OEM).

### `supplier_risk_analysis`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| oemId | UUID FK → oems.id CASCADE | |
| workflowRunId | UUID FK → workflow_runs.id CASCADE | |
| supplierId | UUID FK → suppliers.id CASCADE (nullable) | |
| riskScore | Numeric(5,2) | |
| risks | JSONB (nullable) | Serialized risk summary |
| description | Text (nullable) | |
| metadata | JSONB (nullable) | |
| createdAt | Timestamptz | |

Per-supplier risk snapshot per workflow run.

---

## Shipping intelligence (separate subdomain)

Tables use integer PKs and snake_case columns.

### `shipping_suppliers`

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | |
| name | String(255) | |
| material_name | String(255) | |
| location_city, destination_city | String(255) | |
| latitude, longitude | Float (nullable) | |
| shipping_mode | String(50) | |
| distance_km, avg_transit_days | Float (nullable) | |
| historical_delay_percentage | Float (nullable) | |
| port_used | String (nullable) | |
| alternate_route_available, is_critical_supplier | Boolean | |
| created_at, updated_at | DateTime | |

**Relations**: `shipments` → Shipment; `risk_assessments` → ShippingRiskAssessment.

### `shipments`

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | |
| supplier_id | Integer FK → shipping_suppliers.id CASCADE | |
| awb_code | String(64) UNIQUE | |
| courier_name | String (nullable) | |
| origin_city, destination_city | String(255) | |
| pickup_date, expected_delivery_date, delivered_date | DateTime (nullable) | |
| current_status | String(100) | e.g. In Transit |
| weight, packages | Float / Integer (nullable) | |

**Relations**: `supplier` → ShippingSupplier.

### `shipping_risk_assessments`

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | |
| supplier_id | Integer FK → shipping_suppliers.id CASCADE | |
| shipping_risk_score | Float | |
| risk_level | String(50) | |
| delay_probability | Float | |
| delay_risk_score, stagnation_risk_score, velocity_risk_score | Float (nullable) | |
| risk_factors, recommended_actions | JSONB | |
| shipment_metadata | JSONB (nullable) | |
| assessed_at | DateTime | |

**Relations**: `supplier` → ShippingSupplier.

---

## Supporting / audit tables

### `trend_insights`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| scope | String | material \| supplier \| global |
| entity_name | String (nullable) | |
| risk_opportunity | String | risk \| opportunity |
| title | String | |
| description, predicted_impact | Text (nullable) | |
| time_horizon, severity | String (nullable) | |
| recommended_actions, source_articles | JSONB (nullable) | |
| confidence | Float (nullable) | |
| oem_name, excel_path, llm_provider | String (nullable) | Provenance |
| createdAt | Timestamptz | |

### `llm_logs`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| callId | String (indexed) | |
| provider, model | String | |
| prompt | Text | |
| response | Text (nullable) | |
| status | String | e.g. success |
| errorMessage | Text (nullable) | |
| elapsedMs | Integer (nullable) | |
| createdAt | Timestamptz | |

### `external_api_logs`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| service | String (nullable) | |
| method | String | e.g. GET |
| url | Text | |
| params | JSONB (nullable) | |
| statusCode | Integer (nullable) | |
| fromCache | Boolean | |
| elapsedMs | Integer (nullable) | |
| requestHeaders, responseBody | JSONB (nullable) | |
| errorMessage | Text (nullable) | |
| createdAt | Timestamptz | |

---

## Diagram (conceptual)

```
Oem 1──* Supplier
  │         │
  │         └──* Risk ──* MitigationPlan
  │
  ├──* WorkflowRun
  │       │
  │       ├──* AgentStatusEntity
  │       ├──* SupplyChainRiskScore
  │       └──* SupplierRiskAnalysis
  │
  └── (Opportunity ──* MitigationPlan)

ShippingSupplier 1──* Shipment
         │
         └──* ShippingRiskAssessment
```

---

## Creation and migrations

- **Creation**: Tables are created at startup via `Base.metadata.create_all(bind=engine)` in `main.py`. No migrations framework is used; schema changes require code/model updates and optional manual or scripted ALTERs.
- **Database bootstrap**: Run `ensure_db.py` to create the PostgreSQL database (named by `DB_NAME` or from `DATABASE_URL`) if it does not exist. Does not create tables; that is done by the app.

For a full list of model files and exports, see `backend/app/models/__init__.py`.
