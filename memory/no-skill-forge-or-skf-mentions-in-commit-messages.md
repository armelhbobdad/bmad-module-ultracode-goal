---
created: "2026-06-04 09:59"
session: "d8b3ff6b-9cc2-4e88-9519-91e7549ab6bf"
---

# No skill-forge or skf mentions in commit messages

The names skill-forge (also "skill forge") and skf never appear in this repository's commit messages: the user asked for it on 2026-06-04, and since the exact wording was not captured the rule comes from the assistant's contemporaneous record of session d8b3ff6b. The sibling repository is the structural reference, so ports of its README, docs, CI, installer and website content are described on their own terms ("adds the installer chain", "two static validators"), never as "ported from skill-forge", because the two modules are independent projects and a reader meeting the other name in this history would be confused about the relationship. That session applied the rule to code comments, README.md, docs/, CHANGELOG.md and website/ as well (the assistant's extension, which has held: at v2.2.0 no tracked file outside memory/ and no commit on any branch matches), and CONTRIBUTING.md, which sets the commit-message convention, does not record it. Before committing, run `git grep -n -i -E 'skill.?forge|\bskf\b' -- . ':!memory/' ':!MEMORY.md'` and check the commit message against the same pattern. The tracked memory store is outside the rule: on 2026-09-21 the user chose to keep two memory notes that name the sibling repo in their titles.
