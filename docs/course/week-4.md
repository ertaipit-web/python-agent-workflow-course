# Неделя 4. Подключение выбранного model provider

<div class="week-brief">
<dl>
<dt>Что уже умеем</dt>
<dd>Вызывать модель и проверять её ответ.</dd>
<dt>Какую проблему решаем</dt>
<dd>Workflow не должен зависеть от конкретного provider SDK; нужен надёжный способ валидировать structured output, tool calls и обрабатывать сбои.</dd>
<dt>Что нового появится</dt>
<dd>ModelClient абстракция, schema validation, tool calling lifecycle, failure handling, mock provider для тестов.</dd>
<dt>Что получится в конце</dt>
<dd>Рабочий провайдер через ModelClient, smoke test, structured output validation, mock provider в тестах.</dd>
</dl>
</div>

---

!!! note "Что меняем в Capstone"
    **Week 4.** Выносим model call за ModelClient boundary: structured output validation, tool calling lifecycle, retry/failure handling. Смена провайдера больше не требует переписывания workflow.

### Вспомни прошлую неделю

1. Чем отличаются State, Context и Evidence?
2. Где в Capstone хранится факт, а где шаг получает только нужный ему контекст?

## Worked example: why provider abstraction

Raw provider call → provider-specific code spread through workflow → **problem: workflow tied to one provider**

> **Anti-pattern:** этот код намеренно показывает provider-specific вызов внутри прикладной логики. Он приведён для демонстрации проблемы coupling. Рекомендуемый интерфейс курса — `ModelClient`.

```python
# Плохо: прямой вызов SDK внутри бизнес-логики
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Analyze this code..."}],
    response_format={"type": "json_object"}
)
data = json.loads(response.choices[0].message.content)
```

```python
# Лучше: ModelClient — тонкий адаптер
class ModelClient:
    def __init__(self, provider: str, model: str, **kwargs):
        self._provider = provider
        self._model = model
        self._config = kwargs

    def generate(self, messages: list[dict], schema: dict | None = None) -> dict:
        # provider-specific logic здесь, а не в workflow
        ...

    def generate_with_tools(self, messages: list[dict], tools: list[dict]) -> "ToolCall":
        ...

# Workflow использует только общий интерфейс
model = ModelClient("openai", "gpt-4o-mini")
result = model.generate(messages, schema=MySchema.model_json_schema())
```

Workflow не знает деталей provider SDK. Смена провайдера = смена одной строки конфигурации.

---

## Материал

### Extension / Experiment: один workflow — два провайдера

Сравнение провайдеров необязательно. Это эксперимент для желающих измерить, как выбор модели меняет latency, cost и quality; техническое ядро недели от него не зависит.

```text
Provider A (OpenAI)          Provider B (Ollama local)
     ↓                            ↓
ModelClient ←── same interface ──→ ModelClient
     ↓                            ↓
Same workflow logic         Same workflow logic
```

Студент меняет provider, workflow остаётся прежним. Provider-specific код изолирован в `ModelClient`.

```python
# Конфигурация — единственное, что меняется
PROVIDER_CONFIGS = {
    "cloud": {"provider": "openai", "model": "gpt-4o-mini", "api_key": os.getenv("OPENAI_KEY")},
    "local": {"provider": "ollama", "model": "qwen3:8b", "base_url": "http://localhost:11434/v1"},
}

model = ModelClient(**PROVIDER_CONFIGS["local"])  # или "cloud"
result = model.generate(messages, schema=AnalysisSchema.model_json_schema())
```

### Обязательное ядро: контролируемый model lifecycle

Для Core достаточно одного выбранного провайдера за `ModelClient`: валидируйте structured output, проверяйте предложенный tool call до исполнения, обработайте ошибки и замените provider на mock в тесте.

---

### Structured output: validation pipeline

Следующий шаг workflow ожидает структуру, а модель может вернуть свободный текст или невалидный JSON.

```text
LLM output
    ↓
schema validation (Pydantic / JSON Schema)
    ↓
valid?
 ├─ yes → next step receives typed dict
 └─ no  → retry with error / return needs_input / blocked
```

```python
from pydantic import BaseModel, ValidationError

class AnalysisResult(BaseModel):
    issue_type: Literal["bug", "refactor", "docs"]
    affected_files: list[str]
    confidence: float = Field(ge=0, le=1)

def validate_structured_output(raw: dict, schema: type[BaseModel]) -> BaseModel:
    try:
        return schema.model_validate(raw)
    except ValidationError as e:
        # ValidationError поднимается наверх — retry logic решает, что делать
        raise
```

**Failure example:** модель вернула `{"issue_type": "feature"}` — не в enum. Validation выбрасывает `ValidationError`. Retry logic ловит его, делает повторную попытку с error context. Только после исчерпания retry — поднимается `ProviderError`, workflow решает: `needs_input` / `blocked`.

---

### Tool calling: lifecycle

```text
Model
  ↓
structured tool request (name, arguments)
  ↓
tool validation (schema + policy + permissions)
  ↓
tool execution (runtime)
  ↓
tool result (success / error / timeout)
  ↓
next model step
```

> **Tool calling ≠ автономное выполнение.** Модель *предлагает* вызов, runtime решает:
> - допустим ли инструмент (allowlist);
> - валидны ли аргументы (schema);
> - можно ли выполнить (permissions, approval);
> - что делать с ошибкой (retry / escalate / blocked).

