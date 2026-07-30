import json
from pathlib import Path

import pytest

from project_alpha.paper_snapshot_io import (
    load_authenticated_paper_ledger,
    load_snapshot,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_published_snapshot_matches_current_ledger():
    ledger = load_authenticated_paper_ledger(
        PROJECT_ROOT / "research/preregistration.json",
        PROJECT_ROOT / "data/paper_observations.csv",
        PROJECT_ROOT / "research/paper_snapshot.json",
    )
    assert ledger.observations[-1].observed_on.isoformat() == "2026-07-29"


def test_tampered_snapshot_is_rejected(tmp_path):
    source = PROJECT_ROOT / "research/paper_snapshot.json"
    document = json.loads(source.read_text(encoding="utf-8"))
    document["ledger_hash"] = "0" * 64
    tampered = tmp_path / "paper_snapshot.json"
    tampered.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        load_authenticated_paper_ledger(
            PROJECT_ROOT / "research/preregistration.json",
            PROJECT_ROOT / "data/paper_observations.csv",
            tampered,
        )


def test_snapshot_schema_is_strict(tmp_path):
    path = tmp_path / "paper_snapshot.json"
    path.write_text('{"ledger_hash":"not enough"}', encoding="utf-8")
    with pytest.raises(ValueError, match="fields"):
        load_snapshot(path)
