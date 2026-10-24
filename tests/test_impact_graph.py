import json
import hashlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from stock_research.impact_graph import build_snapshot, train_candidate, predict_candidate, manual_candidate

ASOF="2026-01-01T00:00:00Z"
def report():
    return {"asof":ASOF,"what_trust":{"events":[{"event_id":"e","available_at":ASOF}],"claims":[{"claim_id":"c","event_id":"e","known_at":ASOF}]},"who_how":{"relationships":[{"relationship_id":"r","known_at":ASOF,"claim_ids":["c"],"subject_type":"sector","subject_id":"s","object_type":"company","object_id":"X","relationship_type":"documented_exposure"},{"relationship_id":"reverse","known_at":ASOF,"claim_ids":["c"],"subject_type":"company","subject_id":"X","object_type":"sector","object_id":"s","relationship_type":"documented_exposure"}]}}
def score(rid,horizon=30): return {"relationship_id":rid,"score_known_at":ASOF,"score_version":"v1","score_mode":"manual","manual_version":"manual-v1","sentiment":-1,"impact_weight":.5,"confidence":.8,"category":"sector_conditions","horizon_minutes":horizon}

def test_snapshot_preserves_direction_horizon_and_deduplicates_event_feature():
    scores=[score("r"),dict(score("reverse"),impact_weight=-.5),score("r",60)]
    out=build_snapshot(report(),scores,asof=ASOF,company_id="X",horizon_minutes=30)
    assert out==build_snapshot(report(),list(reversed(scores)),asof=ASOF,company_id="X",horizon_minutes=30)
    assert len(out["edges"])==3
    assert out["edges"][1]["subject_id"]=="s" or out["edges"][0]["subject_id"]=="s"
    assert out["features"]=={"sector_conditions|documented_exposure|sector":-.4}
    assert out["features_known_at"]==ASOF and out["score_versions"]==["v1"]
    assert {"relationship_id":"r","horizon_minutes":30} in out["adjacency"]["sector/s"]["outgoing"]
    assert {"relationship_id":"r","horizon_minutes":30} in out["adjacency"]["company/X"]["incoming"]
    assert {"relationship_id":"reverse","horizon_minutes":30} in out["adjacency"]["company/X"]["outgoing"]
    assert next(edge for edge in out["edges"] if edge["relationship_id"]=="reverse")["impact_weight"]==-0.5

def test_manual_candidate_update_changes_prediction_without_mutating_parent():
    snapshot=build_snapshot(report(),[score("r")],asof=ASOF,company_id="X",horizon_minutes=30)
    key=next(iter(snapshot["features"]))
    parent=manual_candidate(version="v1",parent_version="base",coefficients={key:1,"__intercept__":0},feature_keys=[key],horizon_minutes=30,available_at=ASOF,company_id="X")
    candidate=manual_candidate(version="v2",parent_version=parent["candidate_version"],coefficients={key:3,"__intercept__":0},feature_keys=[key],horizon_minutes=30,available_at=ASOF,company_id="X")
    old_weights=parent["weights"].copy()
    assert predict_candidate(candidate,snapshot,at=ASOF,horizon_minutes=30)!=predict_candidate(parent,snapshot,at=ASOF,horizon_minutes=30)
    assert parent["weights"]==old_weights

def test_bad_score_claim_and_score_bounds_raise_valueerror():
    with pytest.raises(ValueError): build_snapshot(report(),[dict(score("r"),sentiment=2)],asof=ASOF,company_id="X",horizon_minutes=30)
    with pytest.raises(ValueError): build_snapshot(report(),[dict(score("r"),relationship_id="r2")],asof=ASOF,company_id="X",horizon_minutes=30)
    with pytest.raises(ValueError): build_snapshot(report(),[None],asof=ASOF,company_id="X",horizon_minutes=30)

