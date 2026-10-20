"""Deterministic gate for cited market relationship proposals."""
from __future__ import annotations

from .context_store import ContextError, ContextStore


def validate_relationship_proposals(batch: dict, company_ids: set[str]) -> dict:
    """Return a cited batch only when company endpoints match supplied identity.

    Claims, endpoints and dates are validated by ContextStore's existing
    deterministic import contract; this gate adds the external identity check.
    """
    if not isinstance(batch, dict) or not isinstance(company_ids, set) or not company_ids:
        raise ContextError("batch and nonempty company_ids set are required")
    companies = {row.get("node_id") for row in batch.get("nodes", [])
                 if isinstance(row, dict) and row.get("node_type") == "company"}
    if companies - company_ids:
        raise ContextError("company node is outside supplied identity")
    for rel in batch.get("relationships", []):
        if not isinstance(rel, dict):
            raise ContextError("relationships must be objects")
        for side in ("subject", "object"):
            if rel.get(f"{side}_type") == "company" and rel.get(f"{side}_id") not in company_ids:
                raise ContextError("relationship company endpoint is outside supplied identity")
        if not rel.get("claim_ids"):
            raise ContextError("relationship proposals require cited claim_ids")
        if rel.get("relationship_type") == "estimated_effect" and "mechanism" not in rel:
            raise ContextError("estimated effects require a mechanism")
    return batch


def import_relationship_proposals(store: ContextStore, batch: dict, company_ids: set[str]) -> dict:
    """Validate identity and delegate all schema/storage checks to ContextStore."""
    return store.import_batch(validate_relationship_proposals(batch, company_ids))
