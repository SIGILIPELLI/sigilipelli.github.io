#!/usr/bin/env python3
"""Builds the registry-driven pages and puts registry numbers into existing pages.

Usage: python3 tools/registry/build_pages.py   (after build_registry.py)
Writes: course-catalogue/, quality-and-verification/, learning-impact/, world-record-attempt/, about/ (redirect),
        registry/course-facts.json (used by assets/learn.js on course pages)
Updates in place: elements marked data-mp-stat="<key>" and course cards' lesson counts in index.html, about.html,
        search/index.html; the hub sitemap. Then applies the shared header/footer (tools/site_chrome.py).
Every number shown comes from registry/summary.json or registry/courses.json; nothing is typed by hand.
"""
import datetime as dt
import html
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / 'registry'
S = json.loads((REG / 'summary.json').read_text())
C = json.loads((REG / 'courses.json').read_text())
CFG = json.loads((REG / 'config.json').read_text())
WEB = json.loads((REG / 'websites.json').read_text())
RECORD = json.loads((REG / 'record.json').read_text())
E = html.escape
HUB = 'https://learnmasterypath.com/'
P = S['published']
STAMP = dt.datetime.fromisoformat(S['audit_timestamp'].replace('Z', '+00:00')).strftime('%d %B %Y, %H:%M UTC')
DAY = S['audit_timestamp'][:10]


def n(x):
    return f'{x:,}'


def lessons_label(c):
    extra = c['project_count'] + c['capstone_count']
    return f"{c['lesson_count']} lessons + {extra} projects"


STATS = {
    'courses': n(P['courses']), 'lessons': n(P['lessons']), 'projects': n(P['projects'] + P['capstones']),
    'categories': n(S['categories']), 'featured_categories': n(S['featured_categories']), 'paths': n(S['learning_paths']),
    'exercises': n(P['exercises']), 'quizzes': n(P['quizzes']), 'technology': n(S['classification']['technology']),
    'professional': n(S['classification']['professional']), 'updated': STAMP, 'updated_day': DAY,
}


def page(path, title, desc, crumb, body, style='', extra_head=''):
    url = HUB + path
    ld = json.dumps({'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': 'Mastery Path', 'item': HUB},
        {'@type': 'ListItem', 'position': 2, 'name': crumb, 'item': url}]})
    doc = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{url}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-05VBGCXN12"></script>
<script>window.dataLayer = window.dataLayer || []; function gtag(){{dataLayer.push(arguments);}} gtag('js', new Date()); gtag('config', 'G-05VBGCXN12');</script>
<meta property="og:type" content="website"><meta property="og:site_name" content="Mastery Path">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{url}"><meta property="og:image" content="https://learnmasterypath.com/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">{ld}</script>
{extra_head}<style>
.kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(140px, 100%), 1fr)); gap: 12px; margin: 0 0 8px; }}
.kpi {{ background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 16px; box-shadow: var(--shadow-sm); }}
.kpi b {{ display: block; font-size: 1.7rem; font-weight: 800; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }}
.kpi span {{ color: var(--sub); font-size: .88rem; }}
.stamp {{ color: var(--sub); font-size: .86rem; margin: 6px 0 0; }}
.pill {{ display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: .74rem; font-weight: 700; background: var(--surface-2); color: var(--sub); }}
.pill.ok {{ background: var(--brand-soft); color: var(--brand); }}
.pill.wait {{ background: var(--amber-soft); color: var(--ink); }}
.grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
@media (max-width: 760px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}
{style}
</style>
</head>
<body>
<main id="content">
<section class="page-hero"><div class="container">
  <nav aria-label="Breadcrumb" class="crumbs"><a href="{HUB}">Mastery Path</a> › <span aria-current="page">{E(crumb)}</span></nav>
  {body[0]}
