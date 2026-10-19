#!/usr/bin/env python3
"""Preview dist/ exactly as GitHub Pages serves the project site.

    python3 website/tools/serve.py [port]     -> http://localhost:8000/arrow-escape/

Serves dist/ under the basePath from site-config.json, redirects / to it, adds the
trailing slash to directories, and answers unknown paths with dist/404.html (status 404),
like GitHub Pages.
"""
import functools
import http.server
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
DIST = os.path.join(SITE, "dist")


def base_path():
    with open(os.path.join(SITE, "site-config.json"), encoding="utf-8") as f:
        b = (json.load(f).get("basePath") or "").strip().strip("/")
    return "/" + b if b else ""


class Handler(http.server.SimpleHTTPRequestHandler):
    base = ""

    def send_head(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if self.base and not (path == self.base or path.startswith(self.base + "/")):
            if path == "/":
                self.send_response(302)
                self.send_header("Location", self.base + "/")
                self.end_headers()
                return None
            return self.not_found()
        if self.base and path == self.base:
            self.send_response(301)
            self.send_header("Location", self.base + "/")
            self.end_headers()
            return None
        rel = path[len(self.base):] or "/"
        fs = os.path.join(DIST, rel.lstrip("/"))
        if os.path.isdir(fs) and not rel.endswith("/"):
            self.send_response(301)
            self.send_header("Location", path + "/")
            self.end_headers()
            return None
        if os.path.isdir(fs):
            fs = os.path.join(fs, "index.html")
        if not os.path.isfile(fs):
            return self.not_found()
        self.path = rel if not rel.endswith("/") else rel + "index.html"
        return super().send_head()

    def not_found(self):
        page = os.path.join(DIST, "404.html")
        body = open(page, "rb").read() if os.path.exists(page) else b"404"
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        import io
        return io.BytesIO(body)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    if not os.path.isdir(DIST):
        sys.exit("dist/ not found. Run python3 tools/build.py first.")
    Handler.base = base_path()
    handler = functools.partial(Handler, directory=DIST)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    print("Serving %s at http://localhost:%d%s/  (Ctrl+C to stop)" % (DIST, port, Handler.base))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
