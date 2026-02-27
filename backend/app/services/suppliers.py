from uuid import UUID
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.supplier import Supplier
from app.models.risk import Risk, RiskSeverity, RiskStatus


def _parse_csv_line(line: str) -> list[str]:
    result = []
    current = ""
    in_quotes = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "," and not in_quotes:
            result.append(current.strip())
            current = ""
        else:
            current += ch
    result.append(current.strip())
    return result


def _normalize_header(h: str) -> str:
    return h.strip().lower().replace(" ", "_")


def upload_csv(
    db: Session, oem_id: UUID, content: bytes, filename: str = "upload.csv"
) -> dict:
    text = content.decode("utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return {
            "created": 0,
            "errors": [
                "CSV must have a header row and at least one data row.",
            ],
        }

    headers = _parse_csv_line(lines[0])
    header_index: Dict[str, int] = {}
    for i, h in enumerate(headers):
        key = _normalize_header(h)
        if key not in header_index:
            header_index[key] = i

    name_idx = (
        header_index.get("name")
        or header_index.get("supplier_name")
        or header_index.get("supplier")
        or 0
    )
    errors = []
    created = 0

    for row_num in range(1, len(lines)):
        values = _parse_csv_line(lines[row_num])
        if len(values) < 1 or not values[name_idx]:
            continue

        metadata = {}
        name = ""
        location = city = country = region = commodities = None

        for i, header in enumerate(headers):
            key = _normalize_header(header)
            value = values[i] if i < len(values) else ""
            if key in ("name", "supplier_name", "supplier"):
                name = value
            elif key in ("location", "address"):
                location = value or None
            elif key == "city":
                city = value or None
            elif key == "country":
                country = value or None
            elif key == "region":
                region = value or None
            elif key in ("commodities", "commodity"):
                commodities = value or None
            else:
                metadata[header.strip()] = value

        if not name:
            errors.append(f"Row {row_num + 1}: missing name.")
            continue

        try:
            supp = Supplier(
                oemId=oem_id,
                name=name,
                location=location,
                city=city,
                country=country,
                countryCode=country,
                region=region,
                commodities=commodities,
                metadata_=metadata if metadata else None,
            )
            db.add(supp)
            db.commit()
            created += 1
        except Exception as e:
            db.rollback()
            errors.append(f"Row {row_num + 1}: {e}")

    return {"created": created, "errors": errors}


def get_all(db: Session, oem_id: UUID) -> list[Supplier]:
    return (
        db.query(Supplier)
        .filter(Supplier.oemId == oem_id)
        .order_by(Supplier.createdAt.desc())
        .all()
    )


def get_by_id(db: Session, supplier_id: UUID) -> Supplier | None:
    return db.query(Supplier).filter(Supplier.id == supplier_id).first()


def get_one(db: Session, id: UUID, oem_id: UUID) -> Supplier | None:
    return (
        db.query(Supplier).filter(Supplier.id == id, Supplier.oemId == oem_id).first()
    )


def update_one(
    db: Session,
    id: UUID,
    oem_id: UUID,
    data: dict,
) -> Supplier | None:
    supplier = get_one(db, id, oem_id)
    if not supplier:
        return None
    allowed = {"name", "location", "city", "country", "region", "commodities"}
    for key, value in data.items():
        if key in allowed:
            setattr(supplier, key, value)
    db.commit()
    db.refresh(supplier)
    return supplier


def delete_one(db: Session, id: UUID, oem_id: UUID) -> bool:
    supplier = get_one(db, id, oem_id)
    if not supplier:
        return False
    db.delete(supplier)
    db.commit()
    return True


