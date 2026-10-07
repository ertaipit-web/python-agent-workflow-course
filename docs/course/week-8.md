# Неделя 8. Business Automation & Solution Design

<div class="week-brief">
<dl>
<dt>Что уже умеем</dt>
<dd>Сравнивать workflow по качеству, trace, времени и ручным вмешательствам.</dd>
<dt>Какую проблему решаем</dt>
<dd>Неясно, какую часть бизнес-процесса стоит автоматизировать и нужен ли здесь агент.</dd>
<dt>Что нового появится</dt>
<dd>Process analysis, приоритизация automation candidates и обоснованный solution design Capstone.</dd>
<dt>Что получится в конце</dt>
<dd>Спроектированная система с выбранной границей автоматизации, архитектурой и измеримыми целями.</dd>
</dl>
</div>

> 🧭 **Где мы:** LLM → Context / State → Tools → Runtime / Orchestration → Policy / Permissions → **[Evaluation / Observability]**.

---

!!! note "Что меняем в Capstone"
    **Week 8.** Не начинаем новый проект. Выбираем бизнес-процесс, уточняем automation opportunity и фиксируем, какую систему будем строить. Уже знакомый Capstone становится конкретным решением с обоснованной границей автоматизации.

### Вспомни прошлую неделю

1. Чем trace помогает отличить ошибку модели от ошибки инструмента?
2. Где измерения предыдущего Capstone workflow уже доступны?

## Сначала business framing

!!! question "🤔 Predict"
    Команда каждый день переносит одинаковые значения из одной таблицы в другую. Нужен ли для этого агент, если шаги и правила всегда одни и те же?

Не всякая повторяющаяся задача требует агента. Например, команда вручную разбирает входящие issue: часть полей можно проверять обычными правилами, часть контекста приходится искать в репозитории, а решение о записи или изменении кода остаётся за человеком. Сначала разберитесь в процессе, затем выбирайте механизм.

Начните с короткого документа `problem-definition.md` в Capstone-репозитории. Не нужна BPMN-модель: достаточно последовательного списка или простой схемы.

### AS-IS: как процесс работает сейчас

Опишите:

1. Что запускает процесс.
2. Какие шаги выполняются и в каком порядке.
3. Где и какое решение принимает человек.
4. Какие системы, файлы или API используются.
5. Где появляется результат и кто его использует.

### Pain points: где процесс теряет время или качество

Для проблемного этапа отметьте ручной труд, задержки, ошибки и повторяющиеся действия; укажите стоимость, узкие места и риски, если это известно. Не автоматизируйте весь процесс только потому, что это возможно.

### Automation candidates: что можно автоматизировать

Выберите 2–3 конкретных этапа процесса. Для оценок достаточно `low / medium / high`; точная математическая модель не нужна.

| Candidate | Frequency | Manual effort | Ambiguity | Risk | Data/API availability | Automation fit |
|---|---:|---:|---:|---:|---|---:|
| A | | | | | | |
| B | | | | | | |
| C | | | | | | |

Выберите один основной кандидат. Хороший выбор сочетает высокую ценность, достаточную автоматизируемость, приемлемый риск и доступные данные/API. В 2–3 предложениях объясните, почему выбрали именно этот участок.

### TO-BE: как будет работать выбранное решение

Опишите целевой процесс по шагам:

1. Trigger — что запускает систему.
2. Agent / workflow — какие действия выполняются автоматически.
3. Tools / integrations — какие данные и системы используются.
4. Human approval — где требуется решение человека.
5. Side effect — что система вправе изменить или отправить.
6. Result / persistence — где сохраняется результат и как его получить.

```text
AS-IS → где теряется время или качество
TO-BE → что именно теперь делает система
```

### Выбор уровня решения

Для выбранного кандидата сравните подходящие варианты: **Code**, **Workflow**, **LLM workflow** или **Agent**. Используйте самый простой механизм, который решает задачу надёжно.

Объясните кратко:

- почему выбран именно этот уровень автономности;
- почему более простой вариант недостаточен;
- почему более сложный вариант не оправдан.

