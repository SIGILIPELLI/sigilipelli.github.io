#!/usr/bin/env python3
"""Mastery Path course registry + counting engine (single source of truth for every published count).

Usage (from the hub repo root):
  python3 tools/registry/build_registry.py [--check-urls] [--repos ../] [--archive]

Reads (published state, so counts describe what learners can actually open):
  - search/courses.json            course list, names, categories (built from the live sites)
  - <course>/search/search_index.json on learnmasterypath.com   every published page + section text
  - learn/quizzes/<course>.json    module quizzes
  - registry/config.json           classification, thresholds, definitions (methodology version)
  - registry/ids.json              stable IDs and first-publication dates (append-only)
  - registry/reviews.json          human content reviews (the only source of "last reviewed")
  - git history (local clones via --repos, else the GitHub API) for content dates and versions
Writes registry/*.json and the evidence CSVs listed in registry/README.md.

Counting rules live in this file only (see METHODOLOGY in registry/config.json).
"""
import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import difflib
import hashlib
import html
import io
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / 'registry'
SITE = 'https://learnmasterypath.com/'
UA = {'User-Agent': 'MasteryPath-registry/1.0'}
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def status(url):
    """HEAD request with retries: GitHub Pages answers 429/503 when hit hard, which is not a missing page."""
    import time
    code = 0
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers=UA, method='HEAD')
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status
        except urllib.error.HTTPError as e:
            code = e.code
            if code not in (429, 500, 502, 503, 504):
                return code
        except Exception:
            code = 0
        time.sleep(2 * (attempt + 1))
    return code


def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def words(s):
    return len(re.findall(r"[A-Za-z0-9][\w'’.-]*", s))


def fingerprint(text):
    norm = re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()
    return hashlib.sha256(norm.encode()).hexdigest()


def shingles(text, k=5):
    w = re.findall(r'[a-z0-9]+', text.lower())
    return {' '.join(w[i:i + k]) for i in range(max(0, len(w) - k + 1))}


def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


