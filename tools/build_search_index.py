"""Build the Mastery Path site-search index from the live course sites.

Sources (no manual lesson lists):
  * index.html            -> every course, its category and the learning tracks (career paths)
  * tools/search-config.json -> synonyms, course types and extra career paths
  * each course's /search/search_index.json (published by MkDocs) -> lessons, descriptions, section topics
  * each course's home page -> meta description
Outputs:
  * search/courses.json, search/lessons.json, search/meta.json  (used by assets/search.js)
  * search-index.json  (legacy flat list used by the home page's "continue learning")
Usage: python3 tools/build_search_index.py [repo_root]
"""
import concurrent.futures as cf
import datetime
import html
import json
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.')
try:
    REGISTRY = {c['course_slug']: c for c in json.loads((ROOT / 'registry/courses.json').read_text())}
    CONFIG = json.loads((ROOT / 'registry/config.json').read_text())
except Exception:  # noqa: BLE001
    REGISTRY = {}
    CONFIG = {}
SITE = 'https://learnmasterypath.com/'
UA = {'User-Agent': 'MasteryPathSearchIndexer/1.0 (+https://learnmasterypath.com/)'}
LEVELS = {1: 'Beginner', 2: 'Intermediate', 3: 'Advanced', 4: 'Expert'}


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            err = e
    raise RuntimeError(f'{url}: {err}')


def clean(s):
    s = html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))
    return re.sub(r'\s+', ' ', s).strip()


def clip(s, n):
    s = clean(s)
    if len(s) <= n:
        return s
    cut = s[: n - 1]
    dot = cut.rfind('. ')
    return (cut[: dot + 1] if dot > n * 0.55 else cut.rsplit(' ', 1)[0].rstrip(',;:—-') + '…')


def strip_emoji(label):
    return re.sub(r'^[^\w(]+', '', label).strip()


hub = (ROOT / 'index.html').read_text()
cfg = json.loads((ROOT / 'tools/search-config.json').read_text())
catalog = json.loads(re.search(r'<script type="application/json" id="mp-catalog-map">(.*?)</script>', hub, re.S).group(1))

# ---- courses & categories from the home page ----
courses, order = {}, []
for m in re.finditer(r'<details class="flashcard[^"]*" id="([^"]+)">.*?fc-title">([^<]+)<.*?<div class="grid">(.*?)</div>', hub, re.S):
    cat_id, cat_name = m.group(1), html.unescape(m.group(2)).strip()
    for url, label in re.findall(r'<a href="(https://learnmasterypath\.com/[^"]+/)">([^<]+)</a>', m.group(3)):
        cid = url.rstrip('/').split('/')[-1]
        if cid in courses:
            continue
        label = html.unescape(label)
        emoji = label.split(' ', 1)[0] if not label[0].isalnum() else ''
        courses[cid] = {'id': cid, 'url': url, 'short': strip_emoji(label), 'emoji': emoji, 'cat': cat_id, 'catName': cat_name,
                        'type': cfg['course_types'].get(cat_id, 'Course'), 'careers': [], 'aliases': cfg['aliases'].get(cid, [])}
        order.append(cid)

# career paths: the home page's learning tracks + config extras
tracks = {}
for m in re.finditer(r'<(\w+) class="track-title">([^<]+)</\1>.*?<(\w+) class="track-steps">(.*?)</\3>', hub, re.S):
    tracks[html.unescape(m.group(2)).strip()] = [u.rstrip('/').split('/')[-1] for u in re.findall(r'href="(https://learnmasterypath\.com/[^"]+)"', m.group(4))]
if len(tracks) < 3:
    sys.exit('Could not read the learning paths from index.html; keeping the previous index.')
for name, ids in cfg['career_paths'].items():  # extras extend a home-page path of the same name
    tracks[name] = list(dict.fromkeys(tracks.get(name, []) + ids))
for name, ids in tracks.items():
    for cid in ids:
        if cid in courses and name not in courses[cid]['careers']:
            courses[cid]['careers'].append(name)


