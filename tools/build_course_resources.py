"""Generate per-course "Interview Questions" and "Cheat Sheet" pages from existing course material.

  interview-questions.md  <- the hub's learn/quizzes/<course>.json (lesson questions, final questions, coding
                             challenges), shown as question + correct answer + explanation, grouped by level/lesson.
  cheat-sheet.md          <- each lesson's "## Cheat sheet" section; for courses without those, each lesson's main
                             reference table. Only built when there is real material (no thin pages).

Usage: python3 tools/build_course_resources.py <repos_root> [--only course-id ...] [--dry]
  <repos_root> has the layout from clone-all.sh: all/<repo>, all/python-mastery-path/<nested>, newcourses/{dm,tally},
  sigilipelli.github.io (this hub). Pages are written into each course's docs/ and added to its mkdocs.yml nav.
Re-run any time quizzes or lessons change; output is deterministic.
"""
import glob
import json
import pathlib
import posixpath
import re
import sys

ROOT = pathlib.Path(sys.argv[1])
ONLY = sys.argv[sys.argv.index('--only') + 1:] if '--only' in sys.argv else None
DRY = '--dry' in sys.argv
HUB = ROOT / 'sigilipelli.github.io'
LEVEL_NAMES = {1: 'Entry', 2: 'Intermediate', 3: 'Advanced', 4: 'Master'}
MIN_CHEAT_SECTIONS, MIN_TABLE_LESSONS = 10, 15
FENCE = '`' * 3

course_dirs = sorted(set(
    [pathlib.Path(p).parent for p in glob.glob(str(ROOT / 'all/*/mkdocs.yml'))]
    + [pathlib.Path(p).parent for p in glob.glob(str(ROOT / 'all/python-mastery-path/*/mkdocs.yml'))]
    + [pathlib.Path(p).parent for p in glob.glob(str(ROOT / 'newcourses/*/mkdocs.yml'))]))


