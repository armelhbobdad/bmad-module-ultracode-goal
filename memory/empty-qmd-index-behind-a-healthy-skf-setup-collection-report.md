---
created: "2026-11-18 22:53"
session: "a57a12c7-5bbf-4ae1-bf92-0e1c4f19db41"
---

# Empty QMD index behind a healthy skf-setup collection report

`skf-setup` reported all 19 registered QMD collections as "healthy" while `qmd status` showed "Total: 0 files indexed": its check (`skf-qmd-classify-collections.py`) only matches collection names and never looks at what is indexed. Deep-tier SKF runs therefore got no QMD context and raised no warning. Running `qmd update` then `qmd embed` rebuilt the machine-wide index under `~/.cache/qmd` in about 7 minutes, to 86 files. Before a Deep-tier run, read `qmd status` rather than the setup report. The check gap is SKF issue #1245.
