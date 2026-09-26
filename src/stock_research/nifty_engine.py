"""Bulk evidence screening and deterministic triggers; no model is needed here."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode

from .collectors.nse_eod import NSEBhavcopyCollector, NSE_EOD_SOURCE_ID, NSE_EOD_BASE_URL
from .collectors.base import CollectedDocument
from .db import connect, transaction
from .governance.rules import evaluate_documents
from .ingest import register_source
from .models import EvidenceTier
from .nifty_store import IST, canonical, digest, initialize, now_utc, source_attempt, stamp
from .nifty_universe import current_members, fetch_official, official_url
from .phase2 import CompanyEvidenceProfile, assess_company_readiness

SPECIALISTS = ("fundamentals", "governance", "valuation", "daily_forecast", "synthesis")
PROMPT_VERSION = "nifty500-1"
POLICY_VERSION = "1.0.0"


def known_before(value, cutoff, *, date_end=False):
    if not value:
        return False
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=IST)
            if date_end and len(value) == 10:
                when += timedelta(days=1)
        return when <= cutoff
    except (ValueError, TypeError):
        return False


def profiles_at(root):
    return {profile.isin: profile for path in Path(root).glob("*/company.json")
            for profile in [CompanyEvidenceProfile.load(path.parent)]}


def freeze_evidence(db, member, cutoff, profiles=None, expected_price_date=None):
    """Copy the as-known data, not a mutable query handle, into the immutable ledger."""
    if cutoff > now_utc():
        raise ValueError("Evidence cutoff cannot be in the future")
    isin = member["isin"]
    with connect(db) as c:
        docs = [dict(r) for r in c.execute(
            "SELECT * FROM documents WHERE isin=? AND validation_status='accepted' ORDER BY document_id", (isin,))
            if known_before(r["retrieved_at"], cutoff) and known_before(r["published_at"], cutoff, date_end=True)]
        ids = {row["document_id"] for row in docs}
        facts = [dict(r) for r in c.execute(
            "SELECT * FROM financial_facts WHERE isin=? AND validation_status='accepted' ORDER BY fact_id", (isin,))
            if r["document_id"] in ids and known_before(r["retrieved_at"], cutoff)
            and known_before(r["publication_date"], cutoff, date_end=True)
            and r["period_end"] <= cutoff.astimezone(IST).date().isoformat()]
        ownership = [dict(r) for r in c.execute(
            "SELECT * FROM ownership_facts WHERE isin=? AND validation_status='accepted' ORDER BY ownership_fact_id", (isin,))
            if r["document_id"] in ids and known_before(r["retrieved_at"], cutoff)]
        prices = [dict(r) for r in c.execute(
            """SELECT p.* FROM price_bars p JOIN sources s USING(source_id)
               WHERE isin=? AND s.evidence_tier IN ('official','company_primary','reputable_secondary')
               ORDER BY trade_date DESC, CASE WHEN p.source_id='nse_eod_bhavcopy' THEN 0 ELSE 1 END""", (isin,))
            if known_before(r["retrieved_at"], cutoff)
            and datetime.fromisoformat(r["trade_date"] + "T15:30:00").replace(tzinfo=IST) <= cutoff]
        # One closing observation per date; official rows win when sources overlap.
        unique_prices = {}
        for row in prices:
            unique_prices.setdefault(row["trade_date"], row)
        prices = list(unique_prices.values())[:2]
        flags = [dict(r) for r in c.execute(
            "SELECT * FROM governance_flags WHERE isin=? AND status='open' ORDER BY flag_id", (isin,))
            if known_before(r["detected_at"], cutoff)]
        last_review = c.execute("""SELECT MAX(r.created_at) FROM specialist_results r
            JOIN specialist_jobs j USING(job_id) WHERE j.isin=? AND j.specialist='synthesis'
            AND json_extract(r.result_json,'$.status')='completed' AND r.created_at<=?""",
                                (isin, stamp(cutoff))).fetchone()[0]
    gaps = []
    profile = (profiles or {}).get(isin)
    if profile:
        _, legacy_gaps = assess_company_readiness(db, profile, cutoff.astimezone(IST).date())
        gaps.extend(legacy_gaps)
    else:
        gaps.append("No validated company financial profile; automatic sector metrics abstain.")
    if member["taxonomy"] in ("insurance", "nbfc_or_financial"):
        gaps.append("Unsupported sector-specific valuation and financial metrics; specialist must abstain.")
    required = profile.required_metrics if profile else ("revenue", "operating_income", "net_income", "eps_diluted")
    for period_type, count in (("quarterly", 8), ("annual", 3)):
        periods = {}
        for f in facts:
            if f["period_type"] == period_type and f["value"] is not None:
                periods.setdefault(f["period_end"], set()).add(f["metric"])
        if sum(set(required) <= metrics for metrics in periods.values()) < count:
            gaps.append(f"Frozen evidence lacks {count} complete {period_type} periods.")
    latest_quarter = max((f["period_end"] for f in facts if f["period_type"] == "quarterly"), default=None)
    if latest_quarter and (cutoff.date() - date.fromisoformat(latest_quarter)).days > 150:
        gaps.append("Quarterly financial evidence is stale (over 150 days).")
    if not prices:
        gaps.append("Closing price is missing at cutoff.")
    elif (expected_price_date and prices[0]["trade_date"] != expected_price_date.isoformat()) or (
        not expected_price_date and (cutoff.date() - date.fromisoformat(prices[0]["trade_date"])).days > 5
    ):
        gaps.append("Closing price is stale for the required exchange session.")
    annual_end = max((f["period_end"] for f in facts if f["period_type"] == "annual"), default=None)
    if not annual_end or not any(d["document_type"] == "annual_report" and d["period_end"] == annual_end for d in docs):
        gaps.append("Latest annual financial period lacks its matching report at cutoff.")
    share_period = max((d["period_end"] or "" for d in docs if d["document_type"] == "shareholding_pattern"), default="")
    if not share_period:
        gaps.append("Shareholding disclosure is missing at cutoff.")
    elif (cutoff.date() - date.fromisoformat(share_period)).days > 150:
        gaps.append("Shareholding disclosure is stale.")
    if any(f["severity"] == "blocking" for f in flags):
        gaps.append("Blocking governance flag requires review.")
    if not docs or not facts:
        status = "missing"
    elif any("Unsupported" in gap or "Blocking" in gap for gap in gaps):
        status = "blocked"
    elif any("stale" in gap for gap in gaps):
        status = "stale"
    else:
        status = "blocked" if gaps else "verified"
    annual_eps = sorted((f for f in facts if f["metric"] == "eps_diluted" and f["period_type"] == "annual"
                         and f["unit"] == "per_share" and f["currency"] == "INR"
                         and f["statement_scope"] == "consolidated" and f["value"] and f["value"] > 0),
                        key=lambda f: f["period_end"], reverse=True)
    valuation = None
    if member["taxonomy"] == "non_financial" and prices and annual_eps:
        eps = annual_eps[0]
        valuation = {"metric": "price_to_earnings", "value": prices[0]["close"] / eps["value"],
                     "eps_period_end": eps["period_end"], "eps_document_id": eps["document_id"],
                     "price_date": prices[0]["trade_date"], "method": "EOD / annual consolidated INR diluted EPS"}
    for doc in docs:
        doc["raw_text"] = (doc.get("raw_text") or "")[:6000]
    packet = {"isin": isin, "symbol": member["symbol"], "company_name": member["company_name"],
              "taxonomy": member["taxonomy"], "documents": docs, "facts": facts,
              "ownership": ownership, "prices": prices, "governance_flags": flags,
              "valuation": valuation, "coverage": status, "missing_data": sorted(set(gaps)),
              "policy_version": POLICY_VERSION, "last_review_at": last_review,
              "target_session": cutoff.astimezone(IST).date().isoformat()}
    content_hash = digest(packet)
    evidence_id = digest([isin, stamp(cutoff), content_hash])
    with connect(db) as c:
        c.execute("INSERT OR IGNORE INTO evidence_snapshots VALUES(?,?,?,?,?,?)",
                  (evidence_id, isin, stamp(cutoff), stamp(), content_hash, canonical(packet)))
    return evidence_id, packet


def dependency_hash(packet, specialist):
    parts = {
        "fundamentals": ("facts", "documents", "taxonomy", "policy_version"),
        "governance": ("documents", "ownership", "governance_flags", "policy_version"),
        "valuation": ("facts", "prices", "taxonomy", "valuation", "policy_version"),
        "daily_forecast": ("documents", "facts", "prices", "governance_flags", "policy_version", "target_session"),
        "synthesis": tuple(k for k in packet if k not in ("last_review_at", "target_session")),
    }
    return digest({key: packet[key] for key in parts[specialist]})


def emit_trigger(c, isin, kind, event, priority, specialists, evidence_id, created):
    key = digest([isin, kind, event])
    c.execute("INSERT OR IGNORE INTO research_triggers VALUES(?,?,?,?,?,?,?,?)",
              (key, isin, kind, event, priority, canonical(specialists), evidence_id, created))


def trigger_and_queue(db, member, evidence_id, packet, cutoff, model=""):
    created, isin = stamp(cutoff), member["isin"]
    with transaction(db) as c:
        if member["state"] == "entered":
            emit_trigger(c, isin, "index_entry", member["snapshot_id"], 3, SPECIALISTS, evidence_id, created)
        if not packet["last_review_at"] or (cutoff - datetime.fromisoformat(packet["last_review_at"])).days >= 30:
            epoch = packet["last_review_at"] or "never"
            emit_trigger(c, isin, "review_expired", epoch, 4, SPECIALISTS, evidence_id, created)
        for doc in packet["documents"]:
            kind = doc["document_type"]
            if any(term in kind for term in ("financial", "annual", "announcement", "governance", "shareholding")):
                specialists = ("governance", "synthesis") if "shareholding" in kind or "governance" in kind else SPECIALISTS
                priority = 2 if "governance" in kind else 3
                emit_trigger(c, isin, kind, doc["content_hash"], priority, specialists, evidence_id, created)
        for flag in packet["governance_flags"]:
            emit_trigger(c, isin, "governance_issue", flag["event_key"], 1 if flag["severity"] == "blocking" else 2,
                         ("governance", "synthesis"), evidence_id, created)
        for fact in packet["ownership"]:
            emit_trigger(c, isin, "promoter_pledge", digest(fact), 2,
                         ("governance", "synthesis"), evidence_id, created)
        prices = packet["prices"]
        if len(prices) == 2 and abs(prices[0]["close"] / prices[1]["close"] - 1) >= 0.05 - 1e-12:
            emit_trigger(c, isin, "daily_move", prices[0]["trade_date"], 2,
                         ("valuation", "daily_forecast", "synthesis"), evidence_id, created)
        # Fixed monitoring bands are triggers only, never buy/sell thresholds.
        if packet["valuation"] and len(prices) == 2:
            pe = packet["valuation"]["value"]
            prior = pe * prices[1]["close"] / prices[0]["close"]
            band = lambda value: sum(value >= boundary for boundary in (15, 25, 40))
            if band(pe) != band(prior):
                emit_trigger(c, isin, "valuation_crossing", prices[0]["trade_date"], 3,
                             ("valuation", "synthesis"), evidence_id, created)
        # Keep incomplete or stale profiles visible, but do not spend model calls on them.
        if packet["coverage"] != "verified":
            return
        # Trigger persistence is deduplicated; current evidence invalidates queued/cache keys.
        events = c.execute("SELECT * FROM research_triggers WHERE isin=?", (isin,)).fetchall()
        required = {}
        for event in events:
            for specialist in json.loads(event["specialists_json"]):
                required[specialist] = min(required.get(specialist, 9), event["priority"])
        for specialist, priority in required.items():
            dependency = dependency_hash(packet, specialist)
            # Review expiry permits a fresh analysis even if numeric evidence did not change.
            if specialist == "synthesis":
                dependency = digest([dependency, cutoff.date().toordinal() // 30])
            job_id = digest([isin, specialist, dependency, PROMPT_VERSION, model])
            c.execute("""UPDATE specialist_jobs SET status='superseded',updated_at=?
                         WHERE isin=? AND specialist=? AND status IN ('queued','waiting')
                         AND job_id!=?""", (created, isin, specialist, job_id))
            c.execute("""INSERT OR IGNORE INTO specialist_jobs
                         (job_id,isin,specialist,evidence_id,dependency_hash,prompt_version,model,
                          priority,status,created_at,updated_at,available_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (job_id, isin, specialist, evidence_id, dependency, PROMPT_VERSION, model,
                       priority, "queued", created, created, created))


