#!/usr/bin/env python3
"""Data-integrity tests for the course registry. Run after build_registry.py: python3 tools/registry/test_registry.py"""
import re, csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REG = Path(__file__).resolve().parents[2] / 'registry'
fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


courses = json.loads((REG / 'courses.json').read_text())
lessons = json.loads((REG / 'lessons.json').read_text())      # teaching lessons only
projects = json.loads((REG / 'projects.json').read_text())    # projects and capstones only
summary = json.loads((REG / 'summary.json').read_text())
ids = json.loads((REG / 'ids.json').read_text())
cfg = json.loads((REG / 'config.json').read_text())

# unique, stable IDs
cid = Counter(c['course_id'] for c in courses)
check(all(v == 1 for v in cid.values()), f'duplicate course IDs: {[k for k, v in cid.items() if v > 1]}')
check(len({c['course_slug'] for c in courses}) == len(courses), 'duplicate course slugs')
check(len({c['course_url'].rstrip('/').lower() for c in courses}) == len(courses), 'duplicate course URLs after normalisation')
check(all(l['lesson_type'] == 'lesson' for l in lessons), 'lessons.json must contain lessons only')
check(all(p['project_type'] in ('project', 'capstone') for p in projects), 'projects.json must contain projects and capstones only')
check(not ({l['lesson_url'] for l in lessons} & {p['project_url'] for p in projects}), 'a page is in both the lesson and the project inventory')
lid = Counter(l['lesson_id'] for l in lessons + [dict(lesson_id=p['project_id']) for p in projects])
check(all(v == 1 for v in lid.values()), f'duplicate lesson IDs: {[k for k, v in lid.items() if v > 1][:5]}')
check(len({l['lesson_url'] for l in lessons}) == len(lessons), 'a lesson URL appears twice')
for c in courses:
    check(ids['courses'][c['course_slug']]['id'] == c['course_id'], f"{c['course_slug']}: ID differs from ids.json")
for l in lessons:
    check(l['lesson_id'].startswith(l['course_id'] + '-'), f"{l['lesson_id']} not under its course {l['course_id']}")

# every lesson belongs to exactly one known course and one level 1-4
known = {c['course_id'] for c in courses}
check(all(l['course_id'] in known for l in lessons), 'lesson with unknown course')
check(all(l['level_id'] in (1, 2, 3, 4) for l in lessons), 'lesson outside levels 1-4')

# per-course counts equal the records; projects are never lessons
by = {}
for l in lessons:
    by.setdefault(l['course_id'], Counter())['lesson'] += 1
    by[l['course_id']]['ex'] += l['exercise_count']
    by[l['course_id']]['noex'] += 0 if l['exercise_count'] else 1
for p in projects:
    by.setdefault(p['course_id'], Counter())[p['project_type']] += 1
