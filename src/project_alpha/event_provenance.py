"""Evidence grading for corporate-action data used in promotion decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import IntEnum
import math
from typing import Iterable


class EvidenceLevel(IntEnum):
    SECONDARY_AGGREGATOR = 1
    ISSUER_ANNOUNCEMENT_MIRROR = 2
    PRIMARY_REGULATORY_FILING = 3


@dataclass(frozen=True)
class DistributionEvidence:
    ex_date: date
    cash_dividend: float
    source_url: str
    level: EvidenceLevel

    def __post_init__(self) -> None:
        if not math.isfinite(self.cash_dividend) or self.cash_dividend <= 0:
            raise ValueError("cash_dividend must be finite and positive")
        if not self.source_url.startswith("https://"):
            raise ValueError("source_url must be an HTTPS URL")


@dataclass(frozen=True)
class ProvenanceAudit:
    expected_events: int
    evidenced_events: int
    primary_events: int
    missing_dates: tuple[str, ...]
    conflicting_dates: tuple[str, ...]
    non_primary_dates: tuple[str, ...]

    @property
    def paper_eligible(self) -> bool:
        return (
            self.expected_events > 0
            and self.evidenced_events == self.expected_events
            and self.primary_events == self.expected_events
            and not self.missing_dates
            and not self.conflicting_dates
            and not self.non_primary_dates
        )


def audit_distribution_evidence(
    expected: dict[date, float],
    evidence: Iterable[DistributionEvidence],
) -> ProvenanceAudit:
    """Require one matching primary filing for every expected distribution."""
    if not expected:
        raise ValueError("expected distribution manifest cannot be empty")
    if any(not math.isfinite(value) or value <= 0 for value in expected.values()):
        raise ValueError("expected distributions must be finite and positive")

    by_date: dict[date, list[DistributionEvidence]] = {}
    for item in evidence:
        by_date.setdefault(item.ex_date, []).append(item)

    missing: list[str] = []
    conflicts: list[str] = []
    non_primary: list[str] = []
    primary = 0
    evidenced = 0
    for event_date, expected_amount in sorted(expected.items()):
        items = by_date.get(event_date, [])
        matching = [
            item
            for item in items
            if math.isclose(item.cash_dividend, expected_amount, abs_tol=1e-12)
        ]
        if not items:
            missing.append(event_date.isoformat())
            continue
        if not matching:
            conflicts.append(event_date.isoformat())
            continue
        evidenced += 1
        if any(item.level == EvidenceLevel.PRIMARY_REGULATORY_FILING for item in matching):
            primary += 1
        else:
            non_primary.append(event_date.isoformat())

    return ProvenanceAudit(
        expected_events=len(expected),
        evidenced_events=evidenced,
        primary_events=primary,
        missing_dates=tuple(missing),
        conflicting_dates=tuple(conflicts),
        non_primary_dates=tuple(non_primary),
    )
