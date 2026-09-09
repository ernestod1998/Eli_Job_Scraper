#!/usr/bin/env python3
"""Secret-free regression tests for scraper filtering and retrieval policy."""

import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import scrape_jobs as sj

# A frozen fixture date becomes provably stale once real time passes it by
# MAX_POSTING_AGE_DAYS and the choke point starts rejecting every fixture
# row — so the default is always "yesterday".
FRESH_FIXTURE_DATE = (
    datetime.now(timezone.utc) - timedelta(days=1)
).strftime("%Y-%m-%dT%H:%M:%SZ")


def role(url="https://example.com/job/1", **overrides):
    job = {
        "company": "Acme", "title": "Financial Analyst",
        "location": "Sacramento, CA", "url": url,
        "date_posted": FRESH_FIXTURE_DATE, "ats": "Test",
    }
    job.update(overrides)
    return job


class RoleAndLocationPolicy(unittest.TestCase):
    def test_uncertainty_and_description_exclusions(self):
        jobs = [role("https://x/remote", location="US Remote", salary=""),
                role("https://x/excluded", location="US Remote", description="Not available in California"),
                role("https://x/ambiguous", title="Administrative Analyst", salary="$12/hour")]
        kept, rejected, _ = sj._filter_job_observations(jobs, default_feed="general")
        self.assertEqual(len(kept), 2)
        self.assertEqual(kept[0]["california_eligibility"], "unverified")
        self.assertEqual(kept[1]["role_fit"], "unverified")
        self.assertEqual(rejected[0]["reason"], "location")

    def test_daily_lookbacks_overlap(self):
        self.assertEqual(sj.LINKEDIN_LOOKBACK_SECONDS, 48 * 3600)
        self.assertEqual(sj.INDEED_LOOKBACK_HOURS, 48)
        self.assertEqual(sj.BOARDS_LOOKBACK_HOURS, 48)

    def test_live_buyer_and_specialized_compliance_false_positives(self):
        for title in ("Inbound Sales Closer — Dental Buyer Advocates", "Grocery Order Writer (Buyer / Inventory Replenishment) - Full Time"):
            self.assertFalse(sj.is_target_role(title), title)
        for title in ("Buyer II", "Procurement Analyst", "Financial Management Analyst II"):
            self.assertTrue(sj.is_target_role(title), title)
        specialized = role(title="Regulatory Compliance Analyst", description="Conduct trade practice surveillance and CFTC regulatory filings.")
        kept, rejected, _ = sj._filter_job_observations([specialized], default_feed="general")
        self.assertEqual(kept, [])
        self.assertEqual(rejected[0]["reason"], "role")
        self.assertEqual(sj.classify_job(role(title="Regulatory Compliance Analyst"))["role_fit"], "unverified")
        self.assertEqual(sj.classify_job(role(title="Financial Management Analyst II"))["role_fit"], "matched")

    def test_fallback_report_is_failure_not_fresh_observation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ELI_SOURCE_REPORT_PATH": os.path.join(tmp, "status.json")}), patch.object(sj, "SOURCE_DIAGNOSTICS", ["⛔ preserving previous results"]):
            sj.write_source_report([role()])
            with open(os.path.join(tmp, "status.json")) as handle:
                report = json.load(handle)
            self.assertEqual(report["status"], "failure")
            self.assertEqual(report["observations"], 0)

    def test_hollywood_company_matching_is_exact_not_substring_based(self):
        self.assertFalse(sj._is_hollywood_company("Meta"))
        self.assertFalse(sj._is_hollywood_company("Disney Cruise Vacations LLC"))
        self.assertTrue(sj._is_hollywood_company("A24"))
        self.assertTrue(sj._is_hollywood_company("Warner Bros. Discovery"))
        self.assertTrue(sj._is_hollywood_company("Creative Artists Agency"))

    def test_eli_roles_and_geography(self):
        for title in ("Financial Analyst", "Senior Financial Analyst", "Budget Analyst", "Buyer II", "Contract Analyst"):
            self.assertTrue(sj.is_target_role(title), title)
        for title in ("Director Financial Analyst", "Software Analyst", "Marketing Coordinator", "AML Compliance Analyst"):
            self.assertFalse(sj.is_target_role(title), title)
        for city in sj.SACRAMENTO_CITIES:
            self.assertTrue(sj.is_watch_location(city + ", CA"))
        for location in ("Woodland, WA", "Davis", "Los Angeles, CA", "Remote - Spain", "US Remote except California"):
            self.assertFalse(sj.is_watch_location(location), location)
        self.assertTrue(sj.is_watch_location("Remote - USA"))

    def test_filter_is_feed_aware_and_reports_stats(self):
        rows = [
            role("https://x/ok"),
            role("https://x/senior", title="Director Financial Analyst"),
            role("https://x/far", location="Boston, MA"),
            role("https://x/company", company="Jack & Jill"),
            role("https://x/old", date_posted="2024-09-04"),
        ]
        kept, rejected, stats = sj._filter_job_observations(rows, default_feed="general")
        self.assertEqual([j["url"] for j in kept], ["https://x/ok"])
        self.assertEqual(kept[0]["feeds"], ["general"])
        self.assertEqual(stats, {"company": 1, "seniority": 1, "role": 0, "location": 1, "stale": 1})
        self.assertEqual({r["reason"] for r in rejected}, {"company", "seniority", "location", "stale"})
        bio, _, _ = sj._filter_job_observations(
            [role("https://x/bio", location="Sacramento, CA")], default_feed="hollywood")
        self.assertEqual(bio[0]["feeds"], ["hollywood"])

    def test_stale_policy_at_the_choke_point(self):
        now = datetime.now(timezone.utc)

        def days_ago(n):
            return (now - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ")

        rows = [
            role("https://x/fresh", date_posted=days_ago(13)),
            role("https://x/stale", date_posted=days_ago(15)),
            role("https://x/workday-old", date_posted="Posted 30+ Days Ago"),
            role("https://x/workday-fresh", date_posted="Posted 2 Days Ago"),
            role("https://x/undated", date_posted=""),
        ]
        kept, _, stats = sj._filter_job_observations(rows, default_feed="general")
        self.assertEqual(
            [j["url"] for j in kept],
            ["https://x/fresh", "https://x/workday-fresh", "https://x/undated"],
        )
        self.assertEqual(stats["stale"], 2)


class MasterPolicy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_dir = sj.SCRIPT_DIR
        sj.SCRIPT_DIR = self.tmp.name

    def tearDown(self):
        sj.SCRIPT_DIR = self.old_dir
        self.tmp.cleanup()

    def read_master(self):
        with open(os.path.join(self.tmp.name, "all_jobs.json")) as f:
            return json.load(f)["jobs"]

    def test_canonical_identity_refreshes_and_preserves_first_seen(self):
        sj._merge_into_all_jobs([role("https://example.com/job/1?source=a", feeds=["general"])])
        first = self.read_master()[0]["first_seen"]
        sj._merge_into_all_jobs([role(
            "https://example.com/job/1?source=b", feeds=["hollywood"],
            title="Financial Analyst", salary="$100k",
        )])
        jobs = self.read_master()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["first_seen"], first)
        self.assertEqual(jobs[0]["title"], "Financial Analyst")
        self.assertEqual(jobs[0]["feeds"], ["general", "hollywood"])

    def test_rejection_removes_only_one_feed(self):
        sj._merge_into_all_jobs([role(feeds=["general", "hollywood"])])
        sj._merge_into_all_jobs([], [{
            "identity": sj._job_identity("https://example.com/job/1"),
            "feed": "general", "reason": "location",
        }])
        self.assertEqual(self.read_master()[0]["feeds"], ["hollywood"])
        sj._merge_into_all_jobs([], [{
            "identity": sj._job_identity("https://example.com/job/1"),
            "feed": "hollywood", "reason": "seniority",
        }])
        self.assertEqual(self.read_master(), [])

    def test_accepted_duplicate_wins_over_same_feed_rejection(self):
        sj._merge_into_all_jobs([role(feeds=["general"])])
        first = self.read_master()[0]["first_seen"]
        sj._merge_into_all_jobs([role(feeds=["general"], salary="$120k")], [{
            "identity": sj._job_identity("https://example.com/job/1"),
            "feed": "general", "reason": "location",
        }])
        self.assertEqual(self.read_master()[0]["first_seen"], first)
        self.assertEqual(self.read_master()[0]["salary"], "$120k")


