"""Client Tools Factory — создание изолированных ToolRegistry для клиентов.

Базовые инструменты доступны всем клиентам.
Кастомные инструменты — из конфига клиента.
ERP-инструменты — только для клиента "erp".
"""
from __future__ import annotations

from tools import Tool, ToolRegistry
from client_registry import ClientConfig


# Базовые инструменты, доступные всем клиентам
BASE_TOOLS = [
    {
        "name": "execute_python",
        "description": "Выполняет код на Python в изолированной песочнице. Используй для вычислений или обработки данных.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Исходный код Python для выполнения."
                }
            },
            "required": ["code"]
        },
        "category": "python_sandbox",
    },
    {
        "name": "monitor_web_resource",
        "description": "Проверяет состояние веб-ресурса (URL), получает preview-данные и записывает проверку в журнал.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL для проверки."
                }
            },
            "required": ["url"]
        },
        "category": "web_monitor",
    },
    {
        "name": "search_knowledge_base",
        "description": "Ищет информацию в базе знаний по ключевым словам.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Ключевые слова для поиска."
                }
            },
            "required": ["query"]
        },
        "category": "knowledge",
    },
]


def create_client_tool_registry(
    client: ClientConfig,
    erp_tool_registry: ToolRegistry | None = None,
    sandbox=None,
    web_monitor=None,
) -> ToolRegistry:
    """Создать ToolRegistry для конкретного клиента.

    Args:
        client: конфиг клиента
        erp_tool_registry: реестр ERP-инструментов (для клиента "erp")
        sandbox: PythonSandbox инстанс
        web_monitor: WebMonitorTool инстанс
    """
    registry = ToolRegistry()

    # 1. Базовые инструменты (с привязкой к реальным объектам)
    for tool_def in BASE_TOOLS:
        func = None
        if tool_def["name"] == "execute_python" and sandbox:
            func = sandbox.execute_code
        elif tool_def["name"] == "monitor_web_resource" and web_monitor:
            func = web_monitor.monitor
        elif tool_def["name"] == "search_knowledge_base" and erp_tool_registry:
            # Ищем в ERP реестре
            existing = erp_tool_registry.tools.get("search_knowledge_base")
            if existing:
                func = existing.func

        if func:
            registry.register(Tool(
                name=tool_def["name"],
                description=tool_def["description"],
                parameters=tool_def["parameters"],
                func=func,
                category=tool_def.get("category", "general"),
            ))

    # 2. ERP-инструменты для клиента "erp"
    if client.client_id == "erp" and erp_tool_registry:
        for name, tool in erp_tool_registry.tools.items():
            if name not in registry.tools:
                registry.register(tool)

    # 3. Кастомные инструменты клиента (из конфига)
    # Кастомные инструменты пока не имеют привязки к функциям —
    # они используются как описание для LLM (текстовые инструменты)
    for tool_def in client.tools:
        if tool_def.get("name") not in registry.tools:
            # Регистрируем как текстовый инструмент (без func)
            # LLM будет использовать их как описание, а выполнение — через агента
            registry.register(Tool(
                name=tool_def["name"],
                description=tool_def.get("description", ""),
                parameters=tool_def.get("parameters", {"type": "object", "properties": {}}),
                func=lambda *a, **kw: {"ok": False, "error": "Text-only tool, use via agent"},
                category=tool_def.get("category", "custom"),
            ))

    return registry
