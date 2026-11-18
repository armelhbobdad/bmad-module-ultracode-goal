---
created: "2026-11-18 00:11"
session: "2e0859f5-9e6d-4ee2-9f4b-2f2cdbb0f2dc"
---

# Lower-case `www.` trim on a gh --repo host, absent from --hostname

gh drops one leading lower-case `www.` from the host of a `--repo HOST/OWNER/REPO` value before it lower-cases it (ghrepo's TrimPrefix), then applies the other host rules (`*.github.com` as `github.com`, `*.github.localhost` as `github.localhost`, `api.TENANT.ghe.com` as `TENANT.ghe.com`). Probed on gh 2.104.0 with `gh issue list --repo <host>/o/r` against `.invalid` hosts on 2026-11-17: `www.ghe-probe.invalid` printed `error connecting to ghe-probe.invalid`, `WWW.ghe-probe.invalid` and `Www.GHE-probe.invalid` printed `error connecting to www.ghe-probe.invalid`, `www.WWW.ghe-probe.invalid` reached `www.ghe-probe.invalid` (one trim only), and `www./o/r` went to gh's default host. `--hostname` on `gh auth status` and `gh api`, and `gh auth login --hostname`, take the host verbatim: a login to `www.HOST` or a mixed-case HOST is one no `--repo` call uses. So `health_check_fp.py`'s `_normalize_host` (`repo` subcommand, `_issue_prefix`) mirrors the trim since #244 (PR #245), and the Health Check page says to log in with HOST in lower case and without a leading `www.`; the sibling module's helper had not taken the trim when PR #245 merged.
