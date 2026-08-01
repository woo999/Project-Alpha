"""Run critical paper-safety checks without third-party test packages."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from urllib.error import HTTPError

from project_alpha import official_source, paper_snapshot_io
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
from project_alpha.daily_official_close_evidence import (
    load_daily_official_close_evidence,
    prepare_daily_official_close_evidence,
)
from project_alpha.official_close import (
    TPEX_DAILY_CLOSE_URL,
    TWSE_DAILY_CLOSE_URL,
    parse_tpex_daily_closes,
    parse_twse_daily_closes,
)
from project_alpha.official_evidence_summary import (
    build_official_evidence_summary,
)
from project_alpha.official_paper_bundle import prepare_official_paper_bundle
from project_alpha.official_paper_advance import advance_next_official_paper
from project_alpha.next_official_bundle import (
    OfficialDateNotMature,
    OfficialSourceContentInvalid,
    prepare_next_official_paper_bundle,
)
from project_alpha.official_source import OfficialSourceDownload
from project_alpha.paper_daily import PaperAction
from project_alpha.official_paper_update import (
    append_official_bundle_mark,
    append_official_daily_mark,
)
from project_alpha.paper_snapshot_io import load_authenticated_paper_ledger
from project_alpha.paper_status import build_paper_status
from project_alpha.paper_evidence_chain import verify_paper_evidence_chain
from project_alpha.paper_tracking import PaperLedger
from scripts.advance_official_paper import run_advance


ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 7, 30)


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
                {"Date": "1150730", "Code": "00682U", "ClosingPrice": ""},
                {"Date": "1150730", "Code": "0050", "ClosingPrice": "98.15"},
            ],
            url,
        )
    if url == TPEX_DAILY_CLOSE_URL:
        return _download(
            [
                {
                    "Date": "1150730",
                    "SecuritiesCompanyCode": "006201",
                    "Close": "---",
                },
                {
                    "Date": "1150730",
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


def _bundle_fetcher(url: str) -> OfficialSourceDownload:
    if url in {TWSE_DAILY_CLOSE_URL, TPEX_DAILY_CLOSE_URL}:
        return _close_fetcher(url)
    return _action_fetcher(url)


def _write_export(
    path: Path,
    symbol: str,
    close: str,
    *,
    observed_on: date = DAY,
) -> None:
    path.write_text(
        f"商品代碼:{symbol}\t商品名稱:test\n\n"
        "日期\t開盤價\t最高價\t最低價\t收盤價\t成交量\n"
        f"'{observed_on:%Y/%m/%d} 00:00\t"
        f"{close}\t{close}\t{close}\t{close}\t100\n",
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
            "ExRrightsExDividendDate": "1150730",
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
        ledger = load_authenticated_paper_ledger(
            ROOT / "research/preregistration.json",
            ROOT / "data/paper_observations.csv",
            ROOT / "research/paper_snapshot.json",
        )
        snapshot_document = json.loads(
            (ROOT / "research/paper_snapshot.json").read_text(encoding="utf-8")
        )
        _require(
            ledger.observations[-1].observed_on.isoformat()
            == snapshot_document["last_observed_on"],
            "authenticated ledger boundary changed",
        )
        checks.append("authenticated_paper_ledger_loaded")
        status = build_paper_status(ledger)
        _require(
            status.allocation_drift_outside_tolerance
            and not status.rebalance_due_next_observation
            and status.next_rebalance_observation == 64,
            "allocation drift was confused with an early rebalance",
        )
        checks.append("allocation_drift_does_not_trigger_early_rebalance")
        chain = verify_paper_evidence_chain(
            ledger,
            audit_dir=ROOT / "research/audits",
            evidence_dir=ROOT / "research/official_evidence",
            primary_actions_path=ROOT / "research/0050_actions.csv",
            defensive_actions_path=ROOT / "research/00719B_actions.csv",
        )
        _require(
            chain["ledger_hash"] == ledger.ledger_hash,
            "official evidence chain lost the authenticated ledger",
        )
        checks.append("official_evidence_chain_verified")
        copied_audits = temp / "audits"
        copied_evidence = temp / "official-evidence"
        shutil.copytree(ROOT / "research/audits", copied_audits)
        shutil.copytree(ROOT / "research/official_evidence", copied_evidence)
        tampered_summary_path = copied_evidence / "2026-07-30.json"
        tampered_summary = json.loads(
            tampered_summary_path.read_text(encoding="utf-8")
        )
        tampered_summary["closes"]["0050"]["raw_sha256"] = "0" * 64
        tampered_summary_path.write_text(
            json.dumps(tampered_summary),
            encoding="utf-8",
        )
        try:
            verify_paper_evidence_chain(
                ledger,
                audit_dir=copied_audits,
                evidence_dir=copied_evidence,
                primary_actions_path=ROOT / "research/0050_actions.csv",
                defensive_actions_path=ROOT / "research/00719B_actions.csv",
            )
        except ValueError as exc:
            _require(
                "SHA-256" in str(exc),
                "tampered evidence failed for the wrong reason",
            )
        else:
            raise RuntimeError("tampered official evidence was accepted")
        checks.append("tampered_official_evidence_rejected")
        event_evidence = temp / "official-event-evidence"
        shutil.copytree(ROOT / "research/official_evidence", event_evidence)
        event_summary_path = event_evidence / "2026-07-30.json"
        event_summary = json.loads(
            event_summary_path.read_text(encoding="utf-8")
        )
        event_summary["corporate_actions"]["0050"][
            "event_on_observed_date"
        ] = True
        event_summary_path.write_text(
            json.dumps(event_summary),
            encoding="utf-8",
        )
        event_actions = temp / "0050-actions-with-target.csv"
        event_actions.write_text(
            "date,split_ratio,cash_dividend\n"
            "2026-07-21,1.0,0.6\n"
            "2026-07-30,1.0,0.1\n",
            encoding="utf-8",
        )
        event_chain = verify_paper_evidence_chain(
            ledger,
            audit_dir=copied_audits,
            evidence_dir=event_evidence,
            primary_actions_path=event_actions,
            defensive_actions_path=ROOT / "research/00719B_actions.csv",
        )
        _require(
            event_chain["valid"] is True,
            "declared official corporate action was rejected",
        )
        checks.append("declared_official_action_supported")
        rollback_observations = temp / "rollback-observations.csv"
        rollback_snapshot = temp / "rollback-snapshot.json"
        rollback_audit = temp / "rollback-audit.json"
        rollback_summary = temp / "rollback-summary.json"
        rollback_paths = (
            rollback_observations,
            rollback_snapshot,
            rollback_audit,
            rollback_summary,
        )
        for path, content in zip(
            rollback_paths,
            ("old observations\n", "old snapshot\n", "old audit\n", "old summary\n"),
            strict=True,
        ):
            path.write_text(content, encoding="utf-8")
        original_replace = paper_snapshot_io._replace_file
        replace_calls = 0

        def fail_fourth_replace(source: Path, destination: Path) -> None:
            nonlocal replace_calls
            replace_calls += 1
            if replace_calls == 4:
                raise OSError("simulated evidence-summary failure")
            original_replace(source, destination)

        paper_snapshot_io._replace_file = fail_fourth_replace
        try:
            try:
                paper_snapshot_io.write_checkpoint(
                    ledger,
                    rollback_observations,
                    rollback_snapshot,
                    additional_text_files={
                        rollback_audit: "new audit\n",
                        rollback_summary: "new summary\n",
                    },
                )
            except OSError as exc:
                _require(
                    "evidence-summary" in str(exc),
                    "four-file rollback failed for the wrong reason",
                )
            else:
                raise RuntimeError("fourth checkpoint failure was accepted")
        finally:
            paper_snapshot_io._replace_file = original_replace
        _require(
            tuple(
                path.read_text(encoding="utf-8")
                for path in rollback_paths
            )
            == (
                "old observations\n",
                "old snapshot\n",
                "old audit\n",
                "old summary\n",
            ),
            "four-file checkpoint rollback left partial output",
        )
        checks.append("four_file_checkpoint_rollback")

        snapshot_document["ledger_hash"] = "0" * 64
        tampered_snapshot = temp / "tampered-paper-snapshot.json"
        tampered_snapshot.write_text(
            json.dumps(snapshot_document),
            encoding="utf-8",
        )
        try:
            load_authenticated_paper_ledger(
                ROOT / "research/preregistration.json",
                ROOT / "data/paper_observations.csv",
                tampered_snapshot,
            )
        except ValueError as exc:
            _require(
                "does not match" in str(exc),
                "tampered snapshot failed for the wrong reason",
            )
        else:
            raise RuntimeError("tampered paper snapshot was accepted")
        checks.append("tampered_paper_snapshot_rejected")

        official_close_package = prepare_daily_official_close_evidence(
            expected_date=DAY,
            output_root=temp / "official-close",
            fetcher=_close_fetcher,
        )
        official_close = load_daily_official_close_evidence(
            official_close_package
        )
        _require(
            official_close.observed_on == DAY,
            "official-only close evidence date changed",
        )
        checks.append("official_only_close_evidence_round_trip")

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

        synthetic_ledger = PaperLedger(
            ledger.spec,
            [
                observation
                for observation in ledger.observations
                if observation.observed_on < DAY
            ],
        )
        _require(
            synthetic_ledger.observations,
            "official-only updater needs a pre-target synthetic boundary",
        )
        preclose_calls: list[str] = []

        def tracked_preclose_fetcher(url: str) -> OfficialSourceDownload:
            preclose_calls.append(url)
            return _bundle_fetcher(url)

        try:
            prepare_next_official_paper_bundle(
                synthetic_ledger,
                primary_action_path=ROOT / "research/0050_actions.csv",
                defensive_action_path=ROOT / "research/00719B_actions.csv",
                output_root=temp / "preclose-bundles",
                fetcher=tracked_preclose_fetcher,
                now=datetime.fromisoformat("2026-07-30T13:30:00+08:00"),
            )
        except OfficialDateNotMature:
            pass
        else:
            raise RuntimeError("same-day pre-close official value was accepted")
        _require(
            set(preclose_calls) == {TWSE_DAILY_CLOSE_URL, TPEX_DAILY_CLOSE_URL}
            and not (temp / "preclose-bundles" / DAY.isoformat()).exists(),
            "pre-close guard fetched actions or left an evidence bundle",
        )
        checks.append("same_day_preclose_value_blocked")
        cutoff_calls: list[str] = []

        def tracked_cutoff_fetcher(url: str) -> OfficialSourceDownload:
            cutoff_calls.append(url)
            return _bundle_fetcher(url)

        cutoff_bundle = prepare_next_official_paper_bundle(
            synthetic_ledger,
            primary_action_path=ROOT / "research/0050_actions.csv",
            defensive_action_path=ROOT / "research/00719B_actions.csv",
            output_root=temp / "cutoff-bundles",
            fetcher=tracked_cutoff_fetcher,
            now=datetime.fromisoformat("2026-07-30T14:30:00+08:00"),
        )
        _require(
            cutoff_bundle is not None
            and cutoff_bundle.name == DAY.isoformat()
            and set(cutoff_calls)
            == {
                TWSE_DAILY_CLOSE_URL,
                TPEX_DAILY_CLOSE_URL,
                TWSE_ACTION_SCHEDULE_URL,
                TPEX_ACTION_SCHEDULE_URL,
            },
            "close cutoff did not enable the complete four-source bundle",
        )
        checks.append("same_day_close_cutoff_allows_complete_bundle")
        count_before_official_update = len(synthetic_ledger.observations)
        audit = append_official_daily_mark(
            synthetic_ledger,
            close_evidence_dir=official_close_package,
            action_evidence_dir=action_package,
            primary_actions_path=ROOT / "research/0050_actions.csv",
            defensive_actions_path=ROOT / "research/00719B_actions.csv",
        )
        _require(
            len(synthetic_ledger.observations) == count_before_official_update + 1
            and synthetic_ledger.observations[-1].observed_on == DAY,
            "official-only updater did not append exactly one target day",
        )
        _require(
            audit["safety"]["orders_placed"] is False,
            "official-only updater audit changed paper safety state",
        )
        checks.append("official_only_paper_update_dry_run")
        bundle_package = prepare_official_paper_bundle(
            observed_on=DAY,
            primary_action_path=ROOT / "research/0050_actions.csv",
            defensive_action_path=ROOT / "research/00719B_actions.csv",
            output_root=temp / "official-bundle",
            fetcher=_bundle_fetcher,
        )
        bundle_ledger = PaperLedger(
            ledger.spec,
            [
                observation
                for observation in ledger.observations
                if observation.observed_on < DAY
            ],
        )
        bundle_audit = append_official_bundle_mark(
            bundle_ledger,
            bundle_dir=bundle_package,
            primary_actions_path=ROOT / "research/0050_actions.csv",
            defensive_actions_path=ROOT / "research/00719B_actions.csv",
        )
        generated_summary = build_official_evidence_summary(
            bundle_dir=bundle_package,
            audit=bundle_audit,
            primary_actions_path=ROOT / "research/0050_actions.csv",
            defensive_actions_path=ROOT / "research/00719B_actions.csv",
        )
        _require(
            generated_summary["closes"]["0050"]["close"] == 98.15
            and generated_summary["format_version"]
            == "official-evidence-summary-v2"
            and generated_summary["closes"]["0050"]["source_row"]["Code"]
            == "0050"
            and generated_summary["closes"]["00719B"]["source_row"][
                "SecuritiesCompanyCode"
            ]
            == "00719B"
            and generated_summary["corporate_actions"]["0050"][
                "event_on_observed_date"
            ]
            is False,
            "official evidence summary was not derived from the verified bundle",
        )
        checks.append("replayable_official_evidence_summary_generated")

        advance_ledger = PaperLedger(
            ledger.spec,
            [
                observation
                for observation in ledger.observations
                if observation.observed_on < DAY
            ],
        )
        advance_observations = temp / "advance-observations.csv"
        advance_snapshot = temp / "advance-snapshot.json"
        advance_audits = temp / "advance-audits"
        advance_evidence = temp / "advance-evidence"
        advance_result = advance_next_official_paper(
            advance_ledger,
            observations_path=advance_observations,
            snapshot_path=advance_snapshot,
            primary_actions_path=ROOT / "research/0050_actions.csv",
            defensive_actions_path=ROOT / "research/00719B_actions.csv",
            bundle_root=temp / "advance-bundles",
            audit_dir=advance_audits,
            evidence_dir=advance_evidence,
            write=True,
            fetcher=_bundle_fetcher,
        )
        _require(
            advance_result["advanced"] is True
            and advance_result["observed_on"] == DAY.isoformat()
            and advance_observations.exists()
            and advance_snapshot.exists()
            and (advance_audits / f"{DAY.isoformat()}.json").exists()
            and (advance_evidence / f"{DAY.isoformat()}.json").exists(),
            "one-command official advance did not atomically publish four files",
        )
        checks.append("one_command_official_advance")
        no_op_result = advance_next_official_paper(
            advance_ledger,
            observations_path=advance_observations,
            snapshot_path=advance_snapshot,
            primary_actions_path=ROOT / "research/0050_actions.csv",
            defensive_actions_path=ROOT / "research/00719B_actions.csv",
            bundle_root=temp / "no-op-bundles",
            audit_dir=advance_audits,
            evidence_dir=advance_evidence,
            write=True,
            fetcher=_bundle_fetcher,
        )
        _require(
            no_op_result["ready"] is False
            and no_op_result["advanced"] is False
            and len(advance_ledger.observations)
            == advance_result["observation_count"],
            "one-command official advance duplicated the current date",
        )
        checks.append("one_command_official_advance_noop")

        advance_args = SimpleNamespace(
            observations=temp / "unused-observations.csv",
            snapshot=temp / "unused-snapshot.json",
            primary_actions=ROOT / "research/0050_actions.csv",
            defensive_actions=ROOT / "research/00719B_actions.csv",
            bundle_root=temp / "unused-bundles",
            audit_dir=temp / "unused-audits",
            evidence_dir=temp / "unused-evidence",
            write=True,
        )

        def fail_local_checkpoint(*args, **kwargs):
            raise OSError("simulated local checkpoint failure")

        local_result, local_exit = run_advance(
            advance_args,
            ledger,
            advance=fail_local_checkpoint,
        )
        _require(
            local_exit == 1
            and local_result["reason"] == "local paper checkpoint failure"
            and "source_error" not in local_result,
            "local checkpoint failure was misclassified as source unavailability",
        )
        checks.append("local_checkpoint_failure_is_fatal")

        def fail_official_source(*args, **kwargs):
            raise HTTPError(
                TWSE_DAILY_CLOSE_URL,
                502,
                "Bad Gateway",
                hdrs=None,
                fp=None,
            )

        source_result, source_exit = run_advance(
            advance_args,
            ledger,
            advance=fail_official_source,
        )
        _require(
            source_exit == 0
            and source_result["reason"] == "official source unavailable"
            and source_result["source_error"]["error"] == "HTTP 502",
            "temporary official source failure stopped being a safe no-op",
        )
        checks.append("official_source_failure_is_nonfatal")

        def fail_invalid_official_content(*args, **kwargs):
            raise OfficialSourceContentInvalid(
                source_url=TPEX_DAILY_CLOSE_URL,
                detail="JSONDecodeError",
            )

        invalid_result, invalid_exit = run_advance(
            advance_args,
            ledger,
            advance=fail_invalid_official_content,
        )
        _require(
            invalid_exit == 0
            and invalid_result["reason"]
            == "official source content is invalid"
            and invalid_result["source_error"]
            == {
                "error": "JSONDecodeError",
                "url": TPEX_DAILY_CLOSE_URL,
            },
            "malformed official source did not become a safe no-op",
        )
        checks.append("invalid_official_source_content_is_nonfatal")

        def fail_immature_date(*args, **kwargs):
            raise OfficialDateNotMature(observed_on=DAY)

        immature_result, immature_exit = run_advance(
            advance_args,
            ledger,
            advance=fail_immature_date,
        )
        _require(
            immature_exit == 0
            and immature_result["reason"]
            == "same-day official close is not mature"
            and immature_result["available_after"]
            == "2026-07-30T14:30:00+08:00",
            "same-day maturity guard was not reported as a safe no-op",
        )
        checks.append("same_day_preclose_status_is_nonfatal")

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

        unsafe_day = ledger.observations[-1].observed_on + timedelta(days=1)
        _write_export(
            primary_export,
            "0050",
            "98.15",
            observed_on=unsafe_day,
        )
        _write_export(
            defensive_export,
            "00719B",
            "31.50",
            observed_on=unsafe_day,
        )
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
