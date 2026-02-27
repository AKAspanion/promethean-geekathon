# Supply Chain Agent API (FastAPI)

Backend API for the Predictive Supply Chain Agent system built with NestJS, LangGraph, LangChain, and PostgreSQL.

## Requirements

- **Python 3.11 or 3.12** (3.14 may fail on `pydantic-core` build)
- PostgreSQL (same DB as Node backend)
- Optional: `ANTHROPIC_API_KEY` or Ollama for LLM analysis; `WEATHER_API_KEY`, `NEWS_API_KEY` for live data

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with DB and API keys
```

## Run

```bash
# From backend/ with venv activated
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Default port is **8000** (Node backend uses 3001). Health: `GET http://localhost:8000/health`.

## API

- **Public:** `POST /oems/register`, `POST /oems/login`, `GET /`, `GET /health`
- **Protected (Bearer JWT):** all other routes under `/risks`, `/opportunities`, `/mitigation-plans`, `/suppliers`, `/agent`

Same request/response shapes as the Node backend; JWT from `/oems/login` works for both backends.

## Scheduler

Agent analysis runs every 5 minutes (all OEMs), same as Node `@Cron(CronExpression.EVERY_5_MINUTES)`.
