"""Run critical paper-safety checks without third-party test packages."""

from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.error import HTTPError

from project_alpha import official_source
from project_alpha.action_schedule import (
    parse_tpex_action_schedule,
    verify_official_action_day,
)
from project_alpha.daily_action_evidence import (
    TPEX_ACTION_SCHEDULE_URL,
    TWSE_ACTION_SCHEDULE_URL,
    load_daily_action_evidence,
    prepare_daily_action_evidence,
)
from project_alpha.daily_close_evidence import (
    load_daily_close_evidence,
    prepare_daily_close_evidence,
)
from project_alpha.official_close import (
    TPEX_DAILY_CLOSE_URL,
    TWSE_DAILY_CLOSE_URL,
    parse_tpex_daily_closes,
    parse_twse_daily_closes,
)
from project_alpha.official_source import OfficialSourceDownload
from project_alpha.paper_daily import PaperAction


ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 7, 29)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _download(rows: list[dict[str, str]], url: str) -> OfficialSourceDownload:
    return OfficialSourceDownload(
        json.dumps(rows, ensure_ascii=False).encode(),
        url,
        "application/json",
    )


def _close_fetcher(url: str) -> OfficialSourceDownload:
    if url == TWSE_DAILY_CLOSE_URL:
        return _download(
            [
                {"Date": "1150729", "Code": "00682U", "ClosingPrice": ""},
                {"Date": "1150729", "Code": "0050", "ClosingPrice": "98.15"},
            ],
            url,
        )
    if url == TPEX_DAILY_CLOSE_URL:
        return _download(
            [
                {
                    "Date": "1150729",
                    "SecuritiesCompanyCode": "006201",
                    "Close": "---",
                },
                {
                    "Date": "1150729",
                    "SecuritiesCompanyCode": "00719B",
                    "Close": "31.50",
                },
            ],
            url,
        )
    raise RuntimeError(f"unexpected close URL: {url}")


def _action_fetcher(url: str) -> OfficialSourceDownload:
    if url in {TWSE_ACTION_SCHEDULE_URL, TPEX_ACTION_SCHEDULE_URL}:
        return _download([], url)
    raise RuntimeError(f"unexpected action URL: {url}")


def _write_export(path: Path, symbol: str, close: str) -> None:
    path.write_text(
        f"商品代碼:{symbol}\t商品名稱:test\n\n"
        "日期\t開盤價\t最高價\t最低價\t收盤價\t成交量\n"
        f"'2026/07/29 00:00\t{close}\t{close}\t{close}\t{close}\t100\n",
        encoding="utf-8-sig",
    )


def _check_http_retry_policy() -> tuple[str, str]:
    """Exercise permanent/transient HTTP handling without a network request."""

    class Headers:
        @staticmethod
        def get_content_type() -> str:
            return "application/json"

    class Response:
        headers = Headers()

        def __init__(self, url: str):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def geturl(self) -> str:
            return self.url

        @staticmethod
        def read(limit: int) -> bytes:
            return b"[]"

    source_url = "https://www.tpex.org.tw/openapi/v1/example"
    original_open = official_source.urlopen
    original_sleep = official_source.time.sleep
    try:
        permanent_calls = 0

        def missing(request, timeout):
            nonlocal permanent_calls
            permanent_calls += 1
            raise HTTPError(request.full_url, 404, "not found", {}, None)

        official_source.urlopen = missing
        official_source.time.sleep = lambda seconds: None
        try:
            official_source.fetch_official_source(source_url)
        except HTTPError as exc:
            _require(exc.code == 404, "permanent HTTP status changed")
        else:
            raise RuntimeError("permanent HTTP error was accepted")
        _require(permanent_calls == 1, "permanent HTTP error was retried")

        transient_calls = 0

        def unavailable(request, timeout):
            nonlocal transient_calls
            transient_calls += 1
            if transient_calls == 1:
                raise HTTPError(
                    request.full_url, 503, "service unavailable", {}, None
                )
            return Response(request.full_url)

        official_source.urlopen = unavailable
        result = official_source.fetch_official_source(source_url)
        _require(result.content == b"[]", "transient HTTP retry lost content")
        _require(transient_calls == 2, "transient HTTP retry count changed")
    finally:
        official_source.urlopen = original_open
        official_source.time.sleep = original_sleep
    return "permanent_http_not_retried", "transient_http_retried"


