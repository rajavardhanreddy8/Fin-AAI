"""Interpret one reviewed source using budgeted Nova and save a cited company graph."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from stock_research.company_impact import build_impact_batch, save_edge_scores
from stock_research.context_store import ContextStore
from stock_research.document_parser_agents import build_nova_relationship_interpreter
from stock_research.impact_graph import build_snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="reviewed JSON with document and title")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new version artifact; existing paths refused")
    parser.add_argument("--budget-config", type=Path, required=True)
    parser.add_argument("--usage-db", type=Path, required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--company-id", default="powergrid")
    parser.add_argument("--profile", default="fin-aai")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("output exists; select a new version artifact")
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        document = payload["document"]
        if not payload.get("reviewed_directions"):
            raise ValueError("reviewed source-specific driver/recipient directions are required")
        interpreter = build_nova_relationship_interpreter(str(args.budget_config), str(args.usage_db), args.namespace, profile=args.profile)
        result = interpreter.interpret_with_audit(document)
        if result["status"] != "completed":
            audit = result.get("audit") or {}
            print(json.dumps({"status": result["status"], "gap": audit.get("failure", "Document or current budget evidence failed admission"), "audit_call_id": audit.get("call_id")}), file=sys.stderr)
            return 2
        evidence = build_impact_batch(document, result, title=payload["title"], reviewed_directions=payload["reviewed_directions"])
        store = ContextStore(args.db)
        added = store.import_batch(evidence["batch"])
        asof = datetime.now(timezone.utc).isoformat()
        report = store.report(asof)
        snapshots = {str(h): build_snapshot(report, evidence["scored_edges"], asof=asof, company_id=args.company_id, horizon_minutes=h) for h in (5, 30, 60)}
        scores_added = save_edge_scores(store, evidence["scored_edges"], asof=asof, company_id=args.company_id)
        artifact = {**evidence, "added": added, "scores_added": scores_added, "report": report, "snapshots": snapshots}
        encoded = json.dumps(artifact, sort_keys=True, indent=2, allow_nan=False)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(encoded + "\n")
        print(json.dumps({"status": "research_only", "path": str(args.output), "added": added,
            "scores_added": scores_added, "model_request_id": result["audit"]["request_id"], "training_ready": False}))
        return 0
    except (OSError, KeyError, TypeError, ValueError) as error:
        print(f"Company impact failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