class RetrievalPolicy(unittest.TestCase):
    @staticmethod
    def card(job_id, title="Financial Analyst"):
        return (
            f'<li><div data-entity-urn="urn:li:jobPosting:{job_id}">'
            f'<h3 class="base-search-card__title">{title}</h3>'
            '<h4 class="base-search-card__subtitle">Acme</h4>'
            '<span class="job-search-card__location">Sacramento, CA</span>'
            '<time datetime="2026-08-05"></time></div></li>'
        )

    def test_linkedin_advances_by_raw_page_size_and_stops_repeat(self):
        page = "".join(self.card(str(i)) for i in range(10))
        urls = []

        def fake_fetch(url):
            urls.append(url)
            return page

        with patch.object(sj, "LINKEDIN_LOCATIONS", [("Sacramento, CA", "1")]), \
             patch.object(sj, "fetch", side_effect=fake_fetch), \
             patch.object(sj.time, "sleep"):
            jobs, raw = sj._linkedin_search(["marketing coordinator"], 3600)
        self.assertEqual(len(jobs), 10)
        self.assertEqual(raw, 20)  # repeated page is counted as received raw data
        self.assertEqual([re.search(r"start=(\d+)", u).group(1) for u in urls], ["0", "10"])

    def test_jobspy_retries_only_on_exactly_fifty(self):
        calls = []

        def fake(**kwargs):
            calls.append(kwargs["results_wanted"])
            return list(range(kwargs["results_wanted"]))

        self.assertEqual(len(sj._jobspy_fetch_with_retry(fake, site_name=["indeed"])), 100)
        self.assertEqual(calls, [50, 100])
        calls.clear()

        def short(**kwargs):
            calls.append(kwargs["results_wanted"])
            return list(range(49))

        self.assertEqual(len(sj._jobspy_fetch_with_retry(short)), 49)
        self.assertEqual(calls, [50])

    def test_jobspy_metro_radii(self):
        self.assertEqual(sj.JOBSPY_LOCATIONS, [("Sacramento, CA", 35), ("Remote", 50)])


