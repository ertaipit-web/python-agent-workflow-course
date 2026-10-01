# Документация курса

Материалы курса оформлены как Zensical-сайт.

## Локальный просмотр в Windows

Не открывайте `site/course/` как `file://...`: при стандартной настройке Zensical используются URL страниц вида `/course/`, которым нужен HTTP-сервер. Из корня проекта запустите preview-сервер в PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install zensical
.\.venv\Scripts\python.exe -m zensical serve
```

Оставьте терминал открытым и перейдите по адресу **http://localhost:8000/**. Основной курс доступен по адресу **http://localhost:8000/course/**. Остановить сервер можно сочетанием `Ctrl+C`.

Чтобы только собрать статический сайт без запуска preview-сервера:

```powershell
.\.venv\Scripts\python.exe -m zensical build --strict
```

Готовый сайт создаётся в `site/`. Эта директория генерируется командой build и не является исходником документации. Для локального просмотра используйте `zensical serve`, а не открытие файлов из `site/` напрямую.

## Структура

- `zensical.toml` — настройки проекта.
- `docs/index.md` — главная страница и карта курса.
- `docs/course.md` — основной 8-недельный практикум.
- `docs/autonomous-agents.md` — дополнительный 6-недельный трек по автономным агентам.
