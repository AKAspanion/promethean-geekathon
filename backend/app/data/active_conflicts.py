"""
Structured geopolitical conflict data for supplier risk.

Maps countries involved in active conflicts (e.g. Operation Epic Fury / US–Iran–Israel)
to reasons. Used to inject critical risks when a supplier's country matches,
so risk score and swarm analysis reflect exposure. Countries are matched
semantically (e.g. "US", "USA", "United States" all match).
"""

from __future__ import annotations

import logging
from typing import TypedDict

logger = logging.getLogger(__name__)


class ConflictEntry(TypedDict):
    Country: str
    Reason: str


# Canonical conflict list (Operation Epic Fury / US–Iran–Israel regional escalation).
# Update this list when the conflict set changes.
ACTIVE_CONFLICT_ENTRIES: list[ConflictEntry] = [
    {
        "Country": "United States",
        "Reason": "Primary initiator of 'Operation Epic Fury' strikes against Iran; U.S. military bases in the region are currently being targeted by Iranian counter-strikes.",
    },
    {
        "Country": "Israel",
        "Reason": "Conducted joint strikes with the U.S. against Iranian military infrastructure; currently the target of retaliatory missile and drone attacks from Iran.",
    },
    {
        "Country": "Iran",
        "Reason": "Primary target of the joint U.S.-Israel military operation; currently engaging in retaliatory strikes against Israel and U.S. military facilities across the Middle East.",
    },
    {
        "Country": "Bahrain",
        "Reason": "Hosts the U.S. Navy's Fifth Fleet; reported to be a target of Iranian retaliatory strikes.",
    },
    {
        "Country": "Kuwait",
        "Reason": "Hosts U.S. military installations; reported to be a target of Iranian retaliatory strikes and drone activity.",
    },
    {
        "Country": "Qatar",
        "Reason": "Hosts major U.S. military presence (e.g., Al Udeid Airbase); reported to be a target of Iranian retaliatory strikes.",
    },
    {
        "Country": "United Arab Emirates",
        "Reason": "Hosts U.S. military facilities; reported casualties from shrapnel and targets of Iranian missile strikes.",
    },
    {
        "Country": "Saudi Arabia",
        "Reason": "Reported to be a target of Iranian retaliatory missile strikes.",
    },
    {
        "Country": "Iraq",
        "Reason": "Reported as a location for missile strikes involving pro-Iran groups and US-linked military bases.",
    },
    {
        "Country": "Syria",
        "Reason": "Reports of defensive military activity and strikes associated with the regional escalation.",
    },
]

# Canonical country name -> aliases for semantic matching (lowercase).
# Used to match scope "countries" (e.g. "US", "USA") and "regions" to conflict entries.
CONFLICT_COUNTRY_ALIASES: dict[str, list[str]] = {
    "United States": ["united states", "usa", "us", "u.s.", "u.s.a.", "america", "united states of america"],
    "Israel": ["israel", "il", "israeli"],
    "Iran": ["iran", "ir", "iranian"],
    "Bahrain": ["bahrain", "bh", "bahraini"],
    "Kuwait": ["kuwait", "kw", "kuwaiti"],
    "Qatar": ["qatar", "qa", "qatari"],
    "United Arab Emirates": ["united arab emirates", "uae", "emirates", "dubai", "abu dhabi", "ae"],
    "Saudi Arabia": ["saudi arabia", "saudi", "sa", "ksa"],
    "Iraq": ["iraq", "iq", "iraqi"],
    "Syria": ["syria", "syrian", "sy"],
}


def _normalize_for_match(s: str) -> str:
    return (s or "").strip().lower()


def _country_matches_entry(scope_value: str, canonical: str, aliases: list[str]) -> bool:
    """Return True if scope_value (e.g. from scope['countries']) matches this conflict country."""
    n = _normalize_for_match(scope_value)
    if not n:
        return False
    if _normalize_for_match(canonical) == n:
        return True
    return any(n == _normalize_for_match(a) for a in aliases)


def get_conflict_risks_for_supplier(
    countries: list[str] | None = None,
    regions: list[str] | None = None,
    supplier_name: str | None = None,
) -> list[dict]:
    """
    Return a list of risk dicts (critical severity) for each conflict country
    that matches the supplier's countries or regions. Used to increase risk
    score and surface in swarm topDrivers when supplier is in an affected country.

    Each risk has: title, description, severity "critical", affectedRegion,
    sourceType "geopolitical", sourceData { "risk_type": "war", "context": "active_conflict" }.
    """
    countries = countries or []
    regions = regions or []
    # Build a single set of tokens to match (country names and region names)
    scope_tokens: list[str] = []
    for c in countries:
        if c and str(c).strip():
            scope_tokens.append(str(c).strip())
    for r in regions:
        if r and str(r).strip():
            scope_tokens.append(str(r).strip())

    if not scope_tokens:
        return []

    out: list[dict] = []
    for entry in ACTIVE_CONFLICT_ENTRIES:
        canonical = entry["Country"]
        reason = entry["Reason"]
        aliases = CONFLICT_COUNTRY_ALIASES.get(canonical, [canonical.lower()])
        for token in scope_tokens:
            if _country_matches_entry(token, canonical, aliases):
                title = f"Active conflict exposure: {canonical}"
                description = (
                    f"Supplier is in or linked to {canonical}. {reason} "
                    "This is treated as a critical supply chain risk and should be reflected in swarm analysis and risk score."
                )
                out.append({
                    "title": title,
                    "description": description,
                    "severity": "critical",
                    "affectedRegion": canonical,
                    "affectedSupplier": supplier_name,
                    "estimatedImpact": None,
                    "estimatedCost": None,
                    "sourceType": "geopolitical",
                    "sourceData": {
                        "risk_type": "war",
                        "context": "active_conflict",
                        "canonical_country": canonical,
                    },
                })
                break  # one risk per matching conflict country
    if out:
        logger.info(
            "active_conflicts: supplier %s matched %d conflict countries → %d critical risks",
            supplier_name or "?",
            len(out),
            len(out),
        )
    return out
