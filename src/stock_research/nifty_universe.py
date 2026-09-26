"""Official, dated membership and bounded exchange calendars; failures stay visible."""
from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
from datetime import date, datetime, timedelta
from http.cookiejar import CookieJar
from urllib.parse import urlparse

from .db import connect, transaction
from .nifty_store import IST, canonical, digest, initialize, now_utc, source_attempt, stamp

UNIVERSE_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
CALENDAR_URL = "https://www.nseindia.com/api/holiday-master?type=trading"
OFFICIAL_HOSTS = {"nseindia.com", "www.nseindia.com", "nsearchives.nseindia.com",
                  "niftyindices.com", "www.niftyindices.com"}


def official_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS or parsed.username:
        raise ValueError("Source must be an HTTPS NSE or Nifty Indices URL")
    return url


def fetch_official(url):
    official_url(url)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    headers = {"User-Agent": "Mozilla/5.0 fin-AAI local research", "Accept": "*/*"}
    if urlparse(url).hostname == "www.nseindia.com" and "/api/" in url:
        with opener.open(urllib.request.Request("https://www.nseindia.com", headers=headers), timeout=20) as response:
            response.read(100000)
    with opener.open(urllib.request.Request(url, headers=headers), timeout=30) as response:
        official_url(response.url)
        payload = response.read(10_000_001)
    if len(payload) > 10_000_000:
        raise ValueError("Official response exceeds the supported payload size")
    return payload


def taxonomy(industry):
    label = industry.lower()
    if "insurance" in label:
        return "insurance"
    if "bank" in label and "non" not in label:
        return "bank"
    if any(word in label for word in ("finance", "financial", "lending", "investment")):
        return "nbfc_or_financial"
    return "non_financial"


def parse_constituents(payload):
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    required = {"Company Name", "Industry", "Symbol", "ISIN Code"}
    if not required.issubset(reader.fieldnames or ()):
        raise ValueError("Official constituent CSV headers are missing; no universe substituted")
    result, isins, symbols = [], set(), set()
    for row in reader:
        isin, symbol = row["ISIN Code"].strip().upper(), row["Symbol"].strip().upper()
        name, industry = row["Company Name"].strip(), row["Industry"].strip()
        if not re.fullmatch(r"IN[A-Z0-9]{9}[0-9]", isin) or not symbol or not name or not industry:
            raise ValueError("Invalid constituent identity")
        if isin in isins or symbol in symbols:
            raise ValueError("Duplicate ISIN or symbol in official constituent CSV")
        isins.add(isin)
        symbols.add(symbol)
        result.append(dict(isin=isin, symbol=symbol, company_name=name,
                           industry=industry, taxonomy=taxonomy(industry)))
    if not result:
        raise ValueError("Empty constituent CSV")
    return result


