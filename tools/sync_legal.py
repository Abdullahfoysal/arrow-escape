#!/usr/bin/env python3
"""Copy the legal docs from the game project into this website repo.

    python3 website/tools/sync_legal.py     (from the game project root)

Source: <game project>/docs/phase3/legal/{privacy-policy,terms-of-service}.md
Target: website/content/legal/   (committed in the PUBLIC website repo, read by build.py)

Every HTML comment (<!-- DRAFT-BANNER ... -->, <!-- REVIEW-NOTE: ... -->, etc.) is stripped
while copying, so internal legal-review notes never reach the public repo.

website/ is expected to sit directly inside the game project (arrow-puzzle/website).
Pass --from <dir> to copy from somewhere else.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import strip_comments, count_review_comments  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
FILES = ["privacy-policy.md", "terms-of-service.md"]


def main():
    src_dir = os.path.join(os.path.dirname(SITE), "docs", "phase3", "legal")
    if "--from" in sys.argv:
        src_dir = os.path.abspath(sys.argv[sys.argv.index("--from") + 1])
    dst_dir = os.path.join(SITE, "content", "legal")
    missing = [f for f in FILES if not os.path.exists(os.path.join(src_dir, f))]
    if missing:
        sys.exit("sync_legal: %s not found in %s (run this from inside the game project, or pass --from DIR)"
                 % (", ".join(missing), src_dir))
    os.makedirs(dst_dir, exist_ok=True)
    for f in FILES:
        src, dst = os.path.join(src_dir, f), os.path.join(dst_dir, f)
        with open(src, encoding="utf-8") as fh:
            raw = fh.read()
        clean = strip_comments(raw)
        same = False
        if os.path.exists(dst):
            with open(dst, encoding="utf-8") as fh:
                same = fh.read() == clean
        if not same:
            with open(dst, "w", encoding="utf-8") as fh:
                fh.write(clean)
        n = raw.count("<!--")
        print("%s %s -> %s (%d comment(s) stripped, %d of them review notes)"
              % ("unchanged" if same else "copied   ", src, os.path.relpath(dst), n, count_review_comments(raw)))


if __name__ == "__main__":
    main()
