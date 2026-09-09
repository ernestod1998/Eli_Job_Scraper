"""Initialize independently verified public employer boards without inherited data."""
from datetime import date, timedelta
import ats_registry as registry

SEEDS = [
    ('Think Academy International Education', 'greenhouse', 'thinkacademyus'),
    ('Strada Education Foundation', 'lever', 'stradaeducation'),
    ('ICF International', 'workday', 'https://icf.wd5.myworkdayjobs.com/wday/cxs/icf/icfexternal_career_site/jobs'),
    ('Robert Half', 'workday', 'https://roberthalf.wd1.myworkdayjobs.com/wday/cxs/roberthalf/roberthalfcareers/jobs'),
    ('Simons Foundation', 'workday', 'https://simonsfoundation.wd1.myworkdayjobs.com/wday/cxs/simonsfoundation/simonsfoundationcareers/jobs'),
    ('Khan Academy', 'greenhouse', 'khanacademy'),
]

def main():
    data = registry.load_registry()
    for name, ats, locator in SEEDS:
        registry.add_candidate(data, name=name, ats=ats, locator=locator, source='eli-curated-public-board')
    client = registry.BoundedClient()
    result = registry.verify_registry(data, client, limit=len(SEEDS))
    for board in data['boards'].values():
        if board['status'] == 'active':
            board['promoted_until'] = (date.today() + timedelta(days=14)).isoformat()
    registry.save_registry(data)
    print(result)

if __name__ == '__main__':
    main()