PAGE = re.compile(r'^\d+-(project|capstone)\b')
LESSON_EXCEPTIONS = {
    (c['course_id'], slug)
    for c in courses
    for slug in cfg.get('rules', {}).get('lesson_slug_exceptions', {}).get(c['course_slug'], [])
}
check(all(any((l['course_id'], l['lesson_slug']) == item for l in lessons) for item in LESSON_EXCEPTIONS), 'every configured lesson slug exception must appear in lessons.json')
check(not any((p['course_id'], p['project_slug']) in LESSON_EXCEPTIONS for p in projects), 'a configured lesson exception appears in projects.json')
learn_js = (REG.parent / 'assets' / 'learn.js').read_text()
check(all(slug in learn_js for _, slug in LESSON_EXCEPTIONS), 'frontend must respect every configured teaching-lesson exception')
for c in courses:
    t = by.get(c['course_id'], Counter())
    check(c['lesson_count'] == t['lesson'], f"{c['course_id']}: lesson_count {c['lesson_count']} != {t['lesson']} lesson records")
    check(c['project_count'] == t['project'], f"{c['course_id']}: project_count mismatch")
    check(c['capstone_count'] == t['capstone'] == 1, f"{c['course_id']}: needs exactly one capstone, has {t['capstone']}")
    check(sum(c['lessons_per_level'].values()) == c['lesson_count'], f"{c['course_id']}: level totals != lesson_count")
    check(c['exercise_count'] == t['ex'] and c['lessons_without_exercise'] == t['noex'], f"{c['course_id']}: exercise counts differ from the lesson records")
    check(c['lessons_with_exercise'] + c['lessons_without_exercise'] == c['lesson_count'], f"{c['course_id']}: exercise coverage does not add up")
    check(c['module_quizzes_on_lessons'] + c['module_quizzes_on_projects'] == c['module_quiz_count'], f"{c['course_id']}: quiz split {c['module_quizzes_on_lessons']}+{c['module_quizzes_on_projects']} != module quizzes {c['module_quiz_count']} (a quiz is attached to no page, or to two)")
    check(c['quiz_count'] == c['module_quiz_count'] + (1 if c['final_quiz'] else 0), f"{c['course_id']}: quiz_count is not module + final")
    check(c['course_classification'] in ('technology', 'professional'), f"{c['course_id']}: bad classification")
    check(c['record_eligibility_status'] in ('qualified', 'passed_automated_checks', 'needs_fixes', 'rejected'), f"{c['course_id']}: unknown status {c['record_eligibility_status']}")
    check((c['record_eligibility_status'] == 'qualified') == bool(c['last_reviewed_date']) or c['record_eligibility_status'] in ('needs_fixes', 'rejected'),
          f"{c['course_id']}: 'qualified' needs a recorded human review, and a recorded review needs 'qualified'")
check(all((p['project_type'] == 'capstone') == (p['level_id'] == 4 and re.match(r'^\d+-capstone\b', p['project_slug']) is not None) for p in projects), 'capstone = Level 4 page named NN-capstone-…, nothing else')
check(all(PAGE.match(p['project_slug']) for p in projects), 'a project page is not named NN-project-/NN-capstone-')
check(not any(PAGE.match(l['lesson_slug']) and (l['course_id'], l['lesson_slug']) not in LESSON_EXCEPTIONS for l in lessons), 'a lesson is named like a project without an explicit course-specific exception')

# summary equals the records
pub = [c for c in courses if c['publication_status'] == 'published']
check(summary['published']['courses'] == len(pub), 'summary course total')
check(summary['published']['lessons'] == sum(c['lesson_count'] for c in pub), 'summary lesson total')
check(summary['published']['projects'] == sum(c['project_count'] for c in pub), 'summary project total')
check(summary['published']['capstones'] == sum(c['capstone_count'] for c in pub), 'summary capstone total')
check(summary['published']['lessons'] == len(lessons) and summary['published']['projects'] + summary['published']['capstones'] == len(projects), 'summary totals must equal the two inventories')
check(summary['published']['lessons_without_exercise'] == summary['lessons_without_exercise'] == len(list(csv.DictReader((REG / 'mastery_path_exercise_gaps.csv').open()))), 'exercise gap list must match the summary')
check(summary['published']['quizzes'] == summary['published']['module_quizzes'] + summary['published']['final_quizzes'], 'quizzes must equal module + final')
check(summary['courses_qualified'] == len([c for c in courses if c['record_eligibility_status'] == 'qualified']), 'qualified total')
check(summary['courses_passing_automated_checks'] == len([c for c in courses if c['record_eligibility_status'] in ('qualified', 'passed_automated_checks')]), 'automated-check total')
check(summary['failed_urls'] == 0 or not summary['urls_checked'] or summary['courses_needs_fixes'] > 0, 'failed URLs must show up as needs_fixes')
check(summary['categories'] == len({c['course_category'] for c in pub}), 'summary category total')
check(summary['classification']['technology'] + summary['classification']['professional'] == len(pub), 'classification totals')
check(set(cfg['classification']['professional']) <= {c['course_slug'] for c in courses}, 'classification list names an unknown course')
check(summary['duplicates_unresolved'] == 0, f"{summary['duplicates_unresolved']} duplicate candidates are unresolved")
check(summary['engagement']['learners'] is None, 'engagement metrics must stay null until measured')

