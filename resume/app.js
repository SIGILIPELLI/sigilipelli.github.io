// Mastery Path Resume Tools: free scan in the browser, paid services via Razorpay + the API worker.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const isLocal = /^(localhost|127\.0\.0\.1)$/.test(location.hostname);
  const API = (isLocal && new URLSearchParams(location.search).get('api')) || 'https://api.learnmasterypath.com';
  const KEYS = { draft: 'mpr:draft', last: 'mpr:last', pending: 'mpr:pending' };
  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
    del(k) { try { localStorage.removeItem(k); } catch {} },
  };
  const LABELS = { report: 'ATS Report', tailor: 'Tailored Resume', pack: 'Complete Job Pack' };
  const PRICES = { report: 11, tailor: 44, pack: 77 };

  const resumeEl = $('#resume');
  const jobEl = $('#job');

  function status(msg, kind = '', spin = false) {
    const el = $('#status');
    if (!msg) { el.hidden = true; return; }
    el.hidden = false;
    el.className = `status ${kind}`;
    el.innerHTML = (spin ? '<span class="spinner"></span>' : '') + msg;
  }

  async function api(path, body) {
    const res = await fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    let data = {};
    try { data = await res.json(); } catch {}
    if (!res.ok) throw Object.assign(new Error(data.error || `Request failed (${res.status})`), { status: res.status });
    return data;
  }

  function inputs() {
    const resume = resumeEl.value.trim();
    const job = jobEl.value.trim();
    if (resume.length < 200) throw new Error('Please paste your full resume first (at least a few lines).');
    if (job.length < 150) throw new Error('Please paste the full job description first.');
    return { resume, job };
  }

  // ---------- drafts & counters ----------
  const draft = store.get(KEYS.draft);
  if (draft) { resumeEl.value = draft.resume || ''; jobEl.value = draft.job || ''; }
  function count() {
    $$('[data-count]').forEach((el) => { el.textContent = ($('#' + el.dataset.count).value.length).toLocaleString(); });
    store.set(KEYS.draft, { resume: resumeEl.value, job: jobEl.value });
  }
  resumeEl.addEventListener('input', count);
  jobEl.addEventListener('input', count);
  count();

  // ---------- upload (parsed in the browser) ----------
  $('#resume-file').addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) return status('That file is too large (max 5 MB).', 'error');
    status(`Reading ${esc(file.name)}…`, '', true);
    try {
      const buf = await file.arrayBuffer();
      let text = '';
      if (/\.pdf$/i.test(file.name) || file.type === 'application/pdf') {
        const lib = window.pdfjsLib;
        lib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
        const pdf = await lib.getDocument({ data: buf }).promise;
        for (let i = 1; i <= pdf.numPages; i++) {
          const page = await pdf.getPage(i);
          const tc = await page.getTextContent();
          let line = '';
          for (const item of tc.items) { line += item.str + (item.hasEOL ? '\n' : ' '); }
          text += line + '\n';
        }
      } else if (/\.docx$/i.test(file.name)) {
        text = (await window.mammoth.extractRawText({ arrayBuffer: buf })).value;
      } else {
        text = new TextDecoder().decode(buf);
      }
      text = text.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
      if (text.length < 50) throw new Error('We could not read text from that file. If it is a scanned image, paste the text instead.');
      resumeEl.value = text.slice(0, 20000);
      count();
      status('Resume loaded. Check the text, then paste the job description.', 'ok');
    } catch (err) {
      status(esc(err.message || 'Could not read that file.'), 'error');
    }
  });

  // ---------- free ATS scan ----------
  const ring = (n, label) => `<div class="score-row"><div class="score" style="--p:${Number(n) || 0}"><span>${Number(n) || 0}</span></div><div><strong>${esc(label)}</strong></div></div>`;
  const chips = (list, cls = '') => (list && list.length ? `<ul class="chips ${cls}">${list.map((k) => `<li>${esc(k)}</li>`).join('')}</ul>` : '<p class="muted small">None</p>');

  $('#scan-btn').addEventListener('click', () => {
    let v;
    try { v = inputs(); } catch (err) { return status(esc(err.message), 'error'); }
    status('');
    const r = window.MPATS.atsScan(v.resume, v.job);
    const out = $('#scan-out');
    out.hidden = false;
    out.innerHTML = `<div class="card" style="margin-top:16px">
      ${ring(r.score, `${r.matched.length} of ${r.keywordCount} key terms from the job are in your resume`)}
      <h3>Missing keywords</h3>${chips(r.missing, 'bad')}
      <h3>Matched keywords</h3>${chips(r.matched, 'good')}
      <h3>Format checks</h3><ul class="checks">${r.checks.map((c) => `<li class="${c.pass ? 'pass' : 'fail'}">${esc(c.label)}</li>`).join('')}</ul>
      <p style="margin-top:14px"><a class="btn" href="#plans">Fix it for this job</a></p>
    </div>`;
    out.scrollIntoView({ behavior: 'smooth', block: 'start' });
    if (window.gtag) gtag('event', 'ats_scan', { score: r.score });
  });

  // ---------- paid services ----------
  async function buy(tier) {
    let v;
    try { v = inputs(); } catch (err) { status(esc(err.message), 'error'); $('#tool').scrollIntoView({ behavior: 'smooth' }); return; }
    if (!window.Razorpay) return status('Payment window is still loading. Please try again in a moment.', 'error');
    const btn = $(`[data-buy="${tier}"]`);
    btn.disabled = true;
    try {
      const order = await api('/api/order', { tier });
      const rz = new window.Razorpay({
        key: order.key_id,
        order_id: order.order_id,
        amount: order.amount,
        currency: 'INR',
        name: 'Mastery Path',
        description: `${LABELS[tier]} (one job)`,
        theme: { color: '#2FA98D' },
        handler: (resp) => {
          const pending = { tier, order_id: resp.razorpay_order_id, payment_id: resp.razorpay_payment_id, signature: resp.razorpay_signature, at: Date.now() };
          store.set(KEYS.pending, pending);
          if (window.gtag) gtag('event', 'purchase', { currency: 'INR', value: PRICES[tier], items: [{ item_name: LABELS[tier] }] });
          fulfill(pending);
        },
        modal: { ondismiss: () => status('Payment cancelled. You have not been charged.', '') },
      });
      rz.on('payment.failed', (r) => status(`Payment failed: ${esc(r.error?.description || 'please try again')}. You have not been charged.`, 'error'));
      rz.open();
    } catch (err) {
      status(esc(err.message), 'error');
    } finally {
      btn.disabled = false;
    }
  }
  $$('[data-buy]').forEach((b) => b.addEventListener('click', () => buy(b.dataset.buy)));

  async function fulfill(p) {
    let v;
    try { v = inputs(); } catch (err) { return status(esc(err.message) + ' Your payment is saved; fill both boxes and press Retry.', 'error'); }
    const t0 = Date.now();
    const tick = setInterval(() => status(`Payment received. Preparing your ${esc(LABELS[p.tier])}… ${Math.round((Date.now() - t0) / 1000)}s (usually under a minute). Keep this page open.`, '', true), 1000);
    status(`Payment received. Preparing your ${esc(LABELS[p.tier])}…`, '', true);
    try {
      const data = await api('/api/fulfill', { ...p, resume: v.resume, job: v.job });
      clearInterval(tick);
      store.del(KEYS.pending);
      const saved = { tier: data.tier, result: data.result, payment_id: p.payment_id, at: Date.now() };
      store.set(KEYS.last, saved);
      status(`Done! Your ${esc(LABELS[data.tier])} is ready below. Payment ID: ${esc(p.payment_id)}`, 'ok');
      render(saved);
    } catch (err) {
      clearInterval(tick);
      const retryable = err.status !== 409 && err.status !== 400;
      status(`${esc(err.message)} ${retryable ? '<button class="btn small" id="retry-btn">Retry with the same payment</button>' : ''}<br><span class="small">Payment ID: ${esc(p.payment_id)} · Need help? <a href="mailto:contact@learnmasterypath.com">contact@learnmasterypath.com</a></span>`, 'error');
      $('#retry-btn')?.addEventListener('click', () => fulfill(p));
    }
  }

  // ---------- rendering ----------
  function resumeHtml(r) {
    const list = (a) => (a || []).map((x) => `<li>${esc(x)}</li>`).join('');
    let h = `<h3>${esc(r.full_name)}</h3>`;
    if (r.headline) h += `<p class="headline">${esc(r.headline)}</p>`;
    if (r.contact?.length) h += `<p class="contact">${r.contact.map(esc).join(' &nbsp;|&nbsp; ')}</p>`;
    if (r.summary) h += `<h4>Summary</h4><p>${esc(r.summary)}</p>`;
    if (r.skills?.length) h += `<h4>Skills</h4>${r.skills.map((g) => `<p><strong>${esc(g.group)}${g.group ? ':' : ''}</strong> ${(g.items || []).map(esc).join(', ')}</p>`).join('')}`;
    if (r.experience?.length) h += `<h4>Experience</h4>${r.experience.map((e) => `<div class="role">${esc(e.title)}${e.company ? ` - ${esc(e.company)}` : ''}</div><div class="meta">${[e.location, e.dates].filter(Boolean).map(esc).join(' | ')}</div><ul>${list(e.bullets)}</ul>`).join('')}`;
    if (r.projects?.length) h += `<h4>Projects</h4>${r.projects.map((p) => `<div class="role">${esc(p.name)}</div><ul>${list(p.bullets)}</ul>`).join('')}`;
    if (r.education?.length) h += `<h4>Education</h4>${r.education.map((e) => `<div class="role">${esc(e.credential)}${e.school ? ` - ${esc(e.school)}` : ''}</div><div class="meta">${esc(e.dates)}</div>${e.details?.length ? `<ul>${list(e.details)}</ul>` : ''}`).join('')}`;
    if (r.certifications?.length) h += `<h4>Certifications</h4><ul>${list(r.certifications)}</ul>`;
    return h;
  }

  const DOC_CSS = 'body{font-family:Calibri,Arial,sans-serif;font-size:11pt;color:#111;max-width:760px;margin:24px auto;padding:0 16px}h3{text-align:center;font-size:20pt;margin:0}.headline{text-align:center;font-style:italic;margin:2px 0}.contact{text-align:center;font-size:9.5pt;color:#333}h4{text-transform:uppercase;font-size:10.5pt;letter-spacing:.06em;border-bottom:1px solid #999;margin:12px 0 4px;padding-bottom:2px}.role{font-weight:700;margin-top:6px}.meta{font-style:italic;color:#444;font-size:9.5pt}ul{margin:2px 0;padding-left:18px}p{margin:3px 0}.letter{white-space:pre-wrap}';
  const docPage = (title, inner) => `<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title><style>${DOC_CSS}</style></head><body>${inner}</body></html>`;

  function download(name, html) {
    const blob = new Blob(['﻿', html], { type: 'application/msword' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  function printPdf(title, inner) {
    const w = window.open('', '_blank');
    if (!w) return status('Allow pop-ups to save as PDF, or use the Word download.', 'error');
    w.document.write(docPage(title, inner) + '<script>setTimeout(function(){window.print()},300)<\/script>');
    w.document.close();
  }
  const safeName = (s) => String(s || 'resume').replace(/[^\w -]+/g, '').trim().replace(/\s+/g, '_') || 'resume';

  function docButtons(kind) {
    return `<div class="downloads"><button class="btn small" data-dl="${kind}">Download Word</button><button class="btn small ghost" data-pdf="${kind}">Save as PDF</button><button class="btn small ghost" data-copy="${kind}">Copy text</button></div>`;
  }

  function render(saved, scroll = true) {
    const { tier, result: r } = saved;
    const out = $('#result');
    out.hidden = false;
    let tabs = [];
    if (tier === 'report') {
      tabs = [['report', 'Your ATS report', `
        ${ring(Math.round(r.match_estimate), 'Estimated fit for this job')}
        <p style="margin-top:12px">${esc(r.verdict)}</p>
        <h3>Top actions</h3><ol>${r.top_actions.map((x) => `<li>${esc(x)}</li>`).join('')}</ol>
        <h3>Missing skills</h3>${r.missing_skills.length ? r.missing_skills.map((m) => `<div class="qa"><h4>${esc(m.skill)}</h4><p class="muted">${esc(m.how_to_address)}</p></div>`).join('') : '<p class="muted">None found.</p>'}
        <h3>Bullet points to improve</h3>${r.weak_bullets.map((b) => `<div class="qa"><p class="muted small">Before: ${esc(b.original)}</p><p><strong>After:</strong> ${esc(b.improved)}</p><p class="small muted">${esc(b.why)}</p></div>`).join('')}
        <h3>Format fixes</h3><ul>${r.section_fixes.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
        <p><a class="btn" href="#plans">Get it rewritten for you · ₹44</a></p>`]];
    } else {
      tabs = [
        ['resume', 'Resume', docButtons('resume') + `<div class="doc">${resumeHtml(r.resume)}</div>`],
        ['letter', 'Cover letter', docButtons('letter') + `<div class="doc letter">${esc(r.cover_letter)}</div>`],
      ];
      if (tier === 'pack') {
        tabs.push(['linkedin', 'LinkedIn', `<div class="qa"><h4>Headline</h4><p>${esc(r.linkedin.headline)}</p></div><div class="qa"><h4>About</h4><p class="letter">${esc(r.linkedin.about)}</p></div><button class="btn small ghost" data-copy="linkedin">Copy LinkedIn text</button>`]);
        tabs.push(['interview', 'Interview prep', r.interview.map((q, i) => `<div class="qa"><h4>${i + 1}. ${esc(q.question)}</h4><p class="small muted">Why they ask: ${esc(q.why_they_ask)}</p><p>${esc(q.answer_guide)}</p></div>`).join('')]);
      }
      tabs.push(['notes', 'What changed', `<h3>Changes made</h3><ul>${r.changes.map((c) => `<li>${esc(c)}</li>`).join('')}</ul><h3>Gaps to address honestly</h3>${r.gaps.length ? `<ul>${r.gaps.map((g) => `<li>${esc(g)}</li>`).join('')}</ul>` : '<p class="muted">None found.</p>'}<p class="small muted">Always review the result before sending. You know your experience best.</p>`]);
    }
    out.innerHTML = `<div class="card result-card"><h2>Your ${esc(LABELS[tier])}</h2>
      <div class="tabs" role="tablist">${tabs.map(([k, l], i) => `<button class="tab" role="tab" data-tab="${k}" aria-selected="${i === 0}">${esc(l)}</button>`).join('')}</div>
      ${tabs.map(([k, , html], i) => `<div data-panel="${k}" ${i ? 'hidden' : ''}>${html}</div>`).join('')}
    </div>`;
    $$('.tab', out).forEach((t) => t.addEventListener('click', () => {
      $$('.tab', out).forEach((x) => x.setAttribute('aria-selected', String(x === t)));
      $$('[data-panel]', out).forEach((p) => { p.hidden = p.dataset.panel !== t.dataset.tab; });
    }));
    const name = safeName(r.resume?.full_name);
    const innerFor = (kind) => (kind === 'letter' ? `<div class="letter">${esc(r.cover_letter)}</div>` : resumeHtml(r.resume));
    $$('[data-dl]', out).forEach((b) => b.addEventListener('click', () => download(`${name}_${b.dataset.dl === 'letter' ? 'cover_letter' : 'resume'}.doc`, docPage(name, innerFor(b.dataset.dl)))));
    $$('[data-pdf]', out).forEach((b) => b.addEventListener('click', () => printPdf(name, innerFor(b.dataset.pdf))));
    $$('[data-copy]', out).forEach((b) => b.addEventListener('click', async () => {
      const k = b.dataset.copy;
      const text = k === 'letter' ? r.cover_letter : k === 'linkedin' ? `${r.linkedin.headline}\n\n${r.linkedin.about}` : $(`[data-panel="resume"] .doc`, out).innerText;
      try { await navigator.clipboard.writeText(text); b.textContent = 'Copied'; } catch { status('Copy failed. Select the text and copy it manually.', 'error'); }
    }));
    if (scroll) out.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // Restore: unfinished paid order first, then the last result.
  const pending = store.get(KEYS.pending);
  if (pending && Date.now() - pending.at < 3 * 24 * 3600 * 1000) {
    status(`You have a paid ${esc(LABELS[pending.tier])} waiting. <button class="btn small" id="resume-pending">Get my result</button>`, 'ok');
    $('#resume-pending').addEventListener('click', () => fulfill(pending));
  } else {
    const last = store.get(KEYS.last);
    if (last?.result) render(last, false);
  }
})();
