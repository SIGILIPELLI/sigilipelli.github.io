#!/usr/bin/env python3
"""Data-integrity tests for the course registry. Run after build_registry.py: python3 tools/registry/test_registry.py"""
import csv
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
lessons = json.loads((REG / 'lessons.json').read_text())
summary = json.loads((REG / 'summary.json').read_text())
ids = json.loads((REG / 'ids.json').read_text())
cfg = json.loads((REG / 'config.json').read_text())

# unique, stable IDs
cid = Counter(c['course_id'] for c in courses)
check(all(v == 1 for v in cid.values()), f'duplicate course IDs: {[k for k, v in cid.items() if v > 1]}')
check(len({c['course_slug'] for c in courses}) == len(courses), 'duplicate course slugs')
check(len({c['course_url'].rstrip('/').lower() for c in courses}) == len(courses), 'duplicate course URLs after normalisation')
lid = Counter(l['lesson_id'] for l in lessons)
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

# per-course counts equal the lesson records; projects are never lessons
by = {}
for l in lessons:
    by.setdefault(l['course_id'], Counter())[l['lesson_type']] += 1
for c in courses:
    t = by.get(c['course_id'], Counter())
    check(c['lesson_count'] == t['lesson'], f"{c['course_id']}: lesson_count {c['lesson_count']} != {t['lesson']} lesson records")
    check(c['project_count'] == t['project'], f"{c['course_id']}: project_count mismatch")
    check(c['capstone_count'] == t['capstone'] and t['capstone'] <= 1, f"{c['course_id']}: capstone count {t['capstone']}")
    check(sum(c['lessons_per_level'].values()) == c['lesson_count'], f"{c['course_id']}: level totals != lesson_count")
    check(c['course_classification'] in ('technology', 'professional'), f"{c['course_id']}: bad classification")
    if c['record_eligibility_status'] == 'eligible':
        check(bool(c['last_reviewed_date']), f"{c['course_id']}: 'eligible' without a recorded human review")

# summary equals the records
pub = [c for c in courses if c['publication_status'] == 'published']
check(summary['published']['courses'] == len(pub), 'summary course total')
check(summary['published']['lessons'] == sum(c['lesson_count'] for c in pub), 'summary lesson total')
check(summary['published']['projects'] == sum(c['project_count'] for c in pub), 'summary project total')
check(summary['categories'] == len({c['course_category'] for c in pub}), 'summary category total')
check(summary['classification']['technology'] + summary['classification']['professional'] == len(pub), 'classification totals')
check(set(cfg['classification']['professional']) <= {c['course_slug'] for c in courses}, 'classification list names an unknown course')
check(summary['engagement']['learners'] is None, 'engagement metrics must stay null until measured')

# CSVs parse and agree; checksums match
for name, n in (('mastery_path_course_inventory.csv', len(courses)), ('mastery_path_lesson_inventory.csv', len(lessons)), ('mastery_path_course_verification_report.csv', len(courses))):
    rows = list(csv.DictReader((REG / name).open()))
    check(len(rows) == n, f'{name}: {len(rows)} rows, expected {n}')
for line in (REG / 'SHA256SUMS').read_text().splitlines():
    h, name = line.split('  ')
    check(hashlib.sha256((REG / name).read_bytes()).hexdigest() == h, f'checksum mismatch: {name}')

print(f"{len(courses)} courses, {len(lessons)} lesson records: {'OK' if not fails else str(len(fails)) + ' failures'}")
for f in fails[:30]:
    print('  FAIL', f)
sys.exit(1 if fails else 0)
