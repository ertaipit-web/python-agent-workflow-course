# Справочник: Ollama, VS Code Chat и Kilo

Эта страница нужна, если вы подключаете локальную модель к VS Code или Kilo. Она не является обязательной частью основной программы: **почему локально вообще имеет смысл, какой размер модели подходит вашей памяти и какой контекст безопасен** — в [странице о выборе модели](local-models.md), а ниже только команды и диагностика.

## Что поставить на компьютер с 14 ГБ RAM

Начальный кандидат для экспериментов с локальными agent tasks — `qwen3:8b`. Для сравнения генерации/объяснения Python-кода можно отдельно попробовать `qwen2.5-coder:7b`. Эти модели могут работать медленно на CPU и не гарантируют надёжного tool calling; не ожидайте поведения на уровне облачных coding-моделей.

```powershell
ollama pull qwen3:8b
ollama run qwen3:8b
```

Начните с одного запроса, контекста 8K и закрытых лишних приложений. Повышайте контекст до 16K только после замера доступной памяти и устойчивости.

## Проверить Ollama локально

Запустите приложение Ollama, затем в PowerShell:

```powershell
ollama --version
ollama list
ollama ps
Invoke-RestMethod http://127.0.0.1:11434/api/tags
Invoke-RestMethod http://127.0.0.1:11434/v1/models
```

Если локальные API возвращают список моделей, служба доступна. На Windows отдельное `ollama serve` обычно не требуется: приложение само запускает сервер. Не запускайте второй сервер на занятом порту и не открывайте локальный API в интернет — Ollama по умолчанию привязывается к localhost, и этого достаточно для VS Code и Kilo на том же компьютере.

Другие команды:

```powershell
ollama show qwen3:8b
ollama pull qwen2.5-coder:7b
ollama run qwen2.5-coder:7b
```

В терминальном чате `ollama run` для завершения используется `/bye`, а `/show info` показывает сведения о загруженной модели. `pull` только загружает веса; `run` запускает диалог.

Чтобы закрепить настройки контекста за отдельным тегом, создайте `Modelfile` в удобной папке и выполните в ней `ollama create`:

```text
FROM qwen3:8b
PARAMETER num_ctx 8192
PARAMETER temperature 0.2
```

```powershell
ollama create qwen3-8b-ctx8k -f .\Modelfile
ollama run qwen3-8b-ctx8k
```

Новый тег использует исходные веса, но задаёт меньший контекст по умолчанию.

## Вариант 1: ответы в стандартном VS Code Chat

Это не Kilo Chat; подключение настраивается независимо:

