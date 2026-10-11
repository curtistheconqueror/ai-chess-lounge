#!/bin/bash
# usage: e2e-smoke/run.sh <spec-or-grep args...>  -> prints compact summary with annotations
cd "$(dirname "$0")/.."
export PLAYWRIGHT_JSON_OUTPUT_NAME=smoke-out/r.json
npx playwright test -c playwright.smoke.config.ts --reporter=json "$@" >/dev/null 2>&1
node e2e-smoke/summarize.mjs smoke-out/r.json --notes
