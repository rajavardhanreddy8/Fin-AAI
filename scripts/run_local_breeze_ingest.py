"""Fetch completed Breeze candles locally and upload only raw snapshots to private S3.

The Breeze API credentials are read from the current local process. The launcher
stores the app key and secret in Git-ignored .env.local; uploads contain candles only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from pathlib import Path
from time import sleep

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from urllib.error import HTTPError, URLError
from stock_research.collectors.breeze_ohlcv import check_breeze_connection, completed_five_minute_candles, resolve_session_token
from stock_research.collectors.breeze_archive import IST, audit_segments, audit_snapshot, build_dataset, raw_evidence, verify_archive, write_json
from stock_research.nifty_universe import load_calendar, session_times


DEFAULT_UPLOAD_ROLE_ARN = "arn:aws:iam::933989369834:role/fin-aai-foundation-LocalIngestRole-YfLIJtjqlAgq"


def parse_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed


def required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required in the current local session")
    return value


def completed_paper_bar(snapshot: dict, *, from_at: datetime, to_at: datetime) -> dict:
    """Extract exactly the requested completed five-minute bar for the paper runner."""
    request = snapshot.get("request", {})
    rows = snapshot.get("response", {}).get("Success")
    expected = to_at.astimezone(IST) - timedelta(minutes=5)
    if (request.get("stock_code"), request.get("exch_code"), request.get("interval")) != ("NIFBEE", "NSE", "5minute") or not isinstance(rows, list):
        raise ValueError("Breeze snapshot is not NSE NIFBEE five-minute evidence")
    matched = []
    for row in rows:
        try:
            at = datetime.fromisoformat(row["datetime"])
            at = at.replace(tzinfo=IST) if at.tzinfo is None else at.astimezone(IST)
            values = {name: float(row[name]) for name in ("open", "high", "low", "close", "volume")}
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Breeze snapshot has an invalid candle") from error
        if row.get("stock_code") != "NIFBEE" or row.get("exchange_code") != "NSE" or not all(math.isfinite(value) for value in values.values()) or min(values[name] for name in ("open", "high", "low", "close")) <= 0 or values["volume"] < 0 or values["low"] > min(values["open"], values["close"]) or values["high"] < max(values["open"], values["close"]):
            raise ValueError("Breeze snapshot has invalid or mismatched OHLCV")
        if at == expected:
            matched.append({"at": at.isoformat(), **values})
    if expected < from_at.astimezone(IST) or len(matched) != 1:
        raise ValueError("Breeze snapshot lacks exactly the requested completed bar")
    return matched[0]


def s3_uploader(args):
    source = boto3.Session(profile_name=args.aws_profile, region_name="ap-southeast-2")
    assumed = source.client("sts").assume_role(RoleArn=args.upload_role_arn, RoleSessionName="fin-aai-local-ingest", DurationSeconds=3600)["Credentials"]
    return boto3.Session(aws_access_key_id=assumed["AccessKeyId"], aws_secret_access_key=assumed["SecretAccessKey"], aws_session_token=assumed["SessionToken"], region_name="ap-southeast-2").client("s3")


def verify_uploaded_versions(args) -> dict:
    """Read only recorded S3 object versions and compare their saved SHA-256 metadata."""
    root = Path(args.archive_dir)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = verify_archive(root)
    client = boto3.Session(profile_name=args.aws_profile, region_name="ap-southeast-2").client("s3")
    uploads = [(day, evidence) for day, session in manifest["sessions"].items() for evidence in raw_evidence(session)]

    def check_raw(upload):
        day, session = upload
        required = ("bucket", "s3_key", "s3_version", "uploaded_sha256", "sha256")
        if any(not session.get(key) for key in required):
            raise ValueError(f"missing upload receipt for {day}")
        response = client.head_object(Bucket=session["bucket"], Key=session["s3_key"], VersionId=session["s3_version"])
        if response.get("VersionId") != session["s3_version"] or response.get("Metadata", {}).get("sha256") != session["sha256"] or session["uploaded_sha256"] != session["sha256"]:
            raise ValueError(f"uploaded raw version does not match local evidence for {day}")
        return day

    with ThreadPoolExecutor(max_workers=16) as workers:
        checked = sum(1 for _ in workers.map(check_raw, uploads))
    receipt = json.loads((root / "collection-result.json").read_text(encoding="utf-8"))
    expected = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if receipt.get("manifest_s3_key") != f"raw/_manifests/{expected}.json" or not receipt.get("manifest_s3_version") or not receipt.get("bucket"):
        raise ValueError("current manifest has no matching upload receipt")
    response = client.head_object(Bucket=receipt["bucket"], Key=receipt["manifest_s3_key"], VersionId=receipt["manifest_s3_version"])
    if response.get("VersionId") != receipt["manifest_s3_version"] or response.get("Metadata", {}).get("sha256") != expected:
        raise ValueError("uploaded manifest version does not match local evidence")
    report["remote_version_checks"] = {"status": "verified", "raw_versions": checked, "manifest_version": receipt["manifest_s3_version"], "manifest_key": receipt["manifest_s3_key"]}
    write_json(root / "verification-report.json", report)
    return report


def saved_regular_closures(root: Path) -> dict:
    path = root / "reference" / "calendar-reconciliation.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("confirmed_regular_closures", {})


def saved_special_sessions(root: Path) -> dict:
    path = root / "reference" / "calendar-reconciliation.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("known_special_sessions_without_cached_bars", {})


def collect_history(args) -> int:
    if args.history_from > args.history_to or args.history_to >= datetime.now(IST).date():
        raise ValueError("history range must be ordered and end before today's session")
    root = Path(args.archive_dir)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"instrument": "NIFTYBEES", "sessions": {}}
    closures = saved_regular_closures(root)
    special_sessions = saved_special_sessions(root)
    requested = [args.history_from.isoformat(), args.history_to.isoformat()]
    if requested not in manifest.setdefault("requested_ranges", []):
        manifest["requested_ranges"].append(requested)
    calendars = {}
    years = {year for start, end in manifest["requested_ranges"] for year in range(date.fromisoformat(start).year, date.fromisoformat(end).year + 1)} | {date.fromisoformat(day).year for day in manifest["sessions"]}
    for year in sorted(years):
        try:
            calendars[year] = load_calendar(args.calendar_db, year) if Path(args.calendar_db).is_file() else None
        except (ValueError, OSError, sqlite3.Error):
            calendars[year] = None
    manifest["calendar_gaps"] = [year for year, value in calendars.items() if value is None]
    secret, client = None, None
    day = args.history_from
    while day <= args.history_to:
        label = day.isoformat()
        special = special_sessions.get(label)
        segments = special.get("segments", []) if special else []
        excluded_intervals = (tuple(tuple(datetime.combine(day, time.fromisoformat(value), IST) for value in segment)
                                   for segment in special.get("excluded_segments", [])) if special else ())
        calendar = calendars[day.year]
        if len(segments) == 1:
            bounds = tuple(datetime.combine(day, time.fromisoformat(value), IST) for value in segments[0])
        else:
            bounds = session_times(calendar, day) if calendar else (None if day.weekday() >= 5 else (datetime.combine(day, time(9, 15), IST), datetime.combine(day, time(15, 30), IST)))
        if bounds is None and not special:
            day += timedelta(days=1)
            continue
        segment_bounds = [tuple(datetime.combine(day, time.fromisoformat(value), IST) for value in segment) for segment in segments] if len(segments) > 1 else [bounds]
        raw_paths = ([root / "raw" / "NIFTYBEES" / label / f"{opening:%H%M}-{closing:%H%M}.json" for opening, closing in segment_bounds]
                     if len(segment_bounds) > 1 else [root / "raw" / "NIFTYBEES" / f"{label}.json"])
        raw = raw_paths[0]
        csv_path = root / "normalized" / "NIFTYBEES" / f"{label}.csv"
        previous = manifest["sessions"].get(label, {})
        try:
            if label in closures and not any(path.exists() for path in raw_paths):
                manifest["sessions"][label] = {"status": "missing", "missing_reason": "exchange_closed", "calendar_evidence": closures[label], "issues": ["saved NSE regular-session closure; no candle expected"]}
                manifest["updated_at"] = datetime.now(IST).isoformat()
                write_json(manifest_path, manifest)
                print(json.dumps({"date": label, "status": "missing", "bars": 0}), flush=True)
                day += timedelta(days=1)
                continue
            if label in special_sessions and not all(path.exists() for path in raw_paths):
                has_single_segment = len(segments) == 1
                if args.retry_missing and not segments:
                    raise ValueError(f"{label} has no saved special-session timings; resolve them before retrying")
                if not args.retry_missing or args.audit_cache or args.upload_cache:
                    reason = "special_session_not_fetched" if has_single_segment else "special_session_multi_segment_not_fetched" if segments else "special_session_unresolved"
                    issue = "saved NSE special-session timings exist but no matching segment was fetched" if has_single_segment else "saved NSE multi-segment session has no per-segment raw evidence" if segments else "saved NSE special-session evidence has no audited session timings or candles"
                    partial = [{"raw_path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in raw_paths if path.exists()]
                    manifest["sessions"][label] = {"status": "missing", "missing_reason": reason, "calendar_evidence": special_sessions[label], "issues": [issue], **({"raw_evidence": partial} if partial else {})}
                    manifest["updated_at"] = datetime.now(IST).isoformat()
                    write_json(manifest_path, manifest)
                    print(json.dumps({"date": label, "status": "missing", "bars": 0}), flush=True)
                    day += timedelta(days=1)
                    continue
            provider_empty = previous.get("missing_reason") == "provider_empty" or any("Breeze returned no candles" in issue for issue in previous.get("issues", []))
            if previous.get("status") == "missing" and provider_empty and not any(path.exists() for path in raw_paths) and not args.retry_missing:
                previous["missing_reason"] = "provider_empty"
                day += timedelta(days=1)
                continue
            if not all(path.exists() for path in raw_paths) and not args.audit_cache and not args.upload_cache:
                if secret is None:
                    app = {"api_key": required_environment("BREEZE_API_KEY"), "api_session": required_environment("BREEZE_API_SESSION")}
                    secret = {"api_key": app["api_key"], "session_token": resolve_session_token(app)}
                for raw_path, (opening, closing) in zip(raw_paths, segment_bounds):
                    if raw_path.exists():
                        continue
                    sleep(0.7)  # Below the documented 100-calls/minute ceiling.
                    snapshot = completed_five_minute_candles(secret, from_at=opening, to_at=closing)
                    write_json(raw_path, snapshot)
            if not all(path.exists() for path in raw_paths):
                manifest["sessions"][label] = {"status": "missing", "missing_reason": "not_cached", "issues": ["raw snapshot not cached; no provider response established"]}
            else:
                previous_by_path = {item.get("raw_path"): item for item in raw_evidence(previous)}
                for raw_path in raw_paths:
                    saved = previous_by_path.get(str(raw_path))
                    if saved and saved.get("sha256") != hashlib.sha256(raw_path.read_bytes()).hexdigest():
                        raise ValueError(f"cached evidence hash changed for {label}; restore the original raw snapshot")
                audit = audit_segments(raw_paths, segment_bounds, csv_path) if len(raw_paths) > 1 else audit_snapshot(raw, *bounds, csv_path, excluded_intervals)
                audit["calendar_verified"] = calendar is not None
                manifest["sessions"][label] = audit
                # The raw evidence is always kept, including incomplete sessions.
                for evidence in raw_evidence(audit):
                    saved = previous_by_path.get(evidence["raw_path"], {})
                    if saved.get("uploaded_sha256") == evidence["sha256"] and (args.audit_cache or saved.get("bucket") == args.bucket):
                        evidence.update({key: saved[key] for key in ("uploaded_sha256", "bucket", "s3_key", "s3_version") if key in saved})
                    elif not args.audit_cache:
                        if client is None:
                            client = s3_uploader(args)
                        key = f"raw/NIFTYBEES/{label}/{evidence['sha256']}.json"
                        # Content-addressed keys preserve experiment inputs across reruns.
                        response = client.put_object(Bucket=args.bucket, Key=key, Body=Path(evidence["raw_path"]).read_bytes(), ContentType="application/json", Metadata={"sha256": evidence["sha256"], "schema-version": "1"})
                        evidence.update(uploaded_sha256=evidence["sha256"], bucket=args.bucket, s3_key=key, s3_version=response.get("VersionId"))
                manifest["sessions"][label] = audit
        except RuntimeError as error:
            # Expected empty historical responses are gaps, never invented candles.
            if "zero candles" not in str(error):
                write_json(manifest_path, manifest)
                raise
            partial = [{"raw_path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in raw_paths if path.exists()]
            manifest["sessions"][label] = {"status": "missing", "missing_reason": "provider_empty_segment" if partial else "provider_empty", "issues": ["Breeze returned no candles; exchange closure or provider gap requires verification"], **({"raw_evidence": partial} if partial else {})}
        finally:
            manifest["updated_at"] = datetime.now(IST).isoformat()
            write_json(manifest_path, manifest)
        print(json.dumps({"date": label, "status": manifest["sessions"][label]["status"], "bars": manifest["sessions"][label].get("bars", 0)}), flush=True)
        day += timedelta(days=1)
    counts = {status: sum(row["status"] == status for row in manifest["sessions"].values()) for status in ("valid", "invalid", "missing")}
    dataset = build_dataset(root, manifest)
    report = {"manifest": str(manifest_path), "sessions": counts, "calendar_gaps": manifest["calendar_gaps"], "completed_at": datetime.now(IST).isoformat()}
    report.update(dataset_path=dataset["path"], dataset_sha256=dataset["sha256"], bars=dataset["bars"])
    if not args.audit_cache:
        client = client or s3_uploader(args)
        encoded = manifest_path.read_bytes()
        content_hash = hashlib.sha256(encoded).hexdigest()
        key = f"raw/_manifests/{content_hash}.json"
        response = client.put_object(Bucket=args.bucket, Key=key, Body=encoded, ContentType="application/json", Metadata={"sha256": content_hash})
        report.update(manifest_s3_key=key, manifest_s3_version=response.get("VersionId"), bucket=args.bucket)
    write_json(root / "collection-result.json", report)
    print(json.dumps(report), flush=True)
    return 0 if not counts["invalid"] and not counts["missing"] and not manifest["calendar_gaps"] else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Breeze-to-private-S3 candle ingestion.")
    parser.add_argument("--check-connection", action="store_true", help="check DNS and verified TLS without credentials")
    parser.add_argument("--from-at", type=parse_at)
    parser.add_argument("--to-at", type=parse_at)
    parser.add_argument("--bucket")
    parser.add_argument("--key")
    parser.add_argument("--paper-bar-output", help="atomically write the requested completed bar for a paper-session invocation")
    parser.add_argument("--aws-profile", default="fin-aai", help="local AWS sign-in profile")
    parser.add_argument("--upload-role-arn", default=DEFAULT_UPLOAD_ROLE_ARN)
    parser.add_argument("--stock-code", default="NIFBEE", help="Breeze security-master code for NIFTYBEES")
    parser.add_argument("--history-from", type=date.fromisoformat)
    parser.add_argument("--history-to", type=date.fromisoformat)
    parser.add_argument("--archive-dir", default="output/market-data")
    parser.add_argument("--calendar-db", default="output/finance-automation.db")
    parser.add_argument("--audit-cache", action="store_true", help="audit saved history without Breeze or AWS access")
    parser.add_argument("--verify-cache", action="store_true", help="verify current local archive hashes without Breeze or AWS access")
    parser.add_argument("--verify-uploaded-versions", action="store_true", help="verify recorded raw and manifest S3 versions without Breeze access")
    parser.add_argument("--upload-cache", action="store_true", help="audit and upload cached history only; never request Breeze credentials or download missing dates")
    parser.add_argument("--retry-missing", action="store_true", help="explicitly retry previously saved provider gaps")
    args = parser.parse_args()
    if args.audit_cache and args.upload_cache:
        parser.error("choose either --audit-cache or --upload-cache")
    if args.verify_cache or args.verify_uploaded_versions:
        if args.verify_cache and args.verify_uploaded_versions:
            parser.error("choose either --verify-cache or --verify-uploaded-versions")
        if args.audit_cache or args.upload_cache or args.history_from or args.history_to:
            parser.error("verification cannot be combined with collection options")
        if args.verify_uploaded_versions:
            report = verify_uploaded_versions(args)
            print(json.dumps(report), flush=True)
            return 0
        report = verify_archive(Path(args.archive_dir))
        write_json(Path(args.archive_dir) / "verification-report.json", report)
        print(json.dumps(report), flush=True)
        return 0
    if args.check_connection:
        check_breeze_connection()
        print("Breeze DNS and TLS verification passed.")
        return 0
    if args.history_from or args.history_to:
        if not args.history_from or not args.history_to or (not args.bucket and not args.audit_cache):
            parser.error("history requires both dates and --bucket unless --audit-cache")
        return collect_history(args)
    if not all((args.from_at, args.to_at, args.bucket, args.key)):
        parser.error("ingestion requires --from-at, --to-at, --bucket and --key")

    secret = {
        "api_key": required_environment("BREEZE_API_KEY"),
        "api_secret": required_environment("BREEZE_API_SECRET"),
        "api_session": required_environment("BREEZE_API_SESSION"),
    }
    snapshot = completed_five_minute_candles(
        secret, from_at=args.from_at, to_at=args.to_at, stock_code=args.stock_code
    )
    encoded = json.dumps(snapshot, separators=(",", ":"), sort_keys=True).encode("utf-8")
    content_hash = hashlib.sha256(encoded).hexdigest()
    s3_uploader(args).put_object(
        Bucket=args.bucket,
        Key=args.key,
        Body=encoded,
        ContentType="application/json",
        Metadata={"sha256": content_hash, "schema-version": "1"},
    )
    result = {"saved": args.key, "sha256": content_hash, "bars": len(snapshot["response"]["Success"])}
    if args.paper_bar_output:
        bar = completed_paper_bar(snapshot, from_at=args.from_at, to_at=args.to_at)
        write_json(Path(args.paper_bar_output), bar)
        result["paper_bar"] = str(args.paper_bar_output)
        result["paper_bar_at"] = bar["at"]
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as error:
        print(f"Local ingestion stopped: {error}", file=sys.stderr)
        raise SystemExit(1)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "unknown")
        print(f"AWS upload stopped ({code}); cached evidence is retained. Refresh AWS access or resolve permissions, then resume.", file=sys.stderr)
        raise SystemExit(1)
    except (BotoCoreError, HTTPError, URLError) as error:
        print(f"Ingestion stopped ({type(error).__name__}); cached evidence is retained. Check connectivity/authentication, then resume.", file=sys.stderr)
        raise SystemExit(1)
