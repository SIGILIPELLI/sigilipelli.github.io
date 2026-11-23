/* Mastery Path certification exam + certificates.
   Used on every course's Final Quiz page (exam), course home (status card) and /verify/ (lookup).
   The exam is set and marked by the API (api.learnmasterypath.com, see the mastery-resume-api repo):
   answers never reach the browser before submission, and each pass is stored under a certificate ID
   that anyone can check at learnmasterypath.com/verify/. */
(function () {
  'use strict';
  if (window.MPCert) return;
  var API = window.MP_API || 'https://api.learnmasterypath.com';
  var HUB = window.MP_HUB || 'https://learnmasterypath.com/';
  var NAME_KEY = 'mp-learner-name';

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
  function saved(course) { try { return JSON.parse(store('mp-cert:' + course)) || null; } catch (e) { return null; } }
  function track(name, params) { try { if (window.gtag) window.gtag('event', name, params || {}); } catch (e) {} }
  function verifyUrl(id) { return HUB + 'verify/?id=' + encodeURIComponent(id); }
  function niceDate(iso) { return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }); }
  // Question text may contain ```code``` blocks and `inline code`.
  function rich(text) {
    return String(text).split(/```[a-z0-9]*\n?/i).map(function (part, i) {
      if (i % 2) return '<pre><code>' + esc(part.replace(/\n$/, '')) + '</code></pre>';
      return esc(part).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\n/g, '<br>');
    }).join('');
  }
  function api(path, body) {
    return fetch(API + path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {})
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { if (!r.ok) throw new Error(d.error || 'Something went wrong. Please try again.'); return d; }); });
  }

  // ---------- styles (work on MkDocs Material pages and on hub pages) ----------
  var css =
    '.mpc{--c-bg:var(--md-default-bg-color,var(--surface,#fff));--c-fg:var(--md-default-fg-color,var(--ink,#0f1d19));--c-sub:var(--md-default-fg-color--light,var(--sub,#4c5d57));' +
    '--c-line:var(--md-default-fg-color--lightest,var(--line,#dbe4e0));--c-brand:var(--md-accent-fg-color,var(--brand,#13785f));--c-soft:var(--md-code-bg-color,var(--surface-2,#eef3f1));' +
    'border:1px solid var(--c-line);border-radius:14px;padding:22px;margin:28px 0;background:var(--c-bg);color:var(--c-fg)}' +
    '.mpc h2{margin:0 0 6px!important;font-size:1.35rem}.mpc .mpc-sub{color:var(--c-sub);margin:0 0 14px}' +
    '.mpc ul.mpc-facts{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 14px!important;padding:0!important;list-style:none!important}.mpc ul.mpc-facts li{margin:0!important;list-style:none!important;padding:4px 10px;border-radius:999px;background:var(--c-soft);font-size:.82rem;font-weight:700}' +
    '.mpc label{display:block;font-weight:700;margin:12px 0 4px}.mpc input[type=text]{width:100%;max-width:420px;padding:10px 12px;border:1.5px solid var(--c-line);border-radius:10px;font:inherit;background:var(--c-bg);color:var(--c-fg)}' +
    '.mpc-check{display:flex!important;gap:8px;align-items:flex-start;font-weight:500!important}.mpc-btn{display:inline-flex;align-items:center;gap:6px;min-height:44px;padding:0 18px;border-radius:10px;border:0;background:var(--c-brand);color:#fff;font-weight:700;font-size:.95rem;font-family:inherit;cursor:pointer;text-decoration:none!important;margin:14px 8px 0 0}' +
    '.mpc a.mpc-btn,.mpc button.mpc-btn{color:#fff!important}.mpc .mpc-btn.ghost{background:transparent;color:var(--c-fg)!important;border:1.5px solid var(--c-line)}.mpc-btn:disabled{opacity:.5;cursor:not-allowed}' +
    '.mpc-bar{position:sticky;top:56px;z-index:3;display:flex;justify-content:space-between;gap:10px;padding:10px 14px;border-radius:10px;background:var(--c-soft);font-weight:700;margin:0 0 14px}' +
    '.mpc-q{border:1px solid var(--c-line);border-radius:12px;padding:14px 16px;margin:0 0 12px}.mpc-q legend{font-weight:700;padding:0 4px}.mpc-q pre{margin:8px 0;font-size:.8rem;overflow-x:auto}' +
    '.mpc-q label{display:flex;gap:10px;align-items:flex-start;font-weight:500;margin:6px 0;padding:8px 10px;border-radius:8px;cursor:pointer}.mpc-q label:hover{background:var(--c-soft)}' +
    '.mpc-q label.ok{background:rgba(19,120,95,.14);font-weight:700}.mpc-q label.bad{background:rgba(180,70,47,.14);text-decoration:line-through}' +
    '.mpc-err{color:#b4462f;font-weight:700;margin:10px 0 0}.mpc-result{padding:16px;border-radius:12px;background:var(--c-soft);margin:0 0 16px}.mpc-result>b{font-size:1.6rem}' +
    '.mpc-cert img{width:100%;max-width:720px;border:1px solid var(--c-line);border-radius:10px;display:block;margin:12px 0}.mpc-small{font-size:.82rem;color:var(--c-sub)}';
  function addCss() { if (document.getElementById('mpc-css')) return; var s = document.createElement('style'); s.id = 'mpc-css'; s.textContent = css; document.head.appendChild(s); }

  // ---------- certificate image ----------
  var sig = new Image();
  var sigReady = new Promise(function (res) { sig.onload = res; sig.onerror = res; });
  sig.crossOrigin = 'anonymous';
  sig.src = HUB + 'assets/signature-vinod.png';

  function wrap(ctx, text, cx, y, max, lh) {
    var words = text.split(' '), line = '', lines = [];
    words.forEach(function (w) { var t = line + w + ' '; if (ctx.measureText(t).width > max && line) { lines.push(line.trim()); line = w + ' '; } else line = t; });
    lines.push(line.trim());
    lines.forEach(function (l, i) { ctx.fillText(l, cx, y + i * lh); });
    return y + lines.length * lh;
  }
  function draw(cert) {
    return sigReady.then(function () {
      var W = 1600, H = 1130, c = document.createElement('canvas'); c.width = W; c.height = H;
      var x = c.getContext('2d'), serif = "Georgia, 'Times New Roman', serif", sans = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
      x.fillStyle = '#FAF7EF'; x.fillRect(0, 0, W, H);
      x.strokeStyle = '#2FA98D'; x.lineWidth = 6; x.strokeRect(36, 36, W - 72, H - 72);
      x.strokeStyle = '#E0B457'; x.lineWidth = 2; x.strokeRect(56, 56, W - 112, H - 112);
      [[0, 24, '#2FA98D'], [17, 40, '#7FC9B7'], [34, 57, '#E0B457'], [51, 74, '#C97B4A']].forEach(function (b) { x.fillStyle = b[2]; x.fillRect(W / 2 - 50 + b[0], 80 + 74 - b[1], 12, b[1]); });
      x.textAlign = 'center';
      x.fillStyle = '#565f52'; x.font = '700 18px ' + serif; x.fillText('M A S T E R Y   P A T H', W / 2, 188);
      x.fillStyle = '#22261f'; x.font = '700 66px ' + serif; x.fillText('C E R T I F I C A T E', W / 2, 300);
      x.fillStyle = '#565f52'; x.font = '700 20px ' + serif; x.fillText('O F   A C H I E V E M E N T', W / 2, 338);
      x.font = '400 22px ' + serif; x.fillText('This certifies that', W / 2, 405);
      x.fillStyle = '#22261f'; x.font = '700 60px ' + serif; x.fillText(cert.name, W / 2, 480);
      var nw = Math.min(x.measureText(cert.name).width + 80, W - 300);
      x.strokeStyle = '#E0B457'; x.lineWidth = 2; x.beginPath(); x.moveTo(W / 2 - nw / 2, 503); x.lineTo(W / 2 + nw / 2, 503); x.stroke();
      x.fillStyle = '#565f52'; x.font = '400 25px ' + serif;
      var y = wrap(x, 'has passed the Mastery Path certification exam for ' + cert.course_name + ' with a score of ' + cert.pct + '% (' + cert.score + ' of ' + cert.total + ') on ' + niceDate(cert.issued) + '.', W / 2, 560, W - 360, 36);
      x.font = '400 19px ' + serif;
      wrap(x, 'The exam is ' + cert.total + ' questions drawn at random from all four levels of the course, set and marked by Mastery Path.', W / 2, y + 8, W - 420, 28);
      var sw = 260, sh = sig.naturalWidth ? Math.round(sw * sig.naturalHeight / sig.naturalWidth) : 0, sy = 840;
      if (sh) x.drawImage(sig, W / 2 - sw / 2, sy - sh, sw, sh);
      x.strokeStyle = '#565f52'; x.lineWidth = 1; x.beginPath(); x.moveTo(W / 2 - 150, sy + 22); x.lineTo(W / 2 + 150, sy + 22); x.stroke();
      x.fillStyle = '#22261f'; x.font = '700 22px ' + serif; x.fillText('VINOD KUMAR S', W / 2, sy + 54);
      x.fillStyle = '#565f52'; x.font = '600 13px ' + sans; x.fillText('F O U N D E R ,   M A S T E R Y   P A T H', W / 2, sy + 78);
      x.fillStyle = '#22261f'; x.font = '700 17px ' + sans; x.fillText('Certificate ID: ' + cert.id + '   ·   Verify at learnmasterypath.com/verify', W / 2, H - 112);
      x.fillStyle = '#8a917f'; x.font = '400 14px ' + sans;
      x.fillText('Issued by Mastery Path, a free online learning platform. Online, unproctored exam. Not an accredited academic or professional qualification.', W / 2, H - 84);
      return c;
    });
  }
  function download(cert) {
    return draw(cert).then(function (c) {
      var a = document.createElement('a'); a.href = c.toDataURL('image/png'); a.download = cert.course + '-certificate-' + cert.id + '.png';
      document.body.appendChild(a); a.click(); a.remove();
    });
  }
  function linkedInUrl(cert) {
    var d = new Date(cert.issued);
    return 'https://www.linkedin.com/profile/add?startTask=CERTIFICATION_NAME&name=' + encodeURIComponent(cert.course_name + ' Certification Exam') +
      '&organizationName=' + encodeURIComponent('Mastery Path') + '&issueYear=' + d.getFullYear() + '&issueMonth=' + (d.getMonth() + 1) +
      '&certUrl=' + encodeURIComponent(verifyUrl(cert.id)) + '&certId=' + encodeURIComponent(cert.id);
  }

  /** Certificate preview + actions. */
  function certBlock(cert) {
    var box = document.createElement('div');
    box.className = 'mpc-cert';
    box.innerHTML = '<p class="mpc-small">Certificate ID <b>' + esc(cert.id) + '</b> · issued ' + esc(niceDate(cert.issued)) + ' · anyone can check it at <a href="' + esc(verifyUrl(cert.id)) + '">learnmasterypath.com/verify</a></p>' +
      '<div class="mpc-img"></div>' +
      '<button type="button" class="mpc-btn" data-a="dl">⬇ Download certificate (PNG)</button>' +
      '<a class="mpc-btn ghost" href="' + esc(linkedInUrl(cert)) + '" target="_blank" rel="noopener">Add to LinkedIn</a>' +
      '<button type="button" class="mpc-btn ghost" data-a="copy">Copy verify link</button>';
    draw(cert).then(function (c) { var img = new Image(); img.alt = 'Certificate for ' + cert.name + ', ' + cert.course_name; img.src = c.toDataURL('image/png'); box.querySelector('.mpc-img').appendChild(img); });
    box.addEventListener('click', function (e) {
      var a = e.target.dataset && e.target.dataset.a;
      if (a === 'dl') { download(cert); track('certificate_download', { course: cert.course }); }
      if (a === 'copy') { try { navigator.clipboard.writeText(verifyUrl(cert.id)); e.target.textContent = 'Link copied ✓'; } catch (err) { prompt('Verify link', verifyUrl(cert.id)); } }
    });
    return box;
  }

  // ---------- exam ----------
  function mountExam(host, opts) {
    addCss();
    var course = opts.course, courseName = opts.courseName || course;
    var sec = document.createElement('section');
    sec.className = 'mpc'; sec.id = 'certification';
    host.appendChild(sec);
    var timer = null;

    function intro(msg) {
      clearInterval(timer);
      var have = saved(course);
      sec.innerHTML = '<h2>🎓 Certification exam</h2>' +
        '<p class="mpc-sub">The practice quiz above is open-book with the answers in the page. The certification exam is different: questions are drawn at random from all four levels, and your answers are marked on our server. Pass it to get a certificate with an ID that employers can check.</p>' +
        '<ul class="mpc-facts"><li>25 questions</li><li>40 minutes</li><li>70% to pass</li><li>Free</li><li>No account</li></ul>' +
        (have ? '<p><b>✅ You passed on ' + esc(niceDate(have.issued)) + ' with ' + have.pct + '%.</b></p>' : '') +
        '<div class="mpc-have"></div>' +
        '<form class="mpc-start"><label for="mpc-name">Your full name, as it should appear on the certificate</label>' +
        '<input id="mpc-name" type="text" maxlength="60" autocomplete="name" required value="' + esc(store(NAME_KEY) || '') + '">' +
        '<label class="mpc-check"><input type="checkbox" required> I will take this exam myself, without help from other people or AI tools.</label>' +
        '<button class="mpc-btn" type="submit">' + (have ? 'Take the exam again' : 'Start the exam') + '</button>' +
        '<p class="mpc-err" role="alert">' + esc(msg || '') + '</p>' +
        '<p class="mpc-small">Your name and score are stored with the certificate so it can be verified. Certificates are issued by Mastery Path and are not accredited qualifications. See the <a href="' + HUB + 'privacy.html">privacy policy</a>.</p></form>';
      if (have) sec.querySelector('.mpc-have').appendChild(certBlock(have));
      sec.querySelector('form').addEventListener('submit', function (e) {
        e.preventDefault();
        var name = sec.querySelector('#mpc-name').value.trim();
        store(NAME_KEY, name);
        var btn = sec.querySelector('.mpc-start button'); btn.disabled = true; btn.textContent = 'Preparing your exam…';
        api('/api/exam/start', { course: course }).then(function (ex) { track('exam_start', { course: course }); run(ex, name); })
          .catch(function (err) { intro(err.message); });
      });
    }

    function run(ex, name) {
      var deadline = Date.now() + ex.minutes * 60000;
      sec.innerHTML = '<h2>🎓 ' + esc(courseName) + ' certification exam</h2>' +
        '<div class="mpc-bar"><span class="mpc-count">0 / ' + ex.questions.length + ' answered</span><span class="mpc-time"></span></div>' +
        '<form class="mpc-form">' + ex.questions.map(function (q, i) {
          return '<fieldset class="mpc-q"><legend>Question ' + (i + 1) + '</legend><div>' + rich(q.q) + '</div>' +
            q.options.map(function (o, j) { return '<label><input type="radio" name="q' + i + '" value="' + j + '"><span>' + rich(o) + '</span></label>'; }).join('') + '</fieldset>';
        }).join('') + '<button class="mpc-btn" type="submit">Submit answers</button><p class="mpc-err" role="alert"></p></form>';
      var form = sec.querySelector('form'), count = sec.querySelector('.mpc-count'), clock = sec.querySelector('.mpc-time');
      function answers() { return ex.questions.map(function (q, i) { var c = form.querySelector('input[name=q' + i + ']:checked'); return c ? +c.value : -1; }); }
      form.addEventListener('change', function () { count.textContent = answers().filter(function (a) { return a >= 0; }).length + ' / ' + ex.questions.length + ' answered'; });
      function tick() {
        var left = Math.max(0, deadline - Date.now()), m = Math.floor(left / 60000), s = Math.floor(left / 1000) % 60;
        clock.textContent = '⏱ ' + m + ':' + (s < 10 ? '0' : '') + s + ' left';
        if (!left) { clearInterval(timer); submit(true); }
      }
      timer = setInterval(tick, 1000); tick();
      sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
      function submit(auto) {
        var a = answers(), blank = a.filter(function (x) { return x < 0; }).length;
        if (!auto && blank && !confirm(blank + ' question(s) are unanswered. Submit anyway?')) return;
        clearInterval(timer);
        var btn = form.querySelector('button'); btn.disabled = true; btn.textContent = 'Marking…';
        api('/api/exam/submit', { exam_id: ex.exam_id, answers: a, name: name }).then(function (r) { result(r, a); })
          .catch(function (err) { form.querySelector('.mpc-err').textContent = err.message; btn.textContent = 'Submit answers'; btn.disabled = /expired|Time is up/i.test(err.message); if (btn.disabled) setTimeout(function () { intro(err.message); }, 2500); });
      }
      form.addEventListener('submit', function (e) { e.preventDefault(); submit(false); });
    }

    function result(r, chosen) {
      track('exam_submit', { course: course, pct: r.pct, passed: r.passed });
      var qs = sec.querySelectorAll('.mpc-q');
      qs.forEach(function (fs, i) {
        fs.querySelectorAll('input').forEach(function (inp) { inp.disabled = true; });
        var labels = fs.querySelectorAll('label');
        if (labels[r.correct[i]]) labels[r.correct[i]].className = 'ok';
        if (chosen[i] >= 0 && chosen[i] !== r.correct[i] && labels[chosen[i]]) labels[chosen[i]].className = 'bad';
      });
      var form = sec.querySelector('form'); form.querySelector('button').remove();
      var box = document.createElement('div');
      box.className = 'mpc-result';
      box.innerHTML = r.passed
        ? '<b>🎉 You passed: ' + r.pct + '%</b><p>' + r.score + ' of ' + r.total + ' correct. Your certificate is ready below. Correct answers are highlighted in each question.</p>'
        : '<b>' + r.pct + '%: not a pass this time</b><p>' + r.score + ' of ' + r.total + ' correct; ' + r.pass_pct + '% is needed. Correct answers are highlighted below. Review those lessons, then take a new exam (the questions change each time).</p>';
      var again = document.createElement('button'); again.type = 'button'; again.className = 'mpc-btn ghost'; again.textContent = r.passed ? 'Back' : 'Try a new exam';
      again.addEventListener('click', function () { intro(); sec.scrollIntoView({ block: 'start' }); });
      if (r.passed && r.certificate) {
        store('mp-cert:' + course, JSON.stringify(r.certificate));
        track('certificate_earned', { course: course });
        box.appendChild(certBlock(r.certificate));
      }
      box.appendChild(again);
      sec.insertBefore(box, sec.querySelector('.mpc-bar'));
      sec.querySelector('.mpc-bar').remove();
      sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    intro();
  }

  /** Small status card for the course home page. */
  function homeCard(host, opts) {
    addCss();
    var have = saved(opts.course);
    var card = document.createElement('div');
    card.className = 'mpc'; card.style.padding = '16px'; card.style.margin = '14px 0 0';
    card.innerHTML = have
      ? '<b>🎓 Certificate earned</b><p class="mpc-small" style="margin:4px 0 0">Passed ' + esc(niceDate(have.issued)) + ' with ' + have.pct + '% · ID ' + esc(have.id) + '</p><a class="mpc-btn" href="' + esc(opts.examUrl) + '">View certificate</a><a class="mpc-btn ghost" href="' + esc(verifyUrl(have.id)) + '">Verify link</a>'
      : '<b>🎓 Earn a verified certificate</b><p class="mpc-small" style="margin:4px 0 0">Finish the levels, then pass the 25-question certification exam (70%). Free, no account, with a public verify link.</p><a class="mpc-btn" href="' + esc(opts.examUrl) + '">Go to the certification exam →</a>';
    host.appendChild(card);
  }

  window.MPCert = { mountExam: mountExam, homeCard: homeCard, draw: draw, download: download, certBlock: certBlock, verifyUrl: verifyUrl, niceDate: niceDate, api: api, addCss: addCss };
})();