def refresh_prices(db, members, as_of, sessions=2):
    """Partial exchange files preserve available companies and disclose absent ones."""
    register_source(db, NSE_EOD_SOURCE_ID, "NSE CM-UDiFF closing data", EvidenceTier.OFFICIAL, NSE_EOD_BASE_URL)
    expected = {row["isin"] for row in members}
    found_sessions = 0
    for offset in range(10):
        day = as_of - timedelta(days=offset)
        if day.weekday() > 4:
            continue
        try:
            prices = NSEBhavcopyCollector().collect(day, expected, require_all=False)
        except HTTPError as exc:
            source_attempt(db, f"nse_eod:{day}", "unavailable", f"HTTP {exc.code}")
            if exc.code == 404:
                continue
            raise
        if not prices:
            source_attempt(db, f"nse_eod:{day}", "missing", "No current members found in official EQ rows")
            continue
        with connect(db) as c:
            for p in prices:
                c.execute("""INSERT INTO price_bars VALUES(?,?,?,?,?,?)
                             ON CONFLICT(isin,trade_date,source_id) DO UPDATE SET
                             close=excluded.close,volume=excluded.volume,retrieved_at=excluded.retrieved_at""",
                          (p.isin, p.trade_date.isoformat(), p.close, p.volume, p.source_id, p.retrieved_at))
        source_attempt(db, f"nse_eod:{day}", "verified" if len(prices) == len(expected) else "partial",
                       f"{len(prices)}/{len(expected)} constituent closes")
        found_sessions += 1
        if found_sessions >= sessions:
            break
    if not found_sessions:
        raise ValueError("No official closing observations acquired")


