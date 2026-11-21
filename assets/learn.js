/* Mastery Path learning layer for every course site (loaded by the shared course template).
 * Everything runs in the browser: progress, quiz scores and notes are stored in localStorage
 * (no account, no server, nothing executed server-side). All lesson content stays readable without JS.
 *   Course home: overview (outcomes, prerequisites, duration, difficulty, skills), progress dashboard,
 *                continue learning, interactive curriculum.
 *   Lessons:     tools bar (reading time, download code examples, official docs), practical exercise card,
 *                module quiz (multiple choice + coding challenge, scoring, explanations, retry).
 *   Projects:    objectives, implementation steps, expected output, GitHub source, evaluation checklist.
 * Course data comes from the course's own published search index; quizzes and docs links from the hub.
 */
(function () {
  'use strict';
  var metaEl = document.getElementById('mp-course-meta');
  if (!metaEl) return;
  var META; try { META = JSON.parse(metaEl.textContent); } catch (e) { return; }
  var HUB = 'https://learnmasterypath.com/';
  var LEVEL_NAMES = { 1: 'Entry', 2: 'Intermediate', 3: 'Advanced', 4: 'Master' };
  // Same storage key scheme as progress-tracker.js (first path segment), so both stay in sync.
  var REPO = (location.pathname.match(/^\/([a-z0-9-]+)\//) || [])[1] || location.hostname;
  var PAGE = location.pathname.match(/\/(level-(\d+))\/([^/]+)\/?$/);
  var SLUG = PAGE ? PAGE[1] + '/' + PAGE[3] : null;

  // ---------- small helpers ----------
  function $(s, el) { return (el || document).querySelector(s); }
  function $$(s, el) { return Array.prototype.slice.call((el || document).querySelectorAll(s)); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { return null; } }
  function storeJSON(k, v) { if (v === undefined) { try { return JSON.parse(store(k)) || null; } catch (e) { return null; } } store(k, JSON.stringify(v)); }
  function isDone(slug) { return store('mp-done:' + REPO + ':' + slug) === '1'; }
  function quizKey(slug) { return 'mp-quiz:' + META.id + ':' + slug; }
  var cache = {};
  function getJSON(url) { if (!cache[url]) cache[url] = fetch(url, { credentials: 'omit' }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); return cache[url]; }
  function strip(html) { var d = document.createElement('div'); d.innerHTML = html || ''; return (d.textContent || '').replace(/\s+/g, ' ').trim(); }
  function words(t) { return (t.match(/\S+/g) || []).length; }
  function track(name, params) { try { if (window.gtag) window.gtag('event', name, params || {}); } catch (e) {} }
  function content() { return $('.md-content__inner'); }
  // Where lesson add-ons go: right after the lesson text, before related courses / sign-up / mark-complete.
  function endAnchor(host) { return $('.mp-related', host) || $('#mp-signup', host) || $('.mp-mark-done', host); }
  function isProject(slug) { return /project|capstone/i.test(slug || ''); }

  // ---------- course model from the course's own search index ----------
  var modelP = null;
  function model() {
    if (modelP) return modelP;
    modelP = getJSON(META.url + 'search/search_index.json').then(function (idx) {
      var lessons = {}, levels = {}, home = {};
      idx.docs.forEach(function (d) {
        var m = d.location.match(/^level-(\d+)\/([^/#]+)\/(#.*)?$/);
        if (m) {
          var slug = 'level-' + m[1] + '/' + m[2];
          var L = lessons[slug] || (lessons[slug] = { slug: slug, level: +m[1], title: '', words: 0, url: META.url + 'level-' + m[1] + '/' + m[2] + '/' });
          var text = strip(d.text);
          if (!m[3]) L.title = strip(d.title).replace(/^\d+\s*·\s*/, '');
          L.words += words(text);
          return;
        }
        var lv = d.location.match(/^level-(\d+)\/(#.*)?$/);
        if (lv && !lv[2]) { var g = strip(d.text).match(/Goal:?\s*(.+?)(?:\s+Modules\b|$)/); levels[lv[1]] = { title: strip(d.title), goal: g ? g[1] : '' }; return; }
        if (/^#?what-you(ll|-ll|'ll)?-need|^#what-youll-need|^#prerequisites/.test(d.location)) home.need = strip(d.text);
        if (d.location === '#how-the-program-is-organized') home.focus = strip(d.text);
      });
      var list = Object.keys(lessons).map(function (k) { return lessons[k]; }).sort(function (a, b) { return a.slug < b.slug ? -1 : 1; });
      list.forEach(function (L) {
        // Estimate: reading at ~200 words/min + practice time (projects need more).
        L.minutes = Math.round(L.words / 200 + (isProject(L.slug) ? 90 : 20));
      });
      return { lessons: list, levels: levels, home: home };
    });
    return modelP;
  }

  function quizzes() { return getJSON(HUB + 'learn/quizzes/' + META.id + '.json').catch(function () { return { lessons: {} }; }); }
  function docsLinks() { return getJSON(HUB + 'learn/docs.json').then(function (d) { return d[META.id] || []; }).catch(function () { return []; }); }

  // ================= COURSE HOME =================
  function levelFocus(home, n) {
    if (!home.focus) return '';
    var re = new RegExp('Level ' + n + ' · \\w+\\s+(.+?)\\s+(?:\\d+ topics|\\d+ modules|9 topics)', 'i');
    var m = home.focus.match(re);
    return m ? m[1] : '';
  }

  function renderHome() {
    var host = content(); if (!host || host.dataset.mplHome) return;
    host.dataset.mplHome = '1';
    Promise.all([model(), quizzes(), getJSON(HUB + 'search/courses.json').catch(function () { return []; }), getJSON(HUB + 'search/meta.json').catch(function () { return {}; })]).then(function (r) {
      var M = r[0], Q = r[1], courses = r[2];
      if (!M.lessons.length) return;
      var total = M.lessons.length, minutes = M.lessons.reduce(function (s, l) { return s + l.minutes; }, 0);
      var hours = Math.round(minutes / 60 / 5) * 5 || Math.round(minutes / 60);
      var done = M.lessons.filter(function (l) { return isDone(l.slug); });
      var next = M.lessons.filter(function (l) { return !isDone(l.slug); })[0];
      var me = courses.filter(function (c) { return c.id === META.id; })[0];
      var projects = M.lessons.filter(function (l) { return isProject(l.slug); }).length;
      var quizCount = Object.keys(Q.lessons || {}).length;

      // outcomes: each level's goal (or its focus line from the course table)
      var outcomes = [1, 2, 3, 4].map(function (n) {
        var g = (M.levels[n] && M.levels[n].goal) || levelFocus(M.home, n);
        g = g.replace(/\s*Modules.*$/, ''); return g ? '<li><b>Level ' + n + ' · ' + LEVEL_NAMES[n] + ':</b> ' + esc(g.charAt(0).toUpperCase() + g.slice(1)) + '</li>' : '';
      }).join('');
      // skills: lesson topics (projects excluded), a few per level
      var skills = [];
      [1, 2, 3, 4].forEach(function (n) { M.lessons.filter(function (l) { return l.level === n && !isProject(l.slug); }).slice(0, 4).forEach(function (l) { skills.push(l.title); }); });
      var need = M.home.need ? esc(M.home.need.split(/(?<=[.!?])\s+/).slice(0, 2).join(' ')) : prereqFromPaths(r[3], courses);

      var levelStats = [1, 2, 3, 4].map(function (n) {
        var ls = M.lessons.filter(function (l) { return l.level === n; });
        var d = ls.filter(function (l) { return isDone(l.slug); }).length;
        return { n: n, total: ls.length, done: d, pct: ls.length ? Math.round(100 * d / ls.length) : 0 };
      });
      var scores = Object.keys(Q.lessons || {}).map(function (s) { return storeJSON(quizKey(s)); }).filter(Boolean);
      var avg = scores.length ? Math.round(scores.reduce(function (s, x) { return s + x.best; }, 0) / scores.length) : null;

      var sec = document.createElement('section');
      sec.className = 'mpl-overview';
      sec.setAttribute('aria-label', 'Course overview');
      sec.innerHTML =
        '<div class="mpl-facts">' +
          fact('Difficulty', 'Beginner → Expert', '4 levels') +
          fact('Estimated duration', '≈ ' + hours + ' hours', 'self-paced estimate') +
          fact('Lessons', total, projects + ' projects') +
          fact('Assessments', quizCount ? quizCount + ' module quizzes' : 'Exercises in every lesson', quizCount ? 'with explanations' : 'quizzes coming') +
        '</div>' +
        '<div class="mpl-cols">' +
          '<div><h2>What you will learn</h2><ul class="mpl-outcomes">' + outcomes + '</ul>' +
          '<h2>Prerequisites</h2><p>' + need + '</p>' + recommended(me, courses) + '</div>' +
          '<div class="mpl-progress-card"><h2>Your progress</h2>' + progressHtml(done.length, total, levelStats, avg, scores.length) +
            '<a class="mpl-btn" href="' + esc(next ? next.url : M.lessons[0].url) + '">' + (done.length ? (next ? 'Continue: ' + esc(next.title) : 'Review the course') : 'Start Level 1') + ' →</a>' +
            '<p class="mpl-small">Progress is saved in this browser only. No account needed.</p></div>' +
        '</div>' +
        '<h2>Skills covered</h2><ul class="mpl-chips">' + skills.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('') + '</ul>' +
        '<h2 id="curriculum">Curriculum</h2>' + curriculumHtml(M, Q, next);
      // Place the overview right after the course intro: after the hero lockup (or the H1) and the first paragraph.
      var after = $('.mp-hero-lockup', host) || $('h1', host);
      while (after && after.parentNode !== host) after = after.parentNode;
      if (after && after.nextElementSibling && after.nextElementSibling.tagName === 'P') after = after.nextElementSibling;
      if (after) host.insertBefore(sec, after.nextSibling); else host.prepend(sec);
      bindCurriculum(sec);
    }).catch(function () {});
  }
  // Prerequisites when the course page states none: the courses just before this one on its career paths.
  function prereqFromPaths(meta, courses) {
    var byId = {}; courses.forEach(function (c) { byId[c.id] = c; });
    var before = [];
    Object.keys((meta && meta.paths) || {}).forEach(function (p) {
      var ids = meta.paths[p], i = ids.indexOf(META.id);
      if (i > 0 && before.indexOf(ids[i - 1]) < 0) before.push(ids[i - 1]);
    });
    before = before.filter(function (id) { return byId[id]; }).slice(0, 3);
    if (!before.length) return 'No prior experience needed. Level 1 starts from the basics.';
    return 'Recommended first: ' + before.map(function (id) { return '<a href="' + esc(byId[id].url) + '">' + esc(byId[id].short) + '</a>'; }).join(', ') +
      ' (the step before this course on its career paths). Level 1 still starts from the fundamentals of this subject.';
  }
  function fact(label, value, sub) { return '<div class="mpl-fact"><span>' + esc(label) + '</span><b>' + esc(value) + '</b><small>' + esc(sub) + '</small></div>'; }
  function recommended(me, courses) {
    if (!me || !me.careers || !me.careers.length) return '';
    return '<p class="mpl-small">Part of the career paths: ' + me.careers.slice(0, 3).map(function (c) { return '<a href="' + HUB + 'search/?career=' + encodeURIComponent(c) + '">' + esc(c) + '</a>'; }).join(', ') + '.</p>';
  }
  function progressHtml(done, total, levelStats, avg, nScores) {
    var pct = total ? Math.round(100 * done / total) : 0;
    return '<p class="mpl-big">' + pct + '%<small>' + done + ' of ' + total + ' lessons complete</small></p>' +
      levelStats.map(function (s) { return '<div class="mpl-lvl"><span>Level ' + s.n + ' · ' + LEVEL_NAMES[s.n] + '</span><div class="mpl-bar" role="progressbar" aria-valuenow="' + s.pct + '" aria-valuemin="0" aria-valuemax="100" aria-label="Level ' + s.n + ' progress"><i style="width:' + s.pct + '%"></i></div><small>' + s.done + '/' + s.total + '</small></div>'; }).join('') +
      (avg != null ? '<p class="mpl-small">Average best quiz score: <b>' + avg + '%</b> across ' + nScores + ' quiz' + (nScores === 1 ? '' : 'zes') + '.</p>' : '');
  }
  function curriculumHtml(M, Q, next) {
    return [1, 2, 3, 4].map(function (n) {
      var ls = M.lessons.filter(function (l) { return l.level === n; });
      if (!ls.length) return '';
      var d = ls.filter(function (l) { return isDone(l.slug); }).length;
      var open = next ? next.level === n : n === 1;
      return '<details class="mpl-level"' + (open ? ' open' : '') + '><summary><span class="mpl-lvl-n">' + n + '</span><span class="mpl-lvl-t"><b>Level ' + n + ' · ' + LEVEL_NAMES[n] + '</b><small>' + esc((M.levels[n] && M.levels[n].goal || '').slice(0, 140)) + '</small></span><span class="mpl-lvl-p">' + d + '/' + ls.length + '</span></summary><ol class="mpl-lessons">' +
        ls.map(function (l) {
          var q = storeJSON(quizKey(l.slug)), hasQ = Q.lessons && Q.lessons[l.slug];
          var state = isDone(l.slug) ? 'done' : (next && next.slug === l.slug ? 'next' : 'todo');
          return '<li class="mpl-' + state + '"><span class="mpl-ico" aria-hidden="true">' + (state === 'done' ? '✓' : state === 'next' ? '▶' : '') + '</span><a href="' + esc(l.url) + '">' + esc(l.title) + '</a>' +
            '<span class="mpl-tags">' + (isProject(l.slug) ? '<em class="mpl-tag-p">Project</em>' : '') + (hasQ ? '<em>' + (q ? 'Quiz ' + q.best + '%' : 'Quiz') + '</em>' : '') + '<small>' + l.minutes + ' min</small></span>' +
            '<span class="sr-only">' + (state === 'done' ? ' (completed)' : state === 'next' ? ' (up next)' : '') + '</span></li>';
        }).join('') + '</ol></details>';
    }).join('');
  }
  function bindCurriculum(sec) {
    var levels = $$('.mpl-level', sec);
    var bar = document.createElement('p'); bar.className = 'mpl-curr-tools';
    bar.innerHTML = '<button type="button" data-x="open">Expand all</button> · <button type="button" data-x="close">Collapse all</button>';
    levels[0] && levels[0].parentNode.insertBefore(bar, levels[0]);
    bar.addEventListener('click', function (e) { var x = e.target.dataset.x; if (x) levels.forEach(function (d) { d.open = x === 'open'; }); });
  }

  // ================= LESSON =================
  function renderLesson() {
    var host = content(); if (!host || host.dataset.mplLesson) return;
    host.dataset.mplLesson = '1';
    var h1 = $('h1', host);
    var code = $$('div.highlight pre, pre > code', host).filter(function (el) { return !el.closest('.mpl-quiz'); });
    var codeBlocks = $$('div.highlight', host).length ? $$('div.highlight', host) : $$('pre', host);
    var text = host.textContent || '';
    var mins = Math.max(1, Math.round(words(text) / 200));

    var bar = document.createElement('div');
    bar.className = 'mpl-toolbar';
    bar.innerHTML = '<span>⏱ ' + mins + ' min read</span>' + (codeBlocks.length ? '<button type="button" class="mpl-dl">⬇ Download code examples (' + codeBlocks.length + ')</button>' : '') + '<span class="mpl-docs"></span>';
    if (h1) h1.insertAdjacentElement('afterend', bar);
    var dl = $('.mpl-dl', bar);
    if (dl) dl.addEventListener('click', function () { downloadExamples(codeBlocks); });
    docsLinks().then(function (links) {
      if (!links.length) return;
      $('.mpl-docs', bar).innerHTML = '📘 ' + links.map(function (l) { return '<a href="' + esc(l[1]) + '" target="_blank" rel="noopener">' + esc(l[0]) + '</a>'; }).join(' · ');
    });

    enhanceExercise(host);
    if (isProject(SLUG)) renderProject(host);
    quizzes().then(function (Q) { var q = Q.lessons && Q.lessons[SLUG]; if (q) renderQuiz(host, q, Q.pass_pct || 70); });
  }

  var COMMENT = { python: '#', py: '#', bash: '#', sh: '#', shell: '#', console: '#', yaml: '#', yml: '#', r: '#', ruby: '#', rb: '#', toml: '#', dockerfile: '#', make: '#', perl: '#', powershell: '#', ps1: '#', hcl: '#', terraform: '#',
    javascript: '//', js: '//', typescript: '//', ts: '//', java: '//', c: '//', cpp: '//', 'c++': '//', csharp: '//', cs: '//', go: '//', rust: '//', kotlin: '//', swift: '//', dart: '//', scala: '//', php: '//', jsx: '//', tsx: '//', groovy: '//', json: null,
    sql: '--', lua: '--', haskell: '--', html: '<!--', xml: '<!--', css: '/*', matlab: '%', tex: '%' };
  var EXT = { python: 'py', py: 'py', bash: 'sh', sh: 'sh', shell: 'sh', console: 'sh', javascript: 'js', js: 'js', typescript: 'ts', ts: 'ts', java: 'java', c: 'c', cpp: 'cpp', csharp: 'cs', go: 'go', rust: 'rs', kotlin: 'kt', swift: 'swift', dart: 'dart', scala: 'scala', php: 'php', ruby: 'rb', r: 'R', sql: 'sql', yaml: 'yaml', yml: 'yaml', html: 'html', css: 'css', json: 'json', matlab: 'm', powershell: 'ps1', hcl: 'tf', terraform: 'tf', dockerfile: 'Dockerfile' };
  function langOf(block) {
    var cls = (block.className + ' ' + ((block.querySelector('code') || {}).className || '')).toLowerCase();
    var m = cls.match(/language-([a-z0-9+#-]+)/) || cls.match(/\b(python|bash|javascript|java|sql|yaml|go|rust|cpp|c|csharp|ruby|php|kotlin|swift|typescript|html|css|json)\b/);
    return m ? m[1] : 'text';
  }
  function downloadExamples(blocks) {
    var langs = blocks.map(langOf);
    var main = langs.filter(function (l) { return l !== 'text' && l !== 'console'; })[0] || 'text';
    var mixed = langs.some(function (l) { return l !== main && l !== 'text' && l !== 'console'; });
    var title = ($('h1', content()) || {}).textContent || document.title;
    var parts = [], i = 0;
    blocks.forEach(function (b, k) {
      var code = ((b.querySelector('code') || b).textContent || '').replace(/\s+$/, '');
      if (!code) return;
      i++;
      if (mixed || !EXT[main]) parts.push('### Example ' + i + ' (' + langs[k] + ')\n```' + langs[k] + '\n' + code + '\n```');
      else {
        var c = COMMENT[main] || '#', end = c === '<!--' ? ' -->' : c === '/*' ? ' */' : '';
        parts.push(c + ' --- Example ' + i + (langs[k] !== main ? ' (' + langs[k] + ')' : '') + ' ---' + end + '\n' + code);
      }
    });
    var header = (mixed || !EXT[main]) ? '# ' + title.trim() + '\nSource: ' + location.href + '\n\n' : ((COMMENT[main] || '#') + ' ' + title.trim() + ' — code examples from ' + location.href + (COMMENT[main] === '<!--' ? ' -->' : COMMENT[main] === '/*' ? ' */' : '') + '\n\n');
    var ext = (mixed || !EXT[main]) ? 'md' : EXT[main];
    var blob = new Blob([header + parts.join('\n\n') + '\n'], { type: 'text/plain;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (SLUG || 'lesson').replace(/\//g, '-') + '-examples.' + ext;
    document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    track('download_examples', { course: META.id, lesson: SLUG });
  }

  function sectionAfter(h) { // h2 and everything up to the next h2
    var nodes = [], n = h.nextElementSibling;
    while (n && !/^H[12]$/.test(n.tagName) && !n.classList.contains('mp-mark-done')) { nodes.push(n); n = n.nextElementSibling; }
    return nodes;
  }
  function enhanceExercise(host) {
    var h = $$('h2', host).filter(function (x) { return /^\s*(exercises?|practice|try it|your turn)\b/i.test(x.textContent.replace('¶', '')); })[0];
    if (!h || h.closest('.mpl-exercise')) return;
    var box = document.createElement('div');
    box.className = 'mpl-exercise';
    h.parentNode.insertBefore(box, h);
    var label = document.createElement('p'); label.className = 'mpl-kicker'; label.textContent = 'Practical exercise';
    box.appendChild(label); box.appendChild(h);
    sectionAfter(h).forEach(function (n) { box.appendChild(n); });
    var key = 'mp-notes:' + META.id + ':' + SLUG;
    var notes = document.createElement('details');
    notes.className = 'mpl-notes';
    notes.innerHTML = '<summary>My notes and solution (saved in this browser)</summary><label class="sr-only" for="mpl-notes-ta">My notes</label><textarea id="mpl-notes-ta" rows="6" placeholder="Write your approach, answers or code here. It stays on this device."></textarea>';
    box.appendChild(notes);
    var ta = $('textarea', notes); ta.value = store(key) || '';
    if (ta.value) notes.open = true;
    var t; ta.addEventListener('input', function () { clearTimeout(t); t = setTimeout(function () { store(key, ta.value || null); }, 300); });
  }

  // ---------- module quiz ----------
  function renderQuiz(host, data, passPct, opts) {
    opts = opts || {};
    var QK = opts.key || SLUG;
    if ($(opts.key ? '.mpl-quiz.mpl-final' : '.mpl-quiz:not(.mpl-final)', host)) return;
    var qs = data.questions || [];
    var wrap = document.createElement('section');
    wrap.className = 'mpl-quiz' + (opts.key ? ' mpl-final' : '');
    wrap.setAttribute('aria-labelledby', 'mpl-quiz-h');
    var prev = storeJSON(quizKey(QK));
    wrap.innerHTML = '<p class="mpl-kicker">' + (opts.kicker || 'Module quiz') + '</p><h2 id="mpl-quiz-h">' + (opts.heading || 'Check your understanding') + '</h2>' +
      '<p class="mpl-small">' + qs.length + ' questions. Pass mark ' + passPct + '%. Retry as often as you like; your best score is saved in this browser.' + (prev ? ' Best so far: <b>' + prev.best + '%</b>.' : '') + '</p>' +
      '<form class="mpl-qform">' + qs.map(function (q, i) {
        return '<fieldset class="mpl-q" data-i="' + i + '"><legend><span class="mpl-qn">' + (i + 1) + '.</span> ' + fmt(q.q) + '</legend>' +
          q.options.map(function (o, j) { return '<label class="mpl-opt"><input type="radio" name="q' + i + '" value="' + j + '"> <span>' + fmt(o) + '</span></label>'; }).join('') +
          '<p class="mpl-explain" hidden></p></fieldset>';
      }).join('') +
      '<div class="mpl-qactions"><button type="submit" class="mpl-btn">Check answers</button><button type="button" class="mpl-retry mpl-btn ghost" hidden>Retry quiz</button><p class="mpl-score" role="status" aria-live="polite"></p></div></form>' +
      (data.challenge ? challengeHtml(data.challenge) : '') + (data.challenges || []).map(challengeHtml).join('');
    var anchor = endAnchor(host);
    if (anchor && anchor.parentNode === host) host.insertBefore(wrap, anchor); else host.appendChild(wrap);
    var form = $('.mpl-qform', wrap), score = $('.mpl-score', wrap), retry = $('.mpl-retry', wrap), submit = $('button[type=submit]', wrap);
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var correct = 0, answered = 0;
      qs.forEach(function (q, i) {
        var fs = $('.mpl-q[data-i="' + i + '"]', form), pick = $('input:checked', fs);
        var ok = pick && +pick.value === q.answer;
        if (pick) answered++;
        if (ok) correct++;
        fs.classList.toggle('mpl-right', !!ok); fs.classList.toggle('mpl-wrong', !ok);
        $$('label', fs).forEach(function (l, j) { l.classList.toggle('mpl-correct-opt', j === q.answer); });
        var ex = $('.mpl-explain', fs); ex.hidden = false;
        ex.innerHTML = (ok ? '<b>Correct.</b> ' : '<b>' + (pick ? 'Not quite.' : 'Not answered.') + '</b> Correct answer: ' + fmt(q.options[q.answer]) + '. ') + fmt(q.explain);
        $$('input', fs).forEach(function (inp) { inp.disabled = true; });
      });
      var pct = Math.round(100 * correct / qs.length);
      var best = Math.max(pct, (storeJSON(quizKey(QK)) || {}).best || 0);
      var attempts = ((storeJSON(quizKey(QK)) || {}).attempts || 0) + 1;
      storeJSON(quizKey(QK), { best: best, last: pct, attempts: attempts, at: Date.now() });
      score.innerHTML = '<b>' + correct + ' / ' + qs.length + ' (' + pct + '%)</b> · ' + (pct >= passPct ? '✓ Passed' : 'Below the ' + passPct + '% pass mark. Review the explanations and retry.') + (best > pct ? ' · Best: ' + best + '%' : '');
      submit.hidden = true; retry.hidden = false;
      track('quiz_submit', { course: META.id, lesson: QK, score: pct });
      retry.focus();
    });
    retry.addEventListener('click', function () {
      form.reset();
      $$('.mpl-q', form).forEach(function (fs) { fs.classList.remove('mpl-right', 'mpl-wrong'); $('.mpl-explain', fs).hidden = true; $$('label', fs).forEach(function (l) { l.classList.remove('mpl-correct-opt'); }); $$('input', fs).forEach(function (i) { i.disabled = false; }); });
      score.textContent = ''; submit.hidden = false; retry.hidden = true;
      $('input', form).focus();
    });
    $$('.mpl-copy', wrap).forEach(function (b) { b.addEventListener('click', function () { copy(b); }); });
  }
  function fmt(s) { // escape, then render ```code blocks```, `code` and line breaks
    var blocks = [];
    var t = esc(s).replace(/```(?:[a-z]*\n)?([\s\S]*?)```/g, function (m, c) { blocks.push('<pre><code>' + c.replace(/\n$/, '') + '</code></pre>'); return '\u0000' + (blocks.length - 1) + '\u0000'; });
    t = t.replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\n/g, '<br>');
    return t.replace(/\u0000(\d+)\u0000/g, function (m, i) { return blocks[+i]; });
  }
  function challengeHtml(c) {
    return '<div class="mpl-challenge"><p class="mpl-kicker">Coding challenge</p><h3>' + esc(c.title) + '</h3><p>' + fmt(c.prompt) + '</p>' +
      '<div class="mpl-code"><div class="mpl-code-h"><span>Starter code</span><button type="button" class="mpl-copy" data-src="starter">Copy</button></div><pre><code>' + esc(c.starter) + '</code></pre></div>' +
      '<div class="mpl-code"><div class="mpl-code-h"><span>Expected output</span></div><pre class="mpl-out"><code>' + esc(c.expected) + '</code></pre></div>' +
      '<p class="mpl-small">Run it on your own computer and compare your output. Nothing you write is sent or run on our servers.</p>' +
      '<details class="mpl-sol"><summary>Show solution and explanation</summary><div class="mpl-code"><div class="mpl-code-h"><span>Solution</span><button type="button" class="mpl-copy">Copy</button></div><pre><code>' + esc(c.solution) + '</code></pre></div><p>' + fmt(c.explain) + '</p></details></div>';
  }
  function copy(btn) {
    var pre = btn.closest('.mpl-code').querySelector('pre');
    var text = pre ? pre.textContent : '';
    var done = function () { var o = btn.textContent; btn.textContent = 'Copied ✓'; setTimeout(function () { btn.textContent = o; }, 1500); };
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () { selectText(pre); });
    else selectText(pre);
  }
  function selectText(el) { var r = document.createRange(); r.selectNodeContents(el); var s = getSelection(); s.removeAllRanges(); s.addRange(r); }

  // ---------- level project ----------
  var GENERIC = /^(how it actually works|stretch goals?|see this in another language|cheat sheet|summary|what you learned|next steps|further reading|🔀)/i;
  function renderProject(host) {
    if ($('.mpl-project', host)) return;
    var h2s = $$('h2', host).filter(function (h) { return !h.closest('.mpl-exercise, .mpl-quiz, .mp-related, .mp-su, nav'); });
    var title = function (h) { return h.textContent.replace('¶', '').trim(); };
    var objectiveH = h2s.filter(function (h) { return /what you('|’)?ll build|objective|goal|overview|scenario/i.test(title(h)); })[0];
    // Only from an explicit objective section; otherwise the intro paragraph right below already says it.
    var objective = objectiveH ? sectionAfter(objectiveH).filter(function (n) { return n.tagName === 'P'; })[0] : null;
    var steps = h2s.filter(function (h) { return !GENERIC.test(title(h)) && h !== objectiveH && !/verif|expected|output|final numbers|running it|checklist/i.test(title(h)); });
    var verify = h2s.filter(function (h) { return /verif|expected|output|final numbers|running it|test it|check it/i.test(title(h)); })[0];
    // checklist: the page's own "[ ]" task items, otherwise one item per implementation step
    var tasks = $$('li', host).filter(function (li) { return /^\s*\[[ xX]\]/.test(li.textContent); });
    var items = tasks.length ? tasks.map(function (li) { return li.textContent.replace(/^\s*\[[ xX]\]\s*/, '').replace(/\s+/g, ' ').trim(); }) : steps.map(function (h) { return 'Completed: ' + title(h); });
    if (verify) items.push('Output matches: ' + title(verify));
    var key = 'mp-check:' + META.id + ':' + SLUG, saved = storeJSON(key) || {};
    var src = META.repo && META.src ? META.repo.replace(/\/$/, '') + '/blob/main/docs/' + META.src : '';
    var box = document.createElement('section');
    box.className = 'mpl-project';
    box.setAttribute('aria-label', 'Project brief');
    box.innerHTML = '<p class="mpl-kicker">Level project</p>' +
      (objective ? '<h3>Objective</h3><p>' + esc(objective.textContent.trim()).slice(0, 420) + '</p>' : '') +
      (steps.length ? '<h3>Implementation steps</h3><ol class="mpl-steps">' + steps.map(function (h) { return '<li><a href="#' + esc(h.id) + '">' + esc(title(h)) + '</a></li>'; }).join('') + '</ol>' : '') +
      (verify ? '<p><b>Expected output:</b> see <a href="#' + esc(verify.id) + '">' + esc(title(verify)) + '</a>.</p>' : '') +
      (src ? '<p class="mpl-small">GitHub reference: <a href="' + esc(src) + '" target="_blank" rel="noopener">view this project\'s source on GitHub</a>.</p>' : '');
    var cl = document.createElement('div');
    cl.className = 'mpl-checklist';
    cl.innerHTML = '<h3>Evaluation checklist</h3><p class="mpl-small">Tick each item when your project meets it. Saved in this browser.</p><ul>' +
      items.slice(0, 20).map(function (t, i) { return '<li><label><input type="checkbox" data-i="' + i + '"' + (saved[i] ? ' checked' : '') + '> <span>' + esc(t.slice(0, 220)) + '</span></label></li>'; }).join('') +
      '</ul><p class="mpl-small mpl-cl-count" aria-live="polite"></p>';
    var h1 = $('h1', host), tb = $('.mpl-toolbar', host);
    (tb || h1).insertAdjacentElement('afterend', box);
    var end = $('.mpl-quiz', host) || endAnchor(host);
    if (end && end.parentNode === host) host.insertBefore(cl, end); else host.appendChild(cl);
    var count = function () { var all = $$('input', cl), on = all.filter(function (i) { return i.checked; }).length; $('.mpl-cl-count', cl).textContent = on + ' of ' + all.length + ' criteria met' + (on === all.length && all.length ? ' — great work!' : ''); };
    cl.addEventListener('change', function (e) { if (e.target.dataset.i == null) return; saved[e.target.dataset.i] = e.target.checked; storeJSON(key, saved); count(); });
    count();
  }

  // ================= LEVEL OVERVIEW =================
  function renderLevel() {
    var host = content(); if (!host || host.dataset.mplLevel) return;
    host.dataset.mplLevel = '1';
    var n = +(location.pathname.match(/\/level-(\d+)\/?$/) || [])[1];
    if (!n) return;
    Promise.all([model(), quizzes()]).then(function (r) {
      var M = r[0], Q = r[1];
      var ls = M.lessons.filter(function (l) { return l.level === n; });
      if (!ls.length) return;
      var mins = ls.reduce(function (s, l) { return s + l.minutes; }, 0);
      var next = ls.filter(function (l) { return !isDone(l.slug); })[0];
      var p = document.createElement('div');
      p.className = 'mpl-toolbar';
      p.innerHTML = '<span>📚 ' + ls.length + ' lessons</span><span>⏱ ≈ ' + Math.round(mins / 60) + ' hours</span>' + (Object.keys(Q.lessons || {}).some(function (s) { return s.indexOf('level-' + n + '/') === 0; }) ? '<span>📝 module quizzes</span>' : '') +
        '<a class="mpl-btn sm" href="' + esc((next || ls[0]).url) + '">' + (next && ls.some(function (l) { return isDone(l.slug); }) ? 'Continue: ' + esc(next.title) : next ? 'Start this level' : 'Review this level') + ' →</a>';
      var h1 = $('h1', host); if (h1) h1.insertAdjacentElement('afterend', p);
    }).catch(function () {});
  }

  // ---------- orchestration ----------
  function init() {
    var path = location.pathname.replace(/index\.html$/, '');
    if (META.home) renderHome();
    else if (SLUG) renderLesson();
    else if (/\/level-\d+\/?$/.test(path)) renderLevel();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
