import hashlib
import json
from datetime import date

import pytest

from project_alpha.action_verification import (
    build_action_verification,
    load_action_verification,
)


def write_proof(tmp_path, action_path, source_path, **overrides):
    payload = {
        "format_version": "action-verification-v2",
        "symbol": "0050",
        "verified_through": "2026-07-29",
        "action_file_sha256": hashlib.sha256(action_path.read_bytes()).hexdigest(),
        "source_file_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "source_url": "https://www.tpex.org.tw/openapi/v1/example",
    }
    payload.update(overrides)
    proof = tmp_path / "proof.json"
    proof.write_text(json.dumps(payload), encoding="utf-8")
    return proof


def test_verification_binds_symbol_hash_and_official_source(tmp_path):
    actions = tmp_path / "actions.csv"
    actions.write_text(
        "date,split_ratio,cash_dividend\n2026-07-21,1,0.6\n",
        encoding="utf-8",
    )
    source = tmp_path / "official.json"
    source.write_text("official", encoding="utf-8")
    proof = write_proof(tmp_path, actions, source)
    result = load_action_verification(
        proof,
        action_path=actions,
        source_path=source,
        expected_symbol="0050",
    )
    assert result.verified_through.isoformat() == "2026-07-29"


def test_modified_action_file_is_rejected(tmp_path):
    actions = tmp_path / "actions.csv"
    actions.write_text("original", encoding="utf-8")
    source = tmp_path / "official.json"
    source.write_text("official", encoding="utf-8")
    proof = write_proof(tmp_path, actions, source)
    actions.write_text("modified", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match action file"):
        load_action_verification(
            proof,
            action_path=actions,
            source_path=source,
            expected_symbol="0050",
        )


def test_nonofficial_source_is_rejected(tmp_path):
    actions = tmp_path / "actions.csv"
    actions.write_text("content", encoding="utf-8")
    source = tmp_path / "official.json"
    source.write_text("official", encoding="utf-8")
    proof = write_proof(
        tmp_path,
        actions,
        source,
        source_url="https://example.com/not-official",
    )
    with pytest.raises(ValueError, match="approved official"):
        load_action_verification(
            proof,
            action_path=actions,
            source_path=source,
            expected_symbol="0050",
        )


def test_builder_is_deterministic_and_hash_bound(tmp_path):
    actions = tmp_path / "actions.csv"
    actions.write_text("content", encoding="utf-8")
    source = tmp_path / "official.json"
    source.write_text("official", encoding="utf-8")
    first = build_action_verification(
        symbol="0050",
        verified_through=date(2026, 7, 29),
        action_path=actions,
        source_path=source,
        source_url="https://www.tpex.org.tw/openapi/v1/example",
    )
    second = build_action_verification(
        symbol="0050",
        verified_through=date(2026, 7, 29),
        action_path=actions,
        source_path=source,
        source_url="https://www.tpex.org.tw/openapi/v1/example",
    )
    assert first == second
    assert first["action_file_sha256"] == hashlib.sha256(
        actions.read_bytes()
    ).hexdigest()
    assert first["source_file_sha256"] == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()


def test_modified_official_source_file_is_rejected(tmp_path):
    actions = tmp_path / "actions.csv"
    actions.write_text("content", encoding="utf-8")
    source = tmp_path / "official.json"
    source.write_text("original", encoding="utf-8")
    proof = write_proof(tmp_path, actions, source)
    source.write_text("modified", encoding="utf-8")
    with pytest.raises(ValueError, match="official source file SHA-256"):
        load_action_verification(
            proof,
            action_path=actions,
            source_path=source,
            expected_symbol="0050",
        )
