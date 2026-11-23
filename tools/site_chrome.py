#!/usr/bin/env python3
"""Applies the homepage design (assets/site.css + the same header and footer) to the other hub pages.

Usage: python3 tools/site_chrome.py [repo_root]

Text pages (about, contact, privacy, ...) get a page band (breadcrumb, title, intro) and a document
column. App pages (search, resume, interview pack/questions, verify) keep their own component CSS, minus
the old colour tokens, body and footer rules, which site.css now provides.
Safe to re-run: after the first pass only the marked header/footer blocks are refreshed.
"""
import re
import sys
from pathlib import Path

HUB = 'https://learnmasterypath.com/'
TEXT_PAGES = ['about.html', 'contact.html', 'privacy.html', 'terms.html', 'refunds.html', 'delivery.html', 'license.html', '404.html']
APP_PAGES = ['search/index.html', 'interview-pack/index.html', 'interview-questions/index.html', 'resume/index.html', 'verify/index.html']
APP_CSS = ['resume/style.css']

LOGO = ('<svg class="brand-mark" aria-hidden="true" focusable="false" viewBox="0 0 160 160">'
        '<circle cx="80" cy="80" r="74" fill="#FAF7EF" stroke="#2FA98D" stroke-width="4"/>'
        '<rect x="36" y="90" width="17" height="24" rx="5" fill="#2FA98D"/><rect x="59" y="74" width="17" height="40" rx="5" fill="#7FC9B7"/>'
        '<rect x="82" y="56" width="17" height="58" rx="5" fill="#E0B457"/><rect x="105" y="38" width="17" height="76" rx="5" fill="#C98B4A"/>'
        '<circle cx="44.5" cy="82" r="7" fill="#22261f"/></svg>')
NAV = [('Courses', HUB + '#courses'), ('Learning Paths', HUB + '#paths'), ('Interview Prep', HUB + 'interview-questions/'),
       ('Resume Tools', HUB + 'resume/'), ('Certificates', HUB + 'verify/'), ('About', HUB + 'about.html')]
HEAD = ('<!-- mp-chrome:head -->'
        '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap">'
        '<link rel="stylesheet" href="/assets/site.css?v=1">'
        '<!-- /mp-chrome:head -->')


def header(page):
    def links(cls=''):
        out = []
        for label, href in NAV:
            cur = ' aria-current="page"' if href.endswith('/' + page.replace('index.html', '')) and not href.endswith('#courses') else ''
            out.append(f'<a href="{href}"{cur}>{label}</a>')
        return ''.join(out)
    return ('<!-- mp-chrome:header --><a class="skip" href="#content">Skip to content</a>\n'
            '<header class="site-header"><div class="container nav-row">'
            f'<a class="brand" href="{HUB}" aria-label="Mastery Path home">{LOGO}<span>Mastery Path</span></a>'
            f'<nav class="nav-links" aria-label="Main">{links()}</nav>'
            '<a class="nav-search" href="/search/"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="M20 20l-4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg><span>Search</span></a>'
            f'<details class="nav-menu"><summary aria-label="Open menu"><span></span><span></span><span></span></summary><nav aria-label="Mobile">{links()}<a href="/search/">Search</a></nav></details>'
            '</div></header><!-- /mp-chrome:header -->')


FOOTER = ('<!-- mp-chrome:footer --><footer class="site-footer"><div class="container foot-grid">'
          f'<div class="foot-brand"><a class="brand" href="{HUB}">{LOGO}<span>Mastery Path</span></a>'
          '<p>Free, structured courses from beginner to expert. Built and maintained by Vinod Bhanuja.</p>'
          '<p>Contact: <a href="mailto:contact@learnmasterypath.com">contact@learnmasterypath.com</a></p></div>'
          f'<nav aria-label="Learn"><h3>Learn</h3><a href="{HUB}#courses">All courses</a><a href="{HUB}#paths">Learning paths</a><a href="{HUB}#projects">Projects</a><a href="/search/">Search</a></nav>'
          f'<nav aria-label="Career"><h3>Career</h3><a href="{HUB}resume/">Resume Tools</a><a href="{HUB}interview-pack/">Interview Pack</a><a href="{HUB}interview-questions/">Interview questions &amp; cheat sheets</a><a href="{HUB}verify/">Verify a certificate</a></nav>'
          f'<nav aria-label="Company"><h3>Company</h3><a href="{HUB}about.html">About</a><a href="{HUB}contact.html">Contact</a><a href="{HUB}privacy.html">Privacy Policy</a><a href="{HUB}terms.html">Terms</a><a href="{HUB}refunds.html">Refunds</a><a href="{HUB}delivery.html">Delivery</a><a href="{HUB}license.html">License</a></nav>'
          '<nav aria-label="Follow"><h3>Follow</h3><a href="https://www.youtube.com/@learnmasterypath">YouTube</a><a href="https://github.com/sigilipelli">GitHub</a><a href="https://learnmasterypath.com/feed.xml">RSS feed</a></nav>'
          '</div><div class="container foot-bottom"><span>© 2026 Vinod Bhanuja · Mastery Path</span>'
          '<span>Except where otherwise noted, content is licensed <a rel="license" href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>, code MIT.</span></div>'
          '</footer><!-- /mp-chrome:footer -->')

