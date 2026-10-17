"""Build a deterministic shadow market-context snapshot from JSON evidence."""
import argparse
import json
from pathlib import Path

from stock_research.market_context import (build_candidate_review, build_investigation,
    build_snapshot, compare_sector_peers, review_rl_outcomes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON with asof, target, events, optional membership")
    parser.add_argument("--operation", choices=("snapshot", "peer-comparison", "investigation", "candidate-review", "rl-review"), default="snapshot")
    parser.add_argument("--output", help="write immutable snapshot JSON here")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if args.operation == "snapshot":
        result = build_snapshot(asof=payload["asof"], target=payload["target"], events=payload["events"], annotations=payload.get("annotations", []), membership=payload.get("membership", []))
    elif args.operation == "peer-comparison":
        result = compare_sector_peers(asof=payload["asof"], target=payload["target"], peer_set=payload["peer_set"], observations=payload["observations"])
    elif args.operation == "investigation":
        result = build_investigation(investigation_id=payload["investigation_id"], kind=payload["kind"], decision_at=payload["decision_at"], decision_snapshot=payload["decision_snapshot"], decision_evidence=payload.get("decision_evidence", []), discoveries=payload.get("discoveries", []))
    elif args.operation == "candidate-review":
        result = build_candidate_review(candidate_version=payload["candidate_version"], records=payload["records"], train_through=payload["train_through"], validation_through=payload["validation_through"], cost_bps=payload["cost_bps"])
    else:
        result = review_rl_outcomes(payload["decisions"], cost_bps=payload["cost_bps"])
    output = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        target = Path(args.output)
        rendered = output + "\n"
        if target.exists():
            if target.read_text(encoding="utf-8") != rendered:
                raise ValueError("snapshot output exists with different content")
        else:
            with target.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
