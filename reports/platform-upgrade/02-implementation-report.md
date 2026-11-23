# Stages 3–7: Implementation, QA and release report

Branches: hub `platform-upgrade`, Worker `admin-verification`. Not deployed to production; awaiting the owner's approval.
Final audit: `MPA-20261123T0912Z` (23 Nov 2026, 09:12 UTC). Stage 1–2 audit and baseline: `01-audit-and-baseline.md`.

## 1. Results in numbers (from the registry, not typed)

| Measure | Value |
|---|---|
| Registered / published courses | 102 / 102 |
| Technology / professional development | 93 / 9 |
| Lessons (qualifying, ≥300 words, HTTP 200) | 3,660 |
| Level projects / final capstones | 323 / 102 |
| Exercises / quizzes (module + final) | 3,912 / 4,107 |
| Categories (featured on homepage) | 15 (12) |
| Career learning paths | 22 |
| First-party domains | 2 (learnmasterypath.com, api.learnmasterypath.com) |
| Lesson URLs checked / failing | 4,085 / 0 |
| Duplicate candidates | 1 (Product Manager vs Project Manager titles: different courses, kept) |
| Pass all automated checks / human-reviewed | 102 / 0 → status `eligible_pending_review` |

Corrections this made visible: the homepage said "4,000+ lessons"; the accurate figure is 3,660 lessons, plus 425 project pages counted separately. Python is 37 lessons + 3 projects + 1 capstone (was shown as 40 and 41 in different places).

## 2. What was built (repository paths)

Hub (`SIGILIPELLI/sigilipelli.github.io`):
- `tools/registry/build_registry.py`: counting engine: reads the live site, assigns stable IDs, classifies, counts lessons/projects/capstones/exercises/quizzes separately, checks levels, word counts, sitemap, every lesson URL, duplicates (SHA-256 text fingerprints, shingle Jaccard, title similarity), writes registry and evidence with checksums, archives audits.
- `tools/registry/build_pages.py`: generates `/course-catalogue/`, `/quality-and-verification/`, `/learning-impact/`, `/world-record-attempt/`, `/about/` (redirect to `/about.html`), `registry/course-facts.json`; fills every `data-mp-stat` number and course-card lesson count in `index.html`, `about.html`, `search/index.html`; updates `sitemap-hub.xml`.
- `tools/registry/test_registry.py`: data-integrity tests (IDs, URLs, one course + level per lesson, per-course and summary totals, projects never lessons, at most one capstone, classification, "eligible" needs a review, CSV row counts, checksums).
- `registry/` (see `registry/README.md`), `registry/config.json` (definitions, rules, classification, website registry), `registry/record.json` (application status).
- `.github/workflows/registry.yml`: daily audit + pages + tests, manual run with archive.
- `index.html`: registry-driven stats (courses, lessons, projects, categories) with "how we count" note; "Featured categories" (12 of 15) with link to all; catalogue links; "Measured, not claimed" band; navigation; accessible amber text.
- `about.html`: mission, ownership, method, development and review process, dated history, contact.
- `assets/learn.js`: course pages show registry counts ("36 lessons · 4 projects, counted separately") and the course record (ID, classification, author, published, updated, review status); course-home layout-shift fix.
- `assets/course.css`, `assets/site.css`, `tools/site_chrome.py`: new navigation (Courses, Learning Paths, Career Tools, Impact, Quality, Record Journey, About; Technology/Professional via catalogue filters in footer), WCAG contrast fixes, underlined in-text links, CLS guard.

Worker (`SIGILIPELLI/mastery-resume-api`, private):
- `src/admin.js`: `/admin/course-verification` dashboard (HTTP Basic, password = `ADMIN_TOKEN`; constant-time compare; 10 failed attempts/hour/IP lock-out; noindex, no-store, CSP, frame-deny): totals, alerts (pending/rejected, inconsistent level totals, missing author/syllabus, missing reviews, failing URLs), filters, duplicates, review recording, audit history, CSV/JSON exports. `GET /api/reviews` (public, read-only). Counts cannot be edited.
- `test/admin.test.js`: 4 tests. All Worker tests: 31/31 pass.

No course repository changes.

## 3. Quality assurance