# CSVs parse and agree; checksums match
for name, n in (('mastery_path_course_inventory.csv', len(courses)), ('mastery_path_lesson_inventory.csv', len(lessons)), ('mastery_path_project_inventory.csv', len(projects)), ('mastery_path_course_verification_report.csv', len(courses))):
    rows = list(csv.DictReader((REG / name).open()))
    check(len(rows) == n, f'{name}: {len(rows)} rows, expected {n}')
for line in (REG / 'SHA256SUMS').read_text().splitlines():
    h, name = line.split('  ')
    check(hashlib.sha256((REG / name).read_bytes()).hexdigest() == h, f'checksum mismatch: {name}')

# registry-driven pages carry the same audit id and numbers as summary.json (guards against a page left behind by a failed rebuild)
ROOT = REG.parent
sid = summary['audit_id']
for page in ('learning-impact/index.html', 'quality-and-verification/index.html', 'world-record-attempt/index.html', 'course-catalogue/index.html'):
    text = (ROOT / page).read_text()
    ids_on_page = set(re.findall(r'MPA-\d{8}T\d{4}Z', text))
    check(ids_on_page <= {sid}, f'{page}: shows audit {sorted(ids_on_page)}, latest is {sid}')
for page in ('index.html', 'about.html'):
    text = (ROOT / page).read_text()
    for key, want in (('courses', summary['published']['courses']), ('lessons', summary['published']['lessons']), ('projects', summary['published']['projects']), ('capstones', summary['published']['capstones'])):
        for got in re.findall(r'data-mp-stat="%s">([\d,]+)' % key, text):
            check(int(got.replace(',', '')) == want, f'{page}: {key} shows {got}, registry says {want}')

# ---- exact quiz reconciliation: records <-> course facts <-> the quiz banks themselves -------------------------------
ROOT_ = Path(__file__).resolve().parents[2]
lesson_q, project_q = Counter(), Counter()
for l in lessons: lesson_q[l['course_id']] += 1 if l['assessment_available'] else 0
for p in projects: project_q[p['course_id']] += 1 if p['assessment_available'] else 0
for c in courses:
    cid = c['course_id']
    check(lesson_q[cid] == c['module_quizzes_on_lessons'], f"{cid}: lessons flagged with a quiz {lesson_q[cid]} != {c['module_quizzes_on_lessons']}")
    check(project_q[cid] == c['module_quizzes_on_projects'], f"{cid}: projects flagged with a quiz {project_q[cid]} != {c['module_quizzes_on_projects']}")
    qf = ROOT_ / 'learn' / 'quizzes' / (c['course_slug'] + '.json')
    check(qf.exists(), f"{cid}: quiz bank {qf.name} missing")
    if qf.exists():
        qd = json.loads(qf.read_text()); ql = qd.get('lessons') or {}; fin = qd.get('final') or {}
        check(len(ql) == c['module_quiz_count'], f"{cid}: quiz bank has {len(ql)} module quizzes, registry {c['module_quiz_count']}")
        check(sum(len(v.get('questions', [])) for v in ql.values()) == c['module_quiz_questions'], f"{cid}: module quiz questions differ from the quiz bank")
        check(len(fin.get('questions', [])) == c['final_quiz_questions'], f"{cid}: final quiz questions differ from the quiz bank")
        check(len(fin.get('challenges', [])) == c['coding_challenges'], f"{cid}: coding challenges differ from the quiz bank")
        check(bool(fin.get('questions')) == bool(c['final_quiz']), f"{cid}: final_quiz flag disagrees with the quiz bank")
        check(c['quiz_count'] == len(ql) + (1 if fin.get('questions') else 0), f"{cid}: quiz_count != module quizzes + final quiz in the bank")
