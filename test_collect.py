import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from collect import run_source, collect
from build_site import build, PUBLIC_FILES


class CollectionTests(unittest.TestCase):
    def run_case(self, status, code=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = {"jobs": [{"url": "old", "date_posted": "2026-09-01"}]}
            (root / "all_jobs.json").write_text(json.dumps(old))
            (root / "linkedin_jobs.json").write_text(json.dumps(old))
            script = "import json,os;from pathlib import Path;Path('all_jobs.json').write_text('{\"jobs\":[]}');Path('linkedin_jobs.json').write_text('{\"jobs\":[]}');Path(os.environ['ELI_SOURCE_REPORT_PATH']).write_text(" + repr(json.dumps({"status": status, "observations": 0})) + ");raise SystemExit(" + str(code) + ")"
            result = run_source("linkedin", root, 5, [sys.executable, "-c", script])
            return result, json.loads((root / "all_jobs.json").read_text()), json.loads((root / "linkedin_jobs.json").read_text())

    def test_failure_restores_previous_data(self):
        result, master, feed = self.run_case("failure")
        self.assertEqual(result["status"], "failure")
        self.assertEqual(master["jobs"][0]["url"], "old")
        self.assertEqual(feed["jobs"][0]["date_posted"], "2026-09-01")

    def test_successful_empty_is_success(self):
        result, _, feed = self.run_case("success")
        self.assertEqual(result["status"], "success")
        self.assertEqual(feed["jobs"], [])

    def test_partial_retains_feed_dates(self):
        _, _, feed = self.run_case("partial")
        self.assertEqual(feed["jobs"][0]["date_posted"], "2026-09-01")

    def test_nonzero_exit_overrides_success_report(self):
        result, master, _ = self.run_case("success", 1)
        self.assertEqual(result["status"], "failure")
        self.assertTrue(master["jobs"])

    def test_timeout_restores_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "all_jobs.json").write_text('{"jobs":[]}')
            result = run_source("linkedin", root, .05, [sys.executable, "-c", "import time;from pathlib import Path;Path('all_jobs.json').write_text('bad');time.sleep(20)"])
            self.assertEqual(result["status"], "failure")
            self.assertEqual(json.loads((root / "all_jobs.json").read_text()), {"jobs": []})

    def test_missing_report_is_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_source("linkedin", root, 5, [sys.executable, "-c", "pass"])
            self.assertEqual(result["status"], "failure")

    def test_failure_does_not_stop_next_source_or_erase_last_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source_status.json").write_text(json.dumps({"sources": {"linkedin": {"last_success": "earlier"}}}))
            with patch("collect.run_source", side_effect=[{"status": "failure"}, {"status": "success", "observations": 2}]):
                status = collect(["linkedin", "indeed"], root)
            self.assertEqual(status["sources"]["linkedin"]["last_success"], "earlier")
            self.assertEqual(status["sources"]["indeed"]["observations"], 2)
            self.assertTrue(status["sources"]["indeed"]["last_success"])

    def test_artifact_excludes_internal_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in PUBLIC_FILES:
                (root / name).write_text("public")
            (root / "private.txt").write_text("private")
            build(root, root / "site")
            self.assertEqual({p.name for p in (root / "site").iterdir()}, set(PUBLIC_FILES) | {".nojekyll"})


if __name__ == "__main__":
    unittest.main()
