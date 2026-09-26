"""Prospective forecasts only: actual creation time, exact sessions, immutable scoring."""
from __future__ import annotations

import json
from datetime import date, datetime

from .db import connect
from .nifty_engine import known_before
from .nifty_specialists import probabilities
from .nifty_store import IST, canonical, digest, now_utc, stamp
from .nifty_universe import current_members, previous_session, session_times

BASELINE = {"up": 1 / 3, "flat": 1 / 3, "down": 1 / 3}


def record_forecast(db, evidence_id, target, calendar, *, origin="baseline", result_id=None):
    now = now_utc()
    hours = session_times(calendar, target)
    if target != now.astimezone(IST).date() or not hours or now >= hours[0]:
        raise ValueError("Forecast must be created on its target session before the exchange opens")
    prior_day = previous_session(calendar, target)
    membership, members = current_members(db, now)
    if not membership:
        raise ValueError("No membership snapshot was known before forecast creation")
    with connect(db) as c:
        evidence = c.execute("SELECT * FROM evidence_snapshots WHERE evidence_id=?", (evidence_id,)).fetchone()
        if not evidence or datetime.fromisoformat(evidence["cutoff"]) > now or datetime.fromisoformat(evidence["created_at"]) > now:
            raise ValueError("Forecast evidence was not frozen before creation")
        packet = json.loads(evidence["payload_json"])
        if packet["target_session"] != target.isoformat():
            raise ValueError("Forecast evidence is for a different session")
        if packet["isin"] not in {m["isin"] for m in members}:
            raise ValueError("Company is outside the known universe")
        if any(p["trade_date"] >= target.isoformat() for p in packet["prices"]):
            raise ValueError("Future closing evidence in forecast snapshot")
        price = next((p for p in packet["prices"] if p["trade_date"] == prior_day.isoformat()
                      and p["source_id"] == "nse_eod_bhavcopy"
                      and known_before(p["retrieved_at"], datetime.fromisoformat(evidence["cutoff"]))), None)
        if not price:
            raise ValueError("Exact previous-session official close is missing")
        model = "uniform-baseline-v1"
        probs = BASELINE
        if origin == "llm":
            row = c.execute("""SELECT r.*,j.evidence_id,j.specialist FROM specialist_results r
                               JOIN specialist_jobs j USING(job_id) WHERE result_id=?""", (result_id,)).fetchone()
            if not row or row["specialist"] != "daily_forecast" or row["evidence_id"] != evidence_id:
                raise ValueError("LLM forecast needs a validated result from this frozen snapshot")
            result = json.loads(row["result_json"])
            if result["status"] != "completed" or not known_before(row["created_at"], now):
                raise ValueError("LLM forecast is not available at creation time")
            probs, model = result["probabilities"], result["model_version"]
        elif origin != "baseline":
            raise ValueError("Unsupported forecast origin")
        probabilities(probs)
        forecast_id = digest([packet["isin"], target.isoformat(), origin])
        c.execute("INSERT OR IGNORE INTO forecasts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                  (forecast_id, packet["isin"], target.isoformat(), stamp(now), evidence["cutoff"], evidence_id,
                   membership["snapshot_id"], origin, model, canonical(probs), price["close"], prior_day.isoformat()))
    return forecast_id


def make_forecasts(db, run_id, calendar):
    result = {"baseline": 0, "llm": 0, "skipped": 0, "reasons": {}}
    target = now_utc().astimezone(IST).date()
    with connect(db) as c:
        rows = c.execute("SELECT * FROM coverage WHERE run_id=?", (run_id,)).fetchall()
    for row in rows:
        try:
            record_forecast(db, row["evidence_id"], target, calendar)
            result["baseline"] += 1
        except ValueError as exc:
            result["skipped"] += 1
            message = str(exc)
            result["reasons"][message] = result["reasons"].get(message, 0) + 1
            continue
        with connect(db) as c:
            model_result = c.execute("""SELECT r.result_id FROM specialist_results r JOIN specialist_jobs j USING(job_id)
                WHERE j.evidence_id=? AND j.specialist='daily_forecast' AND json_extract(r.result_json,'$.status')='completed'
                ORDER BY r.created_at DESC LIMIT 1""", (row["evidence_id"],)).fetchone()
        if model_result:
            record_forecast(db, row["evidence_id"], target, calendar, origin="llm", result_id=model_result[0])
            result["llm"] += 1
    return result


def score_forecasts(db, calendar):
    now, scored, missing = now_utc(), 0, 0
    with connect(db) as c:
        rows = c.execute("""SELECT f.* FROM forecasts f LEFT JOIN forecast_scores s USING(forecast_id)
                            WHERE s.forecast_id IS NULL""").fetchall()
        for row in rows:
            target = date.fromisoformat(row["target_session"])
            hours = session_times(calendar, target)
            if not hours or now < hours[1]:
                continue
            actual = c.execute("""SELECT * FROM price_bars WHERE isin=? AND trade_date=?
                                  AND source_id='nse_eod_bhavcopy'""", (row["isin"], row["target_session"])).fetchone()
            if not actual or not known_before(actual["retrieved_at"], now):
                missing += 1
                continue
            change = actual["close"] / row["previous_close"] - 1
            direction = "flat" if abs(change) <= 0.005 + 1e-12 else "up" if change > 0 else "down"
            probs = json.loads(row["probabilities_json"])
            # Ties choose flat then up then down, declared and identical for both origins.
            prediction = max(("flat", "up", "down"), key=probs.get)
            brier = sum((probs[key] - int(key == direction)) ** 2 for key in probs)
            c.execute("INSERT OR IGNORE INTO forecast_scores VALUES(?,?,?,?,?,?,?,?)",
                      (row["forecast_id"], stamp(now), direction, actual["close"], change,
                       float(prediction == direction), brier, canonical(dict(actual))))
            scored += 1
        c.execute("UPDATE long_term_slots SET status='awaiting_verified_outcome' WHERE due_date<=? AND status='pending'",
                  (now.date().isoformat(),))
    return {"scored": scored, "missing_exact_close": missing}


def performance(db):
    with connect(db) as c:
        forecasts = [dict(r) for r in c.execute("""SELECT f.*,s.accuracy,s.brier,s.outcome
                      FROM forecasts f LEFT JOIN forecast_scores s USING(forecast_id)""")]
        totals = dict(c.execute("SELECT snapshot_id,constituent_count FROM universe_snapshots"))
        slots = [dict(r) for r in c.execute("SELECT months,status,COUNT(*) AS count FROM long_term_slots GROUP BY months,status")]
    result = {}
    for origin in ("baseline", "llm"):
        group = [r for r in forecasts if r["origin"] == origin]
        matured = [r for r in group if r["accuracy"] is not None]
        sessions = {r["target_session"]: r["membership_id"] for r in group}
        denominator = sum(totals[snapshot_id] for snapshot_id in sessions.values())
        result[origin] = {
            "issued": len(group), "scored": len(matured), "target_sessions": len(sessions),
            "forecast_coverage": len(group) / denominator if denominator else None,
            "outcome_coverage": len(matured) / len(group) if group else None,
            "direction_accuracy": sum(r["accuracy"] for r in matured) / len(matured) if matured else None,
            "brier_score": sum(r["brier"] for r in matured) / len(matured) if matured else None,
            "status": "observed_samples" if matured else "insufficient_history",
        }
    return {"forecasts": result, "long_term_slots": slots,
            "long_term_status": "No verified matured long-term return metrics computed"}
