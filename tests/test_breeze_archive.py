from __future__ import annotations

import json
import hashlib
import csv
import importlib.util
import tempfile
import unittest
from argparse import Namespace
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from stock_research.collectors.breeze_archive import IST, audit_snapshot, build_dataset, build_reconciled_dataset, verify_archive, verify_dataset, write_json


class BreezeArchiveTests(unittest.TestCase):
    def test_reconciled_dataset_is_separate_and_excludes_unreceipted_special_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = {}
            for day, expected in (("2026-10-01", 75), ("2026-10-03", 12)):
                raw = root / "raw" / f"{day}.json"
                raw.parent.mkdir(parents=True, exist_ok=True)
                raw.write_text(day, encoding="utf-8")
                normalized = root / "normalized" / f"{day}.csv"
                normalized.parent.mkdir(parents=True, exist_ok=True)
                start = datetime.fromisoformat(f"{day}T09:15:00+05:30")
                with normalized.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(("at", "open", "high", "low", "close", "volume"))
                    for index in range(expected):
                        writer.writerow(((start + timedelta(minutes=5 * index)).isoformat(), 10, 11, 9, 10, 100))
                raw_hash = hashlib.sha256(raw.read_bytes()).hexdigest()
                normalized_hash = hashlib.sha256(normalized.read_bytes()).hexdigest()
                evidence = {"raw_path": str(raw), "sha256": raw_hash}
                if expected == 75:
                    evidence.update(uploaded_sha256=raw_hash, bucket="archive", s3_key=f"raw/{day}", s3_version="v1")
                sessions[day] = {
                    "status": "valid", "expected_bars": expected, "bars": expected,
                    "csv_path": str(normalized), "csv_sha256": normalized_hash,
                    "calendar_verified": False, "raw_evidence": [evidence],
                }

            source_manifest = {"sessions": sessions, "calendar_gaps": []}
            write_json(root / "manifest.json", source_manifest)
            canonical_csv = root / "audited-bars.csv"
            canonical_manifest = root / "dataset-manifest.json"
            canonical_csv.write_bytes(b"frozen canonical csv\n")
            canonical_manifest.write_bytes(b"stale canonical manifest\n")
            before = (canonical_csv.read_bytes(), canonical_manifest.read_bytes())

            result = build_reconciled_dataset(root, source_manifest)

            self.assertEqual(result["included_sessions"], ["2026-10-01"])
            self.assertEqual(result["excluded_sessions"], ["2026-10-03"])
            self.assertIn("missing a complete matching upload receipt", result["reconciliation"]["excluded_special_sessions"]["2026-10-03"])
            self.assertEqual(result["reconciliation"]["source_manifest_sha256"], hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest())
            self.assertEqual((canonical_csv.read_bytes(), canonical_manifest.read_bytes()), before)
            verify_dataset(root / "reconciled-bars-v1.csv", root / "reconciled-bars-v1-manifest.json")

    def test_atomic_json_write_retries_a_transient_windows_file_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(Path, "replace", side_effect=[PermissionError("locked"), None]) as replace, patch("stock_research.collectors.breeze_archive.sleep") as retry_sleep:
                write_json(Path(temporary) / "manifest.json", {"sessions": {}})
            self.assertEqual(replace.call_count, 2)
            retry_sleep.assert_called_once_with(0.1)

    def test_collector_extracts_only_the_requested_completed_paper_bar(self):
        spec = importlib.util.spec_from_file_location("local_ingest", Path(__file__).resolve().parents[1] / "scripts/run_local_breeze_ingest.py")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except ModuleNotFoundError as error:
            if error.name in ("boto3", "botocore"):
                self.skipTest("AWS optional dependencies are not installed")
            raise
        opening = datetime(2026, 10, 1, 9, 15, tzinfo=IST)
        rows = [{"datetime": (opening + timedelta(minutes=5 * index)).strftime("%Y-%m-%d %H:%M:%S"), "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100, "stock_code": "NIFBEE", "exchange_code": "NSE"} for index in range(3)]
        snapshot = {"request": {"stock_code": "NIFBEE", "exch_code": "NSE", "interval": "5minute"}, "response": {"Success": rows}}
        bar = module.completed_paper_bar(snapshot, from_at=opening, to_at=opening + timedelta(minutes=15))
        self.assertEqual(bar["at"], (opening + timedelta(minutes=10)).isoformat())
        self.assertEqual(bar["close"], 11.0)
        snapshot["response"]["Success"] = rows[:-1]
        with self.assertRaisesRegex(ValueError, "requested completed"):
            module.completed_paper_bar(snapshot, from_at=opening, to_at=opening + timedelta(minutes=15))

    def test_resume_retains_a_provider_gap_without_reading_breeze_credentials(self):
        spec = importlib.util.spec_from_file_location("local_ingest", Path(__file__).resolve().parents[1] / "scripts/run_local_breeze_ingest.py")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except ModuleNotFoundError as error:
            if error.name in ("boto3", "botocore"):
                self.skipTest("AWS optional dependencies are not installed")
            raise
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module.write_json(root / "manifest.json", {"instrument": "NIFTYBEES", "sessions": {"2026-10-01": {"status": "missing", "missing_reason": "provider_empty", "issues": ["saved provider gap"]}}})
            args = Namespace(history_from=date(2026, 10, 1), history_to=date(2026, 10, 1), archive_dir=root, calendar_db=root / "absent.db", audit_cache=True, upload_cache=False, retry_missing=False, bucket=None)
            with patch.object(module, "required_environment", side_effect=AssertionError("must not request credentials")), patch.object(module, "completed_five_minute_candles", side_effect=AssertionError("must not refetch")):
                self.assertEqual(module.collect_history(args), 2)
            self.assertFalse((root / "absent.db").exists())
            self.assertEqual(json.loads((root / "manifest.json").read_text())["sessions"]["2026-10-01"]["status"], "missing")
            # A local audit's absence is not a completed empty provider request.
            saved = json.loads((root / "manifest.json").read_text())
            saved["sessions"]["2026-10-01"] = {"status": "missing", "issues": ["raw snapshot not cached"]}
            module.write_json(root / "manifest.json", saved)
            args.audit_cache, args.bucket = False, "test-bucket"
            uploader = Mock()
            uploader.put_object.return_value = {"VersionId": "manifest-version"}
            with patch.object(module, "required_environment", return_value="dummy"), patch.object(module, "resolve_session_token", return_value="dummy"), patch.object(module, "completed_five_minute_candles", side_effect=RuntimeError("zero candles")) as fetch, patch.object(module, "s3_uploader", return_value=uploader), patch.object(module, "sleep"):
                self.assertEqual(module.collect_history(args), 2)
            fetch.assert_called_once()
            self.assertEqual(json.loads((root / "manifest.json").read_text())["sessions"]["2026-10-01"]["missing_reason"], "provider_empty")

    def test_saved_closure_reclassifies_empty_cache_without_breeze(self):
        spec = importlib.util.spec_from_file_location("local_ingest", Path(__file__).resolve().parents[1] / "scripts/run_local_breeze_ingest.py")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except ModuleNotFoundError as error:
            if error.name in ("boto3", "botocore"):
                self.skipTest("AWS optional dependencies are not installed")
            raise
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module.write_json(root / "manifest.json", {"sessions": {"2026-10-01": {"status": "missing", "missing_reason": "provider_empty"}}})
            module.write_json(root / "reference" / "calendar-reconciliation.json", {"confirmed_regular_closures": {"2026-10-01": {"source": "saved-notice", "sha256": "evidence"}}})
            args = Namespace(history_from=date(2026, 10, 1), history_to=date(2026, 10, 1), archive_dir=root, calendar_db=root / "absent.db", audit_cache=True, upload_cache=False, retry_missing=False, bucket=None)
            with patch.object(module, "completed_five_minute_candles", side_effect=AssertionError("must not refetch")):
                self.assertEqual(module.collect_history(args), 2)
            row = json.loads((root / "manifest.json").read_text())["sessions"]["2026-10-01"]
            self.assertEqual(row["missing_reason"], "exchange_closed")
            self.assertEqual(row["calendar_evidence"]["source"], "saved-notice")

    def test_saved_special_session_needs_explicit_retry_before_fetching(self):
        spec = importlib.util.spec_from_file_location("local_ingest", Path(__file__).resolve().parents[1] / "scripts/run_local_breeze_ingest.py")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except ModuleNotFoundError as error:
            if error.name in ("boto3", "botocore"):
                self.skipTest("AWS optional dependencies are not installed")
            raise
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module.write_json(root / "manifest.json", {"sessions": {"2026-10-01": {"status": "missing", "missing_reason": "provider_empty"}}})
            module.write_json(root / "reference" / "calendar-reconciliation.json", {"known_special_sessions_without_cached_bars": {"2026-10-01": {"source": "saved-notice", "timings": "pending"}}})
            args = Namespace(history_from=date(2026, 10, 1), history_to=date(2026, 10, 1), archive_dir=root, calendar_db=root / "absent.db", audit_cache=True, upload_cache=False, retry_missing=False, bucket=None)
            with patch.object(module, "completed_five_minute_candles", side_effect=AssertionError("must not refetch")):
                self.assertEqual(module.collect_history(args), 2)
            row = json.loads((root / "manifest.json").read_text())["sessions"]["2026-10-01"]
            self.assertEqual(row["missing_reason"], "special_session_unresolved")

    def test_saved_timed_special_session_is_never_fetched_by_regular_audit(self):
        spec = importlib.util.spec_from_file_location("local_ingest", Path(__file__).resolve().parents[1] / "scripts/run_local_breeze_ingest.py")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except ModuleNotFoundError as error:
            if error.name in ("boto3", "botocore"):
                self.skipTest("AWS optional dependencies are not installed")
            raise
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module.write_json(root / "manifest.json", {"sessions": {}})
            module.write_json(root / "reference" / "calendar-reconciliation.json", {"known_special_sessions_without_cached_bars": {"2026-10-01": {"source": "saved-notice", "segments": [["18:00", "19:00"]]}}})
            args = Namespace(history_from=date(2026, 10, 1), history_to=date(2026, 10, 1), archive_dir=root, calendar_db=root / "absent.db", audit_cache=True, upload_cache=False, retry_missing=False, bucket=None)
            with patch.object(module, "completed_five_minute_candles", side_effect=AssertionError("must not refetch")):
                self.assertEqual(module.collect_history(args), 2)
            row = json.loads((root / "manifest.json").read_text())["sessions"]["2026-10-01"]
            self.assertEqual(row["missing_reason"], "special_session_not_fetched")
            args.retry_missing = True
            with patch.object(module, "completed_five_minute_candles", side_effect=AssertionError("cache audit must not fetch")):
                self.assertEqual(module.collect_history(args), 2)
            self.assertEqual(json.loads((root / "manifest.json").read_text())["sessions"]["2026-10-01"]["missing_reason"], "special_session_not_fetched")

    def test_saved_multi_segment_session_is_explicitly_excluded(self):
        spec = importlib.util.spec_from_file_location("local_ingest", Path(__file__).resolve().parents[1] / "scripts/run_local_breeze_ingest.py")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except ModuleNotFoundError as error:
            if error.name in ("boto3", "botocore"):
                self.skipTest("AWS optional dependencies are not installed")
            raise
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module.write_json(root / "manifest.json", {"sessions": {}})
            module.write_json(root / "reference" / "calendar-reconciliation.json", {"known_special_sessions_without_cached_bars": {"2026-10-03": {"source": "saved-notice", "segments": [["09:15", "10:00"], ["11:30", "12:30"]]}}})
            args = Namespace(history_from=date(2026, 10, 3), history_to=date(2026, 10, 3), archive_dir=root, calendar_db=root / "absent.db", audit_cache=True, upload_cache=False, retry_missing=False, bucket=None)
            with patch.object(module, "completed_five_minute_candles", side_effect=AssertionError("must not refetch")):
                self.assertEqual(module.collect_history(args), 2)
            row = json.loads((root / "manifest.json").read_text())["sessions"]["2026-10-03"]
            self.assertEqual(row["missing_reason"], "special_session_multi_segment_not_fetched")
            args.retry_missing, args.audit_cache, args.bucket = True, False, "test-bucket"

            def snapshot_for_segment(_, *, from_at, to_at, **__):
                bars = []
                at = from_at
                while at <= to_at:
                    bars.append({"datetime": at.strftime("%Y-%m-%d %H:%M:%S"), "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100, "stock_code": "NIFBEE", "exchange_code": "NSE"})
                    at += timedelta(minutes=5)
                return {"retrieved_at": "2026-10-04T00:00:00Z", "request": {"stock_code": "NIFBEE", "exch_code": "NSE", "interval": "5minute"}, "response": {"Status": 200, "Success": bars}}

            uploader = Mock()
            uploader.put_object.return_value = {"VersionId": "saved-version"}
            with patch.object(module, "required_environment", return_value="dummy"), patch.object(module, "resolve_session_token", return_value="dummy"), patch.object(module, "completed_five_minute_candles", side_effect=snapshot_for_segment) as fetch, patch.object(module, "s3_uploader", return_value=uploader), patch.object(module, "sleep"):
                self.assertEqual(module.collect_history(args), 2)
            row = json.loads((root / "manifest.json").read_text())["sessions"]["2026-10-03"]
            self.assertEqual((row["status"], row["bars"], len(row["raw_evidence"])), ("valid", 21, 2))
            self.assertEqual(fetch.call_count, 2)
            self.assertTrue(all(Path(item["raw_path"]).is_file() for item in row["raw_evidence"]))
            report = verify_archive(root)
            self.assertEqual((report["raw_hashes_verified"], report["recorded_upload_receipts"]), (2, 2))

    def test_multi_segment_provider_gap_preserves_completed_segment_for_retry(self):
        spec = importlib.util.spec_from_file_location("local_ingest", Path(__file__).resolve().parents[1] / "scripts/run_local_breeze_ingest.py")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except ModuleNotFoundError as error:
            if error.name in ("boto3", "botocore"):
                self.skipTest("AWS optional dependencies are not installed")
            raise
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module.write_json(root / "manifest.json", {"sessions": {}})
            module.write_json(root / "reference" / "calendar-reconciliation.json", {"known_special_sessions_without_cached_bars": {"2026-10-03": {"source": "saved-notice", "segments": [["09:15", "09:25"], ["11:30", "11:40"]]}}})
            args = Namespace(history_from=date(2026, 10, 3), history_to=date(2026, 10, 3), archive_dir=root, calendar_db=root / "absent.db", audit_cache=False, upload_cache=False, retry_missing=True, bucket="test-bucket")

            def snapshot_for_segment(_, *, from_at, to_at, **__):
                bars, at = [], from_at
                while at <= to_at:
                    bars.append({"datetime": at.strftime("%Y-%m-%d %H:%M:%S"), "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100, "stock_code": "NIFBEE", "exchange_code": "NSE"})
                    at += timedelta(minutes=5)
                return {"retrieved_at": "2026-10-04T00:00:00Z", "request": {"stock_code": "NIFBEE", "exch_code": "NSE", "interval": "5minute"}, "response": {"Status": 200, "Success": bars}}

            uploader = Mock()
            uploader.put_object.return_value = {"VersionId": "saved-version"}
            with patch.object(module, "required_environment", return_value="dummy"), patch.object(module, "resolve_session_token", return_value="dummy"), patch.object(module, "completed_five_minute_candles", side_effect=[snapshot_for_segment(None, from_at=datetime(2026, 10, 3, 9, 15, tzinfo=IST), to_at=datetime(2026, 10, 3, 9, 25, tzinfo=IST)), RuntimeError("zero candles")]), patch.object(module, "s3_uploader", return_value=uploader), patch.object(module, "sleep"):
                self.assertEqual(module.collect_history(args), 2)
            row = json.loads((root / "manifest.json").read_text())["sessions"]["2026-10-03"]
            self.assertEqual((row["missing_reason"], len(row["raw_evidence"])), ("provider_empty_segment", 1))
            with patch.object(module, "required_environment", return_value="dummy"), patch.object(module, "resolve_session_token", return_value="dummy"), patch.object(module, "completed_five_minute_candles", side_effect=snapshot_for_segment) as fetch, patch.object(module, "s3_uploader", return_value=uploader), patch.object(module, "sleep"):
                self.assertEqual(module.collect_history(args), 2)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(json.loads((root / "manifest.json").read_text())["sessions"]["2026-10-03"]["status"], "valid")

    def test_archive_preserves_raw_and_rejects_gaps_duplicates_invalid_and_future_bars(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw, csv_path = root / "raw.json", root / "bars.csv"
            opening = datetime(2026, 10, 1, 9, 15, tzinfo=IST)
            closing = opening + timedelta(minutes=375)
            rows = [{"datetime": (opening + timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S"),
                     "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100,
                     "stock_code": "NIFBEE", "exchange_code": "NSE"} for i in range(76)]
            snapshot = {"retrieved_at": "2026-10-02T00:00:00Z", "request": {"stock_code": "NIFBEE", "exch_code": "NSE", "interval": "5minute"}, "response": {"Status": 200, "Success": rows}}
            write_json(raw, snapshot)
            original = raw.read_bytes()
            result = audit_snapshot(raw, opening, closing, csv_path)
            self.assertEqual((result["status"], result["bars"], result["raw_bars"]), ("valid", 75, 76))
            self.assertEqual(raw.read_bytes(), original)
            self.assertEqual(len(csv_path.read_text().splitlines()), 76)
            dataset = build_dataset(root, {"sessions": {"2026-10-01": result, "2026-10-02": {"status": "missing"}}})
            self.assertEqual(dataset["bars"], 75)
            self.assertEqual(dataset["excluded_sessions"], ["2026-10-02"])
            self.assertFalse(dataset["qualified_for_trading"])
            verified = verify_dataset(root / "audited-bars.csv", root / "dataset-manifest.json")
            self.assertEqual(verified["bars"], 75)
            root.joinpath("audited-bars.csv").write_bytes(root.joinpath("audited-bars.csv").read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "hash"):
                verify_dataset(root / "audited-bars.csv", root / "dataset-manifest.json")
            raw.write_bytes(original + b" ")
            with self.assertRaisesRegex(ValueError, "raw evidence hash changed"):
                build_dataset(root, {"sessions": {"2026-10-01": result}})
            raw.write_bytes(original)
            # Cache-only audit/upload must retain existing receipts and avoid Breeze.
            spec = importlib.util.spec_from_file_location("local_ingest", Path(__file__).resolve().parents[1] / "scripts/run_local_breeze_ingest.py")
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except ModuleNotFoundError as error:
                if error.name in ("boto3", "botocore"):
                    self.skipTest("AWS optional dependencies are not installed")
                raise
            archive_raw = root / "raw" / "NIFTYBEES" / "2026-10-01.json"
            write_json(archive_raw, snapshot)
            result = audit_snapshot(archive_raw, opening, closing, root / "normalized" / "NIFTYBEES" / "2026-10-01.csv")
            result.update(uploaded_sha256=result["sha256"], bucket="test-bucket", s3_key="raw/test", s3_version="saved-version")
            write_json(root / "manifest.json", {"requested_ranges": [["2023-10-09", "2026-10-01"]], "sessions": {"2026-10-01": result}})
            args = Namespace(history_from=date(2026, 10, 1), history_to=date(2026, 10, 1), archive_dir=root, calendar_db=root / "absent.db", audit_cache=True, upload_cache=False, retry_missing=False, bucket=None)
            with patch.object(module, "required_environment", side_effect=AssertionError("must not request credentials")), patch.object(module, "completed_five_minute_candles", side_effect=AssertionError("must not refetch")):
                self.assertEqual(module.collect_history(args), 2)
            self.assertEqual(json.loads((root / "manifest.json").read_text())["sessions"]["2026-10-01"]["s3_version"], "saved-version")
            self.assertEqual(json.loads((root / "manifest.json").read_text())["calendar_gaps"], [2023, 2024, 2025, 2026])
            args.audit_cache, args.upload_cache, args.bucket = False, True, "test-bucket"
            uploader = Mock()
            uploader.put_object.return_value = {"VersionId": "manifest-version"}
            with patch.object(module, "required_environment", side_effect=AssertionError("must not request credentials")), patch.object(module, "completed_five_minute_candles", side_effect=AssertionError("must not refetch")), patch.object(module, "s3_uploader", return_value=uploader):
                self.assertEqual(module.collect_history(args), 2)
            self.assertEqual(uploader.put_object.call_count, 1)  # Manifest only, no repeated raw upload.
            for bad_rows in (rows[1:], [rows[0], *rows], [{**rows[0], "volume": -1}, *rows[1:]], [{**rows[0], "close": float("nan")}, *rows[1:]]):
                snapshot["response"]["Success"] = bad_rows
                write_json(raw, snapshot)
                self.assertEqual(audit_snapshot(raw, opening, closing, csv_path)["status"], "invalid")
                self.assertFalse(csv_path.exists())
            snapshot["response"]["Success"] = rows
            snapshot["retrieved_at"] = opening.isoformat()
            write_json(raw, snapshot)
            self.assertEqual(audit_snapshot(raw, opening, closing, csv_path)["status"], "invalid")

    def test_source_backed_non_normal_interval_is_excluded_without_invalidating_normal_bars(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            opening = datetime(2026, 10, 1, 9, 15, tzinfo=IST)
            closing = datetime(2026, 10, 1, 9, 25, tzinfo=IST)
            rows = [{"datetime": at.strftime("%Y-%m-%d %H:%M:%S"), "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100, "stock_code": "NIFBEE", "exchange_code": "NSE"} for at in (opening, opening + timedelta(minutes=5), closing, closing + timedelta(minutes=5))]
            raw = root / "raw.json"
            write_json(raw, {"retrieved_at": "2026-10-02T00:00:00Z", "request": {"stock_code": "NIFBEE", "exch_code": "NSE", "interval": "5minute"}, "response": {"Status": 200, "Success": rows}})
            audit = audit_snapshot(raw, opening, closing, root / "bars.csv", ((closing + timedelta(minutes=5), closing + timedelta(minutes=15)),))
            self.assertEqual((audit["status"], audit["bars"], len(audit["excluded_non_normal_rows"])), ("valid", 2, 1))

    def test_archive_verifier_checks_current_manifest_and_local_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            opening = datetime(2026, 10, 1, 9, 15, tzinfo=IST)
            closing = datetime(2026, 10, 1, 9, 25, tzinfo=IST)
            raw = root / "raw" / "NIFTYBEES" / "2026-10-01.json"
            snapshot = {"retrieved_at": "2026-10-02T00:00:00Z", "request": {"stock_code": "NIFBEE", "exch_code": "NSE", "interval": "5minute"}, "response": {"Status": 200, "Success": [{"datetime": opening.strftime("%Y-%m-%d %H:%M:%S"), "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100, "stock_code": "NIFBEE", "exchange_code": "NSE"}, {"datetime": (opening + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"), "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100, "stock_code": "NIFBEE", "exchange_code": "NSE"}]}}
            write_json(raw, snapshot)
            audit = audit_snapshot(raw, opening, closing, root / "normalized" / "NIFTYBEES" / "2026-10-01.csv")
            audit.update(uploaded_sha256=audit["sha256"], s3_key="raw/NIFTYBEES/example.json", s3_version="version")
            manifest = {"sessions": {"2026-10-01": audit}}
            write_json(root / "manifest.json", manifest)
            build_dataset(root, manifest)
            report = verify_archive(root)
            self.assertEqual(report["dataset_bars"], 2)
            self.assertEqual(report["raw_hashes_verified"], 1)
            self.assertEqual(report["recorded_upload_receipts"], 1)

    def test_uploaded_version_verifier_checks_only_recorded_objects(self):
        spec = importlib.util.spec_from_file_location("local_ingest", Path(__file__).resolve().parents[1] / "scripts/run_local_breeze_ingest.py")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except ModuleNotFoundError as error:
            if error.name in ("boto3", "botocore"):
                self.skipTest("AWS optional dependencies are not installed")
            raise
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            opening = datetime(2026, 10, 1, 9, 15, tzinfo=IST)
            closing = datetime(2026, 10, 1, 9, 25, tzinfo=IST)
            raw = root / "raw" / "NIFTYBEES" / "2026-10-01.json"
            snapshot = {"retrieved_at": "2026-10-02T00:00:00Z", "request": {"stock_code": "NIFBEE", "exch_code": "NSE", "interval": "5minute"}, "response": {"Status": 200, "Success": [{"datetime": opening.strftime("%Y-%m-%d %H:%M:%S"), "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100, "stock_code": "NIFBEE", "exchange_code": "NSE"}, {"datetime": (opening + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"), "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100, "stock_code": "NIFBEE", "exchange_code": "NSE"}]}}
            write_json(raw, snapshot)
            audit = audit_snapshot(raw, opening, closing, root / "normalized" / "NIFTYBEES" / "2026-10-01.csv")
            audit.update(uploaded_sha256=audit["sha256"], bucket="test-bucket", s3_key="raw/NIFTYBEES/example.json", s3_version="raw-version")
            manifest = {"sessions": {"2026-10-01": audit}}
            write_json(root / "manifest.json", manifest)
            build_dataset(root, manifest)
            manifest_hash = hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
            write_json(root / "collection-result.json", {"bucket": "test-bucket", "manifest_s3_key": f"raw/_manifests/{manifest_hash}.json", "manifest_s3_version": "manifest-version"})
            client, session = Mock(), Mock()
            session.client.return_value = client
            client.head_object.side_effect = [{"VersionId": "raw-version", "Metadata": {"sha256": audit["sha256"]}}, {"VersionId": "manifest-version", "Metadata": {"sha256": manifest_hash}}]
            with patch.object(module.boto3, "Session", return_value=session):
                report = module.verify_uploaded_versions(Namespace(archive_dir=root, aws_profile="test"))
            self.assertEqual(report["remote_version_checks"]["raw_versions"], 1)
            self.assertEqual(client.head_object.call_count, 2)


if __name__ == "__main__":
    unittest.main()