</div></section>
<div class="container page-body">
{body[1]}
</div>
</main>
</body>
</html>
'''
    out = ROOT / path / 'index.html'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc)


def kpi(v, label):
    return f'<div class="kpi"><b>{v}</b><span>{E(label)}</span></div>'


# ------------------------------------------------------------------ course catalogue
def catalogue():
    cats = sorted({(c['course_category_id'], c['course_category']) for c in C}, key=lambda x: x[1])
    rows = []
    for c in sorted(C, key=lambda c: c['course_title'].lower()):
        rows.append(f'''<article class="cat-card" data-title="{E(c['course_title'].lower())}" data-text="{E((c['course_title'] + ' ' + c['course_description'] + ' ' + (c['course_type'] or '') + ' ' + c['course_category']).lower())}" data-cat="{E(c['course_category_id'])}" data-class="{c['course_classification']}" data-pub="{c['publication_date'] or ''}" data-upd="{c['last_content_update'] or ''}" data-rev="{c['last_reviewed_date'] or ''}">
  <div class="cc-head"><span class="pill">{E(c['course_id'])}</span><span class="pill {'ok' if c['course_classification'] == 'technology' else 'wait'}">{'Technology' if c['course_classification'] == 'technology' else 'Professional development'}</span></div>
  <h2><a href="{E(c['course_url'])}">{E(c['course_title'])}</a></h2>
  <p class="cc-desc">{E(c['course_description'].replace(' -- ', ' – '))}</p>
  <ul class="cc-facts"><li><b>{c['lesson_count']}</b> lessons</li><li><b>{c['project_count'] + c['capstone_count']}</b> projects</li><li><b>{c['quiz_count']}</b> quizzes</li><li><b>4</b> levels</li></ul>
  <p class="cc-meta">{E(c['course_category'])} · Free, no sign-up · {E(c['course_author'])}<br>Published {E(c['publication_date'] or 'not recorded')} · Updated {E(c['last_content_update'] or '—')} · {('Reviewed ' + E(c['last_reviewed_date'])) if c['last_reviewed_date'] else 'Human review pending'}</p>
  <p class="cc-levels">{''.join(f'<a href="{E(c["course_url"])}level-{k}/" data-level="{k}">L{k} · {E(re.sub(r"^Level \d+\s*·\s*", "", v))}</a>' for k, v in c['level_titles'].items())}</p>
</article>''')
    style = '''