Это связывает Week 4 с Week 5–6: `ModelClient` возвращает `ToolCall`, `Runtime` валидирует и исполняет.

```python
@dataclass
class ToolCall:
    name: str
    arguments: dict
    call_id: str

@dataclass
class ToolResult:
    call_id: str
    output: Any
    error: str | None = None

def execute_tool(call: ToolCall, registry: ToolRegistry, policy: Policy) -> ToolResult:
    # 1. Найти tool в registry
    # 2. Валидировать аргументы по schema
    # 3. Проверить policy (allowlist, permissions)
    # 4. Исполнить или вернуть error
    ...
```

---

### Failure experiment: model call — unreliable dependency

| Scenario | What runtime sees | What application should do |
|----------|-------------------|----------------------------|
| **A. Normal** | Valid response | Continue workflow |
| **B. Timeout** | `TimeoutError` / no response | Retry (idempotent only) → escalate → `blocked` |
| **C. Invalid structured output** | `ValidationError` | One retry with error context → `needs_input` / `blocked` |
| **D. Provider error / unavailable** | HTTP 5xx / connection error | Retry with backoff → fallback provider / `blocked` |

```python
class ProviderError(Exception):
    def __init__(self, message: str, retryable: bool = False, fallback: str | None = None):
        self.retryable = retryable
        self.fallback = fallback

def call_with_retry(model: ModelClient, messages: list, schema: type, max_retries: int = 2):
    for attempt in range(max_retries + 1):
        try:
            raw = model.generate(messages)
            return validate_structured_output(raw, schema)
        except ValidationError as e:
            if attempt == max_retries:
                raise ProviderError(f"Structured output invalid after {max_retries} retries: {e}")
            messages.append({"role": "assistant", "content": str(e)})  # feedback для retry
        except TimeoutError:
            if attempt == max_retries:
                raise ProviderError("Provider timeout", retryable=True)
            time.sleep(2 ** attempt)
        except ProviderError as e:
            if not e.retryable or attempt == max_retries:
                raise
            time.sleep(2 ** attempt)
    raise ProviderError("Exhausted retries")
```

---

### Mock provider: deterministic tests

Зачем mock provider:
- тесты не зависят от реального API;
- можно воспроизводить ошибки (timeout, invalid output, provider down);
- CI не требует API credentials;
- workflow прогоняется детерминированно.

```python
class MockModelClient(ModelClient):
    def __init__(self, responses: list[dict | Exception]):
        self._responses = iter(responses)

    def generate(self, messages: list[dict], schema: dict | None = None) -> dict:
        resp = next(self._responses)
        if isinstance(resp, Exception):
            raise resp
        return resp

# Тест: workflow обрабатывает invalid structured output
def test_workflow_handles_invalid_output():
    mock = MockModelClient([
        {"wrong_field": "value"},  # invalid schema
        {"issue_type": "bug", "affected_files": ["a.py"], "confidence": 0.9},
    ])
    result = run_workflow(mock, issue="...")
    assert result.status == "complete"
```

---

### Decision table: что проверять на каждом шаге

| Ситуация | Что проверяем |
|----------|---------------|
| Structured output | schema validation (Pydantic) |
| Tool call | arguments schema + policy + permissions |
| Timeout | retry (idempotent) / backoff / escalate |
| Provider unavailable | fallback / failure handling |
| Expensive model | cost tracking / budget limit |
| Slow model | latency budget / async |
| Sensitive data | privacy: local-only / no-logging |

---

## Практика {: .course-section .course-section--practice }

**Обязательное ядро:** настроить `ModelClient` для выбранного провайдера, выполнить smoke test с structured output и одним tool call.
{: .course-note .course-note--core }

1. Реализовать `ModelClient.generate(schema=...)` с Pydantic validation.
2. Добавить один tool call через `ModelClient.generate_with_tools(...)` и выполнить его через runtime.
3. Проверить failure case: передать намеренно невалидный schema, убедиться, что validation ловит ошибку.
4. Заменить реальный provider на `MockModelClient` и прогнать существующий workflow тест.

**Расширение:** сравнить два провайдера (cloud + local) на одном наборе задач; зафиксировать latency, cost, quality.
{: .course-note .course-note--extension }

**Extension / Experiment:** provider-specific параметры, подробное сравнение privacy и локального/облачного запуска не нужны для зачёта Core.
{: .course-note .course-note--extension }

---

## Результат недели {: .course-section .course-section--result }

После этой недели я могу:

- заменить provider без переписывания workflow;
- валидировать structured output через schema;
- понимать lifecycle tool call: proposal → validation → execution → result;
- обрабатывать типовые provider failures (timeout, invalid output, unavailable);
- использовать mock provider в тестах для детерминированных прогонов;
- учитывать latency / cost / privacy при выборе модели.

!!! takeaway "Capstone checkpoint"
    **Week 4.** Provider-specific SDK скрыт за `ModelClient`, а tool calling проходит контролируемый lifecycle: proposal → validation → execution → result.

### Проверь себя

1. Какую зависимость `ModelClient` прячет от workflow?
2. Чем tool proposal отличается от tool execution?
3. Какой вызов Capstone теперь можно подменить mock provider?

---

## Навигация

| | |
|---|---|
| ← | [Week 3: Context engineering](week-3/) |
| → | [Week 5: Runtime / Orchestration](week-5/) |