# Практикум мультиагентных систем на Python

Продвинутый практикум по мультиагентной разработке на Python.

🌐 **[Открыть сайт курса](https://ertaipit-web.github.io/python-agent-workflow-course/)**

Материалы курса оформлены как Zensical-сайт.

## Локальный просмотр в Windows

Не открывайте `site/course/` как `file://...`: при стандартной настройке Zensical используются URL страниц вида `/course/`, которым нужен HTTP-сервер. Из корня проекта запустите preview-сервер в PowerShell:

```powershell
if (-not (Test-Path .\.venv\Scripts\python.exe)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install "zensical==0.0.67"
.\.venv\Scripts\python.exe -m pip install -e ".\labs\starter-repo[dev]"
.\.venv\Scripts\python.exe -m pip install -e ".\labs\repo-triage[dev]"
.\.venv\Scripts\python.exe -m pip install -e ".\labs\rag-lab[dev]"
.\.venv\Scripts\python.exe -m pip install -e ".\labs\integration-lab[dev]"
.\.venv\Scripts\python.exe -m zensical serve
```

Оставьте терминал открытым и перейдите по адресу **http://localhost:8000/**. Основной курс доступен по адресу **http://localhost:8000/course/**. Остановить сервер можно сочетанием `Ctrl+C`.

Чтобы только собрать статический сайт без запуска preview-сервера:

```powershell
.\.venv\Scripts\python.exe -m zensical build --strict
```

Если виртуальное окружение `.venv` уже настроено, не создавайте его заново; установите в него только отсутствующие зависимости.

Готовый сайт создаётся в `site/`. Эта директория генерируется командой build и не является исходником документации. Для локального просмотра используйте `zensical serve`, а не открытие файлов из `site/` напрямую.

## GitHub Pages

Workflow [`.github/workflows/pages.yml`](.github/workflows/pages.yml) проверяет учебные Python-проекты и собирает сайт на pull request в `main`; после каждого push/merge в `main` он также публикует сайт в GitHub Pages. Один только локальный commit workflow не запускает — нужен push. Базовый URL проекта определяется GitHub Pages автоматически.

Чтобы включить публикацию в GitHub:

1. Создайте или подготовьте GitHub-репозиторий для проекта.
2. Откройте **Settings → Pages** и установите **Build and deployment → Source: GitHub Actions**.
3. Подключите local repo к GitHub remote и отправьте ветку `main`.
4. Проверьте выполнение workflow во вкладке **Actions**. После успешного deploy URL сайта появится в deployment `github-pages`.

Опубликованный сайт: **[ertaipit-web.github.io/python-agent-workflow-course](https://ertaipit-web.github.io/python-agent-workflow-course/)**. Локальную сборку можно проверить командой `zensical build --strict`.

## Структура

- `zensical.toml` — настройки проекта.
- `docs/index.md` — главная страница и карта курса.
- `docs/course.md` — основной 8-недельный практикум с обязательным ядром и необязательными расширениями.
- `docs/autonomous-agents.md` — каталог из 6 модулей по автономным агентам; выбирайте 2–3 по своему use case.
- `docs/ollama-vscode.md` — команды подключения Ollama к VS Code Chat и Kilo, диагностика по симптомам.
- `docs/local-models.md` — выбор локальной модели под объём RAM и фиксация результатов локального прогона.
- `docs/sources.md` — источники и материалы, использованные при подготовке программы.
- `docs/lab-repository.md` — четыре учебных проекта: когда открывать каждый и как получить файлы.
- `docs/repo-triage.md` — локальный разбор issue и инвентаризация Python-репозитория.
- `docs/rag-lab.md` — retrieval как инструмент агента: chunking, embeddings, vector search, отказ отвечать без источника и метрики качества.
- `docs/integration-lab.md` — агент и внешняя система: REST-сервис issue, scopes, least privilege, human gate и trace.
- `labs/starter-repo/` — автономный учебный Python-проект с issue и pytest-тестами.
- `labs/repo-triage/` — локальная утилита для разбора issue и инвентаризации Python-репозитория.
- `labs/rag-lab/` — retrieval tool, grounded-ответчик и набор проверочных вопросов с метриками.
- `labs/integration-lab/` — локальный REST-сервис issue, типизированные инструменты агента и runtime с разрешениями.
- `.github/workflows/pages.yml` — проверка, сборка и публикация GitHub Pages.
