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


def command(args: list[str]) -> dict:
    try:
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=90)
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


def main() -> int:
    git_status = command(["git", "status", "--short"])
    git_head = command(["git", "rev-parse", "HEAD"])
    git_remote = command(["git", "ls-remote", "origin", "refs/heads/main"])
    tests_env = os.environ.copy()
    tests_env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + tests_env.get("PYTHONPATH", "")
    try:
        test_run = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=ROOT, capture_output=True, text=True, timeout=90, env=tests_env)
        tests = {"returncode": test_run.returncode, "stdout": test_run.stdout.strip(), "stderr": test_run.stderr.strip()}
    except Exception as exc:
        tests = {"returncode": None, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}
    task_query = command(["powershell", "-NoProfile", "-Command", "Get-ScheduledTask -TaskName 'fin-AAI API agents pre-market','fin-AAI API agents post-market' | Select-Object -ExpandProperty TaskName"])
    report_path, report = latest_report()
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "projectRoot": str(ROOT),
        "git": {
            "head": git_head["stdout"],
            "remoteMain": git_remote["stdout"],
            "workingTreeClean": not bool(git_status["stdout"]),
            "status": git_status["stdout"].splitlines(),
        },
        "tests": {"passed": tests["returncode"] == 0, "returncode": tests["returncode"], "output": tests["stdout"] or tests["stderr"]},
        "scheduler": {"registeredTasks": task_query["stdout"].splitlines(), "queryReturncode": task_query["returncode"]},
        "provider": provider_status(),
        "latestAgentReport": {"path": report_path, "report": report},
        "boundary": "Research and simulation only; no broker orders are placed.",
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if tests["returncode"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


