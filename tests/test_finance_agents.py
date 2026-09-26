from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from stock_research.finance_agents import AgentContext, AgentResult, FinanceOrchestrator


class FinanceAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = AgentContext(
            phase="post",
            db=Path("test.db"),
            session_date=date(2026, 9, 24),
            calendar={"year": 2026, "holidays": [], "special_sessions": {}},
            members=[{"isin": "INE000000001", "symbol": "TEST"}],
            max_model_calls=2,
            evaluate_trading=True,
        )

    def test_post_orchestrator_records_each_named_agent_and_surfaces_errors(self) -> None:
        class Market:
            name = "market_evidence"

            def run(self, context):
                return AgentResult(self.name, "completed", {"priceSession": "2026-09-24"})

        class Screening:
            name = "evidence_screening"

            def run(self, context):
                return AgentResult(self.name, "completed", {"run_id": "screen-1"})

        class Acquisition:
            name = "evidence_acquisition"

            def __init__(self, screening):
                self.screening = screening

            def run(self, context):
                return AgentResult(self.name, "completed", {"planned": 2})

        class Forecast:
            name = "forecast_measurement"

            def __init__(self, screening):
                self.screening = screening

            def run(self, context):
                return AgentResult(self.name, "completed", {"scores": {"scored": 1}})

        class Specialists:
            name = "research_specialists"

            def run(self, context):
                return AgentResult(self.name, "configuration_required", {"calls": 0})

        class Trading:
            name = "trading_evaluation"

            def run(self, context):
                return AgentResult(self.name, "failed", {}, ("historical source unavailable",))

        with patch("stock_research.finance_agents.MarketEvidenceAgent", Market), patch(
            "stock_research.finance_agents.EvidenceScreeningAgent", Screening
        ), patch("stock_research.finance_agents.EvidenceAcquisitionAgent", Acquisition), patch("stock_research.finance_agents.ForecastMeasurementAgent", Forecast), patch(
            "stock_research.finance_agents.ResearchSpecialistAgent", Specialists
        ), patch("stock_research.finance_agents.TradingEvaluationAgent", Trading):
            result = FinanceOrchestrator().run(self.context)

        self.assertEqual(result["orchestrator"], "finance_orchestrator")
        self.assertEqual(
            [agent["agent"] for agent in result["agents"]],
            ["market_evidence", "evidence_screening", "evidence_acquisition", "forecast_measurement", "research_specialists", "trading_evaluation"],
        )
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["errors"], ["historical source unavailable"])

    def test_pre_orchestrator_excludes_trading_agent(self) -> None:
        context = AgentContext(**{**self.context.__dict__, "phase": "pre", "evaluate_trading": False})
        completed = AgentResult("stub", "completed", {})
        with patch("stock_research.finance_agents.MarketEvidenceAgent.run", return_value=completed), patch(
            "stock_research.finance_agents.EvidenceScreeningAgent.run", return_value=completed
        ), patch("stock_research.finance_agents.EvidenceAcquisitionAgent.run", return_value=completed), patch("stock_research.finance_agents.ForecastMeasurementAgent.run", return_value=completed), patch(
            "stock_research.finance_agents.ResearchSpecialistAgent.run", return_value=completed
        ), patch("stock_research.finance_agents.TradingEvaluationAgent.run") as trading:
            result = FinanceOrchestrator().run(context)

        self.assertEqual(len(result["agents"]), 5)
        trading.assert_not_called()


if __name__ == "__main__":
    unittest.main()