# ---------------------------------------------------------------- git dates
def git_dates(repos_root, course):
    """(first_commit_date, last_docs_commit_date, last_docs_commit_sha) from a local clone or the GitHub API."""
    slug = course['id']
    rel = course['url'].replace(SITE, '').strip('/')          # e.g. python-mastery-path/mcp-mastery-path
    repo = rel.split('/')[0]
    sub = '/'.join(rel.split('/')[1:])
    docs = (sub + '/docs') if sub else 'docs'
    if repos_root:
        for cand in (Path(repos_root) / 'all' / repo, Path(repos_root) / 'newcourses' / {'tally-gst-mastery-path': 'tally', 'digital-marketing-mastery-path': 'dm'}.get(repo, '-'), Path(repos_root) / repo):
            if (cand / '.git').exists():
                def g(*a):
                    return subprocess.run(['git', '-C', str(cand), *a], capture_output=True, text=True).stdout.strip()
                first = g('log', '--reverse', '--format=%cI', '--', docs).split('\n')[0]
                last = g('log', '-1', '--format=%cI|%h', '--', docs)
                if first and last:
                    return first[:10], last.split('|')[0][:10], last.split('|')[1]
    token = os.environ.get('GITHUB_TOKEN')
    try:
        h = dict(UA, Accept='application/vnd.github+json')
        if token:
            h['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(f'https://api.github.com/repos/SIGILIPELLI/{repo}/commits?path={docs}&per_page=1', headers=h)
        with urllib.request.urlopen(req, timeout=30) as r:
            c = json.loads(r.read())[0]
        return None, c['commit']['committer']['date'][:10], c['sha'][:7]
    except Exception:
        return None, None, None


# ---------------------------------------------------------------- per course
def read_course(c, cfg, quizzes_dir):
    url = c['url']
    out = {'ok': False, 'errors': []}
    try:
        st, body = fetch(url + 'search/search_index.json')
        docs = json.loads(body)['docs']
    except Exception as e:
        out['errors'].append(f'search index unavailable: {e}')
        return out
    try:
        st_home, home = fetch(url)
        home = home.decode('utf-8', 'replace')
    except Exception as e:
        st_home, home = 0, ''
        out['errors'].append(f'course home unavailable: {e}')
    pages = {}
    for d in docs:
        loc = d['location']
        base, _, anchor = loc.partition('#')
        p = pages.setdefault(base, {'title': '', 'text': [], 'heads': []})
        if anchor:
            p['heads'].append(clean(d['title']))
        else:
            p['title'] = clean(d['title'])
        p['text'].append(clean(d['text']))
    lessons, levels = [], {}
    for base, p in pages.items():
        m = re.match(r'^level-(\d+)/([^/]+)/$', base)
        if base.startswith('level-') and re.match(r'^level-\d+/$', base):
            levels[int(base.split('-')[1].rstrip('/'))] = p['title']
            continue
        if not m:
            continue
        text = ' '.join(p['text'])
        slug = m.group(2)
        kind = 'lesson'
        if re.search(cfg['rules']['project_slug'], slug, re.I) or re.search(cfg['rules']['capstone_slug'], slug, re.I):
            kind = 'project'
        ex = [h for h in p['heads'] if re.match(cfg['rules']['exercise_heading'], h, re.I)]
        num = re.match(r'^(\d+)', slug)
        lessons.append({'path': base, 'level': int(m.group(1)), 'ordinal': int(num.group(1)) if num else 0, 'slug': slug,
                        'title': re.sub(r'^\d+\s*·\s*', '', p['title']), 'type': kind, 'words': words(text),
                        'exercises': len(ex), 'fp': fingerprint(text), 'sh': shingles(text) if kind == 'lesson' else set()})
    lessons.sort(key=lambda x: (x['level'], x['ordinal'], x['slug']))
    # capstone = the final project page of the highest level (one per course at most)
    finals = [l for l in lessons if l['type'] == 'project' and l['level'] == 4]
    if finals:
        finals[-1]['type'] = 'capstone'
    q = load(quizzes_dir / f"{c['id']}.json", {})
    fin = q.get('final') or {}
    out.update(ok=True, http_home=st_home, home_html=home, lessons=lessons, level_titles=levels,
               module_quizzes=len((q.get('lessons') or {})), quiz_keys={k.rstrip('/') for k in (q.get('lessons') or {})},
               quiz_questions=sum(len(v.get('questions', [])) for v in (q.get('lessons') or {}).values()),
               final_questions=len(fin.get('questions', [])), challenges=len(fin.get('challenges', [])), final_quiz='quiz/' in pages,
               syllabus=bool(re.search(r'href="level-1/', home)) and bool(re.search(r'href="level-4/', home)),
               noindex='name="robots" content="noindex' in home)
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check-urls', action='store_true', help='HEAD-request every lesson URL')
    ap.add_argument('--repos', help='folder holding the course clones (all/, newcourses/) for git dates')
    ap.add_argument('--archive', action='store_true', help='also keep a dated copy of the evidence under registry/audits/')
    args = ap.parse_args()

    cfg = load(REG / 'config.json', None)
    if not cfg:
        sys.exit('registry/config.json missing')
    ids = load(REG / 'ids.json', {'courses': {}, 'lessons': {}})
    reviews = load(REG / 'reviews.json', [])
    try:  # reviews recorded in the protected dashboard (public, read-only endpoint)
        reviews += json.loads(fetch('https://api.learnmasterypath.com/api/reviews')[1]).get('reviews', [])
    except Exception:
        pass
    courses = json.loads((ROOT / 'search/courses.json').read_text())
    meta = json.loads((ROOT / 'search/meta.json').read_text())
    sitemap_index = fetch(SITE + 'sitemap.xml')[1].decode()

    # stable course IDs: existing ones never change; new courses get the next number
    used = [int(v['id'].split('-')[1]) for v in ids['courses'].values()]
    for c in sorted(courses, key=lambda c: c['id']):
        if c['id'] not in ids['courses']:
            n = max(used, default=0) + 1; used.append(n)
            ids['courses'][c['id']] = {'id': f'MP-{n:03d}', 'registered': NOW.date().isoformat()}

    with cf.ThreadPoolExecutor(12) as ex:
        data = dict(zip([c['id'] for c in courses], ex.map(lambda c: read_course(c, cfg, ROOT / 'learn/quizzes'), courses)))
        dates = dict(zip([c['id'] for c in courses], ex.map(lambda c: git_dates(args.repos, c), courses)))

    rv = {}
    for r in reviews:
        if r.get('course_slug') and r.get('date') and r['date'] >= rv.get(r['course_slug'], {}).get('date', ''):
            rv[r['course_slug']] = r

    # lesson URL checks
    url_status = {}
    if args.check_urls:
        targets = [c['url'] + l['path'] for c in courses for l in data[c['id']].get('lessons', [])]
        with cf.ThreadPoolExecutor(12) as ex:
            url_status = dict(zip(targets, ex.map(status, targets)))

    # duplicates: exact text fingerprints, then near-duplicate text among lessons with the same title, then similar course titles
    dup_rows, fp_seen, by_title = [], {}, {}
    for c in courses:
        for l in data[c['id']].get('lessons', []):
            key = (c['id'], l['path'])
            if l['words'] >= 40 and l['fp'] in fp_seen:
                dup_rows.append({'type': 'exact_lesson_text', 'a': '/'.join(fp_seen[l['fp']]), 'b': '/'.join(key), 'score': '1.00', 'action': 'review'})
            fp_seen.setdefault(l['fp'], key)
            if l['type'] == 'lesson':
                by_title.setdefault(re.sub(r'[^a-z0-9]+', ' ', l['title'].lower()).strip(), []).append((key, l['sh']))
    for t, group in by_title.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i][1], group[j][1]
                if a and b:
                    jac = len(a & b) / len(a | b)
                    if jac >= cfg['rules']['near_duplicate_jaccard']:
                        dup_rows.append({'type': 'near_duplicate_lesson', 'a': '/'.join(group[i][0]), 'b': '/'.join(group[j][0]), 'score': f'{jac:.2f}', 'action': 'review'})
    names = [(c['id'], re.sub(r'\s*mastery path\s*$', '', c['name'], flags=re.I)) for c in courses]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if min(len(names[i][1]), len(names[j][1])) < 4:
                continue
            r = difflib.SequenceMatcher(None, names[i][1].lower(), names[j][1].lower()).ratio()
            if r >= cfg['rules']['similar_title_ratio']:
                dup_rows.append({'type': 'similar_course_title', 'a': names[i][0], 'b': names[j][0], 'score': f'{r:.2f}', 'action': 'review (titles only; not removed)'})
    # candidates a person has assessed and recorded in config.json stay in the file, marked as reviewed, so the audit has no unresolved item
    for row in dup_rows:
        for rv_ in cfg.get('duplicate_reviews', []):
            if {row['a'], row['b']} == {rv_['a'], rv_['b']} and row['type'] == rv_['type']:
                row['action'] = f"reviewed {rv_['date']}: {rv_['decision']} ({rv_['by']}: {rv_['note']})"
    dup_courses = {row['a'].split('/')[0] for row in dup_rows if row['type'] != 'similar_course_title'} | {row['b'].split('/')[0] for row in dup_rows if row['type'] != 'similar_course_title'}

    # build records
    R = cfg['rules']
    prof = set(cfg['classification']['professional'])
    course_recs, lesson_recs, project_recs, verify_rows = [], [], [], []
    for c in sorted(courses, key=lambda c: ids['courses'][c['id']]['id']):
        d = data[c['id']]
        cid = ids['courses'][c['id']]['id']
        first, last, sha = dates[c['id']]
        if first and not ids['courses'][c['id']].get('first_published'):
            ids['courses'][c['id']]['first_published'] = first
        L = d.get('lessons', [])
        lessons = [l for l in L if l['type'] == 'lesson']
        projects = [l for l in L if l['type'] in ('project', 'capstone')]
        per_level = {n: len([l for l in lessons if l['level'] == n]) for n in range(1, 5)}
        levels_present = sorted({l['level'] for l in L})
        thin = [l for l in lessons if l['words'] < R['min_lesson_words']]
        broken = [l for l in L if args.check_urls and url_status.get(c['url'] + l['path']) != 200]
        in_sitemap = f"{c['url']}sitemap.xml" in sitemap_index
        checks = {
            'page_accessible': d.get('http_home') == 200,
            'four_levels_present': all(per_level[n] >= R['min_lessons_per_level'] for n in range(1, 5)),
            'syllabus_present': bool(d.get('syllabus')),
            'substantive_content_present': len(lessons) >= R['min_lessons_per_course'] and len(thin) <= R['max_thin_lessons'],
            'lessons_verified': (not broken) if args.check_urls else None,
            'duplicate_check': c['id'] not in dup_courses,
            'publication_verified': in_sitemap and not d.get('noindex') and d.get('ok', False),
            'project_present': len(projects) >= 1,
        }
        reasons = []
        if not d.get('ok'): reasons += d.get('errors', [])
        if not checks['page_accessible']: reasons.append(f"course home returned {d.get('http_home')}")
        if not checks['four_levels_present']: reasons.append('lessons per level ' + ', '.join(f'L{n}={per_level[n]}' for n in range(1, 5)) + f" (min {R['min_lessons_per_level']})")
        if not checks['syllabus_present']: reasons.append('no level links on the course home')
        if not checks['substantive_content_present']: reasons.append(f"{len(lessons)} lessons, {len(thin)} under {R['min_lesson_words']} words")
        if checks['lessons_verified'] is False: reasons.append(f'{len(broken)} lesson URLs did not return 200')
        if not checks['duplicate_check']: reasons.append('duplicate candidate needs human review')
        if not checks['publication_verified']: reasons.append('not in sitemap or marked noindex')
        if not checks['project_present']: reasons.append('no project')
        hard = [k for k in ('page_accessible', 'publication_verified', 'syllabus_present') if not checks[k]]
        eligible = all(v is not False for v in checks.values())
        review = rv.get(c['id'])
        # automated checks alone never make a course "verified": a human content review must be recorded in registry/reviews.json
        # status names: qualified = automated checks + recorded human review; passed_automated_checks = checks only (review still to do);
        # needs_fixes = at least one check failed; rejected = the course is not publicly reachable/indexed
        if eligible:
            status_ = 'qualified' if review else 'passed_automated_checks'
        else:
            status_ = 'rejected' if hard else 'needs_fixes'
        if c['id'] in prof:
            classification = 'professional'
        else:
            classification = 'technology'
        rec = {
            'course_id': cid, 'course_slug': c['id'], 'course_title': c['name'], 'course_description': c.get('desc', ''),
            'course_category_id': c.get('cat'), 'course_category': c.get('catName'), 'course_type': c.get('type'),
            'course_classification': classification, 'classification_note': cfg['classification']['notes'].get(c['id'], ''),
            'course_owner': cfg['owner'], 'course_author': cfg['author'], 'course_url': c['url'],
            'source_repository': 'https://github.com/SIGILIPELLI/' + c['url'].replace(SITE, '').strip('/').split('/')[0],
            'publication_status': 'published' if checks['publication_verified'] else 'unverified',
            'publication_date': ids['courses'][c['id']].get('first_published'),
            'last_content_update': last, 'content_version': sha,
            'last_reviewed_date': review['date'] if review else None, 'last_reviewed_by': review.get('reviewer') if review else None,
            'learning_level_count': len(levels_present), 'level_titles': {str(k): v for k, v in sorted(d.get('level_titles', {}).items())},
            'lesson_count': len(lessons), 'lessons_per_level': {str(k): v for k, v in per_level.items()},
            'project_count': len([p for p in projects if p['type'] == 'project']), 'capstone_count': len([p for p in projects if p['type'] == 'capstone']),
            # exercises are counted on lessons only (a project page's practice sections are reported separately)
            'exercise_count': sum(l['exercises'] for l in lessons), 'lessons_with_exercise': len([l for l in lessons if l['exercises']]),
            'lessons_without_exercise': len([l for l in lessons if not l['exercises']]), 'project_exercise_sections': sum(l['exercises'] for l in projects),
            # quizzes: a module quiz belongs to one page (lesson or project); a final quiz belongs to the course
            'quiz_count': d.get('module_quizzes', 0) + (1 if d.get('final_quiz') else 0),
            'module_quiz_count': d.get('module_quizzes', 0),
            'module_quizzes_on_lessons': len([l for l in lessons if l['path'].rstrip('/') in d.get('quiz_keys', set())]),
            'module_quizzes_on_projects': len([l for l in projects if l['path'].rstrip('/') in d.get('quiz_keys', set())]),
            'module_quiz_questions': d.get('quiz_questions', 0), 'final_quiz': bool(d.get('final_quiz')),
            'final_quiz_questions': d.get('final_questions', 0), 'coding_challenges': d.get('challenges', 0),
            'total_words': sum(l['words'] for l in L),
            'language': 'en', 'access_type': 'free, public', 'registration_required': False, 'payment_required': False,
            'record_eligibility_status': status_, 'record_eligibility_reason': '; '.join(reasons) or 'meets all criteria',
            'checks': checks,
        }
        course_recs.append(rec)
        verify_rows.append({'course_id': cid, 'course_title': c['name'], 'course_url': c['url'],
                            **{k: ('' if v is None else ('yes' if v else 'no')) for k, v in checks.items()},
                            'overall_result': status_, 'failure_reason': '; '.join(reasons)})
        for l in L:
            is_proj = l['type'] != 'lesson'
            k = c['id'] + '|' + l['path']
            if k not in ids['lessons']:
                n = 1 + sum(1 for x in ids['lessons'] if x.startswith(c['id'] + '|'))
                ids['lessons'][k] = f'{cid}-{n:04d}'
            u = c['url'] + l['path']
            (project_recs if is_proj else lesson_recs).append({
                ('project_id' if is_proj else 'lesson_id'): ids['lessons'][k], 'course_id': cid, 'course_title': c['name'], 'level_id': l['level'],
                'level': f"Level {l['level']}", 'module_id': f"{cid}-L{l['level']}-M{l['ordinal']:02d}", 'module': f"Level {l['level']} · module {l['ordinal']:02d}",
                ('project_title' if is_proj else 'lesson_title'): l['title'], ('project_slug' if is_proj else 'lesson_slug'): l['slug'], ('project_url' if is_proj else 'lesson_url'): u, ('project_type' if is_proj else 'lesson_type'): l['type'],
                'content_status': ('published' if (not args.check_urls or url_status.get(u) == 200) else f"http {url_status.get(u)}"),
                'word_count': l['words'], 'exercise_count': l['exercises'],
                **({} if is_proj else {'qualifies_as_lesson': l['words'] >= R['min_lesson_words'] and (not args.check_urls or url_status.get(u) == 200)}),
                'publication_date': rec['publication_date'], 'last_content_update': last, 'last_reviewed_date': rec['last_reviewed_date'],
                'author': cfg['author'], 'assessment_available': l['path'].rstrip('/') in {x.rstrip('/') for x in (load(ROOT / 'learn/quizzes' / f"{c['id']}.json", {}).get('lessons') or {})},
            })

    def tally(recs):
        return {
            'courses': len(recs), 'lessons': sum(r['lesson_count'] for r in recs), 'projects': sum(r['project_count'] for r in recs),
            'capstones': sum(r['capstone_count'] for r in recs), 'exercises': sum(r['exercise_count'] for r in recs),
            'quizzes': sum(r['quiz_count'] for r in recs),
            'module_quizzes': sum(r['module_quiz_count'] for r in recs), 'final_quizzes': sum(1 for r in recs if r['final_quiz']),
            'module_quiz_questions': sum(r['module_quiz_questions'] for r in recs), 'final_quiz_questions': sum(r['final_quiz_questions'] for r in recs),
            'coding_challenges': sum(r['coding_challenges'] for r in recs),
            'lessons_with_exercise': sum(r['lessons_with_exercise'] for r in recs), 'lessons_without_exercise': sum(r['lessons_without_exercise'] for r in recs),
            'project_exercise_sections': sum(r['project_exercise_sections'] for r in recs),
        }
    published = [r for r in course_recs if r['publication_status'] == 'published']
    passed = [r for r in course_recs if r['record_eligibility_status'] in ('qualified', 'passed_automated_checks')]
    qualified = [r for r in course_recs if r['record_eligibility_status'] == 'qualified']
    cats = {}
    for r in published:
        cats.setdefault(r['course_category'], 0); cats[r['course_category']] += 1
    commit = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    summary = {
        'audit_id': 'MPA-' + NOW.strftime('%Y%m%dT%H%MZ'), 'audit_timestamp': NOW.isoformat().replace('+00:00', 'Z'),
        'methodology_version': cfg['methodology_version'], 'repository_commit': commit, 'urls_checked': bool(args.check_urls),
        'registered': tally(course_recs), 'published': tally(published), 'passed_automated_checks': tally(passed), 'qualified': tally(qualified),
        'courses_passing_automated_checks': len(passed),
        'courses_human_reviewed': len(qualified),
        'courses_qualified': len(qualified),
        'courses_needs_fixes': len([r for r in course_recs if r['record_eligibility_status'] == 'needs_fixes']),
        'courses_rejected': len([r for r in course_recs if r['record_eligibility_status'] == 'rejected']),
        'lessons_without_exercise': sum(r['lessons_without_exercise'] for r in course_recs),
        'qualifying_lessons': sum(1 for l in lesson_recs if l['qualifies_as_lesson']),
        'classification': {k: len([r for r in published if r['course_classification'] == k]) for k in ('technology', 'professional')},
        'categories': len(cats), 'category_totals': dict(sorted(cats.items())), 'featured_categories': len(cfg['featured_categories']),
        'learning_paths': len(meta.get('paths', {})), 'learning_levels': 4,
        'first_party_domains': len([w for w in cfg['websites'] if w['first_party_status'] == 'first-party']),
        'failed_urls': sum(1 for v in url_status.values() if v != 200), 'duplicate_candidates': len(dup_rows), 'duplicates_unresolved': len([r for r in dup_rows if r['action'].startswith('review') and not r['action'].startswith('reviewed')]),
        'courses_with_review_record': len([r for r in course_recs if r['last_reviewed_date']]),
        'engagement': {'learners': None, 'completions': None, 'countries': None, 'note': 'Not currently measured as verifiable counts.'},
    }

    # write
    REG.mkdir(exist_ok=True)
    (REG / 'ids.json').write_text(json.dumps(ids, indent=1, sort_keys=True) + '\n')
    (REG / 'courses.json').write_text(json.dumps(course_recs, indent=1, ensure_ascii=False) + '\n')
    (REG / 'lessons.json').write_text(json.dumps(lesson_recs, separators=(',', ':'), ensure_ascii=False) + '\n')   # teaching lessons only
    (REG / 'projects.json').write_text(json.dumps(project_recs, separators=(',', ':'), ensure_ascii=False) + '\n')   # projects and capstones only
    (REG / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
    (REG / 'websites.json').write_text(json.dumps(cfg['websites'], indent=1) + '\n')

    def write_csv(name, rows, fields):
        buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
        (REG / name).write_text(buf.getvalue())
    inv = [dict(r, category=r['course_category'], classification=r['course_classification'], level_count=r['learning_level_count'],
                author=r['course_author'], validation_status=r['record_eligibility_status']) for r in course_recs]
    write_csv('mastery_path_course_inventory.csv', inv, ['course_id', 'course_title', 'category', 'classification', 'course_url', 'publication_status', 'level_count', 'lesson_count', 'project_count', 'capstone_count', 'exercise_count', 'quiz_count', 'author', 'publication_date', 'last_content_update', 'last_reviewed_date', 'record_eligibility_status', 'validation_status'])
    write_csv('mastery_path_lesson_inventory.csv', lesson_recs, ['lesson_id', 'course_id', 'course_title', 'level', 'module', 'lesson_title', 'lesson_url', 'lesson_type', 'content_status', 'word_count', 'exercise_count', 'qualifies_as_lesson', 'publication_date', 'last_content_update', 'last_reviewed_date'])
    write_csv('mastery_path_project_inventory.csv', project_recs, ['project_id', 'course_id', 'course_title', 'level', 'module', 'project_title', 'project_url', 'project_type', 'content_status', 'word_count', 'exercise_count', 'assessment_available', 'publication_date', 'last_content_update', 'last_reviewed_date'])
    gaps = [dict(l) for l in lesson_recs if not l['exercise_count']]
    write_csv('mastery_path_exercise_gaps.csv', gaps, ['lesson_id', 'course_id', 'course_title', 'level', 'lesson_title', 'lesson_url', 'word_count'])
    write_csv('mastery_path_course_verification_report.csv', verify_rows, ['course_id', 'course_title', 'course_url', 'page_accessible', 'four_levels_present', 'syllabus_present', 'substantive_content_present', 'lessons_verified', 'duplicate_check', 'publication_verified', 'project_present', 'overall_result', 'failure_reason'])
    write_csv('mastery_path_duplicate_candidates.csv', dup_rows, ['type', 'a', 'b', 'score', 'action'])
    (REG / 'mastery_path_audit_summary.json').write_text(json.dumps(summary, indent=1) + '\n')

    # evidence register with SHA-256 of each artefact
    arte = ['mastery_path_course_inventory.csv', 'mastery_path_lesson_inventory.csv', 'mastery_path_project_inventory.csv', 'mastery_path_exercise_gaps.csv', 'mastery_path_course_verification_report.csv', 'mastery_path_duplicate_candidates.csv', 'mastery_path_audit_summary.json', 'courses.json', 'lessons.json', 'projects.json', 'summary.json', 'config.json', 'ids.json']
    ev = []
    for i, name in enumerate(arte, 1):
        h = hashlib.sha256((REG / name).read_bytes()).hexdigest()
        ev.append({'evidence_id': f"{summary['audit_id']}-E{i:02d}", 'evidence_type': 'audit artefact', 'related_course_id': 'ALL',
                   'file': f'registry/{name}', 'collected_at': summary['audit_timestamp'], 'collector': 'tools/registry/build_registry.py (automated)',
                   'verification_status': 'generated by script; not independently verified', 'description': name, 'sha256': h})
    write_csv('mastery_path_evidence_register.csv', ev, list(ev[0].keys()))
    (REG / 'SHA256SUMS').write_text(''.join(f"{e['sha256']}  {e['file'].split('/')[-1]}\n" for e in ev))
    if args.archive:
        dest = REG / 'audits' / summary['audit_id']
        dest.mkdir(parents=True, exist_ok=True)
        for name in arte + ['mastery_path_evidence_register.csv', 'SHA256SUMS']:
            (dest / name).write_bytes((REG / name).read_bytes())
    hist = []
    for d in sorted((REG / 'audits').glob('MPA-*')) if (REG / 'audits').exists() else []:
        try:
            a = json.loads((d / 'summary.json').read_text())
            hist.append({'audit_id': a['audit_id'], 'audit_timestamp': a['audit_timestamp'], 'courses': a['published']['courses'], 'lessons': a['published']['lessons'], 'folder': f'registry/audits/{d.name}/'})
        except Exception:
            continue
    if hist:
        (REG / 'audits' / 'index.json').write_text(json.dumps(hist[::-1], indent=1) + '\n')

    p, e = summary['published'], summary['passed_automated_checks']
    print(f"{summary['audit_id']}: registered {summary['registered']['courses']}, published {p['courses']} courses / {p['lessons']} lessons / {p['projects']} projects / {p['capstones']} capstones, "
          f"passed automated checks {e['courses']}, qualified (human-reviewed) {summary['courses_qualified']}, needs fixes {summary['courses_needs_fixes']}, rejected {summary['courses_rejected']}, duplicates {len(dup_rows)} ({summary['duplicates_unresolved']} unresolved), failed URLs {summary['failed_urls']}")


if __name__ == '__main__':
    main()