Иногда правильный ответ — обычный код. Если процесс детерминированный, например проверка полей или отчёт по расписанию, агент добавит стоимость, задержки и новые точки отказа без пользы.

### Human boundary

Зафиксируйте границу автономности в `problem-definition.md`:

```text
Agent can do autonomously:
...

Human must approve / decide:
...
```

Свяжите её с уже знакомыми `Policy`, permissions и Human-in-the-loop: анализ и подготовка результата могут быть автоматическими, а значимые side effects требуют явного разрешения.

### Ожидаемый outcome и KPI

Сохраните ожидаемый outcome и риски. Для выбранного кандидата задайте baseline до автоматизации, target и измеренный результат после проверки. Для учебного проекта подойдут небольшая тестовая выборка, наблюдения или разумные оценки, явно помеченные как estimates; реальные production-данные не обязательны.

| KPI | Baseline | Target | Measured |
|---|---:|---:|---:|
| Time per task | | | |
| Manual effort | | | |
| Success rate | | | |
| Error rate | | | |
| Human intervention | | | |
| Cost per task | | | |

`Baseline` — как процесс работает до автоматизации; `Target` — чего хотим добиться; `Measured` — что получилось по факту. Не подменяйте измеренный результат целевым.

### Worked example: GitHub issue triage

Рассмотрим типичный пример, который легко перевести в Capstone:

```markdown
# Business problem
Команда получает десятки GitHub issues в день. Баги и др. задачи иногда теряются в ручной сортировке, а часть повторяющихся задач требует только чтения репозитория и проверки существующих тестов.

# AS-IS
Trigger: новый issue создаётся в GitHub.
Steps:
1. сотрудник читает issue;
2. проверяет репозиторий и связанные тесты;
3. решает, что делать: закрыть, перенаправить, ответить, или назначить фикс;
4. после решения вручную пишет комментарий или обновляет метки.
Human decision: кто именно определяет, что issue относится к bug, docs или feature request.

# Pain points
- время тратится на повторное чтение одного и того же issue;
- часть задач легко классифицировать, но их всё равно проверяет человек;
- без чётких критериев один и тот же issue интерпретируется по-разному;
- риск пропустить regression или установить неверный тип issue выше, чем польза от ручного разбора.

# Automation candidates
A. Triage label assignment
B. Read-only issue classification using repo context
C. Draft fix proposal with validation hints

Prioritization: B is the best fit because repository context matters, but the action should stay bounded and reviewable.

# Selected candidate and TO-BE
Selected candidate: read-only issue classification and acceptance criteria draft.
TO-BE:
1. issue arrives;
2. workflow reads issue text and matching files;
3. it classifies bug/refactor/docs/needs-more-info;
4. it writes a structured summary and suggests acceptance criteria;
5. human reviews and approves before any code change.

# Solution choice
LLM workflow is sufficient here: classification and evidence gathering are ambiguous, but the actual patch is still human-owned. A full autonomous agent would be too broad for this step.

# Human boundary
Agent can do:
- read repository context;
- propose likely cause and relevant files;
- produce structured classification and notes.

Human must approve:
- any code change;
- any write action or label mutation beyond safe read-only triage;
- issue assignment that changes business priority.

# Expected outcome and KPI
Baseline: 12 minutes per issue, manual triage, frequent ambiguity.
Target: 4 minutes per issue, 70% issues classified with human review only.
Measured: after pilot, time reduced and classification coverage increased for low-risk issues.
```

Это именно worked example: одна проблема, один AS-IS, один выбранный candidate и понятная Human boundary. После такого примера студент может заполнить свой own `problem-definition.md` для Capstone.

### `problem-definition.md`

Соберите решения выше в один компактный артефакт:

```markdown
# Business problem
Для кого существует проблема и какой результат нужен?

# AS-IS
Trigger, шаги, решения человека, системы и место результата.

# Pain points
На каких этапах возникают ручной труд, задержки, ошибки, стоимость или риск?

# Automation candidates
2–3 этапа, их ценность, автоматизируемость, риск и доступность данных/API.

# Selected candidate and TO-BE
Выбранный этап и целевой процесс от trigger до результата.

# Solution choice
Code, Workflow, LLM workflow или Agent — почему этот уровень достаточен?

# Human boundary
Что система делает сама, а что требует решения/approval человека?

# Expected outcome and KPI
Baseline, target, measured result; estimates отмечены явно.

# Risks
Какие ошибки, утечки или нежелательные side effects нужно предотвратить?
```

