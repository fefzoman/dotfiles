---
name: investigation
description: Resolve disputed facts, uncertain compatibility, or repeated failures when another attempt needs a new hypothesis. Skip routine lookups and failures with an established fix.
---

# Investigation

Resolve the question that changes the next decision. Keep a short evidence summary in the conversation; no separate investigation file is needed.

- Identify the unresolved question, the decision it affects, and what evidence would settle it.
- Establish the target version and execution environment. During upgrades, distinguish the requested target from the installed version. In Context7 queries, write `target version: X.Y.Z` when investigating a different version; verify that the returned source actually covers that target. If unavailable, use the exact release's primary source and state the gap.
- Retrieve only the relevant passage using the existing retrieval tools. Run a minimal check in the target environment when documentation cannot settle the question. Missing wheels alone do not prove an unsupported runtime; a failed installation establishes only that attempt's failure.
- Before another attempt, identify the changed hypothesis and the new evidence expected. Reuse established results; repeating the same experiment in another environment needs a reason tied to the target.
- When evidence settles the decision, stop investigating and continue the authorized work. If attempts add no evidence, change the hypothesis or report the blocker. Ask only when continuing changes requirements, supported behavior, cost, or authorization; preserve safety checks and meaningful validation.

For root-cause debugging, use the existing debugging skill when applicable; this skill supplies the evidence and stop conditions, not a second debugging procedure.
