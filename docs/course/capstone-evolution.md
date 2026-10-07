# Capstone: эволюция системы

Этот документ — spine курса. Вместо восьми оторванных задач вы развиваете **одну и ту же систему** от Week 1 до Week 8: agent, который безопасно решает issue в Python-репозитории. Каждая неделя меняет архитектуру, а не заменяет проект.

> **Skill Lab ≠ Capstone.** Специализированные лаборатории (Taskboard, Repo Triage, RAG Lab, Integration Lab) учит механику изолированно. Capstone показывает, зачем эта механика нужна в реальной системе.

---

## Архитектурная эволюция

```mermaid
%%{init: {"flowchart": {"useMaxWidth": false, "nodeSpacing": 20, "rankSpacing": 40}, "themeVariables": {"fontSize": "13px"}}}%%
flowchart TD
  W1["Week 1\nbaseline + issue"] --> W2["Week 2\nplanner → analyst → implementer\n+ handoff contract"]
  W2 --> W3["Week 3\n+ State\n+ evidence path:line\n+ role context"]
  W3 --> W4["Week 4\n+ ModelClient\n(provider abstraction)"]
  W4 --> W5["Week 5\n+ Runtime\n+ RunPolicy\n+ HumanGate"]
  W5 --> W6["Week 6\n+ Tools\n+ Policy\n+ Approval\n+ external integration"]
  W6 --> W7["Week 7\n+ Eval\n+ Trace"]
  W7 --> W8["Week 8\nFastAPI service\n+ PostgreSQL\n+ Docker\n+ KPI"]
  classDef week fill:#f5faf9,stroke:#0d9488,stroke-width:2px;
  class W1,W2,W3,W4,W5,W6,W7,W8 week;
```

---

## Таблица эволюции

| Week | Capstone change | Student artifact |
|----|-----------------|------------------|
| 1 | baseline + candidate task | `problem-definition.md`, baseline, acceptance criteria, issue set |
| 2 | topology + handoff | capstone graph, handoff contract schema |
| 3 | context + state | `State` struct, `path:line` evidence, role templates |
| 4 | ModelClient | `ModelClient`, structured output validation, mock provider |
| 5 | runtime + policy | `Workflow`, `RunPolicy`, `HumanGate`, budget |
| 6 | tools + external integration | Tool registry, allowlist, approval gate, external API |
| 7 | evaluation + tracing | Eval report baseline vs workflow, trace of 2 runs |
| 8 | production service | FastAPI, PostgreSQL, Docker, KPI report |

---

## Week 1 → Week 2

**Problem:** baseline работает, но передача результата между этапами теряется в свободном тексте — следующий этап догадывается.

**Change:** заменяем "один промпт" на цепочку ролей с фиксированным контрактом handoff: `planner → read-only analyst → implementer → review`.

**Reason:** каждая роль видит только то, что явно передано в контракте — а не всю историю переписки.

**Result:** student builds capstone graph с указанием read-only / write / human approval узлов.

---

## Week 2 → Week 3

**Problem:** агент видит либо слишком мало контекста (баг не воспроизводится), либо слишком много (история за 40 шагов теряет релевантное).

**Change:** вводим `State` — структурированный факты о прогрессе, `path:line` evidence вместо пересказа, JIT-контекст и role-specific шаблоны.

**Reason:** контекст — это внимание, а не объём. State передаётся между ролями вместо истории переписки.

**Result:** before/after:

```text
Week 2: agent receives issue
        → planner returns free text

Week 3: agent receives issue
        → planner fills State
        + repo_evidence with path:line
        + role-specific context
        + JIT context from read-only analyst
```

---

## Week 3 → Week 4

**Problem:** workflow завязан на конкретный provider SDK. Смена провайдера = переписывание бизнес-логики.

**Change:** выносим model call за `ModelClient` — тонкий адаптер. Workflow видит только `generate(messages, schema=...)` и `generate_with_tools(...)`.

**Reason:** модель становится заменяемой частью системы, а не частью бизнес-логики.

**Result:** student swaps provider (cloud → local) без изменения workflow кода; mock provider в тестах.

---

## Week 4 → Week 5

**Problem:** между вызовами теряется состояние, лимиты не соблюдаются, опасное действие выполняется сразу.

**Change:** формализуем runtime: `State → Role → Transition → RunPolicy → HumanGate`. RunPolicy задаёт конечный budget (calls, time, retries). HumanGate останавливает side effects.

**Reason:** без конечных retry-лимитов цикл «попробовать ещё раз» превращается в зависший процесс.

**Result:** student runs workflow с конечным бюджетом на mock; invalid schema → `blocked`, unsafe action → `needs_approval`.

---

## Week 5 → Week 6

**Problem:** модель может предложить запись, и промпт её не остановит — правило «не трогай чужие файлы» в тексте не работает.

**Change:** добавляем Tool registry с narrow schema, Policy check (allowlist путей/команд), Permission (least privilege per role), HumanGate для side effects.

**Reason:** разрешения реально применяет runtime и policy, а не текст промпта.

**Result:** Integration Lab учит механику изолированно, затем student переносит pattern в Capstone — тот же `Tool → Policy → Approval → Trace`, но уже в свой workflow.

---

## Week 6 → Week 7

**Problem:** два workflow выглядят одинаково убедительно, но один выполняет критерии приёмки, а другой нет. Разница видна только в измерении.

**Change:** запускаем Eval: ground truth, метрики (quality, cost, latency, human intervention), trace двух прогонов — baseline vs Week 6 system.

**Reason:** без измерения нельзя сравнить архитектуры. Каждое изменение должно иметь измеримую пользу.

**Result:** student produces eval report с разницей baseline vs multi-agent, root-cause из trace одного неудачного запуска.

---

## Week 7 → Week 8

**Problem:** система работает в эксперименте, но не доставляет бизнес-ценность — нет API, persistence, deployment.

**Change:** упаковываем существующий workflow в production-like сервис: FastAPI, PostgreSQL persistent state, async execution, Docker, observability, KPI.

**Reason:** Capstone продолжение, а не новый проект. Всё, что было построено в Week 1–7, переходит в сервис.

**Result:** student runs `docker compose up`, получает работающий сервис с KPI report — `time saved`, `success rate`, `automation rate`.

---

## Источники заимствований

| Skill Lab | Механика | Где применяется в Capstone |
|---|---|---|
| Taskboard | handoff contract, baseline test | Week 1-2 |
| Repo Triage | repository evidence, `path:line` | Week 3 |
| RAG Lab | JIT context, retrieval as tool | Week 3 (extension) |
| Integration Lab | Tool → Policy → Approval → Trace, external API | Week 6 → 8 |
