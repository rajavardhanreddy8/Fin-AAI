from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing

from stock_research.nifty_engine import emit_trigger, refresh_announcements
from stock_research.nifty_store import initialize


class AgentBoundaryTests(unittest.TestCase):
    def test_trigger_agent_persists_to_the_eight_column_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "finance.db"
            initialize(db)
            with closing(sqlite3.connect(db)) as connection:
                connection.execute("INSERT INTO securities VALUES(?,?,?,?,?,?,?,?,?)", (
                    "INE000000001", "Test Co", "TEST", None, None, "watchlist", 1,
                    "2026-09-24T00:00:00+00:00", "2026-09-24T00:00:00+00:00",
                ))
                connection.execute("INSERT INTO evidence_snapshots VALUES(?,?,?,?,?,?)", (
                    "evidence-1", "INE000000001", "2026-09-24T00:00:00+00:00",
                    "2026-09-24T00:00:00+00:00", "hash", "{}",
                ))
                emit_trigger(
                    connection, "INE000000001", "daily_move", "2026-09-24", 2,
                    ("valuation",), "evidence-1", "2026-09-24T00:00:00+00:00",
                )
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM research_triggers").fetchone()[0], 1)

    def test_announcement_agent_keeps_only_an_official_location(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "finance.db"
            initialize(db)
            with closing(sqlite3.connect(db)) as connection:
                connection.execute("INSERT INTO securities VALUES(?,?,?,?,?,?,?,?,?)", (
                    "INE000000001", "Test Co", "TEST", None, None, "watchlist", 1,
                    "2026-09-24T00:00:00+00:00", "2026-09-24T00:00:00+00:00",
                ))
                connection.commit()
            rows = [{
                "symbol": "TEST", "an_dt": "24-Sep-2026 16:00:00",
                "attchmntFile": "https://untrusted.example/file.pdf", "desc": "Board update",
            }]
            refresh_announcements(
                db,
                [{"isin": "INE000000001", "symbol": "TEST"}],
                date(2026, 9, 24), date(2026, 9, 24), fetch=lambda _url: str.encode(__import__("json").dumps(rows)),
            )
            with closing(sqlite3.connect(db)) as connection:
                location = connection.execute("SELECT source_location FROM documents").fetchone()[0]
            self.assertEqual(location.split("?")[0], "https://www.nseindia.com/api/corporate-announcements")


if __name__ == "__main__":
    unittest.main()
