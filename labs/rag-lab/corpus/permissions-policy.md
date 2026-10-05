# Permissions and policy

A tool call is a proposal. The runtime checks the tool name, the typed arguments, the repository allowlist and the granted scopes before anything reaches an external system. The model never decides its own permissions.

## Least privilege

Each role receives only the scopes its task needs. A read-only analyst gets read scopes, and a role that may file a triage issue gets a write scope as well. Deny by default: an unknown tool name is rejected instead of being resolved dynamically.

## Read and write operations

Reading is reversible, writing is not. Read tools can run without a human confirmation, while a write tool needs an explicit approval step and a recorded audit entry with the run identifier, the tool name and the redacted arguments.

## Tokens and secrets

A token is a credential with a scope, not a flag. Give the agent the narrowest token that still allows the approved tool to work, and keep the token out of prompts, artifacts and traces. A trace event stores a redacted view of the arguments instead of the secret values.

## Path validation

Paths are compared with an allowlist before a file is read or written, and traversal segments such as `..` and absolute paths are rejected. Validation happens in code; an instruction in the prompt is not a boundary.
