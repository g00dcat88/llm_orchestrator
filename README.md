# LLM Orchestrator

Agentic LLM-оркестратор для ERP-системы L-Start. Управляет инструментами, навыками, маршрутизацией и самообучением.

## Назначение

Сервис-оркестратор, который:
- Принимает запросы от пользователя (через Flask API или ERP-фронтенд)
- Классифицирует запрос и определяет нужный scope
- Выбирает LLM-провайдера (локальный, API, роутер)
- Вызывает инструменты (ERP-запросы, Python-песочница, мониторинг)
- Возвращает структурированный ответ

## Модули

### Ключевые компоненты

| Модуль | Файл | Назначение |
|--------|------|------------|
| `main.py` | Agentic loop | Основной цикл: classify → RAG → generate → tools → respond |
| `dispatcher.py` | Классификатор | Определение scope запроса (HR, задачи, код, общий) |
| `router.py` | Роутер провайдеров | Выбор LLM по стратегии (hybrid, local-first, api-first) |
| `conversation.py` | Буфер диалога | История сообщений пользователя |
| `session_store.py` | Хранилище сессий | SQLite для персистентных диалогов и обучения |
| `self_learning.py` | Самообучение | Запись успешных паттернов, поиск похожих примеров |
| `rag.py` | BM25-поиск | Индексация и поиск по базе знаний |
| `skills.py` | Менеджер навыков | Управление системными промптами агентов |
| `tools.py` | Реестр инструментов | ERP-интеграция, Python-песочница, веб-мониторинг |
| `providers.py` | LLM-провайдеры | LlamaServer, OpenAI-compatible, Anthropic, Mock |

### Навыки (Skills)

Специализированные системные промпты для разных задач:

- `general_agent` — Генеральный ассистент
- `hr_agent` — Аналитик персонала
- `fsm_agent` — Секретарь задач
- `schedule_agent` — Диспетчер графиков
- `chat_secretary` — Структурирование чата в отчёты
- `erp_assistant` — Координатор ERP
- `python_coder` — Программист Python
- `web_monitoring` — Аналитик мониторинга

## Архитектура

```
                    ┌─────────────────┐
                    │   ERP Frontend  │
                    │  (Next.js L-Start)│
                    └────────┬────────┘
                             │ POST /api/v1/assistant/messages
                             ▼
                    ┌─────────────────┐
                    │  ERP Backend    │
                    │  (FastAPI)      │
                    └────────┬────────┘
                             │ POST /api/orchestrator/run
                             ▼
┌────────────────────────────────────────────────────────┐
│                  LLM Orchestrator                       │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │Dispatcher│  │   RAG    │  │   Self-Learner       │  │
│  │(classify)│  │ (search) │  │ (patterns, knowledge)│  │
│  └────┬─────┘  └────┬─────┘  └──────────┬───────────┘  │
│       │              │                    │              │
│       ▼              ▼                    ▼              │
│  ┌─────────────────────────────────────────────────┐    │
│  │              run_agentic_loop()                  │    │
│  │  classify → context → generate → tools → respond│    │
│  └─────────────────────────────────────────────────┘    │
│       │              │                    │              │
│       ▼              ▼                    ▼              │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │  Router  │  │  Tools   │  │   SessionStore       │  │
│  │(provider)│  │ (ERP,py) │  │   (SQLite)           │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
└────────────────────────────────────────────────────────┘
         │              │                    │
         ▼              ▼                    ▼
    LLM Provider   ERP Backend          SQLite DB
    (llama/API)    (FastAPI)        (sessions, patterns)
```

## API

### Основные эндпоинты

| Эндпоинт | Метод | Описание |
|-----------|-------|----------|
| `/api/orchestrator/run` | POST | Запуск agentic loop |
| `/api/orchestrator/status` | GET | Статус сервера |
| `/api/orchestrator/skills` | GET | Список навыков |
| `/api/orchestrator/skills/<id>` | POST | Обновление навыка |
| `/api/orchestrator/providers` | GET | Список LLM-провайдеров |
| `/api/orchestrator/providers/<name>/test` | POST | Тест провайдера |
| `/api/orchestrator/session/clear` | POST | Очистка сессии |
| `/api/orchestrator/session/history` | POST | История сессии |
| `/api/orchestrator/learning/patterns` | GET | Изученные паттерны |
| `/api/orchestrator/learning/stats` | GET | Статистика пользователя |
| `/api/orchestrator/learning/feedback` | POST | Обратная связь |

### Запрос agentic loop

```json
POST /api/orchestrator/run
{
  "prompt": "покажи командировки на следующую неделю",
  "user_id": "emp_123",
  "session_id": "sess_abc",
  "skill_id": "schedule_agent",
  "erp_url": "http://127.0.0.1:8000",
  "erp_service_token": "..."
}
```

## Инструменты

| Инструмент | Категория | Описание |
|------------|-----------|----------|
| `get_project_card` | projects | Карточка проекта по коду |
| `get_trip_details` | hr | Детали командировки |
| `list_upcoming_trips` | hr | Список командировок |
| `append_task_details` | projects | Запись в лог задачи |
| `update_task_summary` | projects | Обновление отчёта задачи |
| `consolidate_to_project` | projects | Перенос отчёта в проект |
| `get_task_comments` | projects | Переписка по задаче |
| `search_knowledge_base` | general | Поиск в документации |
| `execute_python` | python_sandbox | Выполнение Python-кода |
| `monitor_web_resource` | web_monitor | Проверка доступности URL |

## База знаний

Файлы в `knowledge_base/`:
- `database_schema.txt` — схема БД ERP
- `api_routes.txt` — документация API
- `project_structure.txt` — структура проекта
- `ui_layout.txt` — описание интерфейса

Индексируются BM25-движком для контекстного поиска.

## Быстрый старт

```bash
pip install -r requirements.txt
python main.py
```

## Стек

- Python 3.11+
- SQLite (сессии, метрики, кэш)
- BM25 (RAG-поиск)
- OpenAI-compatible API (LLM)