class RefilterCommand(unittest.TestCase):
    def test_preview_is_read_only_and_write_preserves_first_seen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "all_jobs.json")
            payload = {"updated_at": "old", "jobs": [
                role("https://x/keep", first_seen="2026-08-01T00:00:00Z"),
                role("https://x/drop", title="Director Financial Analyst",
                     first_seen="2026-08-01T00:00:00Z"),
            ]}
            with open(path, "w") as f:
                json.dump(payload, f)
            with open(path) as f:
                before = f.read()
            with patch.object(sj, "SCRIPT_DIR", tmp):
                sj.refilter_existing_outputs(write=False)
                with open(path) as f:
                    self.assertEqual(f.read(), before)
                sj.refilter_existing_outputs(write=True)
            with open(path) as f:
                jobs = json.load(f)["jobs"]
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["first_seen"], "2026-08-01T00:00:00Z")

    def test_master_migration_uses_hollywood_source_url_provenance(self):
        job = role("https://unknown-studio.example/job/1", location="Sacramento, CA")
        kept, stats = sj._refilter_master_jobs(
            [job], {sj._job_identity(job["url"])})
        self.assertEqual(stats["location"], 0)
        self.assertEqual(kept[0]["feeds"], ["hollywood"])


class RegistrySaveIntegration(unittest.TestCase):
    def test_mixed_feeds_and_per_board_baseline_marker(self):
        rows = [
            role("https://registry/quiet", location="Sacramento, CA", ats="Greenhouse",
                 feeds=["hollywood"], registry_notify_eligible=False),
            role("https://registry/loud", location="Sacramento, CA", ats="Lever",
                 feeds=["general"], registry_notify_eligible=True),
        ]
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(sj, "SCRIPT_DIR", tmp), \
             patch("notify.notify_new_jobs") as mocked_notify:
            sj.save_jobs_output(
                rows, basename="registry_jobs", title="Registry", subtitle="Test",
                accent="#000", empty_message="Empty", window_label="test",
                default_feed="general",
            )
            with open(os.path.join(tmp, "registry_jobs.json")) as f:
                saved = json.load(f)["jobs"]
        self.assertEqual([j["feeds"] for j in saved], [["hollywood"], ["general"]])
        self.assertTrue(all("registry_notify_eligible" not in j for j in saved))
        mocked_notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
