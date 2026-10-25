---
created: "2026-08-07 11:31"
session: "9507dda8-dad6-4b2c-ae09-66cac7a0d9d3"
---

# STABILITY.md posture strings hand-moved on every major bump

`docs/_internal/STABILITY.md` ships in the npm tarball as the public contract a consumer pins against (`test/test-pack-contents.js` checks that it ships), but its major-version posture lives in three hand-maintained strings: the frontmatter `description` ("The 3.x stability posture: ..."), the `> **Status:** 3.x.` line, and the opening sentence. v2.0.0 shipped all three saying `1.x` (`git show v2.0.0:docs/_internal/STABILITY.md | grep 'Status:'`) because 5a4a59b wrote the `1.x` strings fresh during 2.0.0 prep, and caf3a8d (2026-08-06, "chore: state the 2.x posture") flipped them in the v2.1.0 prep, a rationale the generated CHANGELOG never carried. Since PR #161 (merged 2026-10-25 as 8162fa4) the release gate catches a missed one: `node tools/changes.js gate --bump major` (`postureProblem` in `tools/changes.js`) refuses while the Status line names another major, with a message ending "restate it as N.x by pull request", the rc hand-bump message names the restatement, and `npm run test:changes-tool` checks that the three strings agree; `docs/_internal/RELEASING.md` documents it. The strings are still moved by hand, in a pull request before the cut (and in the hand-bump pull request when an RC comes first, since an RC ships the file too).
