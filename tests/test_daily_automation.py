from __future__ import annotations

import json
from contextlib import closing
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from stock_research.daily_automation import phase_gate, run_phase


IST = timezone(timedelta(hours=5, minutes=30))
CALENDAR = {"year": 2026, "holidays": ["2026-09-25"], "special_sessions": {}}


class DailyAutomationTests(unittest.TestCase):
    def test_exchange_clock_prevents_hindsight_and_holiday_runs(self) -> None:
        self.assertIsNone(phase_gate("pre", datetime(2026, 9, 24, 8, 30, tzinfo=IST), CALENDAR))
        self.assertEqual(phase_gate("pre", datetime(2026, 9, 24, 9, 15, tzinfo=IST), CALENDAR),
                         "after_market_open")
        self.assertEqual(phase_gate("post", datetime(2026, 9, 24, 15, 40, tzinfo=IST), CALENDAR),
                         "before_completed_close")
        self.assertIsNone(phase_gate("post", datetime(2026, 9, 24, 17, tzinfo=IST), CALENDAR))
        self.assertEqual(phase_gate("pre", datetime(2026, 9, 25, 8, 30, tzinfo=IST), CALENDAR),
                         "exchange_closed")

    def test_late_run_is_recorded_once_without_fetching_market_data(self) -> None:
        now = datetime(2026, 9, 24, 11, tzinfo=IST)
        with tempfile.TemporaryDirectory() as temp, patch(
            "stock_research.daily_automation._calendar", return_value=CALENDAR
        ), patch("stock_research.daily_automation._membership") as membership:
            db = Path(temp) / "daily.db"
            first = run_phase("pre", db=db, now=now)
            second = run_phase("pre", db=db, now=now)
            self.assertEqual(first["status"], "skipped")
            self.assertEqual(first["reason"], "after_market_open")
            self.assertEqual(second["runKey"], first["runKey"])
            membership.assert_not_called()
            with closing(sqlite3.connect(db)) as connection:
                self.assertEqual(connection.execute("SELECT attempts FROM automation_runs").fetchone()[0], 1)
            saved = json.loads(Path(first["reportPath"]).read_text(encoding="utf-8"))
            self.assertEqual(saved["reason"], "after_market_open")


if __name__ == "__main__":
    unittest.main()
