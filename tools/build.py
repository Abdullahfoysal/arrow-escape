#!/usr/bin/env python3
"""Build the Arrow Escape static website into website/dist/.

Usage (from anywhere):
    python3 website/tools/build.py            # build; warns loudly if placeholders remain
    python3 website/tools/build.py --strict   # same, but exit 1 if anything is unfilled

Python 3 standard library only (the `markdown` package is not assumed). The small
converter below handles exactly the Markdown the legal docs use: front matter,
headings (with optional {#id}), paragraphs, nested "-" lists, pipe tables,
blockquotes, **bold**, *italic*, `code`, [links](url) and bare URLs.
"""
import datetime
import html
import json
import os
import re
import shutil
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)                       # website/
SRC = os.path.join(SITE, "src")
DIST = os.path.join(SITE, "dist")
CONFIG = os.path.join(SITE, "site-config.json")
# Committed copies of the legal docs (refresh with tools/sync_legal.py from the game project).
LEGAL_DIR = os.path.join(SITE, "content", "legal")
# Upstream source, present only when website/ sits inside the game project.
UPSTREAM_LEGAL_DIR = os.path.join(os.path.dirname(SITE), "docs", "phase3", "legal")

LEGAL_PAGES = [
    # (markdown file, fallback permalink, nav key, fallback title, description).
    # The front matter's `title` and `permalink` win when present.
    ("privacy-policy.md", "/privacy-policy/", "privacy", "Arrow Escape — Privacy Policy",
     "What Arrow Escape: Tap Puzzle collects, why, who we share it with, and your choices."),
    ("terms-of-service.md", "/terms/", "terms", "Arrow Escape — Terms of Service",
     "The terms for playing Arrow Escape: Tap Puzzle."),
]

# Placeholder tokens used in the legal docs -> site-config.json key.
TOKEN_KEYS = {
    "[EFFECTIVE DATE]": "effectiveDate",
    "[COMPANY/DEVELOPER NAME]": "developerName",
    "[POSTAL ADDRESS]": "postalAddress",
    "[SUPPORT_EMAIL]": "supportEmail",
    "[JURISDICTION]": "jurisdiction",
    "[PRIVACY OFFICER NAME/TITLE]": "privacyOfficer",
    "[PRIVACY_POLICY_URL]": "privacyPolicyUrl",
}
REQUIRED_KEYS = ["developerName", "postalAddress", "supportEmail", "effectiveDate",
                 "jurisdiction", "privacyOfficer", "siteUrl", "privacyPolicyUrl"]
OPTIONAL_KEYS = ["googlePlayUrl", "appStoreUrl"]
# basePath: the URL prefix the site is served under ("/arrow-escape" for the project site
# https://abdullahfoysal.github.io/arrow-escape/; "" for a root/custom-domain site).
# siteUrl is the origin only (scheme + host, no path).

# Leftover placeholders in output: [UPPER CASE ...] or [2]-style numeric choices.
PLACEHOLDER_RE = re.compile(r"\[(?:[A-Z][A-Z0-9_/ .&-]{2,}(?:,[^\]\[]*)?|\d+)\]")
# Editorial notes for the reviewer: *[confirm ...]* -> rendered as <em>[...]</em>.
NOTE_RE = re.compile(r"<em>\[(?:[^\[\]]|\[[^\[\]]*\])*\]\.?</em>")


# --------------------------------------------------------------------------- config
def is_unfilled(value):
    v = (value or "").strip()
    return (not v) or (v.startswith("[") and v.endswith("]")) or "<" in v or ">" in v


def load_config():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    for k in REQUIRED_KEYS + OPTIONAL_KEYS:
        cfg.setdefault(k, "")
    cfg["siteUrl"] = cfg["siteUrl"].rstrip("/")
    base = (cfg.get("basePath") or "").strip().strip("/")
    cfg["basePath"] = ("/" + base) if base else ""
    return cfg


def with_base(html_text, base):
    """Prefix root-relative href/src/action attributes ("/x") with the base path."""
    if not base:
        return html_text
    return re.sub(r'\b(href|src|action)="/(?!/)', lambda m: '%s="%s/' % (m.group(1), base), html_text)


# ------------------------------------------------------------------ markdown → html
def strip_front_matter(text):
    meta = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            text = text[end + 4:]
    return meta, text


