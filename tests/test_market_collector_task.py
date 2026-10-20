import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_status_module():
    path = ROOT / "scripts" / "status_market_collector_task.py"
    spec = importlib.util.spec_from_file_location("status_market_collector_task", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registration_action_is_fixed_to_local_permitted_collector():
    script = (ROOT / "scripts" / "register_market_collector_task.ps1").read_text(encoding="utf-8")
    for expected in (
        '"fin-AAI local market news collector"',
        '"scripts\\run_market_ingest.py --feed-registry config\\market-news-sources.json --output output\\market-news --refresh"',
        'Get-Command python -ErrorAction Stop',
        '& $python --version',
        "-WorkingDirectory $ProjectRoot",
        "-RepetitionInterval ([TimeSpan]::FromSeconds($intervalSeconds))",
        "New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew",
        "Register-ScheduledTask",
    ):
        assert expected in script
    for forbidden in ("run_market_agents.py", "bedrock", "ContextStore", "broker", "--firecrawl-live"):
        assert forbidden.lower() not in script.lower()


def test_status_reports_age_gaps_integrity_and_task_metadata(tmp_path):
    module = load_status_module()
    report = tmp_path / "market-ingest.json"
    report.write_text(json.dumps({
        "status": "partial",
        "coverage": {
            "retrieved_at": "2026-10-20T10:00:00+00:00",
            "gaps": [{"unit": "pib_press_releases", "reason": "timeout"}],
            "integrity_failures": 1,
        },
    }), encoding="utf-8")
    task = {"available": True, "state": "Ready", "last_task_result": 0}
    status = module.inspect_status(report, task, datetime(2026, 10, 20, 10, 5, tzinfo=timezone.utc))
    assert status["task"] == task
    assert status["report"]["age_seconds"] == 300
    assert status["report"]["status"] == "partial"
    assert status["report"]["gaps"][0]["unit"] == "pib_press_releases"
    assert status["report"]["integrity_status"] == "failed"


def test_status_handles_missing_report_and_access_denied_metadata(tmp_path):
    module = load_status_module()
    status = module.inspect_status(tmp_path / "missing.json", {"available": False, "reason": "Access denied"})
    assert status["task"]["available"] is False
    assert status["report"]["status"] == "missing"
