// Tests the site search engine (assets/search.js) against the full generated index.
// Usage: node tools/test_search.mjs   (run from the repo root after build_search_index.py)
import fs from 'node:fs';
import vm from 'node:vm';

const read = (p) => fs.readFileSync(p, 'utf8');
const ctx = {
  window: {}, console, performance, URLSearchParams, Map, Set, Promise, JSON, Math, String, Array, RegExp, Number, setTimeout, clearTimeout,
  document: { currentScript: { src: 'https://learnmasterypath.com/assets/search.js' } },
  localStorage: { _s: {}, getItem(k) { return this._s[k] ?? null; }, setItem(k, v) { this._s[k] = String(v); }, removeItem(k) { delete this._s[k]; } },
  fetch: async (url) => ({ json: async () => JSON.parse(read(url.replace('https://learnmasterypath.com/', ''))) }),
};
vm.createContext(ctx);
vm.runInContext(read('assets/search.js'), ctx);
const S = ctx.window.MPSearch;
await S.loadLessons();
const courses = S.courses();
const lessons = JSON.parse(read('search/lessons.json')).rows;

let fails = 0, checks = 0;
const ok = (cond, msg) => { checks++; if (!cond) { fails++; if (fails <= 25) console.log('  FAIL', msg); } };
const top = (q, f = {}) => S.query(q, f, {});

// 1. every course by its name and short name
for (const c of courses) {
  const r = top(c.short);
  ok(r.courses.slice(0, 3).some((x) => x.url === c.url), `course "${c.short}" not in top 3 (got ${r.courses.slice(0, 3).map((x) => x.courseShort)})`);
  const r2 = top(c.name);
  ok(r2.courses[0] && r2.courses[0].url === c.url, `course name "${c.name}" not first`);
}
const courseChecks = checks;

// 2. every lesson by its exact title, within the top 5 lessons (or top 5 within its course when titles repeat)
let lessonMiss = 0;
const times = [];
for (const row of lessons) {
  const c = courses[row[0]];
  const title = row[2].replace(/^\d+\s*·\s*/, '');
  const url = `${c.url}level-${row[1]}/${row[3]}`;
  const t0 = performance.now();
  let r = top(title);
  times.push(performance.now() - t0);
  let found = r.lessons.slice(0, 5).some((x) => x.url === url);
  if (!found) found = top(title, { tech: c.id }).lessons.slice(0, 5).some((x) => x.url === url);
  if (!found) { lessonMiss++; if (lessonMiss <= 10) console.log('  lesson miss:', title, '|', c.short); }
  checks++; if (!found) fails++;
}

// 3. typos, synonyms, roles, topics
const expectCourse = (q, short) => {
  const r = top(q);
  ok(r.courses.slice(0, 3).some((x) => x.courseShort === short), `"${q}" should find course ${short} (got ${r.courses.slice(0, 3).map((x) => x.courseShort)})`);
};
[['pyhton', 'Python'], ['kubernets', 'Kubernetes'], ['javscript', 'JavaScript'], ['excell', 'Excel'], ['dockr', 'Docker'], ['terrafrom', 'Terraform'], ['tablaeu', 'Tableau'],
 ['js', 'JavaScript'], ['k8s', 'Kubernetes'], ['gst', 'Tally Prime & GST'], ['golang', 'Go'], ['c++', 'C++'], ['c#', 'C#'], ['ml', 'AI/ML'], ['seo', 'Digital Marketing & SEO'],
 ['postgres', 'PostgreSQL'], ['ielts', 'English Fluency & IELTS'], ['leetcode', 'DSA & Coding Interviews'], ['scrum', 'Agile/Scrum/Kanban']].forEach(([q, s]) => expectCourse(q, s));
const role = top('data analyst');
ok(role.courses.length >= 4 && role.courses.slice(0, 6).every((x) => x.careers.includes('Data Analyst')), `"data analyst" role courses: ${role.courses.slice(0, 6).map((x) => x.courseShort)}`);
const acct = top('accountant');
ok(acct.courses.some((x) => x.courseShort === 'Tally Prime & GST'), 'accountant -> Tally');
const vl = top('vlookup');
ok(vl.lessons.slice(0, 3).some((x) => /lookup/i.test(x.title) && x.courseShort === 'Excel'), `vlookup -> Excel lookup lesson (got ${vl.lessons.slice(0, 3).map((x) => x.title)})`);
const dec = top('python decorators');
ok(dec.lessons.slice(0, 3).some((x) => /decorator/i.test(x.title + x.topics)), 'python decorators lesson');
const hooks = top('react hooks');
ok(hooks.lessons.slice(0, 3).some((x) => x.courseShort === 'React'), 'react hooks -> React lesson');
const typoLesson = top('pivot tabels');
ok(typoLesson.lessons.slice(0, 5).some((x) => /pivot/i.test(x.title)), 'typo "pivot tabels" finds PivotTables');

// 4. filters
const l1 = top('sql', { level: '1' });
ok(l1.lessons.length && l1.lessons.every((x) => x.levelN === 1), 'level filter');
const car = top('', { career: 'Data Engineer' });
ok(car.courses.length && car.courses.every((x) => x.careers.includes('Data Engineer')), 'career filter browse');
const cat = top('testing', { cat: 'testing-qa' });
ok(cat.lessons.length && cat.lessons.every((x) => x.category === 'Testing & QA'), 'category filter');
const typ = top('', { type: 'Cloud platform' });
ok(typ.courses.length === courses.filter((c) => c.type === 'Cloud platform').length, 'course type filter');
const tech = top('', { tech: 'excel-mastery-path', level: '2' });
ok(tech.lessons.length === 10 && tech.lessons.every((x) => x.courseShort === 'Excel' && x.levelN === 2), `technology+level browse (${tech.lessons.length})`);
ok(top('xqzzvbnm').courses.length + top('xqzzvbnm').lessons.length === 0, 'nonsense returns nothing');

// 5. history
S.history.add('docker'); S.history.add('python'); S.history.add('Docker');
ok(S.history.get()[0] === 'Docker' && S.history.get().length === 2, 'history de-dupes, newest first');

times.sort((a, b) => a - b);
console.log(`courses: ${courses.length} (${courseChecks} checks) | lessons: ${lessons.length}, not found: ${lessonMiss}`);
console.log(`query time over ${times.length} lesson searches: median ${times[times.length >> 1].toFixed(2)} ms, p95 ${times[Math.floor(times.length * 0.95)].toFixed(2)} ms, max ${times[times.length - 1].toFixed(1)} ms`);
console.log(`${checks - fails}/${checks} checks passed`);
process.exit(fails ? 1 : 0);
