"""Atomic daily close evidence sourced directly from TWSE and TPEx."""

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

from project_alpha.official_close import (
    OfficialClose,
    TPEX_DAILY_CLOSE_URL,
    TWSE_DAILY_CLOSE_URL,
    official_close_for_symbol,
)
from project_alpha.official_source import (
    OfficialSourceDownload,
    fetch_official_source,
)


@dataclass(frozen=True)
class DailyOfficialCloseEvidence:
    observed_on: date
    primary: OfficialClose
    defensive: OfficialClose
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


def prepare_daily_official_close_evidence(
    *,
    expected_date: date,
    output_root: str | Path,
    fetcher: Callable[[str], OfficialSourceDownload] = fetch_official_source,
) -> Path:
    """Fetch, reconcile, and atomically publish two official close sources."""
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / expected_date.isoformat()
    if target.exists():
        raise FileExistsError(
            f"daily official close evidence already exists: {target}"
        )
    temporary = Path(
        tempfile.mkdtemp(prefix=".official-close-evidence-", dir=root)
    )
    try:
        primary_download = fetcher(TWSE_DAILY_CLOSE_URL)
        defensive_download = fetcher(TPEX_DAILY_CLOSE_URL)
        primary = official_close_for_symbol(
            primary_download.content,
            source_url=primary_download.final_url,
            symbol="0050",
        )
        defensive = official_close_for_symbol(
            defensive_download.content,
            source_url=defensive_download.final_url,
            symbol="00719B",
        )
        for close in (primary, defensive):
            if close.observed_on != expected_date:
                raise ValueError(
                    f"{close.symbol} official close is dated "
                    f"{close.observed_on.isoformat()}, expected "
                    f"{expected_date.isoformat()}"
                )
        primary_source = temporary / "0050_official_close.json"
        defensive_source = temporary / "00719B_official_close.json"
        _write_bytes(primary_source, primary_download.content)
        _write_bytes(defensive_source, defensive_download.content)
        _write_json(
            temporary / "manifest.json",
            {
                "format_version": "daily-official-close-evidence-v1",
                "mode": "paper_only_no_broker",
                "observed_on": expected_date.isoformat(),
                "sources": {
                    "0050": {
                        "close": primary.close,
                        "sha256": primary_download.sha256,
                        "url": primary_download.final_url,
                    },
                    "00719B": {
                        "close": defensive.close,
                        "sha256": defensive_download.sha256,
                        "url": defensive_download.final_url,
                    },
                },
            },
        )
        temporary.rename(target)
        return target
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def load_daily_official_close_evidence(
    directory: str | Path,
) -> DailyOfficialCloseEvidence:
    """Reload and verify every hash, URL, symbol, date, and close."""
    root = Path(directory)
    expected_names = {
        "0050_official_close.json",
        "00719B_official_close.json",
        "manifest.json",
    }
    if not root.is_dir():
        raise ValueError("daily official close evidence path is not a directory")
    if {item.name for item in root.iterdir()} != expected_names:
        raise ValueError(
            "daily official close evidence package is incomplete or has extra files"
        )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != {
        "format_version",
        "mode",
        "observed_on",
        "sources",
    }:
        raise ValueError("daily official close manifest does not match schema")
    if (
        manifest["format_version"] != "daily-official-close-evidence-v1"
        or manifest["mode"] != "paper_only_no_broker"
    ):
        raise ValueError("unsupported daily official close evidence package")
    try:
        observed_on = date.fromisoformat(manifest["observed_on"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid daily official close evidence date") from exc
    if root.name != observed_on.isoformat():
        raise ValueError(
            "daily official close evidence directory date does not match manifest"
        )
    sources = manifest["sources"]
    if (
        not isinstance(sources, dict)
        or set(sources) != {"0050", "00719B"}
        or any(
            not isinstance(sources[symbol], dict)
            or set(sources[symbol]) != {"close", "sha256", "url"}
            for symbol in ("0050", "00719B")
        )
    ):
        raise ValueError("daily official close source manifest is invalid")
    primary_source = root / "0050_official_close.json"
    defensive_source = root / "00719B_official_close.json"
    for symbol, source in (
        ("0050", primary_source),
        ("00719B", defensive_source),
    ):
        if _sha256(source) != sources[symbol]["sha256"]:
            raise ValueError(
                f"{symbol} official close does not match package manifest"
            )
    primary = official_close_for_symbol(
        primary_source.read_bytes(),
        source_url=sources["0050"]["url"],
        symbol="0050",
    )
    defensive = official_close_for_symbol(
        defensive_source.read_bytes(),
        source_url=sources["00719B"]["url"],
        symbol="00719B",
    )
    for close in (primary, defensive):
        recorded_close = sources[close.symbol]["close"]
        if (
            close.observed_on != observed_on
            or isinstance(recorded_close, bool)
            or not isinstance(recorded_close, (int, float))
            or not math.isclose(
                close.close,
                float(recorded_close),
                rel_tol=0,
                abs_tol=1e-9,
            )
        ):
            raise ValueError(
                f"{close.symbol} official close conflicts with package manifest"
            )
    return DailyOfficialCloseEvidence(
        observed_on=observed_on,
        primary=primary,
        defensive=defensive,
        primary_source_path=primary_source,
        defensive_source_path=defensive_source,
        manifest_path=manifest_path,
    )
