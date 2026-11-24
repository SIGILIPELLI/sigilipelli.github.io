/* Mastery Path site search: courses + lessons, instant suggestions, typo tolerance, filters, local history.
 * Index files are built automatically by tools/build_search_index.py (GitHub Action, every 6 hours).
 *   MPSearch.ready()                    -> Promise (courses + meta loaded; lessons load on first search)
 *   MPSearch.query(q, filters, {limit}) -> { courses, lessons, total, ms }
 *   MPSearch.attachSuggest(input, box)  -> instant suggestions dropdown with keyboard navigation
 */
(function () {
  'use strict';
  var BASE = (document.currentScript && document.currentScript.src.replace(/assets\/search\.js.*$/, '')) || '/';
  var LEVELS = { 1: 'Beginner', 2: 'Intermediate', 3: 'Advanced', 4: 'Expert' };
  var HISTORY_KEY = 'mp-search-history';

  // ---------- text normalisation ----------
  var STOP = {};
  'a an and are as at be by for from how in into is it of on or the to with what why your you'.split(' ').forEach(function (w) { STOP[w] = 1; });
  function norm(s) {
    return String(s || '').toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/c\+\+/g, ' cpp ').replace(/c#/g, ' csharp ').replace(/\.net\b/g, ' dotnet ')
      .replace(/\b(node|next|vue|react)\.js\b/g, '$1js')
      .replace(/[^a-z0-9]+/g, ' ').trim();
  }
  function tokens(s, keepStop) {
    return norm(s).split(' ').filter(function (t) { return t && (keepStop || !STOP[t]); });
  }

  // ---------- state ----------
  var courses = [], meta = null, lessonRows = null;
  var docs = [];                 // {kind, c (course index), l (level), title, url, desc, topics, titleN}
  var index = new Map();         // token -> Map(docIdx -> weight)
  var vocab = [];                // all tokens, for typo matching
  var readyP = null, lessonsP = null;

  function addField(doc, text, weight) {
    tokens(text).forEach(function (t) {
      var m = index.get(t);
      if (!m) { m = new Map(); index.set(t, m); }
      if ((m.get(doc) || 0) < weight) m.set(doc, weight);
    });
  }
  function rebuildVocab() { vocab = Array.from(index.keys()); }

  function ready() {
    if (readyP) return readyP;
    readyP = Promise.all([
      fetch(BASE + 'search/courses.json').then(function (r) { return r.json(); }),
      fetch(BASE + 'search/meta.json').then(function (r) { return r.json(); }),
    ]).then(function (res) {
      courses = res[0]; meta = res[1];
      courses.forEach(function (c, i) {
        var d = docs.length;
        docs.push({ kind: 'course', c: i, title: c.name, url: c.url, desc: c.desc, titleN: norm(c.name + ' ' + c.short) });
        addField(d, c.name, 10); addField(d, c.short, 12); addField(d, c.aliases.join(' '), 9);
        addField(d, c.careers.join(' '), 5); addField(d, c.catName + ' ' + c.type, 3.5); addField(d, c.desc, 2);
      });
      // Course resources (interview questions, cheat sheet): shown with lessons, ranked by their own title.
      courses.forEach(function (c, i) {
        (c.res || []).forEach(function (r) {
          var d = docs.length;
          docs.push({ kind: 'resource', c: i, title: r[0], url: c.url + r[1], desc: /interview/i.test(r[1]) ? 'Questions with answers and explanations, beginner to advanced.' : 'Quick-reference tables from every level of the course.', titleN: norm(r[0]) });
          addField(d, r[0], 8); addField(d, c.short, 5); addField(d, c.aliases.join(' '), 2);
          addField(d, /interview/i.test(r[1]) ? 'interview questions answers prep' : 'cheat sheet quick reference', 6);
        });
      });
      rebuildVocab();
    });
    return readyP;
  }

  function loadLessons() {
    if (lessonsP) return lessonsP;
    lessonsP = ready().then(function () {
      return fetch(BASE + 'search/lessons.json').then(function (r) { return r.json(); });
    }).then(function (data) {
      lessonRows = data.rows;
      lessonRows.forEach(function (r) {
        var c = courses[r[0]], d = docs.length;
        var title = r[2].replace(/^\d+\s*·\s*/, '');
        docs.push({ kind: 'lesson', c: r[0], l: r[1], title: title, url: c.url + 'level-' + r[1] + '/' + r[3], desc: r[4], topics: r[5], titleN: norm(title) });
        addField(d, title, 7); addField(d, r[5], 3.5); addField(d, r[4], 1.5);
        addField(d, c.short, 4); addField(d, c.aliases.join(' '), 1.5);
      });
      rebuildVocab();
    });
    return lessonsP;
  }

  // ---------- typo tolerance ----------
  function within(a, b, max) { // Damerau-Levenshtein with early exit
    var la = a.length, lb = b.length;
    if (Math.abs(la - lb) > max) return false;
    var prev2 = null, prev = [], cur, i, j;
    for (j = 0; j <= lb; j++) prev[j] = j;
    for (i = 1; i <= la; i++) {
      cur = [i]; var rowMin = i;
      for (j = 1; j <= lb; j++) {
        var cost = a[i - 1] === b[j - 1] ? 0 : 1;
        var v = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
        if (prev2 && i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) v = Math.min(v, prev2[j - 2] + 1);
        cur[j] = v; if (v < rowMin) rowMin = v;
      }
      if (rowMin > max) return false;
      prev2 = prev; prev = cur;
    }
    return prev[lb] <= max;
  }

  var termCache = new Map();
  function expand(qt, isLast) { // -> [[term, factor]]
    var key = qt + (isLast ? '|L' : '');
    if (termCache.has(key)) return termCache.get(key);
    var out = [];
    if (index.has(qt)) out.push([qt, 1]);
    if (qt.length >= 2) {
      var n = 0;
      for (var i = 0; i < vocab.length && n < 60; i++) {
        var v = vocab[i];
        if (v !== qt && v.length > qt.length && v.lastIndexOf(qt, 0) === 0) { out.push([v, isLast ? 0.85 : 0.7]); n++; }
      }
    }
    if (qt.length >= 4 && out.length < 3) {
      var max = qt.length >= 8 ? 2 : 1;
      for (var k = 0; k < vocab.length; k++) {
        var w = vocab[k];
        if (w !== qt && w[0] === qt[0] && within(qt, w, max)) out.push([w, within(qt, w, 1) ? 0.62 : 0.5]);
      }
    }
    termCache.set(key, out);
    return out;
  }

  // ---------- query ----------
  function passes(doc, f) {
    var c = courses[doc.c];
    if (f.cat && c.cat !== f.cat) return false;
    if (f.type && c.type !== f.type) return false;
    if (f.career && c.careers.indexOf(f.career) < 0) return false;
    if (f.tech && c.id !== f.tech) return false;
    if (f.level && doc.kind !== 'course' && String(doc.l) !== String(f.level)) return false;
    if (f.kind && doc.kind !== f.kind) return false;
    return true;
  }

  function query(q, filters, opts) {
    var t0 = performance.now();
    filters = filters || {}; opts = opts || {};
    var qts = tokens(q);
    var scores = new Map(), hitCount = new Map();
    var corrected = false;
    qts.forEach(function (qt, qi) {
      var best = new Map();
      expand(qt, qi === qts.length - 1).forEach(function (pair) {
        if (pair[1] < 0.65) corrected = true;
        var post = index.get(pair[0]);
        if (!post) return;
        post.forEach(function (w, d) {
          var s = w * pair[1];
          if ((best.get(d) || 0) < s) best.set(d, s);
        });
      });
      best.forEach(function (s, d) {
        scores.set(d, (scores.get(d) || 0) + s);
        hitCount.set(d, (hitCount.get(d) || 0) + 1);
      });
    });
    var qn = norm(q), list = [];
    var need = qts.length;
    function collect(minHits) {
      list = [];
      scores.forEach(function (s, d) {
        if (hitCount.get(d) < minHits) return;
        var doc = docs[d];
        if (!passes(doc, filters)) return;
        var bonus = 0;
        if (qn && doc.titleN === qn) bonus += 12;
        else if (qn && (' ' + doc.titleN + ' ').indexOf(' ' + qn) >= 0) bonus += 5;
        if (doc.kind === 'course') bonus += 3;
        list.push({ d: d, s: s * (hitCount.get(d) / need) + bonus });
      });
    }
    if (need) {
      collect(need);
      if (!list.length && need > 1) collect(Math.max(1, need - 1));
    } else {
      // filter-only browsing: list matching courses (and, with a level or course filter, their lessons)
      docs.forEach(function (doc, d) {
        if (!passes(doc, filters)) return;
        if (doc.kind !== 'course' && !(filters.level || filters.tech)) return;
        list.push({ d: d, s: doc.kind === 'course' ? 2 : 1 - d / 1e6 });
      });
    }
    list.sort(function (a, b) { return b.s - a.s; });
    var cs = [], ls = [];
    list.forEach(function (x) { (docs[x.d].kind === 'course' ? cs : ls).push(view(docs[x.d], qts)); });
    var lim = opts.limit || 1e9;
    return { courses: cs.slice(0, opts.courseLimit || lim), lessons: ls.slice(0, lim), totalCourses: cs.length, totalLessons: ls.length, corrected: corrected, ms: performance.now() - t0, lessonsLoaded: !!lessonRows };
  }

  function view(doc, qts) {
    var c = courses[doc.c];
    return {
      kind: doc.kind, title: doc.title, url: doc.url, desc: doc.desc, topics: doc.topics || '',
      course: c.name, courseShort: c.short, emoji: c.emoji, courseUrl: c.url, category: c.catName, type: c.type, careers: c.careers,
      level: doc.kind === 'lesson' ? LEVELS[doc.l] : doc.kind === 'resource' ? 'All levels' : 'Beginner → Expert', levelN: doc.l || 0, lessons: c.lessons, projects: c.projects || 0, capstones: c.capstones || 0, terms: qts,
    };
  }

  // ---------- helpers for UIs ----------
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (ch) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]; }); }
  function highlight(text, terms) {
    var out = esc(text);
    (terms || []).filter(function (t) { return t.length >= 2; }).forEach(function (t) {
      out = out.replace(new RegExp('\\b(' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '[a-z0-9]*)', 'gi'), '<mark>$1</mark>');
    });
    return out;
  }
  var history = {
    get: function () { try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; } catch (e) { return []; } },
    add: function (q) {
      q = String(q || '').trim(); if (q.length < 2) return;
      try { var h = history.get().filter(function (x) { return x.toLowerCase() !== q.toLowerCase(); }); h.unshift(q); localStorage.setItem(HISTORY_KEY, JSON.stringify(h.slice(0, 8))); } catch (e) {}
    },
    clear: function () { try { localStorage.removeItem(HISTORY_KEY); } catch (e) {} },
  };

  // ---------- instant suggestions (home page and anywhere else) ----------
  var uid = 0;
  function attachSuggest(input, box, opts) {
    opts = opts || {};
    var searchPage = opts.searchPage || (BASE + 'search/');
    var id = 'mps-' + (++uid), active = -1, timer = null, items = [];
    box.id = box.id || id + '-list';
    box.setAttribute('role', 'listbox');
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-controls', box.id);
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('enterkeyhint', 'search');
    var live = document.createElement('div');
    live.className = 'mps-live'; live.setAttribute('aria-live', 'polite');
    live.style.cssText = 'position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)';
    input.parentNode.appendChild(live);

    function open(html) { box.innerHTML = html; box.hidden = false; input.setAttribute('aria-expanded', 'true'); items = Array.prototype.slice.call(box.querySelectorAll('[role="option"]')); setActive(-1); }
    function close() { box.hidden = true; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); active = -1; }
    function setActive(i) {
      active = i;
      items.forEach(function (el, k) { el.classList.toggle('active', k === i); el.setAttribute('aria-selected', String(k === i)); });
      if (i >= 0) { input.setAttribute('aria-activedescendant', items[i].id); items[i].scrollIntoView({ block: 'nearest' }); } else input.removeAttribute('aria-activedescendant');
    }
    function opt(i, href, inner, extra) { return '<a role="option" id="' + id + '-o' + i + '" href="' + esc(href) + '" ' + (extra || '') + '>' + inner + '</a>'; }
    function allLink(q, i) { return opt(i, searchPage + '?q=' + encodeURIComponent(q), '<span class="search-result-title">See all results for “' + esc(q) + '” →</span>', 'class="mps-all" data-q="' + esc(q) + '"'); }

    function showEmpty() {
      ready().then(function () {
        var h = history.get(), i = 0, html = '';
        if (h.length) {
          html += '<div class="mps-head">Recent searches <button type="button" class="mps-clear">Clear</button></div>';
          html += h.map(function (q) { return opt(i++, searchPage + '?q=' + encodeURIComponent(q), '<span class="search-result-title">🕘 ' + esc(q) + '</span>', 'data-q="' + esc(q) + '"'); }).join('');
        }
        html += '<div class="mps-head">Try</div>' + meta.suggested.map(function (q) { return opt(i++, searchPage + '?q=' + encodeURIComponent(q), '<span class="search-result-title">' + esc(q) + '</span>', 'data-q="' + esc(q) + '"'); }).join('');
        open(html);
        var clr = box.querySelector('.mps-clear');
        if (clr) clr.addEventListener('mousedown', function (e) { e.preventDefault(); history.clear(); showEmpty(); });
      });
    }

    function run() {
      var q = input.value.trim();
      if (!q) return showEmpty();
      ready().then(function () {
        var r = query(q, {}, { courseLimit: 4, limit: 6 });
        var i = 0, html = '';
        if (r.courses.length) html += '<div class="mps-head">Courses</div>' + r.courses.map(function (x) {
          return opt(i++, x.url, '<span class="search-result-title">' + esc(x.emoji) + ' ' + highlight(x.courseShort, x.terms) + '</span><span class="search-result-site">' + esc(x.category) + ' · ' + x.lessons + ' lessons' + (x.projects ? ' + ' + x.projects + ' projects' : '') + (x.capstones ? ' + ' + x.capstones + ' capstone' : '') + '</span>', 'data-q="' + esc(q) + '"');
        }).join('');
        if (r.lessons.length) html += '<div class="mps-head">Lessons</div>' + r.lessons.map(function (x) {
          return opt(i++, x.url, '<span class="search-result-title">' + highlight(x.title, x.terms) + '</span><span class="search-result-site">' + esc(x.courseShort) + ' · ' + esc(x.level) + '</span>', 'data-q="' + esc(q) + '"');
        }).join('');
        if (!r.lessonsLoaded) html += '<div class="mps-head mps-loading">Searching lessons…</div>';
        if (!r.courses.length && !r.lessons.length && r.lessonsLoaded) html += '<div class="search-empty">No matches yet. Try a broader word, like a language or tool name.</div>';
        html += allLink(q, i++);
        open(html);
        live.textContent = r.lessonsLoaded ? (r.totalCourses + ' courses and ' + r.totalLessons + ' lessons found') : '';
      });
    }

    input.addEventListener('focus', function () { loadLessons(); if (!input.value.trim()) showEmpty(); else run(); });
    input.addEventListener('input', function () {
      clearTimeout(timer); timer = setTimeout(run, 60);
      if (!lessonRows) loadLessons().then(function () { if (document.activeElement === input) run(); });
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); if (box.hidden) run(); else setActive(Math.min(active + 1, items.length - 1)); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(Math.max(active - 1, -1)); }
      else if (e.key === 'Escape') { if (!box.hidden) { e.preventDefault(); close(); } }
      else if (e.key === 'Enter') {
        e.preventDefault();
        var q = input.value.trim();
        if (active >= 0) { history.add(items[active].getAttribute('data-q') || q); window.location.href = items[active].href; }
        else if (q) { history.add(q); window.location.href = searchPage + '?q=' + encodeURIComponent(q); }
      }
    });
    box.addEventListener('mousedown', function (e) { // keep focus so the click lands
      var a = e.target.closest('[role="option"]'); if (a) history.add(a.getAttribute('data-q') || input.value);
    });
    document.addEventListener('click', function (e) { if (!box.contains(e.target) && e.target !== input) close(); });
  }

  window.MPSearch = { ready: ready, loadLessons: loadLessons, query: query, attachSuggest: attachSuggest, history: history, highlight: highlight, esc: esc, meta: function () { return meta; }, courses: function () { return courses; }, LEVELS: LEVELS };
})();
