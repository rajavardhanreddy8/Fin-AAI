"""Parse cited company event proposals from JSON and optionally store them."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from stock_research.context_store import ContextStore
from stock_research.parsing_storage_agent import parse_and_store, parse_documents
from stock_research.document_parser_agents import build_nova_document_interpreter


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--db", type=Path, help="append validated batch to a ContextStore")
    parser.add_argument("--nova-budget-config", type=Path)
    parser.add_argument("--usage-db", type=Path)
    parser.add_argument("--namespace")
    parser.add_argument("--profile", help="optional AWS profile for Nova")
    args = parser.parse_args(argv)
    nova_options = (args.nova_budget_config, args.usage_db, args.namespace)
    if any(nova_options) and not all(nova_options):
        parser.error("--nova-budget-config, --usage-db, and --namespace are required together")
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        docs = payload["documents"]
        interpret = (build_nova_document_interpreter(str(args.nova_budget_config), str(args.usage_db),
                    args.namespace, profile=args.profile) if all(nova_options) else
                    lambda document: next(row.get("proposals", []) for row in docs
                                          if row["source_id"] == document["source_id"]))
        inputs = {key: payload[key] for key in ("company", "symbol", "aliases", "start", "end", "documents")}
        result = parse_and_store(ContextStore(args.db), interpret=interpret, **inputs) if args.db else parse_documents(interpret=interpret, **inputs)
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
        return 0
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"Parsing/storage failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