P_ = summary['published']
for k, f in (('module_quizzes', 'module_quiz_count'), ('module_quiz_questions', 'module_quiz_questions'), ('final_quiz_questions', 'final_quiz_questions'), ('coding_challenges', 'coding_challenges'), ('quizzes', 'quiz_count')):
    check(P_[k] == sum(c[f] for c in courses if c['publication_status'] == 'published'), f'summary {k} != sum of course records')
check(P_['final_quizzes'] == sum(1 for c in courses if c['publication_status'] == 'published' and c['final_quiz']), 'summary final_quizzes != courses with a final quiz')

# ---- course descriptions: any count they state must be the course's own registry count --------------------------------
for c in courses:
    d = c['course_description']
    for m in re.finditer(r'\b(\d+) (?:hands-on |real )?lessons\b', d):
        check(int(m.group(1)) == c['lesson_count'], f"{c['course_slug']}: description says {m.group(0)}, registry {c['lesson_count']}")
    for m in re.finditer(r'\b(\d+) (?:hands-on |real )?projects\b', d):
        check(int(m.group(1)) == c['project_count'] and 'capstone' in d, f"{c['course_slug']}: description says {m.group(0)}; registry has {c['project_count']} projects + {c['capstone_count']} capstone, stated separately")
    for m in re.finditer(r'\b(\d+) capstones?\b', d):
        check(int(m.group(1)) == c['capstone_count'], f"{c['course_slug']}: description says {m.group(0)}")
sc = json.loads((ROOT_ / 'search' / 'courses.json').read_text())
sc = sc.get('courses', sc) if isinstance(sc, dict) else sc
reg = {c['course_slug']: c for c in courses}
for x in sc:
    r = reg.get(x['id'])
    if r:
        check((x['lessons'], x['projects'], x.get('capstones')) == (r['lesson_count'], r['project_count'], r['capstone_count']), f"search index counts for {x['id']} differ from the registry")
        check(x['desc'] == r['course_description'] or not re.search(r'\d+ (?:hands-on )?lessons', x['desc']), f"search description for {x['id']} states counts that differ from the registry description")

# ---- every public hub page carries the current audit id, and nothing else ----------------------------------------------
ALL_PAGES = ['404.html', 'about.html', 'contact.html', 'delivery.html', 'index.html', 'license.html', 'privacy.html', 'refunds.html', 'terms.html',
             'course-catalogue/index.html', 'interview-pack/index.html', 'interview-questions/index.html', 'learning-impact/index.html',
             'quality-and-verification/index.html', 'resume/index.html', 'search/index.html', 'verify/index.html', 'world-record-attempt/index.html']
for page in ALL_PAGES:
    text = (ROOT_ / page).read_text()
    check(re.findall(r'<meta name="mp-audit-id" content="([^"]+)"', text) == [summary['audit_id']], f'{page}: audit meta tag missing or not {summary["audit_id"]}')
    check(set(re.findall(r'MPA-\d{8}T\d{4}Z', text)) == {summary['audit_id']}, f'{page}: visible audit ids differ from {summary["audit_id"]}')
    check('data-mp-audit-stamp' in text, f'{page}: no visible audit stamp')
prov = summary.get('provenance', {})
for k in ('source_commit', 'audit_tool_commit', 'audit_tool_sha256', 'config_sha256', 'run_mode', 'url_check_method'):
    check(bool(prov.get(k)), f'provenance.{k} missing')
check(prov.get('url_check_method') == 'GET', 'lesson URLs must be checked with GET')
check(summary['methodology_version'] == json.loads((REG / 'config.json').read_text())['methodology_version'], 'summary methodology version differs from config.json')
check(summary['repository_commit'] == prov.get('source_commit'), 'repository_commit != provenance.source_commit')

