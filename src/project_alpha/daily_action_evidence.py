"""Prepare one atomic daily package of official corporate-action evidence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import shutil
import tempfile

from project_alpha.action_schedule import verify_official_action_day
from project_alpha.action_verification import (
    ActionVerification,
    build_action_verification,
    load_action_verification,
    sha256_file,
)
from project_alpha.official_source import (
    OfficialSourceDownload,
    fetch_official_source,
)
from project_alpha.paper_daily import load_paper_actions


TWSE_ACTION_SCHEDULE_URL = (
    "https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL"
)
TPEX_ACTION_SCHEDULE_URL = (
    "https://www.tpex.org.tw/openapi/v1/tpex_exright_prepost"
)


@dataclass(frozen=True)
class DailyActionEvidence:
    verified_through: date
    primary_source_path: Path
    defensive_source_path: Path
    primary_verification_path: Path
    defensive_verification_path: Path
    primary_verification: ActionVerification
    defensive_verification: ActionVerification


def _write_bytes(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _write_json(path: Path, payload: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def prepare_daily_action_evidence(
    *,
    verified_through: date,
    primary_action_path: str | Path,
    defensive_action_path: str | Path,
    output_root: str | Path,
    fetcher: Callable[[str], OfficialSourceDownload] = fetch_official_source,
) -> Path:
    """Download, reconcile, and atomically publish both official proofs."""
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / verified_through.isoformat()
    if target.exists():
        raise FileExistsError(
            f"daily action evidence already exists: {target}"
        )
    primary_path = Path(primary_action_path)
    defensive_path = Path(defensive_action_path)
    primary_actions = load_paper_actions(primary_path)
    defensive_actions = load_paper_actions(defensive_path)
    temporary = Path(
        tempfile.mkdtemp(prefix=".action-evidence-", dir=root)
    )
    try:
        primary_download = fetcher(TWSE_ACTION_SCHEDULE_URL)
        defensive_download = fetcher(TPEX_ACTION_SCHEDULE_URL)
        primary_source = temporary / "0050_official_schedule.json"
        defensive_source = temporary / "00719B_official_schedule.json"
        _write_bytes(primary_source, primary_download.content)
        _write_bytes(defensive_source, defensive_download.content)
        verify_official_action_day(
            primary_source,
            source_url=primary_download.final_url,
            symbol="0050",
            event_date=verified_through,
            actions=primary_actions,
        )
        verify_official_action_day(
            defensive_source,
            source_url=defensive_download.final_url,
            symbol="00719B",
            event_date=verified_through,
            actions=defensive_actions,
        )
        primary_proof = build_action_verification(
            symbol="0050",
            verified_through=verified_through,
            action_path=primary_path,
            source_path=primary_source,
            source_url=primary_download.final_url,
        )
        defensive_proof = build_action_verification(
            symbol="00719B",
            verified_through=verified_through,
            action_path=defensive_path,
            source_path=defensive_source,
            source_url=defensive_download.final_url,
        )
        _write_json(
            temporary / "0050_action_verification.json", primary_proof
        )
        _write_json(
            temporary / "00719B_action_verification.json", defensive_proof
        )
        _write_json(
            temporary / "manifest.json",
            {
                "format_version": "daily-action-evidence-v1",
                "mode": "paper_only_no_broker",
                "verified_through": verified_through.isoformat(),
                "sources": {
                    "0050": {
                        "url": primary_download.final_url,
                        "sha256": primary_download.sha256,
                    },
                    "00719B": {
                        "url": defensive_download.final_url,
                        "sha256": defensive_download.sha256,
                    },
                },
            },
        )
        temporary.rename(target)
        return target
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def load_daily_action_evidence(
    directory: str | Path,
    *,
    primary_action_path: str | Path,
    defensive_action_path: str | Path,
) -> DailyActionEvidence:
    """Load exactly one complete, internally consistent daily evidence package."""
    root = Path(directory)
    expected_names = {
        "0050_official_schedule.json",
        "00719B_official_schedule.json",
        "0050_action_verification.json",
        "00719B_action_verification.json",
        "manifest.json",
    }
    if not root.is_dir():
        raise ValueError("daily action evidence path is not a directory")
    if {item.name for item in root.iterdir()} != expected_names:
        raise ValueError("daily action evidence package is incomplete or has extra files")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != {
        "format_version",
        "mode",
        "sources",
        "verified_through",
    }:
        raise ValueError("daily action evidence manifest does not match schema")
    if (
        manifest["format_version"] != "daily-action-evidence-v1"
        or manifest["mode"] != "paper_only_no_broker"
    ):
        raise ValueError("unsupported daily action evidence package")
    try:
        verified_through = date.fromisoformat(manifest["verified_through"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid daily action evidence date") from exc
    if root.name != verified_through.isoformat():
        raise ValueError("daily action evidence directory date does not match manifest")
    sources = manifest["sources"]
    if (
        not isinstance(sources, dict)
        or set(sources) != {"0050", "00719B"}
        or any(
            not isinstance(sources[symbol], dict)
            or set(sources[symbol]) != {"sha256", "url"}
            for symbol in ("0050", "00719B")
        )
    ):
        raise ValueError("daily action evidence source manifest is invalid")
    primary_source = root / "0050_official_schedule.json"
    defensive_source = root / "00719B_official_schedule.json"
    if sha256_file(primary_source) != sources["0050"]["sha256"]:
        raise ValueError("0050 official source does not match package manifest")
    if sha256_file(defensive_source) != sources["00719B"]["sha256"]:
        raise ValueError("00719B official source does not match package manifest")
    primary_verification_path = root / "0050_action_verification.json"
    defensive_verification_path = root / "00719B_action_verification.json"
    primary_verification = load_action_verification(
        primary_verification_path,
        action_path=primary_action_path,
        source_path=primary_source,
        expected_symbol="0050",
    )
    defensive_verification = load_action_verification(
        defensive_verification_path,
        action_path=defensive_action_path,
        source_path=defensive_source,
        expected_symbol="00719B",
    )
    for symbol, verification in (
        ("0050", primary_verification),
        ("00719B", defensive_verification),
    ):
        if verification.verified_through != verified_through:
            raise ValueError(f"{symbol} proof date does not match package manifest")
        if verification.source_url != sources[symbol]["url"]:
            raise ValueError(f"{symbol} proof URL does not match package manifest")
    return DailyActionEvidence(
        verified_through=verified_through,
        primary_source_path=primary_source,
        defensive_source_path=defensive_source,
        primary_verification_path=primary_verification_path,
        defensive_verification_path=defensive_verification_path,
        primary_verification=primary_verification,
        defensive_verification=defensive_verification,
    )
