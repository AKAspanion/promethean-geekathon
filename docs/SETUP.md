# Setup Guide

This guide covers everything required to run the **Predictive Supply Chain Agent** backend and frontend locally.

---

## Prerequisites

### Backend

| Requirement | Version / Notes |
|-------------|-----------------|
| **Python** | 3.11 or 3.12 recommended. **3.14 is not supported** (pydantic-core). Use `python3.11` or `python3.12`. |
| **PostgreSQL** | 14+ (used for all persistent data). |
| **pip** | For installing Python dependencies. |

Optional for full functionality:

- **Ollama** (local LLM): if using `LLM_PROVIDER=ollama`, install and run [Ollama](https://ollama.ai) (e.g. `ollama run llama3`).
- **Anthropic API key**: for `LLM_PROVIDER=anthropic`.
- **OpenAI-compatible API**: for `LLM_PROVIDER=openai` or Shipping Risk Intelligence agent.
- **OpenWeatherMap API key**: for real weather data (otherwise mock).
- **NewsAPI key**: for real news (otherwise mock).

### Frontend

| Requirement | Version / Notes |
|-------------|-----------------|
| **Node.js** | 20+ |
| **Package manager** | npm or yarn |

---

## Backend Setup

### 1. Clone and enter backend

```bash
cd backend
```

### 2. Environment variables

```bash
cp .env.example .env
```

Edit `.env` with your values. All keys are documented below.

#### Database

| Variable | Required | Description |
|----------|----------|-------------|
| `DB_HOST` | Yes* | PostgreSQL host (default: `localhost`). |
| `DB_PORT` | Yes* | Port (default: `5432`). |
| `DB_USERNAME` | Yes* | DB user. |
| `DB_PASSWORD` | Yes* | DB password. |
| `DB_NAME` | Yes* | Database name (default: `supply_chain`). |
| `DATABASE_URL` | No | Full URL; if set, overrides `DB_*` (e.g. `postgresql://user:pass@host:5432/dbname`). |

\*Required for DB features; app can start without DB for stateless routes (e.g. weather agent).

#### LLM provider

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_PROVIDER` | No | `anthropic` \| `ollama` \| `openai` (default: `anthropic`). |

**When `LLM_PROVIDER=anthropic`:**

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key. |
| `ANTHROPIC_MODEL` | No | Model name (default: `claude-3-5-sonnet-20241022`). |

**When `LLM_PROVIDER=ollama`:**

| Variable | Required | Description |
|----------|----------|-------------|
| `OLLAMA_BASE_URL` | No | Base URL (default: `http://localhost:11434`). |
| `OLLAMA_MODEL` | No | Model (default: `llama3`). |

**When `LLM_PROVIDER=openai` (or for Shipping Risk agent):**

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes* | OpenAI or compatible API key. |
| `OPENAI_BASE_URL` | No | Custom base URL for compatible APIs. |
| `OPENAI_MODEL` | No | Model (default: `gpt-4o-mini`). |

#### External APIs (optional; mock used if unset)

| Variable | Required | Description |
|----------|----------|-------------|
| `WEATHER_API_KEY` | No | OpenWeatherMap API key. |
| `WEATHER_DAYS_FORECAST` | No | Forecast days (default: `3`). |
| `NEWS_API_KEY` | No | NewsAPI key. |

#### JWT (OEM login)

| Variable | Required | Description |
|----------|----------|-------------|
| `JWT_SECRET` | Yes | Secret for signing tokens; **change in production**. |
| `JWT_ALGORITHM` | No | Algorithm (default: `HS256`). |
| `JWT_EXPIRE_DAYS` | No | Token expiry in days (default: `7`). |

#### Trend insights agent (scheduled)

| Variable | Required | Description |
|----------|----------|-------------|
| `TREND_AGENT_ENABLED` | No | Set to `true` to run scheduled trend insights. |
| `TREND_AGENT_INTERVAL_MINUTES` | No | Interval in minutes (default: `60`). |
| `TREND_AGENT_EXCEL_PATH` | No | Path to Excel file for trend input. |

#### Application

| Variable | Required | Description |
|----------|----------|-------------|
| `PORT` | No | API port (default: `8000`). |
| `ENV` | No | `development` \| `production` (affects reload, etc.). |
| `FRONTEND_URL` | No | Allowed CORS origin (default: `http://localhost:3000`). |

### 3. Create database (if using PostgreSQL)

Ensure PostgreSQL is running, then create the application database if it does not exist. If you use **Option B** (manual run), activate your virtualenv first so `python` can import the app and psycopg2:

```bash
# If using manual setup (Option B), activate venv first:
# source .venv/bin/activate
python ensure_db.py
```

This uses `DATABASE_URL` or `DB_*` from `.env`. Non-fatal if DB already exists or if you skip DB. **Option A** (`./start.sh`) runs this for you.

### 4. Install dependencies and run

**Option A – start script (recommended)**

```bash
./start.sh
```

This script:

- Finds a compatible Python (3.11/3.12/3.13, not 3.14).
- Creates `.venv` if missing.
- Installs `requirements.txt` if needed.
- Runs `ensure_db.py`.
- Starts uvicorn with reload on `http://0.0.0.0:8000` (or `PORT` from env).

**Option B – manual**

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Backend is available at **http://localhost:8000**. API docs: http://localhost:8000/docs.

---

## Frontend Setup

### 1. Enter frontend

```bash
cd frontend
```

### 2. Environment variables

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | No | Backend base URL (default: `http://localhost:8000`). Used for REST and WebSocket. |

Ensure this matches the URL where the backend is running (including port).

### 3. Install and run

```bash
yarn install
yarn dev
```

Frontend runs at **http://localhost:3000**.

---

## Running both together

1. Start **backend** first (e.g. `cd backend && ./start.sh`).
2. Start **frontend** (e.g. `cd frontend && yarn dev`).
3. Open http://localhost:3000 and log in with an email (OEM login).

---

## Troubleshooting

- **Database connection failed**: Check `DB_*` or `DATABASE_URL`, and that PostgreSQL is running. Run `ensure_db.py` to create the DB.
- **Python 3.14**: Use 3.11 or 3.12. Remove `.venv` and run `./start.sh` again after installing a supported Python.
- **CORS errors**: Set `FRONTEND_URL` in backend `.env` to your frontend origin (e.g. `http://localhost:3000`).
- **API unreachable from frontend**: Confirm `NEXT_PUBLIC_API_URL` in `frontend/.env` matches the backend URL and that the backend is running.
