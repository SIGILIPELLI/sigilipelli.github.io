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
for c in courses:
    t = by.get(c['course_id'], Counter())
    check(c['lesson_count'] == t['lesson'], f"{c['course_id']}: lesson_count {c['lesson_count']} != {t['lesson']} lesson records")
    check(c['project_count'] == t['project'], f"{c['course_id']}: project_count mismatch")
    check(c['capstone_count'] == t['capstone'] and t['capstone'] <= 1, f"{c['course_id']}: capstone count {t['capstone']}")
    check(sum(c['lessons_per_level'].values()) == c['lesson_count'], f"{c['course_id']}: level totals != lesson_count")
    check(c['exercise_count'] == t['ex'] and c['lessons_without_exercise'] == t['noex'], f"{c['course_id']}: exercise counts differ from the lesson records")
    check(c['lessons_with_exercise'] + c['lessons_without_exercise'] == c['lesson_count'], f"{c['course_id']}: exercise coverage does not add up")
    check(c['module_quizzes_on_lessons'] + c['module_quizzes_on_projects'] <= c['module_quiz_count'], f"{c['course_id']}: quiz split exceeds quiz total")
    check(c['quiz_count'] == c['module_quiz_count'] + (1 if c['final_quiz'] else 0), f"{c['course_id']}: quiz_count is not module + final")
    check(c['course_classification'] in ('technology', 'professional'), f"{c['course_id']}: bad classification")
    check(c['record_eligibility_status'] in ('qualified', 'passed_automated_checks', 'needs_fixes', 'rejected'), f"{c['course_id']}: unknown status {c['record_eligibility_status']}")
    check((c['record_eligibility_status'] == 'qualified') == bool(c['last_reviewed_date']) or c['record_eligibility_status'] in ('needs_fixes', 'rejected'),
          f"{c['course_id']}: 'qualified' needs a recorded human review, and a recorded review needs 'qualified'")
check(all(PAGE.match(p['project_slug']) for p in projects), 'a project page is not named NN-project-/NN-capstone-')
check(not any(PAGE.match(l['lesson_slug']) for l in lessons), 'a lesson is named like a project')

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
    for key, want in (('courses', summary['published']['courses']), ('lessons', summary['published']['lessons']), ('projects', summary['published']['projects'] + summary['published']['capstones'])):
        for got in re.findall(r'data-mp-stat="%s">([\d,]+)' % key, text):
            check(int(got.replace(',', '')) == want, f'{page}: {key} shows {got}, registry says {want}')

print(f"{len(courses)} courses, {len(lessons)} lessons + {len(projects)} projects: {'OK' if not fails else str(len(fails)) + ' failures'}")
for f in fails[:30]:
    print('  FAIL', f)
sys.exit(1 if fails else 0)
