#!/usr/bin/env python3
"""Check website/dist/: internal links and anchors, basic HTML validity, leftovers.

    python3 website/tools/check.py

Exit 1 on errors. Unfilled [PLACEHOLDER]s are reported as expected warnings
(the build marks the site DRAFT while they remain); an error is raised only if a
placeholder survives whose site-config.json value IS filled (a substitution bug).
"""
import html.parser
import json
import os
import re
import sys
from urllib.parse import urlparse, unquote

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
DIST = os.path.join(SITE, "dist")
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import build  # noqa: E402

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Page(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors, self.ids, self.links = [], [], [], []
        self.h1 = 0
        self.has_title = False
        self.lang = None
        self.text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        if tag == "h1":
            self.h1 += 1
        if tag == "title":
            self.has_title = True
        if tag == "img" and "alt" not in a:
            self.errors.append("img without alt: %s" % a.get("src"))
        if "id" in a:
            self.ids.append(a["id"])
        for k in ("href", "src"):
            if a.get(k):
                self.links.append((tag, a[k]))
        if tag not in VOID:
            self.stack.append((tag, self.getpos()))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1][0] != tag:
            # allow implicit </p>/<li> closing only as an error report
            self.errors.append("mismatched </%s> at line %d (open: %s)" % (
                tag, self.getpos()[0], self.stack[-1] if self.stack else None))
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    break
            return
        self.stack.pop()

    def handle_data(self, data):
        self.text.append(data)


def target_file(path):
    p = os.path.join(DIST, unquote(path).lstrip("/"))
    if path.endswith("/") or os.path.isdir(p):
        p = os.path.join(p, "index.html")
    return p


def main():
    cfg = build.load_config()
    site = cfg["siteUrl"]
    base = cfg["basePath"]
    filled_tokens = {t for t, k in build.TOKEN_KEYS.items() if not build.is_unfilled(cfg.get(k))}
    errors, warnings, pages, external = [], [], {}, set()

    for root, _, files in os.walk(DIST):
        for f in files:
            if f.endswith(".html"):
                path = os.path.join(root, f)
                src = open(path, encoding="utf-8").read()
                p = Page()
                p.feed(src)
                pages[path] = (p, src)

    for path, (p, src) in sorted(pages.items()):
        rel = os.path.relpath(path, DIST)
        if not src.lower().startswith("<!doctype html>"):
            errors.append("%s: missing <!doctype html>" % rel)
        if p.lang != "en":
            errors.append("%s: <html lang> is %r" % (rel, p.lang))
        if not p.has_title:
            errors.append("%s: no <title>" % rel)
        if p.h1 != 1:
            errors.append("%s: %d <h1> elements" % (rel, p.h1))
        if 'name="viewport"' not in src:
            errors.append("%s: no viewport meta" % rel)
        for prop in ("og:title", "og:description", "og:image", "og:url"):
            if 'property="%s"' % prop not in src:
                errors.append("%s: missing %s" % (rel, prop))
        dup = {i for i in p.ids if p.ids.count(i) > 1}
        if dup:
            errors.append("%s: duplicate ids %s" % (rel, sorted(dup)))
        errors += ["%s: %s" % (rel, e) for e in p.errors]
        if p.stack:
            errors.append("%s: unclosed tags %s" % (rel, p.stack))
        if "{{" in src or "}}" in src:
            errors.append("%s: unsubstituted template variable" % rel)
        if re.search(r"<script\b", src, re.I):
            errors.append("%s: contains a <script> (site should be script-free)" % rel)
        text = "".join(p.text)
        for m in build.PLACEHOLDER_RE.findall(text):
            if m in filled_tokens:
                errors.append("%s: %s is filled in site-config.json but still in the page" % (rel, m))
            else:
                warnings.append(m)

        for tag, url in p.links:
            u = urlparse(url)
            if u.scheme in ("mailto", "tel"):
                continue
            if u.scheme in ("http", "https"):
                if site and url.startswith(site + base + "/") and not build.is_unfilled(site):
                    url = url[len(site):]
                    u = urlparse(url)
                else:
                    if tag == "a":
                        external.add(url)
                    continue
            if tag in ("meta",):
                continue
            if not u.path and u.fragment:
                tpath, tpage = path, p
            else:
                if u.path.startswith("/"):
                    if base and not (u.path == base or u.path.startswith(base + "/")):
                        errors.append("%s: link without the base path %s: %s" % (rel, base, url))
                        continue
                    abs_path = u.path[len(base):] or "/"
                else:
                    abs_path = "/" + os.path.normpath(os.path.join(os.path.dirname(rel), u.path)).replace(os.sep, "/")
                tpath = target_file(abs_path)
                if not os.path.exists(tpath):
                    errors.append("%s: broken link %s" % (rel, url))
                    continue
                tpage = pages.get(tpath, (None,))[0]
            if u.fragment and tpage is not None and u.fragment not in tpage.ids:
                errors.append("%s: missing anchor %s" % (rel, url))

    for name in (".nojekyll", "robots.txt", "favicon.ico", "404.html", "index.html",
                 "support/index.html", "licenses/index.html") + tuple(
                     build.legal_meta(m).get("permalink", p).strip("/") + "/index.html"
                     for m, p, *_ in build.LEGAL_PAGES):
        if not os.path.exists(os.path.join(DIST, name)):
            errors.append("missing %s" % name)
    if os.path.exists(os.path.join(DIST, "app-ads.txt")):
        warnings.append("app-ads.txt present: confirm its lines came from the AdMob/LevelPlay dashboards")

    total = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(DIST) for f in fs)
    for path, (p, src) in pages.items():
        for m in re.finditer(r'(?:href|src|content)="(https?://[^"]*)"', src):
            if site and m.group(1).startswith(site + "/") and base and not m.group(1).startswith(site + base + "/"):
                errors.append("%s: absolute URL without base path: %s" % (os.path.relpath(path, DIST), m.group(1)))
    print("Base path: %r" % (base or "/"))
    print("Checked %d HTML pages, %d KB in dist/" % (len(pages), total // 1024))
    print("External links (not fetched): %d" % len(external))
    for e in sorted(external):
        print("   ", e)
    if warnings:
        counts = {}
        for w in warnings:
            counts[w] = counts.get(w, 0) + 1
        print("Expected placeholder warnings (unfilled in site-config.json):")
        for w, n in sorted(counts.items()):
            print("    %-32s x%d" % (w, n))
    if errors:
        print("ERRORS (%d):" % len(errors))
        for e in errors:
            print("   ", e)
        sys.exit(1)
    print("OK: no broken internal links or anchors, HTML structure checks passed.")


if __name__ == "__main__":
    main()