def samples():
    start=datetime(2026,1,1,tzinfo=timezone.utc); rows=[]
    for i in range(27):
        d=start+timedelta(days=i); outcome=d+timedelta(minutes=30); label=outcome
        frozen={"asof":(d-timedelta(minutes=1)).isoformat(),"company_id":"X","horizon_minutes":30,"features":{"sector|exposure":1.0},"feature_hash":hashlib.sha256(b'["sector|exposure"]').hexdigest(),"features_known_at":(d-timedelta(minutes=1)).isoformat(),"score_versions":["v1"]}
        frozen["snapshot_hash"]=hashlib.sha256(json.dumps(frozen,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
        rows.append({"sample_id":f"sample-{i}","event_id":f"event-{i}","decision_at":d.isoformat(),"outcome_completed_at":outcome.isoformat(),"label_known_at":label.isoformat(),"horizon_minutes":30,"company_id":"X","target_return_bps":10+2*(i%3),"snapshot":frozen,"provenance":"fixture"})
    return rows
def train(rows):
    return train_candidate(rows,train_cutoff="2026-01-22T00:00:00Z",validation_cutoff="2026-02-01T00:00:00Z",horizon_minutes=30,parent_version="v1",candidate_version="v2",available_at="2026-02-01T00:00:00Z",learning_rate=.01,epochs=100)

def test_training_fits_coefficients_without_reading_future_holdout():
    rows=samples(); a=train(rows)
    rows.append({**samples()[-1],"sample_id":"future","event_id":"future","decision_at":"2027-01-01T00:00:00Z","outcome_completed_at":"2027-01-01T00:30:00Z","label_known_at":"2027-01-01T00:30:00Z","target_return_bps":999999,"provenance":"real"})
    b=train(rows)
    assert a["weights"]==b["weights"] and a["validation_mse"]<a["zero_baseline_validation_mse"]
    assert a["auto_promote"] is False and a["status"]=="candidate_review_only"
    assert a["training_data_status"]=="fixture_only" and a["training_provenance_counts"]["fixture"]==26
    with pytest.raises(ValueError): predict_candidate(a,rows[0]["snapshot"],at="2026-01-15T00:00:00Z",horizon_minutes=30)

def test_training_purges_same_event_across_split_and_binds_snapshot():
    rows=samples(); rows[-1]["event_id"]=rows[0]["event_id"]
    result=train(rows)
    assert result["purged_shared_event_count"]==1
    rows=samples(); rows[0]["snapshot"]["features"]["sector|exposure"]=100
    with pytest.raises(ValueError,match="snapshot hash") : train(rows)

def test_training_rejects_future_snapshot_even_with_recomputed_hash():
    rows=samples(); snap=rows[0]["snapshot"]; snap["asof"]="2026-01-02T00:00:00Z"
    snap["snapshot_hash"]=hashlib.sha256(json.dumps({k:v for k,v in snap.items() if k!="snapshot_hash"},sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    with pytest.raises(ValueError,match="future information"): train(rows)

def test_prediction_checks_snapshot_horizon_schema_and_weights():
    snapshot=build_snapshot(report(),[score("r")],asof=ASOF,company_id="X",horizon_minutes=30)
    candidate={"candidate_version":"v2","parent_version":"v1","status":"candidate_review_only","available_at":ASOF,"horizon_minutes":30,"feature_keys":list(snapshot["features"]),"weights":{**{k:1.0 for k in snapshot["features"]},"__intercept__":0.0}}
    assert isinstance(predict_candidate(candidate,snapshot,at=ASOF,horizon_minutes=30),float)
    with pytest.raises(ValueError): predict_candidate(candidate,snapshot,at=ASOF,horizon_minutes=60)
    candidate["weights"]["__intercept__"]=float("nan")
    with pytest.raises(ValueError): predict_candidate(candidate,snapshot,at=ASOF,horizon_minutes=30)

def test_prediction_rejects_future_snapshot_asof():
    snapshot=build_snapshot(report(),[score("r")],asof=ASOF,company_id="X",horizon_minutes=30)
    snapshot["asof"]="2026-01-02T00:00:00Z"
    snapshot["snapshot_hash"]=hashlib.sha256(json.dumps({k:v for k,v in snapshot.items() if k!="snapshot_hash"},sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    candidate={"candidate_version":"v2","parent_version":"v1","status":"candidate_review_only","available_at":ASOF,"horizon_minutes":30,"feature_keys":list(snapshot["features"]),"weights":{**{k:1.0 for k in snapshot["features"]},"__intercept__":0.0}}
    with pytest.raises(ValueError,match="unavailable"): predict_candidate(candidate,snapshot,at=ASOF,horizon_minutes=30)

@pytest.mark.parametrize("mutate",[lambda r:r[0]["snapshot"].update(features={"event-0":float("nan")}),lambda r:r[0].update(label_known_at="2025-12-01T00:00:00Z"),lambda r:r[1].update(sample_id=r[0]["sample_id"]),lambda r:r[0]["snapshot"].update(features={"sector|exposure":True})])
def test_invalid_sample_rejected(mutate):
    rows=samples(); mutate(rows)
    with pytest.raises(ValueError): train(rows)

def test_invalid_learning_rate_and_cutoffs_rejected():
    args=dict(train_cutoff="2026-01-21T00:00:00Z",validation_cutoff="2026-02-01T00:00:00Z",horizon_minutes=30,parent_version="v1",candidate_version="v2",available_at="2026-02-01T00:00:00Z")
    with pytest.raises(ValueError): train_candidate(samples(),**args,learning_rate=float("nan"))
    with pytest.raises(ValueError): train_candidate(samples(),**{**args,"validation_cutoff":args["train_cutoff"]})

def test_cli_refuses_overwrite(tmp_path):
    script=__import__("pathlib").Path(__file__).resolve().parents[1]/"scripts"/"run_impact_graph.py"
    source=tmp_path/"in.json"; output=tmp_path/"out.json"; source.write_text(json.dumps({"report":report(),"scored_edges":[score("r")],"asof":ASOF,"company_id":"X","horizon_minutes":30}))
    command=[sys.executable,str(script),"snapshot",str(source),str(output)]
    assert subprocess.run(command,capture_output=True).returncode==0
    assert subprocess.run(command,capture_output=True).returncode!=0
