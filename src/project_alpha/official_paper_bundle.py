"""Atomic bundle of all official evidence required for one paper mark."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from project_alpha.daily_action_evidence import (
    DailyActionEvidence,
    load_daily_action_evidence,
    prepare_daily_action_evidence,
)
from project_alpha.daily_official_close_evidence import (
    DailyOfficialCloseEvidence,
    load_daily_official_close_evidence,
    prepare_daily_official_close_evidence,
)
from project_alpha.official_source import OfficialSourceDownload, fetch_official_source


@dataclass(frozen=True)
class OfficialPaperBundle:
    observed_on: date
    close: DailyOfficialCloseEvidence
    actions: DailyActionEvidence
    manifest_path: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def prepare_official_paper_bundle(
    *,
    observed_on: date,
    primary_action_path: str | Path,
    defensive_action_path: str | Path,
    output_root: str | Path,
    fetcher: Callable[[str], OfficialSourceDownload] = fetch_official_source,
) -> Path:
    """Fetch all four official sources and publish only a complete bundle."""
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / observed_on.isoformat()
    if target.exists():
        raise FileExistsError(f"official paper bundle already exists: {target}")
    temporary = Path(tempfile.mkdtemp(prefix=".official-paper-", dir=root))
    try:
        close_package = prepare_daily_official_close_evidence(
            expected_date=observed_on,
            output_root=temporary / "close",
            fetcher=fetcher,
        )
        action_package = prepare_daily_action_evidence(
            verified_through=observed_on,
            primary_action_path=primary_action_path,
            defensive_action_path=defensive_action_path,
            output_root=temporary / "actions",
            fetcher=fetcher,
        )
        close_manifest = close_package / "manifest.json"
        action_manifest = action_package / "manifest.json"
        _write_json(
            temporary / "manifest.json",
            {
                "format_version": "official-paper-bundle-v1",
                "mode": "paper_only_no_broker",
                "observed_on": observed_on.isoformat(),
                "manifests": {
                    "close": _sha256(close_manifest),
                    "actions": _sha256(action_manifest),
                },
            },
        )
        temporary.rename(target)
        return target
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def load_official_paper_bundle(
    directory: str | Path,
    *,
    primary_action_path: str | Path,
    defensive_action_path: str | Path,
) -> OfficialPaperBundle:
    """Reload the bundle and verify its two complete evidence packages."""
    root = Path(directory)
    if not root.is_dir() or {item.name for item in root.iterdir()} != {
        "close",
        "actions",
        "manifest.json",
    }:
        raise ValueError("official paper bundle is incomplete or has extra files")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != {
        "format_version",
        "mode",
        "observed_on",
        "manifests",
    }:
        raise ValueError("official paper bundle manifest does not match schema")
    if (
        manifest["format_version"] != "official-paper-bundle-v1"
        or manifest["mode"] != "paper_only_no_broker"
    ):
        raise ValueError("unsupported official paper bundle")
    try:
        observed_on = date.fromisoformat(manifest["observed_on"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid official paper bundle date") from exc
    if root.name != observed_on.isoformat():
        raise ValueError("official paper bundle directory date does not match")
    hashes = manifest["manifests"]
    if not isinstance(hashes, dict) or set(hashes) != {"close", "actions"}:
        raise ValueError("official paper bundle manifest hashes are invalid")
    close_dir = root / "close" / observed_on.isoformat()
    action_dir = root / "actions" / observed_on.isoformat()
    if _sha256(close_dir / "manifest.json") != hashes["close"]:
        raise ValueError("official close manifest does not match bundle")
    if _sha256(action_dir / "manifest.json") != hashes["actions"]:
        raise ValueError("official action manifest does not match bundle")
    close = load_daily_official_close_evidence(close_dir)
    actions = load_daily_action_evidence(
        action_dir,
        primary_action_path=primary_action_path,
        defensive_action_path=defensive_action_path,
    )
    if close.observed_on != observed_on or actions.verified_through != observed_on:
        raise ValueError("official evidence dates do not match bundle")
    return OfficialPaperBundle(observed_on, close, actions, manifest_path)
