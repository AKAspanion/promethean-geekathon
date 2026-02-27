from datetime import datetime
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def root():
    return "Predictive Supply Chain Agent API"


@router.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
