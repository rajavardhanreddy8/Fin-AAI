"""Deterministic, rules-controlled NIFTYBEES simulation. No live broker execution."""
from __future__ import annotations

import csv
from contextlib import closing
import hashlib
import json
import math
import re
import random
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Literal

Action = Literal["BUY", "ABSTAIN", "HOLD", "SELL"]
Mode = Literal["backtest", "paper", "live"]
INSTRUMENT = "NIFTYBEES"
INITIAL_CASH = 5000.0
MAX_DRAWDOWN = 0.05
MAX_DAILY_LOSS = 0.01
RISK_PER_TRADE = 0.0025
JEV_MONTHLY_CAP_INR = 300.0
IST = timezone(timedelta(hours=5, minutes=30))
BAR_INTERVAL = timedelta(minutes=5)
ACTIONS = ("BUY", "ABSTAIN", "HOLD", "SELL")


@dataclass(frozen=True)
class Bar:
    at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Snapshot:
    bar: Bar
    breakout: bool
    above_vwap: bool
    atr: float
    trend: int
    volatility: int
    session: int
    in_position: bool
    unrealized: int

    @property
    def state(self) -> str:
        return ":".join(map(str, (self.trend, self.volatility, int(self.breakout), int(self.above_vwap), self.session, int(self.in_position), self.unrealized)))


@dataclass(frozen=True)
class ExecutionAssumptions:
    """Sensitivity inputs, NOT verified ICICI tariffs or observed fills."""
    fee_bps: float = 10.0
    minimum_fee_inr: float = 1.0
    slippage_bps: float = 5.0
    decision_latency_seconds: float = 1.0
    participation_rate: float = 0.01

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(not math.isfinite(value) or value < 0 for value in values.values()):
            raise ValueError("execution assumptions must be finite and nonnegative")
        if not 0 < self.participation_rate <= 1:
            raise ValueError("participation_rate must be in (0, 1]")
        if self.slippage_bps >= 10000:
            raise ValueError("slippage must be below 100 percent")

    def fee(self, value: float) -> float:
        return max(self.minimum_fee_inr, value * self.fee_bps / 10000)


Transition = tuple[Snapshot, Action, Action | None, Action, float, Snapshot, bool]


class ReplayResult(list[Transition]):
    """Legacy transition list with the execution evidence needed by record_run."""
    def __init__(self, assumptions: ExecutionAssumptions) -> None:
        super().__init__()
        self.trades: list[dict] = []
        self.sessions: list[dict] = []
        self.final_state: dict = {}
        self.defects: list[str] = []
        self.terminal: list[bool] = []
        self.assumptions = asdict(assumptions)
        self.max_drawdown = 0.0
        self.costs_inr = 0.0
        self.variant = "rules-only"
        self.provenance = "historical-replay"
        self.entry_start_at: str | None = None


class QPolicy:
    """Seeded tabular learner; exploration is enabled only during training."""
    def __init__(self, values: dict[str, dict[str, float]] | None = None) -> None:
        self.values = values or {}
        self._random = random.Random(42)
        self.version = "unversioned"

    def choose(self, snapshot: Snapshot, explore: float = 0.0) -> Action:
        allowed: tuple[Action, ...] = ("HOLD", "SELL") if snapshot.in_position else ("BUY", "ABSTAIN")
        if explore and self._random.random() < explore:
            return self._random.choice(allowed)
        scores = self.values.get(snapshot.state, {})
        return max(allowed, key=lambda action: (scores.get(action, 0.0), action))

    def update(self, state: str, action: Action, reward: float, next_state: str, *, alpha: float = 0.1, gamma: float = 0.99) -> None:
        row = self.values.setdefault(state, {})
        current = row.get(action, 0.0)
        allowed = ("HOLD", "SELL") if next_state != "TERMINAL" and next_state.split(":")[5] == "1" else ("BUY", "ABSTAIN")
        future = 0.0 if next_state == "TERMINAL" else max((self.values.get(next_state, {}).get(item, 0.0) for item in allowed), default=0.0)
        row[action] = current + alpha * (reward + gamma * future - current)

    def to_json(self) -> str:
        return json.dumps(self.values, sort_keys=True, allow_nan=False)

    @classmethod
    def from_json(cls, raw: str) -> "QPolicy":
        values = json.loads(raw)
        if not isinstance(values, dict) or any(not isinstance(row, dict) or any(action not in ACTIONS or isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) for action, score in row.items()) for row in values.values()):
            raise ValueError("invalid Q-policy values")
        return cls(values)


