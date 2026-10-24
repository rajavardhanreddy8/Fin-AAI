"""Build an impact snapshot or train a review-only linear candidate from JSON.

Snapshot input: {report, scored_edges, asof, company_id, horizon_minutes}. Training input:
{samples, training}, where training contains train_cutoff, validation_cutoff,
horizon_minutes, parent_version, candidate_version, available_at and optional
learning_rate/epochs. Samples carry sample_id, event_id, decision_at,
outcome_completed_at, label_known_at, horizon_minutes, target_return_bps,
provenance (real or fixture), company_id and the full frozen snapshot object.
Manual input: {candidate: {version, parent_version, coefficients, feature_keys,
horizon_minutes, available_at}}. Coefficients may include __intercept__.
Predict input: {candidate, snapshot, at, horizon_minutes}; both objects must
come from their saved versions, and prediction remains review-only.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from stock_research.impact_graph import build_snapshot, train_candidate, manual_candidate, predict_candidate

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("snapshot", "train", "manual", "predict"))
    parser.add_argument("input", type=Path, help="JSON input; see --help and module docstring")
    parser.add_argument("output", type=Path, help="new JSON artifact path; existing files are refused")
    args=parser.parse_args()
    try:
        data=json.loads(args.input.read_text(encoding="utf-8"))
        if args.operation=="snapshot": result=build_snapshot(data["report"],data["scored_edges"],asof=data["asof"],company_id=data["company_id"],horizon_minutes=data["horizon_minutes"])
        elif args.operation=="train": result=train_candidate(data["samples"],**data["training"])
        elif args.operation=="manual": result=manual_candidate(**data["candidate"])
        else: result={"prediction_bps":predict_candidate(data["candidate"],data["snapshot"],at=data["at"],horizon_minutes=data["horizon_minutes"]),"status":"heuristic_candidate_output"}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        encoded=json.dumps(result,indent=2,allow_nan=False)
        with args.output.open("x",encoding="utf-8") as f: f.write(encoded+"\n")
    except (OSError,ValueError,KeyError,TypeError) as exc:
        parser.error(str(exc))
if __name__=="__main__": main()