def get_risks_by_supplier(db: Session) -> dict:
    """
    Lightweight aggregation used by the existing UI to show simple counts.
    """
    risks = (
        db.query(
            Risk.id,
            Risk.title,
            Risk.severity,
            Risk.affectedSupplier,
            Risk.affectedSuppliers,
            Risk.createdAt,
        )
        .order_by(Risk.createdAt.desc())
        .all()
    )
    out: Dict[str, dict] = {}
    for r in risks:
        # Support multiple suppliers per risk; fall back to single label.
        names: list[str] = []
        if getattr(r, "affectedSuppliers", None):
            names = [
                (str(n).strip()) for n in (r.affectedSuppliers or []) if str(n).strip()
            ]
        elif r.affectedSupplier:
            names = [r.affectedSupplier.strip()]
        for key in names:
            if not key:
                continue
            if key not in out:
                out[key] = {"count": 0, "bySeverity": {}, "latest": None}
            out[key]["count"] += 1
            sev = str(r.severity.value if hasattr(r.severity, "value") else r.severity)
            out[key]["bySeverity"][sev] = out[key]["bySeverity"].get(sev, 0) + 1
            if out[key]["latest"] is None:
                out[key]["latest"] = {
                    "id": str(r.id),
                    "severity": sev,
                    "title": r.title,
                }
    return out


SEVERITY_WEIGHT: Dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def _compute_agent_score(risks: List[Risk]) -> Tuple[float, Dict[str, int]]:
    """
    Collapse multiple risks for a single agent into a 0-100 score plus per-severity counts.
    """
    if not risks:
        return 0.0, {}
    severity_counts: Dict[str, int] = {}
    weighted_sum = 0
    for r in risks:
        sev_value = (
            getattr(
                r.severity,
                "value",
                r.severity,
            )
            or RiskSeverity.MEDIUM.value
        )
        sev = str(sev_value).lower()
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        weight = SEVERITY_WEIGHT.get(sev, SEVERITY_WEIGHT["medium"])
        weighted_sum += weight
    count = len(risks)
    avg = weighted_sum / count if count else 0
    score = min(100.0, round(avg * 25))
    return score, severity_counts


def _score_to_risk_level(score: float) -> str:
    if score <= 25:
        return "LOW"
    if score <= 50:
        return "MEDIUM"
    if score <= 75:
        return "HIGH"
    return "CRITICAL"