def strip_review_blocks(text, dropped):
    """Remove 'requires legal review' banners, whether HTML comments or marked blocks."""
    # Marked blocks: <!-- BEGIN/START ... legal review ... --> ... <!-- END ... -->
    marked = re.compile(
        r"<!--\s*(?:BEGIN|START)[^>]*?legal[\s_-]*review[^>]*?-->.*?<!--\s*END[^>]*?-->",
        re.I | re.S)
    text, n = marked.subn("", text)
    if n:
        dropped.append("%d marked legal-review block(s)" % n)
    # Any remaining HTML comments (including a single-comment review banner).
    comments = re.findall(r"<!--.*?-->", text, re.S)
    review_notes = [c for c in comments if re.search(r"REVIEW[-_ ]NOTE|DRAFT[-_ ]BANNER|legal review", c, re.I)]
    if review_notes:
        dropped.append("REVIEW:%d" % len(review_notes))
    if comments:
        dropped.append("%d HTML comment(s)" % len(comments))
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return text


def slugify(s):
    s = re.sub(r"^\s*\d+[.)]\s*", "", s).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "section"


class Inline:
    def __init__(self):
        self.stash = []

    def _keep(self, s):
        self.stash.append(s)
        return "\x00%d\x00" % (len(self.stash) - 1)

    def render(self, text):
        t = html.escape(text, quote=False)
        t = re.sub(r"`([^`]+)`", lambda m: self._keep("<code>%s</code>" % m.group(1)), t)
        t = re.sub(r"\[([^\]\[]+)\]\(([^)\s]+)\)",
                   lambda m: self._keep('<a href="%s">%s</a>' % (html.escape(m.group(2)), m.group(1))), t)

        def autolink(m):
            url = m.group(0)
            trail = ""
            while url and url[-1] in ".,;:":
                trail = url[-1] + trail
                url = url[:-1]
            return self._keep('<a href="%s">%s</a>' % (url, url)) + trail
        t = re.sub(r"https?://[^\s<)\]]+", autolink, t)
        t = re.sub(r"\*\*(?=\S)(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<![*\w])\*(?=\S)(.+?)(?<=\S)\*(?![*\w])", r"<em>\1</em>", t)
        while "\x00" in t:
            t = re.sub(r"\x00(\d+)\x00", lambda m: self.stash[int(m.group(1))], t)
        return t


LIST_RE = re.compile(r"^(\s*)([-*]|\d+[.)])\s+(.*)$")


def render_list(lines, inline):
    """lines: list of (indent, ordered, text). Returns HTML for a nested list."""
    out = []

    def build(i, base_indent):
        ordered = lines[i][1]
        tag = "ol" if ordered else "ul"
        out.append("<%s>" % tag)
        while i < len(lines) and lines[i][0] >= base_indent:
            indent, _, text = lines[i]
            if indent > base_indent:
                out.pop()  # reopen previous </li>
                i = build(i, indent)
                out.append("</li>")
                continue
            out.append("<li>%s" % inline.render(text))
            out.append("</li>")
            i += 1
        out.append("</%s>" % tag)
        return i

    i = 0
    while i < len(lines):
        i = build(i, lines[i][0])
    return "\n".join(out)


def render_table(rows, inline):
    def cells(row):
        row = row.strip()
        if row.startswith("|"):
            row = row[1:]
        if row.endswith("|"):
            row = row[:-1]
        return [c.strip() for c in row.split("|")]
    head = cells(rows[0])
    body = [cells(r) for r in rows[2:]]
    h = ['<div class="table-wrap"><table>', "<thead><tr>"]
    h += ['<th scope="col">%s</th>' % inline.render(c) for c in head]
    h.append("</tr></thead><tbody>")
    for r in body:
        h.append("<tr>" + "".join("<td>%s</td>" % inline.render(c) for c in r) + "</tr>")
    h.append("</tbody></table></div>")
    return "\n".join(h)


