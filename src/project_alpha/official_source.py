"""Restricted downloader for free official corporate-action evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from project_alpha.action_verification import validate_official_source_url


MAX_OFFICIAL_SOURCE_BYTES = 25 * 1024 * 1024
RETRYABLE_HTTP_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/json",
        "application/pdf",
        "text/csv",
        "text/html",
        "text/plain",
    }
)


@dataclass(frozen=True)
class OfficialSourceDownload:
    content: bytes
    final_url: str
    content_type: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def fetch_official_source(
    source_url: str,
    *,
    timeout: float = 30.0,
    max_bytes: int = MAX_OFFICIAL_SOURCE_BYTES,
    attempts: int = 3,
    retry_delay: float = 0.5,
) -> OfficialSourceDownload:
    """Download one bounded official response; never accesses broker services."""
    validate_official_source_url(source_url)
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if max_bytes <= 0 or max_bytes > MAX_OFFICIAL_SOURCE_BYTES:
        raise ValueError("max_bytes is outside the safe range")
    if attempts < 1 or attempts > 3:
        raise ValueError("attempts must be between 1 and 3")
    if retry_delay < 0 or retry_delay > 5:
        raise ValueError("retry_delay is outside the safe range")
    request = Request(
        source_url,
        headers={
            "Accept": "application/json,text/csv,text/html,application/pdf",
            "User-Agent": "Project-Alpha research/1.0",
        },
    )
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=timeout) as response:
                final_url = response.geturl()
                validate_official_source_url(final_url)
                content_type = response.headers.get_content_type().lower()
                if content_type not in ALLOWED_CONTENT_TYPES:
                    raise ValueError(
                        f"unsupported official response type: {content_type}"
                    )
                content = response.read(max_bytes + 1)
            break
        except HTTPError as exc:
            if exc.code not in RETRYABLE_HTTP_STATUS_CODES:
                raise
            if attempt + 1 == attempts:
                raise
            time.sleep(retry_delay * (2**attempt))
        except (TimeoutError, URLError):
            if attempt + 1 == attempts:
                raise
            time.sleep(retry_delay * (2**attempt))
    if not content:
        raise ValueError("official source response is empty")
    if len(content) > max_bytes:
        raise ValueError("official source response exceeds size limit")
    return OfficialSourceDownload(content, final_url, content_type)
