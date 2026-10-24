import pytest
from stock_research.context_store import ContextError, ContextStore
from stock_research.source_reliability import save_adjudications, save_event_reviews, source_reliability, response_policy

T="2026-01-01T00:00:00Z"
def ev(eid, canon, source="wire", when=T, published=T):
    return {"event_id":eid,"canonical_id":canon,"source_id":source,"source_url":f"https://news.test/{eid}","raw_hash":(eid[0] if eid[0] in "abcdef0123456789" else "a")*64,"published_at":published,"observed_at":when,"available_at":when,"verification_status":"unverified","title":eid,"entities":["ACME"]}
def evidence(e, known=T):
    return {"source_id":e["source_id"],"source_url":e["source_url"],"raw_hash":e["raw_hash"],"known_at":known,"source_event_id":e["event_id"],"citation":"paragraph 2, sentence 1"}
def setup(tmp_path, count=1):
    s=ContextStore(tmp_path/"ctx.db"); events=[ev(f"e{i}",f"story{i}",when=f"2026-01-01T00:00:{i:02d}Z",published=f"2026-01-01T00:00:{i:02d}Z") for i in range(count)]
    nodes=[{"node_type":"company","node_id":"acme","canonical_id":"ACME","known_at":T,"effective_from":T,"source":{"source_id":"wire","source_url":"https://news.test/e0","raw_hash":"e"*64,"known_at":T}}]
    s.import_batch({"events":events,"nodes":nodes,"claims":[],"relationships":[],"analogs":[]})
    return s,events
def record(e, i, verdict="confirmed", known=T):
    verification={"source_id":"independent","source_url":"https://verify.test/correction","raw_hash":"f"*64,"known_at":known,"citation":"filing paragraph 4"}
    return {"adjudication_id":f"a{i}","event_id":e["event_id"],"company_id":"ACME","category":"company_performance","verdict":verdict,"known_at":known,"reviewer_id":"reviewer","evidence_refs":[evidence(e,known)],"verification_refs":[verification] if verdict!="unresolved" else []}
def review(e, rid="r1", origin="authenticated_primary", support=None, known=None):
    known=known or e["available_at"]
    return {"review_id":rid,"event_id":e["event_id"],"company_id":"ACME","category":"company_performance","known_at":known,"reviewer_id":"reviewer","origin_status":origin,"authentication_method":"issuer domain and signature review","evidence_refs":[evidence(e,known)],"corroboration_event_ids":support or []}

def test_asof_revisions_raw_events_dedup_and_immutable(tmp_path):
    s,es=setup(tmp_path,2); a=record(es[0],1); assert save_adjudications(s,[a],asof=T)==1
    later="2026-01-01T00:01:00Z"; correction=record(es[0],2,"refuted",later); correction["evidence_refs"]=[evidence(es[0],later)]
    assert save_adjudications(s,[correction],asof=later)==1
    assert source_reliability(s,source_id="wire",company_id="ACME",category="company_performance",asof=T)["confirmed"]==1
    score=source_reliability(s,source_id="wire",company_id="ACME",category="company_performance",asof=later)
    assert (score["confirmed"],score["refuted"],score["resolved_n"])==(0,1,1)
    with pytest.raises(ContextError): save_adjudications(s,[{**a,"verdict":"refuted"}],asof=T)
    with pytest.raises(Exception):
        import sqlite3
        with sqlite3.connect(s.path) as db: db.execute("DELETE FROM ctx_source_adjudications")

def test_single_source_cold_start_refutation_and_target_exclusion(tmp_path):
    s,es=setup(tmp_path); assert source_reliability(s,source_id="wire",company_id="ACME",category="company_performance",asof=T)["cold_start"]
    assert response_policy(s,event_id="e0",company_id="ACME",category="company_performance",asof=T)["action"]=="monitor_now"
    a=record(es[0],1,"refuted"); save_adjudications(s,[a],asof=T)
    result=response_policy(s,event_id="e0",company_id="ACME",category="company_performance",asof=T)
    assert result["action"]=="abstain_directional_entry" and result["monitor_risk"] and not result["live_order_authorized"]
    assert result["reliability"]["resolved_n"]==0

def test_reject_bad_verdict_future_and_unknown_source(tmp_path):
    s,es=setup(tmp_path)
    with pytest.raises(ContextError): save_adjudications(s,[record(es[0],1,"BUY")],asof=T)
    with pytest.raises(ContextError): save_adjudications(s,[record(es[0],1,known="2026-01-02T00:00:00Z")],asof=T)
    with pytest.raises(ContextError): source_reliability(s,source_id="unknown",company_id="ACME",category="company_performance",asof=T)
    own=record(es[0],2); own["verification_refs"]=own["evidence_refs"]
    with pytest.raises(ContextError): save_adjudications(s,[own],asof=T)

