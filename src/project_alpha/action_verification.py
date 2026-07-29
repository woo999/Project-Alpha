"""Bind corporate-action freshness claims to reviewed official-source files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

OFFICIAL_ACTION_SOURCE_HOSTS = frozenset(
    {
        "api.yuantafunds.com",
        "mopsov.twse.com.tw",
        "www.sitca.org.tw",
        "www.taifex.com.tw",
        "www.tpex.org.tw",
    }
)


@dataclass(frozen=True)
class ActionVerification:
    symbol: str
    verified_through: date
    action_file_sha256: str
    source_file_sha256: str
    source_url: str


def validate_official_source_url(source_url: str) -> None:
    parsed = urlparse(source_url) if isinstance(source_url, str) else None
    if (
        parsed is None
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname.lower() not in OFFICIAL_ACTION_SOURCE_HOSTS
    ):
        raise ValueError("action verification source must be an approved official URL")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_action_verification(
    *,
    symbol: str,
    verified_through: date,
    action_path: str | Path,
    source_path: str | Path,
    source_url: str,
) -> dict[str, str]:
    """Build deterministic proof content for a reviewed official-source query."""
    if not symbol or not symbol.strip() or symbol != symbol.strip():
        raise ValueError("symbol must be a non-empty trimmed string")
    validate_official_source_url(source_url)
    return {
        "format_version": "action-verification-v2",
        "symbol": symbol,
        "verified_through": verified_through.isoformat(),
        "action_file_sha256": sha256_file(action_path),
        "source_file_sha256": sha256_file(source_path),
        "source_url": source_url,
    }


def load_action_verification(
    path: str | Path,
    *,
    action_path: str | Path,
    source_path: str | Path,
    expected_symbol: str,
) -> ActionVerification:
    """Load a strict proof and verify that it belongs to the exact action file."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    expected_keys = {
        "format_version",
        "symbol",
        "verified_through",
        "action_file_sha256",
        "source_file_sha256",
        "source_url",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ValueError("action verification document does not match schema")
    if payload["format_version"] != "action-verification-v2":
        raise ValueError("unsupported action verification format")
    if payload["symbol"] != expected_symbol:
        raise ValueError("action verification symbol does not match candidate")
    try:
        verified_through = date.fromisoformat(payload["verified_through"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid action verification date") from exc
    claimed_hash = payload["action_file_sha256"]
    if not isinstance(claimed_hash, str) or len(claimed_hash) != 64:
        raise ValueError("invalid action file SHA-256")
    if claimed_hash.lower() != sha256_file(action_path):
        raise ValueError("action verification does not match action file SHA-256")
    claimed_source_hash = payload["source_file_sha256"]
    if not isinstance(claimed_source_hash, str) or len(claimed_source_hash) != 64:
        raise ValueError("invalid official source file SHA-256")
    if claimed_source_hash.lower() != sha256_file(source_path):
        raise ValueError(
            "action verification does not match official source file SHA-256"
        )
    source_url = payload["source_url"]
    validate_official_source_url(source_url)
    return ActionVerification(
        symbol=expected_symbol,
        verified_through=verified_through,
        action_file_sha256=claimed_hash.lower(),
        source_file_sha256=claimed_source_hash.lower(),
        source_url=source_url,
    )
