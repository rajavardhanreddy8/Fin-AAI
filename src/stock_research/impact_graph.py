"""Directed, evidence-backed impact graph and review-only linear candidates."""
from __future__ import annotations
import hashlib, json, math
from datetime import datetime, timezone
from .market_context import CATEGORIES

def _dt(v):
    if not isinstance(v, str): raise ValueError("timezone-aware timestamp required")
    try: d=datetime.fromisoformat(v.replace("Z","+00:00"))
    except ValueError: raise ValueError("invalid timestamp") from None
    if d.tzinfo is None: raise ValueError("timezone-aware timestamp required")
    return d.astimezone(timezone.utc)
def _finite(v, lo, hi, name):
    if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi: raise ValueError(f"{name} out of bounds")
def _digest(v,name):
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v.lower()): raise ValueError(f"{name} must be SHA-256 hex")
def _canonical(v): return json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False)

def build_snapshot(report: dict, scored_edges: list[dict], *, asof: str, company_id: str, horizon_minutes: int) -> dict:
    cutoff=_dt(asof)
    if type(horizon_minutes) is not int or horizon_minutes<1: raise ValueError("positive horizon_minutes required")
    if not isinstance(report,dict) or _dt(report.get("asof"))!=cutoff: raise ValueError("report asof mismatch")
    trust=report.get("what_trust",{}); who=report.get("who_how",{})
    rels={r.get("relationship_id"):r for r in who.get("relationships",[]) if isinstance(r,dict)}
    claims={c.get("claim_id"):c for c in trust.get("claims",[]) if isinstance(c,dict)}
    events={e.get("event_id"):e for e in trust.get("events",[]) if isinstance(e,dict)}
    if not isinstance(scored_edges,list) or any(not isinstance(x,dict) for x in scored_edges): raise ValueError("scored_edges must be a list of objects")
    seen=set(); edges=[]; contrib={}; versions=set(); feature_times=[]
    for score in sorted(scored_edges,key=lambda x:(str(x.get("relationship_id","")),str(x.get("horizon_minutes","")))):
        if not isinstance(score,dict): raise ValueError("scores must be objects")
        rid=score.get("relationship_id")
        score_identity=(rid,score.get("horizon_minutes"))
        if not isinstance(rid,str) or not rid or score_identity in seen: raise ValueError("unique relationship_id and horizon required")
        seen.add(score_identity); rel=rels.get(rid)
        if rel is None: raise ValueError("score references missing relationship")
        try: known=_dt(rel["known_at"]); scored=_dt(score.get("score_known_at"))
        except (KeyError,TypeError): raise ValueError("relationship and score timestamps required") from None
        if known>cutoff or scored>cutoff: continue
        if scored<known or not isinstance(score.get("score_version"),str) or not score["score_version"]: raise ValueError("score timing/version invalid")
        mode=score.get("score_mode")
        if mode=="manual":
            if not isinstance(score.get("manual_version"),str) or not score["manual_version"]: raise ValueError("manual score requires manual_version")
        elif mode=="model":
            if not all(isinstance(score.get(k),str) and score[k] for k in ("audit_call_id","audit_model_version")) or score.get("audit_status")!="completed" or _dt(score.get("audit_available_at"))!=scored:
                raise ValueError("model score requires completed audit identity available at score time")
        else: raise ValueError("score_mode must explicitly be manual or model")
        cited=rel.get("claim_ids")
        if not isinstance(cited,list) or not cited: raise ValueError("relationship requires cited claims")
        event_ids=set()
        for cid in cited:
            claim=claims.get(cid)
            if not isinstance(cid,str) or not isinstance(claim,dict): raise ValueError("missing cited claim")
            try: claim_known=_dt(claim["known_at"]); event=events.get(claim["event_id"]); available=_dt(event["available_at"])
            except (KeyError,TypeError): raise ValueError("claim must reference typed visible event with timestamps") from None
            if claim_known>scored or available>scored: raise ValueError("score predates cited claim or event")
            if not isinstance(claim["event_id"],str): raise ValueError("invalid cited event identity")
            event_ids.add(claim["event_id"])
        for name,lo,hi in (("sentiment",-1,1),("impact_weight",-1,1),("confidence",0,1)):_finite(score.get(name),lo,hi,name)
        if score.get("category") not in CATEGORIES or type(score.get("horizon_minutes")) is not int or score["horizon_minutes"]<1: raise ValueError("invalid score category or horizon")
        st,sid,ot,oid=(rel.get(x) for x in ("subject_type","subject_id","object_type","object_id"))
        if not all(isinstance(x,str) and x for x in (st,sid,ot,oid)) or not isinstance(rel.get("relationship_type"),str): raise ValueError("typed relationship endpoints required")
        edge={**score,"known_at":rel["known_at"],"subject_type":st,"subject_id":sid,"object_type":ot,"object_id":oid,"relationship_type":rel["relationship_type"],"event_ids":sorted(event_ids)}
        edges.append(edge); versions.add(score["score_version"])
        if oid==company_id and ot=="company" and score["horizon_minutes"]==horizon_minutes:
            key=f"{score['category']}|{rel['relationship_type']}|{st}"
            for eid in event_ids: contrib.setdefault((eid,key),score["sentiment"]*score["confidence"]*score["impact_weight"])
            feature_times.append(scored)
    features={}
    for (_,key),value in sorted(contrib.items()): features[key]=features.get(key,0.0)+value
    feature_hash=hashlib.sha256(_canonical(sorted(features)).encode()).hexdigest()
    adjacency={}
    for edge in edges:
        ref={"relationship_id":edge["relationship_id"],"horizon_minutes":edge["horizon_minutes"]}
        source=f"{edge['subject_type']}/{edge['subject_id']}"; target=f"{edge['object_type']}/{edge['object_id']}"
        adjacency.setdefault(source,{"incoming":[],"outgoing":[]})["outgoing"].append(ref)
        adjacency.setdefault(target,{"incoming":[],"outgoing":[]})["incoming"].append(ref)
    for entry in adjacency.values():
        for direction in ("incoming","outgoing"):
            entry[direction].sort(key=lambda ref:(ref["relationship_id"],ref["horizon_minutes"]))
    result={"asof":asof,"company_id":company_id,"horizon_minutes":horizon_minutes,"edges":sorted(edges,key=lambda e:(e["relationship_id"],e["horizon_minutes"])),"adjacency":adjacency,"features":features,"feature_hash":feature_hash,"features_known_at":max(feature_times).isoformat().replace("+00:00","Z") if feature_times else None,"score_versions":sorted(versions),"feature_deduplication":"one contribution per event and structural feature; lexically first relationship_id represents parallel edges","known_gaps":[] if features else ["No scored, evidence-supported incoming edge at this horizon."],"interpretation":"heuristic features; not a probability, forecast, or causal price-impact estimate; score audit references are not cryptographically authenticated here"}
    result["snapshot_hash"]=hashlib.sha256(_canonical(result).encode()).hexdigest()
    return result

