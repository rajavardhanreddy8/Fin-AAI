"""Durable candle evidence and regular-session quality checks; no credentials."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
DATASET_FIELDS = ("at", "open", "high", "low", "close", "volume")


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2), encoding="utf-8")
    for attempt in range(5):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            sleep(0.1 * (attempt + 1))


def audit_snapshot(path: Path, opening: datetime, closing: datetime, csv_path: Path, excluded_intervals: tuple[tuple[datetime, datetime], ...] = ()) -> dict:
    if opening.tzinfo is None or closing.tzinfo is None or opening >= closing:
        raise ValueError("audit requires an ordered timezone-aware session")
    if any(start.tzinfo is None or end.tzinfo is None or start >= end for start, end in excluded_intervals):
        raise ValueError("excluded intervals must be ordered and timezone-aware")
    raw = path.read_bytes()
    snapshot = json.loads(raw)
    request = snapshot["request"]
    if snapshot["response"].get("Status") != 200 or not isinstance(snapshot["response"].get("Success"), list):
        raise ValueError("raw snapshot does not contain a successful candle response")
    if (request.get("stock_code"), request.get("exch_code"), request.get("interval")) != ("NIFBEE", "NSE", "5minute"):
        raise ValueError("archive accepts only NSE NIFBEE five-minute evidence")
    retrieved = datetime.fromisoformat(snapshot["retrieved_at"].replace("Z", "+00:00"))
    if retrieved.tzinfo is None:
        raise ValueError("snapshot retrieval timestamp must include a timezone")
    expected = []
    at = opening
    while at + timedelta(minutes=5) <= closing:
        expected.append(at)
        at += timedelta(minutes=5)
    rows, issues, excluded, excluded_non_normal = {}, [], [], []
    last = None
    for source in snapshot["response"]["Success"]:
        at = datetime.fromisoformat(source["datetime"])
        at = at.replace(tzinfo=IST) if at.tzinfo is None else at.astimezone(IST)
        if source.get("exchange_code") != "NSE" or source.get("stock_code") != "NIFBEE":
            issues.append("instrument identity mismatch")
            continue
        values = [float(source[name]) for name in ("open", "high", "low", "close", "volume")]
        op, high, low, close, volume = values
        if not all(math.isfinite(v) for v in values) or min(op, high, low, close) <= 0 or volume < 0 or low > min(op, close) or high < max(op, close):
            issues.append(f"invalid OHLCV: {at.isoformat()}")
            continue
        # Breeze includes the endpoint row. A bar starting at the regular close
        # cannot be a completed five-minute continuous-session bar.
        if at == closing:
            excluded.append(at.isoformat())
            continue
        if any(start <= at < end for start, end in excluded_intervals):
            excluded_non_normal.append(at.isoformat())
            continue
        if at not in expected or at + timedelta(minutes=5) > retrieved:
            issues.append(f"outside session, off grid or incomplete: {at.isoformat()}")
            continue
        if at in rows or (last is not None and at <= last):
            issues.append(f"duplicate or unordered timestamp: {at.isoformat()}")
            continue
        last = at
        rows[at] = values
    missing = [at.isoformat() for at in expected if at not in rows]
    if missing:
        issues.append(f"missing {len(missing)} expected bars")
    result = {"sha256": hashlib.sha256(raw).hexdigest(), "raw_path": str(path),
              "raw_bars": len(snapshot["response"]["Success"]), "bars": len(rows),
              "expected_bars": len(expected), "excluded_close_rows": excluded,
              "excluded_non_normal_rows": excluded_non_normal,
              "missing": missing, "issues": sorted(set(issues)),
              "status": "valid" if rows and not issues else "invalid"}
    if result["status"] == "valid":
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = csv_path.with_suffix(".csv.tmp")
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(("at", "open", "high", "low", "close", "volume"))
            writer.writerows((at.isoformat(), *rows[at]) for at in expected)
        temporary.replace(csv_path)
        result.update(csv_path=str(csv_path), csv_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest())
    else:
        csv_path.unlink(missing_ok=True)
    return result


def audit_segments(paths: list[Path], bounds: list[tuple[datetime, datetime]], csv_path: Path) -> dict:
    """Audit each official segment separately, then join only complete segments."""
    if len(paths) != len(bounds) or not paths:
        raise ValueError("segment paths and session bounds must be non-empty and aligned")
    audits = [audit_snapshot(path, opening, closing, csv_path.with_name(f"{csv_path.stem}-{index}.csv"))
              for index, (path, (opening, closing)) in enumerate(zip(paths, bounds), start=1)]
    result = {
        "raw_evidence": audits,
        "raw_bars": sum(audit["raw_bars"] for audit in audits),
        "bars": sum(audit["bars"] for audit in audits),
        "expected_bars": sum(audit["expected_bars"] for audit in audits),
        "issues": sorted({issue for audit in audits for issue in audit["issues"]}),
        "status": "valid" if all(audit["status"] == "valid" for audit in audits) else "invalid",
    }
    if result["status"] != "valid":
        csv_path.unlink(missing_ok=True)
        return result
    rows = []
    for audit in audits:
        with Path(audit["csv_path"]).open(newline="", encoding="utf-8") as source:
            rows.extend(csv.DictReader(source))
    if any(datetime.fromisoformat(later["at"]) <= datetime.fromisoformat(earlier["at"])
           for earlier, later in zip(rows, rows[1:])):
        raise ValueError("official session segments are not strictly ordered")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=DATASET_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    result.update(csv_path=str(csv_path), csv_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest())
    return result


def raw_evidence(session: dict) -> list[dict]:
    """Return legacy single raw evidence or every independently preserved segment."""
    return session.get("raw_evidence") or ([session] if session.get("raw_path") else [])


def build_dataset(root: Path, manifest: dict) -> dict:
    """Combine audited sessions, retaining exclusions; this does not qualify trading."""
    destination = root / "audited-bars.csv"
    temporary = destination.with_suffix(".csv.tmp")
    included, excluded, evidence, count = [], [], {}, 0
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        fields = ("at", "open", "high", "low", "close", "volume")
        writer.writerow(fields)
        for day, audit in sorted(manifest["sessions"].items()):
            evidence_items = raw_evidence(audit)
            for item in evidence_items:
                raw_path = Path(item["raw_path"])
                if hashlib.sha256(raw_path.read_bytes()).hexdigest() != item["sha256"]:
                    raise ValueError(f"raw evidence hash changed for {day}; restore the original snapshot")
            if evidence_items:
                evidence[day] = {key: audit[key] for key in ("status", "csv_path", "csv_sha256", "calendar_verified") if key in audit}
                evidence[day]["segments"] = [{key: item[key] for key in ("raw_path", "sha256", "bucket", "uploaded_sha256", "s3_key", "s3_version") if key in item} for item in evidence_items]
            if audit["status"] != "valid":
                excluded.append(day)
                continue
            path = Path(audit["csv_path"])
            if hashlib.sha256(path.read_bytes()).hexdigest() != audit["csv_sha256"]:
                raise ValueError(f"normalized evidence hash changed for {day}; rerun the cache audit")
            with path.open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
                writer.writerows([row[field] for field in fields] for row in rows)
            count += len(rows)
            included.append(day)
    temporary.replace(destination)
    result = {"path": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
              "fields": list(DATASET_FIELDS),
              "bars": count, "included_sessions": included, "excluded_sessions": excluded,
              "instrument": {"nse_symbol": "NIFTYBEES", "breeze_code": "NIFBEE", "exchange": "NSE", "isin": "INF204KB14I2"},
              "timestamp_semantics": "aware Asia/Kolkata five-minute bar start; provider close endpoint excluded; independent label cross-check pending",
              "requested_ranges": manifest.get("requested_ranges", []),
              "coverage": {"first_session": included[0] if included else None, "last_session": included[-1] if included else None, "included_sessions": len(included), "excluded_sessions": len(excluded)},
              "exclusions": {day: manifest["sessions"][day] for day in excluded},
              "calendar": {"missing_years": manifest.get("calendar_gaps", []), "fully_reconciled": False, "scope": "weekday fallback where calendar missing; saved holiday calendars do not establish historical amendments or complete special-session coverage"},
              "raw_evidence": evidence,
              "source_evidence": [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted((root / "reference").glob("*")) if path.is_file()],
              "manifest_sha256": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest() if (root / "manifest.json").exists() else None,
              "corporate_actions": "unadjusted Breeze V2; saved empty NSE response does not establish issuer distributions or adjustment history",
              "execution_costs": "owner brokerage plan, effective tariffs and ETF applicability unverified",
              "qualified_for_trading": False,
              "gaps": ["calendar amendments/special sessions", "corporate-action reconciliation", "execution costs and engine qualification"]}
    reconciliation = root / "reference" / "calendar-reconciliation.json"
    if reconciliation.exists():
        result["calendar"]["reconciliation"] = json.loads(reconciliation.read_text(encoding="utf-8"))
    write_json(root / "dataset-manifest.json", result)
    return result


def verify_dataset(csv_path: Path, manifest_path: Path) -> dict:
    """Verify an aggregate CSV is exactly the admitted dataset in its manifest."""
    csv_path, manifest_path = Path(csv_path), Path(manifest_path)
    dataset = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = dataset.get("sha256")
    actual = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError("aggregate dataset hash does not match its manifest")
    if tuple(dataset.get("fields", DATASET_FIELDS)) != DATASET_FIELDS:
        raise ValueError("dataset manifest has unexpected CSV fields")
    included = set(dataset.get("included_sessions", []))
    excluded = set(dataset.get("excluded_sessions", []))
    if included & excluded:
        raise ValueError("dataset manifest admits and excludes the same session")
    with csv_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != DATASET_FIELDS:
            raise ValueError("aggregate dataset has unexpected CSV fields")
        rows = list(reader)
    timestamps = []
    for row in rows:
        timestamp = datetime.fromisoformat(row["at"])
        timestamps.append(timestamp.replace(tzinfo=IST) if timestamp.tzinfo is None else timestamp.astimezone(IST))
    if any(later <= earlier for earlier, later in zip(timestamps, timestamps[1:])):
        raise ValueError("aggregate timestamps are not strictly increasing")
    dates = {timestamp.date().isoformat() for timestamp in timestamps}
    if dates != included or dates & excluded:
        raise ValueError("aggregate contains bars outside admitted sessions")
    if len(rows) != dataset.get("bars"):
        raise ValueError("aggregate bar count does not match its manifest")
    return {"sha256": actual, "bars": len(rows), "included_sessions": sorted(dates)}


def verify_archive(root: Path) -> dict:
    """Verify all local evidence referenced by the current archive manifests."""
    root = Path(root)
    manifest_path = root / "manifest.json"
    dataset_path = root / "dataset-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if dataset.get("manifest_sha256") != manifest_sha256:
        raise ValueError("dataset manifest does not match the current session manifest")
    aggregate = verify_dataset(root / "audited-bars.csv", dataset_path)
    raw_hashes = normalized_hashes = upload_receipts = 0
    statuses = {}
    for day, session in manifest.get("sessions", {}).items():
        status = session.get("status")
        statuses[status] = statuses.get(status, 0) + 1
        for evidence in raw_evidence(session):
            raw_hashes += 1
            if hashlib.sha256(Path(evidence["raw_path"]).read_bytes()).hexdigest() != evidence.get("sha256"):
                raise ValueError(f"raw evidence hash changed for {day}")
            if evidence.get("uploaded_sha256"):
                if evidence["uploaded_sha256"] != evidence["sha256"]:
                    raise ValueError(f"upload receipt hash differs for {day}")
                upload_receipts += 1
        if status == "valid":
            normalized_hashes += 1
            if hashlib.sha256(Path(session["csv_path"]).read_bytes()).hexdigest() != session.get("csv_sha256"):
                raise ValueError(f"normalized evidence hash changed for {day}")
    source_hashes = 0
    for source in dataset.get("source_evidence", []):
        source_hashes += 1
        if hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest() != source.get("sha256"):
            raise ValueError(f"source evidence hash changed for {source['path']}")
    return {
        "verified_at": datetime.now(IST).isoformat(),
        "manifest": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "dataset": str(root / "audited-bars.csv"),
        "dataset_manifest": str(dataset_path),
        "dataset_bars": aggregate["bars"],
        "dataset_sha256": aggregate["sha256"],
        "sessions": statuses,
        "raw_hashes_verified": raw_hashes,
        "normalized_hashes_verified": normalized_hashes,
        "source_hashes_verified": source_hashes,
        "recorded_upload_receipts": upload_receipts,
        "remote_version_checks": {"status": "not_run", "reason": "local cache verification does not access S3"},
    }
