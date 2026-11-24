#!/usr/bin/env python3
"""Compares what visitors can actually load with the latest audit: the published summary.json, the registry-driven hub pages
and every course home page. Exit code 1 if anything is out of step. Run it after a deploy: python3 tools/registry/check_live_sync.py"""
import concurrent.futures as cf, json, re, sys, urllib.request
SITE = 'https://learnmasterypath.com/'
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'MasteryPath-sync/1.0'}), timeout=40).read().decode('utf8', 'replace')
S = json.loads(get(SITE + 'registry/summary.json'))
C = json.loads(get(SITE + 'registry/courses.json'))
bad = []
for page in ('learning-impact/', 'quality-and-verification/', 'world-record-attempt/'):
    ids = set(re.findall(r'MPA-\d{8}T\d{4}Z', get(SITE + page)))
    if not ids <= {S['audit_id']}: bad.append(f'{page}: shows {sorted(ids)}, summary is {S["audit_id"]}')
for page in ('', 'about.html'):
    t = get(SITE + page)
    for key, want in (('courses', S['published']['courses']), ('lessons', S['published']['lessons']), ('projects', S['published']['projects'] + S['published']['capstones'])):
        for got in re.findall(r'data-mp-stat="%s">([\d,]+)' % key, t):
            if int(got.replace(',', '')) != want: bad.append(f'{page or "/"}: {key} {got} != {want}')
facts = json.loads(get(SITE + 'registry/course-facts.json'))
if facts.get('audit_id') != S['audit_id']: bad.append(f'course-facts.json is from {facts.get("audit_id")}')
def course(c):
    h = get(c['course_url']); out = []
    m = re.search(r'(\d+) lessons and (\d+) projects?', re.sub(r'<[^>]+>', ' ', h))
    if m and (int(m.group(1)), int(m.group(2))) != (c['lesson_count'], c['project_count'] + c['capstone_count']):
        out.append(f"{c['course_slug']}: page says {m.group(0)}, registry {c['lesson_count']} lessons and {c['project_count'] + c['capstone_count']} projects")
    return out
with cf.ThreadPoolExecutor(12) as ex:
    for r in ex.map(course, C): bad += r
print('OUT OF SYNC:' if bad else 'in sync with', S['audit_id'])
for b in bad[:30]: print(' -', b)
sys.exit(1 if bad else 0)
