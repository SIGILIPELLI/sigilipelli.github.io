#!/usr/bin/env python3
"""Compares what visitors can actually load with the latest audit. Exit code 1 if anything is out of step.

Checks (all against https://learnmasterypath.com/, not local files):
  - registry/summary.json is the audit the repository says it is (optional --expect AUDIT_ID), and every file in registry/SHA256SUMS
    downloads with the listed checksum;
  - every public hub page carries the same audit id (meta tag + visible stamp) and any data-mp-stat numbers equal the summary;
  - the registry-driven pages show only that audit id and list lessons, projects and capstones separately;
  - search/courses.json counts equal the registry for every course; course-facts.json is from the same audit;
  - every course home page: meta description and visible text state the course's own lessons, projects and capstone, and nothing else.
Usage: python3 tools/registry/check_live_sync.py [--expect MPA-...] [--wait SECONDS]"""
import argparse, concurrent.futures as cf, hashlib, json, re, sys, time, urllib.request
SITE = 'https://learnmasterypath.com/'
ap = argparse.ArgumentParser(); ap.add_argument('--expect'); ap.add_argument('--wait', type=int, default=0)
args = ap.parse_args()
PAGES = ['', '404.html', 'about.html', 'contact.html', 'delivery.html', 'license.html', 'privacy.html', 'refunds.html', 'terms.html', 'course-catalogue/',
         'interview-pack/', 'interview-questions/', 'learning-impact/', 'quality-and-verification/', 'resume/', 'search/', 'verify/', 'world-record-attempt/']
def raw(u):
    last = None
    for i in range(4):
        try:
            return urllib.request.urlopen(urllib.request.Request(u + ('&' if '?' in u else '?') + 'sync=%d' % time.time(), headers={'User-Agent': 'MasteryPath-sync/2.0', 'Cache-Control': 'no-cache'}), timeout=40).read()
        except Exception as e:  # noqa: BLE001
            last = e; time.sleep(3 * (i + 1))
    raise last
def get(u): return raw(u).decode('utf8', 'replace')
def text(h): return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)\b.*?</\1>', ' ', h, flags=re.S)))
deadline = time.time() + args.wait
while True:
    S = json.loads(get(SITE + 'registry/summary.json'))
    if not args.expect or S['audit_id'] == args.expect or time.time() > deadline: break
    time.sleep(20)
bad = []
if args.expect and S['audit_id'] != args.expect: bad.append(f'live summary.json is {S["audit_id"]}, expected {args.expect}')
sid = S['audit_id']; P = S['published']
C = json.loads(get(SITE + 'registry/courses.json'))
# 1. evidence files match their published checksums
for line in get(SITE + 'registry/SHA256SUMS').splitlines():
    m = re.match(r'([0-9a-f]{64})\s+\*?(\S+)', line)
    if m and hashlib.sha256(raw(SITE + 'registry/' + m.group(2).split('registry/')[-1])).hexdigest() != m.group(1): bad.append(f'registry/{m.group(2)}: checksum differs from SHA256SUMS')
# 2. every public page: same audit id
def page(rel):
    out = []; h = get(SITE + rel); t = text(h)
    if re.findall(r'<meta name="mp-audit-id" content="([^"]+)"', h) != [sid]: out.append(f'{rel or "/"}: audit meta tag is not {sid}')
    ids = set(re.findall(r'MPA-\d{8}T\d{4}Z', h))
    if ids != {sid}: out.append(f'{rel or "/"}: shows audit ids {sorted(ids)}, summary is {sid}')
    for key, want in (('courses', P['courses']), ('lessons', P['lessons']), ('projects', P['projects'] + P['capstones'])):
        for got in re.findall(r'data-mp-stat="%s"[^>]*>([\d,]+)' % key, h):
            if int(got.replace(',', '')) != want: out.append(f'{rel or "/"}: {key} {got} != {want}')
    if rel in ('learning-impact/', 'world-record-attempt/', 'quality-and-verification/') or rel == 'course-catalogue/':
        for label, want in (('lessons', P['lessons']), ('projects', P['projects']), ('capstones', P['capstones'])):
            if rel != 'course-catalogue/' and f'{want:,}' not in t and str(want) not in t: out.append(f'{rel}: does not show {label} total {want:,}')
    if re.search(r'\b3,660\b|\b425 projects\b|eligible_pending_review', t): out.append(f'{rel or "/"}: contains a figure/status from an older audit')
    return out
with cf.ThreadPoolExecutor(8) as ex:
    for r in ex.map(page, PAGES): bad += r
# 3. course-facts and search index
facts = json.loads(get(SITE + 'registry/course-facts.json'))
if facts.get('audit_id') != sid: bad.append(f'course-facts.json is from {facts.get("audit_id")}')
sc = json.loads(get(SITE + 'search/courses.json')); sc = sc.get('courses', sc) if isinstance(sc, dict) else sc
reg = {c['course_slug']: c for c in C}
for x in sc:
    r = reg.get(x['id'])
    if r and (x['lessons'], x['projects'], x.get('capstones')) != (r['lesson_count'], r['project_count'], r['capstone_count']):
        bad.append(f"search index: {x['id']} has {x['lessons']}/{x['projects']}/{x.get('capstones')}, registry {r['lesson_count']}/{r['project_count']}/{r['capstone_count']}")
# 4. every course home page
def course(c):
    h = get(c['course_url']); t = text(h); out = []; s = c['course_slug']
    md = re.search(r'<meta name="description" content="([^"]*)"', h); d = md.group(1) if md else ''
    if d != c['course_description'].replace('&', '&amp;') and d != c['course_description']:
        out.append(f'{s}: meta description differs from the registry description')
    for blob, where in ((d, 'meta description'), (t, 'page text')):
        for m in re.finditer(r'\b(\d+) (?:hands-on |real )?lessons\b', blob):
            if int(m.group(1)) != c['lesson_count']: out.append(f"{s}: {where} says {m.group(0)}, registry {c['lesson_count']}")
        for m in re.finditer(r'\b(\d+) (?:hands-on |real )?projects\b', blob):
            if int(m.group(1)) != c['project_count']: out.append(f"{s}: {where} says {m.group(0)}, registry {c['project_count']} projects + {c['capstone_count']} capstone")
        for m in re.finditer(r'\b(\d+) capstones?\b', blob):
            if int(m.group(1)) != c['capstone_count']: out.append(f"{s}: {where} says {m.group(0)}, registry {c['capstone_count']}")
    return out
with cf.ThreadPoolExecutor(12) as ex:
    for r in ex.map(course, C): bad += r
print('OUT OF SYNC:' if bad else 'in sync with', sid, f"({len(C)} courses, {len(PAGES)} hub pages checked)")
for b in bad[:40]: print(' -', b)
sys.exit(1 if bad else 0)
