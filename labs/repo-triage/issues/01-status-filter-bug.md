# Normalize status filter
Type: bug

## Request

Status filtering currently treats `OPEN` and `open` as different values. Make matching case-insensitive without changing the stored status.

## Acceptance criteria

- A filter value with different casing matches the same status.
- The original task objects are not mutated.
- Add a regression test.
