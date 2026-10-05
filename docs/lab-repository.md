# Учебные репозитории курса

В репозитории курса есть четыре самостоятельных Python-проекта с собственными зависимостями и тестами. Они не являются частью Zensical-сайта:

| Проект | Когда открывать | Материалы |
|---|---|---|
| **Taskboard** (`labs/starter-repo/`) | Самый простой вводный проход: небольшая задача, baseline-тесты и контракт работы агента. | Пять issue и упражнения в `labs/starter-repo/issues/` и `labs/starter-repo/exercises/`; инструкции — в `labs/starter-repo/README.md`. |
| **Repo Triage** (`labs/repo-triage/`) | Второй шаг: подготовка фактов о запросе и структуре существующего Python-репозитория. Локальная CLI-утилита собирает инвентарь файлов и символов, ранжирует контекст по ключевым словам и отмечает неоднозначные запросы как требующие уточнения. | Четыре issue типов bug/test/docs/ambiguous, тестовый Python-репозиторий и инструкции в `labs/repo-triage/README.md`. |
| **RAG Lab** (`labs/rag-lab/`) | Тема retrieval из недели 3 в коде: ingestion, chunking, embeddings, vector search, retrieval tool, ответ с цитатами и отказ отвечать без источника. | Корпус Markdown-документов, набор проверочных вопросов с метриками и инструкции в `labs/rag-lab/README.md`. |
| **Integration Lab** (`labs/integration-lab/`) | Тема tools и policy из недели 6 на реальной внешней системе: локальный REST-сервис issue поверх SQLite, типизированные инструменты, scopes, least privilege, human gate и trace. | Четыре сценария запуска и инструкции в `labs/integration-lab/README.md`. |

Подробное описание каждой лаборатории есть на сайте: [Repo Triage](repo-triage.md), [RAG Lab](rag-lab.md), [Integration Lab](integration-lab.md).

Repo Triage не вызывает LLM, не меняет код и не запускает команды в анализируемом репозитории. Ранжирование файлов — эвристика для подготовки контекста, а не замена анализа разработчиком или coding agent.

RAG Lab и Integration Lab тоже работают без API-ключей: retrieval использует детерминированный локальный embedder и extractive-ответчик, а Integration Lab поднимает собственный локальный сервис. Обе лаборатории устроены так, чтобы заменяемая часть — эмбеддер, ответчик и planner — оставалась за интерфейсом, как `ModelClient` в основном курсе.

## Как получить файлы

- Если репозиторий уже клонирован, откройте `labs/starter-repo/` в корне checkout-а.
- Если вы читаете опубликованный сайт, откройте исходный GitHub-репозиторий курса, выберите **Code → Download ZIP**, распакуйте архив и перейдите в `labs/starter-repo/`.

Учебный проект можно открыть отдельно в VS Code, но для изменений курса и лабораторных достаточно одного клона. Submodule не нужен: материалы и упражнения меняются вместе с программой курса.

Для общего окружения курса из корня репозитория установите тестовые зависимости и запустите оба suite:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".\labs\starter-repo[dev]"
.\.venv\Scripts\python.exe -m pip install -e ".\labs\repo-triage[dev]"
.\.venv\Scripts\python.exe -m pip install -e ".\labs\rag-lab[dev]"
.\.venv\Scripts\python.exe -m pip install -e ".\labs\integration-lab[dev]"
.\.venv\Scripts\python.exe -m pytest .\labs\starter-repo\tests
.\.venv\Scripts\python.exe -m pytest .\labs\repo-triage\tests
.\.venv\Scripts\python.exe -m pytest .\labs\rag-lab\tests
.\.venv\Scripts\python.exe -m pytest .\labs\integration-lab\tests
```

Если учебный проект скопирован отдельно от курса, установите его в собственное окружение `.venv` по инструкциям в README этого проекта.
