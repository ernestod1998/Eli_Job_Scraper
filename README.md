# Eli's Job Scraper

Independent Sacramento-area and California-compatible U.S. remote job search.

Targets finance, budgeting, fiscal and administrative analysis, grants and contracts,
accounting, procurement, purchasing, and related compliance roles. All salaries and
work arrangements are included. Unknown eligibility is labeled for review.

The dashboard stores saved, applied, and dismissed decisions in this browser only.
Use Export regularly to keep a backup; Import restores it on another device.
There is no cross-device service, paid AI ranking, or notification integration.

This public repository contains no résumé or contact information. Never commit
credentials or candidate documents. This is an independent copy of the scraper
maintained by ernestod1998; it does not synchronize code or personal data with any
other scraper.

## Dashboard

Open https://ernestod1998.github.io/Eli_Job_Scraper/ after deployment.
Source status distinguishes successful collection from partial or failed requests.
A listed role is a potential match, not confirmation of eligibility or availability.

## Development

Use Python 3.11 or newer and install `requirements.txt`. Run Python tests with
`python -m unittest discover -p 'test_*.py'` and the dashboard checks with
`node test_dashboard.mjs` and `node test_dates.mjs`.

Daily automation is gated by the repository variable `ENABLE_SCHEDULE`. It remains
off until the initial manual collection and Pages deployment are verified.
