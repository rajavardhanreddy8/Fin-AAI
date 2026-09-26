"""Produce a visible, secret-safe readiness report for the fin-AAI workspace."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"


def command(args: list[str], *, cwd: Path = ROOT, timeout: int = 90, env: dict | None = None) -> dict:
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
        return {"returncode": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except Exception as exc:
        return {"returncode": None, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}


def provider_status() -> dict[str, str]:
    names = (
        "RESEARCH_LLM_BASE_URL", "RESEARCH_LLM_API_KEY", "RESEARCH_LLM_MODEL",
        "RESEARCH_LLM_RPM", "RESEARCH_LLM_RPD", "RESEARCH_LLM_TPM", "RESEARCH_LLM_TPD",
        "GROQ_FREE_TIER_CONFIRMED", "GROQ_API_KEY", "GROQ_MODEL", "GROQ_RPM", "GROQ_RPD", "GROQ_TPM", "GROQ_TPD",
        "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
    )
    return {name: ("set" if os.getenv(name, "").strip() else "missing") for name in names}


def latest_report() -> tuple[str | None, dict | None]:
    reports = sorted(OUTPUT.glob("finance-automation-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in reports:
        try:
            return str(path.relative_to(ROOT)), json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return None, None


def test_record(result: dict) -> dict:
    text = result["stdout"] or result["stderr"]
    return {"passed": result["returncode"] == 0, "returncode": result["returncode"], "output_tail": text[-1200:]}


def main() -> int:
    full = "--full" in sys.argv[1:]
    git_status = command(["git", "status", "--short"])
    git_head = command(["git", "rev-parse", "HEAD"])
    git_remote = command(["git", "ls-remote", "origin", "refs/heads/main"])
    tests_env = os.environ.copy()
    tests_env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + tests_env.get("PYTHONPATH", "")
    tests = command([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], env=tests_env, timeout=120)
    task_query = command(["powershell", "-NoProfile", "-Command", "Get-ScheduledTask -TaskName 'fin-AAI API agents pre-market','fin-AAI API agents post-market' | Select-Object -ExpandProperty TaskName"])
    report_path, report = latest_report()
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "projectRoot": str(ROOT),
        "git": {"head": git_head["stdout"], "remoteMain": git_remote["stdout"], "workingTreeClean": not bool(git_status["stdout"]), "status": git_status["stdout"].splitlines()},
        "tests": test_record(tests),
        "scheduler": {"registeredTasks": task_query["stdout"].splitlines(), "queryReturncode": task_query["returncode"]},
        "provider": provider_status(),
        "latestAgentReport": {"path": report_path, "report": report},
        "boundary": "Research and simulation only; no broker orders are placed.",
    }
    if full:
        node_tests = [
            ["node", "workstream/investing/tests/finance-investing.test.mjs"],
            ["node", "workstream/investing/tests/finance-research.test.mjs"],
            ["node", "workstream/trading/finance-paper.test.mjs"],
            ["node", "workstream/trading/finance-paper-v2.test.mjs"],
        ]
        payload["workstreamTests"] = {str(args[-1]): test_record(command(args, timeout=60)) for args in node_tests}
        site = ROOT / "momentum-site"
        site_result = command(["npm.cmd", "test"], cwd=site, timeout=180)
        payload["siteTests"] = test_record(site_result)
        walkforward = command(["node", "scripts/evaluate_finance_walkforward.mjs"], timeout=180)`r`n        payload["walkForward"] = test_record(walkforward)`r`n    required = [payload["tests"]["passed"], payload["scheduler"]["queryReturncode"] == 0]
    if full:
        required += [all(item["passed"] for item in payload["workstreamTests"].values()), payload["siteTests"]["passed"], payload["walkForward"]["passed"]]
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if all(required) else 1


if __name__ == "__main__":
    raise SystemExit(main())

