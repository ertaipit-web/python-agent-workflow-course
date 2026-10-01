# Repo Triage

Локальная CLI-утилита для подготовки контекста к coding-agent workflow. Она читает Markdown-issue и Python-репозиторий, выводит список файлов и символов, а затем предлагает небольшой набор файлов-кандидатов по совпадениям ключевых слов и типу задачи.

Repo Triage не вызывает модели, не изменяет исходные файлы анализируемого репозитория и не запускает команды из issue. Категория `ambiguous` всегда получает статус `needs_input`: инструмент не угадывает scope и не предлагает файлы для изменения. При задании `--output` отчёт записывается только по указанному пути.

## Требования и установка

- Python 3.11 или новее

Из каталога `labs/repo-triage`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

После установки CLI запустите её через скрипт виртуального окружения:

```powershell
.\.venv\Scripts\repo-triage.exe --repo .\sample-repo --issues .\issues
```

В корневом окружении курса:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".\labs\repo-triage[dev]"
.\.venv\Scripts\python.exe -m repo_triage --repo .\labs\repo-triage\sample-repo --issues .\labs\repo-triage\issues
.\.venv\Scripts\python.exe -m repo_triage --repo .\labs\repo-triage\sample-repo --issues .\labs\repo-triage\issues --output .\triage-report.md
```

## Формат issue

Каждый файл `.md` должен содержать заголовок и строку типа:

```markdown
# Normalize status filter
Type: bug

## Request
Match status values without regard to case.
```

Допустимы `bug`, `test`, `docs`, `ambiguous`. Если тип отсутствует или не распознан, запрос обрабатывается как `ambiguous`, а его статусом будет `needs_input`.

## Практика

В `issues/` есть по одной задаче каждого типа, в `sample-repo/` — небольшой репозиторий для анализа. Для каждой задачи сравните:

1. Что утилита включила в инвентарь и какие кандидаты ранжировала выше.
2. Какие файлы и критерии acceptance tests предложил бы planner/read-only analyst.
3. Где keyword-поиск ошибся или пропустил релевантный файл.
4. Почему неоднозначная задача должна остановиться до планирования изменений.

Ранжирование детерминированное и поверхностное: оно не анализирует граф импортов, git history, тестовое покрытие или смысл кода. Проверяйте кандидатов вручную; не считайте их доказательством релевантности.
