# Agent Course Capstone - Production Service

Production-oriented educational service для Week 9 Capstone: FastAPI сервис, оборачивающий существующий `AgentRuntime` в HTTP API с персистентным состоянием, асинхронным выполнением, Docker и observability.

**Это не production-ready система** — учебный production-like сервис для демонстрации принципов. Нет HA, масштабирования, production secrets management.

## Архитектура

```
Client (HTTP)
    │
    ▼
FastAPI Service
    │
    ├── POST /tasks → 202 Accepted + task_id
    ├── GET /tasks/{task_id} → status, result, trace
    ├── GET /health → liveness probe
    │
    ▼
PostgreSQL (Task Store)
    │
    ▼
Agent Runtime (Integration Lab)
    │
    ├── ScriptedPlanner (deterministic; ModelClient is not connected)
    ├── Tools + Policy (Week 5-6)
    └── GitHub API (External Integration)
```

## Быстрый старт

### 1. Подготовка окружения

```bash
cd labs/integration-lab

# Скопируйте .env.example и заполните значения
cp .env.example .env
```

**По умолчанию `RUNNER_MODE=test`** — не требует `GITHUB_TOKEN`. Задача создаётся, но tool calls не выполняются.

Для demo/production режимов нужен **fine-grained Personal Access Token**:
- один token → один repository → minimum permissions
- Issues: read/write (read для list/get, write для create/close)
- Contents: **не требуется** — этот flow работает только через Issues
- Metadata: read (требуется GitHub API для валидации токена)
- Избегайте classic PAT со scope `repo` — он даёт доступ ко всем репозиториям

`ModelClient` — архитектурная часть Week 4, но текущий deterministic Production Layer использует `ScriptedPlanner` и не подключает LLM.

### 2. Запуск через Docker Compose (рекомендуется)

```bash
# Из корня репозитория
docker compose -f labs/integration-lab/docker-compose.yml up --build
```

Сервис будет доступен на `http://localhost:8000`

### 3. Локальный запуск (для разработки)

```bash
cd labs/integration-lab

# Установите зависимости
pip install -e ".[dev]"

# Запустите PostgreSQL (отдельно)
# docker run -d --name postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16-alpine

# Запустите сервис
agent-service
# или
python -m integration_lab.service
```

## API Endpoints

### `POST /tasks`
Создаёт задачу для асинхронного выполнения агентом.

**Request:**
```json
{
  "task": "Create an issue in owner/repo with title 'Bug: login fails'",
  "metadata": {"priority": "high"}
}
```

**Response (202 Accepted):**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued"
}
```

### `GET /tasks/{task_id}`
Возвращает статус и результат выполнения.

**Response (200 OK):**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "created_at": "2024-01-15T10:30:00Z",
  "started_at": "2024-01-15T10:30:01Z",
  "completed_at": "2024-01-15T10:30:15Z",
  "result": {
    "status": "completed",
    "results": [{"issue_number": 42, "url": "https://github.com/owner/repo/issues/42"}],
    "trace": [...]
  },
  "error": null,
  "execution_id": "run-a1b2c3d4"
}
```

**Статусы:** `queued` | `running` | `completed` | `failed` | `needs_approval` | `blocked`

### Статусный контракт

| Статус | Terminal? | `completed_at` | Значение |
|---|---|---|---|
| `queued` | нет | `null` | Задача создана, ожидает выполнения |
| `running` | нет | `null` | Выполняется в background |
| `completed` | да | установлен | Успешно завершена, `result` доступен |
| `failed` | да | установлен | Ошибка после начала execution (provider/tool/API failure, timeout или исчерпанный retry), `error` доступен |
| `needs_approval` | нет | `null` | Persisted snapshot выполнения, остановленного на HumanGate; это не success и не completed execution. |
| `blocked` | да | установлен | Действие не допущено до исполнения: policy rejection, insufficient scope, invalid arguments, unknown tool, repository not allowed или явно отклонённое human approval. `error` содержит причину. |

