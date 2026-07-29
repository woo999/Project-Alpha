"""Prepare an atomic package reconciling Mitake and official daily closes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile

from project_alpha.mitake import load_mitake_daily_export
from project_alpha.official_close import (
    TPEX_DAILY_CLOSE_URL,
    TWSE_DAILY_CLOSE_URL,
    verify_official_close,
)
from project_alpha.official_source import (
    OfficialSourceDownload,
    fetch_official_source,
)


@dataclass(frozen=True)
class DailyCloseEvidence:
    observed_on: date
    primary_source_path: Path
    defensive_source_path: Path
    manifest_path: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def prepare_daily_close_evidence(
    *,
    primary_export_path: str | Path,
    defensive_export_path: str | Path,
    output_root: str | Path,
    fetcher: Callable[[str], OfficialSourceDownload] = fetch_official_source,
) -> Path:
    """Validate both latest closes and publish all evidence in one rename."""
    primary_path = Path(primary_export_path)
    defensive_path = Path(defensive_export_path)
    primary = load_mitake_daily_export(primary_path, expected_symbol="0050")
    defensive = load_mitake_daily_export(
        defensive_path, expected_symbol="00719B"
    )
    primary_latest = primary[-1]
    defensive_latest = defensive[-1]
    if primary_latest.observed_on != defensive_latest.observed_on:
        raise ValueError("Mitake exports have different latest dates")
    observed_on = primary_latest.observed_on
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / observed_on.isoformat()
    if target.exists():
        raise FileExistsError(f"daily close evidence already exists: {target}")
    temporary = Path(tempfile.mkdtemp(prefix=".close-evidence-", dir=root))
    try:
        primary_download = fetcher(TWSE_DAILY_CLOSE_URL)
        defensive_download = fetcher(TPEX_DAILY_CLOSE_URL)
        verify_official_close(
            primary_download.content,
            source_url=primary_download.final_url,
            symbol="0050",
            expected_date=observed_on,
            expected_close=primary_latest.close,
        )
        verify_official_close(
            defensive_download.content,
            source_url=defensive_download.final_url,
            symbol="00719B",
            expected_date=observed_on,
            expected_close=defensive_latest.close,
        )
        primary_source = temporary / "0050_official_close.json"
        defensive_source = temporary / "00719B_official_close.json"
        _write_bytes(primary_source, primary_download.content)
        _write_bytes(defensive_source, defensive_download.content)
        _write_json(
            temporary / "manifest.json",
            {
                "format_version": "daily-close-evidence-v1",
                "mode": "paper_only_no_broker",
                "observed_on": observed_on.isoformat(),
                "exports": {
                    "0050": {
                        "close": primary_latest.close,
                        "sha256": _sha256(primary_path),
                    },
                    "00719B": {
                        "close": defensive_latest.close,
                        "sha256": _sha256(defensive_path),
                    },
                },
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


def load_daily_close_evidence(
    directory: str | Path,
    *,
    primary_export_path: str | Path,
    defensive_export_path: str | Path,
) -> DailyCloseEvidence:
    """Reload and verify every link in one daily close evidence package."""
    root = Path(directory)
    expected_names = {
        "0050_official_close.json",
        "00719B_official_close.json",
        "manifest.json",
    }
    if not root.is_dir():
        raise ValueError("daily close evidence path is not a directory")
    if {item.name for item in root.iterdir()} != expected_names:
        raise ValueError("daily close evidence package is incomplete or has extra files")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != {
        "exports",
        "format_version",
        "mode",
        "observed_on",
        "sources",
    }:
        raise ValueError("daily close evidence manifest does not match schema")
    if (
        manifest["format_version"] != "daily-close-evidence-v1"
        or manifest["mode"] != "paper_only_no_broker"
    ):
        raise ValueError("unsupported daily close evidence package")
    try:
        observed_on = date.fromisoformat(manifest["observed_on"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid daily close evidence date") from exc
    if root.name != observed_on.isoformat():
        raise ValueError("daily close evidence directory date does not match manifest")
    exports = manifest["exports"]
    sources = manifest["sources"]
    if (
        not isinstance(exports, dict)
        or set(exports) != {"0050", "00719B"}
        or not isinstance(sources, dict)
        or set(sources) != {"0050", "00719B"}
        or any(
            not isinstance(exports[symbol], dict)
            or set(exports[symbol]) != {"close", "sha256"}
            or not isinstance(sources[symbol], dict)
            or set(sources[symbol]) != {"sha256", "url"}
            for symbol in ("0050", "00719B")
        )
    ):
        raise ValueError("daily close evidence entries do not match schema")
    primary_path = Path(primary_export_path)
    defensive_path = Path(defensive_export_path)
    if _sha256(primary_path) != exports["0050"]["sha256"]:
        raise ValueError("0050 export does not match daily close evidence")
    if _sha256(defensive_path) != exports["00719B"]["sha256"]:
        raise ValueError("00719B export does not match daily close evidence")
    primary = load_mitake_daily_export(primary_path, expected_symbol="0050")
    defensive = load_mitake_daily_export(
        defensive_path, expected_symbol="00719B"
    )
    primary_latest = primary[-1]
    defensive_latest = defensive[-1]
    if (
        primary_latest.observed_on != observed_on
        or defensive_latest.observed_on != observed_on
    ):
        raise ValueError("Mitake latest date does not match daily close evidence")
    if (
        not isinstance(exports["0050"]["close"], (int, float))
        or not isinstance(exports["00719B"]["close"], (int, float))
        or not math.isclose(
            primary_latest.close,
            float(exports["0050"]["close"]),
            rel_tol=0,
            abs_tol=1e-9,
        )
        or not math.isclose(
            defensive_latest.close,
            float(exports["00719B"]["close"]),
            rel_tol=0,
            abs_tol=1e-9,
        )
    ):
        raise ValueError("Mitake close does not match daily close manifest")
    primary_source = root / "0050_official_close.json"
    defensive_source = root / "00719B_official_close.json"
    if _sha256(primary_source) != sources["0050"]["sha256"]:
        raise ValueError("0050 official close does not match package manifest")
    if _sha256(defensive_source) != sources["00719B"]["sha256"]:
        raise ValueError("00719B official close does not match package manifest")
    verify_official_close(
        primary_source.read_bytes(),
        source_url=sources["0050"]["url"],
        symbol="0050",
        expected_date=observed_on,
        expected_close=primary_latest.close,
    )
    verify_official_close(
        defensive_source.read_bytes(),
        source_url=sources["00719B"]["url"],
        symbol="00719B",
        expected_date=observed_on,
        expected_close=defensive_latest.close,
    )
    return DailyCloseEvidence(
        observed_on=observed_on,
        primary_source_path=primary_source,
        defensive_source_path=defensive_source,
        manifest_path=manifest_path,
    )