.cat-tools { display: grid; grid-template-columns: 2fr repeat(4, 1fr); gap: 10px; margin: 0 0 14px; }
.cat-tools > :not(.sr-only) { min-width: 0; width: 100%; }
.cat-tools input, .cat-tools select { min-height: 46px; padding: 0 12px; border: 1.5px solid var(--line); border-radius: 12px; background: var(--surface); color: var(--ink); font: 500 .95rem var(--font); }
.cat-tools input:focus, .cat-tools select:focus { outline: none; border-color: var(--brand); box-shadow: 0 0 0 4px color-mix(in srgb, var(--brand) 22%, transparent); }
.cat-count { color: var(--sub); margin: 0 0 14px; font-size: .92rem; }
.cat-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(330px, 100%), 1fr)); gap: 14px; }
.cat-card[hidden] { display: none !important; }
.cat-card { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 18px; box-shadow: var(--shadow-sm); display: flex; flex-direction: column; }
.cat-card h2 { font-size: 1.12rem; margin: 10px 0 6px; } .cat-card h2 a { color: var(--ink); text-decoration: none; } .cat-card h2 a:hover { color: var(--brand); }
.cc-head { display: flex; gap: 6px; flex-wrap: wrap; }
.cc-desc { color: var(--sub); font-size: .9rem; margin: 0 0 10px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.cc-facts { display: flex; flex-wrap: wrap; gap: 6px 14px; list-style: none; padding: 0; margin: 0 0 10px; font-size: .88rem; color: var(--sub); }
.cc-facts b { color: var(--ink); }
.cc-meta { font-size: .78rem; color: var(--sub); margin: 0 0 10px; }
.cc-levels { margin: auto 0 0; display: flex; flex-wrap: wrap; gap: 6px; }
.cc-levels a { font-size: .74rem; font-weight: 700; padding: 3px 8px; border-radius: 8px; background: var(--surface-2); color: var(--ink); text-decoration: none; }
.cc-levels a:hover, .cc-levels a.on { background: var(--brand-soft); color: var(--brand); }
.cc-levels a.on { outline: 1.5px solid var(--brand); }
.chk { display: inline-flex; gap: 6px; align-items: center; color: var(--sub); font-size: .9rem; }
@media (max-width: 900px) { .cat-tools { grid-template-columns: 1fr 1fr; } .cat-tools input { grid-column: 1 / -1; } }
@media (max-width: 520px) { .cat-tools { grid-template-columns: 1fr; } }
'''
    script = '''<script>
(function () {
  var q = document.getElementById('cq'), cat = document.getElementById('ccat'), cls = document.getElementById('ccls'), lvl = document.getElementById('clvl'), sort = document.getElementById('csort');
  var list = document.getElementById('clist'), count = document.getElementById('ccount'), cards = [].slice.call(list.children);
  var p = new URLSearchParams(location.search);
  if (p.get('q')) q.value = p.get('q'); if (p.get('cat')) cat.value = p.get('cat'); if (p.get('class')) cls.value = p.get('class'); if (p.get('level')) lvl.value = p.get('level');
  function apply() {
    var terms = q.value.toLowerCase().split(/\\s+/).filter(Boolean), shown = 0;
    cards.forEach(function (c) {
      var ok = terms.every(function (t) { return c.dataset.text.indexOf(t) >= 0; }) && (!cat.value || c.dataset.cat === cat.value) && (!cls.value || c.dataset['class'] === cls.value);
      c.hidden = !ok; if (ok) shown++;
      c.querySelectorAll('.cc-levels a').forEach(function (a) { a.classList.toggle('on', a.dataset.level === lvl.value); });
    });
    var key = { az: 'title', newest: 'pub', updated: 'upd', reviewed: 'rev' }[sort.value];
    cards.slice().sort(function (a, b) { return key === 'title' ? (a.dataset.title < b.dataset.title ? -1 : 1) : (b.dataset[key] || '').localeCompare(a.dataset[key] || '') || (a.dataset.title < b.dataset.title ? -1 : 1); }).forEach(function (c) { list.appendChild(c); });
    count.textContent = shown + ' of ' + cards.length + ' courses shown';
    var u = new URLSearchParams(); if (q.value) u.set('q', q.value); if (cat.value) u.set('cat', cat.value); if (cls.value) u.set('class', cls.value); if (lvl.value) u.set('level', lvl.value);
    history.replaceState(null, '', u.toString() ? '?' + u : location.pathname);
  }
  [q, cat, cls, lvl, sort].forEach(function (el) { el.addEventListener('input', apply); });
  apply();
})();
</script>'''
    hero = (f'<h1>Course catalogue</h1><p>All {STATS["courses"]} published Mastery Path courses, each listed once with its stable ID, counts, dates and review status. '
            f'Every number comes from the course registry (audit of {STAMP}).</p>')
    body = f'''<form class="cat-tools" role="search" onsubmit="return false">
  <label class="sr-only" for="cq">Search courses</label><input id="cq" type="search" placeholder="Search by course, subject or technology">
  <label class="sr-only" for="ccat">Category</label><select id="ccat"><option value="">All {len(cats)} categories</option>{''.join(f'<option value="{E(i)}">{E(nm)}</option>' for i, nm in cats)}</select>
  <label class="sr-only" for="ccls">Classification</label><select id="ccls"><option value="">Technology + professional</option><option value="technology">Technology ({STATS['technology']})</option><option value="professional">Professional development ({STATS['professional']})</option></select>
  <label class="sr-only" for="clvl">Level</label><select id="clvl"><option value="">Highlight a level</option><option value="1">Level 1 · Entry</option><option value="2">Level 2 · Intermediate</option><option value="3">Level 3 · Advanced</option><option value="4">Level 4 · Master</option></select>
  <label class="sr-only" for="csort">Sort</label><select id="csort"><option value="az">Sort: A–Z</option><option value="newest">Sort: newest</option><option value="updated">Sort: recently updated</option><option value="reviewed">Sort: recently reviewed</option></select>
</form>
<p class="cat-count"><span id="ccount" aria-live="polite">{len(C)} courses</span> · All courses are free and public, with no sign-up. Every course spans all four levels; "Highlight a level" marks the level link on each card.</p>
<div class="cat-list" id="clist">
{chr(10).join(rows)}
</div>
<p class="stamp">Source: <a href="/registry/mastery_path_course_inventory.csv">course inventory (CSV)</a> · <a href="/registry/courses.json">courses.json</a> · Last updated {STAMP}.</p>
{script}'''
    page('course-catalogue/', f'Course Catalogue: {STATS["courses"]} Free Courses | Mastery Path',
         f'Every Mastery Path course with its ID, lesson and project counts, category, classification, publication date and review status. Search, filter and sort.',
         'Course catalogue', (hero, body), style)


# ------------------------------------------------------------------ quality & verification
def quality():
    D, R = CFG['definitions'], CFG['rules']
    hero = ('<h1>Quality &amp; verification</h1><p>How Mastery Path defines, counts and checks its courses. These rules decide every number on the site '
            f'and in the record evidence. Methodology version {E(CFG["methodology_version"])}.</p>')
    body = f'''<div class="doc">
<h2>1. Educational quality policy</h2>
<p>Every course is written to teach a subject end to end in four progressive levels, with runnable or practical examples in each lesson, exercises, module quizzes, level projects and a final capstone. Courses are free to read with no account. Content is published from public source repositories, so every change is dated and traceable.</p>

<h2>2. Definitions used for counting</h2>
<table><tbody>
<tr><th>Course</th><td>{E(D['course'])}</td></tr>
<tr><th>Learning level</th><td>{E(D['learning_level'])}</td></tr>
<tr><th>Module</th><td>{E(D['module'])}</td></tr>
<tr><th>Lesson</th><td>{E(D['lesson'])} The minimum is {R['min_lesson_words']} words.</td></tr>
<tr><th>Exercise</th><td>{E(D['exercise'])}</td></tr>
<tr><th>Quiz</th><td>{E(D['quiz'])}</td></tr>
<tr><th>Project</th><td>{E(D['project'])}</td></tr>
<tr><th>Capstone</th><td>{E(D['capstone'])}</td></tr>
</tbody></table>

<h2>3. Course eligibility criteria</h2>
<p>A course qualifies for platform and record measurements only when all of these automated checks pass <em>and</em> a human content review is recorded:</p>
<ol>
<li><b>Accessible:</b> the course home page returns HTTP 200 without login.</li>
<li><b>Published:</b> listed in the site's sitemap and not marked noindex.</li>
<li><b>Four levels:</b> each of Levels 1–4 has at least {R['min_lessons_per_level']} lessons.</li>
<li><b>Syllabus:</b> the course home links to its levels.</li>
<li><b>Substantive:</b> at least {R['min_lessons_per_course']} lessons, with no more than {R['max_thin_lessons']} under {R['min_lesson_words']} words.</li>
<li><b>Lessons reachable:</b> every lesson URL returns HTTP 200.</li>
<li><b>Practical:</b> at least one project.</li>
<li><b>Not a duplicate:</b> no exact or near-duplicate lesson text shared with another course (see 6).</li>
<li><b>First-party and free:</b> hosted on learnmasterypath.com from the owner's repositories; no payment or registration.</li>
<li><b>Human review:</b> a named reviewer has read the course and recorded a dated review. Until then the status is "eligible – human review pending".</li>
</ol>

<h2>4. Course classification</h2>
<p>{E(CFG['classification']['rule'])} Borderline cases are recorded with a note in the registry (for example Tally Prime &amp; GST: accounting practice taught in software, classified professional). Both groups stay on the platform; the classification only decides which measurements a course belongs to.</p>

<h2>5. What is never counted</h2>
<ul><li>Projects, capstones, exercises and quizzes are never counted as lessons.</li>
<li>A course used in several learning paths is counted once (one course ID).</li>
<li>Level overview pages, interview-question pages, cheat sheets, privacy and licence pages are not lessons.</li>
<li>External links (official documentation, videos on other sites) are references, never courses.</li>
<li>Learner, visitor or completion numbers are not published because they are not measured as verifiable counts.</li></ul>

<h2>6. Duplicate detection</h2>
<p>Each audit checks exact duplicate course IDs, slugs and normalised URLs; fingerprints the text of every lesson (SHA-256 of normalised text) to find identical lessons across courses; compares 5-word shingles of lessons with the same title (Jaccard ≥ {R['near_duplicate_jaccard']}) to find near-duplicates; and flags course titles that are very similar (ratio ≥ {R['similar_title_ratio']}). Similarity only flags candidates for human review; nothing is removed automatically. Latest audit: <b>{S['duplicate_candidates']}</b> candidate(s) – see <a href="/registry/mastery_path_duplicate_candidates.csv">duplicate candidates (CSV)</a>.</p>

<h2>7. Accessibility policy</h2>
<p>Pages target WCAG 2.2 AA: semantic headings, keyboard-reachable controls with visible focus, sufficient colour contrast in light and dark mode, labelled form fields, text that reflows on phones, and reduced motion when the device asks for it. Problems can be reported through the <a href="/contact.html">contact page</a>.</p>

<h2>8. Content review and publication</h2>
<p>Courses are written in Markdown in public GitHub repositories and published automatically when changes are merged, so each lesson's history is public. A content review is recorded in <code>registry/reviews.json</code> with the course ID, reviewer, date and notes; the most recent review becomes the course's "last reviewed" date. Corrections from learners are welcome and are fixed in the source.</p>

<h2>9. Verification and audit process</h2>
<p>The audit tool (<code>tools/registry/build_registry.py</code>) reads the live published site, so it measures what learners can actually open: every course's published pages, every lesson's text, quiz banks and sitemaps. It then requests every lesson URL, applies the rules above, and writes dated evidence files with SHA-256 checksums. Audit IDs and timestamps are never edited afterwards; each archived audit lives in its own folder under <code>registry/audits/</code>.</p>

<h2>10. Latest audit</h2>
<div class="kpis">{kpi(STATS['courses'], 'published courses')}{kpi(n(S['courses_passing_automated_checks']), 'pass all automated checks')}{kpi(n(S['courses_human_reviewed']), 'human-reviewed')}{kpi(STATS['lessons'], 'qualifying lessons')}{kpi(n(S['failed_urls']), 'lesson URLs failing')}</div>
<p class="stamp">Audit {E(S['audit_id'])} · {STAMP} · methodology {E(S['methodology_version'])} · repository commit <code>{E(S['repository_commit'][:7])}</code></p>

<h2>11. Data reporting and evidence files</h2>
<ul>
<li><a href="/registry/mastery_path_course_inventory.csv">Course inventory (CSV)</a> · <a href="/registry/mastery_path_lesson_inventory.csv">Lesson inventory (CSV)</a></li>
<li><a href="/registry/mastery_path_course_verification_report.csv">Course verification report (CSV)</a> · <a href="/registry/mastery_path_audit_summary.json">Audit summary (JSON)</a></li>
<li><a href="/registry/mastery_path_evidence_register.csv">Evidence register (CSV)</a> · <a href="/registry/SHA256SUMS">SHA-256 checksums</a></li>
</ul>
</div>'''
    page('quality-and-verification/', 'Quality & Verification: How We Count Courses | Mastery Path',
         'How Mastery Path defines courses, lessons, projects and levels, the eligibility rules, duplicate detection, review process and the latest audit results.',
         'Quality & verification', (hero, body))


# ------------------------------------------------------------------ learning impact
def impact():
    cats = ''.join(f'<tr><td>{E(k)}</td><td>{v}</td></tr>' for k, v in S['category_totals'].items())
    hero = ('<h1>Learning impact</h1><p>What Mastery Path publishes, measured from the course registry. Content volume is counted from the live site; '
            'engagement numbers are shown only when they are measured.</p>')
    body = f'''<h2>Published content</h2>
<div class="kpis">
{kpi(STATS['courses'], 'published courses')}{kpi(STATS['lessons'], 'lessons')}{kpi(n(P['projects']), 'level projects')}{kpi(n(P['capstones']), 'final capstones')}
{kpi(STATS['exercises'], 'exercises')}{kpi(STATS['quizzes'], 'quizzes (module + final)')}{kpi(STATS['categories'], 'categories')}{kpi(STATS['paths'], 'career learning paths')}
{kpi('4', 'levels in every course')}{kpi(STATS['technology'], 'technology courses')}{kpi(STATS['professional'], 'professional-development courses')}{kpi(n(S['first_party_domains']), 'first-party domains')}
</div>
<p class="stamp">Last updated {STAMP} (audit {E(S['audit_id'])}). Lessons exclude projects, capstones, exercises and quizzes, which are counted separately. <a href="/quality-and-verification/">How these are counted</a>.</p>

<h2 style="margin-top:32px">Courses by category</h2>
<div class="grid2"><div class="doc"><table><thead><tr><th>Category</th><th>Courses</th></tr></thead><tbody>{cats}</tbody></table></div>
<div class="doc"><h3>Review status</h3><p>{S['courses_passing_automated_checks']} of {P['courses']} courses pass every automated check. {S['courses_human_reviewed']} have a recorded human content review so far; reviews are being recorded course by course.</p>
<h3>Engagement</h3><table><tbody>
<tr><th>Learners</th><td>Not currently measured</td></tr><tr><th>Course completions</th><td>Not currently measured</td></tr><tr><th>Countries reached</th><td>Not currently measured</td></tr><tr><th>Certificates issued</th><td>Recorded per certificate; check any certificate at <a href="/verify/">/verify/</a></td></tr>
</tbody></table><p class="stamp">Progress is stored only in each learner's browser and no accounts exist, so there is no verifiable learner count. Page-view analytics are not used as learner numbers.</p></div></div>'''
    page('learning-impact/', f'Learning Impact: {STATS["courses"]} Courses, {STATS["lessons"]} Lessons | Mastery Path',
         'Measured content on Mastery Path: courses, lessons, projects, exercises, quizzes, categories and learning paths, with the date of the latest audit.',
         'Learning impact', (hero, body))


# ------------------------------------------------------------------ world record journey
def record():
    st = RECORD['status']
    ladder = ''.join(f'<li class="{"done" if s["state"] == "done" else ("now" if s["state"] == "current" else "")}"><b>{E(s["label"])}</b><span>{E(s["detail"])}</span></li>' for s in st)
    alts = ''.join(f'<tr><td>{E(a["title"])}</td><td>{E(a["assessment"])}</td></tr>' for a in RECORD['alternatives'])
    faq = ''.join(f'<details><summary>{E(q)}</summary><p>{E(a)}</p></details>' for q, a in RECORD['faq'])
    style = '''
.ladder2 { list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; counter-reset: s; }
.ladder2 li { display: grid; grid-template-columns: 34px 1fr; column-gap: 12px; padding: 12px 14px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); }
.ladder2 li::before { counter-increment: s; content: counter(s); grid-row: 1 / 3; width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; font-weight: 800; background: var(--surface-2); color: var(--sub); }
.ladder2 li.done::before { content: "✓"; background: var(--brand); color: var(--brand-ink); }
.ladder2 li.now { border-color: var(--amber); } .ladder2 li.now::before { background: var(--amber); color: #2b1d00; }
.ladder2 span { color: var(--sub); font-size: .9rem; }
details { border: 1px solid var(--line); border-radius: 12px; padding: 12px 16px; margin: 0 0 8px; background: var(--surface); } summary { font-weight: 700; cursor: pointer; }
'''
    hero = ('<h1>World record journey</h1><p>Mastery Path has applied to Guinness World Records for a new record title. This page shows exactly where that application stands '
            'and how the numbers behind it are measured. <b>No record has been awarded.</b></p>')
    body = f'''<div class="note" style="margin:0 0 24px"><b>Status: {E(RECORD['current_status'])}.</b> {E(RECORD['status_note'])} Mastery Path is not affiliated with, sponsored or endorsed by Guinness World Records.</div>
<div class="grid2">
<div class="doc">
<h2>What is Mastery Path?</h2><p>A free library of {STATS['courses']} structured courses, each in four levels, written and published by Vinod Bhanuja on one website. No account or payment is needed.</p>
<h2>Why apply for a record?</h2><p>To have the size and structure of the library measured by an independent body against published rules, instead of relying on our own claims.</p>
<h2>Title applied for</h2><p><b>{E(RECORD['submitted_title'])}</b><br><span class="stamp">Submitted as a new-record-title application on {E(RECORD['submitted_on'])}. Wording is proposed by us; Guinness World Records decides whether a title exists and what its rules are.</span></p>
<h2>How the count is measured</h2><p>Courses and lessons are counted by the open audit tool under the published <a href="/quality-and-verification/">quality &amp; verification rules</a>: one course counted once, projects and quizzes never counted as lessons, external links never counted, every lesson URL checked.</p>
<h2>Current published statistics</h2>
<div class="kpis">{kpi(STATS['courses'], 'courses')}{kpi(STATS['lessons'], 'lessons')}{kpi(STATS['projects'], 'projects + capstones')}{kpi(n(S['courses_human_reviewed']), 'human-reviewed so far')}</div>
<p class="stamp">Audit {E(S['audit_id'])}, {STAMP}.</p>
</div>
<div>
<h2 style="margin-top:0">Application status</h2>
<ol class="ladder2">{ladder}</ol>
<h2>Evidence collection</h2><p class="doc">Each audit produces dated inventories, a verification report, a duplicate report and an evidence register with SHA-256 checksums. Archived audits are never edited. If Guinness World Records accepts a title, the formal attempt will follow their guidelines exactly, including any independent witnesses or reviewers they require.</p>
</div></div>
<h2 style="margin-top:32px">Other titles we evaluated</h2>
<div class="doc"><table><thead><tr><th>Possible title</th><th>Our assessment</th></tr></thead><tbody>{alts}</tbody></table></div>
<h2 style="margin-top:32px">Frequently asked questions</h2>
{faq}'''
    page('world-record-attempt/', "World Record Journey: Our Proposed Application | Mastery Path",
         "Where Mastery Path's Guinness World Records application stands, the title applied for and how courses are measured. No record has been awarded.",
         'World record journey', (hero, body), style)


# ------------------------------------------------------------------ about redirect, facts, stats in existing pages
def about_redirect():
    out = ROOT / 'about/index.html'
    out.parent.mkdir(exist_ok=True)
    out.write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>About Mastery Path</title><meta name="robots" content="noindex">'
                   '<link rel="canonical" href="https://learnmasterypath.com/about.html"><meta http-equiv="refresh" content="0; url=/about.html"></head>'
                   '<body><p><a href="/about.html">About Mastery Path</a></p></body></html>\n')