DROP_SEL = re.compile(r'^(:root|\*|html|body|footer\b|footer a|\.topbar|\.site-footer|\.wrap > footer)', re.I)


def filter_css(css):
    """Removes token, body, universal and footer rules (now in site.css); keeps component rules."""
    out, i, n = [], 0, len(css)
    while i < n:
        j = css.find('{', i)
        if j < 0:
            out.append(css[i:]); break
        sel = css[i:j].strip()
        depth, k = 1, j + 1
        while k < n and depth:
            depth += {'{': 1, '}': -1}.get(css[k], 0); k += 1
        block = css[j + 1:k - 1]
        if sel.startswith('@media') or sel.startswith('@supports'):
            inner = filter_css(block)
            if inner.strip():
                out.append(f'{sel} {{{inner}}}\n')
        elif sel.startswith('@'):
            out.append(f'{sel} {{{block}}}\n')
        else:
            sels = [s.strip() for s in re.sub(r'/\*.*?\*/', '', sel, flags=re.S).split(',')]
            keep = [s for s in sels if s and not DROP_SEL.match(s)]
            if keep:
                out.append(f'{", ".join(keep)} {{{block}}}\n')
        i = k
    return ''.join(out)


def put_head(html):
    html = re.sub(r'<!-- mp-chrome:head -->.*?<!-- /mp-chrome:head -->\s*', '', html, flags=re.S)
    html = re.sub(r'<link rel="preconnect" href="https://fonts\.g[^>]*>\s*', '', html)
    m = re.search(r'<style|<link rel="(stylesheet|preload)"', html)
    pos = m.start() if m else html.index('</head>')
    return html[:pos] + HEAD + '\n' + html[pos:]


def refresh(html, page):
    html = re.sub(r'<!-- mp-chrome:header -->.*?<!-- /mp-chrome:header -->', lambda m: header(page), html, flags=re.S)
    html = re.sub(r'<!-- mp-chrome:footer -->.*?<!-- /mp-chrome:footer -->', lambda m: FOOTER, html, flags=re.S)
    return put_head(html)


def text_page(html, page):
    html = re.sub(r'<style>.*?</style>\s*', '', html, flags=re.S)
    body_open = re.search(r'<body[^>]*>', html)
    head, body = html[:body_open.end()], html[body_open.end():html.rindex('</body>')]
    main = re.search(r'<main[^>]*>(.*)</main>', body, re.S)
    inner = main.group(1).strip()
    scripts = ''.join(re.findall(r'<script\b.*?</script>', body[main.end():], re.S))
    crumbs = re.search(r'<nav aria-label="Breadcrumb"[^>]*>.*?</nav>', inner, re.S)
    crumbs_html = crumbs.group(0) if crumbs else f'<nav aria-label="Breadcrumb" class="crumbs"><a href="{HUB}">Mastery Path</a></nav>'
    if crumbs:
        inner = inner.replace(crumbs.group(0), '', 1)
    h1 = re.search(r'<h1[^>]*>.*?</h1>', inner, re.S)
    inner = inner.replace(h1.group(0), '', 1)
    lede = re.match(r'\s*<p[^>]*>.*?</p>', inner, re.S)
    lede_html = ''
    if lede:
        lede_html = re.sub(r'<p[^>]*>', '<p>', lede.group(0).strip(), count=1)
        inner = inner[lede.end():]
    new_body = (f'\n{header(page)}\n<main id="content">\n<section class="page-hero"><div class="container">{crumbs_html}{h1.group(0)}{lede_html}</div></section>\n'
                f'<div class="container page-body"><div class="doc">\n{inner.strip()}\n</div></div>\n</main>\n{FOOTER}\n{scripts}\n')
    return put_head(head + new_body + html[html.rindex('</body>'):])


def app_page(html, page):
    html = re.sub(r'(<style>)(.*?)(</style>)', lambda m: m.group(1) + filter_css(m.group(2)) + m.group(3), html, flags=re.S)
    html = re.sub(r'<div class="topbar">.*?</div>\s*', '', html, count=1, flags=re.S)
    html = re.sub(r'<footer\b[^>]*>.*?</footer>\s*', '', html, count=1, flags=re.S)
    html = re.sub(r'(<body[^>]*>)', lambda m: m.group(1) + '\n' + header(page), html, count=1)
    end = html.rindex('</main>') + len('</main>')
    nxt = re.match(r'\s*</div>', html[end:])
    if nxt:
        end += nxt.end()
    html = html[:end] + '\n' + FOOTER + html[end:]
    return put_head(html)


def main(root):
    root = Path(root)
    for page in TEXT_PAGES + APP_PAGES:
        p = root / page
        if not p.exists():
            print('skip (missing)', page); continue
        html = p.read_text()
        if '<!-- mp-chrome:header -->' in html:
            new = refresh(html, page)
        elif page in TEXT_PAGES:
            new = text_page(html, page)
        else:
            new = app_page(html, page)
        if new != html:
            p.write_text(new); print('updated', page)
    for css in APP_CSS:
        p = root / css
        if p.exists() and '/* mp-chrome:' not in p.read_text():
            p.write_text('/* mp-chrome: tokens, body and footer come from /assets/site.css */\n' + filter_css(p.read_text()))
            print('updated', css)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')
