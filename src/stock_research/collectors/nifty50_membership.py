"""Source-backed, dated Nifty 50 constituent and weight snapshots."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from .base import read_bytes
from .upstox import digest

SOURCE_ID = "nifty_indices_nifty50_weights"


def build_snapshot(payload: bytes, source_url: str, *, observed_at: datetime, effective_at: datetime | None = None, expected_count: int = 50) -> dict:
    if not source_url.startswith("https://www.niftyindices.com/"):
        raise ValueError("Nifty 50 source must be an official HTTPS Nifty Indices URL")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None or (effective_at and (effective_at.tzinfo is None or effective_at.utcoffset() is None)):
        raise ValueError("membership timestamps must include a timezone")
    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    fields = {field.strip().lower(): field for field in (reader.fieldnames or [])}
    def find(*names):
        return next((fields[name] for name in names if name in fields), None)
    symbol_col, isin_col, weight_col = find("symbol"), find("isin code", "isin"), find("weight", "weight (%)", "weight(%)")
    if not symbol_col or not isin_col or not weight_col:
        raise ValueError("official Nifty 50 source must include Symbol, ISIN and Weight columns")
    members, symbols, isins = [], set(), set()
    for row in reader:
        symbol, isin = row[symbol_col].strip().upper(), row[isin_col].strip().upper()
        try: weight = float(row[weight_col].strip().rstrip("%"))
        except (TypeError, ValueError): raise ValueError("invalid Nifty 50 constituent weight") from None
        if not symbol or len(isin) != 12 or not isin.isalnum() or weight <= 0:
            raise ValueError("invalid Nifty 50 constituent identity or weight")
        if symbol in symbols or isin in isins:
            raise ValueError("duplicate Nifty 50 constituent identity")
        symbols.add(symbol); isins.add(isin)
        members.append({"symbol": symbol, "isin": isin, "weight": weight})
    if expected_count is not None and len(members) != expected_count:
        raise ValueError(f"incomplete Nifty 50 snapshot: expected {expected_count} members, received {len(members)}")
    if abs(sum(member["weight"] for member in members) - 100) > 2:
        raise ValueError("Nifty 50 weights are materially incomplete")
    raw = {"source_id": SOURCE_ID, "source_url": source_url, "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
           "known_at": observed_at.astimezone(timezone.utc).isoformat(),
           "effective_at": (effective_at or observed_at).astimezone(timezone.utc).isoformat(), "members": members, "raw_csv": text}
    return {**raw, "snapshot_id": digest(raw), "raw_hash": digest(text)}


def collect_snapshot(url: str, *, fetch=read_bytes, observed_at: datetime | None = None, effective_at: datetime | None = None) -> dict:
    return build_snapshot(fetch(url), url, observed_at=observed_at or datetime.now(timezone.utc), effective_at=effective_at)
