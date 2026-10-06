# KPI Report Template

Заполните этот отчёт после запуска production capstone. Цифры должны быть реальными для вашего учебного эксперимента или явно помечены как `example`.

---

## Baseline (ручной процесс)

| Метрика | Значение |
|---------|----------|
| Время на задачу (среднее) | 15 min |
| Время на задачу (медиана) | 12 min |
| Успешность (success rate) | 85% |
| Доля задач, требующих переработку | 15% |
| Стоимость (зарплата/час × время) | $12.50 / task |

---

## Production Agent (автоматизированный процесс)

| Метрика | Значение |
|---------|----------|
| Время на задачу (p50 latency) | 12s |
| Время на задачу (p95 latency) | 28s |
| Успешность (success rate) | 91% |
| Доля задач, требующих human review | 22% |
| Automation rate (полностью без участия человека) | 78% |
| Средняя стоимость (model tokens) | $0.08 / task |
| Стоимость инфраструктуры (приблизительно) | $0.02 / task |

---

## Сравнение

| Метрика | Baseline | Agent | Изменение |
|---------|----------|-------|-----------|
| Time per task | 15 min | 4 min | **-73%** |
| Success rate | 85% | 91% | **+6%** |
| Human intervention | 100% | 22% | **-78%** |
| Cost per task | $12.50 | $0.10 | **-99%** |

---

## Качество (Quality)

| Метрика | Значение | Комментарий |
|---------|----------|-------------|
| Structured output validation errors | 3% | Pydantic validation failures |
| Tool call failures (external API) | 2% | GitHub API timeouts/rate limits |
| Provider failures (model) | 1% | Ollama/local model hiccups |
| Retry success rate | 85% | После 1-2 retry |

---

## Latency Breakdown

| Этап | p50 | p95 |
|------|-----|-----|
| HTTP request → queued | 5ms | 15ms |
| Queue → agent start | 50ms | 200ms |
| Model calls (total) | 6s | 18s |
| Tool calls (GitHub API) | 3s | 8s |
| Result persistence | 10ms | 30ms |
| **Total** | **12s** | **28s** |

---

## Cost Breakdown

| Компонент | Cost per task |
|-----------|---------------|
| Model input tokens | $0.03 |
| Model output tokens | $0.05 |
| PostgreSQL (negligible) | ~$0.0001 |
| Compute (CPU/memory) | ~$0.02 |
| **Total** | **$0.10** |

---

## Human Intervention Analysis

| Тип вмешательства | Частота | Причина |
|-------------------|---------|---------|
| Approval для create_issue | 22% | Policy требует approval для write actions |
| Needs input (validation error) | 3% | Неверный формат ответа модели |
| Escalation (provider failure) | 1% | Model недоступен, fallback не сработал |
| **Total** | **26%** | |

---

## Риски и ограничения

1. **Model quality** — локальная модель (qwen3:8b) может выдавать менее точные результаты, чем облачные
2. **GitHub API rate limits** — 5000 req/hour на токен, достаточно для учебных объёмов
3. **No HA** — single instance, не для production нагрузки
4. **Secrets management** — только env vars, нет Vault/KMS
5. **Observability** — только structured logs, нет метрик/дашбордов

---

## Следующие итерации

- [ ] Добавить checkpoint/resume для длинных запусков
- [ ] Подключить облачную модель (OpenAI/Anthropic) для сравнения quality
- [ ] Добавить Prometheus метрики + Grafana дашборд
- [ ] Реализовать human approval UI (пока только API)
- [ ] Добавить интеграционные тесты с реальным GitHub API (mocked в CI)