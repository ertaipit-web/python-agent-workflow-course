# Agent Course Capstone - Production Service

Production Layer для Week 8 capstone: FastAPI сервис, оборачивающий существующий `AgentRuntime` в HTTP API с персистентным состоянием, асинхронным выполнением, Docker и observability.

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
    ├── ModelClient (Week 4)
    ├── Tools + Policy (Week 5-6)
    └── GitHub API (External Integration)
```

## Быстрый старт

### 1. Подготовка окружения

```bash
cd labs/integration-lab

# Скопируйте .env.example и заполните значения
cp .env.example .env

# Обязательно: GITHUB_TOKEN (Personal Access Token с scope: repo)
# Опционально: MODEL_PROVIDER, MODEL_NAME для LLM
```

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

**Статусы:** `queued` | `running` | `completed` | `failed` | `needs_approval`

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
| `GITHUB_TOKEN` | GitHub Personal Access Token | **required** |
| `GITHUB_BASE_URL` | GitHub API base URL | `https://api.github.com` |
| `MODEL_PROVIDER` | Model provider (Week 4) | `ollama` |
| `MODEL_NAME` | Model name | `qwen3:8b` |
| `MODEL_BASE_URL` | Model API base URL | `http://localhost:11434/v1` |
| `MODEL_API_KEY` | Model API key | `` |
| `SERVICE_HOST` | Bind host | `0.0.0.0` |
| `SERVICE_PORT` | Bind port | `8000` |
| `LOG_LEVEL` | Log level | `INFO` |

## Тесты

```bash
cd labs/integration-lab
pip install -e ".[dev]"

# Запуск тестов (требует PostgreSQL)
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/agent_course \
GITHUB_TOKEN=test \
pytest tests/ -v
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

GitHub Actions workflow: `.github/workflows/capstone-ci.yml`

Запускается при изменениях в `labs/integration-lab/**`:
1. **test** — pytest + pyright + ruff (с PostgreSQL service)
2. **build** — Docker build + smoke test
3. **zensical-build** — проверка сборки курса

## KPI Report

Шаблон отчёта: `labs/integration-lab/KPI_REPORT_TEMPLATE.md`

Заполните после запуска эксперимента:
- Baseline metrics (ручной процесс)
- Agent metrics (автоматизированный)
- Quality, Latency, Cost breakdown
- Human intervention analysis

## Связь с курсом

Этот Production Layer применяет все концепции курса:

| Неделя | Концепция | Применение здесь |
|--------|-----------|------------------|
| Week 1 | Baseline/workflow | Baseline measurement в KPI |
| Week 2 | Workflows/Handoff | AgentRuntime planner → tools |
| Week 3 | Context/State | PostgreSQL persistent state |
| Week 4 | ModelClient | `ScriptedPlanner` — ModelClient не обязателен; deterministic flow |

## Demo Mode

По умолчанию Production Layer использует `RUNNER_MODE=test` с `ScriptedPlanner(calls=[])` — задача создаётся, но без выполнения tool calls.

Для демонстрации полного vertical slice включите `RUNNER_MODE=demo`:

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
| `DEMO_APPROVE_WRITES` | Auto-approve write operations в demo mode | `true` |

## Ограничения (намеренно

- ❌ ModelClient (Week 4) не подключён — сервис использует `ScriptedPlanner` как deterministic planner. Для реального agent workflow подключите LLM-провайдер через ModelClient.
- ❌ Нет Kubernetes, Kafka, RabbitMQ, Celery
- ❌ Нет ELK/Grafana/Prometheus stack
- ❌ Нет Vault/KMS для секретов
- ❌ Нет production frontend
- ❌ Нет HA/multi-instance scaling

Это **учебный** production-like сервис для демонстрации принципов, не production-ready система.

## Лицензия

Часть курса "Продвинутый практикум: мультиагентная разработка на Python".