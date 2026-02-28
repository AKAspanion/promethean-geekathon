# Weather Agent Architecture

## Overview

The weather agent is a **LangGraph-based workflow** that analyzes weather exposure for shipments along a supplier-to-OEM transit route. It combines:

- Real-time and historical weather data from **WeatherAPI.com**
- Shipment route data from a mock tracking server
- Risk scoring via the internal `compute_risk()` engine
- Optional LLM executive summaries
- WebSocket progress broadcasting
- Database persistence of risks and opportunities

---

## Trigger Paths

### Path 1 — Risk Analysis Pipeline (primary)

The weather agent runs per-supplier, in parallel with news and shipping agents:

```python
# risk_analysis_graph.py:811
supplier_result, global_result, weather_result, shipping_result = await asyncio.gather(
    run_news_agent_graph(scope, "supplier"),
    run_news_agent_graph(scope, "global"),
    run_weather_graph(scope),          # ← weather agent
    run_shipment_risk_graph(scope),
)
```

The results are then normalized and persisted to the database as `Risk` and `Opportunity` rows.

### Path 2 — Direct REST API

```
POST /api/v1/shipment/weather-exposure
Body: { "supplier_id": "<UUID>" }
```

Returns the raw `{ risks[], opportunities[], daily_timeline[] }` payload without DB persistence.

---

## LangGraph Pipeline

The weather graph is a **linear 5-node pipeline**:

```
START
  │
  ▼
[1] resolve_cities         DB lookup + mock tracking API
  │
  ▼
[2] fetch_forecasts        Parallel WeatherAPI calls for all route cities
  │
  ▼
[3] build_daily_timeline   Day-by-day weather fetch + risk scoring
  │
  ▼
[4] build_exposure_risks   Convert timeline → risk/opportunity dicts
  │
  ▼
[5] llm_summary            Optional LLM executive briefing
  │
  ▼
 END
```

---

## Node Details

### Node 1 — `resolve_cities` (`weather.py:401`)

Resolves the supplier and OEM cities, and fetches the actual shipment route.

**What it does:**
- Queries the database for OEM and Supplier city fields
- Calls the mock shipment tracking API to get the actual route plan (waypoints, transport modes, dates)
- Extracts `transit_days` and `pickup_date` from the tracking response
- Falls back to `DEFAULT_TRANSIT_DAYS = 7` and today's date if tracking fails

**External call:**
```
GET {MOCK_SERVER_BASE_URL}/mock/shipment-tracking?q=supplier_id:{id}
```

**State outputs:**
```
supplier_city, oem_city, oem_name, supplier_name,
transit_days, shipment_start_date, route_plan[]
```

---

### Node 2 — `fetch_forecasts` (`weather.py:554`)

Fetches weather forecasts for every city on the route in parallel.

**What it does:**
- Collects all unique cities: supplier + OEM + all route waypoints
- Determines forecast window (today → shipment end date, capped at 14 days)
- Fires async parallel requests for all cities via `asyncio.gather()`

**External call:**
```
GET https://api.weatherapi.com/v1/forecast.json
    ?key=WEATHER_API_KEY&q={city}&days=1-14&aqi=no&alerts=yes
```

**State outputs:**
```
supplier_forecast, oem_forecast, route_city_forecasts{ city → forecast_json }
```

---

### Node 3 — `build_daily_timeline` (`weather.py:633`)

Builds a day-by-day weather + risk snapshot across the full transit window.

**For each day 1..transit_days:**

1. **Determine location** — from route_plan waypoints, or interpolated fallback
2. **Fetch weather** for that day:
   - Today → `GET /current.json` (live conditions)
   - Past days → `GET /history.json?dt=YYYY-MM-DD` (historical)
   - Future days → use pre-fetched forecast from Node 2
   - Beyond 14 days → reuse last forecast day, flagged `is_estimated: true`
3. **Score risk** via `compute_risk(weather_dict)` across 5 dimensions
4. **Build `DayRiskSnapshot`** for the day

**Aggregated into `exposure_payload`:**
- `average_risk_score`, `peak_risk_score`, `peak_risk_day`
- `high_risk_day_count`, `high_risk_dates[]`
- `overall_exposure_score = 50% × peak + 50% × average`
- `risk_factors_max{ transportation, power_outage, production, port_and_route, raw_material_delay }`
- `primary_concerns[]`, `recommended_actions[]`
- `daily_timeline[]` — full per-day records

**State outputs:**
```
day_results[], exposure_payload{}
```

---

### Node 4 — `build_exposure_risks` (`weather.py:912`)

Converts the exposure payload into DB-ready risk and opportunity dicts.

**Severity mapping from `exposure_score`:**

| Score | Severity |
|-------|----------|
| ≥ 75  | critical |
| ≥ 50  | high     |
| ≥ 25  | moderate |
| < 25  | low      |

**Risk generation (when `exposure_score > 10`):**
- One route-level summary risk with dominant factor, peak day, high-risk count
- One risk per high/critical day with precise weather snapshot

**Opportunity generation (when `exposure_score ≤ 10`):**
- Type: `time_saving`
- Title: `"Favorable weather: {supplier_city} → {oem_city} route clear"`
- Suggests prioritizing high-value or time-sensitive shipments

> ⚠ **Known issue:** The `≤ 10` threshold is extremely strict. In practice, almost any real-world weather results in a score above 10, so opportunities are rarely generated from this agent.

**State outputs:**
```
weather_risks[], weather_opportunities[]
```

---

### Node 5 — `llm_summary` (`weather.py:1178`) — optional

Generates a short executive briefing from the exposure payload.

**What it does:**
- Formats `exposure_payload` as structured JSON context
- Calls LLM with strict instructions: cite exact numbers, no speculation, flag estimated data
- Produces a 3-5 sentence narrative
- Persists the LLM call log to the database

