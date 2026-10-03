#!/usr/bin/env bash
#
# Smoke-test the search API against a running backend.
#   ./test-search.sh                 run the verified example queries
#   ./test-search.sh "your query"    run a single custom query
#
# Requires the backend running (./run.sh backend). Uses python3 to pretty-print.
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8000}"

if ! curl -sf -m 5 -o /dev/null "$BASE/search?q=test"; then
  printf '\033[1;31m✗ Backend not reachable at %s — start it with ./run.sh backend\033[0m\n' "$BASE" >&2
  exit 1
fi

run_query() {
  local q="$1"
  printf '\033[1;36m▶ q=%q\033[0m\n' "$q"
  curl -sG -m 60 "$BASE/search" --data-urlencode "q=$q" | python3 -c '
import sys, json
d = json.load(sys.stdin)
panels = d.get("panels", [])
if not panels:
    print("  (no results)")
for p in panels[:6]:
    tags = p.get("matched_tags") or p.get("matched_labels") or []
    pid = p["id"]; via = p["matched_via"]; score = p.get("score", 0)
    print("  #%3d  via=%-11s score=%.2f  %s" % (pid, via, score, tags[:4]))
print("  %d results total" % len(panels))
'
  echo
}

if [ "$#" -ge 1 ]; then
  run_query "$*"
else
  for q in eyes angry chibi hands face smile glasses sword running screaming "open mouth"; do
    run_query "$q"
  done
fi
