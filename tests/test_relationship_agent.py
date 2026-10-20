import pytest

from stock_research.context_store import ContextError
from stock_research.relationship_agent import validate_relationship_proposals


def test_relationship_gate_requires_citations_and_company_identity():
    batch = {"nodes": [{"node_type": "company", "node_id": "acme"}], "relationships": [
        {"subject_type": "event", "subject_id": "e1", "object_type": "company", "object_id": "acme",
         "relationship_type": "documented_exposure", "claim_ids": ["c1"]}]}
    assert validate_relationship_proposals(batch, {"acme"}) is batch
    with pytest.raises(ContextError, match="outside supplied identity"):
        validate_relationship_proposals(batch, {"other"})
    batch["relationships"][0]["claim_ids"] = []
    with pytest.raises(ContextError, match="cited claim_ids"):
        validate_relationship_proposals(batch, {"acme"})


def test_estimated_effect_requires_mechanism():
    batch = {"nodes": [], "relationships": [{"subject_type": "company", "subject_id": "acme",
        "object_type": "sector", "object_id": "s1", "relationship_type": "estimated_effect", "claim_ids": ["c1"]}]}
    with pytest.raises(ContextError, match="mechanism"):
        validate_relationship_proposals(batch, {"acme"})
