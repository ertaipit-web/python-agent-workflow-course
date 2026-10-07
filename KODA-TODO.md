# Task 12 — Final consistency and reliability audit

1. [x] Пункт 1: Исправить семантику `DEFAULT_MAX_RETRIES` → real retries=3 (max_attempts=4)
2. [x] Пункт 2: Сделать HTTP 429 retryable для idempotent операций
3. [x] Пункт 3: Развести `blocked` и `failed` в runtime
4. [x] Пункт 4: Исправить allowlist — убрать wildcard из Production Layer policy
5. [x] Пункт 5: Исправить integration tests для policy deny
6. [x] Пункт 6: Привести `needs_approval` к честной семантике
7. [x] Пункт 7: Исправить `completed_at` — blocked должен иметь completed_at
8. [x] Пункт 8: Исправить `RUNNER_MODE` documentation
9. [x] Пункт 9: Убрать stale GitHub permissions из Week 8
10. [x] Пункт 10: Исправить описание тестов в README (pytest vs PostgreSQL)
11. [x] Пункт 11: Сделать `pyright` настоящим CI gate (убрать `|| true`, исправить type errors)
12. [x] Пункт 12: Audit Settings — LOG_LEVEL использовать, MODEL_* пометить
13. [x] Пункт 13: Docker CI smoke test — реальный HTTP health check
14. [x] Пункт 14: Уточнить ограничения BackgroundTasks в docs
15. [x] Пункт 15: Исправить Capstone Evolution (KPI report не auto-generated)
16. [x] Пункт 16: Провести final stale-contract search
17. [x] Пункт 17: Validation — Integration Lab pytest, Ruff, Pyright, Zensical build

## Проверка результата

- Integration Lab: `71 passed`
- Pyright Integration Lab: `0 errors, 0 warnings, 0 informations`
- Ruff Integration Lab: `All checks passed`
- Zensical: `No issues found`
- Docker Compose: PostgreSQL healthy, API health check в CI использует `/health`
- Корневой `pytest -q` и `ruff check .` остаются заблокированы уже существующими ошибками в других labs (`repo-triage/sample-repo`, RAG, Repo Triage, Starter Repo). Это не является ошибкой Task 12 Integration Lab.
- В пункте 6 исходная формулировка о `needs_approval` как terminal snapshot конфликтует с фактическим контрактом и тестами. Исправлен фактический контракт: `needs_approval` — неterminal snapshot без `completed_at`, а `blocked` — terminal с `completed_at`; resume endpoint не добавлялся.
- Commit/push не выполнялись.