| Area | Method | Result |
|---|---|---|
| Data integrity | `test_registry.py` | pass (102 courses, 4,085 page records) |
| Counting rules | manual check of Python (37/3/1), SQL (36 + 4) against source | consistent on homepage, catalogue, course page, CSV |
| Search regression | `node tools/test_search.mjs` | 4,506 / 4,506 |
| Worker | `npm test` | 31 / 31; `npm audit`: 0 vulnerabilities |
| Catalogue functions | search, category, classification, level highlight, 4 sorts, URL state | pass (e.g. professional → 9, cloud → 5) |
| Responsive | 375 / 768 / 1280 px, all new pages, no horizontal scroll | pass (fixed 2 issues) |
| Accessibility | axe-core 4.10.2, WCAG 2.0/2.1/2.2 A+AA, 10 pages incl. course home and lesson | 0 violations after fixes (contrast of small text and code tokens, amber labels, in-text links) |
| SEO | titles ≤ 65 chars and unique, descriptions, canonical, one H1, valid JSON-LD (BreadcrumbList), sitemap | pass |
| Claims | scan for "record holder", "world record achieved", Guinness logos | none; explicit non-affiliation statement |
| Performance (lab, local) | Performance API in Chrome | new pages 12–16 KB (catalogue 172 KB uncompressed), CLS 0; course-home cold-load CLS issue (0.73) found and fixed with a CSS guard |
| Security | admin auth, lock-out, input validation (slug regex, length caps, control/angle chars stripped), output escaping in dashboard, CSP, no secrets in registry (grep) | pass |

Not done here: Lighthouse/PageSpeed field run (the PageSpeed API quota was exhausted earlier; run it after deployment); Core Web Vitals field data needs ~28 days in Search Console.

## 4. Acceptance criteria

| Requirement | Status |
|---|---|
| No existing course lost | ✅ 102 before and after; no course repo changed |
| Stable course and lesson IDs | ✅ `registry/ids.json` (append-only), tested |
| Counts dynamic from source records | ✅ every displayed count comes from the registry; daily job |
| Duplicate detection | ✅ exact, near-duplicate and title checks; 1 candidate for review |
| Four levels represented accurately | ✅ per-level lesson counts per course; all 102 have ≥5 lessons in each level |
| Catalogue search/filters | ✅ tested |
| Public methodology | ✅ `/quality-and-verification/` |
| No misleading Guinness claims | ✅ status ladder; "No record has been awarded" |
| CSV / JSON exports | ✅ in `registry/`, row counts tested |
| Admin protected and functional | ✅ in code and tests; ⏳ needs `ADMIN_TOKEN` secret to switch on |
| SEO validated | ✅ |
| Accessibility tested | ✅ axe WCAG 2.2 AA |
| Performance measured | ◐ lab measurements done; Lighthouse after deploy |
| Regression | ✅ search 4,506/4,506, Worker 31/31, existing URLs unchanged |
| Staging reviewed before production | ⏳ owner review of the pull requests |
| Dated, traceable evidence | ✅ audits `MPA-20261123T0853Z`, `0909Z`, `0912Z` archived with SHA-256 |

## 5. Known issues and blockers (what the owner must do)
1. **Human reviews.** All 102 courses are `eligible_pending_review`. A named person must read each course and record a review (dashboard or `registry/reviews.json`). Automated checks cannot do this.
2. **`ADMIN_TOKEN`.** Set this Worker secret in Cloudflare (Workers → mastery-resume-api → Settings → Variables and Secrets) to switch the dashboard on.
3. **Record title.** The submitted title is individual-based ("…created and published by an individual on a single website"). The brief's platform-based title is listed as an alternative; changing titles needs Guinness World Records' agreement, not a second overlapping application.
4. **Learner metrics** are shown as "Not currently measured" because no verifiable learner records exist (no accounts).
5. **Curriculum standardisation (brief §7).** All courses already meet the structural rules (4 levels, projects, capstone, exercises, quizzes); a subject-matter review of each level's content is part of the human reviews in item 1.

## 6. Deployment
1. Review and merge the Worker PR → Cloudflare Workers Builds deploys. Set `ADMIN_TOKEN`.
2. Review and merge the hub PR → GitHub Pages deploys in ~1 minute.
3. After deploy: open the new routes; run the "Course registry audit" workflow with archive; check `/sitemap-hub.xml`; submit the sitemap in Search Console; run PageSpeed on `/`, `/course-catalogue/`, one course.

## 7. Rollback
`git revert -m 1 <merge-commit>` on `main` in the affected repository (hub or Worker) and push; Pages/Workers redeploy the previous version. Baseline commits: `baseline-commits.csv`. The registry files are additive; reverting removes them without touching courses.
