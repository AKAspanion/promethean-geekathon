# Application Architecture

High-level architecture of the **Predictive Supply Chain Agent**: backend (FastAPI), frontend (Next.js), and how they interact.

---

## Overview

- **Backend**: FastAPI (Python). REST API, WebSocket, PostgreSQL, pluggable data sources, and LLM-based agents for risk/opportunity/mitigation.
- **Frontend**: Next.js 16 (App Router), React 19, TanStack Query, TailwindCSS. Consumes REST + WebSocket for real-time dashboards.
- **Auth**: Email-only OEM login; JWT scopes all data to an OEM.

---

## Backend

### Stack

| Layer | Technology |
|-------|------------|
| Framework | FastAPI |
| DB | PostgreSQL + SQLAlchemy 2 (declarative models, sync sessions) |
| Config | pydantic-settings from `.env` (`app/config.py`) |
| LLM | Anthropic / Ollama / OpenAI-compatible (selected via `LLM_PROVIDER`) |
| Async | uvicorn ASGI; async route handlers where needed |

### Directory layout

```
backend/
├── main.py                 # FastAPI app, CORS, lifespan (scheduler, seed), route includes
├── ensure_db.py            # Create PostgreSQL DB if missing (uses config)
├── start.sh                # Venv + deps + ensure_db + uvicorn
├── requirements.txt
├── .env.example
└── app/
    ├── config.py           # Settings (env-backed); single `settings` instance
    ├── database.py         # Engine, SessionLocal, get_db, Base
    ├── seed.py             # Seed OEMs/suppliers/shipping data if empty
    ├── api/
    │   ├── deps.py         # JWT create/verify, get_current_oem, get_db
    │   └── routes/         # Route modules
    │       ├── app_routes.py
    │       ├── oems.py
    │       ├── risks.py
    │       ├── opportunities.py
    │       ├── mitigation_plans.py
    │       ├── suppliers.py
    │       ├── agent.py            # GET status, POST trigger
    │       ├── ws.py               # WebSocket (agent status, supplier snapshots)
    │       ├── weather_agent.py
    │       ├── shipping_suppliers.py
    │       ├── shipping_risk.py
    │       ├── shipping_tracking.py
    │       └── trend_insights.py
    ├── models/             # SQLAlchemy models (see DB-ARCHITECTURE.md)
    ├── schemas/            # Pydantic request/response schemas
    ├── services/           # Business logic
    │   ├── agent_orchestrator.py   # Main agent: data sources → LLM → risks/opportunities/plans
    │   ├── llm_client.py           # LLM client (Anthropic/Ollama/OpenAI)
    │   ├── langchain_llm.py        # LangChain chat model (agent use)
    │   ├── weather_service.py
    │   ├── trend_orchestrator.py
    │   ├── shipping_agent.py
    │   ├── shipping_risk.py
    │   ├── risks.py, opportunities.py, mitigation_plans.py
    │   ├── oems.py, suppliers.py
    │   ├── websocket_manager.py
    │   └── ...
    ├── agents/             # Agent-specific logic (weather, news, shipment, etc.)
    ├── data/               # Data source implementations (weather, news, traffic, market, shipping, trends)
    ├── core/               # Shared core (e.g. risk_engine)
    └── orchestration/      # Orchestration (e.g. agent_service)
```

### Key flows

1. **OEM login**: Frontend sends email → backend finds or creates OEM → returns JWT. All subsequent requests send JWT; `deps.get_current_oem` scopes access.
2. **Suppliers**: CSV upload at `/suppliers/upload` creates suppliers for the current OEM. These define the supply network for the agent.
3. **Trigger analysis**: `POST /agent/trigger` starts a run for the current OEM: build scope (OEM + suppliers), fetch data (weather, news, traffic, market, shipping), run LLM orchestrator to produce risks, opportunities, and mitigation plans; persist and update risk scores.
4. **Real-time updates**: Backend pushes agent status and supplier snapshots over WebSocket; frontend subscribes and TanStack Query keeps UI in sync.

### Configuration

All backend configuration is in `app/config.py`, loaded from environment (`.env`). See [SETUP.md](SETUP.md) for every variable.

---

## Frontend

### Stack

| Layer | Technology |
|-------|------------|
| Framework | Next.js 16 (App Router) |
| UI | React 19, TailwindCSS 4 |
| Data / state | TanStack Query (server state), React state for local UI |
| HTTP | Axios or fetch; base URL from `NEXT_PUBLIC_API_URL` |
| Realtime | WebSocket to same API base URL |

### Directory layout

```
frontend/
├── app/
│   ├── layout.tsx              # Root layout
│   ├── login/page.tsx         # Email-only login
│   ├── suppliers/              # Suppliers list + upload; supplier detail
│   │   ├── page.tsx
│   │   └── [id]/page.tsx
│   └── (app)/                  # Authenticated app group
│       ├── layout.tsx          # App shell (nav, header)
│       ├── page.tsx            # Dashboard (agent status, risks, opportunities, plans)
│       ├── weather-risk/page.tsx
│       ├── news-risk/page.tsx
│       └── shipping-risk/page.tsx
├── components/                 # Reusable UI
│   ├── AppHeader.tsx
│   ├── AppNav.tsx
│   ├── AgentStatus.tsx
│   ├── RisksList.tsx
│   ├── OpportunitiesList.tsx
│   ├── MitigationPlansList.tsx
│   ├── ShippingRiskDashboard.tsx
│   ├── ShipmentTimeline.tsx
│   ├── ShipmentExposureSummary.tsx
│   ├── SuppliersList.tsx
│   └── ...
├── lib/
│   ├── api.ts                  # API client (base URL from NEXT_PUBLIC_API_URL)
│   ├── constants.ts
│   ├── providers.tsx           # TanStack Query + theme providers
│   └── theme-context.tsx
├── hooks/
│   └── useWebSocketNotifications.ts   # WebSocket to backend for live updates
├── .env.example                # NEXT_PUBLIC_API_URL
└── public/
```

### Data flow

- **Auth**: Login page posts email → receives JWT → stored (e.g. in memory or storage); API client sends JWT on every request.
- **REST**: TanStack Query fetches risks, opportunities, mitigation plans, agent status, suppliers, shipping data from backend REST endpoints.
- **WebSocket**: One hook connects to the backend WebSocket; backend broadcasts agent status and supplier snapshots; frontend updates query cache or state so the dashboard updates in real time without polling.

---

## API surface (summary)

- **Auth**: OEM login (email → JWT).
- **OEMs**: Resolve/create by email.
- **Suppliers**: CRUD + CSV upload; scoped by OEM.
- **Agent**: `GET /agent/status`, `POST /agent/trigger`.
- **Risks / Opportunities / Mitigation plans**: CRUD + filters; scoped by OEM.
- **Weather / Shipping / Trend insights**: Dedicated routes and agents.
- **WebSocket**: Single endpoint for live agent and supplier updates.

See root [README.md](../README.md) for a concise endpoint list.

---

## Documentation cross-references

- [SETUP.md](SETUP.md) – Environment variables and setup for backend and frontend.
- [DB-ARCHITECTURE.md](DB-ARCHITECTURE.md) – PostgreSQL schema and entity relationships.
