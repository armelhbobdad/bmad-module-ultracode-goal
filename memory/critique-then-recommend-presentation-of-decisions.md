---
created: "2026-06-03 20:39"
session: "1acef71c-d598-4de7-86ab-6746eb16bd3c"
---

# Critique-then-recommend presentation of decisions

When the user gives a tentative pick, critique it first (trade-offs, risks, where it may be wrong), then give one strong, opinionated recommendation; a pick already made that carries real risk gets pushback plus a stronger alternative before anything is built on it. The rule comes from the assistant's contemporaneous record of session 1acef71c (2026-06-03; the gitignored `skills/ultracode-goal/.decision-log.md` also records "Armel asked to always be given a critique + strong recommendation before choosing"), and the user's later words show it holding: "what is your honest recommendations?" and "let's follow your recommendations" (2026-06-08), "let take the best honest decision right now" (2026-08-03), "Let's follow your genuine recommendations" (2026-08-06). When a question is genuinely needed, a neutral menu wastes a round trip: in an AskUserQuestion, lead with the option marked "(Recommended)" and say why the others are weaker. Decisions the user has reserved ("Ask; don't pick") are still asked, with the critique and recommendation attached.

The recommendation is not a hand-back: when the user asks for genuine recommendations, the assistant makes the call itself, says which option it took and why, and starts the work, stopping only for a decision that is genuinely the user's. A critique and a recommendation followed by a hand-back is the mistaken form: on 2026-10-24 (session 3db662c1), after giving recommendations, the assistant ended with "Decisions I need from you" and called one of them "your call"; the user answered "I need you genuine help too", and later that day widened it: "you can call if when you really need my critical decision".
