"""Offline one-date NSE versus retained Yahoo price check."""
import argparse
import csv
import io
import json
import zipfile
from decimal import Decimal
from pathlib import Path

ISIN = "INE752E01010"
SYMBOL = "POWERGRID"


def verify(archive_path: Path, provider_path: Path, trade_date: str) -> dict:
    with zipfile.ZipFile(archive_path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError("NSE ZIP must contain exactly one CSV")
        rows = csv.DictReader(io.StringIO(archive.read(members[0]).decode("utf-8-sig")))
        matches = [r for r in rows if r.get("ISIN", "").strip().upper() == ISIN
                   and r.get("TckrSymb", "").strip().upper() == SYMBOL
                   and r.get("SctySrs", "").strip() == "EQ"]
    matches = [r for r in matches if r.get("TradDt", "").strip() == trade_date]
    if len(matches) != 1:
        raise ValueError(f"Expected one POWERGRID EQ row for {trade_date}; found {len(matches)}")
    official = matches[0]
    data = json.loads(provider_path.read_text(encoding="utf-8"))
    if data.get("symbol") != "POWERGRID.NS" or data.get("exchange_name") != "NSE" or data.get("currency") != "INR":
        raise ValueError("Saved provider metadata does not identify POWERGRID.NS on NSE in INR")
    bars = [b for b in data.get("bars", []) if b.get("date") == trade_date]
    if len(bars) != 1:
        raise ValueError(f"Expected one saved provider bar for {trade_date}; found {len(bars)}")
    bar = bars[0]
    comparisons = {field: {"official": official[nse], "yahoo_unadjusted": bar[yahoo],
                            "match": Decimal(official[nse]) == Decimal(str(bar[yahoo]))}
                   for field, nse, yahoo in (("open", "OpnPric", "unadjusted_open"),
                                             ("high", "HghPric", "unadjusted_high"),
                                             ("low", "LwPric", "unadjusted_low"),
                                             ("close", "ClsPric", "unadjusted_close"),
                                             ("volume", "TtlTradgVol", "volume"))}
    return {"trade_date": trade_date, "identity": {"symbol": SYMBOL, "isin": ISIN, "series": "EQ"},
            "status": "match" if all(x["match"] for x in comparisons.values()) else "mismatch",
            "fields": comparisons, "adjusted_close": bar.get("adj_close"),
            "adjusted_close_compared": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("provider_json", type=Path)
    parser.add_argument("trade_date")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = verify(args.archive, args.provider_json, args.trade_date)
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, indent=2) + "\n")
