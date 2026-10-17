"""Run the isolated, data-only Breeze historical-candle collector on AWS."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

import boto3

from stock_research.collectors.breeze_ohlcv import completed_five_minute_candles, save_raw_snapshot


def parse_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone, for example 2026-10-03T09:15:00+05:30")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch completed NIFTYBEES five-minute candles only.")
    parser.add_argument("--from-at", required=True, type=parse_at)
    parser.add_argument("--to-at", required=True, type=parse_at)
    parser.add_argument("--stock-code", default="NIFTYBEES")
    parser.add_argument("--secret-id", default=os.environ["BREEZE_SECRET_ID"])
    parser.add_argument("--bucket", default=os.environ["PILOT_DATA_BUCKET"])
    parser.add_argument("--key", required=True)
    args = parser.parse_args()

    secret_value = boto3.client("secretsmanager").get_secret_value(SecretId=args.secret_id)["SecretString"]
    secret = json.loads(secret_value)
    snapshot = completed_five_minute_candles(
        secret, from_at=args.from_at, to_at=args.to_at, stock_code=args.stock_code
    )
    content_hash = save_raw_snapshot(snapshot, bucket=args.bucket, key=args.key)
    print(json.dumps({"saved": args.key, "sha256": content_hash, "bars": len(snapshot["response"]["Success"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
