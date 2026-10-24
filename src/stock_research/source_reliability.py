"""Experimental, time-locked reliability review for individual news sources."""
from __future__ import annotations

import hashlib
import json
import math
from contextlib import closing
from datetime import timedelta

from .context_store import ContextError, _check_source, _check_source_event, _db, _json, _stamp, _text, _time
from .market_context import CATEGORIES

SCHEMA = """
CREATE TABLE IF NOT EXISTS ctx_source_adjudications(
 adjudication_id TEXT PRIMARY KEY,
 event_id TEXT NOT NULL REFERENCES ctx_events(event_id),
 company_id TEXT NOT NULL, category TEXT NOT NULL, known_at TEXT NOT NULL,
 payload_json TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS ctx_source_adjudications_update_immutable BEFORE UPDATE ON ctx_source_adjudications BEGIN SELECT RAISE(ABORT,'source history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS ctx_source_adjudications_delete_immutable BEFORE DELETE ON ctx_source_adjudications BEGIN SELECT RAISE(ABORT,'source history is append-only'); END;
CREATE TABLE IF NOT EXISTS ctx_event_reviews(review_id TEXT PRIMARY KEY,event_id TEXT NOT NULL REFERENCES ctx_events(event_id),company_id TEXT NOT NULL,category TEXT NOT NULL,known_at TEXT NOT NULL,payload_json TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS ctx_event_reviews_update_immutable BEFORE UPDATE ON ctx_event_reviews BEGIN SELECT RAISE(ABORT,'review history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS ctx_event_reviews_delete_immutable BEFORE DELETE ON ctx_event_reviews BEGIN SELECT RAISE(ABORT,'review history is append-only'); END;
"""
VERSION = "experimental-source-reliability-v1"


def save_event_reviews(store, records, *, asof) -> int:
    cutoff=_time(asof,"asof")
    if not isinstance(records,list) or any(not isinstance(r,dict) for r in records): raise ContextError("records must be a list of objects")
    _setup(store); db=_db(store.path)
    try:
        db.execute("BEGIN IMMEDIATE")
        events={r["event_id"]:json.loads(r["payload_json"]) for r in db.execute("SELECT event_id,payload_json FROM ctx_events")}
        companies=[(r["canonical_id"],_time(r["known_at"],"known_at")) for r in db.execute("SELECT canonical_id,known_at FROM ctx_nodes WHERE node_type='company'")]
        accepted=[]; seen={}
        for src in records:
            r=dict(src)
            for k in ("review_id","event_id","company_id","category","reviewer_id","origin_status","authentication_method"):_text(r.get(k),k)
            if r["category"] not in CATEGORIES or r["origin_status"] not in {"authenticated_primary","authenticated_publisher","unverified"}: raise ContextError("unsupported category or origin_status")
            known=_time(r.get("known_at"),"known_at")
            if known>cutoff: raise ContextError("review is later than asof")
            event=events.get(r["event_id"])
            if not event or _time(event["available_at"],"available_at")>known: raise ContextError("review event is missing or unavailable")
            if not any(cid==r["company_id"] and at<=known for cid,at in companies): raise ContextError("company is not a known graph company at review time")
            refs=r.get("evidence_refs")
            if not isinstance(refs,list) or (r["origin_status"]!="unverified" and not refs): raise ContextError("authenticated reviews require evidence_refs")
            for ref in refs:
                if not isinstance(ref,dict) or not isinstance(ref.get("citation"),str) or not ref["citation"].strip(): raise ContextError("evidence reference requires precise citation text")
                kt=_check_source(ref,"evidence_ref"); _check_source_event(ref,"evidence_ref",events,kt)
                if kt>known: raise ContextError("evidence is later than review")
            if r["origin_status"]!="unverified" and not any(ref["source_id"]==event["source_id"] and ref["source_url"]==event["source_url"] and ref["raw_hash"]==event["raw_hash"] for ref in refs): raise ContextError("authenticated review evidence must cite the reviewed event")
            support=r.get("corroboration_event_ids")
            if not isinstance(support,list) or any(not isinstance(x,str) or not x for x in support) or len(set(support))!=len(support): raise ContextError("corroboration_event_ids must be unique event IDs")
            origins=set()
            for eid in support:
                cited=events.get(eid)
                if not cited or _time(cited["available_at"],"available_at")>known or eid==r["event_id"] or cited["source_id"]==event["source_id"] or cited["canonical_id"]==event["canonical_id"]: raise ContextError("corroboration must be timely, distinct-origin, and independent")
                origins.add(cited["source_id"])
            if len(origins)!=len(support): raise ContextError("corroboration requires distinct source origins")
            r["canonical_id"]=event["canonical_id"]
            encoded=_json(r)
            if r["review_id"] in seen:
                if seen[r["review_id"]]!=encoded: raise ContextError("review ID repeated with different content")
                continue
            seen[r["review_id"]]=encoded
            for prior_row in db.execute("SELECT payload_json FROM ctx_event_reviews WHERE event_id=? AND company_id=? AND category=?",(r["event_id"],r["company_id"],r["category"])):
                old=json.loads(prior_row[0])
                if _time(old["known_at"],"known_at")==known and (old["origin_status"],old["authentication_method"],old["corroboration_event_ids"])!=(r["origin_status"],r["authentication_method"],r["corroboration_event_ids"]): raise ContextError("conflicting same-time event reviews")
            prior=db.execute("SELECT payload_json FROM ctx_event_reviews WHERE review_id=?",(r["review_id"],)).fetchone()
            if prior:
                if prior[0]!=encoded: raise ContextError("review ID already exists with different content")
            else: accepted.append((r,known,encoded))
        for r,known,encoded in accepted: db.execute("INSERT INTO ctx_event_reviews VALUES(?,?,?,?,?,?)",(r["review_id"],r["event_id"],r["company_id"],r["category"],_stamp(known),encoded))
        db.commit(); return len(accepted)
    except Exception: db.rollback(); raise
    finally: db.close()


