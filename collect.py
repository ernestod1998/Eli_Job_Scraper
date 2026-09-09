"""Sequential, bounded collection; source reports distinguish failure from zero jobs."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
SOURCES = ("linkedin", "indeed", "boards", "registry", "usajobs", "governmentjobs", "calopps", "calcareers")


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def run_source(source, root=ROOT, timeout=600, command=None):
    paths = [root / "all_jobs.json"] + [root / f"{source}_jobs.{ext}" for ext in ("json", "md", "html")]
    # The registry maintains private collection state as well as public outputs.
    paths += [root / "ats_registry.json", root / "ats_registry_state.json"] if source == "registry" else []
    before = {path: path.read_bytes() if path.exists() else None for path in paths}
    with tempfile.TemporaryDirectory(prefix="eli-source-") as directory:
        report = Path(directory) / "report.json"
        environment = dict(os.environ, ELI_SOURCE_REPORT_PATH=str(report))
        for name in ("PUSHOVER_TOKEN", "PUSHOVER_USER"):
            environment.pop(name, None)
        process = subprocess.Popen(command or [sys.executable, "-u", str(root / "scrape_jobs.py"), f"--{source}-only"], cwd=root, env=environment, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
            outcome = read_json(report, {})
            if code or outcome.get("status") not in ("success", "partial", "failure"):
                outcome = {"status": "failure", "error": f"Process exited {code}; valid source report required"}
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            outcome = {"status": "failure", "error": f"Source exceeded {timeout}s limit"}
        except (ValueError, OSError):
            outcome = {"status": "failure", "error": "Invalid source report"}
    if outcome["status"] != "failure":
        try:
            for path in (root / "all_jobs.json", root / f"{source}_jobs.json"):
                payload = read_json(path, None)
                if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
                    raise ValueError("Missing jobs array")
        except (ValueError, OSError):
            outcome = {"status": "failure", "error": "Source did not write valid job data"}
    if outcome["status"] == "failure":
        for path, contents in before.items():
            if contents is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(contents)
    elif outcome["status"] == "partial":
        # Fresh observations win; retained rows keep their original dates.
        path = root / f"{source}_jobs.json"
        previous = json.loads(before[path] or b'{"jobs": []}')
        current = read_json(path, {"jobs": []})
        combined = {job.get("url") or str(job): job for job in previous.get("jobs", [])}
        combined.update({job.get("url") or str(job): job for job in current.get("jobs", [])})
        current["jobs"] = list(combined.values())
        current["total"] = len(current["jobs"])
        write_json(path, current)
    return outcome


def collect(sources=SOURCES, root=ROOT, timeout=600):
    path = root / "source_status.json"
    status = read_json(path, {"sources": {}})
    for source in sources:
        attempted = stamp()
        old = status["sources"].get(source, {})
        try:
            outcome = run_source(source, root, timeout)
        except Exception as error:
            outcome = {"status": "failure", "error": f"Collector error: {type(error).__name__}"}
        status["sources"][source] = {
            "status": outcome["status"], "last_attempt": attempted,
            "last_success": stamp() if outcome["status"] == "success" else old.get("last_success"),
            "observations": outcome.get("observations", 0),
            "error": outcome.get("error", ""),
        }
        status["updated_at"] = stamp()
        write_json(path, status)
        print(f"{source}: {outcome['status']}", flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as stream:
            stream.write("## Collection status\n\n")
            for name, item in status["sources"].items():
                stream.write(f"- {name}: {item['status']} ({item.get('observations', 0)} observations)\n")
    return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", nargs="+", choices=SOURCES, default=list(SOURCES))
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    collect(args.sources, timeout=args.timeout)
