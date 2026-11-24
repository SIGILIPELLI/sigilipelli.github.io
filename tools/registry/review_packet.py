#!/usr/bin/env python3
"""Writes registry/review-packet.csv: one row per course for the HUMAN reviewer.

It records nothing in reviews.json. A reviewer reads the sample pages, fills the check columns and, only then, adds an entry to
registry/reviews.json (course_slug, reviewer, date, notes). Sample pages are chosen deterministically: the first lesson of each
level plus the capstone, so every reviewer sees the same pages."""
import csv, json
from pathlib import Path
REG = Path(__file__).resolve().parents[2] / 'registry'
courses = json.loads((REG / 'courses.json').read_text())
lessons = json.loads((REG / 'lessons.json').read_text())
by = {}
for l in lessons:
    by.setdefault(l['course_id'], []).append(l)
cols = ['course_slug', 'course_title', 'course_url', 'lessons', 'projects_and_capstones', 'module_quizzes', 'final_quiz', 'automated_status',
        'sample_page_1', 'sample_page_2', 'sample_page_3', 'sample_page_4', 'sample_capstone',
        'accurate_and_current (Y/N)', 'examples_run_or_checked (Y/N)', 'original_not_copied (Y/N)', 'ai_assistance_disclosed_ok (Y/N)',
        'reviewer', 'date', 'notes']
rows = []
for c in courses:
    ls = sorted(by[c['course_id']], key=lambda l: (l['level_id'], l['lesson_slug']))
    first = {}
    for l in ls:
        if l['lesson_type'] == 'lesson':
            first.setdefault(l['level_id'], l['lesson_url'])
    cap = next((l['lesson_url'] for l in ls if l['lesson_type'] == 'capstone'), '')
    row = {k: '' for k in cols}
    row.update(course_slug=c['course_slug'], course_title=c['course_title'], course_url=c['course_url'], lessons=c['lesson_count'],
               projects_and_capstones=c['project_count'] + c['capstone_count'], module_quizzes=c['module_quiz_count'],
               final_quiz='yes' if c['final_quiz'] else 'no', automated_status=c['record_eligibility_status'], sample_capstone=cap)
    for i in range(1, 5):
        row[f'sample_page_{i}'] = first.get(i, '')
    rows.append(row)
with (REG / 'review-packet.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
print(f'{len(rows)} courses -> registry/review-packet.csv (no review recorded)')