def refresh_announcements(db, members, start, end, fetch=fetch_official):
    """Collect dated exchange announcement metadata. Full filings need validation separately."""
    url = "https://www.nseindia.com/api/corporate-announcements?" + urlencode(
        {"index": "equities", "from_date": start.strftime("%d-%m-%Y"), "to_date": end.strftime("%d-%m-%Y")})
    rows = json.loads(fetch(url))
    if not isinstance(rows, list):
        raise ValueError("Exchange announcements response is not a list")
    by_symbol = {m["symbol"]: m for m in members}
    register_source(db, "nse_bulk_announcements", "NSE announcements metadata",
                    EvidenceTier.OFFICIAL, "https://www.nseindia.com")
    count = 0
    with connect(db) as c:
        for row in rows:
            member = by_symbol.get(row.get("symbol"))
            if not member:
                continue
            published = datetime.strptime(row["an_dt"], "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
            if not start <= published.date() <= end:
                continue
            attachment = row.get("attchmntFile")
            try:
                location = official_url(attachment) if attachment else url
            except ValueError:
                # The official metadata endpoint remains attributable; do not persist an untrusted attachment URL.
                location = url
            title = str(row.get("desc") or row.get("attchmntText") or "Exchange announcement")
            text = canonical(row)
            doc = CollectedDocument(
                digest(row), member["isin"], "nse_bulk_announcements", "official", "announcement",
                title, stamp(published), stamp(), location, None, "not_applicable", digest(row), text, 1.0)
            cursor = c.execute("""INSERT OR IGNORE INTO documents
                (isin,source_id,document_type,title,published_at,retrieved_at,source_location,
                 content_hash,confidence,raw_text,document_key,reporting_scope)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (doc.isin, doc.source_id, doc.document_type, doc.title, doc.published_at, doc.retrieved_at,
                 doc.source_location, doc.content_hash, doc.confidence, doc.raw_text, doc.document_key, doc.reporting_scope))
            count += cursor.rowcount
            document_id = c.execute("SELECT document_id FROM documents WHERE source_id=? AND content_hash=?",
                                    (doc.source_id, doc.content_hash)).fetchone()[0]
            for flag in evaluate_documents([doc]):
                c.execute("""INSERT OR IGNORE INTO governance_flags
                    (isin,rule_id,event_key,severity,message,source_document_id,detected_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    (doc.isin, flag.rule_id, flag.event_key, flag.severity, flag.message, document_id, stamp()))
    source_attempt(db, "nse_announcements", "verified", f"{count} new metadata records; full filing parsing is separate")
    return count


def screen_universe(db, *, mode="screen", profiles_root="tests/fixtures", refresh=False,
                    model="", expected_price_date=None):
    initialize(db)
    run_id, started = digest([stamp(), mode]), stamp()
    membership, members = current_members(db)
    with connect(db) as c:
        c.execute("INSERT INTO research_runs(run_id,mode,started_at,status,membership_id) VALUES(?,?,?,?,?)",
                  (run_id, mode, started, "running", membership["snapshot_id"] if membership else None))
    errors = []
    try:
        if not members:
            raise ValueError("Official Nifty 500 membership missing; run universe-refresh")
        if refresh:
            day = now_utc().astimezone(IST).date()
            for label, operation in (
                ("prices", lambda: refresh_prices(db, members, day)),
                ("announcements", lambda: refresh_announcements(db, members, day - timedelta(days=7), day)),
            ):
                try:
                    operation()
                except Exception as exc:
                    errors.append(f"{label}: {type(exc).__name__}: {exc}")
                    source_attempt(db, label, "failed", errors[-1])
        cutoff = now_utc()
        profiles = profiles_at(profiles_root)
        for member in members:
            evidence_id, packet = freeze_evidence(db, member, cutoff, profiles, expected_price_date)
            trigger_and_queue(db, member, evidence_id, packet, cutoff, model)
            with connect(db) as c:
                c.execute("INSERT INTO coverage VALUES(?,?,?,?,?,?,?)",
                          (run_id, member["isin"], evidence_id, packet["coverage"],
                           canonical(packet["missing_data"]), packet["prices"][0]["trade_date"] if packet["prices"] else None,
                           packet["last_review_at"]))
        status = "partial" if errors else "completed"
    except Exception as exc:
        status = "failed"
        errors.append(f"{type(exc).__name__}: {exc}")
    with connect(db) as c:
        counts = dict(c.execute("SELECT status,COUNT(*) FROM coverage WHERE run_id=? GROUP BY status", (run_id,)))
        details = {"companies": len(members), "coverage": counts, "errors": errors}
        c.execute("UPDATE research_runs SET status=?,finished_at=?,detail_json=? WHERE run_id=?",
                  (status, stamp(), canonical(details), run_id))
    return {"run_id": run_id, "status": status, **details}