def esc_text(s):
    """Escape characters Markdown would treat as HTML, leaving `code` spans and fenced blocks untouched."""
    out, parts = [], re.split(r'(' + FENCE + r'[\s\S]*?' + FENCE + r'|`[^`\n]+`)', str(s))
    for i, p in enumerate(parts):
        out.append(p if i % 2 else p.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
    return ''.join(out)


def block(s):
    """A question/answer text as a Markdown block: escaped, and any code fence started on its own line."""
    s = esc_text(s).strip()
    return re.sub(r'([^\n])\n?(' + FENCE + r')', r'\1\n\n\2', s, count=1) if FENCE in s else s


def lessons_of(docs):
    out = []
    for f in sorted(docs.glob('level-*/[0-9]*.md')):
        t = f.read_text()
        h1 = re.search(r'^# (.+)$', t, re.M)
        title = re.sub(r'\s*\{[^}]*\}\s*$', '', h1.group(1)).strip() if h1 else f.stem
        out.append({'level': int(f.parent.name.split('-')[1]), 'path': f.relative_to(docs).as_posix(),
                    'slug': f.parent.name + '/' + f.stem, 'title': title, 'text': t})
    return out


def level_title(docs, n):
    f = docs / f'level-{n}' / 'index.md'
    if f.exists():
        h = re.search(r'^# (.+)$', f.read_text(), re.M)
        if h:
            return re.sub(r'<span[^>]*>.*?</span>|<[^>]+>', '', h.group(1)).strip()
    return f'Level {n} · {LEVEL_NAMES[n]}'


def rewrite_links(md, lesson_path):
    """Relative links/images in copied lesson content must point from the docs root instead of the lesson folder."""
    base = posixpath.dirname(lesson_path)

    def fix(m):
        target = m.group(2)
        if re.match(r'^(https?:|mailto:|#|/)', target):
            return m.group(0)
        path, _, frag = target.partition('#')
        new = posixpath.normpath(posixpath.join(base, path)) if path else lesson_path
        return f'{m.group(1)}({new}{"#" + frag if frag else ""})'
    return re.sub(r'(!?\[[^\]]*\])\(([^)\s]+)\)', fix, md)


def section(md, heading_re):
    m = re.search(r'^##\s+(' + heading_re + r')[^\n]*\n', md, re.M | re.I)
    if not m:
        return None
    rest = md[m.end():]
    end = re.search(r'^##\s', rest, re.M)
    return rest[: end.start()].strip() if end else rest.strip()


def first_table(md):
    """The lesson's first Markdown table with the nearest heading above it as a caption."""
    m = re.search(r'((?:^\|.*\|[ \t]*\n){2,})', md, re.M)
    if not m or not re.search(r'^\|\s*:?-{3}', m.group(1), re.M):
        return None, None
    heads = re.findall(r'^#{2,4}\s+(.+)$', md[: m.start()], re.M)
    cap = re.sub(r'^\d+\.\s*', '', heads[-1]).strip() if heads else None
    return cap, m.group(1).rstrip()


def interview_page(c, quiz, lessons, docs):
    les_q = quiz.get('lessons', {})
    final = quiz.get('final') or {}
    n = sum(len(v.get('questions', [])) for v in les_q.values()) + len(final.get('questions', []))
    if n < 20:
        return None, 0
    topic = c['topic']
    lines = ['---',
             f'title: "{topic} Interview Questions and Answers ({n} Questions)"',
             f'description: "{n} {topic} interview questions with answers and explanations, from beginner to advanced, organised by level. Free, from the {c["name"]}."',
             '---', '', f'# {topic} Interview Questions and Answers', '',
             f'**{n} questions** with the correct answer and a short explanation, organised from beginner (Level 1) to advanced (Level 4). '
             f'Every question comes from a lesson in the free {c["name"]}, so you can open the lesson to go deeper.', '',
             '!!! tip "Practise, don\'t just read"',
             '    Each lesson also ends with an interactive quiz, and the [final quiz](quiz.md) tests all four levels. '
             'Try to answer each question below before reading the answer.' if (docs / 'quiz.md').exists() else
             '    Each lesson also ends with an interactive quiz. Try to answer each question below before reading the answer.', '']
    k = 0
    for lvl in (1, 2, 3, 4):
        group = [L for L in lessons if L['level'] == lvl and les_q.get(L['slug'], {}).get('questions')]
        if not group:
            continue
        lines += [f'## {level_title(docs, lvl)}', '']
        for L in group:
            lines += [f'### [{esc_text(L["title"])}]({L["path"]})', '']
            for q in les_q[L['slug']]['questions']:
                k += 1
                lines += [f'**Q{k}.** {block(q["q"])}', '', f'**Answer:** {block(q["options"][q["answer"]])}', '']
                if q.get('explain'):
                    lines += [block(q['explain']), '']
    if final.get('questions'):
        lines += ['## Mixed questions across all levels', '']
        for q in final['questions']:
            k += 1
            lines += [f'**Q{k}.** {block(q["q"])}', '', f'**Answer:** {block(q["options"][q["answer"]])}', '']
            if q.get('explain'):
                lines += [block(q['explain']), '']
    ch = (final.get('challenges') or []) + [v['challenge'] for v in les_q.values() if v.get('challenge')]
    if ch:
        lines += ['## Practical coding questions', '']
        for x in ch:
            lang = x.get('lang', '')
            lines += [f'### {esc_text(x.get("title", "Challenge"))}', '', block(x.get('prompt', '')), '']
            if x.get('starter'):
                lines += ['Starter code:', '', FENCE + lang, x['starter'].rstrip(), FENCE, '']
            if x.get('expected'):
                lines += ['Expected output:', '', FENCE + 'text', x['expected'].rstrip(), FENCE, '']
            if x.get('solution'):
                lines += ['??? success "Show a solution"', '', '    ' + FENCE + lang]
                lines += ['    ' + ln if ln else '' for ln in x['solution'].rstrip().split('\n')]
                lines += ['    ' + FENCE, '']
                if x.get('explain'):
                    lines += ['    ' + esc_text(x['explain']), '']
    lines += ['---', '', f'More free practice: the [{c["name"]}](index.md) curriculum, the '
              '[Interview Prep Pack](https://learnmasterypath.com/interview-pack/) and the '
              '[free resume ATS check](https://learnmasterypath.com/resume/).', '']
    return '\n'.join(lines), n


def cheat_page(c, lessons, docs):
    items, mode = [], None
    with_cs = [L for L in lessons if section(L['text'], r'[^\n]*cheat')]
    if len(with_cs) >= MIN_CHEAT_SECTIONS:
        mode = 'cheat'
        for L in lessons:
            s = section(L['text'], r'[^\n]*cheat')
            if s and len(s) > 40:
                items.append((L, None, rewrite_links(s, L['path'])))
    else:
        for L in lessons:
            cap, tbl = first_table(L['text'])
            if tbl:
                items.append((L, cap, rewrite_links(tbl, L['path'])))
        mode = 'tables' if len(items) >= MIN_TABLE_LESSONS else None
    if not mode:
        return None, 0
    topic = c['topic']
    n = len(items)
    lines = ['---',
             f'title: "{topic} Cheat Sheet: Quick Reference, Beginner to Advanced"',
             f'description: "A free {topic} cheat sheet: {n} quick-reference tables from every level of the {c["name"]}, each linked to its full lesson."',
             '---', '', f'# {topic} Cheat Sheet', '',
             f'Quick-reference tables from **{n} lessons** of the free {c["name"]}, in course order from beginner to advanced. '
             'Each section links to the full lesson with explanations and runnable examples.', '']
    for lvl in (1, 2, 3, 4):
        group = [x for x in items if x[0]['level'] == lvl]
        if not group:
            continue
        lines += [f'## {level_title(docs, lvl)}', '']
        for L, cap, content in group:
            lines += [f'### [{esc_text(L["title"])}]({L["path"]})', '']
            if cap:
                lines += [f'*{esc_text(cap)}*', '']
            lines += [content, '']
    lines += ['---', '', f'Go deeper with the full [{c["name"]}](index.md) curriculum or test yourself with the '
              '[interview questions](interview-questions.md).' if (docs / 'interview-questions.md').exists() or True else '', '']
    return '\n'.join(lines), n


def add_nav(yml, entries):
    """Insert nav entries right after the Home entry (idempotent)."""
    t = yml.read_text()
    for label, page in reversed(entries):
        if f': {page}' in t:
            continue
        t = re.sub(r'^(  - Home: index\.md\n)', r'\1' + f'  - "{label}": {page}\n', t, count=1, flags=re.M)
    return t


report = []
for d in course_dirs:
    y = (d / 'mkdocs.yml').read_text()
    name = re.search(r'^site_name:\s*(.+)$', y, re.M).group(1).strip().strip('"\'')
    url = re.search(r'^site_url:\s*(.+)$', y, re.M).group(1).strip()
    cid = url.rstrip('/').split('/')[-1]
    if ONLY and cid not in ONLY:
        continue
    c = {'id': cid, 'name': name, 'topic': name.replace(' Mastery Path', '')}
    docs = d / 'docs'
    lessons = lessons_of(docs)
    qf = HUB / 'learn/quizzes' / f'{cid}.json'
    quiz = json.loads(qf.read_text()) if qf.exists() else {}
    iv, n_iv = interview_page(c, quiz, lessons, docs)
    cs, n_cs = cheat_page(c, lessons, docs)
    nav = []
    if iv:
        nav.append(('Interview Questions', 'interview-questions.md'))
    if cs:
        nav.append(('Cheat Sheet', 'cheat-sheet.md'))
    if not DRY:
        if iv:
            (docs / 'interview-questions.md').write_text(iv)
        if cs:
            (docs / 'cheat-sheet.md').write_text(cs)
        if nav:
            (d / 'mkdocs.yml').write_text(add_nav(d / 'mkdocs.yml', nav))
    report.append((cid, n_iv, n_cs))

def hub_directory(report):
    """learnmasterypath.com/interview-questions/: one page linking every interview page and cheat sheet, by category."""
    import html as H
    courses = {c['id']: c for c in json.loads((HUB / 'search/courses.json').read_text())}
    rows = [(courses[cid], n_iv, n_cs) for cid, n_iv, n_cs in report if cid in courses and (n_iv or n_cs)]
    total_q = sum(r[1] for r in rows)
    cats = {}
    for c, n_iv, n_cs in rows:
        cats.setdefault(c['catName'], []).append((c, n_iv, n_cs))
    e = lambda s: H.escape(str(s))
    sections = []
    for cat in sorted(cats):
        items = ''.join(
            f'<li data-name="{e(c["short"].lower())}"><span class="nm"><span aria-hidden="true">{c["emoji"]}</span> {e(c["short"])}</span>'
            + (f'<a href="{c["url"]}interview-questions/">Interview questions <small>({n_iv})</small></a>' if n_iv else '')
            + (f'<a href="{c["url"]}cheat-sheet/">Cheat sheet</a>' if n_cs else '') + '</li>'
            for c, n_iv, n_cs in sorted(cats[cat], key=lambda x: x[0]['short'].lower()))
        sections.append(f'<section><h2>{e(cat)}</h2><ul class="dir">{items}</ul></section>')
    n_iv_pages = sum(1 for r in rows if r[1])
    n_cs_pages = sum(1 for r in rows if r[2])
    page = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Free Interview Questions &amp; Cheat Sheets – Mastery Path</title>
<meta name="description" content="{total_q:,} free interview questions with answers for {n_iv_pages} technologies, plus {n_cs_pages} cheat sheets: Python, SQL, Java, AWS, Excel, Tally, React and more, beginner to advanced.">
<link rel="canonical" href="https://learnmasterypath.com/interview-questions/">
<meta property="og:type" content="website"><meta property="og:site_name" content="Mastery Path">
<meta property="og:title" content="Free Interview Questions &amp; Cheat Sheets – Mastery Path">
<meta property="og:description" content="{total_q:,} interview questions with answers and {n_cs_pages} cheat sheets across {n_iv_pages} technologies.">
<meta property="og:url" content="https://learnmasterypath.com/interview-questions/"><meta property="og:image" content="https://learnmasterypath.com/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-05VBGCXN12"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-05VBGCXN12');</script>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9440969811959397" crossorigin="anonymous"></script>
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{{"@type":"ListItem","position":1,"name":"Mastery Path","item":"https://learnmasterypath.com/"}},{{"@type":"ListItem","position":2,"name":"Interview questions & cheat sheets","item":"https://learnmasterypath.com/interview-questions/"}}]}}</script>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<style>
  :root {{ --ink:#0f1d19; --sub:#4c5d57; --bg:#f6f8f7; --card:#fff; --line:#dbe4e0; --brand:#13785f; --soft:#e1f2ec; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --ink:#e9f1ee; --sub:#a5b5ae; --bg:#0d1412; --card:#141d1a; --line:#26332e; --brand:#4fd1ae; --soft:#173a30; }} }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif; }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 32px 16px 72px; }}
  a {{ color: var(--brand); }}
  .crumbs {{ font-size:.9rem; color:var(--sub); margin:0 0 14px; }}
  h1 {{ font-size: clamp(1.6rem, 3.4vw, 2.2rem); line-height:1.2; margin: 0 0 8px; text-wrap: balance; }}
  .lede {{ color: var(--sub); margin: 0 0 18px; max-width: 70ch; }}
  #filter {{ width: 100%; max-width: 420px; padding: 12px 14px; font-size: 16px; border-radius: 10px; border: 1.5px solid var(--line); background: var(--card); color: var(--ink); }}
  #filter:focus {{ outline: 3px solid color-mix(in srgb, var(--brand) 35%, transparent); border-color: var(--brand); }}
  h2 {{ font-size: 1.1rem; margin: 30px 0 10px; }}
  .dir {{ list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 8px; }}
  .dir li {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; padding: 10px 14px; border-radius: 10px; background: var(--card); border: 1px solid var(--line); }}
  .dir .nm {{ font-weight: 700; flex: 1 1 100%; }}
  .dir a {{ font-size: .9rem; font-weight: 600; text-decoration: none; padding: 2px 10px; border-radius: 999px; background: var(--soft); }}
  .dir a:hover {{ text-decoration: underline; }}
  .dir small {{ color: var(--sub); font-weight: 500; }}
  footer {{ margin-top: 48px; padding-top: 18px; border-top: 1px solid var(--line); font-size: .85rem; color: var(--sub); }}
  footer a {{ color: var(--sub); margin-right: 14px; }}
</style>
</head>
<body>
<div class="wrap">
<nav aria-label="Breadcrumb" class="crumbs"><a href="https://learnmasterypath.com/">Mastery Path</a> › <span aria-current="page">Interview questions &amp; cheat sheets</span></nav>
<main id="content">
  <h1>Free interview questions and cheat sheets</h1>
  <p class="lede"><b>{total_q:,} interview questions</b> with answers and explanations for {n_iv_pages} technologies, plus <b>{n_cs_pages} cheat sheets</b>. Every question comes from a lesson in a free Mastery Path course, from beginner to advanced. No signup needed.</p>
  <label for="filter" style="position:absolute;left:-9999px">Filter technologies</label>
  <input id="filter" type="search" placeholder="Filter: Python, SQL, AWS, Excel…" autocomplete="off">
  {''.join(sections)}
  <p class="lede" style="margin-top:32px">Preparing for a specific job? Run your resume through the <a href="https://learnmasterypath.com/resume/">free ATS check</a> and grab the <a href="https://learnmasterypath.com/interview-pack/">Interview Prep Pack</a>.</p>
</main>
<footer><a href="https://learnmasterypath.com/">Home</a><a href="https://learnmasterypath.com/search/">Search</a><a href="https://learnmasterypath.com/resume/">Resume Tools</a><a href="https://learnmasterypath.com/about.html">About</a><a href="https://learnmasterypath.com/privacy.html">Privacy</a></footer>
</div>
<script>
document.getElementById('filter').addEventListener('input', function (e) {{
  var q = e.target.value.trim().toLowerCase();
  document.querySelectorAll('.dir li').forEach(function (li) {{ li.hidden = q && li.dataset.name.indexOf(q) < 0; }});
  document.querySelectorAll('main section').forEach(function (s) {{ s.hidden = !s.querySelector('li:not([hidden])'); }});
}});
</script>
</body>
</html>
'''
    (HUB / 'interview-questions').mkdir(exist_ok=True)
    (HUB / 'interview-questions/index.html').write_text(page)
    # same header, footer and design as the homepage (idempotent)
    import importlib.util
    spec = importlib.util.spec_from_file_location('site_chrome', pathlib.Path(__file__).with_name('site_chrome.py'))
    chrome = importlib.util.module_from_spec(spec); spec.loader.exec_module(chrome)
    chrome.main(HUB)
    return len(rows)


if not DRY and not ONLY:
    print('hub directory rows:', hub_directory(report))

print(f'courses: {len(report)} | interview pages: {sum(1 for r in report if r[1])} ({sum(r[1] for r in report)} questions) | '
      f'cheat sheets: {sum(1 for r in report if r[2])} ({sum(r[2] for r in report)} sections)')
print('no interview page:', [r[0] for r in report if not r[1]])
print('no cheat sheet:', [r[0] for r in report if not r[2]])
