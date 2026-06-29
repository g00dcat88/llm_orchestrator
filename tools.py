import os
import subprocess
import sys
from pathlib import Path

class Tool:
    """
    Класс-обертка для инструмента (функции), который может быть вызван моделью.
    """
    def __init__(self, name: str, description: str, parameters: dict, func, category: str = "general"):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func
        self.category = category

    def to_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }

    def execute(self, **kwargs) -> str:
        try:
            return str(self.func(**kwargs))
        except Exception as e:
            return f"Ошибка выполнения инструмента {self.name}: {e}"


class PythonSandbox:
    """
    Безопасная песочница для выполнения кода только внутри определенной папки.
    """
    def __init__(self, sandbox_dir: Path):
        self.sandbox_dir = sandbox_dir.resolve()
        self.sandbox_dir.mkdir(exist_ok=True, parents=True)

    def _install_missing_imports(self, code: str):
        import ast
        try:
            tree = ast.parse(code)
        except Exception:
            return

        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_modules.add(node.module.split('.')[0])

        package_mapping = {
            'bs4': 'beautifulsoup4',
            'yaml': 'pyyaml',
            'sklearn': 'scikit-learn',
            'dateutil': 'python-dateutil',
            'PIL': 'pillow',
            'pg': 'pygresql',
            'mysql': 'mysql-connector-python'
        }

        for module in imported_modules:
            try:
                __import__(module)
            except ImportError:
                pip_name = package_mapping.get(module, module)
                print(f"[Sandbox] Автоматическая установка библиотеки: {pip_name}")
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", pip_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

    def execute_code(self, code: str) -> str:
        # Автоматически доустанавливаем импортируемые ИИ библиотеки
        self._install_missing_imports(code)

        script_path = (self.sandbox_dir / "temp_script.py").resolve()
        
        # Гарантируем, что путь находится внутри папки песочницы
        if not str(script_path).startswith(str(self.sandbox_dir)):
            return "Ошибка безопасности: Попытка выхода за пределы папки песочницы!"

        try:
            script_path.write_text(code, encoding="utf-8")
        except Exception as e:
            return f"Ошибка записи кода в песочницу: {e}"

        try:
            # Запускаем скрипт, принудительно выставляя рабочую директорию в sandbox_dir
            res = subprocess.run(
                [sys.executable, "temp_script.py"],
                cwd=str(self.sandbox_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10
            )
            
            # Удаляем временный файл
            if script_path.exists():
                script_path.unlink()
                
            if res.returncode == 0:
                return res.stdout if res.stdout.strip() else "Скрипт выполнен успешно (вывода нет)."
            else:
                return f"Ошибка выполнения (код возврата {res.returncode}):\n{res.stderr}"
                
        except subprocess.TimeoutExpired:
            if script_path.exists():
                script_path.unlink()
            return "Ошибка: Выполнение превысило тайм-аут в 10 секунд."
        except Exception as e:
            if script_path.exists():
                script_path.unlink()
            return f"Критическая ошибка запуска: {e}"


class ToolRegistry:
    """
    Реестр инструментов, управляющий их регистрацией и вызовами.
    """
    def __init__(self):
        self.tools = {}

    def register(self, tool: Tool):
        self.tools[tool.name] = tool

    def get_schemas(self) -> list:
        return [tool.to_schema() for tool in self.tools.values()]

    def get_schemas_for_scope(self, scope: str) -> list:
        """Returns schemas of tools that belong to a specific scope or are general-purpose."""
        return [
            tool.to_schema()
            for tool in self.tools.values()
            if tool.category == scope or tool.category == "general"
        ]

    def call(self, name: str, arguments: dict) -> str:
        if name not in self.tools:
            return f"Ошибка: Инструмент '{name}' не найден в реестре."
        return self.tools[name].execute(**arguments)


import urllib.request
import urllib.error
import time
import json

class WebMonitorTool:
    """
    Инструмент для мониторинга веб-ресурсов с логированием результатов (учет работы).
    """
    def __init__(self, log_path: Path):
        self.log_path = log_path
        if not self.log_path.exists():
            self.log_path.parent.mkdir(exist_ok=True, parents=True)
            self.log_path.write_text("[]", encoding="utf-8")

    def monitor(self, url: str) -> str:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        status_code = -1
        message = ""
        success = False
        data_preview = ""
        content_len = 0

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "LLMOrchestrator-Monitor/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status_code = resp.status
                content = resp.read()
                content_len = len(content)
                success = True
                message = "Успешно"
                try:
                    text = content.decode("utf-8")
                    data_preview = text[:300] + ("..." if len(text) > 300 else "")
                except:
                    data_preview = f"[Бинарные данные, {content_len} байт]"
        except urllib.error.HTTPError as e:
            status_code = e.code
            message = f"HTTP Error: {e.reason}"
            data_preview = f"Ошибка HTTP {e.code}"
        except urllib.error.URLError as e:
            message = f"URL Error: {e.reason}"
            data_preview = "Ошибка подключения к хосту"
        except Exception as e:
            message = str(e)
            data_preview = "Внутреннее исключение"

        # Сохранение записи лога (учет и контроль работы)
        record = {
            "timestamp": timestamp,
            "url": url,
            "success": success,
            "status_code": status_code,
            "message": message,
            "data_length": content_len
        }

        try:
            logs = []
            if self.log_path.exists():
                try:
                    logs = json.loads(self.log_path.read_text(encoding="utf-8"))
                except:
                    logs = []
            logs.append(record)
            self.log_path.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as log_err:
            print(f"Ошибка сохранения лога мониторинга: {log_err}")

        return (
            f"[Мониторинг URL]: {url}\n"
            f"[Время проверки]: {timestamp}\n"
            f"[Статус]: {status_code} ({message})\n"
            f"[Данные (превью)]: {data_preview}\n"
            f"[Учет работы]: Лог сохранен в {self.log_path.name}"
        )

import urllib.parse

class ERPIntegrationTools:
    """
    Инструменты для интеграции Оркестратора с REST API L-Start ERP.
    """
    def __init__(self, base_url: str = "http://localhost:8000", service_token: str = None):
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token

    def _make_request(self, url, data=None, headers=None, method=None):
        req_headers = {}
        if headers:
            req_headers.update(headers)
        if getattr(self, "service_token", None):
            req_headers["X-ERP-Service-Token"] = self.service_token
        return urllib.request.Request(url, data=data, headers=req_headers, method=method)

    def get_project_card(self, project_code: str) -> str:
        """
        Получить информацию о проекте по его коду.
        """
        url = f"{self.base_url}/api/v1/hr/projects?search={urllib.parse.quote(project_code)}"
        try:
            req = self._make_request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if not data:
                    return f"Проект с кодом {project_code} не найден в ERP."
                p = data[0]
                return (
                    f"Карточка Проекта:\n"
                    f"- ID: {p.get('id')}\n"
                    f"- Код: {p.get('code')}\n"
                    f"- Год: {p.get('year')}\n"
                    f"- Направление: {p.get('direction_display') or p.get('direction')}\n"
                    f"- Заказчик: {p.get('customer') or '—'}\n"
                    f"- Договор: {p.get('contract_info') or '—'}\n"
                    f"- Статус: {p.get('status_display') or p.get('status') or '—'}\n"
                    f"- Оборудование: {p.get('equipment_list') or '—'}\n"
                    f"- Комментарии / История:\n{p.get('comments') or '—'}"
                )
        except Exception as e:
            return f"Ошибка при получении карточки проекта: {e}"

    def get_trip_details(self, schedule_id: int) -> str:
        """
        Получить параметры командировки по ее ID.
        """
        url = f"{self.base_url}/api/v1/hr/employee-schedules/{schedule_id}"
        try:
            req = self._make_request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                s = json.loads(resp.read().decode('utf-8'))
                return (
                    f"Параметры командировки:\n"
                    f"- ID Командировки: {s.get('id')}\n"
                    f"- Имя сотрудника: {s.get('employee_name')}\n"
                    f"- Код проекта: {s.get('project_code')}\n"
                    f"- Период: {s.get('start_date')[:10]} — {s.get('end_date')[:10]}\n"
                    f"- Цель поездки: {s.get('notes') or '—'}"
                )
        except Exception as e:
            return f"Ошибка при получении деталей командировки: {e}"

    def append_task_details(self, work_order_id: int, text: str, author_name: str) -> str:
        """
        Дополнить существующий наряд новой записью лога работ.
        """
        get_url = f"{self.base_url}/api/v1/hr/work-orders/{work_order_id}"
        try:
            req = self._make_request(get_url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                wo = json.loads(resp.read().decode('utf-8'))
                
            current_log = wo.get("history_log") or ""
            date_str = time.strftime("%d.%m.%Y %H:%M")
            new_log_entry = f"\n\n[{date_str}] {author_name} (записано через ИИ-Ассистент Гермес):\n{text}"
            updated_log = current_log.strip() + new_log_entry
            
            put_url = f"{self.base_url}/api/v1/hr/work-orders/{work_order_id}"
            payload = {
                "history_log": updated_log
            }
            data = json.dumps(payload).encode('utf-8')
            req = self._make_request(
                put_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="PUT"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                # This will also trigger FastAPI side project comments consolidation
                json.loads(resp.read().decode('utf-8'))
                
            return f"Наряд #{work_order_id} успешно дополнен отчетом от {author_name}."
        except Exception as e:
            return f"Ошибка при дополнении наряда: {e}"

    def consolidate_to_project(self, project_id: int, summary_text: str) -> str:
        """
        Записать отчет в карточку проекта.
        """
        try:
            put_url = f"{self.base_url}/api/v1/hr/projects/{project_id}"
            payload = {
                "comments": summary_text
            }
            data = json.dumps(payload).encode('utf-8')
            req = self._make_request(
                put_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="PUT"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                json.loads(resp.read().decode('utf-8'))
            return f"Отчет успешно сохранен в карточке проекта #{project_id}."
        except Exception as e:
            return f"Ошибка при консолидации отчета в проект: {e}"

    def get_task_comments(self, work_order_id: int) -> str:
        """
        Получить историю сообщений и комментариев по задаче.
        """
        url = f"{self.base_url}/api/v1/hr/work-orders/{work_order_id}/comments"
        try:
            req = self._make_request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                comments = json.loads(resp.read().decode('utf-8'))
                if not comments:
                    return f"Чат по задаче #{work_order_id} пуст."
                
                log = f"История обсуждения по задаче #{work_order_id}:\n"
                for c in comments:
                    is_sys = " [СИСТЕМНОЕ]" if c.get("is_system") else ""
                    log += f"- {c.get('sender_name')}{is_sys} [{c.get('created_at')}]: {c.get('text')}\n"
                return log
        except Exception as e:
            return f"Ошибка при получении комментариев по задаче: {e}"

    def update_task_summary(self, work_order_id: int, summary_text: str) -> str:
        """
        Обновить официальный сводный отчет по задаче (history_log).
        """
        put_url = f"{self.base_url}/api/v1/hr/work-orders/{work_order_id}"
        try:
            payload = {
                "history_log": summary_text
            }
            data = json.dumps(payload).encode('utf-8')
            req = self._make_request(
                put_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="PUT"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                json.loads(resp.read().decode('utf-8'))
            return f"Сводный отчет по задаче #{work_order_id} успешно обновлен."
        except Exception as e:
            return f"Ошибка при обновлении сводного отчета задачи: {e}"

    def list_upcoming_trips(self) -> str:
        """
        Получить список всех запланированных и активных командировок сотрудников.
        """
        url = f"{self.base_url}/api/v1/hr/employee-schedules"
        try:
            req = self._make_request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                schedules = json.loads(resp.read().decode('utf-8'))
                if not schedules:
                    return "В системе нет запланированных или активных командировок."
                
                lines = ["Список командировок:"]
                for s in schedules:
                    display_type = s.get('type_display') or s.get('type', '')
                    lines.append(
                        f"- ID командировки (графика): {s.get('id')}, Сотрудник: {s.get('employee_name')}, "
                        f"Проект: {s.get('project_code')}, "
                        f"Период: {s.get('start_date')[:10]} - {s.get('end_date')[:10]}, "
                        f"Тип: {display_type}, Цель: {s.get('notes') or '—'}"
                    )
                return "\n".join(lines)
        except Exception as e:
            return f"Ошибка при получении списка командировок: {e}"

    def search_knowledge_base(self, query: str) -> str:
        """
        Ищет информацию в базе знаний компании (инструкции, регламенты, регламенты ПНР, контакты).
        Параметр 'query' — ключевые слова для поиска.
        """
        # Dynamically determine the path of knowledge_base relative to this file
        current_dir = Path(__file__).resolve().parent
        knowledge_dir = current_dir / "knowledge_base"
        if not knowledge_dir.exists():
            knowledge_dir.mkdir(exist_ok=True, parents=True)
            readme = knowledge_dir / "README.txt"
            readme.write_text("База знаний Л-Старт. Поместите сюда текстовые инструкции.", encoding="utf-8")
            
        results = []
        keywords = [k.lower().strip() for k in query.split() if len(k.strip()) > 2]
        if not keywords:
            return "Запрос слишком короткий для поиска."

        for file_path in knowledge_dir.glob("**/*"):
            if file_path.is_file() and file_path.suffix in [".txt", ".md"]:
                try:
                    text = file_path.read_text(encoding="utf-8")
                    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                    for p_idx, para in enumerate(paragraphs):
                        score = sum(1 for kw in keywords if kw in para.lower())
                        if score > 0:
                            results.append({
                                "file": file_path.name,
                                "paragraph": para,
                                "score": score
                            })
                except Exception as e:
                    print(f"Ошибка чтения файла {file_path.name}: {e}")

        if not results:
            return "В локальной базе знаний ничего не найдено по вашему запросу."

        results.sort(key=lambda x: x["score"], reverse=True)
        top_results = results[:3]
        
        output = [f"Результаты поиска в базе знаний по запросу '{query}':"]
        for r in top_results:
            output.append(f"--- Источник: {r['file']} (Релевантность: {r['score']}) ---\n{r['paragraph']}\n")
        return "\n".join(output)

