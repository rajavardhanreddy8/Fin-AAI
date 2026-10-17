from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("paper_session", Path(__file__).parents[1] / "scripts/run_paper_session.py")
paper_session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paper_session)


class PaperSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.bar = self.path / "handoff.json"
        self.report = self.path / "report.json"

    def payload(self):
        return {"at": "2026-10-15T09:15:00+05:30", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}

    def test_waiting_does_not_create_a_paper_run(self):
        self.assertEqual(paper_session.consume(self.bar, report=self.report, runner_args=[]), 0)
        self.assertEqual(json.loads(self.report.read_text())["status"], "waiting")

    def test_successful_delivery_archives_handoff_and_restarts_are_idempotent(self):
        self.bar.write_text(json.dumps(self.payload()), encoding="utf-8")
        result = type("Result", (), {"returncode": 0, "stdout": '{"status":"ok"}', "stderr": ""})()
        with patch.object(paper_session.subprocess, "run", return_value=result) as run:
            self.assertEqual(paper_session.consume(self.bar, report=self.report, runner_args=["--run-id", "forward-20261015"]), 0)
        self.assertFalse(self.bar.exists())
        self.assertTrue((self.path / "processed" / "handoff.json").exists())
        self.assertEqual(json.loads(self.report.read_text())["status"], "processed")
        run.assert_called_once()
        self.assertEqual(paper_session.consume(self.bar, report=self.report, runner_args=[]), 0)

    def test_runner_failure_retains_handoff_for_recovery(self):
        self.bar.write_text(json.dumps(self.payload()), encoding="utf-8")
        result = type("Result", (), {"returncode": 2, "stdout": '{"status":"blocked"}', "stderr": ""})()
        with patch.object(paper_session.subprocess, "run", return_value=result):
            self.assertEqual(paper_session.consume(self.bar, report=self.report, runner_args=[]), 2)
        self.assertTrue(self.bar.exists())
        self.assertEqual(json.loads(self.report.read_text())["status"], "blocked")

    def test_overlapping_consumer_is_rejected_without_touching_handoff(self):
        self.bar.write_text(json.dumps(self.payload()), encoding="utf-8")
        self.report.parent.mkdir(parents=True, exist_ok=True)
        self.report.with_suffix(self.report.suffix + ".lock").write_text("busy", encoding="utf-8")
        self.assertEqual(paper_session.consume(self.bar, report=self.report, runner_args=[]), 2)
        self.assertTrue(self.bar.exists())

    def test_explicit_frozen_policy_is_forwarded(self):
        with patch.object(paper_session, "consume", return_value=0) as consume:
            self.assertEqual(paper_session.main(["--bar", str(self.bar), "--run-id", "forward-20261016",
                                                 "--policy-db", "pilot.db", "--policy-version", "candidate-v1"]), 0)
        self.assertIn("--policy-db", consume.call_args.kwargs["runner_args"])
        self.assertIn("candidate-v1", consume.call_args.kwargs["runner_args"])
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            paper_session.main(["--bar", str(self.bar), "--run-id", "forward-20261016", "--policy-db", "pilot.db"])


if __name__ == "__main__":
    unittest.main()
