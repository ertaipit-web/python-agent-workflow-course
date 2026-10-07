# Источники и материалы для дальнейшего изучения

Программа составлена как самостоятельный практический курс для Python-разработчиков. Источники ниже использовались для изучения учебного формата, сравнения подходов к агентной оркестрации и проверки технических инструкций по локальным моделям. Они не означают, что курс следует целиком по конкретному фреймворку или продукту.

## Учебные программы и примеры практикумов

- [Первый практикум по вайбкодингу — Zerocoder](https://zerocoder.ru/pervyy-praktikum-po-vaybkodingu) — пример практико-ориентированного формата и создания работающего результата.
- [Практикум Claude Code — Zerocoder](https://zerocoder.ru/claude-code) — источник исходного интереса к Claude Code и демонстрации мультиагентной команды.
- [AI Agents for Beginners — Microsoft](https://github.com/microsoft/ai-agents-for-beginners) — обзор базовых паттернов построения агентов; использован для сопоставления структуры и последовательности тем. Курс здесь рассчитан на более опытную аудиторию.
- [AI Agents in LangGraph — DeepLearning.AI](https://www.deeplearning.ai/courses/ai-agents-in-langgraph/) — практическое построение агента на Python, управление состоянием и human-in-the-loop.
- [Multi AI Agent Systems with crewAI — DeepLearning.AI](https://www.deeplearning.ai/courses/multi-ai-agent-systems-with-crewai/) — специализация ролей, сотрудничество, память и guardrails.

## Фреймворки и SDK агентов

- [LangGraph: overview](https://docs.langchain.com/oss/python/langgraph/overview) — управление состоянием и длительными workflow, сочетание детерминированных узлов с модельными шагами, human-in-the-loop.
- [CrewAI documentation](https://docs.crewai.com/) — агенты, crews и flows, инструменты, память, guardrails и наблюдаемость.
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) — handoffs, tools, guardrails и встроенный tracing; использован как один из примеров Python-first SDK.
- [Claude Agent SDK — Anthropic](https://code.claude.com/docs/en/agent-sdk/overview) — программный запуск агента, инструменты, permissions, sessions и hooks.
- [Microsoft Agent Framework overview](https://learn.microsoft.com/en-us/agent-framework/overview/) — агентные и мультиагентные workflow; использован для сравнения современного framework-подхода.
- [AutoGen documentation — Microsoft](https://microsoft.github.io/autogen/stable/) — event-driven и распределённые мультиагентные workflow; включён в обзор альтернатив.

## Anthropic — current agent engineering

Новые инженерные материалы Anthropic 2025–2026 годов дополняют базовые workflow patterns конкретными практиками для context, tools, долгих запусков и containment:

- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — контекст как информация и состояние, доступные модели; ограниченный attention budget и отбор релевантного контекста.
- [Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents) — tool как интерфейс агента со средой: ясная ответственность, входы, выходы и пригодность к использованию.
- [Advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use) — поиск и загрузка инструментов по мере необходимости вместо помещения всего большого набора определений в каждый вызов.
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — долгие coding runs, инкрементальный прогресс, handoff-артефакты и восстановление между сессиями.
- [How we contain Claude](https://www.anthropic.com/engineering/how-we-contain-claude) — ограничение blast radius через техническое containment, sandboxing и управление доступом; human approval не заменяет эти меры.
- [Building effective agents](https://www.anthropic.com/research/building-effective-agents) — базовые workflow patterns (2024). Это фундаментальный материал, а не руководство по сегодняшнему tooling: более новые статьи отражают дальнейшее развитие agent engineering.

## Локальные модели и интеграция с инструментами

- Установка Ollama: [Windows](https://ollama.com/download/windows), [macOS](https://ollama.com/download/mac), [Linux](https://docs.ollama.com/linux); также [общая страница загрузки](https://ollama.com/download) и [FAQ](https://docs.ollama.com/faq) — установка, работа локального сервера и типовые вопросы.
- Каталог моделей Ollama: [Qwen3](https://ollama.com/library/qwen3) и [Qwen2.5-Coder](https://ollama.com/library/qwen2.5-coder) — сверка названий и доступных тегов моделей, рекомендованных для начальных экспериментов на ограниченной конфигурации.
- [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility) — подключение совместимых клиентов и проверка локального API.
- [Ollama integration for VS Code](https://docs.ollama.com/integrations/vscode) — подключение локальной модели к VS Code Chat.
- Документация Kilo: [Ollama provider](https://kilo.ai/docs/ai-providers/ollama) и [custom models](https://kilo.ai/docs/code-with-ai/agents/custom-models) — отдельная настройка provider и пользовательских моделей в Kilo Code.

## Retrieval и RAG

Материалы для компактной RAG-лаборатории и для объяснения, почему retrieval измеряют, а не считают заданным:

- [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401) — исходная работа по RAG (Lewis et al., NeurIPS 2020): разделение параметрической памяти модели и непараметрической памяти индекса. Отсюда же идея передавать provenance вместе с найденным фрагментом.
- [Effective context engineering for AI agents — Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — общий принцип отбора релевантного контекста, к которому подключается retrieval: в модель попадает только необходимое для текущего шага.

## Интеграции, доступ и least privilege

- [REST API endpoints for issues — GitHub](https://docs.github.com/en/rest/issues/issues) — формат реального issue API, на который ориентирована лабораторная интеграция.
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html) — методы, идемпотентность, коды состояния и семантика ошибок, на которых построен клиент и retry для чтения.
- [OWASP Cheat Sheet: Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — deny by default, least privilege и проверка прав на каждом запросе.
- [OWASP Cheat Sheet: AI Agent Security](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html) — безопасность инструментов агента, разделение read и high-impact действий, human-in-the-loop, валидация входа и выхода.

Материалы статей Anthropic ниже покрывают и business framing: когда агент не нужен и почему workflow лучше одиночного агента, — см. [Building effective agents](https://www.anthropic.com/research/building-effective-agents).

## Как читать рекомендации

Описания продуктов, API, доступность курсов, требования редакторов и теги моделей со временем меняются. Проверяйте актуальную документацию перед установкой или настройкой. Рекомендации по запуску на компьютере с 14 ГБ RAM — осторожная отправная точка для экспериментов, а не гарантия скорости или качества: результат зависит от GPU/VRAM, CPU, контекста и параллельно запущенных приложений.

Материалы использованы как источники идей и технической сверки; формулировки, задания, архитектура курса и практики безопасности разработаны отдельно для этого курса.
