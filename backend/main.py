import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import Base, engine

# Import all models so they are registered with Base.metadata before create_all
import app.models  # noqa: F401

from app.api.routes import (
    app_routes,
    oems,
    risks,
    opportunities,
    mitigation_plans,
    suppliers,
    agent,
    ws,
    weather_agent,
    shipping_suppliers,
    shipping_risk,
    shipping_tracking,
    trend_insights,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Suppress SQL echo/logging (engine already has echo=False)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# Ensure DB tables exist for SQLAlchemy models (non-blocking: app can run without DB for weather-agent etc.)
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    logger.warning(
        "Database not available (tables not created): %s. "
        "Set DATABASE_URL or db_* env vars and ensure PostgreSQL is running. "
        "Weather-agent and other stateless routes will still work.",
        e,
    )


def _scheduled_trend_insights_job():
    if not settings.trend_agent_enabled:
        return
    from app.database import SessionLocal
    from app.services.trend_orchestrator import run_trend_insights_cycle
    db = SessionLocal()
    try:
        logger.info("Scheduled trend-insights cycle starting…")
        run_trend_insights_cycle(db)
        logger.info("Scheduled trend-insights cycle complete.")
    except Exception as e:
        logger.exception("Scheduled trend-insights cycle failed: %s", e)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Optional: trend-insights scheduler when trend_agent_enabled is True
    scheduler = None
    if settings.trend_agent_enabled:
        scheduler = BackgroundScheduler()
        interval = max(1, settings.trend_agent_interval_minutes)
        scheduler.add_job(
            _scheduled_trend_insights_job,
            "interval",
            minutes=interval,
            id="trend_insights_cycle",
        )
        scheduler.start()
        logger.info(
            "Trend-insights scheduler started (interval=%d minutes)", interval
        )
    # Seed OEMs, suppliers, and shipping data if empty
    try:
        from app.seed import seed_all_if_empty
        seed_all_if_empty()
    except Exception as e:
        logger.warning("Seed skipped (non-fatal): %s", e)
    yield
    if scheduler:
        scheduler.shutdown()


app = FastAPI(
    title="Predictive Supply Chain Agent API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(app_routes.router)
app.include_router(oems.router)
app.include_router(risks.router)
app.include_router(opportunities.router)
app.include_router(mitigation_plans.router)
app.include_router(suppliers.router)
app.include_router(agent.router)
app.include_router(weather_agent.router)
app.include_router(ws.router)
app.include_router(shipping_suppliers.router)
app.include_router(shipping_risk.router)
app.include_router(shipping_tracking.router)
app.include_router(trend_insights.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.env == "development",
    )
