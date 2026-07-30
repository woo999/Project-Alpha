"""Verify the complete committed official-evidence chain for paper tracking."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_alpha.paper_evidence_chain import verify_paper_evidence_chain
from project_alpha.paper_snapshot_io import load_authenticated_paper_ledger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify paper ledger, daily audits, and official summaries."
    )
    parser.add_argument("preregistration", type=Path)
    parser.add_argument("observations", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("audit_dir", type=Path)
    parser.add_argument("evidence_dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ledger = load_authenticated_paper_ledger(
        args.preregistration,
        args.observations,
        args.snapshot,
    )
    result = verify_paper_evidence_chain(
        ledger,
        audit_dir=args.audit_dir,
        evidence_dir=args.evidence_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