# ---- per-course data from the live sites ----
def load(cid):
    c = courses[cid]
    home = get(c['url'])
    title = re.search(r'<meta property="og:title" content="([^"]*)"', home)
    desc = re.search(r'<meta name="description" content="([^"]*)"', home)
    name = re.search(r'"@type": "Course",\s*"name": ("(?:[^"\\]|\\.)+")', home)
    idx = json.loads(get(c['url'] + 'search/search_index.json'))['docs']
    lessons, heads, res = [], {}, []
    for d in idx:
        loc = d['location']
        if loc in ('interview-questions/', 'cheat-sheet/'):
            res.append([clean(d['title']), loc])
            continue
        m = re.match(r'^(level-(\d+)/([^/#]+)/)(#.*)?$', loc)
        if not m:
            continue
        if m.group(4):
            t = clean(d['title'])
            if t and not re.match(r'^(cheat sheet|exercise|exercises|how it actually works|summary|key takeaways|quiz)$', t, re.I):
                heads.setdefault(m.group(1), []).append(re.sub(r'^\d+\.\s*', '', t))
        else:
            lessons.append({'path': m.group(1), 'level': int(m.group(2)), 'title': clean(d['title']), 'text': d['text']})
    out = []
    for les in lessons:
        out.append({'c': cid, 'l': les['level'], 't': les['title'], 'u': les['path'], 'd': clip(les['text'], 105),
                    'k': clip(' · '.join(dict.fromkeys(heads.get(les['path'], []))), 110)})
    c['res'] = res
    return cid, {'name': html.unescape(json.loads(name.group(1))) if name else c['short'] + ' Mastery Path',
                 'desc': clip(html.unescape(desc.group(1)) if desc else '', 200), 'seo': html.unescape(title.group(1)) if title else ''}, out


errors, lessons = [], []
with cf.ThreadPoolExecutor(12) as ex:
    futs = {ex.submit(load, cid): cid for cid in order}
    for f in cf.as_completed(futs):
        cid = futs[f]
        try:
            _, info, les = f.result()
            courses[cid].update(name=info['name'], desc=info['desc'])
            lesson_exceptions = set(CONFIG.get('rules', {}).get('lesson_slug_exceptions', {}).get(cid, []))
            is_proj = lambda x: x['u'].rstrip('/').split('/')[-1] not in lesson_exceptions and bool(re.search(r'/\d+-(project|capstone)\b', x['u']))
            courses[cid]['lessons'] = len([x for x in les if not is_proj(x)])
            courses[cid]['projects'] = len([x for x in les if is_proj(x)])
            # course-specific counts come from the registry audit, not from this crawl (the crawl is only a cross-check)
            reg = REGISTRY.get(cid)
            if reg:
                courses[cid]['lessons'] = reg['lesson_count']
                courses[cid]['projects'] = reg['project_count']
                courses[cid]['capstones'] = reg['capstone_count']
            lessons += les
        except Exception as e:  # noqa: BLE001
            errors.append(f'{cid}: {e}')

if errors:
    print('ERRORS:\n  ' + '\n  '.join(errors))
    if len(errors) > 5:
        sys.exit('Too many course fetch errors; keeping the previous index.')

ids = [cid for cid in order if courses[cid].get('lessons')]
pos = {cid: i for i, cid in enumerate(ids)}
course_list = [{k: courses[cid].get(k, []) for k in ('id', 'name', 'short', 'emoji', 'url', 'desc', 'cat', 'catName', 'type', 'careers', 'aliases', 'lessons', 'projects', 'capstones', 'res')} for cid in ids]
lessons.sort(key=lambda x: (pos.get(x['c'], 999), x['l'], x['u']))
# path is stored without the 'level-N/' prefix (the level is its own field) to keep the file small
lesson_list = [[pos[x['c']], x['l'], x['t'], x['u'].split('/', 1)[1], x['d'], x['k']] for x in lessons if x['c'] in pos]

out = ROOT / 'search'
out.mkdir(exist_ok=True)
(out / 'courses.json').write_text(json.dumps(course_list, ensure_ascii=False, separators=(',', ':')))
(out / 'lessons.json').write_text(json.dumps({'fields': ['course', 'level', 'title', 'slug', 'desc', 'topics'], 'url': '{course.url}level-{level}/{slug}', 'rows': lesson_list}, ensure_ascii=False, separators=(',', ':')))
cats = sorted({(c['cat'], c['catName']) for c in course_list}, key=lambda x: x[1])
meta = {'built': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), 'courses': len(course_list), 'lessons': len(lesson_list),
        'categories': [{'id': a, 'name': b} for a, b in cats], 'types': sorted({c['type'] for c in course_list}),
        'careers': sorted(tracks), 'paths': tracks, 'levels': LEVELS, 'suggested': cfg['suggested']}
(out / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1))
legacy = [{'title': x[2], 'url': course_list[x[0]]['url'] + f'level-{x[1]}/' + x[3], 'site': course_list[x[0]]['short']} for x in lesson_list]
(ROOT / 'search-index.json').write_text(json.dumps(legacy, ensure_ascii=False, indent=2) + '\n')
print(f"built {len(course_list)} courses, {len(lesson_list)} lessons; courses.json {(out / 'courses.json').stat().st_size // 1024} KB, lessons.json {(out / 'lessons.json').stat().st_size // 1024} KB")
