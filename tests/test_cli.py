import json

import numpy as np
import pandas as pd

from project_alpha.cli import main


def test_cli_emits_machine_readable_research_report(tmp_path, capsys):
    rows = 400
    returns = np.where(np.arange(rows) % 40 < 30, 0.003, -0.002)
    path = tmp_path / "prices.csv"
    pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01", periods=rows, freq="D"),
            "close": 100.0 * np.cumprod(1.0 + returns),
        }
    ).to_csv(path, index=False)

    exit_code = main(
        [
            str(path),
            "--min-train",
            "200",
            "--test-size",
            "100",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert report["mode"] == "research_only"
    assert report["fold_count"] == 2
    assert isinstance(report["passed"], bool)
    assert report["aggregate_performance"]["observations"] == 200
    assert report["benchmark"]["benchmark_name"] == "frictionless_buy_and_hold"
    assert "excess_total_return" in report["benchmark"]
    assert [item["cost_multiplier"] for item in report["cost_stress"]["scenarios"]] == [
        1.0,
        1.5,
        2.0,
    ]
