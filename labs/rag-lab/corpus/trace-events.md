# Trace events

A trace answers one question: why did the workflow reach this result. It records the nodes that ran, the data they received, the tool that was selected, what the tool returned and why the system moved to the next state.

## Minimal event

Each event carries a run identifier, a node identifier, an attempt counter, the model or provider tag, the prompt version, references to input and output artifacts, a status, a duration, an error type and a transition reason. The transition reason is the field that makes a run readable: it states why the orchestrator moved on.

## Separate artifacts from prompts

Tool results, exit codes and trace spans belong to their own records and are linked by run identifier and node identifier. The full prompt and the hidden reasoning of the model are not required to reconstruct a run, and storing the whole repository for every step is a data leak rather than a debugging aid.

## Failure chains

For every failure the chain failure, detection, recovery or escalation and the final state is written down. A retry is allowed only within a fixed limit, and a tool with an external side effect is never repeated blindly after a timeout, because the first attempt may already have been applied.

## Retention

Traces contain text, arguments and error messages, so keys, tokens and personal data are removed before logging and a retention period is defined. Long-running workflows produce more events than memory allows, which is why events are summarised per node and kept outside the model context.
