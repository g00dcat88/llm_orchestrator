import sys
import json
import os
from pathlib import Path

# Add project paths to Python sys.path
APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
BACKEND_DIR = PROJECT_DIR / "L-start" / "backend"
sys.path.append(str(BACKEND_DIR))

# Ensure knowledge_base directory exists
KB_DIR = APP_DIR / "knowledge_base"
KB_DIR.mkdir(exist_ok=True, parents=True)


def generate_db_schema():
    print("Генерация схемы базы данных...")
    try:
        from app.models import Base
    except Exception as e:
        print(f"Ошибка импорта Base: {e}")
        return

    output = []
    output.append("=== СХЕМА БАЗЫ ДАННЫХ ERP ООО «Л-СТАРТ» ===")
    output.append("Этот документ описывает таблицы SQLite базы данных, типы полей и связи.\n")

    for table_name, table in Base.metadata.tables.items():
        output.append(f"Таблица: {table_name}")
        output.append("-" * (len(table_name) + 9))
        output.append("Столбцы:")
        for column in table.columns:
            nullable_str = "NULL" if column.nullable else "NOT NULL"
            pk_str = " (PRIMARY KEY)" if column.primary_key else ""
            default_str = f" DEFAULT {column.default.arg}" if column.default else ""
            
            # Connections (Foreign Keys)
            fk_str = ""
            if column.foreign_keys:
                fk = next(iter(column.foreign_keys))
                fk_str = f" -> Ссылка на {fk.column.table.name}({fk.column.name})"
                
            output.append(f"  - {column.name}: {column.type} {nullable_str}{pk_str}{default_str}{fk_str}")
        
        output.append("\n" + "="*40 + "\n")

    schema_file = KB_DIR / "database_schema.txt"
    schema_file.write_text("\n".join(output), encoding="utf-8")
    print(f"Схема БД сохранена в: {schema_file}")


def generate_api_routes():
    print("Генерация документации API-маршрутов...")
    try:
        from app.main import app
    except ImportError as e:
        print(f"Ошибка импорта FastAPI приложения: {e}")
        return

    output = []
    output.append("=== РУКОВОДСТВО ПО API ERP-СИСТЕМЫ (FastAPI) ===")
    output.append("Этот документ содержит перечень всех API-маршрутов бэкенда для интеграции.\n")

    for route in app.routes:
        # We only document routing endpoints with methods
        if hasattr(route, "methods") and route.methods:
            methods = ", ".join(route.methods)
            # Skip standard static/docs routes
            if "/docs" in route.path or "/openapi.json" in route.path or "/static" in route.path:
                continue
                
            output.append(f"Маршрут: {route.path}")
            output.append(f"Методы: {methods}")
            desc = getattr(route, "description", None) or getattr(route, "summary", None)
            if not desc and hasattr(route, "endpoint") and route.endpoint:
                desc = route.endpoint.__doc__
            desc = desc or "Нет описания"
            output.append(f"Описание: {desc.strip()}")
            
            if hasattr(route, "dependant") and route.dependant.query_params:
                params_list = []
                for p in route.dependant.query_params:
                    p_type = "str"
                    if hasattr(p, "field_info") and hasattr(p.field_info, "annotation") and p.field_info.annotation:
                        p_type = getattr(p.field_info.annotation, "__name__", str(p.field_info.annotation))
                    elif hasattr(p, "type_") and p.type_:
                        p_type = getattr(p.type_, "__name__", str(p.type_))
                    elif hasattr(p, "annotation") and p.annotation:
                        p_type = getattr(p.annotation, "__name__", str(p.annotation))
                    params_list.append(f"    * {p.name} ({p_type})")
                if params_list:
                    output.append("Параметры запроса (Query Params):")
                    output.extend(params_list)

            output.append("-" * 30 + "\n")

    api_file = KB_DIR / "api_routes.txt"
    api_file.write_text("\n".join(output), encoding="utf-8")
    print(f"Схема API сохранена в: {api_file}")


def generate_project_structure():
    print("Генерация карты структуры проекта...")
    output = []
    output.append("=== КАРТА СТРУКТУРЫ И ФАЙЛОВ ERP-ПРОЕКТА ===")
    output.append("Этот документ описывает основные папки и назначение файлов в проекте.\n")
    
    structure = """
📁 F:\\Projects\\
  ├── 📁 L-start\\               - Основной проект ERP (FastAPI + Next.js)
  │    ├── 📁 backend\\           - Бэкенд на Python (FastAPI)
  │    │    └── 📁 app\\          - Исходный код бэкенда
  │    │         ├── 📁 models\\  - Описание таблиц базы данных (SQLAlchemy)
  │    │         ├── 📁 schemas\\ - Схемы валидации API (Pydantic)
  │    │         ├── 📁 routers\\ - Эндпоинты API (FastAPI)
  │    │         └── 📁 database\\- Настройка подключения к SQLite (l_start.db)
  │    └── 📁 frontend\\          - Фронтенд на React/Next.js/TypeScript
  │         └── 📁 src\\
  │              ├── 📁 app\\     - Маршрутизация страниц Next.js
  │              └── 📁 components\\- UI-компоненты (включая виджет чата)
  └── 📁 llm_orchestrator\\       - ИИ-Оркестратор и Ассистент Гермес
       ├── 📁 skills\\            - JSON-файлы с системными промптами (core_agent, erp_assistant)
       ├── 📁 sandbox\\           - Папка-песочница для безопасного запуска Python-кода
       ├── 📁 knowledge_base\\    - База знаний (RAG) компании (регламенты, схемы, API)
       ├── 📄 tools.py\\          - Описание всех инструментов ИИ (execute_python, search_knowledge_base)
       └── 📄 generate_project_maps.py - Скрипт автоматического обновления карт проекта
"""
    output.append(structure)
    
    structure_file = KB_DIR / "project_structure.txt"
    structure_file.write_text("\n".join(output), encoding="utf-8")
    print(f"Карта структуры проекта сохранена в: {structure_file}")


if __name__ == "__main__":
    generate_api_routes()
    generate_db_schema()
    generate_project_structure()
    print("\n[Все карты проекта успешно обновлены в Базе Знаний RAG!]")
