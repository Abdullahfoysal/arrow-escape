#!/bin/sh
# Build, check, and push dist/ to the gh-pages branch of the website repo.
# Run from the website repo root (the folder holding site-config.json):  sh tools/publish.sh
# Only with the owner's go-ahead. Needs: a git remote "origin" (github.com/Abdullahfoysal/arrow-escape)
# and push rights. It force-pushes gh-pages, which holds only built files (no history worth keeping).
#   sh tools/publish.sh                        normal: fails while legal review comments remain upstream
#   sh tools/publish.sh --allow-review-notes   publish before legal review is finished (still warns loudly)
set -eu
cd "$(dirname "$0")/.."
python3 tools/build.py --strict "$@"
python3 tools/check.py
REMOTE_URL=$(git remote get-url origin)
TMP=$(mktemp -d)
cp -R dist/. "$TMP"/
cd "$TMP"
git init -q
git checkout -q -b gh-pages
git add -A
git commit -q -m "Publish site from $(cd - >/dev/null && git rev-parse --short HEAD 2>/dev/null || echo local)"
git push -f "$REMOTE_URL" gh-pages
cd - >/dev/null
rm -rf "$TMP"
echo "Pushed. Site: https://abdullahfoysal.github.io/arrow-escape/ (allow 1-2 minutes)."
