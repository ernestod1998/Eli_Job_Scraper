"""Reapply current eligibility policy to source evidence and the public master."""
import json
from pathlib import Path
import scrape_jobs as scraper

def main():
    rejected = []
    for path in Path(__file__).parent.glob('*_jobs.json'):
        if path.name == 'all_jobs.json':
            continue
        data = json.loads(path.read_text())
        accepted, excluded, _ = scraper._filter_job_observations(data.get('jobs', []), default_feed='general')
        rejected.extend(excluded)
        data['jobs'] = accepted
        data['total'] = len(accepted)
        path.write_text(json.dumps(data, indent=2) + '\n')
    scraper._merge_into_all_jobs([], rejected)
    print(f'Reviewed source evidence; {len(rejected)} excluded observations removed.')

if __name__ == '__main__':
    main()