def markdown_to_html(text, dropped):
    """Returns (h1_text, body_html, headings[(id, text)])."""
    inline = Inline()
    lines = text.splitlines()
    out, headings, used_ids = [], [], set()
    h1 = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if m:
            level, content = len(m.group(1)), m.group(2)
            idm = re.search(r"\s*\{#([\w-]+)\}\s*$", content)
            hid = idm.group(1) if idm else None
            if idm:
                content = content[:idm.start()]
            if level == 1 and h1 is None:
                h1 = content
            else:
                hid = hid or slugify(content)
                base, n = hid, 2
                while hid in used_ids:
                    hid = "%s-%d" % (base, n)
                    n += 1
                used_ids.add(hid)
                if level == 2:
                    headings.append((hid, content))
                out.append('<h%d id="%s">%s</h%d>' % (level, hid, inline.render(content), level))
            i += 1
            continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", line):
            out.append("<hr>")
            i += 1
            continue
        if line.lstrip().startswith(">"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                block.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            joined = " ".join(block)
            if re.search(r"legal review|before publishing|not legal advice", joined, re.I):
                dropped.append("legal-review banner (blockquote)")
                continue
            paras = "\n".join(block).split("\n\n")
            out.append("<blockquote>%s</blockquote>" % "".join(
                "<p>%s</p>" % "<br>\n".join(inline.render(l) for l in p.splitlines()) for p in paras))
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(render_table(rows, inline))
            continue
        if LIST_RE.match(line):
            items = []
            while i < len(lines) and lines[i].strip():
                lm = LIST_RE.match(lines[i])
                if lm:
                    indent = len(lm.group(1).replace("\t", "    "))
                    items.append([indent, lm.group(2)[0].isdigit(), lm.group(3)])
                elif items:  # continuation line
                    items[-1][2] += " " + lines[i].strip()
                i += 1
            out.append(render_list([tuple(x) for x in items], inline))
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6}\s|>|\|)", lines[i]) \
                and not LIST_RE.match(lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append("<p>%s</p>" % "<br>\n".join(inline.render(p) for p in para))
    return h1, "\n".join(out), headings


# ------------------------------------------------------------------ substitutions
def substitute_tokens(md, cfg, privacy_path="/privacy-policy/"):
    for token, key in TOKEN_KEYS.items():
        value = cfg.get(key, "")
        if key == "privacyPolicyUrl" and is_unfilled(value):
            value = privacy_path  # same site; with_base() adds the base path
        if not is_unfilled(value):
            md = md.replace(token, value)
    return md


def email_html(cfg):
    e = cfg["supportEmail"]
    if is_unfilled(e):
        return '<mark class="ph">%s</mark>' % html.escape(e or "[SUPPORT_EMAIL]")
    return '<a href="mailto:%s">%s</a>' % (html.escape(e), html.escape(e))


def mark_leftovers(body):
    """Highlight unfilled placeholders and reviewer notes in generated HTML."""
    notes = NOTE_RE.findall(body)
    body = NOTE_RE.sub(lambda m: '<mark class="ph">%s</mark>' % m.group(0), body)
    found = []

    def repl(m):
        found.append(m.group(0))
        return '<mark class="ph">%s</mark>' % m.group(0)
    # Only outside tags/attributes.
    parts = re.split(r"(<[^>]+>)", body)
    for n, p in enumerate(parts):
        if not p.startswith("<") and "ph\">" not in (parts[n - 1] if n else ""):
            parts[n] = PLACEHOLDER_RE.sub(repl, p)
    body = "".join(parts)
    return body, found, notes


def linkify_email(body, cfg):
    e = cfg["supportEmail"]
    if is_unfilled(e):
        return body
    parts = re.split(r"(<a\b[^>]*>.*?</a>|<[^>]+>)", body, flags=re.S)
    for n, p in enumerate(parts):
        if p and not p.startswith("<"):
            parts[n] = p.replace(html.escape(e), email_html(cfg))
    return "".join(parts)


# ------------------------------------------------------------------ fonts: TTF → WOFF
def ttf_to_woff(src, dst):
    """WOFF 1.0 encoder (zlib per table), stdlib only."""
    data = open(src, "rb").read()
    flavor, num_tables = struct.unpack(">IH", data[:6])
    entries = []
    for t in range(num_tables):
        tag, checksum, offset, length = struct.unpack(">4sIII", data[12 + 16 * t: 28 + 16 * t])
        entries.append((tag, checksum, offset, length))
    entries.sort(key=lambda e: e[0])
    header_size = 44 + 20 * num_tables
    blobs, dir_entries, offset = [], [], header_size
    for tag, checksum, toff, tlen in entries:
        raw = data[toff:toff + tlen]
        comp = zlib.compress(raw, 9)
        stored = comp if len(comp) < len(raw) else raw
        dir_entries.append(struct.pack(">4sIIII", tag, offset, len(stored), tlen, checksum))
        pad = (4 - len(stored) % 4) % 4
        blobs.append(stored + b"\0" * pad)
        offset += len(stored) + pad
    total_sfnt = 12 + 16 * num_tables + sum((e[3] + 3) & ~3 for e in entries)
    header = struct.pack(">4sIIHHIHHIIIII", b"wOFF", flavor, offset, num_tables, 0,
                         total_sfnt, 1, 0, 0, 0, 0, 0, 0)
    with open(dst, "wb") as f:
        f.write(header + b"".join(dir_entries) + b"".join(blobs))