**State outputs:**
```
agent_summary (str | None)
```

---

## State Schema (`WeatherState`)

```python
class WeatherState(TypedDict, total=False):
    # Input
    scope: OemScope                          # oemId, supplierId, names

    # After Node 1
    supplier_city: str
    oem_city: str
    oem_name: str | None
    supplier_name: str | None
    transit_days: int
    shipment_start_date: str                 # YYYY-MM-DD
    route_plan: list[dict] | None            # Actual waypoints

    # After Node 2
    supplier_forecast: dict | None
    oem_forecast: dict | None
    route_city_forecasts: dict[str, dict]    # city → full forecast JSON

    # After Node 3
    day_results: list[dict]                  # DayRiskSnapshot per day
    exposure_payload: dict                   # Aggregated stats + daily timeline

    # After Node 4
    weather_risks: list[dict]               # DB-ready risk dicts
    weather_opportunities: list[dict]       # DB-ready opportunity dicts

    # After Node 5
    agent_summary: str | None               # LLM briefing
```

---

## External APIs

### WeatherAPI.com

| Endpoint | When used |
|----------|-----------|
| `/v1/forecast.json` | Node 2 (all cities, parallel) + Node 3 (retry if missing) |
| `/v1/current.json`  | Node 3 — today only |
| `/v1/history.json`  | Node 3 — past dates |

Config: `settings.weather_api_key` (env var `WEATHER_API_KEY`)

### Mock Shipment Tracking Server

```
GET {MOCK_SERVER_BASE_URL}/mock/shipment-tracking?q=supplier_id:{id}
```

Returns route plan with waypoints, transport modes, planned/actual arrival dates, and shipment metadata.

Config: `settings.mock_server_base_url` (env var `MOCK_SERVER_BASE_URL`)

---

## Risk Scoring — `compute_risk()`

**Input:** weather dict with condition, temp_c, wind_kph, precip_mm, snow_cm, vis_km, humidity, uv, pressure_mb

**Output per day:**
```
{
  score: 0–100,
  level: low | moderate | high | critical,
  factors: {
    transportation:      float,   # wind, visibility, precipitation
    power_outage:        float,   # storms, temperature extremes
    production:          float,   # humidity, UV
    port_and_route:      float,   # precip, snow, wind
    raw_material_delay:  float,   # combined adverse conditions
  }
}
```

**Overall exposure score formula:**
```
overall_exposure_score = (peak_score × 0.5) + (average_score × 0.5)
```

---

## Data Flow

```
OemScope (oemId + supplierId)
        │
        ▼
   resolve_cities
   ├── DB: OEM city, Supplier city
   └── Mock API: route_plan, transit_days, pickup_date
        │
        ▼
   fetch_forecasts
   └── WeatherAPI: forecast for each route city (parallel)
        │
        ▼
   build_daily_timeline
   ├── WeatherAPI: current / history / forecast per day
   ├── compute_risk() → score + 5 risk factors per day
   └── Aggregate → exposure_payload
        │
        ▼
   build_exposure_risks
   ├── exposure_score > 10  → weather_risks[]
   └── exposure_score ≤ 10  → weather_opportunities[]
        │
        ▼
   llm_summary (optional)
   └── LLM → agent_summary
        │
   ┌────┴────────────────────┐
   │                         │
   ▼                         ▼
PATH 1 (orchestration)   PATH 2 (REST API)
Normalize + persist      Return JSON response
to DB as Risk /          to frontend
Opportunity rows
```

---

## WebSocket Events

At each node, progress is broadcast via `_broadcast_progress()`:

| Event | Fired at |
|-------|----------|
| `cities_resolved` | End of Node 1 |
| `forecasts_fetched` | End of Node 2 |
| `timeline_built` | End of Node 3 |
| `exposure_risks_built` | End of Node 4 |
| `agent_done` | After graph completes |

---

## Frontend — `weather-risk` page

**File:** `frontend/app/(app)/weather-risk/page.tsx`

**Flow:** Select supplier → `POST /api/v1/shipment/weather-exposure` → render `ShipmentExposureSummary`

**Component tree:**

```
ShipmentExposureSummary
├── ExposureOverview        route, score, peak risk, key metrics
├── ShipmentTimeline        day grid with risk colour strip + clickable day cards
│    └── DayRiskModal       weather stats + 5 risk factor breakdown + concerns
├── RiskFactorsMax          bar chart of max score per dimension
├── DayRiskTimeline         detailed cards for high/critical days only
├── RiskItem[]              expandable list of all risk dicts
├── OpportunityItem[]       favorable condition cards
└── RawJsonPanel            full JSON response (copyable)
```

---

## Known Issues

| Issue | Location | Details |
|-------|----------|---------|
| Opportunities threshold too strict | `weather.py:960` | Opportunities only generated when `exposure_score ≤ 10`. In practice almost never fires since any real-world weather pushes score above 10. |
| Global news never generates opportunities | `news.py:491` | Global news prompt hardcodes `"opportunities": []`. |
| No seeded opportunities | `seed.py` | DB starts empty; opportunities only appear after a successful full agent run. |

---

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/agents/weather.py` | Full weather agent — graph nodes, state, entrypoint |
| `backend/app/api/routes/weather_agent.py` | REST API route (`POST /shipment/weather-exposure`) |
| `backend/app/orchestration/graphs/risk_analysis_graph.py` | Calls `run_weather_graph()` in the main pipeline |
| `backend/app/core/risk_engine.py` | `compute_risk()` — weather → risk score |
| `backend/app/config.py` | `weather_api_key`, `mock_server_base_url` |
| `frontend/app/(app)/weather-risk/page.tsx` | Weather risk page |
