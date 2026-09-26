"""Specialist agents for the fin-AAI daily research workflow.

Agents return structured observations and may propose research work, but cannot
alter trading rules, advance the authenticated paper ledger, or route orders.
The :class:`FinanceOrchestrator` is the only component called by the scheduler.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from .evidence_acquisition import plan_acquisition
from .nifty_engine import refresh_announcements, refresh_prices, screen_universe
from .nifty_forecasts import make_forecasts, performance, score_forecasts
from .nifty_specialists import run_queue
from .nifty_store import IST
from .nifty_universe import previous_session


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AgentResult:
    """A durable, JSON-safe result with an explicit owning agent."""

    agent: str
    status: str
    output: dict[str, Any]
    errors: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status,
            "output": self.output,
            "errors": list(self.errors),
        }


class FinanceAgent(Protocol):
    name: str

    def run(self, context: "AgentContext") -> AgentResult:
        """Perform one bounded research responsibility."""


@dataclass(frozen=True)
class AgentContext:
    phase: str
    db: Path
    session_date: date
    calendar: dict[str, Any]
    members: list[dict[str, Any]]
    max_model_calls: int
    evaluate_trading: bool


class MarketEvidenceAgent:
    """Refreshes official prices and post-market disclosure metadata."""

    name = "market_evidence"

    def run(self, context: AgentContext) -> AgentResult:
        target = (previous_session(context.calendar, context.session_date)
                  if context.phase == "pre" else context.session_date)
        refresh_prices(context.db, context.members, target, sessions=1)
        output: dict[str, Any] = {"priceSession": target.isoformat(), "constituents": len(context.members)}
        errors: list[str] = []
        if context.phase == "post":
            try:
                output["newAnnouncements"] = refresh_announcements(
                    context.db, context.members, context.session_date - timedelta(days=7), context.session_date
                )
            except Exception as exc:  # Disclosure refresh should not erase a completed price refresh.
                errors.append(f"announcements: {type(exc).__name__}: {exc}"[:400])
        return AgentResult(self.name, "partial" if errors else "completed", output, tuple(errors))


class EvidenceScreeningAgent:
    """Freezes evidence and records coverage/trigger state for every constituent."""

    name = "evidence_screening"

    def run(self, context: AgentContext) -> AgentResult:
        expected = (previous_session(context.calendar, context.session_date)
                    if context.phase == "pre" else context.session_date)
        scan = screen_universe(
            context.db,
            mode="pre_market" if context.phase == "pre" else "post_market",
            model=os.getenv("RESEARCH_LLM_MODEL", os.getenv("GROQ_MODEL", "")).strip(),
            expected_price_date=expected,
        )
        errors = tuple(scan.get("errors", ()))
        status = "completed" if scan.get("status") == "completed" and not errors else "partial"
        return AgentResult(self.name, status, scan, errors)


class EvidenceAcquisitionAgent:
    """Creates a bounded, attributable filing and IR acquisition queue."""

    name = "evidence_acquisition"

    def __init__(self, screening: AgentResult) -> None:
        self.screening = screening

    def run(self, context: AgentContext) -> AgentResult:
        run_id = self.screening.output.get("run_id")
        if self.screening.status != "completed" or not run_id:
            return AgentResult(
                self.name,
                "abstained",
                {"reason": "Evidence screening did not finish cleanly; no acquisition queue created."},
            )
        try:
            return AgentResult(self.name, "completed", plan_acquisition(context.db, run_id))
        except (ValueError, OSError) as exc:
            return AgentResult(self.name, "failed", {}, (f"{type(exc).__name__}: {exc}"[:400],))


class ForecastMeasurementAgent:
    """Creates pre-open baseline forecasts or scores forecast outcomes after close."""

    name = "forecast_measurement"

    def __init__(self, screening: AgentResult) -> None:
        self.screening = screening

    def run(self, context: AgentContext) -> AgentResult:
        if context.phase == "pre":
            run_id = self.screening.output.get("run_id")
            if self.screening.status != "completed" or not run_id:
                return AgentResult(
                    self.name,
                    "abstained",
                    {"reason": "Evidence screening did not finish cleanly; no forecasts created."},
                )
            return AgentResult(self.name, "completed", make_forecasts(context.db, run_id, context.calendar))
        return AgentResult(
            self.name,
            "completed",
            {"scores": score_forecasts(context.db, context.calendar), "performance": performance(context.db)},
        )


class ResearchSpecialistAgent:
    """Consumes only verified frozen packets and runs a bounded model-work queue."""

    name = "research_specialists"

    def run(self, context: AgentContext) -> AgentResult:
        if not context.max_model_calls:
            return AgentResult(self.name, "disabled", {"calls": 0, "reason": "Model-call budget is zero."})
        queue = run_queue(context.db, max_calls=context.max_model_calls)
        status = "completed" if queue.get("status") == "processed" else queue.get("status", "partial")
        return AgentResult(self.name, status, queue)


class TradingEvaluationAgent:
    """Runs the existing read-only historical evaluator and exposes its promotion gate."""

    name = "trading_evaluation"

    def run(self, context: AgentContext) -> AgentResult:
        if context.phase != "post" or not context.evaluate_trading:
            return AgentResult(self.name, "not_applicable", {"reason": "Trading evaluation runs after market close only."})
        node = shutil.which("node")
        script = PROJECT_ROOT / "scripts" / "evaluate_finance_daily.mjs"
        if not node or not script.exists():
            return AgentResult(self.name, "failed", {}, ("Node.js or the daily trading evaluator is unavailable",))
        try:
            completed = subprocess.run(
                [node, str(script)], cwd=PROJECT_ROOT, capture_output=True, text=True,
                timeout=240, check=False,
            )
            if completed.returncode:
                raise RuntimeError((completed.stderr or completed.stdout).strip()[-500:])
            output = json.loads(completed.stdout)
            if not output.get("promotionGate"):
                raise ValueError("Trading evaluation omitted its promotion gate")
            return AgentResult(self.name, "completed", output)
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            return AgentResult(self.name, "failed", {}, (f"{type(exc).__name__}: {exc}"[:400],))


class FinanceOrchestrator:
    """Routes a phase through explicit agent roles and returns their audit trail."""

    name = "finance_orchestrator"

    def run(self, context: AgentContext) -> dict[str, Any]:
        results: list[AgentResult] = []
        market = MarketEvidenceAgent().run(context)
        results.append(market)
        screening = EvidenceScreeningAgent().run(context)
        results.append(screening)
        results.append(EvidenceAcquisitionAgent(screening).run(context))
        results.append(ForecastMeasurementAgent(screening).run(context))
        results.append(ResearchSpecialistAgent().run(context))
        if context.phase == "post":
            results.append(TradingEvaluationAgent().run(context))

        errors = [error for result in results for error in result.errors]
        return {
            "orchestrator": self.name,
            "agents": [result.as_dict() for result in results],
            "errors": errors,
            "status": "partial" if errors else "completed",
        }
