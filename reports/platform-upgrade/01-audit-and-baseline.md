# Stage 1–2: Repository and live-site audit, baseline

Audit date: 23 November 2026. Method: source inspection of all 102 repositories (cloned under `repos/`), plus live checks of https://learnmasterypath.com.

## 1. Technology stack (as found)

| Part | Technology | Source | Deploy |
|---|---|---|---|
| Hub site (homepage, search, career tools, legal, verify) | Static HTML/CSS/vanilla JS, no framework, no build step | `SIGILIPELLI/sigilipelli.github.io` | GitHub Pages from `main`, custom domain via `CNAME` |
| 102 course sites | MkDocs 1.x + Material for MkDocs 9.8.1, Markdown content, one shared template (`docs/overrides/main.html`) | 100 repos `SIGILIPELLI/*-mastery-path` (Python repo also builds the nested MCP and Vector Databases courses) | GitHub Actions `deploy.yml` → `gh-pages`, served under `learnmasterypath.com/<course>/` |
| API | Cloudflare Worker (JavaScript), KV namespace `SUBSCRIBERS` | `SIGILIPELLI/mastery-resume-api` (private) | Cloudflare Workers Builds on push to `main` |
| Shared front-end | `assets/learn.js` (course overview, quizzes, exam), `cert.js`, `search.js`, `signup.js`, `course.css`, `site.css` | hub repo | instant for all courses (served from the hub) |
| Analytics | Google Analytics 4 `G-05VBGCXN12` (page views only) | template | — |
| Database | None. Content lives in Markdown; derived JSON (search index, quiz bank) lives in the hub repo; certificates/sign-ups in Cloudflare KV | — | — |
| Authentication | None for learners (by design). Worker admin export is gated by an optional `ADMIN_TOKEN` secret (not set yet) | — | — |

## 2. Route inventory

Hub (`learnmasterypath.com/`): `/`, `/search/`, `/resume/`, `/interview-pack/`, `/interview-questions/`, `/verify/`, `/about.html`, `/contact.html`, `/privacy.html`, `/terms.html`, `/refunds.html`, `/delivery.html`, `/license.html`, `/404.html`, `/feed.xml`, `/sitemap.xml` (index of 103 sitemaps), `/sitemap-hub.xml`, `/robots.txt`, `/learn/quizzes/<course>.json`, `/search/*.json`.

Each course (`/<course>/`): home, `level-1/` … `level-4/` overviews, lesson pages `level-N/<NN-slug>/`, `interview-questions/`, `cheat-sheet/` (83 courses), `quiz/` (final quiz + certification exam), `privacy/`, `license/`, `404.html`, `search/search_index.json`, `sitemap.xml`. Last full crawl: 4,912 pages, all HTTP 200.

API (`api.learnmasterypath.com`): `/health`, `POST /api/order`, `/api/fulfill`, `/api/subscribe`, `/api/exam/start`, `/api/exam/submit`, `GET /api/cert/<id>`, `GET /api/subscribers.csv` (token).

## 3. Course data sources (before this work)

| Fact | Where it came from | Problem |
|---|---|---|
| Course list | `index.html` catalogue + `tools/search-config.json` + live course sites → `search/courses.json` | no stable course IDs |
| Lesson list | each course's `search_index.json` (built from Markdown) → `search/lessons.json` | projects mixed into lessons |
| "102 courses", "4,000+ lessons", "15 categories" | **hard-coded** in `index.html` (stat chips, hero, meta), `about.html`, `search/index.html` | not derived from data |
| Per-course "40 lessons" on homepage cards | hard-coded in `index.html` | Python card says 41 |
| Course overview facts | `learn.js` counts nav pages at runtime: "41 lessons · 4 projects" | projects counted inside lessons |
| Quizzes | `learn/quizzes/<course>.json` (generated) | — |
| Dates, author, review status | not recorded per course | — |

## 4. Findings against the brief's observations

- **A. Count inconsistency: confirmed.** Python has 37 topic lessons and 4 project pages (41 pages). The course page's own table says "9 topics + 1 project" per level, the overview says "41 lessons · 4 projects", and the homepage card says 41. Root cause: two counting rules (pages vs topics) applied in different places.
- **B. Categories: confirmed.** The homepage shows 12 tiles under "Explore categories"; the data has 15 categories.
- **C. Classification: needed.** 9 courses teach management, language, accounting or marketing skills rather than a technology (see the registry config).
- **D. Websites: clarified.** All 102 courses are first-party sections of one domain, not independent websites. One first-party subdomain (`api.`). External documentation links (`learn/docs.json`) are references only.
- **E. Content records: missing.** No per-course publication date, author, version or review date.

## 5. Functionality map (kept working)

Search (instant + full page), course overview/progress/curriculum, module quizzes, final quiz, certification exam + certificate verify, interview questions and cheat sheets, email sign-up (KV + Brevo), Resume Tools (Razorpay + Claude), AdSense, GA4, RSS, sitemaps, structured data.

## 6. Technical risk register

| # | Risk | Impact | Mitigation in this work |
|---|---|---|---|
| R1 | Counts hard-coded in several pages drift from reality | misleading claims, weak record evidence | single registry + counting engine; pages read from it |
| R2 | GitHub Pages cannot protect routes | an "admin" page on the hub would be public | admin dashboard served by the Worker behind a secret token |
| R3 | A registry built from live pages fails if a course site is down | wrong counts | builder fails loudly; a failed course becomes "pending", never silently dropped |
| R4 | Changing course IDs later breaks evidence trails | lost traceability | IDs stored in `registry/ids.json`, append-only |
| R5 | Over-claiming a record | reputational/legal | record page shows only verified status; no Guinness branding |
| R6 | 100-repo template changes | slow rollout | this work changes only the hub and the Worker |
| R7 | Quiz bank quality (correct option often longest) | weak assessment evidence | exam already uses length-matched options; noted in methodology |

## 7. Baseline and rollback (Stage 2)

- Production commits for all 102 repositories: `reports/platform-upgrade/baseline-commits.csv`.
- Default branch everywhere: `main`. Work branches: hub `platform-upgrade`, Worker `admin-verification`. No course repository is changed.
- Rollback: the work arrives as pull requests; revert the merge commit (`git revert -m 1 <merge>`) and GitHub Pages / Workers Builds redeploy the previous state within minutes.
