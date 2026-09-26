from __future__ import annotations

import json
import os
import urllib.request
from urllib.error import HTTPError
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .db import connect, transaction
from .phase2 import CompanyEvidenceProfile, assess_company_readiness


ALLOWED_ACTIONS = {"buy", "add", "hold", "reduce", "sell", "watch", "avoid"}
ALLOWED_CLASSIFICATIONS = {
    "core_investment",
    "high_risk_investment",
    "speculative_investment",
    "watchlist_only",
    "avoid",
}
POSITIVE_ACTIONS = {"buy", "add"}


@dataclass(frozen=True, slots=True)
class ResearchResult:
    status: str
    isin: str
    as_of: str
    report: str
    recommendation_id: int | None = None
    blockers: tuple[str, ...] = ()


class OpenAICompatibleLLM:
    """Minimal adapter for providers exposing the OpenAI chat-completions shape."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.last_headers: dict[str, str] = {}
        self.max_completion_tokens: int | None = None

    @classmethod
    def from_env(cls) -> "OpenAICompatibleLLM":
        values = {
            "base_url": os.getenv("RESEARCH_LLM_BASE_URL", "").strip(),
            "api_key": os.getenv("RESEARCH_LLM_API_KEY", "").strip(),
            "model": os.getenv("RESEARCH_LLM_MODEL", "").strip(),
        }
        missing = [f"RESEARCH_LLM_{name.upper()}" for name, value in values.items() if not value]
        if missing:
            raise ValueError(f"Missing server-only LLM setting(s): {', '.join(missing)}")
        return cls(**values)

    def __call__(self, system: str, user: str) -> dict[str, Any]:
        payload = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode()
        if self.max_completion_tokens is not None:
            body_payload = json.loads(payload)
            body_payload["max_completion_tokens"] = self.max_completion_tokens
            payload = json.dumps(body_payload).encode()
        request = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                self.last_headers = {k.lower(): v for k, v in response.headers.items()}
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            self.last_headers = {k.lower(): v for k, v in exc.headers.items()}
            raise
        return json.loads(body["choices"][0]["message"]["content"])


def build_evidence_packet(
    db_path: str | Path,
    fixture_dir: str | Path,
    as_of: date,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    profile = CompanyEvidenceProfile.load(fixture_dir)
    ready, blockers = assess_company_readiness(db_path, profile, as_of)
    with connect(db_path) as connection:
        security = dict(connection.execute("SELECT * FROM securities WHERE isin=?", (profile.isin,)).fetchone())
        price = connection.execute(
            "SELECT trade_date,close,volume,source_id,retrieved_at FROM price_bars WHERE isin=? AND trade_date<=? ORDER BY trade_date DESC LIMIT 1",
            (profile.isin, as_of.isoformat()),
        ).fetchone()
        facts = [
            dict(row)
            for row in connection.execute(
                """
                WITH ranked AS (
                    SELECT f.*, d.document_key, d.title AS document_title,
                           ROW_NUMBER() OVER (
                               PARTITION BY f.metric, f.period_type
                               ORDER BY f.period_end DESC,
                                        CASE f.statement_scope WHEN 'consolidated' THEN 0 WHEN 'bank' THEN 0 ELSE 1 END,
                                        f.fact_id DESC
                           ) AS rank
                    FROM financial_facts f JOIN documents d ON d.document_id=f.document_id
                    WHERE f.isin=? AND f.validation_status='accepted' AND d.validation_status='accepted'
                )
                SELECT metric,value,unit,currency,period_end,period_type,statement_scope,
                       evidence_label,document_id,document_key,document_title,source_location,
                       publication_date,retrieved_at
                FROM ranked WHERE rank=1 ORDER BY period_type,metric
                """,
                (profile.isin,),
            )
        ]
        documents = [
            dict(row)
            for row in connection.execute(
                """SELECT document_id,document_key,document_type,title,published_at,retrieved_at,
                          source_location,period_end,reporting_scope
                   FROM documents WHERE isin=? AND validation_status='accepted'
                   ORDER BY published_at DESC,document_id DESC LIMIT 20""",
                (profile.isin,),
            )
        ]
        flags = [
            dict(row)
            for row in connection.execute(
                """SELECT rule_id,severity,message,source_document_id,detected_at
                   FROM governance_flags WHERE isin=? AND status='open'
                   ORDER BY CASE severity WHEN 'blocking' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END""",
                (profile.isin,),
            )
        ]

    eps = next(
        (
            row for row in facts
            if row["metric"] == "eps_diluted" and row["currency"] == "INR" and row["unit"] == "per_share"
        ),
        None,
    )
    valuation = None
    if price and eps and eps["value"] and float(eps["value"]) > 0:
        valuation = {
            "metric": "price_to_earnings",
            "value": round(float(price["close"]) / float(eps["value"]), 2),
            "price_date": price["trade_date"],
            "eps_period_end": eps["period_end"],
            "eps_document_id": eps["document_id"],
            "method": "latest EOD close / latest accepted diluted INR EPS",
        }
    packet = {
        "as_of": as_of.isoformat(),
        "research_ready": ready,
        "blockers": list(blockers),
        "security": security,
        "latest_eod_price": dict(price) if price else None,
        "latest_metrics": facts,
        "valuation": valuation,
        "governance_flags": flags,
        "documents": documents,
        "evidence_index": [
            {
                "evidence_key": f"metric:{row['period_type']}:{row['metric']}",
                "document_id": row["document_id"],
                "source_location": row["source_location"],
            }
            for row in facts
        ] + [
            {
                "evidence_key": f"governance:{row['rule_id']}",
                "document_id": row["source_document_id"],
                "source_location": next(
                    (
                        document["source_location"]
                        for document in documents
                        if document["document_id"] == row["source_document_id"]
                    ),
                    None,
                ),
            }
            for row in flags
            if row["source_document_id"] is not None
        ],
        "data_timestamps": {
            "price_trade_date": price["trade_date"] if price else None,
            "price_retrieved_at": price["retrieved_at"] if price else None,
            "packet_created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        },
    }
    return packet, blockers


SYSTEM_PROMPT = """You are an Indian public-equity research analyst. Use only the supplied evidence packet.
Return one JSON object with: action, classification, confidence, opinion, thesis, risks,
assumptions, exit_triggers, and evidence_claims. evidence_claims is a list of objects with
evidence_key, document_id and claim. Use only pairs listed in evidence_index. Never invent
facts, live prices, target prices, entry zones, or source citations.
Allowed actions: buy, add, hold, reduce, sell, watch, avoid. If evidence is inadequate,
choose watch or avoid and explain the gap. A positive action requires valuation evidence,
no blocking governance flag, and research_ready=true. This is research, not trade execution."""


def _validate_response(response: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    required = {"action", "classification", "confidence", "opinion", "thesis", "risks", "assumptions", "exit_triggers", "evidence_claims"}
    missing = sorted(required - response.keys())
    if missing:
        raise ValueError(f"LLM response is missing: {', '.join(missing)}")
    if {"target_price", "price_target", "entry_zone"} & response.keys():
        raise ValueError("LLM response must not contain invented price targets or entry zones")
    action = str(response["action"]).lower()
    classification = str(response["classification"]).lower()
    if action not in ALLOWED_ACTIONS or classification not in ALLOWED_CLASSIFICATIONS:
        raise ValueError("LLM response contains an unsupported action or classification")
    confidence = float(response["confidence"])
    if not 0 <= confidence <= 1:
        raise ValueError("LLM confidence must be between 0 and 1")
    for field in ("risks", "assumptions", "exit_triggers", "evidence_claims"):
        if not isinstance(response[field], list):
            raise ValueError(f"LLM field {field} must be a list")
    for field in ("opinion", "thesis"):
        if not isinstance(response[field], str) or not response[field].strip():
            raise ValueError(f"LLM field {field} must be non-empty text")
    for field in ("risks", "assumptions", "exit_triggers"):
        if any(not isinstance(item, str) or not item.strip() for item in response[field]):
            raise ValueError(f"LLM field {field} must contain only non-empty text")
    if not response["exit_triggers"]:
        raise ValueError("LLM response must include at least one exit or review trigger")
    valid_evidence = {
        (row["evidence_key"], row["document_id"])
        for row in packet["evidence_index"]
    }
    if not response["evidence_claims"] or any(
        not isinstance(item, dict)
        or (item.get("evidence_key"), item.get("document_id")) not in valid_evidence
        or not str(item.get("claim", "")).strip()
        for item in response["evidence_claims"]
    ):
        raise ValueError("Every evidence claim must cite a supplied evidence key and document ID")
    blocking_flags = [flag for flag in packet["governance_flags"] if flag["severity"] == "blocking"]
    if action in POSITIVE_ACTIONS and (
        not packet["research_ready"] or packet["valuation"] is None or blocking_flags
    ):
        raise ValueError("Positive recommendation failed deterministic evidence gates")
    response = dict(response)
    response["action"] = action
    response["classification"] = classification
    response["confidence"] = confidence
    return response


def _insufficient_report(packet: dict[str, Any], blockers: tuple[str, ...]) -> str:
    items = "\n".join(f"- {item}" for item in blockers)
    return f"""# Research result — {packet['security']['company_name']}