def course_facts():
    facts = {c['course_slug']: {k: c[k] for k in ('course_id', 'lesson_count', 'project_count', 'capstone_count', 'exercise_count', 'quiz_count', 'lessons_per_level',
                                                  'course_author', 'publication_date', 'last_content_update', 'last_reviewed_date', 'course_classification', 'record_eligibility_status')} for c in C}
    (REG / 'course-facts.json').write_text(json.dumps({'audit_id': S['audit_id'], 'updated': S['audit_timestamp'], 'courses': facts}, separators=(',', ':')) + '\n')


def apply_stats():
    by_slug = {c['course_slug']: c for c in C}
    for rel in ('index.html', 'about.html', 'search/index.html', '404.html'):
        p = ROOT / rel
        if not p.exists():
            continue
        s = p.read_text()
        s = re.sub(r'(<([a-z0-9]+)\b[^>]*\bdata-mp-stat="([a-z_]+)"[^>]*>)(.*?)(</\2>)', lambda m: m.group(1) + E(STATS.get(m.group(3), m.group(4))) + m.group(5), s, flags=re.S)
        # numeric data-count used by the homepage count-up must match the shown value
        s = re.sub(r'data-count="\d+"(\s+data-suffix="[^"]*")?(\s+data-mp-stat="([a-z_]+)")', lambda m: f'data-count="{STATS[m.group(3)].replace(",", "")}"' + m.group(2), s)
        # course cards: "<li ... data-mp-lessons="slug">..</li>" and "· NN lessons" in new-course tiles
        s = re.sub(r'(<li data-mp-lessons="([a-z0-9-]+)">)(.*?)(</li>)', lambda m: m.group(1) + (lessons_label(by_slug[m.group(2)]) if m.group(2) in by_slug else m.group(3)) + m.group(4), s)
        s = re.sub(r'(<span data-mp-lessons="([a-z0-9-]+)">)(.*?)(</span>)', lambda m: m.group(1) + (lessons_label(by_slug[m.group(2)]) if m.group(2) in by_slug else m.group(3)) + m.group(4), s)
        # counts inside <head> (title, meta descriptions, JSON-LD text) follow the registry too
        head_end = s.find('</head>')
        if head_end > 0:
            head = s[:head_end]
            head = re.sub(r'\b\d{2,3}(?= (?:self-paced|free|structured|free, structured)\b[^"<]*?courses)', str(P['courses']), head)
            head = re.sub(r'\b\d{1,2},?\d{3}\+? (Lessons|lessons)\b', lambda m: f"{STATS['lessons']} {m.group(1)}", head)
            s = head + s[head_end:]
        p.write_text(s)


def sitemap():
    p = ROOT / 'sitemap-hub.xml'
    s = p.read_text()
    for path in ('course-catalogue/', 'quality-and-verification/', 'learning-impact/', 'world-record-attempt/'):
        loc = HUB + path
        if loc in s:
            s = re.sub(rf'(<loc>{re.escape(loc)}</loc><lastmod>)[^<]*', rf'\g<1>{DAY}', s)
        else:
            s = s.replace('</urlset>', f'  <url><loc>{loc}</loc><lastmod>{DAY}</lastmod></url>\n</urlset>')
    p.write_text(s)


if __name__ == '__main__':
    catalogue(); quality(); impact(); record(); about_redirect(); course_facts(); apply_stats(); sitemap()
    spec = importlib.util.spec_from_file_location('site_chrome', ROOT / 'tools/site_chrome.py')
    chrome = importlib.util.module_from_spec(spec); spec.loader.exec_module(chrome); chrome.main(ROOT)
    print('pages built from', S['audit_id'])
