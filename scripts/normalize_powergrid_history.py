"""Validate and normalize the retained POWERGRID.NS daily history response offline."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "output/powergrid-history/20261025/prices/yahoo-provider-v1/provider-data.json"
DEFAULT_OUTPUT = DEFAULT_INPUT.parent.parent / "yahoo-provider-v2"
ISIN = "INE752E01010"
START, END = date(2023, 10, 25), date(2026, 10, 25)
SOURCE_ID = "finance-yahoo-com"
COLUMNS = [
    "isin", "trade_date", "timestamp_ms", "datetime", "open", "high", "low", "close",
    "adj_close", "volume", "split_factor", "unadjusted_open", "unadjusted_high",
    "unadjusted_low", "unadjusted_close", "source_id", "source_location", "retrieved_at",
]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _number(row: dict[str, Any], key: str, *, positive: bool = False) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"invalid numeric field {key}")
    if (positive and value <= 0) or (not positive and value < 0):
        raise ValueError(f"out-of-range numeric field {key}")
    return float(value)


def normalize(input_path: Path = DEFAULT_INPUT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    raw = input_path.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("provider data must be a JSON object")
    expected = {"symbol": "POWERGRID.NS", "name": "Power Grid Corporation of India Limited",
                "currency": "INR", "exchange_name": "NSE", "exchange_timezone": "Asia/Kolkata",
                "interval": "1d", "instrument_type": "EQUITY", "start": START.isoformat(),
                "end": END.isoformat()}
    for key, value in expected.items():
        if data.get(key) != value:
            raise ValueError(f"provider metadata mismatch for {key}")
    bars = data.get("bars")
    if not isinstance(bars, list) or not bars or data.get("count") != len(bars):
        raise ValueError("bar list and provider count disagree")

    if data.get("source_url") != "https://finance.yahoo.com/quote/POWERGRID.NS/history/":
        raise ValueError("unexpected provider source URL")
    available_at = datetime.now(timezone.utc)
    observed_at = datetime.fromtimestamp(data["observed_at_ms"] / 1000, tz=timezone.utc)
    if observed_at > available_at:
        raise ValueError("provider observation timestamp is in the future")
    rows: list[dict[str, Any]] = []
    previous_day: date | None = None
    seen_timestamps: set[int] = set()
    for bar in bars:
        if not isinstance(bar, dict):
            raise ValueError("bar must be an object")
        day = date.fromisoformat(bar["date"])
        if day < START or day > END or (previous_day is not None and day <= previous_day):
            raise ValueError("bars must be unique, chronological and within requested bounds")
        previous_day = day
        timestamp = bar.get("timestamp_ms")
        if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp in seen_timestamps:
            raise ValueError("bar timestamps must be unique integer milliseconds")
        seen_timestamps.add(timestamp)
        dt = datetime.fromisoformat(bar["datetime"].replace("Z", "+00:00"))
        if dt.tzinfo is None or int(dt.timestamp() * 1000) != timestamp:
            raise ValueError("provider datetime and timestamp_ms disagree")
        if dt.astimezone(ZoneInfo("Asia/Kolkata")).date() != day:
            raise ValueError("provider timestamp does not fall on its declared exchange date")
        values = {key: _number(bar, key, positive=True) for key in
                  ("open", "high", "low", "close", "adj_close", "unadjusted_open",
                   "unadjusted_high", "unadjusted_low", "unadjusted_close")}
        if not (values["low"] <= values["open"] <= values["high"] and
                values["low"] <= values["close"] <= values["high"] and
                values["low"] <= values["high"]):
            raise ValueError(f"inconsistent OHLC bounds on {day}")
        if not (values["unadjusted_low"] <= values["unadjusted_open"] <= values["unadjusted_high"] and
                values["unadjusted_low"] <= values["unadjusted_close"] <= values["unadjusted_high"]):
            raise ValueError(f"inconsistent unadjusted OHLC bounds on {day}")
        volume = _number(bar, "volume")
        split = _number(bar, "split_factor", positive=True)
        row = {"isin": ISIN, "trade_date": day.isoformat(), "timestamp_ms": timestamp,
               "datetime": bar["datetime"], **values, "volume": volume, "split_factor": split,
               "source_id": SOURCE_ID,
               "source_location": "https://finance.yahoo.com/quote/POWERGRID.NS/history/",
               "retrieved_at": available_at.isoformat()}
        rows.append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "daily-bars.csv"
    metadata_path = output_dir / "provider-metadata.json"
    manifest_path = output_dir / "manifest.json"
    if any(path.exists() for path in (csv_path, metadata_path, manifest_path)):
        raise FileExistsError("refusing to overwrite normalized output files")
    with csv_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    metadata = {key: data[key] for key in
                ("symbol", "name", "currency", "exchange_name", "exchange_timezone", "interval",
                 "instrument_type", "start", "end", "count", "observed_at_ms", "source_url",
                 "dividends", "splits", "latest_trade")}
    with metadata_path.open("x", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(metadata, indent=2, sort_keys=True) + "\n")

    csv_bytes = csv_path.read_bytes()
    response_path = input_path.with_name("raw-response.json")
    response_persisted = None
    if response_path.exists():
        response_persisted = datetime.fromtimestamp(response_path.stat().st_ctime, tz=timezone.utc).isoformat()
    manifest: dict[str, Any] = {
        "schema_version": "powergrid-daily-bars-v1", "status": "valid",
        "isin": ISIN, "symbol": data["symbol"], "source_id": SOURCE_ID,
        "source_location": data["source_url"], "interval": "1d",
        "requested_window": {"start": START.isoformat(), "end": END.isoformat(), "timezone": "Asia/Kolkata"},
        "observed_window": {"first_trade_date": rows[0]["trade_date"],
                            "last_trade_date": rows[-1]["trade_date"]},
        "rows": len(rows), "csv_sha256": _sha(csv_bytes), "provider_data_sha256": _sha(raw),
        "provider_metadata_sha256": _sha(metadata_path.read_bytes()),
        "provider_observed_at_ms": data["observed_at_ms"],
        "provider_observed_at_utc": datetime.fromtimestamp(data["observed_at_ms"] / 1000,
                                                            tz=timezone.utc).isoformat(),
        "retrieved_at_utc": available_at.isoformat(),
        "retrieved_at_semantics": "time this validated normalized dataset became locally available; not the network receipt time",
        "response_wrapper_first_persisted_at_utc": response_persisted,
        "retrieval_time_note": "Exact network receipt time is not recorded. Response-wrapper filesystem creation time is retained separately and is not represented as provider receipt time.",
        "coverage": {"status": "unknown", "note": "No exchange calendar reconciliation; row count and endpoint dates do not establish exhaustive session coverage."},
        "mechanical_validation": {"status": "passed", "checks": [
            "provider identity metadata", "requested and returned date bounds", "chronological unique trade dates",
            "unique timestamps and timestamp agreement", "finite positive OHLC and adjusted close",
            "valid adjusted and unadjusted OHLC bounds", "finite nonnegative volume", "positive split factor"]},
        "identity_mapping": {"isin": ISIN, "status": "project_context_only",
                              "independent_corroboration": "not performed; symbol-to-ISIN mapping is not proven by this provider response"},
        "independent_validation": {"status": "pending", "receipt": None,
                                   "note": "No independent bar-validation receipt is included; not eligible for assembler outcomes until reviewed."},
        "research_only": True, "orders_or_execution_authorized": False,
    }
    with manifest_path.open("x", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = normalize(args.input, args.output_dir)
    print(json.dumps({k: result[k] for k in ("rows", "csv_sha256", "provider_data_sha256", "observed_window", "coverage")}, indent=2))
