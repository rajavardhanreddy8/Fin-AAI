from __future__ import annotations

import csv
from contextlib import closing
import hashlib
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, time, timedelta
from pathlib import Path

from stock_research.intraday_pilot import (
    Bar, ExecutionAssumptions, IST, QPolicy, Snapshot, can_execute_live, compare_holdout,
    initialize_pilot_db, load_bars, load_verified_bars, pilot_status, qualification, record_run, replay,
    snapshots, train_candidate, train_candidate_from_bars,
)
from stock_research.pilot_agents import canonical, digest


def session(day: int = 1) -> list[Bar]:
    start = datetime(2026, 10, day, 9, 15)
    return [Bar(start + timedelta(minutes=5 * index), 100, 101, 99, 100, 10000) for index in range(75)]


def breakout_bars() -> list[Bar]:
    bars = session()
    bars[20] = replace(bars[20], high=103, close=102)
    return bars


class IntradayPilotTests(unittest.TestCase):
    def test_bar_loader_rejects_short_nan_duplicates_and_end_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            path.write_text("at,open,high,low,close,volume\n2026-10-01T09:20:00,1,2,1,2,1\n")
            with self.assertRaisesRegex(ValueError, "35"):
                load_bars(path)
            for bars, message in (([replace(session()[0], open=float("nan")), *session()[1:]], "invalid"), ([session()[0], *session()], "duplicate"), ([*session(), replace(session()[-1], at=datetime(2026, 10, 1, 15, 30))], "bar-start")):
                with path.open("w", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(("at", "open", "high", "low", "close", "volume"))
                    writer.writerows((bar.at.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume) for bar in bars)
                with self.assertRaisesRegex(ValueError, message):
                    load_bars(path)

    def test_verified_loader_requires_matching_archive_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "audited-bars.csv"
            rows = session()
            with csv_path.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("at", "open", "high", "low", "close", "volume"))
                writer.writerows((bar.at.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume) for bar in rows)
            with self.assertRaisesRegex(ValueError, "manifest"):
                load_verified_bars(csv_path)

    def test_true_atr_uses_gaps_and_current_completed_bar(self) -> None:
        bars = session()
        bars[20] = replace(bars[20], open=110, high=111, low=109, close=110)
        state = snapshots(bars)[0]
        self.assertAlmostEqual(state.atr, (2 * 13 + 11) / 14)
        # An unseen future spike cannot change this completed-bar indicator.
        changed = bars[:]
        changed[21] = replace(changed[21], high=1000)
        self.assertEqual(snapshots(changed)[0], state)

    def test_rules_baseline_is_not_q_policy_and_close_decision_fills_later(self) -> None:
        bars = breakout_bars()
        bars[21] = replace(bars[21], open=103, high=104, low=102, close=103)
        bars[22] = replace(bars[22], open=105, high=106, low=104, close=105)
        result = replay(bars)
        self.assertEqual(result.variant, "rules-only")
        self.assertTrue(result.trades)
        self.assertEqual(result.trades[0]["entry_at"], "2026-10-01T11:05:00+05:30")
        self.assertAlmostEqual(result.trades[0]["entry"], 105 * 1.0005)
        self.assertFalse(any(row[6] for row in result))
        self.assertTrue(result[0][5].in_position)
        no_entries = replay(bars, QPolicy({item.state: {"ABSTAIN": 1} for item in snapshots(bars)}))
        self.assertEqual(no_entries.trades, [])

    def test_stop_beats_same_bar_target_and_total_reward_equals_equity_change(self) -> None:
        bars = breakout_bars()
        bars[22] = replace(bars[22], open=102, high=130, low=90, close=102)
        result = replay(bars)
        trade = result.trades[0]
        self.assertEqual(trade["reason"], "stop")
        self.assertLess(trade["net_pnl"], 0)
        self.assertLessEqual(-trade["net_pnl"], 5000 * .0025 + 1e-8)
        self.assertGreater(trade["costs"], 0)
        self.assertAlmostEqual(sum(row[4] for row in result), result.final_state["equity"] - 5000)
        self.assertFalse(result[0][5].in_position)

    def test_opening_target_gap_precedes_intrabar_stop_touch(self) -> None:
        bars = session()
        bars[0] = replace(bars[0], open=125, high=130, low=85, close=125)
        checkpoint = {"cash": 4000, "quantity": 10, "entry": 100, "stop": 90,
                      "target": 120, "entry_at": "2026-10-01T09:15:00+05:30",
                      "high_water": 5000, "day_start": 5000, "equity": 5000,
                      "day": "2026-10-01"}
        trade = replay(bars, initial_state=checkpoint).trades[0]
        self.assertEqual(trade["reason"], "gap-target")
        self.assertEqual(trade["exit_at"], "2026-10-01T09:15:00+05:30")
        self.assertAlmostEqual(trade["exit"], 120 * (1 - .0005))

    def test_stop_gap_uses_adverse_open_not_stop_and_latches_pause(self) -> None:
        bars = breakout_bars()
        bars[22] = replace(bars[22], open=102, high=103, low=101, close=102)
        # The planned trade risk cannot limit an actual catastrophic gap.
        bars[23] = replace(bars[23], open=1, high=2, low=1, close=1)
        for index in range(24, len(bars)):
            bars[index] = replace(bars[index], open=100, high=120, low=99, close=110)
        # Force sufficient exposure from a prior checkpoint to exercise 5% pause.
        checkpoint = {"cash": 0, "quantity": 50, "entry": 100, "stop": 90, "target": 120, "entry_at": "2026-09-30T14:00:00+05:30", "high_water": 5000, "day_start": 5000, "equity": 5000, "day": "2026-10-01"}
        result = replay(bars, initial_state=checkpoint)
        self.assertTrue(result.final_state["paused"])
        self.assertEqual(result.final_state["quantity"], 0)
        self.assertEqual(len(result.trades), 1)
        self.assertLess(result.trades[0]["exit"], 90)
        resumed = replay(session(2), initial_state=result.final_state)
        self.assertTrue(resumed.final_state["paused"])
        self.assertFalse(resumed.trades)

    def test_daily_loss_blocks_before_purchase_even_after_prices_recover(self) -> None:
        bars = breakout_bars()
        checkpoint = {"cash": 4949, "equity": 4949, "high_water": 5000, "day_start": 5000, "day": "2026-10-01"}
        result = replay(bars, initial_state=checkpoint)
        self.assertEqual(result.trades, [])
        self.assertEqual(result.final_state["cash"], 4949)
        self.assertTrue(result.final_state["daily_loss_blocked"])
        self.assertFalse(result.final_state["paused"])

    def test_entries_blocked_at_1500_and_liquidation_begins_1515(self) -> None:
        bars = breakout_bars()
        # Keep the breakout entry above its protective stop through 15:15.
        for index in range(21, len(bars)):
            bars[index] = replace(bars[index], open=102, high=103, low=101, close=102)
        result = replay(bars)
        self.assertEqual(result.trades[0]["reason"], "session-liquidation")
        self.assertEqual(result.trades[0]["exit_at"], "2026-10-01T15:15:00+05:30")
        late = session()
        late[68] = replace(late[68], high=104, close=103)  # 14:55 completed at 15:00.
        self.assertFalse(replay(late, assumptions=ExecutionAssumptions(decision_latency_seconds=0)).trades)

    def test_gap_cancels_pending_entry_and_terminal_never_invents_fill(self) -> None:
        bars = breakout_bars()
        del bars[21]
        result = replay(bars)
        self.assertFalse(result.trades)
        self.assertTrue(any("missing five-minute" in item for item in result.defects))
        self.assertTrue(result.final_state["daily_loss_blocked"])
        # A later breakout cannot trade on this incomplete session.
        bars[30] = replace(bars[30], high=110, close=109)
        self.assertFalse(replay(bars).trades)
        cut = breakout_bars()[:35]
        for index in range(21, len(cut)):
            cut[index] = replace(cut[index], open=102, high=103, low=101, close=102)
        result = replay(cut)
        self.assertEqual(result.final_state["quantity"], 2)
        self.assertFalse(result.trades)
        self.assertTrue(any("end of data" in item for item in result.defects))
        open_result = replay(cut, terminal=False)
        self.assertFalse(any("end of data" in item for item in open_result.defects))
        self.assertFalse(any(open_result.terminal))
        # Continuous rebuild extends the prefix without an end-of-prefix close.
        full = [*cut, *breakout_bars()[35:]]
        continued = replay(full, terminal=False)
        self.assertEqual(len(continued.trades), 1)
        self.assertEqual(continued.trades[0]["reason"], "session-liquidation")

    def test_partial_and_gapped_sessions_are_explicitly_incomplete(self) -> None:
        partial = replay(session()[:40])
        self.assertFalse(partial.sessions[0]["complete"])
        self.assertEqual(partial.sessions[0]["observed_bars"], 40)
        self.assertTrue(any("incomplete session" in defect for defect in partial.defects))
        prefix = replay(session()[:40], terminal=False)
        self.assertFalse(prefix.sessions[0]["complete"])
        self.assertFalse(any("incomplete session" in defect for defect in prefix.defects))
        full = replay(session())
        self.assertTrue(full.sessions[0]["complete"])
        self.assertEqual(full.sessions[0]["observed_bars"], 75)
        gapped = session()
        del gapped[21]
        self.assertFalse(replay(gapped).sessions[0]["complete"])
        resumed = replay(session(), initial_state={"last_at": "2026-10-01T11:55:00+05:30", "day": "2026-10-01", "open_decision": False})
        self.assertFalse(resumed.sessions[0]["complete"])

    def test_source_backed_special_session_is_complete_but_execution_blocked(self) -> None:
        special = [replace(session(2)[0], at=datetime(2026, 10, 2, 13, 45) + timedelta(minutes=5 * index)) for index in range(12)]
        result = replay([*session(), *special], session_windows={"2026-10-02": (time(13, 45), time(14, 45))})
        recorded = result.sessions[-1]
        self.assertTrue(recorded["complete"])
        self.assertTrue(recorded["special_session"])
        self.assertFalse(any("2026-10-02" in defect for defect in result.defects))

    def test_source_backed_multi_segment_session_allows_only_its_official_gap(self) -> None:
        starts = (datetime(2026, 10, 2, 9, 15), datetime(2026, 10, 2, 11, 30))
        special = [replace(session(2)[0], at=start + timedelta(minutes=5 * index)) for start, count in zip(starts, (9, 12)) for index in range(count)]
        result = replay([*session(), *special], session_schedules={"2026-10-02": ((time(9, 15), time(10)), (time(11, 30), time(12, 30)))})
        recorded = result.sessions[-1]
        self.assertEqual((recorded["complete"], recorded["observed_bars"], recorded["special_session"]), (True, 21, True))
        self.assertFalse(any("2026-10-02" in defect for defect in result.defects))

    def test_open_hold_decision_cannot_disappear_on_checkpoint_resume(self) -> None:
        prefix = replay(session()[:35], terminal=False)
        self.assertIsNone(prefix.final_state["pending"])
        self.assertTrue(prefix.final_state["open_decision"])
        with self.assertRaisesRegex(ValueError, "open decisions"):
            replay(session(), initial_state=prefix.final_state)
        with self.assertRaisesRegex(ValueError, "legacy checkpoint"):
            replay(session(), initial_state={"last_at": prefix.final_state["last_at"]})
        complete = replay(session(), terminal=False)
        self.assertFalse(complete.final_state["open_decision"])
        replay(session(2), initial_state=complete.final_state)

    def test_evaluation_window_warms_indicators_without_prior_trades_or_model_calls(self) -> None:
        later = session(2)
        later[20] = replace(later[20], high=103, close=102)
        bars = [*breakout_bars(), *later]
        start = later[0].at
        seen = []
        def decide(evidence: dict, rl_action: str | None) -> str:
            seen.append(evidence["bar"]["at"])
            return evidence["rules_action"]
        result = replay(bars, decide=decide, entry_start_at=start)
        self.assertEqual(len(result.trades), 1)
        self.assertTrue(all(trade["entry_at"][:10] == "2026-10-02" for trade in result.trades))
        self.assertTrue(all(at[:10] == "2026-10-02" for at in seen))
        self.assertEqual(result.entry_start_at, start.replace(tzinfo=IST).isoformat())
        self.assertEqual(result.sessions[0]["completed_trades"], 0)
        with self.assertRaisesRegex(ValueError, "evaluation start"):
            replay(bars, entry_start_at=start + timedelta(minutes=1))
        with self.assertRaisesRegex(ValueError, "evaluation start"):
            replay(bars, entry_start_at=start + timedelta(minutes=5))
        with self.assertRaisesRegex(ValueError, "evaluation start"):
            replay(bars, entry_start_at=start, initial_state={"cash": 5000})

    def test_models_cannot_invent_entry_and_exceptions_fail_closed(self) -> None:
        evidence = []
        def buy_everything(item: dict, action: str | None) -> str:
            evidence.append(item)
            return "BUY"
        self.assertFalse(replay(session(), decide=buy_everything).trades)
        self.assertIn("decision_at", evidence[0])
        def broken(item: dict, action: str | None) -> str:
            raise TimeoutError("timeout")
        result = replay(breakout_bars(), decide=broken)
        self.assertFalse(result.trades)
        self.assertTrue(result.defects)

    def test_learning_rewards_match_only_unchanged_execution_and_mark_hold_periods(self) -> None:
        bars = breakout_bars()
        for index in range(21, len(bars)):
            bars[index] = replace(bars[index], open=102, high=103, low=101, close=102)
        bars[23] = replace(bars[23], close=103)
        policy = QPolicy()
        state = snapshots(bars)[0]
        policy.values[state.state] = {"BUY": 1}
        for snap in snapshots(bars):
            for sign in (-1, 1):
                policy.values[replace(snap, in_position=True, unrealized=sign).state] = {"HOLD": 1}
        result = replay(bars, policy)
        buy = next(row for row in result if row[3] == "BUY")
        self.assertTrue(buy[6])
        self.assertTrue(buy[5].in_position)
        self.assertTrue(any(row[3] == "HOLD" and row[4] > 0 and row[6] for row in result))
        liquidation = next(row for row in result if row[3] == "SELL")
        self.assertFalse(liquidation[6])
        overridden = replay(bars, policy, decide=lambda evidence, action: "ABSTAIN")
        self.assertFalse(any(row[6] for row in overridden if row[1] == "BUY"))
        self.assertAlmostEqual(sum(row[4] for row in result), result.final_state["equity"] - 5000)

    def test_seeded_training_explores_only_training_and_terminal_has_no_bootstrap(self) -> None:
        bars = breakout_bars()
        first = replay(bars, QPolicy(), training=True, seed=42)
        second = replay(bars, QPolicy(), training=True, seed=42)
        self.assertEqual(first, second)
        self.assertNotEqual([row[1] for row in first], [row[1] for row in replay(bars, QPolicy())])
        policy = QPolicy({"TERMINAL": {"BUY": 1000}})
        policy.update("0:0:0:0:1:0:0", "BUY", 3, "TERMINAL")
        self.assertAlmostEqual(policy.values["0:0:0:0:1:0:0"]["BUY"], .3)

    def test_bars_training_freezes_holdout_and_never_replaces_active_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path, db_path = root / "audited-bars.csv", root / "pilot.db"
            bars = [*breakout_bars(), *(bar for day in range(2, 6) for bar in session(day))]
            def write_dataset() -> None:
                with csv_path.open("w", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(("at", "open", "high", "low", "close", "volume"))
                    writer.writerows((bar.at.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume) for bar in bars)
                root.joinpath("dataset-manifest.json").write_text(json.dumps({
                    "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                    "bars": len(bars), "included_sessions": [f"2026-10-{day:02d}" for day in range(1, 6)],
                    "excluded_sessions": []}), encoding="utf-8")
            write_dataset()
            first = train_candidate_from_bars(db_path, csv_path, "candidate-a", seed=7)
            second = train_candidate_from_bars(db_path, csv_path, "candidate-b", seed=7)
            self.assertEqual(first.values, second.values)
            with closing(sqlite3.connect(db_path)) as db:
                metadata = json.loads(db.execute("SELECT metadata_json FROM pilot_policies WHERE version='candidate-a'").fetchone()[0])
                self.assertEqual((metadata["train_last"], metadata["holdout_first"]), ("2026-10-03", "2026-10-05"))
                self.assertGreater(metadata["matched_transitions"], 0)
                db.execute("UPDATE pilot_policies SET status='active' WHERE version='candidate-a'")
                db.commit()
            partial = compare_holdout(db_path, csv_path, "candidate-a")
            self.assertEqual(set(partial["variants"]), {"rules-only", "rl-only"})
            self.assertTrue(any("Jev decision" in gap for gap in partial["qualification_gaps"]))
            evaluation_bars = load_bars(csv_path)
            def capture(policy: QPolicy | None) -> dict[str, str]:
                actions: dict[str, str] = {}
                def decide(evidence: dict, rl_action: str | None) -> str:
                    key = digest(canonical({"evidence": evidence, "rl_action": rl_action}))
                    action = evidence["rules_action"] if policy is None else rl_action or "ABSTAIN"
                    actions[key] = action
                    return action
                replay(evaluation_bars, policy, decide=decide, entry_start_at=evaluation_bars[300].at)
                return actions
            jev, rl_jev = capture(None), capture(first)
            comparison = compare_holdout(db_path, csv_path, "candidate-a", jev_actions=jev, rl_jev_actions=rl_jev)
            self.assertEqual(set(comparison["variants"]), {"rules-only", "jev-only", "rl-only", "rl+jev"})
            self.assertFalse(comparison["qualified"])
            self.assertEqual(comparison["model_decision_provenance"], "caller-supplied-unverified")
            self.assertTrue(pilot_status(db_path)["comparison"]["intact"])
            with closing(sqlite3.connect(db_path)) as db:
                self.assertEqual(db.execute("SELECT policy_version,dataset_sha256 FROM pilot_comparisons WHERE comparison_id=?", (comparison["comparison_id"],)).fetchone()[0], "candidate-a")
                original_metadata = db.execute("SELECT metadata_json FROM pilot_policies WHERE version='candidate-a'").fetchone()[0]
                db.execute("UPDATE pilot_policies SET metadata_json='{}' WHERE version='candidate-a'")
                self.assertTrue(any("invalid frozen" in item for item in qualification(db)[1]))
                db.execute("UPDATE pilot_policies SET metadata_json=? WHERE version='candidate-a'", (original_metadata,))
                db.execute("UPDATE pilot_comparisons SET report_json='{}' WHERE comparison_id=?", (comparison["comparison_id"],))
                db.commit()
                self.assertTrue(any("invalid frozen" in item for item in qualification(db)[1]))
            self.assertFalse(pilot_status(db_path)["comparison"]["intact"])
            self.assertEqual(comparison["variants"]["rules-only"], partial["variants"]["rules-only"])
            missing = dict(jev)
            missing.pop(next(iter(missing)))
            with self.assertRaisesRegex(ValueError, "missing or invalid frozen"):
                compare_holdout(db_path, csv_path, "candidate-a", jev_actions=missing, rl_jev_actions=rl_jev)
            with self.assertRaisesRegex(ValueError, "assumptions changed"):
                compare_holdout(db_path, csv_path, "candidate-a", assumptions=ExecutionAssumptions(fee_bps=20))
            bars[-1] = replace(bars[-1], high=500, close=300)
            write_dataset()
            with self.assertRaisesRegex(ValueError, "dataset, split"):
                compare_holdout(db_path, csv_path, "candidate-a")
            third = train_candidate_from_bars(db_path, csv_path, "candidate-c", seed=7)
            self.assertEqual(first.values, third.values)
            with closing(sqlite3.connect(db_path)) as db:
                self.assertEqual(db.execute("SELECT status,values_json FROM pilot_policies WHERE version='candidate-a'").fetchone(), ("active", first.to_json()))
            with self.assertRaisesRegex(ValueError, "already exists"):
                train_candidate_from_bars(db_path, csv_path, "candidate-a", seed=7)
            del bars[75 + 21]
            write_dataset()
            with self.assertRaisesRegex(ValueError, "incomplete or defective"):
                train_candidate_from_bars(db_path, csv_path, "candidate-d", seed=7)
            csv_path.write_bytes(csv_path.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "hash"):
                train_candidate_from_bars(db_path, csv_path, "candidate-d")

    def test_holdout_ignores_defects_before_its_warmup_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path, db_path = root / "audited-bars.csv", root / "pilot.db"
            bars = [bar for day in range(1, 11) for bar in session(day)]
            del bars[6 * 75 + 20]  # A validation-session gap must not taint the untouched holdout.
            with csv_path.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("at", "open", "high", "low", "close", "volume"))
                writer.writerows((bar.at.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume) for bar in bars)
            root.joinpath("dataset-manifest.json").write_text(json.dumps({
                "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(), "bars": len(bars),
                "included_sessions": [f"2026-10-{day:02d}" for day in range(1, 11)], "excluded_sessions": []}), encoding="utf-8")
            train_candidate_from_bars(db_path, csv_path, "candidate-boundary", seed=7)
            report = compare_holdout(db_path, csv_path, "candidate-boundary")
            self.assertEqual(report["holdout_first"], "2026-10-09")
            self.assertEqual(set(report["variants"]), {"rules-only", "rl-only"})

    def test_database_migration_trades_sessions_training_and_live_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pilot.db"
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE pilot_transitions (run_id TEXT NOT NULL, at TEXT NOT NULL, state TEXT NOT NULL, rl_action TEXT NOT NULL, jev_action TEXT, executed_action TEXT NOT NULL, reward REAL NOT NULL, next_state TEXT NOT NULL, execution_matched_rl INTEGER NOT NULL, PRIMARY KEY(run_id,at))")
                db.execute("CREATE TABLE pilot_policies (version TEXT PRIMARY KEY, status TEXT NOT NULL, trained_at TEXT NOT NULL, values_json TEXT NOT NULL, source_run_id TEXT)")
                db.execute("INSERT INTO pilot_policies VALUES('prior-active','active','2026-10-01','{}',NULL)")
            initialize_pilot_db(path)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("SELECT status,metadata_json FROM pilot_policies WHERE version='prior-active'").fetchone(), ("active", None))
            bars = breakout_bars()
            result = replay(bars)
            summary = record_run(path, "paper-replay", "paper", None, result)
            self.assertEqual(summary["provenance"], "historical-replay")
            self.assertEqual(summary["policy"], "rules-only")
            with self.assertRaisesRegex(ValueError, "no verified"):
                train_candidate(path, "paper-replay", "candidate")
            policy = QPolicy()
            record_run(path, "rl", "backtest", policy, replay(bars, policy))
            trained = train_candidate(path, "rl", "candidate")
            self.assertTrue(trained.values)
            with closing(sqlite3.connect(path)) as db, db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM pilot_trades WHERE run_id='paper-replay'").fetchone()[0], len(result.trades))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM pilot_sessions").fetchone()[0], 2)
                self.assertEqual(db.execute("SELECT observed_bars,complete FROM pilot_sessions WHERE run_id='paper-replay'").fetchone(), (75, 1))
                self.assertEqual(db.execute("SELECT status FROM pilot_policies WHERE version='candidate'").fetchone()[0], "candidate")
                db.execute("UPDATE pilot_policies SET status='active' WHERE version='candidate'")
                db.execute("UPDATE pilot_activation SET live_enabled=1")
                db.execute("UPDATE pilot_runs SET status='qualified'")
                db.execute("UPDATE pilot_sessions SET provenance='forward-paper-verified', complete=1")
                ready, reasons = qualification(db)
                self.assertFalse(ready)
                self.assertTrue(any("holdout" in item for item in reasons))
                self.assertTrue(any("pilot replay rows are historical" in item for item in reasons))
                self.assertFalse(can_execute_live(db)[0])
            with self.assertRaisesRegex(ValueError, "already exists"):
                train_candidate(path, "rl", "candidate")


if __name__ == "__main__":
    unittest.main()