`blocked` и `failed` — terminal outcomes и фиксируют `completed_at`. `needs_approval` — non-terminal persisted snapshot остановленного execution на HumanGate с `completed_at = null`. Текущий сервис не предоставляет resume endpoint, поэтому это не полноценное возобновляемое состояние очереди, не success и не completed execution.

### `GET /health`
Liveness probe.

**Response:**
```json
{
  "status": "healthy",
  "service": "agent-course-capstone",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Конфигурация

Все настройки через environment variables (`.env`):

| Переменная | Описание | Default |
|------------|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg://postgres:postgres@localhost:5432/agent_course` |
| `GITHUB_TOKEN` | GitHub Personal Access Token (требуется для demo/production режимов) | `""` (не требуется для `RUNNER_MODE=test`) |
| `GITHUB_BASE_URL` | GitHub API base URL | `https://api.github.com` |
| `SERVICE_HOST` | Bind host | `0.0.0.0` |
| `SERVICE_PORT` | Bind port | `8000` |
| `LOG_LEVEL` | Log level | `INFO` |
| `DEFAULT_MAX_RETRIES` | Повторы после первоначального запроса (максимум попыток = значение + 1) | `3` |
| `RUNNER_MODE` | `test` (пустой planner) или `demo` (create_issue ToolCall) | `test` |
| `GITHUB_OWNER` | Owner для demo create_issue | `demo-owner` |
| `GITHUB_REPO` | Repository для demo create_issue | `demo-repo` |
| `DEMO_APPROVE_WRITES` | Auto-approve write operations в demo mode | `false` |

## Тесты

```bash
cd labs/integration-lab
pip install -e ".[dev]"

# pytest использует SQLite in-memory (не требует PostgreSQL)
pytest tests/ -v

# CI запускает pytest с PostgreSQL service
# Docker/demo использует PostgreSQL через docker-compose
```

## Docker

```bash
# Build
docker build -t agent-course-capstone -f labs/integration-lab/Dockerfile labs/integration-lab

# Run (требует PostgreSQL)
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql+psycopg://postgres:postgres@host.docker.internal:5432/agent_course \
  -e GITHUB_TOKEN=your_token \
  agent-course-capstone
```

## CI/CD

Единый GitHub Actions workflow: [`.github/workflows/pages.yml`](../../.github/workflows/pages.yml). Он запускается при pull request и push в `main`, проверяет labs, собирает сайт и выполняет Docker smoke test перед публикацией Pages.

Workflow не ограничен только изменениями в `labs/integration-lab/**`.

## KPI Report

Шаблон отчёта: `labs/integration-lab/KPI_REPORT_TEMPLATE.md`

Заполните после запуска эксперимента:
- Baseline metrics (ручной процесс)
- Agent metrics (автоматизированный)
- Quality, Latency, Cost breakdown
- Human intervention analysis

## Связь с курсом

Этот Production Layer — продолжение Capstone, а не отдельный проект. Он применяет все концепции курса:

| Неделя | Концепция | Применение в Production Layer |
|--------|-----------|-------------------------------|
| Week 1 | Baseline, problem-definition | KPI report: baseline (ручной процесс) vs agent |
| Week 2 | Workflow / Handoff | AgentRuntime: planner → tools → review |
| Week 3 | Context / State | Persistent State в PostgreSQL, `path:line` evidence в trace |
| Week 4 | ModelClient | `ModelClient` — архитектурная граница курса; текущий Production Layer использует deterministic `ScriptedPlanner`. Подключение LLM через ModelClient возможно как будущее расширение, но сейчас не реализовано. |
| Week 5 | Runtime / Policy / HumanGate | `AgentRuntime`, `Policy` и `HumanGate`. Finite run budget изучается в учебном runtime Week 5, но не подключён к deterministic Production Layer. |
| Week 6 | Tools / Permissions | Tool registry, Policy (allowlist), Permission (scope), Approval |
| Week 7 | Evaluation / Trace | Trace события, метрики (quality, cost, latency, human intervention) |
| Week 9 | Production / KPI | FastAPI, PostgreSQL, Docker, observability, KPI report

