import pytest

from project_alpha.twse_dividends import parse_twse_dividend_html


HTML = """
<html><body><table>
<tr>
<th>ETF Code</th><th>ETF Name</th><th>Ex-dividend Date</th>
<th>Dividend Payment Date</th>
<th>Cash Dividend (NT$/Per beneficiary unit)</th><th>Year Announced</th>
</tr>
<tr><td>0050</td><td>Yuanta Taiwan Top 50</td><td>2025/07/21</td>
<td>2025/08/08</td><td>0.36</td><td>2025</td></tr>
<tr><td>0050</td><td>Yuanta Taiwan Top 50</td><td>2025/01/17</td>
<td>2025/02/20</td><td>2.7</td><td>2025</td></tr>
</table></body></html>
"""


def test_parse_official_dividend_table():
    result = parse_twse_dividend_html(HTML, etf_code="0050")

    assert result.index.is_monotonic_increasing
    assert result["cash_dividend"].tolist() == [2.7, 0.36]
    assert result["announced_year"].tolist() == [2025, 2025]


def test_parse_rejects_schema_change():
    with pytest.raises(ValueError, match="schema changed"):
        parse_twse_dividend_html(
            "<table><tr><th>unexpected</th></tr></table>",
            etf_code="0050",
        )


def test_parse_rejects_nonpositive_dividend():
    bad = HTML.replace(">0.36<", ">0<")

    with pytest.raises(ValueError, match="positive"):
        parse_twse_dividend_html(bad, etf_code="0050")


def test_parser_accepts_bond_etf_code():
    bond_html = HTML.replace("0050", "00679B")

    result = parse_twse_dividend_html(bond_html, etf_code="00679B")

    assert len(result) == 2