def _latest_review(db, event_id, company_id, category, cutoff):
    rows=[json.loads(r[0]) for r in db.execute("SELECT payload_json FROM ctx_event_reviews WHERE event_id=? AND company_id=? AND category=?",(event_id,company_id,category))]
    rows=[r for r in rows if _time(r["known_at"],"known_at")<=cutoff]
    if not rows:return None
    rows.sort(key=lambda r:(_time(r["known_at"],"known_at"),r["review_id"]))
    tied=[r for r in rows if _time(r["known_at"],"known_at")==_time(rows[-1]["known_at"],"known_at")]
    if len({(r["origin_status"],tuple(r["corroboration_event_ids"])) for r in tied})>1:raise ContextError("conflicting same-time event reviews")
    return tied[0]


def _setup(store):
    if not store.path.exists():
        raise ContextError("context database does not exist")
    with closing(_db(store.path)) as db, db:
        db.executescript(SCHEMA)


def save_adjudications(store, records, *, asof) -> int:
    cutoff = _time(asof, "asof")
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise ContextError("records must be a list of objects")
    _setup(store)
    db = _db(store.path)
    try:
        db.execute("BEGIN IMMEDIATE")
        events = {r["event_id"]: json.loads(r["payload_json"]) for r in db.execute("SELECT event_id,payload_json FROM ctx_events")}
        companies = [(r["canonical_id"], _time(r["known_at"], "node.known_at")) for r in db.execute("SELECT canonical_id,known_at FROM ctx_nodes WHERE node_type='company'")]
        accepted=[]; seen={}; times={}
        for supplied in records:
            r=dict(supplied)
            for k in ("adjudication_id","event_id","company_id","category","verdict","reviewer_id"):
                _text(r.get(k), f"{k}")
            if r["category"] not in CATEGORIES or r["verdict"] not in {"confirmed","refuted","unresolved"}:
                raise ContextError("unsupported category or verdict")
            known=_time(r.get("known_at"),"known_at")
            if known>cutoff: raise ContextError("adjudication is later than asof")
            event=events.get(r["event_id"])
            if event is None: raise ContextError("adjudication references missing event")
            available=_time(event["available_at"],"event.available_at")
            if known<available: raise ContextError("adjudication predates event availability")
            if not any(cid==r["company_id"] and nk<=known for cid,nk in companies):
                raise ContextError("company is not a known graph company at adjudication time")
            refs=r.get("evidence_refs")
            if not isinstance(refs,list) or not refs: raise ContextError("evidence_refs must be a nonempty list")
            for ref in refs:
                if not isinstance(ref,dict) or not isinstance(ref.get("citation"),str) or not ref["citation"].strip():
                    raise ContextError("each evidence reference needs precise citation text")
                evidence_known=_check_source(ref,"evidence_ref")
                _check_source_event(ref,"evidence_ref",events,evidence_known)
                if evidence_known>known: raise ContextError("evidence is later than adjudication")
            verification=r.get("verification_refs")
            if not isinstance(verification,list) or (r["verdict"] in {"confirmed","refuted"} and not verification): raise ContextError("confirmed or refuted adjudications require verification_refs")
            for ref in verification:
                if not isinstance(ref,dict) or not isinstance(ref.get("citation"),str) or not ref["citation"].strip(): raise ContextError("verification reference requires precise citation text")
                kt=_check_source(ref,"verification_ref"); _check_source_event(ref,"verification_ref",events,kt)
                if kt>known: raise ContextError("verification evidence is later than adjudication")
                if ref["source_url"]==event["source_url"] and ref["raw_hash"].lower()==event["raw_hash"].lower(): raise ContextError("verification must be independent of the report under review")
            if not any(ref["source_id"]==event["source_id"] and ref["source_url"]==event["source_url"] and ref["raw_hash"]==event["raw_hash"] for ref in refs): raise ContextError("adjudication evidence must cite the reviewed event")
            r["canonical_id"]=event["canonical_id"]
            encoded=_json(r)
            if r["adjudication_id"] in seen:
                if seen[r["adjudication_id"]]!=encoded: raise ContextError("adjudication ID repeated with different content")
                continue
            seen[r["adjudication_id"]]=encoded
            tie=(event["source_id"],r["canonical_id"],r["company_id"],r["category"],known)
            if tie in times and times[tie]!=r["verdict"]: raise ContextError("conflicting same-time adjudications")
            times[tie]=r["verdict"]
            for oldrow in db.execute("SELECT a.payload_json,e.payload_json FROM ctx_source_adjudications a JOIN ctx_events e USING(event_id) WHERE a.company_id=? AND a.category=?",(r["company_id"],r["category"])):
                old,oldevent=map(json.loads,oldrow)
                if oldevent["source_id"]==event["source_id"] and old["canonical_id"]==r["canonical_id"] and _time(old["known_at"],"known_at")==known and old["verdict"]!=r["verdict"]: raise ContextError("conflicting same-time adjudications")
            prior=db.execute("SELECT payload_json FROM ctx_source_adjudications WHERE adjudication_id=?",(r["adjudication_id"],)).fetchone()
            if prior:
                if prior[0]!=encoded: raise ContextError("adjudication ID already exists with different content")
            else: accepted.append((r,encoded,known))
        for r,encoded,known in accepted:
            db.execute("INSERT INTO ctx_source_adjudications VALUES(?,?,?,?,?,?)",(r["adjudication_id"],r["event_id"],r["company_id"],r["category"],_stamp(known),encoded))
        db.commit()
        return len(accepted)
    except Exception:
        db.rollback(); raise
    finally: db.close()


