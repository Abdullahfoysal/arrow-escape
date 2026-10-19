# Arrow Escape website

Static site for **Arrow Escape: Tap Puzzle** (D-74): landing page, Privacy Policy, Terms of Service, Support, Licences and a 404 page.

- **Hosting:** GitHub Pages **project site** from the repo `Abdullahfoysal/arrow-escape`.
- **Site:** `https://abdullahfoysal.github.io/arrow-escape/`
- **Privacy policy:** `https://abdullahfoysal.github.io/arrow-escape/privacy-policy/` (the path comes from the legal doc's front matter `permalink`).
- **Pages:** `/arrow-escape/terms/`, `/arrow-escape/support/`, `/arrow-escape/licenses/`, plus `404.html`.

Plain HTML and CSS: no framework, no Jekyll, no JavaScript, no trackers, analytics, cookies or third-party requests. The local preview serves the same files under the same `/arrow-escape/` prefix as GitHub Pages.

## Layout

This folder is its own git repo (`Abdullahfoysal/arrow-escape`), nested inside the game project at `arrow-puzzle/website/`.

```
site-config.json       public values: basePath, developer name, email, dates, URLs (no secrets)
content/legal/         committed copies of the game project's docs/phase3/legal/*.md
src/templates/         base.html (shared head, header, footer)
src/pages/            index, support, licenses, 404 page bodies
src/notices/          verbatim third-party licence texts shown on /licenses/
src/assets/           CSS, images (app icon, 3 game screenshots, og-image), Manrope TTF + OFL.txt
tools/sync_legal.py   copies the legal docs from the game project into content/legal/
tools/build.py        builds dist/ (Python 3 standard library only)
tools/check.py        link, anchor, base-path and HTML checks on dist/
tools/serve.py        local preview at http://localhost:8000/arrow-escape/
tools/publish.sh      build --strict + check + force-push dist/ to the gh-pages branch
tools/screenshots.mjs headless-Chrome screenshots (Node 22+, no npm packages)
tools/og-image.html   source of src/assets/img/og-image.png
dist/                 build output (git-ignored on main; it is what gh-pages contains)
screenshots/          verification screenshots (git-ignored)
```

### Deployment choice: `main` = source, `gh-pages` = built site

`main` holds the source above. `tools/publish.sh` builds locally and force-pushes `dist/` as the only content of a `gh-pages` branch.

I chose this over a GitHub Actions workflow because Actions needs the owner to switch **Settings › Pages › Source** to "GitHub Actions". It would also publish whatever is on `main` without the local `--strict` gate. GitHub normally turns Pages on by itself when a `gh-pages` branch is pushed. If it doesn't, the only setup is: **Settings › Pages › Build and deployment › Deploy from a branch › `gh-pages` / `(root)`**.

### Base path

All internal links are written root-relative in the sources (`/support/`). `build.py` prefixes every `href`/`src` with `basePath` from `site-config.json` (`/arrow-escape`). It also builds canonical, Open Graph image and sitemap URLs as `siteUrl + basePath + path`. In `site-config.json`, `siteUrl` is the origin only (`https://abdullahfoysal.github.io`, no path). The CSS loads fonts with relative URLs. To move to a custom domain at the root later, set `basePath` to `""` and `siteUrl` to the new origin, then rebuild.

`404.html`: GitHub serves `/arrow-escape/404.html` for missing pages under the project path. All its links carry the base path, so it works at any depth.

## Legal pages

`build.py` reads `content/legal/privacy-policy.md` and `terms-of-service.md`, never `../docs`, so the build works in a standalone clone. To refresh them from the game project:

```
python3 website/tools/sync_legal.py        # run from the game project root (arrow-puzzle/)
```

When `website/` sits inside the game project, the build also prints a NOTE if `content/legal/` differs from `docs/phase3/legal/`.

The build:
- uses the front matter `title` (page title) and `permalink` (output path, e.g. `/privacy-policy/`, `/terms/`), and doesn't render the front matter. The nav, footer and in-page links follow the permalink automatically;
- strips every HTML comment (`<!-- DRAFT-BANNER … -->`, `<!-- REVIEW-NOTE: … -->`), any `<!-- BEGIN … legal review … --> … <!-- END … -->` block, and any `>` blockquote banner that says it needs legal review;
- builds a table of contents from the `##` headings. Anchors are slugs of the heading text (`Your choices` → `#your-choices`), or an explicit `{#id}` if a heading has one;
- shows "Last updated: <effectiveDate>";
- replaces `[EFFECTIVE DATE]`, `[COMPANY/DEVELOPER NAME]`, `[POSTAL ADDRESS]`, `[SUPPORT_EMAIL]` (as a mailto link), `[JURISDICTION]`, `[PRIVACY OFFICER NAME/TITLE]` and `[PRIVACY_POLICY_URL]` from `site-config.json`. While `[PRIVACY_POLICY_URL]` is unfilled, it falls back to the site's own privacy page.

The Markdown converter in `build.py` handles what the legal docs use: headings, paragraphs (consecutive lines become line breaks), nested `-` lists, pipe tables, blockquotes, `**bold**`, `*italic*`, `` `code` ``, `[links](url)` and bare URLs.

## Sync, build, check, preview

From the game project root (`arrow-puzzle/`):

```
python3 website/tools/sync_legal.py      # 1. refresh content/legal/ from docs/phase3/legal/
python3 website/tools/build.py           # 2. build dist/ (warns while placeholders remain)
python3 website/tools/check.py           # 3. links, anchors, base path, HTML basics
python3 website/tools/serve.py           # 4. preview: http://localhost:8000/arrow-escape/
```

In a standalone clone of the website repo, run the same scripts as `python3 tools/build.py` and so on (no sync step).

`build.py --strict` exits 1 while anything is unfilled. While any `site-config.json` value is still a `[PLACEHOLDER]` or contains `<username>`, or a placeholder or `*[reviewer note]*` is left in a legal doc, the build:
- prints a loud `!!` warning;
- adds a "DRAFT, not yet published" banner to every page and highlights each placeholder;
- adds `<meta name="robots" content="noindex">`.

DRAFT-BANNER / REVIEW-NOTE comments are always stripped. The build only reminds you that legal review should be finished, and `--strict` fails on them. When everything is filled, the build also writes `sitemap.xml`.

`serve.py` behaves like GitHub Pages. It redirects `/` to `/arrow-escape/`, adds trailing slashes to directories, and answers unknown paths with `404.html`. Don't use `python3 -m http.server` inside `dist/`: the `/arrow-escape/…` links would break there.

Screenshots (needs Google Chrome):
- `node website/tools/screenshots.mjs` takes all pages at 390 and 1280 px, light and dark, into `website/screenshots/`.
- `--only home,privacy --width 390 --scheme light` takes a subset.
- `--og` re-renders the share image.

## Publish (only with the owner's go-ahead)

`gh` isn't installed on this machine, so use the GitHub web UI plus plain git. The PM runs the git steps.

1. Fill `site-config.json`:
   - `siteUrl`: `https://abdullahfoysal.github.io`
   - `privacyPolicyUrl`: `https://abdullahfoysal.github.io/arrow-escape/privacy-policy/`
   - developer name, postal address, support email, effective date, jurisdiction, privacy officer.

   Keep `basePath` at `/arrow-escape`. Run sync, build with `--strict`, and check. They must pass with no warnings.
2. On github.com, create the **public** repository `Abdullahfoysal/arrow-escape`, empty (no README).
3. First push of the source (from `arrow-puzzle/website/`):
   ```
   git init -b main
   git add -A
   git commit -m "Arrow Escape website source"
   git remote add origin https://github.com/Abdullahfoysal/arrow-escape.git
   git push -u origin main
   ```
   The game project should ignore this nested repo: add `website/` to the game project's `.gitignore`, or track it as a submodule.
4. Publish the built site:
   ```
   sh tools/publish.sh
   ```
   Before legal review is finished, use `sh tools/publish.sh --allow-review-notes`. It still prints a loud warning listing the REVIEW-NOTE/DRAFT-BANNER comments in `../docs/phase3/legal/`. `sync_legal.py` strips every HTML comment, so these never reach `content/legal/` or the public repo. In a standalone clone, the review status can't be checked and the build only warns.
   This runs `build.py --strict` and `check.py`, copies `dist/` (including `.nojekyll`) into a temporary repo, and force-pushes it as `gh-pages` to `origin`.
5. If Pages didn't switch on by itself: **Settings › Pages › Deploy from a branch › `gh-pages` / `(root)`**. After 1–2 minutes, open the site and `/arrow-escape/privacy-policy/`.
6. To update later: sync, commit the source on `main`, then `sh tools/publish.sh` again.

Use these URLs in:
- the Play Console listing: Website `https://abdullahfoysal.github.io` (see app-ads.txt below) and the privacy policy URL;
- App Store Connect: Marketing URL and Privacy Policy URL;
- the game's Settings links (T-040).

## app-ads.txt: needs the domain root

AdMob and the other ad buyers look for `app-ads.txt` at the **root of the developer website's domain**: `https://abdullahfoysal.github.io/app-ads.txt`. A project site can only serve `/arrow-escape/app-ads.txt`, which they ignore. So this repo deliberately has **no `app-ads.txt`**, and `robots.txt` / `sitemap.xml` here are informational only, because crawlers read them from the root as well.

Fix, when the ad accounts exist:
1. Create a second tiny public repo named exactly **`Abdullahfoysal.github.io`**, the user site served at the domain root. Put three files in it on `main`, and set Pages to deploy from `main` / root if it isn't on already:
   - `app-ads.txt`: the exact lines from the dashboards, never invented:
     - AdMob: **Apps › View all apps › app-ads.txt**. Copy the line it shows (`google.com, pub-…, DIRECT, f08c47fec0942fa0`).
     - LevelPlay / Unity: the app-ads.txt list in the LevelPlay or Unity monetization dashboard, or ask Unity support. Copy their lines exactly.
   - `.nojekyll`: empty.
   - `index.html`: a redirect to the game site:
     ```html
     <!doctype html><html lang="en"><head><meta charset="utf-8">
     <title>Arrow Escape</title>
     <meta http-equiv="refresh" content="0; url=/arrow-escape/">
     <link rel="canonical" href="https://abdullahfoysal.github.io/arrow-escape/">
     </head><body><p><a href="/arrow-escape/">Arrow Escape: Tap Puzzle</a></p></body></html>
     ```
2. Set the store listing **Website** to `https://abdullahfoysal.github.io`. AdMob matches the domain, so the developer website and the app-ads.txt location agree. The redirect sends visitors on to the game site.
3. Wait about 24 hours, then check AdMob's app-ads.txt tab for "Found". It only works once the Play listing is published (at least in closed testing) with that Website.

Alternative: a custom domain (about $10–15 a year). Point it at this repo, set `basePath` to `""` and `siteUrl` to the domain, and serve `app-ads.txt` from this site's root. To do that, save it as `src/app-ads.txt` and copy it in `build.py` next to `favicon.ico`.

## Credits and licences

- Manrope font: SIL Open Font License 1.1. The licence is in `src/assets/fonts/OFL.txt`, served at `/arrow-escape/assets/fonts/OFL.txt` and shown on `/licenses/`. The build converts the TTFs to WOFF (about 41 KB each) with the standard library.
- App icon and screenshots: the game's own art, from `unity/Assets/Art/Icon/AppIcon-1024.png` and `docs/design/screenshots/ios-{home,game-10x10,daily}.png` (status-bar area cropped off, resized, JPEG). Replace the files in `src/assets/img/` keeping the names, and update `width`/`height` in `src/pages/index.html` if the size changes.
- `/licenses/` lists what the game ships today: Manrope, the CC0 music by Juhani Junkala, and the Unity packages with their SmartFormat and Newtonsoft.Json MIT notices copied verbatim. It also lists the SDKs still to come. Add their notices when Firebase, Google Mobile Ads/UMP, LevelPlay and Unity IAP are integrated.
- Store buttons: set `googlePlayUrl` / `appStoreUrl` and rebuild. Text buttons appear in the `STORE LINKS` spot on the home page. Update the "Coming soon" wording in `src/pages/index.html` and `tools/og-image.html` at launch, then re-render with `--og`.