def _dot(x,w): return w.get("__intercept__",0.0)+sum(v*w.get(k,0.0) for k,v in x.items())
def _validate_features(features, keys=None):
    if not isinstance(features,dict): raise ValueError("features must be an object")
    for k,v in features.items():
        if not isinstance(k,str) or not k or k in {"sample_id","event_id","decision_id"}: raise ValueError("feature names must be structural keys")
        _finite(v,-1e12,1e12,"feature")
    if keys is not None and set(features)-set(keys): raise ValueError("unknown feature key")

def predict_candidate(candidate:dict, snapshot:dict, *, at:str, horizon_minutes:int):
    available=_dt(candidate.get("available_at")); when=_dt(at)
    if when<available: raise ValueError("candidate unavailable at prediction time")
    if candidate.get("status")!="candidate_review_only" or not isinstance(candidate.get("candidate_version"),str) or not candidate["candidate_version"] or not isinstance(candidate.get("parent_version"),str) or not candidate["parent_version"] or candidate["candidate_version"]==candidate["parent_version"]: raise ValueError("unreviewed candidate metadata required")
    if horizon_minutes!=candidate.get("horizon_minutes") or snapshot.get("horizon_minutes")!=horizon_minutes: raise ValueError("prediction horizon mismatch")
    frozen={k:v for k,v in snapshot.items() if k!="snapshot_hash"}
    if snapshot.get("snapshot_hash")!=hashlib.sha256(_canonical(frozen).encode()).hexdigest(): raise ValueError("snapshot hash does not match payload")
    asof=_dt(snapshot.get("asof")); features_known=_dt(snapshot.get("features_known_at"))
    if asof>when or features_known>asof: raise ValueError("snapshot contains information unavailable at prediction time")
    if candidate.get("company_id") is not None and candidate["company_id"]!=snapshot.get("company_id"): raise ValueError("candidate company mismatch")
    _validate_features(snapshot.get("features"),candidate.get("feature_keys",[]))
    if snapshot.get("feature_hash")!=hashlib.sha256(_canonical(sorted(snapshot["features"])).encode()).hexdigest(): raise ValueError("snapshot feature schema mismatch")
    weights=candidate.get("weights")
    if not isinstance(weights,dict) or set(weights)!=(set(candidate.get("feature_keys",[]))|{"__intercept__"}): raise ValueError("candidate coefficients do not match feature schema")
    for v in weights.values(): _finite(v,-1e12,1e12,"coefficient")
    if _dt(snapshot.get("features_known_at"))>when: raise ValueError("snapshot features unavailable at prediction time")
    return _dot(snapshot["features"],weights)

