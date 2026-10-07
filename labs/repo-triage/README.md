# Repo Triage

Локальная CLI-утилита для подготовки контекста к coding-agent workflow. Она читает Markdown-issue и Python-репозиторий, выводит список файлов и символов, а затем предлагает небольшой набор файлов-кандидатов по совпадениям ключевых слов и типу задачи.

Repo Triage не вызывает модели, не изменяет исходные файлы анализируемого репозитория и не запускает команды из issue. Категория `ambiguous` всегда получает статус `needs_input`: инструмент не угадывает scope и не предлагает файлы для изменения. При задании `--output` отчёт записывается только по указанному пути.

## Требования и установка

- Python 3.11 или новее

Из каталога `labs/repo-triage` создайте окружение, установите пакет и запустите тесты.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\repo-triage.exe --repo .\sample-repo --issues .\issues
```

### macOS

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
./.venv/bin/python -m pytest
./.venv/bin/repo-triage --repo ./sample-repo --issues ./issues
```

### Linux

В Linux используются те же команды, что и в разделе macOS. Установленная CLI должна вывести Markdown-отчёт в терминал.

### Запуск из корневого окружения курса

В следующих командах предполагается текущий каталог — корень репозитория курса. Вариант через `python -m repo_triage` не зависит от расположения установленного console-script.

#### Windows PowerShell

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".\labs\repo-triage[dev]"
.\.venv\Scripts\python.exe -m repo_triage --repo .\labs\repo-triage\sample-repo --issues .\labs\repo-triage\issues
.\.venv\Scripts\python.exe -m repo_triage --repo .\labs\repo-triage\sample-repo --issues .\labs\repo-triage\issues --output .\triage-report.md
```

#### macOS / Linux

```bash
./.venv/bin/python -m pip install -e "./labs/repo-triage[dev]"
./.venv/bin/python -m repo_triage --repo ./labs/repo-triage/sample-repo --issues ./labs/repo-triage/issues
./.venv/bin/python -m repo_triage --repo ./labs/repo-triage/sample-repo --issues ./labs/repo-triage/issues --output ./triage-report.md
```

Обычный запуск выводит отчёт в терминал; команда с `--output` сохраняет его в `triage-report.md` в текущем каталоге. Создайте корневое `.venv` по инструкции в [README курса](../../README.md), если оно ещё не настроено.

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