def _build_swarm_summary_for_supplier(risks: List[Risk]) -> Optional[dict]:
    """
    Build a Swarm Controller style summary for a given supplier from existing risks.

    Maps Risk.sourceType -> conceptual agent buckets (WEATHER, SHIPPING, NEWS)
    and then applies the weighted finalization formula from the PRD.
    """
    if not risks:
        return None

    # Partition risks by conceptual agent type based on their sourceType
    weather_risks: List[Risk] = []
    shipping_risks: List[Risk] = []
    news_risks: List[Risk] = []
    other_risks: List[Risk] = []

    for r in risks:
        if r.sourceType == "weather":
            weather_risks.append(r)
        elif r.sourceType in ("traffic", "shipping"):
            shipping_risks.append(r)
        elif r.sourceType in ("news", "global_news"):
            news_risks.append(r)
        else:
            other_risks.append(r)

    weather_score, weather_counts = _compute_agent_score(weather_risks)
    shipping_score, shipping_counts = _compute_agent_score(shipping_risks)
    news_score, news_counts = _compute_agent_score(news_risks)

    final_score = round(
        (weather_score * 0.4) + (shipping_score * 0.3) + (news_score * 0.3)
    )
    final_level = _score_to_risk_level(final_score)

    # Top drivers: take the most recent, highest-severity risk titles
    def _severity_weight(r: Risk) -> int:
        sev_value = (
            getattr(
                r.severity,
                "value",
                r.severity,
            )
            or RiskSeverity.MEDIUM.value
        )
        sev = str(sev_value).lower()
        return SEVERITY_WEIGHT.get(sev, SEVERITY_WEIGHT["medium"])

    sorted_risks = sorted(
        risks,
        key=lambda r: (_severity_weight(r), r.createdAt or 0),
        reverse=True,
    )
    top_drivers = [r.title for r in sorted_risks[:3]]

    # Simple rule-based mitigation suggestions aligned with PRD examples
    mitigation_plan: List[str] = []

    if _score_to_risk_level(weather_score) in ("HIGH", "CRITICAL"):
        mitigation_plan.append(
            "Increase safety stock near affected regions.",
        )
        mitigation_plan.append(
            "Identify alternate regional suppliers to bypass weather hotspots.",
        )

    if _score_to_risk_level(shipping_score) in ("HIGH", "CRITICAL"):
        mitigation_plan.append(
            "Shift part of volume to air freight for critical orders.",
        )
        mitigation_plan.append(
            "Re-route shipments via less congested ports or lanes.",
        )

    if _score_to_risk_level(news_score) in ("HIGH", "CRITICAL"):
        mitigation_plan.append(
            "Hedge commodity prices for exposed materials.",
        )
        mitigation_plan.append(
            "Activate backup or secondary suppliers in stable regions.",
        )

    # Fallback mitigation guidance if nothing specific triggered
    if not mitigation_plan and final_score > 0:
        mitigation_plan.append(
            "Review supplier exposure and validate business continuity plans.",
        )
        mitigation_plan.append(
            "Schedule a risk review with procurement and operations teams.",
        )

    # Agent-level summaries in AgentResult shape
    def _build_agent_result(
        agent_type: str,
        score: float,
        agent_risks: List[Risk],
        counts: Dict[str, int],
    ) -> dict:
        signals = [r.title for r in agent_risks[:5]]
        interpreted = [r.description for r in agent_risks[:5]]
        # Confidence is a simple heuristic: more corroborating risks → higher confidence
        confidence = min(1.0, 0.5 + 0.1 * len(agent_risks)) if agent_risks else 0.0
        return {
            "agentType": agent_type,
            "score": score,
            "riskLevel": _score_to_risk_level(score),
            "signals": signals,
            "interpretedRisks": interpreted,
            "confidence": confidence,
            "metadata": {
                "severityCounts": counts,
                "riskCount": len(agent_risks),
            },
        }

    agents: List[dict] = [
        _build_agent_result("WEATHER", weather_score, weather_risks, weather_counts),
        _build_agent_result(
            "SHIPPING", shipping_score, shipping_risks, shipping_counts
        ),
        _build_agent_result("NEWS", news_score, news_risks, news_counts),
    ]

    return {
        "finalScore": final_score,
        "riskLevel": final_level,
        "topDrivers": top_drivers,
        "mitigationPlan": mitigation_plan,
        "agents": agents,
    }


def get_swarm_summaries_by_supplier(
    db: Session, oem_id: Optional[UUID] = None
) -> Dict[str, dict]:
    """
    Compute Swarm Controller style outputs per supplier using existing Risk rows.

    The key is the supplier name (matching Risk.affectedSupplier and Supplier.name),
    because that is how risks are currently correlated to suppliers in the system.
    """
    q = db.query(Risk).filter(Risk.status == RiskStatus.DETECTED)
    if oem_id:
        q = q.filter(Risk.oemId == oem_id)
    risks = q.order_by(Risk.createdAt.desc()).all()

    grouped: Dict[str, List[Risk]] = {}
    for r in risks:
        names: list[str] = []
        if getattr(r, "affectedSuppliers", None):
            names = [
                (str(n).strip()) for n in (r.affectedSuppliers or []) if str(n).strip()
            ]
        elif r.affectedSupplier:
            names = [r.affectedSupplier.strip()]
        for key in names:
            if not key:
                continue
            grouped.setdefault(key, []).append(r)

    out: Dict[str, dict] = {}
    for supplier_name, supplier_risks in grouped.items():
        summary = _build_swarm_summary_for_supplier(supplier_risks)
        if summary:
            out[supplier_name] = summary
    return out
