from datetime import date

from project_alpha.mitake import MitakeDailyBar
from project_alpha.paper_audit import build_batch_audit, file_evidence
from project_alpha.paper_daily import PaperAction


def bar(day):
    return MitakeDailyBar(day, 1.0, 1.0, 1.0, 1.0, 1)


def test_file_evidence_changes_with_content(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("first", encoding="utf-8")
    first = file_evidence(path)
    path.write_text("second", encoding="utf-8")
    second = file_evidence(path)
    assert first.sha256 != second.sha256
    assert first.byte_count == 5
    assert second.byte_count == 6


def test_batch_audit_links_sources_and_ledger_hashes(tmp_path):
    paths = []
    for index in range(4):
        path = tmp_path / f"source-{index}.txt"
        path.write_text(str(index), encoding="utf-8")
        paths.append(path)
    day = date(2026, 7, 29)
    audit = build_batch_audit(
        candidate_id="candidate",
        prior_ledger_hash="1" * 64,
        new_ledger_hash="2" * 64,
        observation_count_before=1,
        observation_count_after=2,
        appended_dates=(day,),
        primary_export_path=paths[0],
        defensive_export_path=paths[1],
        primary_actions_path=paths[2],
        defensive_actions_path=paths[3],
        primary_bars=(bar(day),),
        defensive_bars=(bar(day),),
        primary_actions={day: PaperAction(1.0, 0.0)},
        defensive_actions={day: PaperAction(1.0, 0.0)},
    )
    assert audit["prior_ledger_hash"] == "1" * 64
    assert audit["new_ledger_hash"] == "2" * 64
    assert audit["appended_dates"] == ["2026-07-29"]
    assert audit["inputs"]["primary_export"]["byte_count"] == 1
    assert audit["safety"]["orders_placed"] is False