**Status:** Insufficient evidence  
**As of:** {packet['as_of']}  
**Latest EOD price date:** {packet['data_timestamps']['price_trade_date'] or 'missing'}

No LLM recommendation was requested because deterministic readiness checks failed.

## Blocking evidence gaps

{items}
"""


def _render_report(packet: dict[str, Any], recommendation: dict[str, Any]) -> str:
    evidence = {
        (row["evidence_key"], row["document_id"]): row
        for row in packet["evidence_index"]
    }
    claims = "\n".join(
        f"- {item['claim']} [[{item['document_id']}]]({evidence[(item['evidence_key'], item['document_id'])]['source_location']})"
        for item in recommendation["evidence_claims"]
    )
    risks = "\n".join(f"- {item}" for item in recommendation["risks"])
    assumptions = "\n".join(f"- {item}" for item in recommendation["assumptions"])
    exits = "\n".join(f"- {item}" for item in recommendation["exit_triggers"])
    price = packet["latest_eod_price"]
    valuation = packet["valuation"]
    valuation_line = (
        f"P/E {valuation['value']:.2f}x using diluted EPS through {valuation['eps_period_end']}"
        if valuation else "Unavailable; positive actions are prohibited"
    )
    return f"""# Evidence-backed research — {packet['security']['company_name']}

