---
created: "2026-08-15 16:07"
session: "23469d3c-bb7a-4480-8f18-58ba7e6ddfde"
---

# Live improvement queue in the GMC consumer checkout

Asked "Can we also clean the improvement-queue?", the assistant read this repo's own gitignored `_bmad-output/ultracode-goal/improvement-queue/` and reported it clean; the user corrected: "I were talking about this queue [GMC checkout]/\_bmad-output/ultracode-goal/improvement-queue/". The live intake is the GMC dogfooding consumer's queue, because that is where runs happen (every project gets the default `health_check_queue_path`, see [docs/health-check.md](../docs/health-check.md)); this repo's own directory only holds filings ported from GMC to be worked on here. The standing expectations, in the user's words: "The queue should be empty in the end" and "update the [GMC checkout]/\_bmad-output/ultracode-goal/improvement-queue/resolved/README.md if it is stale". Closure is placement in `resolved/` plus a row in that README; the archive step (`resolved/` subfolder, then `health_check_fp.py record --action resolved`) is documented under "Workflow Health Check" in CONTRIBUTING.md.
