from datetime import date

from project_alpha.event_provenance import (
    DistributionEvidence,
    EvidenceKind,
    EvidenceLevel,
    audit_distribution_evidence,
)


def item(day, amount, level, *, kind=EvidenceKind.ACTUAL_DISTRIBUTION):
    return DistributionEvidence(
        ex_date=day,
        cash_dividend=amount,
        source_url="https://www.sitca.org.tw/FundNote/filing.pdf",
        level=level,
        kind=kind,
    )


def test_secondary_complete_history_still_cannot_promote():
    day = date(2026, 7, 21)
    audit = audit_distribution_evidence(
        {day: 0.27},
        [item(day, 0.27, EvidenceLevel.SECONDARY_AGGREGATOR)],
    )
    assert audit.evidenced_events == 1
    assert audit.primary_events == 0
    assert audit.paper_eligible is False


def test_matching_primary_history_is_eligible():
    day = date(2026, 7, 21)
    audit = audit_distribution_evidence(
        {day: 0.27},
        [item(day, 0.27, EvidenceLevel.PRIMARY_REGULATORY_FILING)],
    )
    assert audit.paper_eligible is True


def test_conflicting_primary_amount_is_rejected():
    day = date(2026, 7, 21)
    audit = audit_distribution_evidence(
        {day: 0.27},
        [item(day, 0.26, EvidenceLevel.PRIMARY_REGULATORY_FILING)],
    )
    assert audit.conflicting_dates == ("2026-07-21",)
    assert audit.paper_eligible is False


def test_estimate_only_document_cannot_count_as_actual_distribution():
    day = date(2026, 7, 21)
    audit = audit_distribution_evidence(
        {day: 0.27},
        [
            item(
                day,
                0.27,
                EvidenceLevel.PRIMARY_REGULATORY_FILING,
                kind=EvidenceKind.ESTIMATE_ONLY,
            )
        ],
    )
    assert audit.evidenced_events == 1
    assert audit.primary_events == 0
    assert audit.estimate_only_dates == ("2026-07-21",)
    assert audit.paper_eligible is False


def test_arbitrary_hostname_cannot_claim_primary_status():
    day = date(2026, 7, 21)
    try:
        DistributionEvidence(
            ex_date=day,
            cash_dividend=0.27,
            source_url="https://example.test/official-looking.pdf",
            level=EvidenceLevel.PRIMARY_REGULATORY_FILING,
        )
    except ValueError as error:
        assert "approved official source hostname" in str(error)
    else:
        raise AssertionError("unapproved hostname was accepted as primary evidence")