## Режимы работы

Production Layer имеет три чётко разделённых режима. Не смешивайте их.

### Test / CI

```text
RUNNER_MODE=test
ScriptedPlanner с пустым calls=[]
без IssueApiClient
без GITHUB_TOKEN
no real side effects
```

Задача создаётся и успешно завершается (`completed` с пустым `result.results` и `trace`), но tool calls не выполняются. Используется в CI и для проверки lifecycle API. **Не требует GITHUB_TOKEN.**

### Demo

```text
RUNNER_MODE=demo
ScriptedPlanner с ToolCall(create_issue)
IssueApiClient (mock или реальный GitHub)
DEMO_APPROVE_WRITES — auto-approve write operations
требует GITHUB_TOKEN
```

Демонстрирует полный vertical slice: POST → ToolCall → Policy → Approval → API → Trace → Result. По умолчанию `DEMO_APPROVE_WRITES=false` — write operations требуют явного подтверждения.

### Production stub

```text
RUNNER_MODE=production (или любое значение, кроме test/demo)
реальный IssueApiClient configured, но ScriptedPlanner(calls=[]) — tool calls не выполняются
требует GITHUB_TOKEN
```

Production Layer не подключает LLM-провайдер к Production Layer. `ScriptedPlanner` с пустым calls=[] означает, что planner не подключён. Для реальной интеграции замените `ScriptedPlanner` на реальный planner через `ModelClient` из Week 4.

---

## Demo Mode

По умолчанию Production Layer использует `RUNNER_MODE=test` с `ScriptedPlanner(calls=[])` — задача создаётся, но без выполнения tool calls.

Для демонстрации полного vertical slice включите `RUNNER_MODE=demo`:

```bash
RUNNER_MODE=demo docker compose -f labs/integration-lab/docker-compose.yml up --build
```

```
POST /tasks → Agent Runtime → ToolCall(create_issue) → Policy → Approval → GitHub API → ToolResult → Trace → Result
```

В demo mode:
- `ScriptedPlanner` возвращает один `ToolCall(create_issue)`;
- `Policy` проверяет allowlist репозиториев и scopes;
- `create_issue` требует human approval (side effect), который auto-approved если `DEMO_APPROVE_WRITES=true`;
- GitHub API вызывается через `IssueApiClient` (реальный GitHub или mock).

Для CI используется mock GitHub API (`IssueApi` из `issue_api.py`), не требующий credentials.

### Конфигурация demo mode

| Переменная | Описание | Default |
|------------|----------|---------|
| `RUNNER_MODE` | `test` (пустой planner) или `demo` (create_issue ToolCall) | `test` |
| `GITHUB_OWNER` | Owner для demo create_issue | `demo-owner` |
| `GITHUB_REPO` | Repository для demo create_issue | `demo-repo` |
| `DEMO_APPROVE_WRITES` | Auto-approve write operations в demo mode | `false` |

## Ограничения (намеренно)

- ❌ LLM runtime не подключён — сервис использует `ScriptedPlanner` как deterministic planner. `ModelClient` остаётся возможной точкой расширения из Week 4.
- ❌ Нет Kubernetes, Kafka, RabbitMQ, Celery
- ❌ Нет ELK/Grafana/Prometheus stack
- ❌ Нет Vault/KMS для секретов
- ❌ Нет production frontend
- ❌ Нет HA/multi-instance scaling
- ❌ Нет production-ready security (secrets management, audit logging)

Это **production-oriented educational service** для демонстрации принципов, не production-ready система.

## Dev-only credentials

Docker Compose использует **dev-only local credentials**:

```yaml
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
```

Это допустимо для локального стенда, но не является production configuration. Для production используйте отдельные variable files или secrets manager. `.env.example` содержит placeholder'ы — никаких реальных credentials не коммитится.

## Лицензия

Часть курса "Продвинутый практикум: мультиагентная разработка на Python".