Этот же `problem-definition.md` остаётся частью Capstone и обосновывает дальнейшую реализацию.

```mermaid
flowchart LR
    ASIS["AS-IS"] --> PAIN["Pain points"] --> CANDIDATES["Automation candidates"]
    CANDIDATES --> PRIORITY["Prioritization"] --> TOBE["TO-BE"]
    TOBE --> CHOICE["Code / Workflow / Agent"] --> BOUNDARY["Human boundary"]
    BOUNDARY --> EVAL["Evaluation"] --> OUTCOME["Business outcome"]
```

---

## Практика {: .course-section .course-section--practice }

Возьмите задачу и учебные issue, с которыми работали в предыдущие недели:

1. Зафиксируйте AS-IS, включая шаги человека и используемые системы.
2. Выберите 2–3 automation candidates и обоснуйте приоритет одного.
3. Нарисуйте TO-BE как последовательность шагов; отметьте tools, данные и human boundary.
4. Сравните code, workflow, LLM workflow и agent на выбранном участке.
5. Задайте baseline, target и способ измерить результат.

Не стройте новую архитектуру, если существующий Capstone уже подходит. На этой неделе нужно решить, **что автоматизировать, почему это стоит делать и какой механизм достаточен**.

---

## Результат недели

- заполненный `problem-definition.md` с AS-IS, pain points, кандидатами, TO-BE и рисками;
- выбранный automation candidate с кратким обоснованием;
- решение Code / Workflow / LLM workflow / Agent и объяснение границ автономности;
- Human boundary, связанная с Policy, permissions и approval;
- baseline, target и план измерения outcome.

> **Итог Week 8:** система спроектирована, обоснована и имеет измеримые цели.

!!! success "🎉 What you can do now"
    Вы можете выбрать участок процесса и обосновать, достаточно ли для него обычного кода, workflow, LLM workflow или агента.

### Проверь себя

1. Как baseline помогает решить, стоит ли автоматизировать выбранный участок?
2. Чем LLM workflow отличается от автономного agent в границах решений?
3. Какое решение Week 8 определяет, что именно будет доставлено как сервис в Week 9?

---

## Архитектурный review

Обоснуйте решение в том же документе:

1. Где неоднозначность требует LLM или agent, а где достаточно детерминированного кода?
2. Какие данные и инструменты доступны выбранному компоненту и почему этого достаточно?
3. Какие действия разрешены автоматически, а какие требуют human approval?
4. Как будут измеряться качество, время, стоимость и ручные вмешательства?
5. Какой риск или failure mode может сделать автоматизацию хуже текущего процесса?

!!! rule "Общий принцип"
    Сначала самый простой работающий вариант, затем измерение и только после этого усложнение.

## Расширение: сравнить архитектуры

Необязательно перенесите тот же workflow в LangGraph. Сравните сложность state/checkpoint, наблюдаемость и удобство тестирования с простым Python-кодом. Не переписывайте проект на framework, если это не решает конкретную проблему.

## ✅ Definition of Done

- Описать AS-IS и назвать конкретное место потери времени, качества или контроля.
- Сравнить 2–3 automation candidates и выбрать один по ценности, риску и доступности данных.
- Обосновать минимально достаточный уровень решения; пройти один учебный сценарий по TO-BE и проверить Human boundary для каждого side effect.
- Задать baseline, target и способ измерить outcome для Capstone; проверить, что KPI измерим, а estimate не выдан за измерение.

> → **Дальше:** solution design задаёт границы и KPI; в Week 9 тот же Capstone станет сервисом, а измеренный результат сравним с целью.

---

## Навигация

| | |
|---|---|
| ← | [Week 7: Evaluation / Trace](week-7/) |
| → | [Week 9: Productionize the Capstone](week-9/) |
