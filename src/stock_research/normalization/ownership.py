from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from stock_research.collectors.base import CollectedDocument, CollectorError


@dataclass(frozen=True, slots=True)
class OwnershipFact:
    isin: str
    metric: str
    value: float
    unit: str
    period_end: str
    source_id: str
    document_key: str
    source_location: str
    evidence_label: str


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalize_shareholding_xbrl(document: CollectedDocument) -> list[OwnershipFact]:
    if document.document_type != "shareholding_pattern" or not document.period_end:
        raise CollectorError("Ownership normalization requires a period-linked shareholding filing")
    try:
        root = ET.fromstring(document.raw_text)
    except ET.ParseError as exc:
        raise CollectorError(f"Invalid shareholding XBRL: {exc}") from exc

    promoter_context = "ShareholdingOfPromoterAndPromoterGroup_ContextI"
    promoter_shares: float | None = None
    promoter_ratio: float | None = None
    pledge_values: list[bool] = []
    for element in root.iter():
        context = element.attrib.get("contextRef")
        name = _local_name(element.tag)
        value = (element.text or "").strip()
        if context == promoter_context and name == "NumberOfShares" and value:
            promoter_shares = float(value)
        elif (
            context == promoter_context
            and name == "ShareholdingAsAPercentageOfTotalNumberOfShares"
            and value
        ):
            promoter_ratio = float(value)
        elif context == "MainI" and name in {
            "WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged",
            "WhetherAnySharesHeldByPromotersAreEncumberedUnderPledgedForPromoterAndPromoterGroup",
            "WhetherAnySharesHeldByPromotersAreEncumberedUnderNonDisposalUndertaking",
            "WhetherAnySharesHeldByPromotersAreEncumberedUnderNonDisposalUndertakingForPromoterAndPromoterGroup",
            "WhetherAnySharesHeldByPromotersAreEncumberedOtherThanByWayOfPledgeOrNDU",
            "WhetherAnySharesHeldByPromotersAreEncumberedOtherThanByWayOfPledgeOrNDUForPromoterAndPromoterGroup",
        }:
            if value.casefold() not in {"true", "false"}:
                raise CollectorError(f"Invalid promoter encumbrance boolean: {value!r}")
            pledge_values.append(value.casefold() == "true")

    if not pledge_values:
        raise CollectorError("Shareholding XBRL has no promoter encumbrance disclosure")
    inferred_no_promoter = promoter_shares is None and promoter_ratio is None
    promoter_shares = 0.0 if inferred_no_promoter else promoter_shares
    promoter_ratio = 0.0 if inferred_no_promoter else promoter_ratio
    if promoter_shares is None or promoter_ratio is None:
        raise CollectorError("Shareholding XBRL has incomplete promoter aggregate facts")
    if promoter_shares < 0 or not 0 <= promoter_ratio <= 1:
        raise CollectorError("Shareholding XBRL contains invalid promoter values")

    common = {
        "isin": document.isin,
        "period_end": document.period_end,
        "source_id": document.source_id,
        "document_key": document.document_key,
        "source_location": document.source_location,
    }
    holding_label = "derived_calculation" if inferred_no_promoter else "fact_source_reported"
    return [
        OwnershipFact(
            **common,
            metric="promoter_holding_pct",
            value=promoter_ratio,
            unit="ratio",
            evidence_label=holding_label,
        ),
        OwnershipFact(
            **common,
            metric="promoter_shares",
            value=promoter_shares,
            unit="shares",
            evidence_label=holding_label,
        ),
        OwnershipFact(
            **common,
            metric="promoter_pledged_flag",
            value=float(any(pledge_values)),
            unit="boolean",
            evidence_label="fact_source_reported",
        ),
    ]