def initialize_pilot_db(path: str | Path) -> None:
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS pilot_runs (
          run_id TEXT PRIMARY KEY, mode TEXT NOT NULL, policy_version TEXT NOT NULL,
          created_at TEXT NOT NULL, status TEXT NOT NULL, summary_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pilot_transitions (
          run_id TEXT NOT NULL, at TEXT NOT NULL, state TEXT NOT NULL, rl_action TEXT NOT NULL,
          jev_action TEXT, executed_action TEXT NOT NULL, reward REAL NOT NULL,
          next_state TEXT NOT NULL, execution_matched_rl INTEGER NOT NULL,
          PRIMARY KEY(run_id, at)
        );
        CREATE TABLE IF NOT EXISTS pilot_policies (
          version TEXT PRIMARY KEY, status TEXT NOT NULL, trained_at TEXT NOT NULL,
          values_json TEXT NOT NULL, source_run_id TEXT, metadata_json TEXT
        );
        CREATE TABLE IF NOT EXISTS pilot_activation (
          singleton INTEGER PRIMARY KEY CHECK(singleton=1), live_enabled INTEGER NOT NULL DEFAULT 0,
          activated_at TEXT, reason TEXT
        );
        INSERT OR IGNORE INTO pilot_activation(singleton, live_enabled) VALUES(1, 0);
        CREATE TABLE IF NOT EXISTS pilot_trades (
          run_id TEXT NOT NULL, trade_number INTEGER NOT NULL, entry_at TEXT NOT NULL,
          exit_at TEXT NOT NULL, quantity INTEGER NOT NULL, entry REAL NOT NULL,
          exit REAL NOT NULL, costs REAL NOT NULL, net_pnl REAL NOT NULL, reason TEXT NOT NULL,
          PRIMARY KEY(run_id, trade_number)
        );
        CREATE TABLE IF NOT EXISTS pilot_sessions (
          run_id TEXT NOT NULL, session_date TEXT NOT NULL, start_equity REAL NOT NULL,
          end_equity REAL NOT NULL, completed_trades INTEGER NOT NULL,
          provenance TEXT NOT NULL, first_at TEXT, last_at TEXT,
          observed_bars INTEGER, complete INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(run_id, session_date)
        );
        CREATE TABLE IF NOT EXISTS pilot_checkpoints (
          run_id TEXT PRIMARY KEY, state_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pilot_comparisons (
          comparison_id TEXT PRIMARY KEY, policy_version TEXT NOT NULL,
          dataset_sha256 TEXT NOT NULL, created_at TEXT NOT NULL, report_json TEXT NOT NULL
        );
        """)
        columns = {row[1] for row in db.execute("PRAGMA table_info(pilot_transitions)")}
        if "terminal" not in columns:
            db.execute("ALTER TABLE pilot_transitions ADD COLUMN terminal INTEGER NOT NULL DEFAULT 0")
        # Old transitions had incomplete next-position/reward attribution. Retain them,
        # but never train on them as if the new engine had generated them.
        if "engine_version" not in columns:
            db.execute("ALTER TABLE pilot_transitions ADD COLUMN engine_version INTEGER NOT NULL DEFAULT 1")
        session_columns = {row[1] for row in db.execute("PRAGMA table_info(pilot_sessions)")}
        for name, definition in (("first_at", "TEXT"), ("last_at", "TEXT"), ("observed_bars", "INTEGER"), ("complete", "INTEGER NOT NULL DEFAULT 0")):
            if name not in session_columns:
                db.execute(f"ALTER TABLE pilot_sessions ADD COLUMN {name} {definition}")
        if "metadata_json" not in {row[1] for row in db.execute("PRAGMA table_info(pilot_policies)")}:
            db.execute("ALTER TABLE pilot_policies ADD COLUMN metadata_json TEXT")


def _validated_bars(bars: list[Bar], *, minimum: int = 35) -> list[Bar]:
    normalized: list[Bar] = []
    for bar in bars:
        at = bar.at.replace(tzinfo=IST) if bar.at.tzinfo is None else bar.at.astimezone(IST)
        values = (bar.open, bar.high, bar.low, bar.close, bar.volume)
        if any(not math.isfinite(value) for value in values) or min(values[:4]) <= 0 or bar.volume < 0 or bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close) or bar.high < bar.low:
            raise ValueError(f"invalid OHLCV bar at {at.isoformat()}")
        if at.second or at.microsecond or at.minute % 5 or not time(9, 15) <= at.time() <= time(15, 25):
            raise ValueError("bars must use regular-session five-minute bar-start timestamps in IST")
        if normalized and at <= normalized[-1].at:
            raise ValueError("bars must be strictly chronological without duplicate timestamps")
        normalized.append(replace(bar, at=at))
    if len(normalized) < minimum:
        raise ValueError(f"bars must contain at least {minimum} completed records")
    return normalized


def load_bars(path: str | Path) -> list[Bar]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        bars = [Bar(datetime.fromisoformat(row["at"]), *(float(row[name]) for name in ("open", "high", "low", "close", "volume"))) for row in csv.DictReader(handle)]
    return _validated_bars(bars)


def load_verified_bars(path: str | Path, manifest_path: str | Path | None = None) -> list[Bar]:
    """Load bars only after the archive manifest admits the exact CSV."""
    csv_path = Path(path)
    manifest = Path(manifest_path) if manifest_path else csv_path.with_name("dataset-manifest.json")
    if not manifest.is_file():
        raise ValueError(f"dataset manifest required for evaluation: {manifest}")
    from .collectors.breeze_archive import verify_dataset
    verify_dataset(csv_path, manifest)
    return load_bars(csv_path)


def snapshots(bars: list[Bar], entry_price: float | None = None) -> list[Snapshot]:
    result: list[Snapshot] = []
    pv = volume = 0.0
    day = None
    ranges: list[float] = []
    atr = 0.0
    for index, bar in enumerate(bars):
        if day != bar.at.date():
            day, pv, volume = bar.at.date(), 0.0, 0.0
        pv += (bar.high + bar.low + bar.close) / 3 * bar.volume
        volume += bar.volume
        previous_close = bars[index - 1].close if index else bar.open
        ranges.append(max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close)))
        if index == 13:
            atr = sum(ranges) / 14
        elif index > 13:
            atr = (atr * 13 + ranges[-1]) / 14
        if index < 20:
            continue
        window = bars[index - 20:index]
        trend = int(bar.close > sum(item.close for item in bars[index - 13:index + 1]) / 14)
        session = 2 if bar.at.time() >= time(15) else 1 if bar.at.time() >= time(10) else 0
        unrealized = 0 if entry_price is None else (1 if bar.close >= entry_price else -1)
        result.append(Snapshot(bar, bar.close > max(item.high for item in window), volume > 0 and bar.close > pv / volume, atr, trend, int(atr / bar.close > 0.003), session, entry_price is not None, unrealized))
    return result


def replay(bars: list[Bar], policy: QPolicy | None = None, *, decide: Callable[[dict, str | None], str] | None = None, assumptions: ExecutionAssumptions | None = None, initial_state: dict | None = None, training: bool = False, seed: int = 42, terminal: bool = True, entry_start_at: datetime | None = None, strict_decisions: bool = False, session_windows: dict[str, tuple[time, time]] | None = None, session_schedules: dict[str, tuple[tuple[time, time], ...]] | None = None) -> ReplayResult:
    """Execute frozen rules with optional entry veto/early exit model decisions.

    Decisions use a completed candle; fills use a later eligible candle open.
    Protective orders execute at the adverse opening price on gaps. When both
    stop and target touch in one candle, the stop wins. Terminal data never
    fabricates a liquidation. ``terminal=False`` supports full-prefix paper
    rebuilds; checkpoints report risk state, not broker order reconciliation.
    """
    bars = _validated_bars(bars)
    session_schedules = session_schedules or {day: (window,) for day, window in (session_windows or {}).items()}
    if any(opening >= closing for schedule in session_schedules.values() for opening, closing in schedule):
        raise ValueError("session windows must be ordered")

    def scheduled_times(schedule: tuple[tuple[time, time], ...]) -> tuple[time, ...]:
        result = []
        for opening, closing in schedule:
            at = datetime.combine(date.today(), opening)
            while at.time() < closing:
                result.append(at.time())
                at += BAR_INTERVAL
        if result != sorted(result) or len(result) != len(set(result)):
            raise ValueError("session windows must be ordered and non-overlapping")
        return tuple(result)
    costs = assumptions or ExecutionAssumptions()
    result = ReplayResult(costs)
    result.variant = "rl+jev" if policy is not None and decide is not None else "rl-only" if policy is not None else "jev-only" if decide is not None else "rules-only"
    if entry_start_at is not None:
        if entry_start_at.tzinfo is None:
            entry_start_at = entry_start_at.replace(tzinfo=IST)
        entry_start_at = entry_start_at.astimezone(IST)
        if entry_start_at.time() != time(9, 15) or entry_start_at not in {bar.at for bar in bars} or initial_state:
            raise ValueError("evaluation start must be an observed 09:15 bar without checkpoint state")
        result.entry_start_at = entry_start_at.isoformat()
    if policy is not None and training:
        policy._random.seed(seed)
    checkpoint = initial_state or {}
    if checkpoint.get("pending") is not None or checkpoint.get("open_decision") is True:
        raise ValueError("open decisions require full-prefix replay with cached decisions")
    cash = float(checkpoint.get("cash", INITIAL_CASH))
    quantity = int(checkpoint.get("quantity", 0))
    if quantity != checkpoint.get("quantity", 0):
        raise ValueError("checkpoint quantity must be whole units")
    entry = float(checkpoint.get("entry", 0.0))
    stop = float(checkpoint.get("stop", 0.0))
    target = float(checkpoint.get("target", 0.0))
    entry_fee = float(checkpoint.get("entry_fee", 0.0))
    entry_slippage = float(checkpoint.get("entry_slippage", 0.0))
    entry_at = checkpoint.get("entry_at")
    high_water = float(checkpoint.get("high_water", INITIAL_CASH))
    paused = bool(checkpoint.get("paused", False))
    day_start = float(checkpoint.get("day_start", cash + quantity * entry))
    day = checkpoint.get("day")
    blocked = bool(checkpoint.get("daily_loss_blocked", False))
    last_at = datetime.fromisoformat(checkpoint["last_at"]) if checkpoint.get("last_at") else None
    if last_at is not None and checkpoint.get("open_decision") is not False:
        raise ValueError("legacy checkpoint lacks decision evidence; rebuild the full prefix")
    before = float(checkpoint.get("equity", cash + quantity * entry))
    if not all(math.isfinite(value) for value in (cash, entry, stop, target, entry_fee, entry_slippage, high_water, day_start, before)) or cash < 0 or quantity < 0 or high_water <= 0 or day_start <= 0 or (quantity and not 0 < stop < entry < target):
        raise ValueError("invalid execution checkpoint")
    pending: dict | None = None
    decision: dict | None = None
    by_at = {snapshot.bar.at: snapshot for snapshot in snapshots(bars)}
    session_bars: dict[str, list[datetime]] = {}
    for bar in bars:
        session_bars.setdefault(bar.at.date().isoformat(), []).append(bar.at)
    expected_times = {day: scheduled_times(schedule) for day, schedule in session_schedules.items()}
    expected_indices = {day: {at: index for index, at in enumerate(times)} for day, times in expected_times.items()}
    session_start = before
    session_trades = len(result.trades)
    session_from_checkpoint = last_at is not None and day == last_at.date().isoformat()

    def finish_session(session_date: str, *, ended: bool) -> None:
        times = session_bars[session_date]
        expected = expected_times.get(session_date) or tuple((datetime.combine(times[0].date(), time(9, 15)) + BAR_INTERVAL * index).time() for index in range(75))
        complete = not session_from_checkpoint and tuple(at.time() for at in times) == expected
        result.sessions.append({"session_date": session_date, "start_equity": session_start,
                                "end_equity": before, "completed_trades": len(result.trades) - session_trades,
                                "provenance": result.provenance, "first_at": times[0].isoformat(),
                                "last_at": times[-1].isoformat(), "observed_bars": len(times), "complete": complete,
                                "special_session": session_date in session_schedules})
        if ended and not complete:
            result.defects.append(f"incomplete session on {session_date}")

    def held(snapshot: Snapshot) -> Snapshot:
        return replace(snapshot, in_position=quantity > 0, unrealized=0 if not quantity else (1 if snapshot.bar.close >= entry else -1))

    def close_position(price: float, at: datetime, reason: str) -> None:
        nonlocal cash, quantity, entry, stop, target, entry_fee, entry_slippage, entry_at
        fill = price * (1 - costs.slippage_bps / 10000)
        fee = costs.fee(quantity * fill)
        cash += quantity * fill - fee
        exit_slippage = quantity * (price - fill)
        result.costs_inr += fee + exit_slippage
        result.trades.append({"entry_at": entry_at, "exit_at": at.isoformat(), "quantity": quantity, "entry": entry, "exit": fill, "costs": entry_fee + fee + entry_slippage + exit_slippage, "net_pnl": quantity * (fill - entry) - entry_fee - fee, "reason": reason})
        quantity, entry, stop, target, entry_fee, entry_slippage, entry_at = 0, 0.0, 0.0, 0.0, 0.0, 0.0, None

    for index, bar in enumerate(bars):
        if last_at is not None and bar.at <= last_at:
            continue
        forced = False
        executed: Action = "HOLD" if quantity else "ABSTAIN"
        if day != bar.at.date().isoformat():
            if day is not None and day in session_bars:
                finish_session(day, ended=True)
            if quantity:
                close_position(bar.open, bar.at, "overnight-gap")
                result.defects.append("position carried across missing session liquidation")
                forced, executed = True, "SELL"
            pending = None
            day = bar.at.date().isoformat()
            day_start = cash
            approved_opening = expected_times.get(day, (time(9, 15),))[0]
            blocked = day in session_schedules or bar.at.time() != approved_opening or forced
            if bar.at.time() != approved_opening:
                result.defects.append(f"session starts after {approved_opening.isoformat(timespec='minutes')} on {day}")
            session_start, session_trades = cash, len(result.trades)
            session_from_checkpoint = False
        expected_index = expected_indices.get(day)
        gap = last_at is not None and bar.at.date() == last_at.date() and ((expected_index is not None and (bar.at.time() not in expected_index or last_at.time() not in expected_index or expected_index[bar.at.time()] != expected_index[last_at.time()] + 1)) or (expected_index is None and bar.at - last_at != BAR_INTERVAL))
        if gap:
            blocked = True
            result.defects.append(f"missing five-minute bars before {bar.at.isoformat()}")
            pending = None
            if quantity:
                close_position(bar.open, bar.at, "stale-gap")
                forced, executed = True, "SELL"
        opening_equity = cash + quantity * bar.open
        high_water = max(high_water, opening_equity)
        drawdown = (high_water - opening_equity) / high_water
        result.max_drawdown = max(result.max_drawdown, drawdown)
        paused = paused or drawdown >= MAX_DRAWDOWN
        blocked = blocked or (day_start - opening_equity) / day_start >= MAX_DAILY_LOSS
        if quantity and (paused or bar.at.time() >= time(15, 15)):
            close_position(bar.open, bar.at, "drawdown-pause" if paused else "session-liquidation")
            forced, executed, pending = True, "SELL", None
        if quantity and bar.open <= stop:
            close_position(bar.open, bar.at, "gap-stop")
            forced, executed, pending = True, "SELL", None
        elif quantity and bar.open >= target:
            close_position(target, bar.at, "gap-target")
            forced, executed, pending = True, "SELL", None
        if pending is not None and bar.at >= pending["available_at"]:
            action = pending["action"]
            if action == "SELL" and quantity:
                close_position(bar.open, bar.at, "model-exit")
                executed = "SELL"
            elif action == "BUY" and not quantity and not paused and not blocked and bar.at.time() < time(15) and pending["session_date"] == day:
                fill = bar.open * (1 + costs.slippage_bps / 10000)
                distance = 2 * pending["atr"]
                # Include adverse exit slippage and both fees in planned stop risk.
                stop_fill = (fill - distance) * (1 - costs.slippage_bps / 10000)
                risk_unit = fill - stop_fill
                allowed = min(int(opening_equity * RISK_PER_TRADE / risk_unit) if risk_unit > 0 else 0, int(cash / fill), int(bars[index - 1].volume * costs.participation_rate) if index else 0)
                while allowed and (allowed * fill + costs.fee(allowed * fill) > cash or allowed * risk_unit + costs.fee(allowed * fill) + costs.fee(allowed * stop_fill) > opening_equity * RISK_PER_TRADE):
                    allowed -= 1
                if allowed and distance > 0 and fill - distance > 0:
                    quantity, entry, stop, target = allowed, fill, fill - distance, fill + 2 * distance
                    entry_fee, entry_at = costs.fee(quantity * fill), bar.at.isoformat()
                    cash -= quantity * fill + entry_fee
                    entry_slippage = quantity * (fill - bar.open)
                    result.costs_inr += entry_fee + entry_slippage
                    executed = "BUY"
            pending = None
        if quantity:
            if bar.low <= stop:
                close_position(stop, bar.at + BAR_INTERVAL, "stop")
                forced, executed = True, "SELL"
            elif bar.high >= target:
                close_position(target, bar.at + BAR_INTERVAL, "target")
                forced, executed = True, "SELL"
        after = cash + quantity * bar.close
        high_water = max(high_water, after)
        drawdown = (high_water - after) / high_water
        result.max_drawdown = max(result.max_drawdown, drawdown)
        paused = paused or drawdown >= MAX_DRAWDOWN
        blocked = blocked or (day_start - after) / day_start >= MAX_DAILY_LOSS
        current = held(by_at[bar.at]) if bar.at in by_at else None
        if decision is not None:
            decision["reward"] += after - before
            if forced:
                decision["overridden"] = True
                decision["executed"] = "SELL"
            elif executed in ("BUY", "SELL"):
                decision["executed"] = executed
            if pending is None and current is not None:
                matched = policy is not None and not decision["overridden"] and decision["rl"] == decision["executed"] and decision["requested"] == decision["rl"]
                result.append((decision["snapshot"], decision["rl"] or "ABSTAIN", decision["jev"], decision["executed"], decision["reward"], current, matched))
                result.terminal.append(terminal and index == len(bars) - 1)
                decision = None
        before, last_at = after, bar.at
        if current is None or decision is not None or (entry_start_at is not None and bar.at < entry_start_at) or bar.at.time() >= time(15, 25) or (terminal and index == len(bars) - 1):
            continue
        base: Action = "HOLD" if quantity else "BUY" if current.breakout and current.above_vwap and not paused and not blocked and (entry_start_at is None or bar.at >= entry_start_at) and (bar.at + BAR_INTERVAL).time() < time(15) else "ABSTAIN"
        rl = policy.choose(current, explore=0.1 if training else 0.0) if policy is not None else None
        jev: Action | None = None
        requested: Action = rl if rl is not None else base
        if decide is not None:
            evidence = {"instrument": INSTRUMENT, "bar": {**asdict(bar), "at": bar.at.isoformat()}, "decision_at": (bar.at + BAR_INTERVAL).isoformat(), "breakout": current.breakout, "above_vwap": current.above_vwap, "atr": current.atr, "state": current.state, "position": {"quantity": quantity, "entry": entry, "stop": stop, "target": target}, "cash_inr": cash, "equity_inr": after, "rules_action": base, "constraints": {"paused": paused, "daily_loss_blocked": blocked, "entry_cutoff": "15:00", "liquidation_start": "15:15", "max_risk_fraction": RISK_PER_TRADE}}
            try:
                jev = decide(evidence, rl)
                if jev not in ACTIONS:
                    raise ValueError("invalid model action")
            except Exception:
                if strict_decisions:
                    raise ValueError(f"missing or invalid frozen model decision at {bar.at.isoformat()}") from None
                jev = "ABSTAIN"
                result.defects.append(f"model decision failed at {bar.at.isoformat()}")
            requested = jev
        action: Action = "SELL" if quantity and requested == "SELL" else "HOLD" if quantity else "BUY" if base == "BUY" and requested == "BUY" else "ABSTAIN"
        decision = {"snapshot": current, "rl": rl, "jev": jev, "requested": requested, "executed": "HOLD" if quantity else "ABSTAIN", "reward": 0.0, "overridden": action != requested}
        if action in ("BUY", "SELL"):
            pending = {"action": action, "atr": current.atr, "session_date": day, "available_at": bar.at + BAR_INTERVAL + timedelta(seconds=costs.decision_latency_seconds)}
    if decision is not None and terminal:
        # A pending last decision is cancelled, never filled using unseen data.
        if not result or decision["snapshot"].bar.at != result[-1][0].bar.at:
            result.append((decision["snapshot"], decision["rl"] or "ABSTAIN", decision["jev"], decision["executed"], decision["reward"], held(by_at[last_at]), False))
            result.terminal.append(True)
    if quantity and terminal:
        result.defects.append("open position at end of data; no observed liquidation fill")
    if day is not None:
        finish_session(day, ended=terminal)
    result.final_state = {"cash": cash, "quantity": quantity, "entry": entry, "stop": stop, "target": target, "entry_fee": entry_fee, "entry_slippage": entry_slippage, "entry_at": entry_at, "equity": before, "high_water": high_water, "paused": paused, "day_start": day_start, "day": day, "daily_loss_blocked": blocked, "last_at": last_at.isoformat() if last_at else None, "pending": {**pending, "available_at": pending["available_at"].isoformat()} if pending is not None and not terminal else None, "open_decision": decision is not None and not terminal}
    result.defects = sorted(set(result.defects))
    return result


def record_run(db_path: str | Path, run_id: str, mode: Mode, policy: QPolicy | None, observations: Iterable[Transition], *, policy_version: str | None = None) -> dict[str, object]:
    if mode == "live":
        raise ValueError("live execution is unavailable in this data-only milestone")
    initialize_pilot_db(db_path)
    rows = list(observations)
    result = observations if isinstance(observations, ReplayResult) else None
    version = policy_version or (policy.version if policy is not None else "frozen-rules-v1")
    summary = {"policy_version": version, "decisions": len(rows), "net_reward": round(sum(row[4] for row in rows), 6), "instrument": INSTRUMENT, "policy": result.variant if result else "legacy-unverified", "completed_trades": len(result.trades) if result else 0, "entry_start_at": result.entry_start_at if result else None, "provenance": "historical-replay", "execution_assumptions": result.assumptions if result else None, "costs_verified": False, "costs_inr": result.costs_inr if result else None, "max_drawdown": result.max_drawdown if result else None, "execution_defects": result.defects if result else ["no execution metadata"], "qualification": "unqualified"}
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute("INSERT INTO pilot_runs VALUES(?,?,?,?,?,?)", (run_id, mode, version, datetime.now(IST).isoformat(), "completed", json.dumps(summary, allow_nan=False)))
        for index, (state, rl, jev, executed, reward, following, matched) in enumerate(rows):
            is_terminal = result.terminal[index] if result else index == len(rows) - 1
            # Supplied legacy observations cannot assert their own correctness.
            verified_match = result is not None and policy is not None and matched and rl == executed and (jev is None or jev == rl)
            db.execute("INSERT INTO pilot_transitions(run_id,at,state,rl_action,jev_action,executed_action,reward,next_state,execution_matched_rl,terminal,engine_version) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (run_id, state.bar.at.isoformat(), state.state, rl, jev, executed, reward, "TERMINAL" if is_terminal else following.state, int(verified_match), int(is_terminal), 2 if result else 1))
        if result:
            for number, trade in enumerate(result.trades, 1):
                db.execute("INSERT INTO pilot_trades VALUES(?,?,?,?,?,?,?,?,?,?)", (run_id, number, *(trade[key] for key in ("entry_at", "exit_at", "quantity", "entry", "exit", "costs", "net_pnl", "reason"))))
            for session in result.sessions:
                db.execute("INSERT INTO pilot_sessions(run_id,session_date,start_equity,end_equity,completed_trades,provenance,first_at,last_at,observed_bars,complete) VALUES(?,?,?,?,?,?,?,?,?,?)", (run_id, *(session[key] for key in ("session_date", "start_equity", "end_equity", "completed_trades", "provenance", "first_at", "last_at", "observed_bars", "complete"))))
            db.execute("INSERT INTO pilot_checkpoints VALUES(?,?)", (run_id, json.dumps(result.final_state, allow_nan=False)))
    return summary


def train_candidate(db_path: str | Path, source_run: str, version: str) -> QPolicy:
    initialize_pilot_db(db_path)
    policy = QPolicy()
    with closing(sqlite3.connect(db_path)) as db, db:
        existing = db.execute("SELECT status FROM pilot_policies WHERE version=?", (version,)).fetchone()
        if existing is not None:
            raise ValueError("policy version already exists; candidates never replace an active policy")
        rows = db.execute("SELECT state, rl_action, reward, next_state FROM pilot_transitions WHERE run_id=? AND execution_matched_rl=1 AND engine_version=2 ORDER BY at", (source_run,)).fetchall()
        if not rows:
            raise ValueError("no verified executed RL transitions available for training")
        for _ in range(10):
            for state, action, reward, following in rows:
                policy.update(state, action, reward, following)
        db.execute("INSERT INTO pilot_policies(version,status,trained_at,values_json,source_run_id) VALUES(?,?,?,?,?)", (version, "candidate", datetime.now(IST).isoformat(), policy.to_json(), source_run))
    policy.version = version
    return policy


def train_candidate_from_bars(db_path: str | Path, bars_csv: str | Path, version: str, *, seed: int = 42, assumptions: ExecutionAssumptions | None = None) -> QPolicy:
    """Train only on the first 60% of manifest-admitted complete sessions."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("training seed must be an integer")
    bars = load_verified_bars(bars_csv)
    dates = sorted({bar.at.date().isoformat() for bar in bars})
    if len(dates) < 5:
        raise ValueError("five complete sessions required for 60/20/20 split")
    train_count = len(dates) * 3 // 5
    validation_count = len(dates) // 5
    training = bars[:next(index for index, bar in enumerate(bars) if bar.at.date().isoformat() == dates[train_count])]
    costs = assumptions or ExecutionAssumptions()
    policy = QPolicy()
    matched = 0
    for epoch in range(10):
        result = replay(training, policy, assumptions=costs, training=True, seed=seed + epoch)
        if result.defects or not all(session["complete"] for session in result.sessions):
            raise ValueError("incomplete or defective training sessions")
        for row, ended in zip(result, result.terminal):
            if row[6]:
                policy.update(row[0].state, row[1], row[4], "TERMINAL" if ended else row[5].state)
                matched += 1
    if not matched:
        raise ValueError("no unchanged executed RL actions available for training")
    metadata = {"dataset_sha256": hashlib.sha256(Path(bars_csv).read_bytes()).hexdigest(),
                "train_first": dates[0], "train_last": dates[train_count - 1],
                "validation_first": dates[train_count], "validation_last": dates[train_count + validation_count - 1],
                "holdout_first": dates[train_count + validation_count], "holdout_last": dates[-1],
                "seed": seed, "epochs": 10, "matched_transitions": matched,
                "execution_assumptions": asdict(costs), "provenance": "historical-training-only"}
    initialize_pilot_db(db_path)
    with closing(sqlite3.connect(db_path)) as db, db:
        if db.execute("SELECT 1 FROM pilot_policies WHERE version=?", (version,)).fetchone():
            raise ValueError("policy version already exists; candidates never replace an active policy")
        db.execute("INSERT INTO pilot_policies(version,status,trained_at,values_json,metadata_json) VALUES(?,?,?,?,?)",
                   (version, "candidate", datetime.now(IST).isoformat(), policy.to_json(), json.dumps(metadata, sort_keys=True)))
    policy.version = version
    return policy


def compare_holdout(db_path: str | Path, bars_csv: str | Path, policy_version: str, *, assumptions: ExecutionAssumptions | None = None, jev_actions: dict[str, str] | None = None, rl_jev_actions: dict[str, str] | None = None) -> dict:
    """Compare frozen variants; model actions must match exact evidence packets."""
    from .pilot_agents import canonical, digest
    bars = load_verified_bars(bars_csv)
    dates = sorted({bar.at.date().isoformat() for bar in bars})
    if len(dates) < 5:
        raise ValueError("five complete sessions required for 60/20/20 split")
    train_count, validation_count = len(dates) * 3 // 5, len(dates) // 5
    holdout_first = dates[train_count + validation_count]
    dataset_hash = hashlib.sha256(Path(bars_csv).read_bytes()).hexdigest()
    costs = assumptions or ExecutionAssumptions()
    initialize_pilot_db(db_path)
    with closing(sqlite3.connect(db_path)) as db:
        row = db.execute("SELECT status,values_json,metadata_json FROM pilot_policies WHERE version=?", (policy_version,)).fetchone()
    if row is None or row[0] not in ("candidate", "active") or row[2] is None:
        raise ValueError("frozen bars-aware candidate required")
    metadata = json.loads(row[2])
    if (metadata.get("dataset_sha256") != dataset_hash or metadata.get("train_last") != dates[train_count - 1]
            or metadata.get("validation_first") != dates[train_count] or metadata.get("holdout_first") != holdout_first
            or metadata.get("holdout_last") != dates[-1] or metadata.get("execution_assumptions") != asdict(costs)):
        raise ValueError("candidate dataset, split or execution assumptions changed")
    policy = QPolicy.from_json(row[1])
    policy.version = policy_version
    start = next(bar.at for bar in bars if bar.at.date().isoformat() == holdout_first)

    def summary(result: ReplayResult) -> dict:
        relevant_defects = [defect for defect in result.defects if (match := re.search(r"\d{4}-\d{2}-\d{2}", defect)) is None or match.group() >= holdout_first]
        if relevant_defects or any(not session["complete"] for session in result.sessions if session["session_date"] >= holdout_first):
            raise ValueError("holdout has incomplete sessions or execution defects")
        net = sum(trade["net_pnl"] for trade in result.trades)
        return {"completed_trades": len(result.trades), "net_pnl_inr": round(net, 6),
                "expectancy_inr": round(net / len(result.trades), 6) if result.trades else None,
                "max_drawdown": result.max_drawdown, "costs_inr": round(result.costs_inr, 6)}

    report = {"dataset_sha256": dataset_hash, "policy_version": policy_version, "train_last": dates[train_count - 1],
              "validation_first": dates[train_count], "holdout_first": holdout_first, "holdout_last": dates[-1],
              "execution_assumptions": asdict(costs), "variants": {}, "model_decision_hashes": {},
              "model_decision_provenance": "caller-supplied-unverified" if jev_actions is not None or rl_jev_actions is not None else "missing",
              "qualified": False}
    report["variants"]["rules-only"] = summary(replay(bars, assumptions=costs, entry_start_at=start))
    report["variants"]["rl-only"] = summary(replay(bars, policy, assumptions=costs, entry_start_at=start))

    for name, actions, selected_policy in (("jev-only", jev_actions, None), ("rl+jev", rl_jev_actions, policy)):
        if actions is None:
            continue
        def decide(evidence: dict, rl_action: str | None) -> str:
            key = digest(canonical({"evidence": evidence, "rl_action": rl_action}))
            return actions[key]
        report["variants"][name] = summary(replay(bars, selected_policy, decide=decide, assumptions=costs, entry_start_at=start, strict_decisions=True))
        report["model_decision_hashes"][name] = digest(canonical(actions))

    gaps = []
    if "jev-only" not in report["variants"] or "rl+jev" not in report["variants"]:
        gaps.append("both complete frozen Jev decision sets required")
    else:
        challenger = report["variants"]["rl+jev"]
        reference = report["variants"]["jev-only"]
        if any(variant["completed_trades"] < 100 for variant in report["variants"].values()):
            gaps.append("requires 100 untouched holdout completed trades per compared variant")
        if challenger["expectancy_inr"] is None or challenger["expectancy_inr"] <= 0:
            gaps.append("requires positive after-cost holdout expectancy")
        if challenger["max_drawdown"] >= MAX_DRAWDOWN:
            gaps.append("requires holdout drawdown below 5 percent")
        if challenger["net_pnl_inr"] <= reference["net_pnl_inr"]:
            gaps.append("requires RL+Jev net improvement over Jev-only")
    gaps.extend(("requires verified effective trading costs", "requires model identity and usage-cost evidence", "requires genuine forward paper qualification"))
    report["qualification_gaps"] = gaps
    serialized = json.dumps(report, sort_keys=True, allow_nan=False)
    comparison_id = hashlib.sha256(serialized.encode()).hexdigest()
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute("INSERT OR IGNORE INTO pilot_comparisons VALUES(?,?,?,?,?)", (comparison_id, policy_version, dataset_hash, datetime.now(IST).isoformat(), serialized))
    report["comparison_id"] = comparison_id
    return report


def audit_forward_paper(path: str | Path, *, strategy_id: str | None = None) -> dict:
    """Rebuild the paper journal; synthetic clocks and unverifiable fills count zero."""
    report = {"completed_trades": 0, "completed_sessions": 0, "trade_sessions": 0, "issues": []}
    if not Path(path).is_file():
        report["issues"].append("forward journal missing")
        return report
    from .pilot_agents import aware, canonical, digest
    from .nifty_universe import official_url, session_times
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        required = {"forward_runs", "forward_bars", "forward_decisions", "forward_trades"}
        if not required <= {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} or any("clock_source" not in {column[1] for column in db.execute(f"PRAGMA table_info({table})")} for table in ("forward_runs", "forward_bars")):
            report["issues"].append("legacy forward journal lacks clock provenance")
            return report
        runs = db.execute("SELECT * FROM forward_runs ORDER BY run_id").fetchall()
        selected = []
        for run in runs:
            try:
                config = json.loads(run["config"])
                if strategy_id is None or config["strategy_id"] == strategy_id:
                    selected.append((run, config))
            except (ValueError, KeyError, TypeError):
                report["issues"].append("invalid forward run configuration")
        if not selected:
            report["issues"].append("no matching forward paper run")
        if strategy_id is None and len({config["strategy_id"] for _, config in selected}) > 1:
            report["issues"].append("select one frozen forward strategy")
            return report
        complete_dates: set[str] = set()
        trade_dates: set[str] = set()
        trade_hashes: set[str] = set()
        for run, config in selected:
            run_id = run["run_id"]
            if run["clock_source"] != "system":
                report["issues"].append(f"{run_id}: injected or unknown start clock")
                continue
            bar_rows = db.execute("SELECT * FROM forward_bars WHERE run_id=? ORDER BY at", (run_id,)).fetchall()
            if not bar_rows or any(row["clock_source"] != "system" for row in bar_rows):
                report["issues"].append(f"{run_id}: injected or unknown bar clock")
                continue
            try:
                started = aware(run["started_at"])
                assumptions = ExecutionAssumptions(**config["assumptions"])
                def decode(value: dict) -> Bar:
                    return Bar(aware(value["at"]), *(value[key] for key in ("open", "high", "low", "close", "volume")))
                warmup = _validated_bars([decode(value) for value in config["warmup"]], minimum=1) if config["warmup"] else []
                observed = _validated_bars([decode(json.loads(row["payload"])) for row in bar_rows], minimum=1)
                if any(row["at"] != bar.at.isoformat() or not timedelta(0) <= aware(row["observed_at"]) - (bar.at + BAR_INTERVAL) <= timedelta(seconds=120) or bar.at + BAR_INTERVAL <= started for row, bar in zip(bar_rows, observed)):
                    raise ValueError("stale or inconsistent observation timestamp")
                calendar_rows = {row["calendar_json"] for row in bar_rows}
                if len(calendar_rows) != 1:
                    raise ValueError("inconsistent calendar evidence")
                calendar = json.loads(calendar_rows.pop())
                if canonical(calendar) not in {row["calendar_json"] for row in bar_rows}:
                    raise ValueError("non-canonical calendar evidence")
                official_url(calendar["source"])
                if any((bounds := session_times(calendar, bar.at.astimezone(IST).date())) is None or not bounds[0] <= bar.at < bounds[1] or bar.at + BAR_INTERVAL > bounds[1] for bar in observed):
                    raise ValueError("calendar does not admit observed bars")
                decisions = db.execute("SELECT * FROM forward_decisions WHERE run_id=?", (run_id,)).fetchall()
                cached = {}
                for item in decisions:
                    packet = json.loads(item["packet"])
                    available = aware(packet["evidence"]["decision_at"])
                    delay = aware(item["decided_at"]) - available
                    if digest(item["packet"]) != item["input_hash"] or item["packet"] != canonical(packet) or item["action"] not in ACTIONS or delay < timedelta(0) or (item["action"] != "ABSTAIN" and delay > timedelta(seconds=assumptions.decision_latency_seconds)):
                        raise ValueError("invalid or late decision record")
                    cached[item["input_hash"]] = item["action"]
                first_decision_at = observed[max(0, 34 - len(warmup))].at + BAR_INTERVAL if len(warmup) + len(observed) >= 35 else None
                def decide(evidence: dict, rl_action: str | None) -> str:
                    available = aware(evidence["decision_at"])
                    if available <= started or first_decision_at is None or available < first_decision_at:
                        return "ABSTAIN"
                    return cached[digest(canonical({"evidence": evidence, "rl_action": rl_action}))]
                policy_json = config.get("policy")
                policy = QPolicy.from_json(policy_json) if policy_json is not None else None
                result = replay([*warmup, *observed], policy=policy, decide=decide, assumptions=assumptions, terminal=False) if len(warmup) + len(observed) >= 35 else None
                if result is not None and result.defects:
                    raise ValueError(f"rebuild defects: {result.defects}")
                stored = db.execute("SELECT trade_hash,payload FROM forward_trades WHERE run_id=?", (run_id,)).fetchall()
                if any(digest(item["payload"]) != item["trade_hash"] for item in stored):
                    raise ValueError("trade hash mismatch")
                expected = {digest(canonical(trade)) for trade in (result.trades if result else []) if aware(trade["entry_at"]) >= started}
                if expected != {item["trade_hash"] for item in stored}:
                    raise ValueError("completed trades differ from journal rebuild")
                by_date: dict[str, list[datetime]] = {}
                for bar in observed:
                    by_date.setdefault(bar.at.date().isoformat(), []).append(bar.at)
                run_dates = {day for day, times in by_date.items() if len(times) == 75 and times[0].time() == time(9, 15) and times[-1].time() == time(15, 25) and all(right - left == BAR_INTERVAL for left, right in zip(times, times[1:]))}
                complete_dates.update(run_dates)
                for item in stored:
                    trade = json.loads(item["payload"])
                    if trade["entry_at"][:10] in run_dates and trade["exit_at"][:10] in run_dates:
                        trade_hashes.add(item["trade_hash"])
                        trade_dates.add(trade["exit_at"][:10])
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                report["issues"].append(f"{run_id}: {exc}")
        report.update(completed_trades=len(trade_hashes), completed_sessions=len(complete_dates), trade_sessions=len(trade_dates))
    return report


def qualification(db: sqlite3.Connection, *, forward_db_path: str | Path | None = None, strategy_id: str | None = None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    forward = audit_forward_paper(forward_db_path, strategy_id=strategy_id) if forward_db_path is not None else {"completed_trades": 0, "trade_sessions": 0, "issues": ["forward journal required; pilot replay rows are historical"]}
    reasons.extend(forward["issues"])
    if forward["completed_trades"] < 30:
        reasons.append("requires 30 completed genuine forward paper trades")
    if forward["trade_sessions"] < 30:
        reasons.append("requires forward trades across 30 genuine sessions")
    comparison = db.execute("SELECT comparison_id,policy_version,dataset_sha256,report_json FROM pilot_comparisons ORDER BY created_at DESC LIMIT 1").fetchone()
    if comparison is None:
        reasons.append("requires frozen four-way holdout comparison evidence")
    else:
        try:
            if hashlib.sha256(comparison[3].encode()).hexdigest() != comparison[0]:
                raise ValueError("comparison hash mismatch")
            report = json.loads(comparison[3])
            policy_row = db.execute("SELECT metadata_json FROM pilot_policies WHERE version=? AND status IN ('candidate','active')", (comparison[1],)).fetchone()
            if policy_row is None or policy_row[0] is None:
                raise ValueError("comparison candidate missing")
            metadata = json.loads(policy_row[0])
            if (report.get("policy_version") != comparison[1] or report.get("dataset_sha256") != comparison[2]
                    or metadata.get("dataset_sha256") != comparison[2]
                    or metadata.get("train_last") != report.get("train_last")
                    or metadata.get("validation_first") != report.get("validation_first")
                    or metadata.get("holdout_first") != report.get("holdout_first")
                    or metadata.get("holdout_last") != report.get("holdout_last")
                    or metadata.get("execution_assumptions") != report.get("execution_assumptions")):
                raise ValueError("comparison candidate provenance mismatch")
            variants = report["variants"]
            if set(variants) != {"rules-only", "jev-only", "rl-only", "rl+jev"}:
                reasons.append("requires complete frozen four-way holdout comparison")
            elif report.get("model_decision_provenance") != "verified-persisted":
                reasons.append("requires verified persisted model decision evidence")
            else:
                challenger, reference = variants["rl+jev"], variants["jev-only"]
                if any(variant["completed_trades"] < 100 for variant in variants.values()):
                    reasons.append("requires 100 untouched holdout completed trades per compared variant")
                if challenger["expectancy_inr"] is None or challenger["expectancy_inr"] <= 0 or challenger["max_drawdown"] >= MAX_DRAWDOWN:
                    reasons.append("requires positive after-cost expectancy and drawdown below 5 percent")
                if challenger["net_pnl_inr"] <= reference["net_pnl_inr"]:
                    reasons.append("requires RL+Jev improvement over Jev-only under identical costs")
        except (TypeError, KeyError, ValueError):
            reasons.append("invalid frozen holdout comparison evidence")
    reasons.extend(["requires verified effective brokerage costs and execution assumptions", "requires no unresolved execution defects and stricter release gates"])
    # No legacy 'qualified' label or manually enabled activation can bypass the
    # missing evidence verifier. A future live release must implement that gate.
    return False, reasons


def can_execute_live(db: sqlite3.Connection) -> tuple[bool, str]:
    enabled = db.execute("SELECT live_enabled FROM pilot_activation WHERE singleton=1").fetchone()
    if not enabled or not enabled[0]:
        return False, "live activation is disabled"
    ready, reasons = qualification(db)
    if not ready:
        return False, "; ".join(reasons)
    return False, "live execution is unavailable in this data-only milestone"


def pilot_status(db_path: str | Path, *, forward_db_path: str | Path | None = None, strategy_id: str | None = None) -> dict[str, object]:
    initialize_pilot_db(db_path)
    with closing(sqlite3.connect(db_path)) as db, db:
        ready, reasons = qualification(db, forward_db_path=forward_db_path, strategy_id=strategy_id)
        live_ok, live_reason = can_execute_live(db)
        comparison = db.execute("SELECT comparison_id,policy_version,dataset_sha256,created_at,report_json FROM pilot_comparisons ORDER BY created_at DESC LIMIT 1").fetchone()
        comparison_status = None
        if comparison:
            comparison_status = {"comparison_id": comparison[0], "policy_version": comparison[1], "dataset_sha256": comparison[2], "created_at": comparison[3], "intact": hashlib.sha256(comparison[4].encode()).hexdigest() == comparison[0]}
        forward = audit_forward_paper(forward_db_path, strategy_id=strategy_id) if forward_db_path is not None else None
        return {"instrument": INSTRUMENT, "initial_cash_inr": INITIAL_CASH, "max_drawdown": MAX_DRAWDOWN, "jev_monthly_cap_inr": JEV_MONTHLY_CAP_INR, "qualified": ready, "qualification_gaps": reasons, "comparison": comparison_status, "forward_paper": forward, "live_ready": live_ok, "live_reason": live_reason, "execution_assumptions": asdict(ExecutionAssumptions()), "costs_verified": False, "aws": {"credit_verified": False, "note": "Verify balance and expiry in AWS Billing before deployment."}}