def _adjudications(db, *, source_id, company_id, category, cutoff, exclude=None):
    rows=[]
    for row in db.execute("SELECT a.payload_json,e.payload_json FROM ctx_source_adjudications a JOIN ctx_events e USING(event_id) WHERE a.company_id=? AND a.category=?",(company_id,category)):
        a,event=map(json.loads,row)
        if event["source_id"]==source_id and _time(a["known_at"],"known_at")<=cutoff and (exclude is None or event["canonical_id"]!=exclude): rows.append((a,event))
    latest={}
    for a,e in rows:
        key=(e["canonical_id"],a["company_id"],a["category"])
        current=latest.get(key)
        stamp=_time(a["known_at"],"known_at")
        if current is None or stamp>current[0]: latest[key]=(stamp,a,e)
        elif stamp==current[0] and a["verdict"]!=current[1]["verdict"]: raise ContextError("conflicting same-time adjudications")
    return sorted((x[1] for x in latest.values()),key=lambda a:a["adjudication_id"])


def _score(db, source_id, company_id, category, cutoff, exclude=None):
    outcomes=_adjudications(db,source_id=source_id,company_id=company_id,category=category,cutoff=cutoff,exclude=exclude)
    resolved=[a for a in outcomes if a["verdict"]!="unresolved"]
    confirmed=sum(a["verdict"]=="confirmed" for a in resolved); n=len(resolved)
    p=(confirmed+1)/(n+2)
    raw=confirmed/n if n else 0.0
    z=1.959963984540054
    lower=(raw+z*z/(2*n)-z*math.sqrt((raw*(1-raw)+z*z/(4*n))/n))/(1+z*z/n) if n else 0.0
    core={"version":VERSION,"source_id":source_id,"company_id":company_id,"category":category,"asof":_stamp(cutoff),"confirmed":confirmed,"refuted":n-confirmed,"unresolved":len(outcomes)-n,"resolved_n":n,"mean":p,"wilson_lower95":lower,"cold_start":n==0,"calibrated":False,"adjudication_ids":[a["adjudication_id"] for a in outcomes],"live_order_authorized":False}
    core["score_hash"]=hashlib.sha256(_json(core).encode()).hexdigest()
    return core


