# Учебный репозиторий: Taskboard

Небольшой Python-пакет для практики по анализу issue, handoff-контрактам, тестированию и ограниченной работе coding agents. Это отдельный проект внутри репозитория курса: его можно запускать независимо, не устанавливая зависимости самого сайта.

## Требования

- Python 3.11 или новее
- Git

## Установка и тесты

Из каталога `labs/starter-repo` в PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

Изначальный набор тестов должен проходить. Для issue 01 добавьте новый acceptance test перед исправлением кода и сохраните его ожидаемое падение как baseline.

## Содержимое

- `src/taskboard/` — небольшой пакет с задачами и статусами;
- `tests/` — исходные regression tests;
- `issues/` — пять задач с scope и критериями приёмки;
- `exercises/` — инструкции и протокол сравнения single-agent и multi-agent.

Не добавляйте реальные credentials, `.env` или приватные данные в этот проект и в артефакты запусков.