def test_authenticated_primary_can_paper_evaluate_without_history_but_refutation_blocks(tmp_path):
    s,es=setup(tmp_path); save_event_reviews(s,[review(es[0])],asof=T)
    assert response_policy(s,event_id="e0",company_id="ACME",category="company_performance",asof=T)["action"]=="paper_evaluate_now"
    save_adjudications(s,[record(es[0],1,"refuted")],asof=T)
    assert response_policy(s,event_id="e0",company_id="ACME",category="company_performance",asof=T)["action"]=="abstain_directional_entry"

def test_unverified_high_history_and_future_history_do_not_pass_gate(tmp_path):
    s,es=setup(tmp_path,22); records=[record(e,i,known=e["available_at"]) for i,e in enumerate(es[:20])]
    assert save_adjudications(s,records,asof="2026-01-01T00:01:00Z")==20
    # Reliability has a strong history, but no origin review means monitor.
    assert response_policy(s,event_id="e20",company_id="ACME",category="company_performance",asof="2026-01-01T00:01:00Z")["action"]=="monitor_now"
    save_event_reviews(s,[review(es[20],origin="unverified")],asof="2026-01-01T00:01:00Z")
    assert response_policy(s,event_id="e20",company_id="ACME",category="company_performance",asof="2026-01-01T00:01:00Z")["action"]=="monitor_now"
    assert response_policy(s,event_id="e21",company_id="ACME",category="company_performance",asof="2026-01-01T00:01:00Z")["reliability"]["resolved_n"]==20

def test_reviews_require_independent_support_and_transaction_rolls_back(tmp_path):
    s,es=setup(tmp_path)
    support=ev("other","independent","wire2")
    s.import_batch({"events":[support],"nodes":[],"claims":[],"relationships":[],"analogs":[]})
    bad=review(es[0],origin="authenticated_publisher",support=["e0"])
    with pytest.raises(ContextError): save_event_reviews(s,[bad],asof=T)
    good=review(es[0],origin="authenticated_publisher",support=["other"])
    assert save_event_reviews(s,[good,good],asof=T)==1
    with pytest.raises(ContextError): save_event_reviews(s,[{**review(es[0],rid="r2"),"origin_status":"bad"}],asof=T)
    assert response_policy(s,event_id="e0",company_id="ACME",category="company_performance",asof=T)["action"]=="monitor_now"

def test_publisher_needs_corrob_and_history_and_uses_decision_time(tmp_path):
    s,es=setup(tmp_path,22)
    assert save_adjudications(s,[record(e,i,known=e["available_at"]) for i,e in enumerate(es[:20])],asof="2026-01-01T00:01:00Z")==20
    support=ev("independent","outside","wire2")
    s.import_batch({"events":[support],"nodes":[],"claims":[],"relationships":[],"analogs":[]})
    assert save_event_reviews(s,[review(es[20],origin="authenticated_publisher")],asof="2026-01-01T00:01:00Z")==1
    assert response_policy(s,event_id="e20",company_id="ACME",category="company_performance",asof="2026-01-01T00:00:20Z")["action"]=="monitor_now"
    good=review(es[20],rid="r2",origin="authenticated_publisher",support=["independent"],known="2026-01-01T00:00:21Z")
    save_event_reviews(s,[good],asof="2026-01-01T00:01:00Z")
    result=response_policy(s,event_id="e20",company_id="ACME",category="company_performance",asof="2026-01-01T00:00:21Z")
    assert result["action"]=="paper_evaluate_now" and result["decision_at"]=="2026-01-01T00:00:21.000000Z"
    assert result["reliability"]["resolved_n"]==20 and result["reliability"]["wilson_lower95"]==pytest.approx(.8388748,abs=1e-6)

def test_late_review_does_not_rewrite_receipt_score_and_canonical_repetitions_count_once(tmp_path):
    s,es=setup(tmp_path,2)
    # Duplicate event copy has the same source and canonical story, so it earns one credit.
    duplicate={**es[1],"event_id":"e-copy","canonical_id":es[0]["canonical_id"],"source_url":"https://news.test/e-copy","raw_hash":"b"*64}
    s.import_batch({"events":[duplicate],"nodes":[],"claims":[],"relationships":[],"analogs":[]})
    late="2026-01-01T00:00:10Z"
    save_adjudications(s,[record(es[0],1),record(duplicate,2,known=duplicate["available_at"])],asof=late)
    assert source_reliability(s,source_id="wire",company_id="ACME",category="company_performance",asof="2026-01-01T00:00:30Z")["resolved_n"]==1
    result=response_policy(s,event_id="e0",company_id="ACME",category="company_performance",asof=T)
    assert result["reliability"]["resolved_n"]==0 and result["decision_at"]==T.replace("Z",".000000Z")
    save_event_reviews(s,[review(es[0],known="2026-01-01T00:00:10Z")],asof="2026-01-01T00:00:10Z")
    assert response_policy(s,event_id="e0",company_id="ACME",category="company_performance",asof="2026-01-01T00:00:20Z")["action"]=="paper_evaluate_now"
