---
created: "2026-11-03 00:32"
session: "3db662c1-d326-4c49-93fb-f5b18179d765"
---

# macOS install-smoke leg cancelled by GitHub hosted-runner capacity

The 4.1.0 install smoke run 41526247961 concluded failure because `smoke (macos-latest)` was cancelled after 15 minutes with "The job was not acquired by Runner of type hosted even after multiple attempts" and "Due to capacity constraints, jobs targeting macOS ...": a GitHub runner shortage, not the package, since the ubuntu and windows legs had installed 4.1.0. `gh run rerun 41526247961 --failed` re-ran only that leg, the "Attach the result to the GitHub Release" job then ran, and `gh release download v4.1.0 --pattern install-smoke.json` showed all three legs successful. With this fingerprint, rerun the failed job rather than debugging, re-dispatching, or taking the failing-leg route to Scenario B in docs/_internal/RELEASING.md.
