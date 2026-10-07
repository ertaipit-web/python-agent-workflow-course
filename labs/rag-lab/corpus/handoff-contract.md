# Handoff artifact

Every handoff artifact must contain a status, a short summary, evidence with source references, assumptions, open questions and a next action. A free-form paragraph is not a handoff: the receiving role cannot validate it, and an orchestrator cannot decide whether the workflow may continue.

## Statuses

A handoff carries one of four statuses: `complete`, `needs_input`, `blocked` or `failed`. `needs_input` means the request is ambiguous and a human has to answer a question. `blocked` means a policy or permission rejected the next action before it executed. `failed` means a model/tool execution started but produced an invalid handoff, hit an error or exhausted its retry budget.

A missing fact must produce `needs_input` instead of a confident guess. Success-shaped fallbacks are the main reason an agent workflow hides failures from its operator.

## Evidence

Evidence is a list of claims, and every claim points at a file with a line range or at a document with an identifier. A claim without a source reference cannot be reviewed, so it must not be presented as a finding.

## Validation

The orchestrator validates the handoff schema before it calls the next role. Unknown fields, an empty evidence list for a code finding, or a status that does not match the content of the summary are validation errors, not details of style. If the producing model already ran and bounded retries cannot repair the output, the run is `failed`; validation prevents the next role from executing.