def manual_candidate(*,version:str,parent_version:str,coefficients:dict,feature_keys:list[str],horizon_minutes:int,available_at:str,company_id:str|None=None):
    if not version or not parent_version or version==parent_version: raise ValueError("distinct candidate and parent versions required")
    if type(horizon_minutes)is not int or horizon_minutes<1: raise ValueError("positive horizon required")
    _dt(available_at)
    if not isinstance(feature_keys,list) or any(not isinstance(k,str) or not k for k in feature_keys): raise ValueError("feature_keys must be structural names")
    keys=sorted(set(feature_keys)); _validate_features(coefficients,set(keys)|{"__intercept__"})
    weights={k:float(coefficients.get(k,0.0)) for k in keys}; weights["__intercept__"]=float(coefficients.get("__intercept__",0.0))
    return {"candidate_version":version,"parent_version":parent_version,"weights":weights,"feature_keys":keys,"horizon_minutes":horizon_minutes,"available_at":available_at,"company_id":company_id,"status":"candidate_review_only","auto_promote":False}

def train_candidate(samples:list[dict], *, train_cutoff:str, validation_cutoff:str, horizon_minutes:int, parent_version:str, candidate_version:str, available_at:str, learning_rate:float=.01, epochs:int=500):
    train_end,val_end=_dt(train_cutoff),_dt(validation_cutoff); available=_dt(available_at)
    if val_end<=train_end or available<val_end: raise ValueError("validation and candidate availability cutoffs must be ordered")
    if not isinstance(parent_version,str) or not parent_version or not isinstance(candidate_version,str) or not candidate_version or parent_version==candidate_version: raise ValueError("distinct nonempty versions required")
    if type(horizon_minutes)is not int or horizon_minutes<1: raise ValueError("positive horizon required")
    _finite(learning_rate,1e-12,1.0,"learning_rate")
    if type(epochs)is not int or not 1<=epochs<=100000: raise ValueError("epochs must be 1..100000")
    if not isinstance(samples,list): raise ValueError("samples must be a list")
    eligible=[]; ids=set(); groups=set(); excluded_horizon=0; excluded_unknown=0; companies=set(); provenances=set()
    for s in samples:
        if not isinstance(s,dict): raise ValueError("samples must be objects")
        sid=s.get("sample_id"); group=(s.get("event_id"),s.get("decision_at"),s.get("horizon_minutes"))
        if not isinstance(sid,str) or not sid or sid in ids or None in group or group in groups: raise ValueError("unique sample_id and event/decision/horizon required")
        ids.add(sid);groups.add(group)
        if s.get("horizon_minutes")!=horizon_minutes: excluded_horizon+=1; continue
        if s.get("provenance") not in {"real","fixture"}: raise ValueError("provenance must explicitly be real or fixture")
        snapshot=s.get("snapshot")
        if not isinstance(snapshot,dict): raise ValueError("frozen snapshot object required")
        supplied_hash=snapshot.get("snapshot_hash"); frozen={k:v for k,v in snapshot.items() if k!="snapshot_hash"}
        expected_sh=hashlib.sha256(_canonical(frozen).encode()).hexdigest()
        if supplied_hash!=expected_sh: raise ValueError("snapshot hash does not match frozen payload")
        if snapshot.get("company_id")!=s.get("company_id") or snapshot.get("horizon_minutes")!=horizon_minutes: raise ValueError("snapshot company or horizon mismatch")
        if not isinstance(s.get("company_id"),str) or not s["company_id"]: raise ValueError("company_id required")
        features=snapshot.get("features"); _validate_features(features)
        expected_fh=hashlib.sha256(_canonical(sorted(features)).encode()).hexdigest()
        if snapshot.get("feature_hash")!=expected_fh: raise ValueError("feature_hash does not match frozen feature schema")
        d,o,k=map(_dt,(s.get("decision_at"),s.get("outcome_completed_at"),s.get("label_known_at")))
        snapshot_asof=_dt(snapshot.get("asof"))
        l=_dt(snapshot.get("features_known_at"))
        if snapshot_asof>d or l>snapshot_asof: raise ValueError("snapshot contains future information")
        if not d<o<=k: raise ValueError("label must follow decision and completion")
        y=s.get("target_return_bps"); _finite(y,-1e12,1e12,"target_return_bps")
        s={**s,"features":features,"snapshot_hash":supplied_hash,"feature_hash":snapshot["feature_hash"],"features_known_at":snapshot["features_known_at"]}
        companies.add(s["company_id"]); provenances.add(s["provenance"])
        if k<=train_end and d<=train_end: eligible.append((d,o,s,"train"))
        elif train_end<d<o<=k<=val_end: eligible.append((d,o,s,"validation"))
        else: excluded_unknown+=1
    train=[x for x in eligible if x[3]=="train"]; val=[x for x in eligible if x[3]=="validation"]
    if len(companies)>1: raise ValueError("training samples must use one company")
    validation_events={x[2]["event_id"] for x in val}
    purged_event_count=sum(x[2]["event_id"] in validation_events for x in train)
    train=[x for x in train if x[2]["event_id"] not in validation_events and not any(x[0]<v[1] and v[0]<x[1] for v in val)]
    if len(train)<20 or len(val)<5: raise ValueError("need at least 20 train and 5 validation examples")
    keys=sorted({k for _,_,s,_ in train for k in s["features"]}); w={k:0.0 for k in keys}; w["__intercept__"]=0.0
    for _ in range(epochs):
        grad={k:0.0 for k in w}
        for _,_,s,_ in train:
            x=s["features"]; err=_dot(x,w)-s["target_return_bps"]; grad["__intercept__"]+=2*err/len(train)
            for k in keys: grad[k]+=2*err*x.get(k,0.0)/len(train)
        for k in w:
            w[k]-=learning_rate*grad[k]
            if not math.isfinite(w[k]): raise ValueError("nonfinite gradient; reduce learning_rate")
    def mse(rows,weighted): return sum(((_dot(s["features"],w) if weighted else 0.0)-s["target_return_bps"])**2 for _,_,s,_ in rows)/len(rows)
    fh=hashlib.sha256(_canonical(keys).encode()).hexdigest()
    provenance_status="fixture_only" if provenances=={"fixture"} else "real_unverified" if provenances=={"real"} else "mixed_fixture_and_real"
    return {"candidate_version":candidate_version,"parent_version":parent_version,"company_id":next(iter(companies)),"feature_hash":fh,"feature_keys":keys,"weights":w,"training_cutoff":train_cutoff,"validation_cutoff":validation_cutoff,"available_at":available_at,"horizon_minutes":horizon_minutes,"train_count":len(train),"validation_count":len(val),"training_provenance_counts":{"real":sum(x[2]["provenance"]=="real" for x in eligible),"fixture":sum(x[2]["provenance"]=="fixture" for x in eligible)},"training_data_status":provenance_status,"purged_shared_event_count":purged_event_count,"excluded_horizon_count":excluded_horizon,"excluded_unknown_count":excluded_unknown,"validation_mse":mse(val,True),"zero_baseline_validation_mse":mse(val,False),"status":"candidate_review_only","validation_interpretation":"chronological validation only; not heldout performance","auto_promote":False}
