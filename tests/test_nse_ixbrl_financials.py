from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from stock_research.collectors.base import CollectorError
from stock_research.collectors.nse_ixbrl_financials import NSEIXBRLFinancialCollector


HTML = b"""
<table>
<tr><th>Scrip Code</th><td>532540</td></tr>
<tr><th>NSE Symbol</th><td>TCS</td></tr>
<tr><th>ISIN</th><td>INE467B01029</td></tr>
<tr><th>Nature of report standalone or consolidated</th><td>Standalone</td></tr>
<tr><th>Revenue from operations</th><td>2,20,93,800.00</td></tr>
<tr><th>Total profit (loss) for period</th><td>49,09,600.00</td></tr>
<tr><th>Total profit before tax</th><td>62,80,600.00</td></tr>
<tr><th>Finance costs</th><td>23,800.00</td><td>1,12,400.00</td></tr>
<tr><th>Depreciation, depletion and amortisation expense</th><td>4,28,800.00</td></tr>
<tr><th>Total equity</th><td>84,67,600.00</td></tr>
<tr><th>Total assets</th><td>1,49,26,800.00</td></tr>
<tr><th>Total current liabilities</th><td>54,96,000.00</td></tr>
<tr><th>Cash and cash equivalents</th><td>1,83,300.00</td></tr>
<tr><th>Borrowings, non-current</th><td>0.00</td></tr>
<tr><th>Borrowings, current</th><td>0.00</td></tr>
<tr><th>Net cash flows from (used in) operating activities</th><td>45,59,700.00</td></tr>
<tr><th>Purchase of property, plant and equipment</th><td>3,08,100.00</td></tr>
<tr><th>Purchase of intangible assets</th><td>45,300.00</td></tr>
<tr><th>Paid-up equity share capital</th><td>36,200.00</td></tr>
<tr><th>Face value of equity share capital</th><td>1</td></tr>
</table>
"""


class NSEIXBRLFinancialCollectorTest(unittest.TestCase):
    def test_extracts_reported_and_derived_annual_facts(self) -> None:
        with patch(
            "stock_research.collectors.nse_ixbrl_financials.read_bytes", return_value=HTML
        ):
            document, facts = NSEIXBRLFinancialCollector().collect_annual(
                "https://nsearchives.nseindia.com/tcs.html",
                "INE467B01029",
                "TCS",
                "532540",
                date(2026, 4, 9),
                date(2026, 3, 31),
            )

        by_metric = {fact.metric: fact for fact in facts}
        self.assertEqual(by_metric["operating_cash_flow"].value, 455970)
        self.assertEqual(by_metric["capital_expenditure"].value, 35340)
        self.assertEqual(by_metric["free_cash_flow"].value, 420630)
        self.assertEqual(by_metric["cash_and_equivalents"].value, 18330)
        self.assertEqual(by_metric["interest_expense"].value, 11240)
        self.assertEqual(by_metric["total_debt"].value, 0)
        self.assertEqual(by_metric["shares_outstanding"].value, 3_620_000_000)
        self.assertGreater(by_metric["interest_coverage"].value, 50)
        self.assertGreater(by_metric["roe"].value, 0)
        self.assertGreater(by_metric["roce"].value, 0)
        self.assertGreater(by_metric["ebitda_margin"].value, 0)
        self.assertGreater(by_metric["net_margin"].value, 0)
        self.assertEqual(by_metric["capital_expenditure"].evidence_label, "fact_derived")
        self.assertEqual(document.reporting_scope, "standalone")
        self.assertIn("INE467B01029", document.raw_text)

    def test_identity_mismatch_fails_closed(self) -> None:
        with (
            patch(
                "stock_research.collectors.nse_ixbrl_financials.read_bytes", return_value=HTML
            ),
            self.assertRaisesRegex(CollectorError, "identity mismatch"),
        ):
            NSEIXBRLFinancialCollector().collect_annual(
                "https://nsearchives.nseindia.com/tcs.html",
                "INE009A01021",
                "TCS",
                "532540",
                date(2026, 4, 9),
                date(2026, 3, 31),
            )


if __name__ == "__main__":
    unittest.main()
