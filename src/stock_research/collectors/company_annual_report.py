from __future__ import annotations

import hashlib
import io
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

from pypdf import PdfReader

from .base import CollectedDocument, CollectorError


_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class AnnualReportSpec:
    isin: str
    symbol: str
    source_id: str
    listing_url: str
    report_url: str
    period_end: date
    identity_text: str
    reporting_scope: str


ANNUAL_REPORT_SPECS = {
    "INE733E01010": AnnualReportSpec(
        isin="INE733E01010",
        symbol="NTPC",
        source_id="ntpc_ir",
        listing_url="https://ntpc.co.in/investors/annual-reports",
        report_url=(
            "https://ntpc.co.in/sites/default/files/annual-report/complete-reports/"
            "Annual%20Report%202025-26%20%283%29.pdf"
        ),
        period_end=date(2026, 3, 31),
        identity_text="NTPC",
        reporting_scope="consolidated",
    ),
    "INE090A01021": AnnualReportSpec(
        isin="INE090A01021",
        symbol="ICICIBANK",
        source_id="icicibank_ir",
        listing_url=(
            "https://www.icici.bank.in/content/icicibank/in/en-newheader/about-us/"
            "annual.dropdown.json?key=2026"
        ),
        report_url=(
            "https://www.icici.bank.in/content/dam/icicibank/managed-assets/docs/"
            "investor/annual-reports/2026/ICICI-Bank-AR2025-2026_narrative.pdf"
        ),
        period_end=date(2026, 3, 31),
        identity_text="ICICI Bank",
        reporting_scope="bank",
    ),
}


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.add(urljoin(self.base_url, href))


class CompanyAnnualReportCollector:
    """Download and validate company-primary annual-report PDFs."""

    def _listing_links(self, spec: AnnualReportSpec) -> set[str] | None:
        request = urllib.request.Request(
            spec.listing_url, headers={"User-Agent": _BROWSER_USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read().decode("utf-8-sig")
        if "Radware Captcha Page" in content:
            return None
        parser = _LinkParser(spec.listing_url)
        parser.feed(content)
        return parser.links

    def _download_pdf(self, url: str) -> tuple[bytes, str | None]:
        request = urllib.request.Request(url, headers={"User-Agent": _BROWSER_USER_AGENT})
        with urllib.request.urlopen(request, timeout=120) as response:
            content_type = response.headers.get_content_type()
            payload = response.read()
            last_modified = response.headers.get("Last-Modified")
        if content_type != "application/pdf" or not payload.startswith(b"%PDF-"):
            raise CollectorError(f"Annual-report URL did not return a PDF: {url}")
        if len(payload) < 100_000:
            raise CollectorError(f"Annual-report PDF is unexpectedly small: {len(payload)} bytes")
        return payload, last_modified

    @staticmethod
    def _extract_identity_text(payload: bytes, pages: int = 20) -> str:
        try:
            reader = PdfReader(io.BytesIO(payload), strict=False)
            return "\n".join(
                page.extract_text() or "" for page in reader.pages[:pages]
            )
        except Exception as exc:
            raise CollectorError(f"Annual-report PDF text extraction failed: {exc}") from exc

    def collect(self, spec: AnnualReportSpec, as_of: date) -> CollectedDocument:
        if spec.period_end > as_of:
            raise CollectorError("Annual-report period is after the collection as-of date")
        links = self._listing_links(spec)
        if links is not None and spec.report_url not in links:
            raise CollectorError(
                f"Official investor page no longer links the expected annual report: {spec.report_url}"
            )
        payload, last_modified = self._download_pdf(spec.report_url)
        identity_text = self._extract_identity_text(payload)
        if spec.identity_text.casefold() not in identity_text.casefold():
            raise CollectorError(
                f"Annual-report PDF does not contain expected identity {spec.identity_text!r}"
            )
        published = as_of
        if last_modified:
            published = parsedate_to_datetime(last_modified).date()
        if published > as_of:
            raise CollectorError("Annual-report publication date is after the collection as-of date")
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return CollectedDocument(
            document_key=f"company_annual_report:{spec.isin}:{spec.period_end.isoformat()}",
            isin=spec.isin,
            source_id=spec.source_id,
            source_tier="company_primary",
            document_type="annual_report",
            title=f"{spec.symbol} annual report FY{spec.period_end.year}",
            published_at=published.isoformat(),
            retrieved_at=retrieved_at,
            source_location=spec.report_url,
            period_end=spec.period_end.isoformat(),
            reporting_scope=spec.reporting_scope,
            content_hash=hashlib.sha256(payload).hexdigest(),
            raw_text=identity_text,
            confidence=0.95,
        )
