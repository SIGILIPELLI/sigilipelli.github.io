// Free ATS match scan. Deterministic (no AI call), so it costs nothing to run.
// Pulls the important terms out of a job description and checks which ones the
// resume already contains, plus a few structural checks ATS parsers care about.

const STOP = new Set(`a about above after again against all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each etc few for from further had has have having he her here
hers him his how i if in into is it its itself just me more most my no nor not now of off on once only or other our ours out
over own same she should so some such than that the their theirs them then there these they this those through to too under
until up very was we were what when where which while who whom why will with would you your yours ability able across
work working works job role position candidate candidates team teams company years year experience experienced including
include includes strong excellent good great well within using use used new must plus preferred required requirements
responsibilities responsible ensure etc highly skills skill knowledge understanding looking join us based level per day
opportunity opportunities environment related relevant various multiple across key help support provide make making best
we're you'll you're it's they're who'll will be minimum least degree equivalent field fields demonstrated proven
successful success global world leading join apply salary benefits remote hybrid office location full time part-time
part full-time contract within other others able ideal ideally across one two three four five six seven eight nine ten
like want need needs needed get gets also may might etc. eg e.g. i.e. ie wide range senior junior`.split(/\s+/));

// Multi-word and special-character skills the tokenizer would otherwise split.
const PHRASES = [
  'machine learning', 'deep learning', 'data analysis', 'data analytics', 'data science', 'data visualization',
  'project management', 'product management', 'stakeholder management', 'change management', 'risk management',
  'supply chain', 'customer service', 'customer success', 'account management', 'business development',
  'financial modeling', 'financial analysis', 'social media', 'content marketing', 'digital marketing',
  'email marketing', 'search engine optimization', 'user experience', 'user research', 'a/b testing',
  'rest apis', 'unit testing', 'test automation', 'continuous integration', 'ci/cd', 'rest api', 'restful apis', 'graphql',
  'microservices', 'cloud computing', 'google cloud', 'google analytics', 'power bi', 'microsoft excel',
  'microsoft office', 'node.js', 'react native', 'next.js', 'vue.js', 'c++', 'c#', '.net', 'objective-c',
  'ruby on rails', 'spring boot', 'sql server', 'big data', 'computer vision', 'natural language processing',
  'agile methodologies', 'scrum master', 'cross-functional', 'problem solving', 'problem-solving',
  'time management', 'attention to detail', 'written communication', 'verbal communication', 'public speaking',
  'team leadership', 'people management', 'budget management', 'quality assurance', 'technical support',
  'network security', 'information security', 'penetration testing', 'incident response', 'devops',
  'site reliability', 'infrastructure as code', 'large language models', 'generative ai', 'prompt engineering',
  'sales pipeline', 'lead generation', 'cold calling', 'b2b sales', 'saas', 'crm', 'erp', 'kpi', 'kpis', 'okrs',
  'go-to-market', 'p&l', 'accounts payable', 'accounts receivable', 'general ledger', 'patient care',
  'electronic health records', 'lesson planning', 'classroom management', 'curriculum development',
];

const norm = (s) => ` ${String(s || '').toLowerCase().replace(/[‘’]/g, "'").replace(/[^a-z0-9+#./&' -]+/g, ' ').replace(/\s+/g, ' ')} `;

function tokens(text) {
  return norm(text)
    .split(' ')
    .map((t) => t.replace(/^[^a-z0-9#+.]+|[^a-z0-9#+]+$/g, ''))
    .filter((t) => t.length > 1 && !STOP.has(t) && !/^\d+$/.test(t));
}

function extractKeywords(job, max = 25) {
  const jn = norm(job);
  const scores = new Map();
  const bump = (k, v) => scores.set(k, (scores.get(k) || 0) + v);

  for (const p of PHRASES) {
    const count = jn.split(` ${p} `).length - 1 + (jn.split(` ${p}, `).length - 1);
    if (count > 0) bump(p, 3 + count);
  }

  const toks = tokens(job);
  const freq = new Map();
  for (const t of toks) freq.set(t, (freq.get(t) || 0) + 1);
  for (let i = 0; i < toks.length - 1; i++) {
    const bi = `${toks[i]} ${toks[i + 1]}`;
    freq.set(bi, (freq.get(bi) || 0) + 1);
  }
  // Words written with capitals or symbols in the original are usually tools/tech (e.g. "Kubernetes", "SQL").
  const special = new Set(
    (String(job).match(/\b[A-Z][a-zA-Z0-9+#.]{1,}\b|\b[A-Z]{2,}\b/g) || []).map((w) => w.toLowerCase())
  );

  for (const [term, n] of freq) {
    const isBigram = term.includes(' ');
    if (isBigram && n < 2) continue;
    if (!isBigram && n < 2 && !special.has(term)) continue;
    bump(term, n * (isBigram ? 1.5 : 1) + (special.has(term) ? 1.5 : 0));
  }

  const ranked = [...scores.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k);
  const picked = [];
  for (const k of ranked) {
    // Skip single words already covered by a picked phrase, and vice versa.
    if (picked.some((p) => p.includes(` ${k} `) || ` ${p} `.includes(` ${k} `) || ` ${k} `.includes(` ${p} `))) continue;
    picked.push(k);
    if (picked.length >= max) break;
  }
  return picked;
}

function contains(haystackNorm, term) {
  const t = term.toLowerCase();
  if (haystackNorm.includes(` ${t} `) || haystackNorm.includes(` ${t}, `) || haystackNorm.includes(` ${t}. `)) return true;
  // Simple plural/singular tolerance.
  if (t.endsWith('s') && haystackNorm.includes(` ${t.slice(0, -1)} `)) return true;
  if (!t.endsWith('s') && haystackNorm.includes(` ${t}s `)) return true;
  return false;
}

function atsScan(resume, job) {
  const keywords = extractKeywords(job);
  const rn = norm(resume).replace(/[,;:()]/g, ' ').replace(/\s+/g, ' ');
  const matched = [];
  const missing = [];
  for (const k of keywords) (contains(rn, k) ? matched : missing).push(k);

  const words = String(resume).trim().split(/\s+/).filter(Boolean).length;
  const lower = String(resume).toLowerCase();
  const checks = [
    { id: 'email', label: 'Email address present', pass: /[\w.+-]+@[\w-]+\.[\w.]+/.test(resume) },
    { id: 'phone', label: 'Phone number present', pass: /(\+?\d[\d\s().-]{7,}\d)/.test(resume) },
    { id: 'experience', label: 'Has an Experience section', pass: /experience|employment|work history/.test(lower) },
    { id: 'education', label: 'Has an Education section', pass: /education|degree|university|college|school/.test(lower) },
    { id: 'skills', label: 'Has a Skills section', pass: /skills|technologies|tools|competencies/.test(lower) },
    { id: 'numbers', label: 'Uses numbers to show impact', pass: (String(resume).match(/\d+%|\$\s?\d|\d+\+|\b\d{2,}\b/g) || []).length >= 3 },
    { id: 'length', label: 'Length between 300 and 1,200 words', pass: words >= 300 && words <= 1200 },
  ];

  const kwScore = keywords.length ? matched.length / keywords.length : 0;
  const checkScore = checks.filter((c) => c.pass).length / checks.length;
  const score = Math.round(100 * (0.75 * kwScore + 0.25 * checkScore));

  return { score, matched, missing, checks, words, keywordCount: keywords.length };
}

window.MPATS = { atsScan: atsScan, extractKeywords: extractKeywords };