# ---- owner name, domain count, URL verification, source ownership ------------------------------------------------------------------
cfg_ = json.loads((REG / 'config.json').read_text())
check(cfg_['author'] == 'Vinod Kumar Sigilipelli' and cfg_['owner'].startswith('Vinod Kumar Sigilipelli'), 'owner/author must be Vinod Kumar Sigilipelli')
check(all(c['course_author'] == 'Vinod Kumar Sigilipelli' and c['course_owner'].startswith('Vinod Kumar Sigilipelli') for c in courses), 'every course record must name Vinod Kumar Sigilipelli')
for page in ALL_PAGES + ['registry/ai-review-register.json']:
    check('Bhanuja' not in (ROOT_ / page).read_text(), f'{page}: old creator name still present')
check(summary['first_party_domains'] == 1 and summary['first_party_hostnames'] == len(summary['first_party_hostname_list']) == 2, 'domain count: expected 1 registered domain and 2 first-party hostnames')
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_registry as BR
exp = {'id': 'mcp-mastery-path', 'course_url': 'https://learnmasterypath.com/python-mastery-path/mcp-mastery-path/', 'path': 'level-1/01-x/'}
good = '<title>x</title><script id="mp-course-meta">{"id":"mcp-mastery-path","url":"https://learnmasterypath.com/python-mastery-path/mcp-mastery-path/","src":"level-1/01-x/index.md"}</script>'
U = exp['course_url'] + 'level-1/01-x/'
check(BR.verify_body(U, U, 'text/html', good, exp) == 200, 'verify_body rejects a correct page')
check(BR.verify_body(U, U + 'other/', 'text/html', good, exp) == 1001, 'verify_body accepts a redirect')
check(BR.verify_body(U, U, 'application/json', good, exp) == 1002, 'verify_body accepts non-HTML')
check(BR.verify_body(U, U, 'text/html', '<body class="mp-404">', exp) == 1003, 'verify_body accepts a soft 404')
check(BR.verify_body(U, U, 'text/html', good.replace('"mcp-mastery-path","url"', '"python-mastery-path","url"'), exp) == 1004, 'verify_body accepts another course\'s page')
check(BR.verify_body(U, U, 'text/html', good.replace('level-1/01-x/index.md', 'level-2/02-y/index.md'), exp) == 1005, 'verify_body accepts the wrong lesson')
own = json.loads((REG / 'ethical-hacking-source-ownership.json').read_text())
check(own['owner_login'] == 'SIGILIPELLI' and own['default_branch'] == 'main' and own['history']['git_author_names_explained'] and own['history']['ai_assistance'] and 'owner_confirmation' in own and not any('@' in str(x) for x in json.dumps(own).split('"')) and not own['is_fork'] and own['source_tree']['http_status'] == 200, 'ethical hacking source-ownership evidence incomplete')

# ---- course cards: the lesson-count identifier must be the card's own course (nested MCP/Vector cards are not Python) ----
slugs_ = {c['course_slug']: c for c in courses}
for page in ('index.html', 'about.html', 'course-catalogue/index.html'):
    text = (ROOT_ / page).read_text()
    for m in re.finditer(r'<li><a href="https://learnmasterypath\.com/([^"]+?)/?">(?:(?!</li>).)*?data-mp-lessons="([^"]+)"', text, re.S):
        check(m.group(1).split('/')[-1] == m.group(2), f'{page}: card for {m.group(1)} uses lesson-count identifier {m.group(2)}')
        check(m.group(2) in slugs_, f'{page}: identifier {m.group(2)} is not a course record')
for slug in ('mcp-mastery-path', 'vector-databases-mastery-path'):
    check(re.search(r'data-mp-lessons="%s">%d lessons' % (slug, slugs_[slug]['lesson_count']), (ROOT_ / 'index.html').read_text()) is not None, f'index.html: {slug} card does not show its own lesson count')

print(f"{len(courses)} courses, {len(lessons)} lessons + {len(projects)} projects: {'OK' if not fails else str(len(fails)) + ' failures'}")
for f in fails[:30]:
    print('  FAIL', f)
sys.exit(1 if fails else 0)