1. Убедитесь, что Ollama запущена, модель есть в `ollama list`, `/api/tags` отвечает.
2. Установите официальное [расширение Ollama для VS Code](https://marketplace.visualstudio.com/items?itemName=Ollama.ollama).
3. Откройте VS Code Chat и выберите модель из секции Ollama в picker внизу поля ввода.
4. Если модели нет: Command Palette (`Ctrl+Shift+P`) → `Ollama: Refresh Models`, затем `Ollama: Diagnose Models`; проверьте Output channel **Ollama**.

По текущей документации Ollama, расширению требуется VS Code 1.127 или новее; оно обнаруживает модели на `http://127.0.0.1:11434`. Актуальные шаги и требования — [официальный гайд Ollama для VS Code](https://docs.ollama.com/integrations/vscode).

## Вариант 2: выбрать Ollama как provider в Kilo

Если нужны именно режимы/чат Kilo:

1. В Kilo откройте выбор модели или настройки provider.
2. Выберите **Ollama**, а не **Ollama Cloud**: Cloud — удалённый сервис, не локальная служба.
3. Укажите локальный адрес `http://127.0.0.1:11434`, если Kilo показывает поле base URL.
4. Выберите точное имя из `ollama list`, например `qwen3:8b`.
5. Поставьте context window `8192`, output limit примерно `2048`; увеличивайте после замеров.
6. Увеличьте **API Request Timeout**, если CPU-инференс не успевает в стандартные 10 минут: начните, например, с 20 минут, но не маскируйте зависшую генерацию бесконечным таймаутом.
7. Сначала проверьте обычный ответ, затем read-only запрос и только затем вызов инструмента в disposable-репозитории.

Расширение Ollama для VS Code Chat само по себе не выбирает модель для Kilo. Это разные интеграции с общим локальным сервером. В Kilo должны быть отдельно выбраны provider, модель и активный профиль/режим.

Если модель отсутствует в picker, Kilo поддерживает custom models: добавьте модель в конфигурацию Kilo, открытую из настроек (не в `settings.json` VS Code).

```json
{
  "model": "ollama/qwen3:8b",
  "provider": {
    "ollama": {
      "models": {
        "qwen3:8b": {
          "name": "Qwen3 8B (local)",
          "tool_call": true,
          "limit": {
            "context": 8192,
            "output": 2048
          }
        }
      }
    }
  }
}
```

`tool_call: true` сообщает Kilo, что модель следует использовать как поддерживающую вызов инструментов; это **не** гарантирует, что конкретный тег хорошо вызывает инструменты. Удалите этот флаг, если модель фактически не справляется с вызовами. Сверьте схему на установленной версии с [официальным руководством Kilo по Ollama](https://kilo.ai/docs/ai-providers/ollama) и [Custom Models](https://kilo.ai/docs/code-with-ai/agents/custom-models): конфигурация продукта может меняться.

## OpenAI-compatible API для Python или другого клиента

Если клиент не имеет отдельного provider Ollama, для OpenAI-compatible интеграции используйте:

```text
Base URL: http://127.0.0.1:11434/v1
API key: ollama
Model: точное имя из ollama list
```

`ollama` здесь — заполнитель, локальный сервер игнорирует это значение. Пример smoke test:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:11434/v1",
    api_key="ollama",
)

response = client.chat.completions.create(
    model="qwen3:8b",
    messages=[{"role": "user", "content": "Ответь одной строкой: локальный API работает"}],
)
print(response.choices[0].message.content)
```

Сначала убедитесь, что запрос проходит из Python, и только затем диагностируйте настройки Kilo. Подробнее: [документация Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).

## Диагностика

| Симптом | Что проверить |
|---|---|
| `ollama` не распознана в PowerShell | Перезапустить терминал после установки и проверить установку Ollama/PATH. |
| `/api/tags` не отвечает | Запустить Ollama app и проверить localhost; отдельный `ollama serve` запускать только если служба действительно не запущена. |
| API отвечает, моделей нет | Выполнить `ollama list`; нужную модель скачать через `ollama pull <точный-тег>`. |
| Ollama app отвечает, но VS Code Chat не видит модель | Установить расширение Ollama, обновить список через Command Palette, проверить Ollama Output channel и версию VS Code. |
| VS Code Chat модель видит, Kilo — нет | В Kilo независимо выбрать provider **Ollama**, а не Ollama Cloud; сверить тег модели. |
| Обычный ответ работает, tool call — нет | Проверить tool-support модели, режим клиента и минимальный пример; не давать модели write-доступ, пока tool calling не проверен. |
| Timeout или долгий старт | Сократить контекст, отключить MCP для диагностики, проверить `ollama ps`, увеличить таймаут умеренно. |
| Компьютер активно использует pagefile | Закрыть лишние приложения, уменьшить контекст или выбрать модель поменьше; не запускать параллельно несколько генераций. |

## Источники

- [Ollama VS Code integration](https://docs.ollama.com/integrations/vscode)
- [Ollama FAQ](https://docs.ollama.com/faq)
- [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)
- [Kilo: Using Ollama](https://kilo.ai/docs/ai-providers/ollama)
- [Kilo: Custom Models](https://kilo.ai/docs/code-with-ai/agents/custom-models)
