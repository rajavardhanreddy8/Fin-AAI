"""Read-only status for the local hourly market-news collector."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TASK_NAME = "fin-AAI local market news collector"


def task_metadata():
    if sys.platform != "win32":
        return {"available": False, "reason": "Windows Task Scheduler is unavailable on this platform."}
    script = (
        "$n='" + TASK_NAME + "'; $t=Get-ScheduledTask -TaskName $n -ErrorAction Stop; "
        "$i=Get-ScheduledTaskInfo -TaskName $n -ErrorAction Stop; "
        "[pscustomobject]@{state=[string]$t.State; last_run=$i.LastRunTime.ToString('o'); "
        "next_run=$i.NextRunTime.ToString('o'); last_task_result=$i.LastTaskResult} | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "reason": str(error)}
    if result.returncode:
        reason = result.stderr.strip() or "Task Scheduler query failed or access was denied."
        return {"available": False, "reason": reason}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"available": False, "reason": "Task Scheduler returned unreadable metadata."}
    return {"available": True, **data}


def inspect_status(report_path: Path, task: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    result = {"task_name": TASK_NAME, "task": task}
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        retrieved = datetime.fromisoformat(report["coverage"]["retrieved_at"].replace("Z", "+00:00"))
        if retrieved.tzinfo is None:
            raise ValueError("retrieved_at has no timezone")
        age = max(0, int((now - retrieved.astimezone(timezone.utc)).total_seconds()))
        coverage = report["coverage"]
        failures = coverage.get("integrity_failures")
        result["report"] = {
            "available": True,
            "path": str(report_path),
            "age_seconds": age,
            "status": report.get("status", "unknown"),
            "gaps": coverage.get("gaps", []),
            "integrity_failures": failures,
            "integrity_status": "unknown" if type(failures) is not int else "failed" if failures else "ok",
        }
    except FileNotFoundError:
        result["report"] = {"available": False, "path": str(report_path), "status": "missing"}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        result["report"] = {"available": False, "path": str(report_path), "status": "invalid", "reason": str(error)}
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    report_path = args.project_root / "output" / "market-news" / "market-ingest.json"
    print(json.dumps(inspect_status(report_path, task_metadata()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
