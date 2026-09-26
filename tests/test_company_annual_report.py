from __future__ import annotations

import hashlib
import unittest
from datetime import date
from unittest.mock import patch

from stock_research.collectors.base import CollectorError
from stock_research.collectors.company_annual_report import (
    ANNUAL_REPORT_SPECS,
    CompanyAnnualReportCollector,
)


class CompanyAnnualReportCollectorTest(unittest.TestCase):
    def test_hashes_binary_pdf_and_preserves_company_primary_provenance(self) -> None:
        spec = ANNUAL_REPORT_SPECS["INE733E01010"]
        payload = b"%PDF-1.7" + (b"x" * 100_000)
        collector = CompanyAnnualReportCollector()
        with (
            patch.object(collector, "_listing_links", return_value={spec.report_url}),
            patch.object(
                collector,
                "_download_pdf",
                return_value=(payload, "Fri, 14 Aug 2026 10:18:30 GMT"),
            ),
            patch.object(collector, "_extract_identity_text", return_value="NTPC Limited"),
        ):
            document = collector.collect(spec, date(2026, 9, 1))

        self.assertEqual(document.document_type, "annual_report")
        self.assertEqual(document.period_end, "2026-03-31")
        self.assertEqual(document.published_at, "2026-08-14")
        self.assertEqual(document.content_hash, hashlib.sha256(payload).hexdigest())
        self.assertEqual(document.source_location, spec.report_url)

    def test_unlinked_pdf_fails_closed_before_download(self) -> None:
        spec = ANNUAL_REPORT_SPECS["INE090A01021"]
        collector = CompanyAnnualReportCollector()
        with (
            patch.object(collector, "_listing_links", return_value=set()),
            patch.object(collector, "_download_pdf") as download,
            self.assertRaisesRegex(CollectorError, "no longer links"),
        ):
            collector.collect(spec, date(2026, 9, 1))
        download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