def save_membership(db, payload, source_url, observed_at=None, expected_count=500):
    official_url(source_url)
    observed_at = observed_at or now_utc()
    observed_date = observed_at.astimezone(IST).date().isoformat()
    # NSE can publish corporate-action dummy entries alongside the 500 real ISINs.
    # Preserve those raw rows as exclusions, never invent a tradable identity.
    raw_reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    raw_rows = list(raw_reader)
    exclusions = [row for row in raw_rows if row.get("ISIN Code", "").startswith("DUM")
                  and row.get("Symbol", "").startswith("DUMMY")]
    filtered = io.StringIO()
    writer = csv.DictWriter(filtered, fieldnames=raw_reader.fieldnames or [])
    writer.writeheader()
    writer.writerows(row for row in raw_rows if row not in exclusions)
    rows = parse_constituents(filtered.getvalue().encode())
    if expected_count is not None and len(rows) != expected_count:
        raise ValueError(f"Expected {expected_count} official constituents; received {len(rows)}")
    snapshot_id = digest([observed_date, payload.decode("utf-8-sig")])
    with transaction(db) as c:
        if c.execute("SELECT 1 FROM universe_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone():
            return snapshot_id
        previous = c.execute("SELECT * FROM universe_snapshots ORDER BY retrieved_at DESC LIMIT 1").fetchone()
        if previous and previous["retrieved_at"] > stamp(observed_at):
            raise ValueError("Cannot backfill current membership as historical membership")
        old = {r["isin"]: dict(r) for r in c.execute(
            "SELECT * FROM universe_members WHERE snapshot_id=? AND state!='exited'",
            (previous["snapshot_id"] if previous else "",))}
        for row in rows:
            collision = c.execute("SELECT isin FROM securities WHERE nse_symbol=? AND isin!=?",
                                  (row["symbol"], row["isin"])).fetchone()
            if collision:
                raise ValueError(f"Existing symbol maps to a different ISIN: {row['symbol']}")
        c.execute("INSERT INTO universe_snapshots VALUES(?,?,?,?,?,?,?)",
                  (snapshot_id, observed_date, stamp(observed_at), source_url,
                   digest(payload.decode("utf-8-sig")), len(rows), payload.decode("utf-8-sig")))
        for excluded in exclusions:
            c.execute("INSERT INTO universe_exclusions VALUES(?,?,?,?)",
                      (snapshot_id, excluded["Symbol"], canonical(excluded),
                       "Official corporate-action dummy has no standard tradable ISIN"))
        for row in rows:
            c.execute("""INSERT INTO securities(isin,company_name,nse_symbol,sector,created_at,updated_at)
                         VALUES(?,?,?,?,?,?) ON CONFLICT(isin) DO UPDATE SET
                         company_name=excluded.company_name,nse_symbol=excluded.nse_symbol,
                         sector=excluded.sector,updated_at=excluded.updated_at""",
                      (row["isin"], row["company_name"], row["symbol"], row["industry"],
                       stamp(observed_at), stamp(observed_at)))
            c.execute("INSERT INTO universe_members VALUES(?,?,?,?,?,?,?)",
                      (snapshot_id, *[row[k] for k in ("isin", "symbol", "company_name", "industry", "taxonomy")],
                       "retained" if row["isin"] in old else "entered"))
        for isin in old.keys() - {row["isin"] for row in rows}:
            row = old[isin]
            # Symbol reuse is rejected above so exited identities remain auditable.
            c.execute("INSERT INTO universe_members VALUES(?,?,?,?,?,?,?)",
                      (snapshot_id, isin, row["symbol"], row["company_name"], row["industry"],
                       row["taxonomy"], "exited"))
    return snapshot_id


def refresh_universe(db, url=UNIVERSE_URL, fetch=fetch_official):
    initialize(db)
    try:
        result = save_membership(db, fetch(official_url(url)), url)
    except Exception as exc:
        source_attempt(db, "nifty500_constituents", "failed", f"{type(exc).__name__}: {exc}")
        raise
    with connect(db) as c:
        excluded = c.execute("SELECT COUNT(*) FROM universe_exclusions WHERE snapshot_id=?", (result,)).fetchone()[0]
    source_attempt(db, "nifty500_constituents", "verified",
                   f"Snapshot {result}: 500 valid constituents; {excluded} official dummy rows separately preserved")
    return result


def current_members(db, cutoff=None):
    with connect(db) as c:
        snapshot = c.execute("SELECT * FROM universe_snapshots WHERE retrieved_at<=? ORDER BY retrieved_at DESC LIMIT 1",
                             (stamp(cutoff),)).fetchone()
        if not snapshot:
            return None, []
        rows = c.execute("SELECT * FROM universe_members WHERE snapshot_id=? AND state!='exited' ORDER BY symbol",
                         (snapshot["snapshot_id"],)).fetchall()
        return dict(snapshot), [dict(row) for row in rows]


def refresh_calendar(db, fetch=fetch_official):
    initialize(db)
    try:
        payload = json.loads(fetch(CALENDAR_URL))
        rows = payload["CM"]
        holidays = sorted({datetime.strptime(row["tradingDate"], "%d-%b-%Y").date().isoformat()
                           for row in rows})
        year = now_utc().astimezone(IST).year
        holidays = [day for day in holidays if day.startswith(str(year))]
        if len(holidays) < 5:
            raise ValueError("Calendar response has insufficient current-year CM holidays")
        data = {"year": year, "holidays": holidays, "special_sessions": {},
                "source": CALENDAR_URL}
        with connect(db) as c:
            c.execute("INSERT OR IGNORE INTO market_calendars VALUES(?,?,?,?,?)",
                      (digest(data), year, CALENDAR_URL, stamp(), canonical(data)))
        source_attempt(db, "exchange_calendar", "verified", f"{year}: {len(holidays)} holidays")
        return data
    except Exception as exc:
        source_attempt(db, "exchange_calendar", "failed", f"{type(exc).__name__}: {exc}")
        raise


def load_calendar(db, year):
    with connect(db) as c:
        row = c.execute("SELECT payload_json FROM market_calendars WHERE year=? ORDER BY retrieved_at DESC LIMIT 1",
                        (year,)).fetchone()
    if not row:
        raise ValueError(f"Verified exchange calendar missing for {year}; scheduled run abstains")
    return json.loads(row[0])


def session_times(calendar, day):
    if day.year != calendar["year"]:
        raise ValueError("Exchange calendar does not cover target year")
    special = calendar.get("special_sessions", {}).get(day.isoformat())
    if special:
        opening, closing = special["open"], special["close"]
    elif day.weekday() >= 5 or day.isoformat() in calendar["holidays"]:
        return None
    else:
        opening, closing = "09:15", "15:30"
    return tuple(datetime.fromisoformat(f"{day.isoformat()}T{t}").replace(tzinfo=IST)
                 for t in (opening, closing))


def previous_session(calendar, day):
    for offset in range(1, 20):
        candidate = day - timedelta(days=offset)
        if session_times(calendar, candidate):
            return candidate
    raise ValueError("No previous exchange session inside supported calendar window")