def main() -> None:
    checks: list[str] = []
    twse = parse_twse_daily_closes(_close_fetcher(TWSE_DAILY_CLOSE_URL).content)
    tpex = parse_tpex_daily_closes(_close_fetcher(TPEX_DAILY_CLOSE_URL).content)
    _require(len(twse) == 1 and twse[0].symbol == "0050", "TWSE schema check failed")
    _require(
        len(tpex) == 1 and tpex[0].symbol == "00719B",
        "TPEx close schema check failed",
    )
    checks.append("current_official_close_schemas")

    unannounced = [
        {
            "ExRrightsExDividendDate": "1150729",
            "SecuritiesCompanyCode": "00719B",
            "StockDividendRatio": "0.00000000",
            "CashDividend": "尚未公告",
        }
    ]
    schedule = parse_tpex_action_schedule(
        json.dumps(unannounced, ensure_ascii=False).encode()
    )
    _require(schedule[0].cash_dividend is None, "unknown cash was treated as zero")
    checks.append("unannounced_dividend_preserved")
    checks.extend(_check_http_retry_policy())

    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        primary_export = temp / "0050.txt"
        defensive_export = temp / "00719B.txt"
        _write_export(primary_export, "0050", "98.15")
        _write_export(defensive_export, "00719B", "31.50")

        close_package = prepare_daily_close_evidence(
            primary_export_path=primary_export,
            defensive_export_path=defensive_export,
            output_root=temp / "close",
            fetcher=_close_fetcher,
        )
        loaded_close = load_daily_close_evidence(
            close_package,
            primary_export_path=primary_export,
            defensive_export_path=defensive_export,
        )
        _require(loaded_close.observed_on == DAY, "close evidence date changed")
        checks.append("close_evidence_round_trip")

        action_package = prepare_daily_action_evidence(
            verified_through=DAY,
            primary_action_path=ROOT / "research/0050_actions.csv",
            defensive_action_path=ROOT / "research/00719B_actions.csv",
            output_root=temp / "actions",
            fetcher=_action_fetcher,
        )
        loaded_actions = load_daily_action_evidence(
            action_package,
            primary_action_path=ROOT / "research/0050_actions.csv",
            defensive_action_path=ROOT / "research/00719B_actions.csv",
        )
        _require(
            loaded_actions.verified_through == DAY,
            "action evidence date changed",
        )
        checks.append("action_evidence_round_trip")

        unknown_source = temp / "unknown-action.json"
        unknown_source.write_text(
            json.dumps(unannounced, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            verify_official_action_day(
                unknown_source,
                source_url=TPEX_ACTION_SCHEDULE_URL,
                symbol="00719B",
                event_date=DAY,
                actions={DAY: PaperAction(1.0, 0.27)},
            )
        except ValueError as exc:
            _require(
                "not yet announced" in str(exc),
                "unexpected unknown-dividend error",
            )
        else:
            raise RuntimeError("unannounced dividend was accepted")
        checks.append("unannounced_dividend_blocked")

        try:
            verify_official_action_day(
                unknown_source,
                source_url="https://www.tpex.org.tw/openapi/v1/tpex_cmode",
                symbol="00719B",
                event_date=DAY,
                actions={},
            )
        except ValueError as exc:
            _require(
                "unsupported" in str(exc),
                "unexpected wrong-endpoint error",
            )
        else:
            raise RuntimeError("wrong official action endpoint was accepted")
        checks.append("exact_action_endpoint_required")

        command = [
            sys.executable,
            str(ROOT / "scripts/update_paper_from_mitake.py"),
            str(ROOT / "research/preregistration.json"),
            str(ROOT / "data/paper_observations.csv"),
            str(primary_export),
            str(defensive_export),
            str(ROOT / "research/0050_actions.csv"),
            str(ROOT / "research/00719B_actions.csv"),
            str(ROOT / "research/paper_snapshot.json"),
            "--write",
            "--audit-output",
            str(temp / "audit.json"),
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
            check=False,
        )
        _require(completed.returncode != 0, "unsafe paper write was accepted")
        _require(
            "official close evidence package is required with --write"
            in completed.stderr,
            "paper write failed for the wrong reason",
        )
        _require(not (temp / "audit.json").exists(), "failed write left an audit file")
        checks.append("write_requires_close_evidence")

    print(
        json.dumps(
            {
                "mode": "paper_only_no_broker",
                "passed": len(checks),
                "checks": checks,
                "full_pytest_replacement": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