**Action:** {recommendation['action'].upper()}  
**Classification:** {recommendation['classification']}  
**Confidence:** {recommendation['confidence']:.0%}  
**Evidence as of:** {packet['as_of']}  
**Latest EOD close:** INR {price['close']} on {price['trade_date']} (retrieved {price['retrieved_at']})  
**Deterministic valuation:** {valuation_line}

## Opinion

{recommendation['opinion']}

## Thesis

{recommendation['thesis']}

## Evidence

{claims}

## Risks

{risks}

## Assumptions

{assumptions}

## Exit or review triggers

{exits}

This report is research only. It does not place or authorize a trade.
"""


def run_research_agent(
    db_path: str | Path,
    fixture_dir: str | Path,
    as_of: date,
    llm: Callable[[str, str], dict[str, Any]],
) -> ResearchResult:
    packet, blockers = build_evidence_packet(db_path, fixture_dir, as_of)
    isin = packet["security"]["isin"]
    if blockers:
        return ResearchResult("insufficient_evidence", isin, as_of.isoformat(), _insufficient_report(packet, blockers), blockers=blockers)

    response = _validate_response(llm(SYSTEM_PROMPT, json.dumps(packet, separators=(",", ":"))), packet)
    report = _render_report(packet, response)
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with transaction(db_path) as connection:
        cursor = connection.execute(
            """INSERT INTO recommendations(isin,created_at,classification,action,score,confidence,
                   facts_json,assumptions_json,risks_json,opinion,entry_zone_json,
                   exit_triggers_json,thesis,policy_version,status)
               VALUES(?,?,?,?,?,?,?,?,?,?,NULL,?,?,?,'active')""",
            (
                isin, created_at, response["classification"], response["action"], None,
                response["confidence"], json.dumps({"metrics": packet["latest_metrics"], "valuation": packet["valuation"]}),
                json.dumps(response["assumptions"]), json.dumps(response["risks"]), response["opinion"],
                json.dumps(response["exit_triggers"]), response["thesis"], "1.0.0",
            ),
        )
        recommendation_id = cursor.lastrowid
        for item in response["evidence_claims"]:
            connection.execute(
                "INSERT INTO recommendation_evidence(recommendation_id,document_id,claim) VALUES(?,?,?)",
                (recommendation_id, item["document_id"], item["claim"]),
            )
    return ResearchResult("completed", isin, as_of.isoformat(), report, recommendation_id)