# ------------------------------------------------------------------ page assembly
def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(rel, content):
    path = os.path.join(DIST, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def page(cfg, draft, title, description, path, content, nav=None, noindex=False, paths=None):
    tpl = read(os.path.join(SRC, "templates", "base.html"))
    site = cfg["siteUrl"]
    banner = ""
    if draft:
        banner = ('<div class="draft-banner" role="note">DRAFT, not yet published. '
                  'Some details below are placeholders.</div>\n')
    robots = '<meta name="robots" content="noindex">\n' if (draft or noindex) else ""
    dev = cfg["developerName"]
    dev_html = ('<mark class="ph">%s</mark>' % html.escape(dev)) if is_unfilled(dev) else html.escape(dev)
    values = {
        "title": html.escape(title),
        "og_title": html.escape(title),
        "description": html.escape(description),
        "canonical": html.escape(site + cfg["basePath"] + path),
        "og_image": html.escape(site + cfg["basePath"] + "/assets/img/og-image.png"),
        "robots_meta": robots,
        "draft_banner": banner,
        "content": content,
        "support_email_html": email_html(cfg),
        "developer_name": dev_html,
        "year": str(datetime.date.today().year),
    }
    for key in ("support", "privacy", "terms"):
        values["cur_" + key] = ' aria-current="page"' if nav == key else ""
    out = tpl
    for k, v in values.items():
        out = out.replace("{{%s}}" % k, v)
    # Fill shared placeholders used inside page fragments too.
    out = out.replace("{{support_email_html}}", email_html(cfg))
    for k, v in (paths or {}).items():
        out = out.replace("{{%s}}" % k, v)
    out = with_base(out, cfg["basePath"])
    left = re.findall(r"\{\{\w+\}\}", out)
    if left:
        raise SystemExit("build error: unsubstituted template variables %s in %s" % (left, path))
    return out


def store_links(cfg):
    links = []
    if not is_unfilled(cfg["googlePlayUrl"]):
        links.append('<a class="btn" href="%s">Get it on Google Play</a>' % html.escape(cfg["googlePlayUrl"]))
    if not is_unfilled(cfg["appStoreUrl"]):
        links.append('<a class="btn" href="%s">Download on the App Store</a>' % html.escape(cfg["appStoreUrl"]))
    return "".join(links)


def legal_meta(md_name):
    return strip_front_matter(read(os.path.join(LEGAL_DIR, md_name)))[0]


def build_legal(cfg, md_name, report, privacy_path):
    src = os.path.join(LEGAL_DIR, md_name)
    raw = read(src)
    meta, body_md = strip_front_matter(raw)
    dropped = []
    body_md = strip_review_blocks(body_md, dropped)
    body_md = substitute_tokens(body_md, cfg, privacy_path)
    h1, body, headings = markdown_to_html(body_md, dropped)
    body = linkify_email(body, cfg)
    body, found, notes = mark_leftovers(body)
    review = sum(int(d.split(":")[1]) for d in dropped if d.startswith("REVIEW:"))
    dropped = [d for d in dropped if not d.startswith("REVIEW:")]
    report[md_name] = {"dropped": dropped, "placeholders": found, "notes": notes, "review": review}
    eff = cfg["effectiveDate"]
    eff_html = ('<mark class="ph">%s</mark>' % html.escape(eff)) if is_unfilled(eff) else html.escape(eff)
    toc = "\n".join('<li><a href="#%s">%s</a></li>' % (hid, Inline().render(text)) for hid, text in headings)
    content = (
        '<div class="page legal">\n<div class="wrap wrap--narrow">\n'
        '<h1 id="top">%s</h1>\n<p class="meta">Last updated: %s</p>\n'
        '<nav class="card toc" aria-labelledby="toc-title"><h2 id="toc-title">Contents</h2>\n<ol>\n%s\n</ol></nav>\n'
        '<article class="card">\n%s\n</article>\n'
        '<p class="back-top"><a href="#top">Back to top</a></p>\n</div>\n</div>'
    ) % (Inline().render(h1 or md_name), eff_html, toc, body)
    return meta, content


REVIEW_COMMENT_RE = re.compile(r"<!--(?:(?!-->).)*?(?:REVIEW[-_ ]NOTE|DRAFT[-_ ]BANNER|legal review)(?:(?!-->).)*-->",
                               re.I | re.S)


def strip_comments(text):
    """Remove every HTML comment and squeeze the blank lines they leave behind."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return re.sub(r"\n{3,}", "\n\n", text)


def count_review_comments(text):
    return len(REVIEW_COMMENT_RE.findall(text))


def check_legal_sync():
    """Names of committed legal copies that differ from the upstream docs (if upstream exists)."""
    stale = []
    for md_name, *_ in LEGAL_PAGES:
        up = os.path.join(UPSTREAM_LEGAL_DIR, md_name)
        here = os.path.join(LEGAL_DIR, md_name)
        if not os.path.exists(here):
            raise SystemExit("build error: %s is missing. Run python3 tools/sync_legal.py from the game project."
                             % os.path.relpath(here))
        if os.path.exists(up) and strip_comments(read(up)) != read(here):
            stale.append(md_name)
    return stale


def main():
    strict = "--strict" in sys.argv
    cfg = load_config()
    unfilled_keys = [k for k in REQUIRED_KEYS if is_unfilled(cfg.get(k))]

    stale = check_legal_sync()

    # Permalinks come from the legal docs' front matter (e.g. /privacy-policy/).
    paths = {}
    for md_name, permalink, nav, _, _ in LEGAL_PAGES:
        paths[nav + "_path"] = "/" + legal_meta(md_name).get("permalink", permalink).strip("/") + "/"

    report = {}
    legal = []
    for md_name, permalink, nav, title, desc in LEGAL_PAGES:
        meta, content = build_legal(cfg, md_name, report, paths["privacy_path"])
        legal.append((paths[nav + "_path"], nav, meta.get("title", title), desc, content))

    leftovers = [p for r in report.values() for p in r["placeholders"]]
    notes = [n for r in report.values() for n in r["notes"]]
    # Legal-review status is read from the SOURCE docs (content/legal/ copies are comment-free).
    upstream_found = True
    for md_name, *_ in LEGAL_PAGES:
        up = os.path.join(UPSTREAM_LEGAL_DIR, md_name)
        if os.path.exists(up):
            report[md_name]["review"] += count_review_comments(read(up))
        else:
            upstream_found = False
    review = sum(r["review"] for r in report.values())
    allow_review = "--allow-review-notes" in sys.argv
    draft = bool(unfilled_keys or leftovers or notes)

    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)

    # Static assets
    shutil.copytree(os.path.join(SRC, "assets"), os.path.join(DIST, "assets"),
                    ignore=shutil.ignore_patterns("*.ttf", ".DS_Store"))
    for ttf in ("Manrope-Regular", "Manrope-Bold"):
        ttf_to_woff(os.path.join(SRC, "assets", "fonts", ttf + ".ttf"),
                    os.path.join(DIST, "assets", "fonts", ttf + ".woff"))
    shutil.copy(os.path.join(SRC, "favicon.ico"), os.path.join(DIST, "favicon.ico"))
    open(os.path.join(DIST, ".nojekyll"), "w").close()

    robots = "User-agent: *\nAllow: /\n"
    if not is_unfilled(cfg["siteUrl"]):
        root = cfg["siteUrl"] + cfg["basePath"]
        robots += "\nSitemap: %s/sitemap.xml\n" % root
        urls = ["/", "/support/", paths["privacy_path"], paths["terms_path"], "/licenses/"]
        write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s</urlset>\n'
              % "".join("  <url><loc>%s%s</loc></url>\n" % (root, u) for u in urls))
    write("robots.txt", robots)

    # Pages
    def fragment(name):
        text = read(os.path.join(SRC, "pages", name)).replace("{{store_links}}", store_links(cfg))
        # {{notice:file.txt}} -> verbatim, escaped text from src/notices/
        return re.sub(r"\{\{notice:([\w.-]+)\}\}",
                      lambda m: html.escape(read(os.path.join(SRC, "notices", m.group(1))).strip("\n"), quote=False),
                      text)

    write("index.html", page(cfg, draft, "Arrow Escape: Tap Puzzle",
                             "Tap an arrow to slide it off the board. Blocked arrows bump. "
                             "Hundreds of levels, a daily challenge, no timers. Coming soon to Google Play and the App Store.",
                             "/", fragment("index.html"), paths=paths))
    write("support/index.html", page(cfg, draft, "Support | Arrow Escape: Tap Puzzle",
                                     "Contact Arrow Escape support, find your Support ID, and get answers to common questions.",
                                     "/support/", fragment("support.html"), nav="support", paths=paths))
    for permalink, nav, title, desc, content in legal:
        write(permalink.strip("/") + "/index.html", page(cfg, draft, title, desc, permalink, content, nav=nav, paths=paths))
    write("licenses/index.html", page(cfg, draft, "Licences | Arrow Escape: Tap Puzzle",
                                      "Open-source software, font and music notices for Arrow Escape: Tap Puzzle.",
                                      "/licenses/", fragment("licenses.html"), paths=paths))
    write("404.html", page(cfg, draft, "Page not found | Arrow Escape: Tap Puzzle",
                           "This page doesn't exist.", "/404.html", fragment("404.html"), noindex=True, paths=paths))

    # Report
    total = 0
    for root, _, files in os.walk(DIST):
        total += sum(os.path.getsize(os.path.join(root, f)) for f in files)
    print("Built %s (%d KB total), base path %r" % (os.path.relpath(DIST), total // 1024, cfg["basePath"] or "/"))
    for name in stale:
        print("NOTE: content/legal/%s differs from the game project's docs/phase3/legal/%s. "
              "Run python3 tools/sync_legal.py to refresh it." % (name, name), file=sys.stderr)
    for name, r in report.items():
        if r["dropped"]:
            print("  %s: dropped %s" % (name, ", ".join(r["dropped"])))
    if draft:
        bar = "!" * 72
        print("\n" + bar, file=sys.stderr)
        print("!!  WARNING: SITE IS A DRAFT. Every page shows a 'DRAFT, not yet published' banner", file=sys.stderr)
        print("!!  and carries <meta name=robots content=noindex>. Do not publish as-is.", file=sys.stderr)
        if unfilled_keys:
            print("!!  Unfilled site-config.json keys: %s" % ", ".join(unfilled_keys), file=sys.stderr)
        for name, r in report.items():
            if r["placeholders"]:
                uniq = sorted(set(r["placeholders"]))
                print("!!  %s: %d placeholder(s) left: %s" % (name, len(r["placeholders"]), ", ".join(uniq)),
                      file=sys.stderr)
            if r["notes"]:
                print("!!  %s: %d reviewer note(s) like *[confirm ...]* still in the text" % (name, len(r["notes"])),
                      file=sys.stderr)
        print(bar + "\n", file=sys.stderr)
    else:
        print("All placeholders filled.")

    review_block = False
    if not upstream_found:
        print("!!  WARNING: ../docs/phase3/legal/ not found (standalone clone): legal-review status "
              "can't be checked here. Check it in the game project.", file=sys.stderr)
    if review:
        bar = "!" * 72
        print("\n" + bar, file=sys.stderr)
        print("!!  LEGAL REVIEW NOT FINISHED: docs/phase3/legal/ still has DRAFT-BANNER/REVIEW-NOTE comments:",
              file=sys.stderr)
        for name, r in report.items():
            if r["review"]:
                print("!!    %s: %d" % (name, r["review"]), file=sys.stderr)
        print("!!  (They are never copied into content/legal/ or the pages.)", file=sys.stderr)
        if allow_review:
            print("!!  --allow-review-notes given: continuing anyway. Publish knowingly.", file=sys.stderr)
        else:
            review_block = True
        print(bar + "\n", file=sys.stderr)

    if strict and (draft or review_block):
        sys.exit(1)
    if not draft and not review:
        print("Ready to publish.")


if __name__ == "__main__":
    main()