def source_reliability(store, *, source_id, company_id, category, asof) -> dict:
    cutoff=_time(asof,"asof")
    for v,n in ((source_id,"source_id"),(company_id,"company_id")):_text(v,n)
    if category not in CATEGORIES: raise ContextError("unsupported category")
    _setup(store)
    with closing(_db(store.path)) as db:
        if not any(_time(json.loads(r[0])["available_at"],"available_at")<=cutoff for r in db.execute("SELECT payload_json FROM ctx_events WHERE json_extract(payload_json,'$.source_id')=?",(source_id,))):
            raise ContextError("source is not present in event history")
        return _score(db,source_id,company_id,category,cutoff)


def response_policy(store, *, event_id, company_id, category, asof) -> dict:
    cutoff=_time(asof,"asof"); _text(event_id,"event_id"); _text(company_id,"company_id")
    if category not in CATEGORIES: raise ContextError("unsupported category")
    _setup(store)
    with closing(_db(store.path)) as db:
        row=db.execute("SELECT payload_json,canonical_id,available_at FROM ctx_events WHERE event_id=?",(event_id,)).fetchone()
        if not row: raise ContextError("event does not exist")
        event=json.loads(row[0]); available=_time(row[2],"available_at")
        if cutoff<available: raise ContextError("event is not available at asof")
        decision=cutoff
        if not db.execute("SELECT 1 FROM ctx_nodes WHERE node_type='company' AND canonical_id=? AND known_at<=? LIMIT 1",(company_id,_stamp(cutoff))).fetchone(): raise ContextError("company is not known at asof")
        reliability=_score(db,event["source_id"],company_id,category,available,exclude=row[1])
        published=_time(event["published_at"],"published_at") if event.get("published_at") else None
        publisher_age=(available-published).total_seconds() if published else None
        age=(cutoff-published).total_seconds() if published else None
        current=_latest_review(db,event_id,company_id,category,cutoff)
        latest=_adjudications(db,source_id=event["source_id"],company_id=company_id,category=category,cutoff=cutoff,exclude=None)
        current_verdict=next((a["verdict"] for a in latest if a["canonical_id"]==row[1]),None)
        if current_verdict=="refuted": action="abstain_directional_entry"
        elif age is None or publisher_age is None or publisher_age>300 or age>300: action="monitor_now"
        elif cutoff-available>timedelta(seconds=60): action="monitor_now"
        elif current and (current["origin_status"]=="authenticated_primary" or (current["origin_status"]=="authenticated_publisher" and current["corroboration_event_ids"] and reliability["resolved_n"]>=20 and reliability["wilson_lower95"]>=.8)): action="paper_evaluate_now"
        else: action="monitor_now"
        gaps=[]
        if not current: gaps.append("No bounded origin review is available.")
        if current and current["origin_status"]=="authenticated_publisher" and not current["corroboration_event_ids"]: gaps.append("Publisher review lacks independent-origin corroboration.")
        if current and current["origin_status"]=="authenticated_publisher" and (reliability["resolved_n"]<20 or reliability["wilson_lower95"]<.8): gaps.append("Publisher route lacks sufficient resolved source history.")
        elif current and current["origin_status"]=="authenticated_primary" and reliability["resolved_n"]<20: gaps.append("Source history is unavailable; primary review can qualify without it.")
        if publisher_age is None: gaps.append("Publication time is unknown.")
        elif publisher_age>300: gaps.append("Publisher report was over 300 seconds old at receipt.")
        observed_age=(cutoff-available).total_seconds()
        if observed_age>60: gaps.append("Event is not within the 60-second receipt freshness window.")
        return {"event_id":event_id,"canonical_id":row[1],"source_id":event["source_id"],"company_id":company_id,"category":category,"asof":_stamp(cutoff),"decision_at":_stamp(cutoff),"event_received_at":_stamp(available),"reliability_cutoff_at":_stamp(available),"observed_age_seconds":observed_age,"publisher_age_seconds":age,"latest_current_review":current,"latest_current_verdict":current_verdict,"action":action,"action_reason":"known refutation" if current_verdict=="refuted" else "fresh authenticated source review and policy gates" if action=="paper_evaluate_now" else "one or more paper-evaluation gates are unmet","policy_version":VERSION,"known_gaps":gaps,"impact_status":"unvalidated","requires_future_execution_gates":True,"monitor_risk":True,"reliability":reliability,"live_order_authorized":False,"execution":"none","interpretation":"experimental paper evaluation only; reviewer authentication assertion does not establish claim truth or price impact"}
